# Confirmed Project Assumptions

## Status

Completed at the specification level.

## Project Goal

Build a `Django + PostgreSQL` tool that analyzes database usage and reports:

* the slowest queries,
* queries with the highest total cost,
* suspected `N+1` patterns,
* unused or rarely used indexes,
* tables with a high `seq_scan` share,
* basic operational database issues.

## Confirmed High-Level Architecture

The project is split into three main areas:

* `shop` as the business-domain application,
* `load_simulator` as the data and traffic generator,
* `db_monitor` as the statistics collection and analysis layer.

## Confirmed Domain

The selected business domain is a simplified e-commerce system with:

* `User`,
* `Category`,
* `Product`,
* `Order`,
* `OrderItem`,
* `Payment`,
* `Shipment`,
* `Review`.

## Confirmed Experiment Model

The project is expected to run on synthetic data and a controlled workload.
The system should intentionally include performance issues so the monitoring layer has real problems to detect.
