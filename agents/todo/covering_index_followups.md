# Covering index follow-ups

All previously listed covering-index follow-ups have been implemented in this iteration.

- `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` capture is available through `collect_stats --include-query-plans` and `capture_query_plans`.
- Experiment index groups and definitions are persisted in database models and synchronized from the built-in manifest with `configure_index_experiment --sync-catalog status`.
