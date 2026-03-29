# Current Repository State

## Status

Completed and refreshed after the foundation sprint.

## What Actually Exists

* Django project configuration in `config/`,
* `shop` app with `Category`, `Product`, `Order`, `OrderItem`, and `Review`,
* JSON endpoints for product list, product details, order history, and sales report,
* `load_simulator` app with `seed_data`, `clear_demo_data`, and `simulate_load`,
* `db_monitor` app with snapshot models, raw PostgreSQL collectors, `collect_stats`, and `analyze_stats`,
* snapshot comparison through `compare_snapshots`,
* Docker-based PostgreSQL baseline with `pg_stat_statements`,
* controlled performance issues implemented in query and workload paths,
* generated migrations, test coverage for the foundation, and PostgreSQL-first configuration.

## What Does Not Exist Yet

* dashboard/reporting UI layer,
* end-to-end validation on a live PostgreSQL run.

## Implications For Agents

* treat the repository as a working Django foundation, not a blank scaffold,
* build the next iteration on top of the existing `shop`, `load_simulator`, and `db_monitor` code,
* assume PostgreSQL is now the main runtime target for monitoring and experiments.
