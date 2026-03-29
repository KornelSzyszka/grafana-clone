# Management Commands Foundation

## Status

Implemented for the command layer foundation and comparison milestone.

## Implemented Commands

### `load_simulator`

* `seed_data --size=small|medium|large`
* `clear_demo_data`
* `simulate_load --scenario=default --duration=30`

### `db_monitor`

* `collect_stats`
* `analyze_stats`
* `compare_snapshots snapshot_a snapshot_b`

## Notes

The command surface is now sufficient to prepare data, generate workload, persist monitoring snapshots, analyze findings, and compare before/after runs.
The remaining gap is live orchestration on a reachable PostgreSQL runtime, not a missing command.
