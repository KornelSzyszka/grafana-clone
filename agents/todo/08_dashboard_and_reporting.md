# 08 Dashboard And Reporting

## Status

Blocked mainly by the lack of a validated live PostgreSQL experiment run.

## Agent Goal

Build the presentation layer for monitoring and analysis results.

## Scope

* overview view,
* query, table, index, activity, and findings views,
* ranking tables,
* before/after comparisons.

## Tasks

* design a minimal dashboard or admin panel,
* prepare top slow query, hot query, and problematic table listings,
* show findings with type, severity, and evidence,
* present the already implemented comparison between two snapshots,
* decide whether the layer should use Django admin, classic views, or an API.

## Expected Outputs

* report views or reporting endpoints,
* ranking and result tables,
* an overview screen,
* UI/reporting around the existing snapshot comparison mechanism.

## Dependencies

Requires collected PostgreSQL snapshot data and analysis findings to exist.
Snapshot comparison is already implemented in the command layer and can now be surfaced in the UI.
