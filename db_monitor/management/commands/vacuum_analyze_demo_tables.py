from django.core.management.base import BaseCommand, CommandError
from django.db import connection


DEFAULT_TABLES = [
    "shop_category",
    "shop_product",
    "shop_order",
    "shop_orderitem",
    "shop_review",
    "auth_user",
]


class Command(BaseCommand):
    help = "Run VACUUM ANALYZE on demo tables to improve visibility maps and planner statistics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--table",
            action="append",
            default=[],
            help="Specific table to vacuum. Can be passed multiple times. Defaults to demo/shop tables.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the VACUUM statements without executing them.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError(f"vacuum_analyze_demo_tables requires PostgreSQL; current backend is {connection.vendor}.")

        tables = options["table"] or DEFAULT_TABLES
        statements = [f"VACUUM (ANALYZE) {connection.ops.quote_name(table)}" for table in tables]

        for statement in statements:
            if options["dry_run"]:
                self.stdout.write(statement)
                continue
            with connection.cursor() as cursor:
                cursor.execute(statement)
            self.stdout.write(self.style.SUCCESS(f"Completed: {statement}"))

        if not options["dry_run"]:
            self.stdout.write(
                "VACUUM ANALYZE can make covering-index experiments clearer by refreshing planner stats "
                "and improving PostgreSQL visibility-map coverage for index-only scans."
            )
