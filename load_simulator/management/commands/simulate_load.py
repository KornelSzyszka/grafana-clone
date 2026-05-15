from django.core.management.base import BaseCommand, CommandError

from load_simulator.services.runs import record_workload_run
from load_simulator.services.simulation import SCENARIO_NAMES, run_simulation


class Command(BaseCommand):
    help = "Run a repeatable workload over shop query flows."

    def add_arguments(self, parser):
        parser.add_argument("--scenario", default="default", choices=SCENARIO_NAMES)
        parser.add_argument("--duration", type=int, default=30)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--iterations", type=int, default=0)
        parser.add_argument("--concurrency", type=int, default=1)
        parser.add_argument("--intensity", type=int, default=1)
        parser.add_argument("--profile", default="")
        parser.add_argument("--warmup", type=int, default=0)
        parser.add_argument("--no-record", action="store_true")

    def handle(self, *args, **options):
        try:
            summary = run_simulation(
                scenario=options["scenario"],
                duration=options["duration"],
                seed=options["seed"],
                iterations=options["iterations"] or None,
                concurrency=max(options["concurrency"], 1),
                intensity=max(options["intensity"], 1),
                profile=options["profile"],
                warmup=max(options["warmup"], 0),
                progress_callback=lambda message: self.stdout.write(message),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if not options["no_record"]:
            run = record_workload_run(summary, command_options={key: value for key, value in options.items() if key != "stdout"})
            summary["workload_run_id"] = run.id

        self.stdout.write(self.style.SUCCESS(f"Simulation complete: {summary}"))
