from django.core.management.base import BaseCommand

from db_monitor.collectors import collect_stats_snapshot
from db_monitor.services.query_plans import capture_representative_query_plans


class Command(BaseCommand):
    help = "Collect PostgreSQL statistics into snapshot models."

    def add_arguments(self, parser):
        parser.add_argument("--label", default="")
        parser.add_argument("--environment", default="")
        parser.add_argument("--query-limit", type=int, default=200)
        parser.add_argument("--activity-limit", type=int, default=50)
        parser.add_argument("--skip-activity", action="store_true")
        parser.add_argument("--include-query-plans", action="store_true")

    def handle(self, *args, **options):
        snapshot, summary = collect_stats_snapshot(
            label=options["label"],
            environment=options["environment"],
            query_limit=options["query_limit"],
            activity_limit=options["activity_limit"],
            include_activity=not options["skip_activity"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Snapshot #{snapshot.id} saved with status={snapshot.status}. "
                f"query_stats={summary['query_stats']}, table_stats={summary['table_stats']}, "
                f"index_stats={summary['index_stats']}, activities={summary['activities']}"
            )
        )
        if summary["notes"]:
            self.stdout.write("Notes:")
            for note in summary["notes"]:
                self.stdout.write(f"- {note}")

        if options["include_query_plans"]:
            plan_summary = capture_representative_query_plans(snapshot)
            if plan_summary.get("skipped"):
                self.stdout.write(f"Query plans skipped: {plan_summary['reason']}")
            else:
                self.stdout.write(f"Captured query plans: {plan_summary['captured']}")
