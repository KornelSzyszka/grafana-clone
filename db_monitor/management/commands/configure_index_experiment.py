from django.core.management.base import BaseCommand, CommandError

from db_monitor.services.index_experiments import (
    EXPERIMENT_GROUPS,
    configure_experiment_indexes,
    get_experiment_index_state,
    sync_experiment_index_catalog,
)


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
        parser.add_argument(
            "--concurrently",
            action="store_true",
            help="Use PostgreSQL CREATE/DROP INDEX CONCURRENTLY. Must run outside an explicit transaction.",
        )
        parser.add_argument(
            "--group",
            action="append",
            choices=EXPERIMENT_GROUPS,
            default=[],
            help="Limit managed indexes to one experiment group. Can be passed multiple times.",
        )
        parser.add_argument(
            "--sync-catalog",
            action="store_true",
            help="Synchronize the database-backed experiment index catalog from the built-in manifest.",
        )
        parser.add_argument(
            "--all-indexes",
            action="store_true",
            help="Apply every managed index in the selected group(s), instead of selecting only top candidates.",
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        snapshot_reference = options["snapshot_id"] or options["snapshot_label"] or None
        limit = max(options["limit"], 1)
        try:
            if options["sync_catalog"]:
                sync_experiment_index_catalog()
                self.stdout.write(self.style.SUCCESS("Experiment index catalog synchronized."))
            if mode == "status":
                summary = get_experiment_index_state(
                    snapshot=snapshot_reference,
                    limit=limit,
                    groups=options["group"],
                )
            else:
                summary = configure_experiment_indexes(
                    mode,
                    snapshot=snapshot_reference,
                    limit=limit,
                    concurrently=options["concurrently"],
                    groups=options["group"],
                    apply_all=options["all_indexes"],
                )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Index experiment mode: {summary['mode']}"))
        if summary.get("groups"):
            self.stdout.write(f"Groups: {', '.join(summary['groups'])}")
        self.stdout.write(f"Selection strategy: {summary.get('selection_strategy', 'manual')}")
        for index in summary["indexes"]:
            status = "present" if index["present"] else "absent"
            source = f" | source query: {index['source_query']}" if index.get("source_query") else ""
            groups = f" | groups: {', '.join(index.get('groups', []))}" if index.get("groups") else ""
            include = f" | include: {index['include']}" if index.get("include") else ""
            self.stdout.write(f"- {index['name']} ({index['description']}): {status}{include}{groups}{source}")

        for item in summary.get("changed", []):
            self.stdout.write(f"* {item['name']} -> {item['action']}")

        if summary.get("notes"):
            self.stdout.write("Notes:")
            for note in summary["notes"]:
                self.stdout.write(f"- {note}")
