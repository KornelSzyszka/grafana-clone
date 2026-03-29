# Foundation Domain Model

## Status

Implemented for the MVP foundation.

## Implemented Models

* `Category`
* `Product`
* `Order`
* `OrderItem`
* `Review`

## Implemented Query Flows

* product listing with filtering, sorting, and pagination,
* product details with reviews and similar products,
* user order history,
* sales summary grouped by category.

## Deferred Domain Scope

The following entities are still intentionally postponed:

* `Payment`
* `Shipment`

They should be introduced when the workload and monitoring scope needs richer query shapes.
