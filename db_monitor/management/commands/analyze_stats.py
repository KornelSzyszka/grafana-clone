from django.core.management.base import BaseCommand, CommandError

from db_monitor.heuristics import analyze_snapshot
from db_monitor.models import StatsSnapshot


class Command(BaseCommand):
    help = "Analyze a stored snapshot and generate findings."

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id", type=int)
        parser.add_argument("--label", default="")
        parser.add_argument("--keep-existing", action="store_true")
        parser.add_argument("--slow-query-mean-ms", type=float)
        parser.add_argument("--slow-query-max-ms", type=float)
        parser.add_argument("--hot-query-total-ms", type=float)
        parser.add_argument("--hot-query-calls", type=int)
        parser.add_argument("--unused-index-idx-scan-max", type=int)
        parser.add_argument("--unused-index-size-min-bytes", type=int)
        parser.add_argument("--seq-scan-table-min", type=int)
        parser.add_argument("--seq-scan-live-rows-min", type=int)
        parser.add_argument("--seq-scan-ratio-min", type=float)
        parser.add_argument("--covering-index-total-ms", type=float)
        parser.add_argument("--covering-index-calls", type=int)

    def handle(self, *args, **options):
        snapshot = self._resolve_snapshot(options)
        thresholds = {
            "slow_query_mean_ms": options["slow_query_mean_ms"],
            "slow_query_max_ms": options["slow_query_max_ms"],
            "hot_query_total_ms": options["hot_query_total_ms"],
            "hot_query_calls": options["hot_query_calls"],
            "unused_index_idx_scan_max": options["unused_index_idx_scan_max"],
            "unused_index_size_min_bytes": options["unused_index_size_min_bytes"],
            "seq_scan_table_min": options["seq_scan_table_min"],
            "seq_scan_live_rows_min": options["seq_scan_live_rows_min"],
            "seq_scan_ratio_min": options["seq_scan_ratio_min"],
            "covering_index_total_ms": options["covering_index_total_ms"],
            "covering_index_calls": options["covering_index_calls"],
        }
        thresholds = {key: value for key, value in thresholds.items() if value is not None}

        snapshot, summary = analyze_snapshot(
            snapshot=snapshot,
            thresholds=thresholds,
            replace_existing=not options["keep_existing"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Analysis for snapshot #{snapshot.id} created {summary['created']} findings."
            )
        )
        for finding_type, count in sorted(summary["by_type"].items()):
            self.stdout.write(f"- {finding_type}: {count}")

    def _resolve_snapshot(self, options):
        snapshot_id = options["snapshot_id"]
        label = options["label"].strip()
        if snapshot_id:
            return StatsSnapshot.objects.filter(id=snapshot_id).first() or self._missing_snapshot(str(snapshot_id))
        if label:
            return StatsSnapshot.objects.filter(label=label).order_by("-created_at").first() or self._missing_snapshot(label)
        snapshot = StatsSnapshot.objects.order_by("-created_at").first()
        if not snapshot:
            raise CommandError("No snapshots available. Run `python manage.py collect_stats` first.")
        return snapshot

    def _missing_snapshot(self, reference):
        raise CommandError(f"Snapshot `{reference}` was not found.")
