# Large dataset experiments

This project is PostgreSQL-first for performance experiments. SQLite can still run many tests, but large workload snapshots require PostgreSQL with `pg_stat_statements`.

## Prepare PostgreSQL

```bash
python manage.py migrate
python manage.py clear_demo_data
python manage.py seed_data --size=huge --seed=42
python manage.py vacuum_analyze_demo_tables
```

The `huge` profile creates a dataset on the order of one million rows across users, products, orders, order items, and reviews. Seeding is batched with `bulk_create`, logs progress per batch, and is safe to rerun after `clear_demo_data`.

For a quicker smoke test, use `--size=large`.

## Collect a baseline

```bash
python manage.py reset_pg_stats
python manage.py simulate_load --scenario=mixed_heavy --iterations=5000 --seed=123 --warmup=100 --intensity=2 --profile=huge
python manage.py collect_stats --label=large-baseline --environment=large-local
python manage.py analyze_stats --label=large-baseline
```

Open `/monitoring/` to inspect slow queries, hot queries, table scan pressure, index usage, and findings.

## Notes

`reset_pg_stats` resets PostgreSQL table/index statistics and `pg_stat_statements` when the extension is available. It requires PostgreSQL privileges for `pg_stat_reset()` and `pg_stat_statements_reset()`.

`vacuum_analyze_demo_tables` refreshes planner statistics after a large load. On huge datasets it can take a while, but it makes before/after experiments more stable and helps PostgreSQL consider index-only scans when visibility maps allow it.
