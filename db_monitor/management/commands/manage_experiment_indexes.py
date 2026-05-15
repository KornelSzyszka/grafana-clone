from django.core.management import call_command
from django.core.management.base import BaseCommand

from db_monitor.services.index_experiments import EXPERIMENT_GROUPS


class Command(BaseCommand):
    help = "Apply, drop, or inspect PostgreSQL indexes used by controlled performance experiments."

    def add_arguments(self, parser):
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument("--apply", action="store_true", help="Create selected experiment indexes.")
        action.add_argument("--drop", action="store_true", help="Drop managed experiment indexes.")
        action.add_argument("--status", action="store_true", help="Show managed experiment index state.")
        parser.add_argument("--snapshot-id", type=int, default=None)
        parser.add_argument("--snapshot-label", default="")
        parser.add_argument("--limit", type=int, default=5)
        parser.add_argument("--group", action="append", choices=EXPERIMENT_GROUPS, default=[])
        parser.add_argument(
            "--concurrently",
            action="store_true",
            help="Use CREATE/DROP INDEX CONCURRENTLY. Django must not wrap this command in a transaction.",
        )
        parser.add_argument("--all-indexes", action="store_true")

    def handle(self, *args, **options):
        if options["apply"]:
            mode = "with_indexes"
        elif options["drop"]:
            mode = "without_indexes"
        else:
            mode = "status"

        command_args = [mode]
        command_options = {
            "snapshot_id": options["snapshot_id"],
            "snapshot_label": options["snapshot_label"],
            "limit": options["limit"],
            "group": options["group"],
            "concurrently": options["concurrently"],
            "all_indexes": options["all_indexes"],
            "stdout": self.stdout,
        }
        call_command("configure_index_experiment", *command_args, **command_options)
