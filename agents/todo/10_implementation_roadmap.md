# 10 Implementation Roadmap

## Status

In progress.

## Agent Goal

Sequence the work so the team can reach a working MVP without getting blocked by the full project scope.

## Delivery Stages

1. Completed: Domain foundation in `shop`.
2. Completed: Data seeding profiles and cleanup commands.
3. Completed: Basic workload simulation for read-heavy scenarios.
4. Completed: Monitoring collectors, snapshots, and statistics models.
5. Completed: First heuristics, findings, and severity.
6. In progress: Validate the PostgreSQL baseline on a live runtime and execute the first before/after experiment.
7. Completed: Dashboard, tables, and richer reporting views over stored snapshot data.

## Minimum MVP To Deliver

Foundation already delivered:

* an application with `Category`, `Product`, `Order`, `OrderItem`, and `Review`,
* `small`, `medium`, and `large` data generation,
* workload for catalog, details, order history, and reporting scenarios,
* management commands for seeding, cleanup, and simulation.

Remaining MVP:

* validate the controlled issues on PostgreSQL,
* run the real before/after comparison on collected PostgreSQL snapshots.

Already delivered beyond the previous MVP boundary:

* a classic reporting layer for snapshot overview, rankings, findings, and comparison views.

## Tasks

* validate the PostgreSQL execution baseline and extension setup,
* execute the first live comparison milestone between snapshots,
* identify when the first reproducible before/after experiment should run,
* mark what remains postponed beyond MVP.

## Expected Outputs

* a technical delivery plan,
* a dependency map,
* an MVP definition and an extension list.

## Dependencies

This is a coordination document.
Snapshot comparison is now implemented; the remaining dependency is a reachable PostgreSQL runtime.
