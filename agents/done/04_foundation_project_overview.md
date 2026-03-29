# Foundation Project Overview

## Status

Implemented in code.

## Delivered Scope

The project now has a working vertical slice for the business and workload layers:

* `shop` provides the e-commerce domain foundation,
* `load_simulator` provides seed data and repeatable traffic generation,
* the application can already expose realistic query patterns through HTTP endpoints and internal service calls.

## Implemented Architecture

Current flow:

`seed_data -> shop models -> shop query services -> JSON endpoints / simulate_load -> database activity`

This foundation now feeds the implemented monitoring and first analysis milestones, and is ready for PostgreSQL-based experiments.

## Constraints

* PostgreSQL is now the default project direction and runtime target,
* SQLite remains only an explicit fallback path for limited local/testing use,
* the remaining work should assume real PostgreSQL statistics and experiment runs.
