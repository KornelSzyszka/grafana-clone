# Agent Documents

This directory tracks what is already implemented and what still remains for the project.

## `done/`

Documents that reflect decisions or implementation work already completed in the repository.

## `todo/`

Documents that still describe work to be implemented.
Some items may be partially completed and explicitly marked as such.

## Current Repository State

The repository now contains:

* a Django project in `config/`,
* the `shop` application with core domain models and JSON endpoints,
* the `load_simulator` application with seeding and workload commands,
* the `db_monitor` application with snapshot models, collection, heuristic findings, and snapshot comparison,
* classic reporting views in `db_monitor` for dashboards, rankings, and before/after comparisons,
* Docker files for PostgreSQL baseline setup,
* controlled performance issues implemented in code for later experiments,
* local environment examples and Python requirements,
* PostgreSQL as the intended runtime path for the next stages,
* live PostgreSQL runtime validation still pending.

## Suggested Usage

1. Read `done/` to understand what already exists in code.
2. Continue with `todo/` starting from PostgreSQL runtime validation.
3. When a work area is implemented, move its final implementation state into `done/`.
