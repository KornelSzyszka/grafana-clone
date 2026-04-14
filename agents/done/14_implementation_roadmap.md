# 14 Implementation Roadmap

## Status

Completed and updated after live PostgreSQL validation.

## Delivery Stages

1. Completed: Domain foundation in `shop`.
2. Completed: Data seeding profiles and cleanup commands.
3. Completed: Basic workload simulation for read-heavy scenarios.
4. Completed: Monitoring collectors, snapshots, and statistics models.
5. Completed: First heuristics, findings, and severity.
6. Completed: Live PostgreSQL validation and before/after experiment execution.
7. Completed: Dashboard, tables, richer reporting views, and workload charts.

## MVP Delivered

Delivered scope:

* core domain models and query flows,
* seed profiles and cleanup commands,
* repeatable workload simulation,
* PostgreSQL statistics collection,
* heuristic findings and snapshot comparison,
* live PostgreSQL runtime validation,
* classic reporting UI with rankings, findings, comparisons, and charts.

## Dependency Map

The original critical dependency was a reachable PostgreSQL runtime with `pg_stat_statements`.
That dependency is now resolved.

Current follow-up work is optional extension work:

* stronger repeatability controls for stats resets,
* threshold tuning for more visible before/after findings,
* richer charting or export/report features.

## Extension List

Useful next steps beyond the delivered MVP:

* dedicated management command for PostgreSQL stats resets,
* saved experiment runs with attached notes,
* exportable HTML or JSON reports,
* more explicit workload presets for controlled issue scenarios.
