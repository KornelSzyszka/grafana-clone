from django.core.management.base import BaseCommand, CommandError

from db_monitor.services.benchmark_indexes import prepare_index_mode


class Command(BaseCommand):
    help = "Switch benchmark indexes between none, regular B-tree, and covering-index modes."

    def add_arguments(self, parser):
        parser.add_argument("mode", choices=["none", "regular", "covering"])
        parser.add_argument("--concurrently", action="store_true")

    def handle(self, *args, **options):
        try:
            prepare_index_mode(options["mode"], concurrently=options["concurrently"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Benchmark index mode set to `{options['mode']}`."))
