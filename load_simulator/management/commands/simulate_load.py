from django.core.management.base import BaseCommand, CommandError

from load_simulator.services.simulation import SCENARIO_NAMES, run_simulation


class Command(BaseCommand):
    help = "Run a repeatable workload over shop query flows."

    def add_arguments(self, parser):
        parser.add_argument("--scenario", default="default", choices=SCENARIO_NAMES)
        parser.add_argument("--duration", type=int, default=30)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--iterations", type=int, default=0)

    def handle(self, *args, **options):
        try:
            summary = run_simulation(
                scenario=options["scenario"],
                duration=options["duration"],
                seed=options["seed"],
                iterations=options["iterations"] or None,
                progress_callback=lambda message: self.stdout.write(message),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Simulation complete: {summary}"))
