# Index benchmark CSV

`run_index_benchmark` runs the same simulated traffic against three index modes:

- `none`: no experimental benchmark indexes.
- `regular`: normal B-tree benchmark indexes without `INCLUDE`.
- `covering`: B-tree benchmark indexes with `INCLUDE` columns.

The default `query_coverage` matrix is:

- dataset profiles: `medium`, `large`, `huge`
- index modes: `none`, `regular`, `covering`
- traffic runs: 8 scenario/seed/intensity combinations covering each major query family

That means 72 workload runs and snapshots by default. It covers catalog, product detail, order history, sales reporting, mixed read/write, inventory updates, and cleanup workloads.

The original larger matrix is still available with `--preset=full`:

- dataset profiles: `medium`, `large`, `huge`
- index modes: `none`, `regular`, `covering`
- traffic runs: 20 different scenario/seed/intensity combinations

That means 180 workload runs and snapshots.

## Full run

```bash
python manage.py migrate
python manage.py configure_index_experiment status --sync-catalog
python manage.py run_index_benchmark --output=reports/index_benchmark_results.csv --concurrently
```

## Full 20-run matrix

```bash
python manage.py run_index_benchmark --preset=full --output=reports/index_benchmark_full.csv --concurrently
```

## Smoke run

```bash
python manage.py run_index_benchmark \
  --profile=medium \
  --runs=2 \
  --iterations=200 \
  --concurrency=2 \
  --warmup=20 \
  --output=reports/index_benchmark_smoke.csv
```

## CSV contents

The CSV is one table. Important columns:

- `profile`: `medium`, `large`, or `huge`.
- `traffic_run`: 1..20 traffic definition.
- `scenario`: simulated traffic mix.
- `index_mode`: `none`, `regular`, or `covering`.
- `row_kind`: `operation_total`, `top_query`, or `query_plan`.
- `query_type`: `SELECT`, `INSERT`, `UPDATE`, `DELETE`, etc.
- `query_name`: operation label, normalized SQL preview, or representative plan name.
- `total_exec_time_ms`, `mean_exec_time_ms`, `max_exec_time_ms`.
- `uses_index_only_scan`, `uses_index_scan`, `uses_seq_scan` for plan rows.

Use `--skip-query-plans` if you only want `pg_stat_statements` timing rows.

On the `huge` profile, reporting-heavy traffic is automatically capped to lower concurrency because PostgreSQL aggregate plans can allocate large shared-memory segments. The CSV records the effective `concurrency` used for each row.

The Docker PostgreSQL service is configured with `shm_size: "1gb"` for these runs. If you already have the container running, recreate it once after pulling this change:

```bash
docker compose down
docker compose up -d postgres
```
