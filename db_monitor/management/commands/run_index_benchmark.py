from django.core.management.base import BaseCommand, CommandError

from db_monitor.services.benchmark_indexes import BenchmarkOptions, run_index_benchmark
from load_simulator.services.seeding import PROFILE_NAMES


class Command(BaseCommand):
    help = "Run a full index benchmark matrix and export query timing results to CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            action="append",
            choices=PROFILE_NAMES,
            default=[],
            help="Dataset profile to benchmark. Can be passed multiple times. Defaults to medium, large, huge.",
        )
        parser.add_argument("--runs", type=int, default=20, help="Number of traffic definitions to run per profile/mode.")
        parser.add_argument("--iterations", type=int, default=5000)
        parser.add_argument("--concurrency", type=int, default=4)
        parser.add_argument("--warmup", type=int, default=100)
        parser.add_argument("--seed", type=int, default=123)
        parser.add_argument("--output", default="reports/index_benchmark_results.csv")
        parser.add_argument("--skip-query-plans", action="store_true")
        parser.add_argument(
            "--reuse-data-between-modes",
            action="store_true",
            help="Do not reseed before regular/covering modes. Faster, but write workloads may slightly diverge.",
        )
        parser.add_argument(
            "--concurrently",
            action="store_true",
            help="Use CREATE/DROP INDEX CONCURRENTLY for benchmark index mode changes.",
        )

    def handle(self, *args, **options):
        profiles = options["profile"] or ["medium", "large", "huge"]
        benchmark_options = BenchmarkOptions(
            profiles=profiles,
            runs=max(options["runs"], 1),
            iterations=max(options["iterations"], 1),
            concurrency=max(options["concurrency"], 1),
            warmup=max(options["warmup"], 0),
            seed=options["seed"],
            output=options["output"],
            include_query_plans=not options["skip_query_plans"],
            reseed_each_mode=not options["reuse_data_between_modes"],
            use_concurrently=options["concurrently"],
        )

        try:
            summary = run_index_benchmark(
                benchmark_options,
                progress_callback=lambda message: self.stdout.write(message),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Index benchmark complete. CSV={summary['output']} rows={summary['rows']} "
                f"snapshots={len(summary['snapshots'])}"
            )
        )
