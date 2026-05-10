# Controlled Performance Issues

This document describes the intentionally preserved performance issues that should be visible once the project runs on PostgreSQL and realistic workload is generated.

## Implemented Issues

### 1. `N+1` in order history

Location:
`shop/services/querying.py`

Mechanism:
`get_order_history()` skips `prefetch_related("items__product")` when controlled issues are enabled.
This causes additional queries for order items and related products during response building.

Expected symptom:

* many repeated `SELECT` statements for order items and products,
* elevated query count for the order history flow,
* later a good candidate for `suspected N+1`.

### 2. Missing index on frequent timestamp filter

Location:
`shop/services/querying.py`

Mechanism:
catalog listing can now filter by `Product.created_at`, but `Product.created_at` still has no index.
The simulator uses this path together with `sort="newest"`.

Expected symptom:

* more sequential scans on `shop_product`,
* degraded product-list performance for recent-product views,
* stronger `seq_scan_heavy_table` signals.

### 3. Expensive text search

Location:
`shop/services/querying.py`

Mechanism:
catalog search uses `ILIKE`-style `icontains` over both `name` and `description`.
This intentionally avoids a more optimized search strategy.

Expected symptom:

* heavy text-filter scans on product listing,
* hot query candidates under repeated catalog search workload,
* slow query candidates once the dataset grows.

### 4. Candidate unused index

Location:
`shop/models.py`

Mechanism:
the index `shop_product_stock_idx` exists, but the workload does not filter by stock.
It is intentionally left in place as a candidate for unused-index analysis.

Expected symptom:

* very low `idx_scan` for `shop_product_stock_idx`,
* potential `unused_index` findings once PostgreSQL snapshots are collected.

## Feature Flag

Controlled issues are enabled by default through:

`ENABLE_CONTROLLED_PERFORMANCE_ISSUES=true`

This can later be turned off when running the "after fix" side of the experiment.

## Index Experiment Flow

If the goal of the comparison is specifically:

* `before` = workload without the optimization index,
* `after` = workload with the optimization index,

use the dedicated command:

* `python manage.py configure_index_experiment without_indexes`
* run workload and collect snapshot `before`
* `python manage.py configure_index_experiment with_indexes`
* run workload and collect snapshot `after`

The command currently manages the experimental PostgreSQL indexes for:

* `shop_product.created_at` as the main before/after indexing experiment,
* `shop_product.name` trigram search index when `pg_trgm` is available.

Collected snapshots store the active index-experiment state in their metadata so the reporting layer can verify whether a comparison really represents `without indexes -> with indexes`.
