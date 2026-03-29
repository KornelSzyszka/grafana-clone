# Snapshot Comparison And Runtime Status

## Status

Implemented for the command layer. Runtime validation is ready but blocked by the current machine state.

## Delivered Scope

The repository now contains:

* `db_monitor.services.comparison.compare_snapshots(...)`,
* management command `compare_snapshots snapshot_a snapshot_b`,
* text and JSON output for before/after summaries,
* comparison coverage for query stats, table stats, index stats, and analysis findings,
* tests for the comparison service and command output.

## Delivered Comparison Behavior

The comparison layer now:

* resolves snapshots by id or label,
* summarizes total query cost and call deltas,
* highlights top query regressions and improvements,
* shows table scan and index usage changes,
* compares finding counts by type and severity,
* lists resolved and newly introduced findings between runs.

## Runtime Validation Result

The current environment was checked on 2026-03-29.

Observed state:

* `docker compose` is installed,
* Docker engine is not available through `dockerDesktopLinuxEngine`,
* `127.0.0.1:5432` is not accepting connections,
* `manage.py migrate` against PostgreSQL fails with `connection timeout expired`.

## Implication

The PostgreSQL-first workflow is prepared in code and documentation, but the live baseline run still requires a running Docker Desktop or another reachable PostgreSQL instance.
