# Index benchmark CSV

`run_index_benchmark` runs the same simulated traffic against three index modes:

- `none`: no experimental benchmark indexes.
- `regular`: normal B-tree benchmark indexes without `INCLUDE`.
- `covering`: B-tree benchmark indexes with `INCLUDE` columns.

The default matrix is:

- dataset profiles: `medium`, `large`, `huge`
- index modes: `none`, `regular`, `covering`
- traffic runs: 20 different scenario/seed/intensity combinations

That means 180 workload runs and snapshots by default. On `huge` this is intentionally expensive.

## Full run

```bash
python manage.py migrate
python manage.py configure_index_experiment status --sync-catalog
python manage.py run_index_benchmark --output=reports/index_benchmark_results.csv --concurrently
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
