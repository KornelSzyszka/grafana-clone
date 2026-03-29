# 09 PostgreSQL Runtime Validation

## Status

Still blocked by the local environment.

## Agent Goal

Run the prepared PostgreSQL-first experiment flow on a live database and capture real before/after data.

## Scope

* Docker PostgreSQL startup or another reachable PostgreSQL instance,
* Django migrations on PostgreSQL,
* seed and workload execution,
* snapshot collection, analysis, and comparison on real stats.

## Tasks

* start PostgreSQL with `pg_stat_statements`,
* run `migrate`, `seed_data`, `simulate_load`, `collect_stats`, and `analyze_stats`,
* capture a baseline snapshot with `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=true`,
* capture an after snapshot with `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=false`,
* execute `compare_snapshots before after`,
* record the observed findings and deltas from the live run.

## Expected Outputs

* a verified PostgreSQL execution baseline,
* at least two real snapshots,
* a real before/after comparison result,
* evidence for the controlled issues on PostgreSQL.

## Dependencies

Command support is already complete in `db_monitor`.
The remaining blocker is runtime availability, not missing comparison code.
