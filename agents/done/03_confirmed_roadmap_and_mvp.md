# Confirmed Roadmap And MVP

## Status

Completed at the planning level.

## Implementation Order

The confirmed implementation order is:

1. domain,
2. data,
3. workload,
4. monitoring,
5. analysis,
6. presentation,
7. before/after experiment.

## Minimum MVP

The minimum MVP includes:

* `Product`, `Order`, and `OrderItem` entities,
* `small` and `medium` data generation profiles,
* workload for product listing, product details, order history, and a simple admin report,
* monitoring based on `pg_stat_statements`, `pg_stat_user_tables`, and `pg_stat_user_indexes`,
* analysis for slow queries, hot queries, candidate unused indexes, and seq-scan-heavy tables,
* three controlled issues: missing index, `N+1`, and unused index.

## Confirmed Target Commands

### `load_simulator`

* `seed_data --size=small|medium|large`
* `simulate_load --scenario=default --duration=300`
* `clear_demo_data`

### `db_monitor`

* `collect_stats`
* `analyze_stats`
* `compare_snapshots snapshot_a snapshot_b`
