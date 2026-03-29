from django.core.management import call_command
from django.test import TestCase

from db_monitor.collectors import collect_stats_snapshot
from db_monitor.heuristics import analyze_snapshot
from db_monitor.services.comparison import compare_snapshots
from db_monitor.models import AnalysisFinding, IndexStatSnapshot, QueryStatSnapshot, StatsSnapshot, TableStatSnapshot


class CollectorFallbackTests(TestCase):
    def test_collect_stats_snapshot_skips_on_sqlite(self):
        snapshot, summary = collect_stats_snapshot(label="sqlite-test", environment="test")

        self.assertEqual(snapshot.status, StatsSnapshot.Status.SKIPPED)
        self.assertEqual(snapshot.database_vendor, "sqlite")
        self.assertEqual(snapshot.query_stats.count(), 0)
        self.assertIn("requires PostgreSQL", snapshot.notes)
        self.assertEqual(summary["query_stats"], 0)

    def test_collect_stats_command_creates_snapshot(self):
        call_command("collect_stats", label="command-test", environment="test")

        snapshot = StatsSnapshot.objects.get(label="command-test")
        self.assertEqual(snapshot.status, StatsSnapshot.Status.SKIPPED)


class AnalysisHeuristicsTests(TestCase):
    def setUp(self):
        self.snapshot = StatsSnapshot.objects.create(
            label="analysis-target",
            environment="test",
            database_vendor="postgresql",
            database_name="grafana_clone",
            status=StatsSnapshot.Status.COMPLETED,
        )
        QueryStatSnapshot.objects.bulk_create(
            [
                QueryStatSnapshot(
                    snapshot=self.snapshot,
                    queryid="slow-1",
                    query_text_normalized="SELECT * FROM orders WHERE status = 'paid'",
                    calls=30,
                    total_exec_time=9000,
                    mean_exec_time=300,
                    min_exec_time=100,
                    max_exec_time=1200,
                    rows=500,
                ),
                QueryStatSnapshot(
                    snapshot=self.snapshot,
                    queryid="hot-1",
                    query_text_normalized="SELECT id, name FROM product_listing_view",
                    calls=1200,
                    total_exec_time=15000,
                    mean_exec_time=12,
                    min_exec_time=2,
                    max_exec_time=40,
                    rows=120000,
                ),
            ]
        )
        IndexStatSnapshot.objects.create(
            snapshot=self.snapshot,
            schema_name="public",
            table_name="shop_product",
            index_name="shop_product_stock_idx",
            idx_scan=0,
            index_size_bytes=8 * 1024 * 1024,
        )
        TableStatSnapshot.objects.create(
            snapshot=self.snapshot,
            schema_name="public",
            table_name="shop_order",
            seq_scan=500,
            idx_scan=20,
            n_live_tup=50000,
            n_dead_tup=500,
            vacuum_count=0,
            autovacuum_count=2,
            analyze_count=0,
            autoanalyze_count=4,
        )

    def test_analyze_snapshot_creates_findings_for_mvp_rules(self):
        snapshot, summary = analyze_snapshot(self.snapshot)

        self.assertEqual(snapshot.id, self.snapshot.id)
        self.assertEqual(summary["created"], 5)
        self.assertEqual(summary["by_type"]["slow_query"], 1)
        self.assertEqual(summary["by_type"]["hot_query"], 2)
        self.assertEqual(summary["by_type"]["unused_index"], 1)
        self.assertEqual(summary["by_type"]["seq_scan_heavy_table"], 1)
        self.assertEqual(AnalysisFinding.objects.filter(snapshot=self.snapshot).count(), 5)

    def test_analyze_stats_command_replaces_existing_findings(self):
        AnalysisFinding.objects.create(
            snapshot=self.snapshot,
            type="old",
            severity="low",
            title="Old finding",
            description="Old finding",
            object_type="query",
            object_name="legacy",
        )

        call_command("analyze_stats", snapshot_id=self.snapshot.id)

        findings = AnalysisFinding.objects.filter(snapshot=self.snapshot)
        self.assertEqual(findings.count(), 5)
        self.assertFalse(findings.filter(type="old").exists())


class SnapshotComparisonTests(TestCase):
    def setUp(self):
        self.before = StatsSnapshot.objects.create(
            label="before",
            environment="baseline",
            database_vendor="postgresql",
            database_name="grafana_clone",
            status=StatsSnapshot.Status.COMPLETED,
        )
        self.after = StatsSnapshot.objects.create(
            label="after",
            environment="optimized",
            database_vendor="postgresql",
            database_name="grafana_clone",
            status=StatsSnapshot.Status.COMPLETED,
        )

        QueryStatSnapshot.objects.bulk_create(
            [
                QueryStatSnapshot(
                    snapshot=self.before,
                    queryid="order-history",
                    query_text_normalized="SELECT * FROM shop_order WHERE user_id = $1",
                    calls=120,
                    total_exec_time=9600,
                    mean_exec_time=80,
                    min_exec_time=10,
                    max_exec_time=200,
                    rows=1200,
                ),
                QueryStatSnapshot(
                    snapshot=self.before,
                    queryid="catalog-search",
                    query_text_normalized="SELECT * FROM shop_product WHERE name ILIKE $1",
                    calls=80,
                    total_exec_time=4000,
                    mean_exec_time=50,
                    min_exec_time=8,
                    max_exec_time=120,
                    rows=800,
                ),
            ]
        )
        QueryStatSnapshot.objects.bulk_create(
            [
                QueryStatSnapshot(
                    snapshot=self.after,
                    queryid="order-history",
                    query_text_normalized="SELECT * FROM shop_order WHERE user_id = $1",
                    calls=120,
                    total_exec_time=2400,
                    mean_exec_time=20,
                    min_exec_time=5,
                    max_exec_time=60,
                    rows=1200,
                ),
                QueryStatSnapshot(
                    snapshot=self.after,
                    queryid="catalog-search",
                    query_text_normalized="SELECT * FROM shop_product WHERE name ILIKE $1",
                    calls=110,
                    total_exec_time=5500,
                    mean_exec_time=50,
                    min_exec_time=8,
                    max_exec_time=125,
                    rows=1100,
                ),
            ]
        )

        TableStatSnapshot.objects.create(
            snapshot=self.before,
            schema_name="public",
            table_name="shop_product",
            seq_scan=600,
            idx_scan=150,
            n_live_tup=8000,
            n_dead_tup=300,
            vacuum_count=0,
            autovacuum_count=1,
            analyze_count=0,
            autoanalyze_count=1,
        )
        TableStatSnapshot.objects.create(
            snapshot=self.after,
            schema_name="public",
            table_name="shop_product",
            seq_scan=200,
            idx_scan=420,
            n_live_tup=8100,
            n_dead_tup=180,
            vacuum_count=0,
            autovacuum_count=2,
            analyze_count=0,
            autoanalyze_count=2,
        )

        IndexStatSnapshot.objects.create(
            snapshot=self.before,
            schema_name="public",
            table_name="shop_product",
            index_name="shop_product_stock_idx",
            idx_scan=0,
            index_size_bytes=8 * 1024 * 1024,
        )
        IndexStatSnapshot.objects.create(
            snapshot=self.after,
            schema_name="public",
            table_name="shop_product",
            index_name="shop_product_stock_idx",
            idx_scan=0,
            index_size_bytes=8 * 1024 * 1024,
        )

        AnalysisFinding.objects.create(
            snapshot=self.before,
            type="slow_query",
            severity="high",
            title="Slow order history query",
            description="Before optimization.",
            object_type="query",
            object_name="order-history",
        )
        AnalysisFinding.objects.create(
            snapshot=self.before,
            type="seq_scan_heavy_table",
            severity="medium",
            title="Product table scans",
            description="Before optimization.",
            object_type="table",
            object_name="public.shop_product",
        )
        AnalysisFinding.objects.create(
            snapshot=self.after,
            type="hot_query",
            severity="medium",
            title="Catalog search is still hot",
            description="After optimization.",
            object_type="query",
            object_name="catalog-search",
        )

    def test_compare_snapshots_returns_before_after_summary(self):
        summary = compare_snapshots(self.before, self.after, top=3)

        self.assertEqual(summary["findings"]["totals"]["before"], 2)
        self.assertEqual(summary["findings"]["totals"]["after"], 1)
        self.assertEqual(summary["findings"]["totals"]["delta"], -1)
        self.assertEqual(summary["queries"]["totals"]["before"]["total_exec_time"], 13600)
        self.assertEqual(summary["queries"]["totals"]["after"]["total_exec_time"], 7900)
        self.assertEqual(summary["tables"]["top_seq_scan_decreases"][0]["table"], "public.shop_product")
        self.assertEqual(summary["findings"]["resolved"][0]["type"], "seq_scan_heavy_table")
        self.assertEqual(summary["findings"]["new"][0]["type"], "hot_query")

    def test_compare_snapshots_command_supports_json_output(self):
        out = []
        call_command("compare_snapshots", str(self.before.id), str(self.after.id), "--format=json", stdout=Buffer(out))

        rendered = "".join(out)
        self.assertIn('"snapshot_a"', rendered)
        self.assertIn('"snapshot_b"', rendered)
        self.assertIn('"findings"', rendered)


class Buffer:
    def __init__(self, output):
        self.output = output

    def write(self, message):
        self.output.append(message)
