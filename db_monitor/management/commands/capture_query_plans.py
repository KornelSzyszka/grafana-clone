from django.core.management.base import BaseCommand, CommandError

from db_monitor.models import StatsSnapshot
from db_monitor.services.query_plans import capture_representative_query_plans


class Command(BaseCommand):
    help = "Capture EXPLAIN ANALYZE JSON plans for representative experiment queries."

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id", type=int)
        parser.add_argument("--label", default="")

    def handle(self, *args, **options):
        snapshot = self._resolve_snapshot(options)
        summary = capture_representative_query_plans(snapshot)
        if summary.get("skipped"):
            raise CommandError(summary["reason"])

        self.stdout.write(self.style.SUCCESS(f"Captured {summary['captured']} query plans for snapshot #{snapshot.id}."))
        for plan in summary["plans"]:
            self.stdout.write(
                "- "
                f"{plan['name']}: execution {plan['execution_time_ms']:.2f} ms | "
                f"index_only={plan['uses_index_only_scan']} | seq_scan={plan['uses_seq_scan']}"
            )

    def _resolve_snapshot(self, options):
        if options["snapshot_id"]:
            snapshot = StatsSnapshot.objects.filter(id=options["snapshot_id"]).first()
        elif options["label"]:
            snapshot = StatsSnapshot.objects.filter(label=options["label"]).order_by("-created_at", "-id").first()
        else:
            snapshot = StatsSnapshot.objects.order_by("-created_at", "-id").first()
        if not snapshot:
            raise CommandError("Snapshot was not found.")
        return snapshot
