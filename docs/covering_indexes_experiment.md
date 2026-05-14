# Covering indexes experiment

The controlled covering-index experiment compares the same workload before and after adding PostgreSQL B-tree indexes with `INCLUDE` columns.

Managed indexes:

- `shop_product_covering_catalog_idx` on `shop_product (is_active, category_id, created_at DESC) INCLUDE (id, name, slug, price, stock, popularity_score)`
- `shop_product_active_price_covering_idx` on `shop_product (is_active, category_id, price, name) INCLUDE (id, slug, stock, popularity_score)`
- `shop_product_popularity_covering_idx` on `shop_product (is_active, category_id, popularity_score DESC, name) INCLUDE (id, slug, price, stock, created_at)`
- `shop_product_slug_detail_covering_idx` on `shop_product (slug, is_active) INCLUDE (id, name, description, price, stock, category_id, popularity_score, created_at)`
- `shop_product_similar_covering_idx` on `shop_product (category_id, is_active, popularity_score DESC, name) INCLUDE (id, slug, price, stock)`
- `shop_order_user_created_at_covering_idx` on `shop_order (user_id, created_at DESC) INCLUDE (id, status, total_amount)`
- `shop_orderitem_order_covering_idx` on `shop_orderitem (order_id) INCLUDE (product_id, quantity, unit_price, line_total)`
- `shop_order_status_created_at_covering_idx` on `shop_order (status, created_at DESC) INCLUDE (id, user_id, total_amount)`
- `shop_orderitem_product_report_covering_idx` on `shop_orderitem (product_id) INCLUDE (order_id, line_total, quantity)`
- `shop_product_id_category_covering_idx` on `shop_product (id) INCLUDE (category_id)`
- `shop_review_product_created_at_covering_idx` on `shop_review (product_id, created_at DESC) INCLUDE (id, user_id, rating, content)`
- `shop_review_created_at_cleanup_covering_idx` on `shop_review (created_at) INCLUDE (id, product_id, user_id)`
- `load_cart_cleanup_covering_idx` on `load_simulator_democart (expires_at, status) INCLUDE (id, user_id)`
- `load_cart_item_cart_covering_idx` on `load_simulator_democartitem (cart_id) INCLUDE (product_id, quantity, unit_price)`
- Additional optional text/search and report indexes selected from slow snapshot queries.

## Full before/after flow

```bash
python manage.py migrate
python manage.py clear_demo_data
python manage.py seed_data --size=huge --seed=42
python manage.py vacuum_analyze_demo_tables
python manage.py configure_index_experiment status --sync-catalog

python manage.py reset_pg_stats
python manage.py manage_experiment_indexes --drop --group=catalog_covering --group=product_detail_covering --group=order_history_covering --group=sales_report --group=cleanup_covering --concurrently
python manage.py simulate_load --scenario=covering_index_experiment --iterations=5000 --seed=123 --warmup=100 --intensity=2 --profile=huge
python manage.py collect_stats --label=covering-before --environment=large-local --include-query-plans
python manage.py analyze_stats --label=covering-before

python manage.py reset_pg_stats
python manage.py manage_experiment_indexes --apply --group=catalog_covering --group=product_detail_covering --group=order_history_covering --group=sales_report --group=cleanup_covering --all-indexes --concurrently --snapshot-label=covering-before
python manage.py simulate_load --scenario=covering_index_experiment --iterations=5000 --seed=123 --warmup=100 --intensity=2 --profile=huge
python manage.py collect_stats --label=covering-after --environment=large-local --include-query-plans
python manage.py analyze_stats --label=covering-after

python manage.py compare_snapshots covering-before covering-after --format=json
```

`--concurrently` uses PostgreSQL `CREATE INDEX CONCURRENTLY` and `DROP INDEX CONCURRENTLY`. These statements cannot run inside an explicit transaction, so the management command keeps the work in normal Django autocommit mode.

Use `--group` to restrict the experiment to a named index set:

- `catalog_covering`
- `order_history_covering`
- `search`
- `sales_report`
- `write_cost`

## What to inspect

The comparison report separates read and write costs, shows top query improvements/regressions, table scan deltas, index usage deltas, and findings. A good covering-index run should show lower catalog read cost and increased usage of the managed indexes. Index-only scans also depend on PostgreSQL visibility maps, so running `VACUUM ANALYZE` after large data loads can make the effect clearer.

`--include-query-plans` stores representative `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plans beside the snapshot. The snapshot page then shows whether PostgreSQL used sequential scans, index scans, or index-only scans for the controlled catalog/order-history queries.
