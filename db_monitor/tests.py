from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from db_monitor.collectors import collect_stats_snapshot
from db_monitor.heuristics import analyze_snapshot
from db_monitor.services.comparison import compare_snapshots
from db_monitor.services.index_experiments import recommend_experiment_indexes
from db_monitor.services.reporting import get_comparison_report, get_dashboard_overview, get_snapshot_report
from db_monitor.models import AnalysisFinding, IndexStatSnapshot, QueryStatSnapshot, StatsSnapshot, TableStatSnapshot
from db_monitor.models import ExperimentIndexDefinition, ExperimentIndexGroup
from db_monitor.services.benchmark_indexes import TRAFFIC_PRESETS, _effective_concurrency, _operation_rows
from db_monitor.services.query_classification import classify_sql_operation
from load_simulator.models import WorkloadRun


class CollectorFallbackTests(TestCase):
    def test_collect_stats_snapshot_skips_on_sqlite(self):
        snapshot, summary = collect_stats_snapshot(label="sqlite-test", environment="test")

        self.assertEqual(snapshot.status, StatsSnapshot.Status.SKIPPED)
        self.assertEqual(snapshot.database_vendor, "sqlite")
        self.assertEqual(snapshot.query_stats.count(), 0)
        self.assertIn("requires PostgreSQL", snapshot.notes)
        self.assertEqual(summary["query_stats"], 0)

    def test_collect_stats_command_creates_snapshot(self):
        WorkloadRun.objects.create(scenario="catalog", seed=99, operations=3)

        call_command("collect_stats", label="command-test", environment="test")

        snapshot = StatsSnapshot.objects.get(label="command-test")
        self.assertEqual(snapshot.status, StatsSnapshot.Status.SKIPPED)
        self.assertEqual(snapshot.workload_runs.count(), 1)
        self.assertEqual(snapshot.metadata_json["workload_run"]["scenario"], "catalog")


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

    def test_analyze_snapshot_flags_covering_index_candidate(self):
        QueryStatSnapshot.objects.create(
            snapshot=self.snapshot,
            queryid="catalog-covering",
            query_text_normalized=(
                "SELECT id, name, slug, price FROM shop_product "
                "WHERE is_active = true AND created_at >= $1 ORDER BY created_at DESC LIMIT 50"
            ),
            calls=100,
            total_exec_time=8000,
            mean_exec_time=80,
            min_exec_time=10,
            max_exec_time=200,
            rows=5000,
        )

        _, summary = analyze_snapshot(self.snapshot)

        self.assertGreaterEqual(summary["by_type"]["covering_index_candidate"], 1)
        finding = AnalysisFinding.objects.filter(snapshot=self.snapshot, type="covering_index_candidate").first()
        self.assertEqual(finding.evidence_json["suggested_index"], "shop_product_covering_catalog_idx")

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
            metadata_json={
                "index_experiment": {
                    "mode": "without_indexes",
                    "indexes": [
                        {
                            "name": "shop_product_created_at_idx",
                            "table": "shop_product",
                            "description": "Recent product filtering and newest-product sorting",
                            "present": False,
                        }
                    ],
                }
            },
        )
        self.after = StatsSnapshot.objects.create(
            label="after",
            environment="optimized",
            database_vendor="postgresql",
            database_name="grafana_clone",
            status=StatsSnapshot.Status.COMPLETED,
            metadata_json={
                "index_experiment": {
                    "mode": "with_indexes",
                    "indexes": [
                        {
                            "name": "shop_product_created_at_idx",
                            "table": "shop_product",
                            "description": "Recent product filtering and newest-product sorting",
                            "present": True,
                        }
                    ],
                }
            },
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
        self.assertEqual(summary["index_experiment"]["before_mode"], "without_indexes")
        self.assertEqual(summary["index_experiment"]["after_mode"], "with_indexes")
        self.assertEqual(summary["index_experiment"]["changes"][0]["change"], "added")
        self.assertEqual(summary["queries"]["top_improvements"][0]["mean_exec_time"]["scale_max"], 80)
        self.assertIn("SELECT", summary["queries"]["by_operation"])
        self.assertEqual(summary["queries"]["read_totals"]["calls"]["before"], 200)

    def test_compare_snapshots_command_supports_json_output(self):
        out = []
        call_command("compare_snapshots", str(self.before.id), str(self.after.id), "--format=json", stdout=Buffer(out))

        rendered = "".join(out)
        self.assertIn('"snapshot_a"', rendered)
        self.assertIn('"snapshot_b"', rendered)
        self.assertIn('"findings"', rendered)

    def test_compare_snapshots_excludes_transaction_control_and_zero_delta_entries(self):
        QueryStatSnapshot.objects.create(
            snapshot=self.before,
            queryid="begin-query",
            query_text_normalized="BEGIN",
            calls=10,
            total_exec_time=1.0,
            mean_exec_time=0.1,
            min_exec_time=0.1,
            max_exec_time=0.1,
            rows=0,
        )
        QueryStatSnapshot.objects.create(
            snapshot=self.after,
            queryid="begin-query",
            query_text_normalized="BEGIN",
            calls=10,
            total_exec_time=1.0,
            mean_exec_time=0.1,
            min_exec_time=0.1,
            max_exec_time=0.1,
            rows=0,
        )
        QueryStatSnapshot.objects.create(
            snapshot=self.before,
            queryid="steady-query",
            query_text_normalized="SELECT 1",
            calls=10,
            total_exec_time=5.0,
            mean_exec_time=0.5,
            min_exec_time=0.5,
            max_exec_time=0.5,
            rows=10,
        )
        QueryStatSnapshot.objects.create(
            snapshot=self.after,
            queryid="steady-query",
            query_text_normalized="SELECT 1",
            calls=10,
            total_exec_time=5.0,
            mean_exec_time=0.5,
            min_exec_time=0.5,
            max_exec_time=0.5,
            rows=10,
        )

        summary = compare_snapshots(self.before, self.after, top=10)
        rendered_labels = [entry["query_label"] for entry in summary["queries"]["top_improvements"]]
        rendered_labels += [entry["query_label"] for entry in summary["queries"]["top_regressions"]]

        self.assertNotIn("BEGIN", rendered_labels)
        self.assertNotIn("SELECT 1", rendered_labels)

    def test_compare_snapshots_matches_same_query_text_even_when_queryid_changes(self):
        QueryStatSnapshot.objects.create(
            snapshot=self.before,
            queryid="before-created-at",
            query_text_normalized="SELECT * FROM shop_product ORDER BY created_at DESC LIMIT 20",
            calls=40,
            total_exec_time=800.0,
            mean_exec_time=20.0,
            min_exec_time=8.0,
            max_exec_time=55.0,
            rows=800,
        )
        QueryStatSnapshot.objects.create(
            snapshot=self.after,
            queryid="after-created-at",
            query_text_normalized="SELECT * FROM shop_product ORDER BY created_at DESC LIMIT 20",
            calls=40,
            total_exec_time=200.0,
            mean_exec_time=5.0,
            min_exec_time=2.0,
            max_exec_time=20.0,
            rows=800,
        )

        summary = compare_snapshots(self.before, self.after, top=5)
        labels = [entry["query_label"] for entry in summary["queries"]["top_improvements"]]

        self.assertTrue(
            any("SELECT * FROM shop_product ORDER BY created_at DESC LIMIT 20" in label for label in labels)
        )
        created_at_entry = next(
            entry
            for entry in summary["queries"]["top_improvements"]
            if "created_at DESC LIMIT 20" in entry["query_label"]
        )
        self.assertLess(created_at_entry["total_exec_time"]["after"], created_at_entry["total_exec_time"]["before"])
        self.assertEqual(created_at_entry["mean_exec_time"]["scale_max"], 20.0)


class Buffer:
    def __init__(self, output):
        self.output = output

    def write(self, message):
        self.output.append(message)


class ReportingDashboardTests(TestCase):
    def setUp(self):
        self.before = StatsSnapshot.objects.create(
            label="before",
            environment="baseline",
            database_vendor="postgresql",
            database_name="grafana_clone",
            status=StatsSnapshot.Status.COMPLETED,
            metadata_json={
                "counts": {"query_stats": 2, "table_stats": 1, "index_stats": 1, "activities": 0},
                "index_experiment": {
                    "mode": "without_indexes",
                    "indexes": [
                        {
                            "name": "shop_product_created_at_idx",
                            "table": "shop_product",
                            "description": "Recent product filtering and newest-product sorting",
                            "present": False,
                        }
                    ],
                },
            },
        )
        self.after = StatsSnapshot.objects.create(
            label="after",
            environment="optimized",
            database_vendor="postgresql",
            database_name="grafana_clone",
            status=StatsSnapshot.Status.DEGRADED,
            metadata_json={
                "counts": {"query_stats": 2, "table_stats": 1, "index_stats": 1, "activities": 1},
                "index_experiment": {
                    "mode": "with_indexes",
                    "indexes": [
                        {
                            "name": "shop_product_created_at_idx",
                            "table": "shop_product",
                            "description": "Recent product filtering and newest-product sorting",
                            "present": True,
                        }
                    ],
                },
            },
        )

        QueryStatSnapshot.objects.bulk_create(
            [
                QueryStatSnapshot(
                    snapshot=self.before,
                    queryid="before-query",
                    query_text_normalized="SELECT * FROM shop_order WHERE user_id = $1",
                    calls=100,
                    total_exec_time=8000,
                    mean_exec_time=80,
                    min_exec_time=10,
                    max_exec_time=200,
                    rows=900,
                ),
                QueryStatSnapshot(
                    snapshot=self.after,
                    queryid="after-query",
                    query_text_normalized="SELECT * FROM shop_product WHERE name ILIKE $1",
                    calls=200,
                    total_exec_time=15000,
                    mean_exec_time=75,
                    min_exec_time=15,
                    max_exec_time=220,
                    rows=1300,
                ),
            ]
        )
        TableStatSnapshot.objects.create(
            snapshot=self.after,
            schema_name="public",
            table_name="shop_product",
            seq_scan=350,
            idx_scan=40,
            n_live_tup=40000,
            n_dead_tup=500,
            vacuum_count=0,
            autovacuum_count=1,
            analyze_count=0,
            autoanalyze_count=1,
        )
        TableStatSnapshot.objects.create(
            snapshot=self.before,
            schema_name="public",
            table_name="shop_product",
            seq_scan=150,
            idx_scan=70,
            n_live_tup=38000,
            n_dead_tup=800,
            vacuum_count=0,
            autovacuum_count=1,
            analyze_count=0,
            autoanalyze_count=1,
        )
        IndexStatSnapshot.objects.create(
            snapshot=self.after,
            schema_name="public",
            table_name="shop_product",
            index_name="shop_product_stock_idx",
            idx_scan=1,
            index_size_bytes=8 * 1024 * 1024,
        )
        IndexStatSnapshot.objects.create(
            snapshot=self.before,
            schema_name="public",
            table_name="shop_product",
            index_name="shop_product_stock_idx",
            idx_scan=4,
            index_size_bytes=8 * 1024 * 1024,
        )
        AnalysisFinding.objects.create(
            snapshot=self.after,
            type="slow_query",
            severity="high",
            title="Slow product search",
            description="Product search remains expensive.",
            object_type="query",
            object_name="after-query",
            evidence_json={"calls": 200},
        )
        AnalysisFinding.objects.create(
            snapshot=self.after,
            type="seq_scan_heavy_table",
            severity="medium",
            title="Product table scan pressure",
            description="Table scans dominate product access.",
            object_type="table",
            object_name="public.shop_product",
            evidence_json={"seq_scan": 350},
        )

    def test_dashboard_service_surfaces_latest_snapshot_and_comparison(self):
        overview = get_dashboard_overview(limit=5)

        self.assertEqual(overview["latest_snapshot"]["snapshot"].id, self.after.id)
        self.assertEqual(overview["latest_snapshot"]["counts"]["findings"], 2)
        self.assertEqual(overview["comparison"]["summary"]["snapshot_b"]["id"], self.after.id)

    def test_snapshot_report_includes_rankings_and_findings(self):
        report = get_snapshot_report(self.after.id, ranking_limit=5)

        self.assertEqual(report["snapshot"].id, self.after.id)
        self.assertEqual(report["queries"]["slowest"][0]["queryid"], "after-query")
        self.assertIn("SELECT * FROM shop_product", report["queries"]["slowest"][0]["label"])
        self.assertEqual(report["tables"]["problematic"][0]["table"], "public.shop_product")
        self.assertEqual(report["findings"]["top"][0]["type"], "slow_query")

    def test_overview_page_renders_dashboard(self):
        response = self.client.get(reverse("db_monitor:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monitoring dashboard")
        self.assertContains(response, "Slow product search")

    def test_snapshot_section_views_render_expected_content(self):
        response = self.client.get(reverse("db_monitor:snapshot-section", args=[self.after.id, "findings"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "seq_scan_heavy_table")
        self.assertContains(response, "public.shop_product")

    def test_compare_view_renders_before_after_summary(self):
        response = self.client.get(reverse("db_monitor:compare"), {"snapshot_a": self.before.id, "snapshot_b": self.after.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Snapshot comparison")
        self.assertContains(response, "Top query regressions")

    def test_comparison_report_builds_index_recommendations_for_product_search(self):
        report = get_comparison_report(self.before.id, self.after.id, top=5)

        self.assertTrue(report["index_advisories"])
        self.assertEqual(report["index_advisories"][0]["target"]["table"], "public.shop_product")
        self.assertIn("CREATE INDEX", report["index_advisories"][0]["target"]["sql"])
        self.assertTrue(report["index_experiment_story"]["is_valid_before_after"])
        self.assertEqual(report["index_experiment_story"]["added_count"], 1)
        self.assertEqual(report["workload_chart"][0]["scale_max"], 15000)


class IndexExperimentCommandTests(TestCase):
    def test_status_command_reports_unsupported_mode_on_sqlite(self):
        out = []

        call_command("configure_index_experiment", "status", stdout=Buffer(out))

        rendered = "".join(out)
        self.assertIn("Index experiment mode: unsupported", rendered)

    def test_manage_experiment_indexes_status_reports_unsupported_mode_on_sqlite(self):
        out = []

        call_command("manage_experiment_indexes", "--status", stdout=Buffer(out))

        rendered = "".join(out)
        self.assertIn("Index experiment mode: unsupported", rendered)

    def test_reset_pg_stats_requires_postgresql(self):
        with self.assertRaisesMessage(Exception, "requires PostgreSQL"):
            call_command("reset_pg_stats")

    def test_vacuum_analyze_demo_tables_requires_postgresql(self):
        with self.assertRaisesMessage(Exception, "requires PostgreSQL"):
            call_command("vacuum_analyze_demo_tables", "--dry-run")

    def test_capture_query_plans_requires_postgresql(self):
        snapshot = StatsSnapshot.objects.create(
            label="plans",
            environment="test",
            database_vendor="sqlite",
            database_name="test",
            status=StatsSnapshot.Status.SKIPPED,
        )
        with self.assertRaisesMessage(Exception, "requires PostgreSQL"):
            call_command("capture_query_plans", snapshot_id=snapshot.id)


class QueryClassificationTests(TestCase):
    def test_classify_sql_operation_groups_common_statement_types(self):
        self.assertEqual(classify_sql_operation("SELECT * FROM shop_product"), "SELECT")
        self.assertEqual(classify_sql_operation("insert into shop_order values ($1)"), "INSERT")
        self.assertEqual(classify_sql_operation(" UPDATE shop_product SET stock = stock + 1"), "UPDATE")
        self.assertEqual(classify_sql_operation("delete from shop_review where id = $1"), "DELETE")
        self.assertEqual(classify_sql_operation("BEGIN"), "OTHER")


class IndexBenchmarkCsvTests(TestCase):
    def test_operation_rows_aggregate_query_types_for_csv(self):
        snapshot = StatsSnapshot.objects.create(
            label="csv",
            environment="test",
            database_vendor="postgresql",
            database_name="grafana_clone",
            status=StatsSnapshot.Status.COMPLETED,
        )
        QueryStatSnapshot.objects.bulk_create(
            [
                QueryStatSnapshot(
                    snapshot=snapshot,
                    operation_type="SELECT",
                    query_text_normalized="SELECT * FROM shop_product",
                    calls=10,
                    total_exec_time=50,
                    mean_exec_time=5,
                    max_exec_time=8,
                    rows=100,
                ),
                QueryStatSnapshot(
                    snapshot=snapshot,
                    operation_type="UPDATE",
                    query_text_normalized="UPDATE shop_product SET stock = stock + 1",
                    calls=4,
                    total_exec_time=20,
                    mean_exec_time=5,
                    max_exec_time=7,
                    rows=4,
                ),
            ]
        )

        rows = _operation_rows(snapshot, {"profile": "medium", "index_mode": "none"})
        by_type = {row["query_type"]: row for row in rows}

        self.assertEqual(by_type["SELECT"]["total_exec_time_ms"], 50)
        self.assertEqual(by_type["UPDATE"]["calls"], 4)

    def test_run_index_benchmark_requires_postgresql(self):
        with self.assertRaisesMessage(Exception, "requires PostgreSQL"):
            call_command("run_index_benchmark", "--profile=medium", "--runs=1", "--iterations=1")

    def test_query_coverage_preset_is_shorter_than_full_matrix(self):
        self.assertLess(len(TRAFFIC_PRESETS["query_coverage"]), len(TRAFFIC_PRESETS["full"]))
        self.assertEqual(len(TRAFFIC_PRESETS["query_coverage"]), 8)

    def test_huge_reporting_benchmark_caps_concurrency(self):
        self.assertEqual(_effective_concurrency("huge", "sales_report_heavy", 4), 1)
        self.assertEqual(_effective_concurrency("huge", "reporting", 4), 1)
        self.assertEqual(_effective_concurrency("large", "sales_report_heavy", 4), 4)


class IndexExperimentSelectionTests(TestCase):
    def test_recommend_experiment_indexes_selects_multiple_candidates_from_slowest_queries(self):
        snapshot = StatsSnapshot.objects.create(
            label="before",
            environment="baseline",
            database_vendor="postgresql",
            database_name="grafana_clone",
            status=StatsSnapshot.Status.COMPLETED,
        )
        QueryStatSnapshot.objects.bulk_create(
            [
                QueryStatSnapshot(
                    snapshot=snapshot,
                    queryid="catalog-newest",
                    query_text_normalized=(
                        "SELECT * FROM shop_product WHERE is_active = true "
                        "AND created_at >= $1 ORDER BY created_at DESC LIMIT 20"
                    ),
                    calls=80,
                    total_exec_time=3200,
                    mean_exec_time=40,
                    min_exec_time=10,
                    max_exec_time=120,
                    rows=1000,
                ),
                QueryStatSnapshot(
                    snapshot=snapshot,
                    queryid="catalog-price",
                    query_text_normalized=(
                        "SELECT * FROM shop_product WHERE is_active = true "
                        "ORDER BY price ASC, name ASC LIMIT 20"
                    ),
                    calls=70,
                    total_exec_time=3000,
                    mean_exec_time=42,
                    min_exec_time=8,
                    max_exec_time=130,
                    rows=900,
                ),
                QueryStatSnapshot(
                    snapshot=snapshot,
                    queryid="catalog-search",
                    query_text_normalized=(
                        "SELECT * FROM shop_product WHERE name ILIKE $1 OR description ILIKE $1"
                    ),
                    calls=60,
                    total_exec_time=2800,
                    mean_exec_time=46,
                    min_exec_time=9,
                    max_exec_time=150,
                    rows=900,
                ),
                QueryStatSnapshot(
                    snapshot=snapshot,
                    queryid="order-history",
                    query_text_normalized=(
                        "SELECT * FROM shop_order WHERE user_id = $1 ORDER BY created_at DESC"
                    ),
                    calls=40,
                    total_exec_time=2400,
                    mean_exec_time=60,
                    min_exec_time=14,
                    max_exec_time=180,
                    rows=500,
                ),
                QueryStatSnapshot(
                    snapshot=snapshot,
                    queryid="sales-report",
                    query_text_normalized=(
                        "SELECT * FROM shop_order WHERE status IN ($1, $2) AND created_at >= $3"
                    ),
                    calls=25,
                    total_exec_time=2200,
                    mean_exec_time=88,
                    min_exec_time=20,
                    max_exec_time=210,
                    rows=300,
                ),
            ]
        )

        selected = recommend_experiment_indexes(snapshot=snapshot, limit=5)
        names = [item["name"] for item in selected]

        self.assertIn("shop_product_covering_catalog_idx", names)
        self.assertIn("shop_product_active_price_covering_idx", names)
        self.assertIn("shop_product_name_trgm_idx", names)
        self.assertIn("shop_product_description_trgm_idx", names)
        self.assertIn("shop_order_user_created_at_covering_idx", names)

    def test_recommend_experiment_indexes_falls_back_to_default_indexes_without_snapshot_data(self):
        selected = recommend_experiment_indexes(snapshot=None, limit=5)
        names = [item["name"] for item in selected]

        self.assertIn("shop_product_covering_catalog_idx", names)
        self.assertIn("shop_product_name_trgm_idx", names)

    def test_recommend_experiment_indexes_can_be_limited_to_group(self):
        selected = recommend_experiment_indexes(snapshot=None, limit=5, groups=["order_history_covering"])
        names = [item["name"] for item in selected]

        self.assertEqual(names, ["shop_order_user_created_at_covering_idx"])

    def test_configure_status_syncs_database_backed_index_catalog(self):
        out = []

        call_command("configure_index_experiment", "status", "--sync-catalog", stdout=Buffer(out))

        self.assertTrue(ExperimentIndexGroup.objects.filter(name="catalog_covering").exists())
        self.assertTrue(ExperimentIndexDefinition.objects.filter(name="shop_product_covering_catalog_idx").exists())
        self.assertTrue(ExperimentIndexDefinition.objects.filter(name="shop_product_slug_detail_covering_idx").exists())
        self.assertTrue(ExperimentIndexDefinition.objects.filter(name="load_cart_cleanup_covering_idx").exists())
