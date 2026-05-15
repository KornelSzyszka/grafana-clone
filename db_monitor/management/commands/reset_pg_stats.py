from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Reset PostgreSQL statistics used by before/after workload experiments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--statements-only",
            action="store_true",
            help="Reset only pg_stat_statements instead of all database statistics.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError(f"reset_pg_stats requires PostgreSQL; current backend is {connection.vendor}.")

        with connection.cursor() as cursor:
            if options["statements_only"]:
                cursor.execute("SELECT pg_stat_statements_reset()")
                self.stdout.write(self.style.SUCCESS("Reset pg_stat_statements."))
                return

            cursor.execute("SELECT pg_stat_reset()")
            cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = %s)", ["pg_stat_statements"])
            if cursor.fetchone()[0]:
                cursor.execute("SELECT pg_stat_statements_reset()")
            self.stdout.write(self.style.SUCCESS("Reset PostgreSQL table, index, and statement statistics."))
