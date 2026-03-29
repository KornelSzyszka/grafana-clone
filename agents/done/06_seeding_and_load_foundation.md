# Seeding And Load Foundation

## Status

Implemented for the MVP foundation.

## Delivered Seeding

The repository now supports:

* `small`, `medium`, and `large` data profiles,
* uneven product popularity,
* uneven user activity,
* recent-data bias for timestamps,
* non-uniform order status distribution.

## Delivered Simulation

The repository now supports:

* repeatable workload execution with a deterministic seed,
* catalog browsing,
* product detail reads,
* order history reads,
* sales reporting reads,
* a `default` mixed scenario.

## Current Limitation

The simulation currently focuses on read-heavy flows and does not yet include write scenarios or intentionally degraded queries.
