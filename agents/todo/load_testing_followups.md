# Load testing follow-ups

All previously listed load-testing follow-ups have been implemented in this iteration.

- `simulate_load --concurrency=N` now runs operations through worker threads with separate Django database connections.
- Workload metadata is persisted in `WorkloadRun` and linked to the next collected `StatsSnapshot`.
- `DemoCart` and `DemoCartItem` provide bounded cleanup targets for DELETE-heavy workloads.
