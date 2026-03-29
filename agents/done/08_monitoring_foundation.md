# Monitoring Foundation

## Status

Implemented for the monitoring stage foundation.

## Delivered Scope

The repository now contains a `db_monitor` app with:

* `StatsSnapshot`,
* `QueryStatSnapshot`,
* `TableStatSnapshot`,
* `IndexStatSnapshot`,
* `ActivitySnapshot`,
* `AnalysisFinding`.

## Delivered Collection Layer

The collector can now:

* detect the active database backend,
* skip gracefully outside PostgreSQL,
* collect from `pg_stat_statements` when the extension exists,
* collect from `pg_stat_user_tables`,
* collect from `pg_stat_user_indexes`,
* optionally collect from `pg_stat_activity`,
* save all collected rows into snapshot models.

## Delivered Command

* `collect_stats --label=... --environment=...`

## Current Limitation

Full-value collection depends on running the project against PostgreSQL with the required stats views enabled.
SQLite fallback still exists in code, but it is no longer the intended project path.
