# 12 Dashboard And Reporting

## Status

Completed in the application layer.

## What Was Delivered

* classic Django reporting views under `/monitoring/`,
* an overview dashboard for recent snapshots,
* per-snapshot query, table, index, activity, and findings views,
* a before/after comparison page backed by the existing snapshot comparison service,
* navigation from the main landing page into the monitoring area,
* test coverage for reporting services and HTTP views.

## Implementation Notes

The reporting layer was implemented as classic Django views and templates instead of Django admin or a new API.
This keeps the MVP small while still surfacing the existing snapshot, finding, and comparison data already stored by `db_monitor`.

## Remaining Dependencies

The UI is ready, but real production-like value still depends on live PostgreSQL experiment data.
The separate runtime-validation task remains open until a reachable PostgreSQL instance is available and the before/after flow is executed end to end.
