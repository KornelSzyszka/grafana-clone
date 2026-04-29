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

    def handle(self, *args, **options):
        mode = options["mode"]
        try:
            if mode == "status":
                summary = get_experiment_index_state()
            else:
                summary = configure_experiment_indexes(mode)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Index experiment mode: {summary['mode']}"))
        for index in summary["indexes"]:
            status = "present" if index["present"] else "absent"
            self.stdout.write(f"- {index['name']} ({index['description']}): {status}")

        for item in summary.get("changed", []):
            self.stdout.write(f"* {item['name']} -> {item['action']}")

        if summary.get("notes"):
            self.stdout.write("Notes:")
            for note in summary["notes"]:
                self.stdout.write(f"- {note}")
