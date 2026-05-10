# Load testing

Use `simulate_load` to generate repeatable PostgreSQL traffic through the existing shop query flows and write paths.

## Useful options

```bash
python manage.py simulate_load \
  --scenario=mixed_read_write \
  --iterations=5000 \
  --seed=123 \
  --warmup=100 \
  --intensity=2 \
  --profile=huge
```

Options:

- `--scenario`: workload mix.
- `--duration`: run until this many seconds when `--iterations` is not set.
- `--iterations`: exact operation count.
- `--seed`: deterministic random source.
- `--warmup`: read-only warmup operations before measurement workload.
- `--intensity`: repeats the heaviest catalog read inside a single operation.
- `--profile`: label carried into output for experiment notes.
- `--concurrency`: accepted for CLI compatibility; the current runner remains sequential in-process.
- `--no-record`: skip writing a `WorkloadRun` metadata row.

Read scenarios include `catalog_heavy`, `order_history_heavy`, `sales_report_heavy`, `mixed_heavy`, and `covering_index_experiment`.

Write scenarios include `write_heavy`, `mixed_read_write`, `order_write_heavy`, `inventory_update_heavy`, and `delete_cleanup_heavy`.

Write workloads create orders, reviews, and bounded demo carts; update order status, product inventory, and prices; and delete only small bounded batches of expired demo carts or old reviews. They are intentionally marked as mutating data in the command summary.

`--concurrency` runs operations through worker threads, each with its own Django database connection. Operation selection remains deterministic for a given seed, while overlapping writes still behave like real concurrent database traffic.

Every workload run is recorded in `load_simulator.WorkloadRun` unless `--no-record` is passed. The next `collect_stats` call links the newest unattached workload run to the created snapshot and stores a compact copy in snapshot metadata.

## Read/write index cost experiment

```bash
python manage.py reset_pg_stats
python manage.py manage_experiment_indexes --drop --group=write_cost
python manage.py simulate_load --scenario=mixed_read_write --iterations=5000 --seed=123
python manage.py collect_stats --label=rw-before --environment=large-local --include-query-plans
python manage.py analyze_stats --label=rw-before

python manage.py reset_pg_stats
python manage.py manage_experiment_indexes --apply --group=write_cost --snapshot-label=rw-before
python manage.py simulate_load --scenario=mixed_read_write --iterations=5000 --seed=123
python manage.py collect_stats --label=rw-after --environment=large-local --include-query-plans
python manage.py analyze_stats --label=rw-after

python manage.py compare_snapshots rw-before rw-after --format=json
```

The comparison output reports total read cost, total write cost, and top SELECT, INSERT, UPDATE, and DELETE queries. This makes the trade-off visible: covering indexes can improve reads while increasing INSERT/UPDATE/DELETE maintenance cost, index size, dead tuples, and future VACUUM work.
