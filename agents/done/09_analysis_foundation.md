# Analysis Foundation

## Status

Implemented for the first heuristics milestone.

## Delivered Heuristics

The repository now generates `AnalysisFinding` records for:

* `slow_query`,
* `hot_query`,
* `unused_index`,
* `seq_scan_heavy_table`.

## Delivered Analysis Behavior

The analysis layer now:

* reads stored snapshot rows from `db_monitor`,
* applies configurable thresholds with sensible defaults,
* stores evidence in `evidence_json`,
* replaces previous findings for the same snapshot by default,
* supports manual execution through `analyze_stats`.

## Current Limitation

The remaining heuristic backlog still includes:

* `dead tuple pressure`,
* `suspected N+1`,
* before/after comparison logic,
* validation on a real PostgreSQL workload.
