# Controlled Performance Issues Foundation

## Status

Implemented in code for the first experiment-ready baseline.

## Delivered Issues

The repository now intentionally includes:

* `N+1` behavior in order history,
* a missing index path on `Product.created_at`-based catalog filtering,
* expensive text search over product name and description,
* a candidate unused index on product stock.

## Delivered Support

The issue set is documented in:

* `docs/controlled_performance_issues.md`

The issue mode is controlled by:

* `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=true|false`

## Current Limitation

The issues are implemented, but they still need to be exercised and measured on a real PostgreSQL runtime to complete the before/after experiment path.
