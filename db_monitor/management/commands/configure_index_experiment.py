from django.core.management.base import BaseCommand, CommandError

from db_monitor.services.index_experiments import configure_experiment_indexes, get_experiment_index_state


class Command(BaseCommand):
    help = "Switch the database between before/without-indexes and after/with-indexes experiment states."

    def add_arguments(self, parser):
        parser.add_argument(
            "mode",
            choices=["with_indexes", "without_indexes", "status"],
            help="Choose `without_indexes` for before snapshots and `with_indexes` for after snapshots.",
        )
        parser.add_argument(
            "--snapshot-id",
            type=int,
            default=None,
            help="Use this snapshot as the before baseline when selecting indexes for `with_indexes`.",
        )
        parser.add_argument(
            "--snapshot-label",
            default="",
            help="Use the latest snapshot with this label as the before baseline when selecting indexes.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Maximum number of automatically selected indexes for the experiment.",
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        snapshot_reference = options["snapshot_id"] or options["snapshot_label"] or None
        limit = max(options["limit"], 1)
        try:
            if mode == "status":
                summary = get_experiment_index_state(snapshot=snapshot_reference, limit=limit)
            else:
                summary = configure_experiment_indexes(mode, snapshot=snapshot_reference, limit=limit)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Index experiment mode: {summary['mode']}"))
        self.stdout.write(f"Selection strategy: {summary.get('selection_strategy', 'manual')}")
        for index in summary["indexes"]:
            status = "present" if index["present"] else "absent"
            source = f" | source query: {index['source_query']}" if index.get("source_query") else ""
            self.stdout.write(f"- {index['name']} ({index['description']}): {status}{source}")

        for item in summary.get("changed", []):
            self.stdout.write(f"* {item['name']} -> {item['action']}")

        if summary.get("notes"):
            self.stdout.write("Notes:")
            for note in summary["notes"]:
                self.stdout.write(f"- {note}")
