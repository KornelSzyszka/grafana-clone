from django.core.management.base import BaseCommand, CommandError

from load_simulator.services.seeding import PROFILE_NAMES, seed_demo_data


class Command(BaseCommand):
    help = "Seed uneven demo data for development and profiling."

    def add_arguments(self, parser):
        parser.add_argument("--size", default="small", choices=PROFILE_NAMES)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--keep-existing", action="store_true")

    def handle(self, *args, **options):
        try:
            summary = seed_demo_data(
                size=options["size"],
                seed=options["seed"],
                clear_existing=not options["keep_existing"],
                progress_callback=lambda message: self.stdout.write(message),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Seed completed: {summary}"))
