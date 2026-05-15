# 13 PostgreSQL Runtime Validation

## Status

Completed with live PostgreSQL runs on `127.0.0.1:5433`.

## Runtime Used

* PostgreSQL reachable locally on port `5433`,
* Django migrations applied successfully,
* demo data reset and reseeded with the `medium` profile,
* workload executed through the existing `simulate_load` command.

## Commands Executed

Executed on April 14, 2026:

* `python manage.py migrate`
* `python manage.py clear_demo_data`
* `python manage.py seed_data --size=medium`
* `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=true python manage.py simulate_load --scenario=default --iterations=500`
* `python manage.py collect_stats --label=before --environment=controlled-issues`
* `python manage.py analyze_stats --label=before`
* `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=false python manage.py simulate_load --scenario=default --iterations=500`
* `python manage.py collect_stats --label=after --environment=issues-disabled`
* `python manage.py analyze_stats --label=after`
* `python manage.py compare_snapshots before after --format=json`

## Observed Live Result

First before/after pair:

* snapshot `before` = id `3`,
* snapshot `after` = id `4`,
* findings: `31 -> 33` (`+2`),
* all findings were `hot_query`,
* query total execution time: `4393.28 ms -> 4749.63 ms`,
* query count tracked: `173 -> 175`.

The strongest regressions were concentrated in reporting and catalog SQL, including:

* grouped sales-report aggregation over `shop_order` and `shop_orderitem`,
* count/search queries over `shop_product`,
* repeated product listing reads.

## Reproducibility Follow-Up

A second experiment was run with `pg_stat_statements_reset()` and `pg_stat_reset()` between phases:

* snapshot `validated-before` = id `5`,
* snapshot `validated-after` = id `6`.

This second run confirmed that the runtime path itself works end to end, but the heuristic findings dropped to `0 -> 0`.
The reset-based pair still captured workload deltas in query/table/index metrics, yet the current `500`-iteration workload did not cross the heuristic thresholds strongly enough once counters were reset between phases.

## Conclusion

The PostgreSQL execution baseline is now verified:

* migrations work on PostgreSQL,
* seeding and workload commands run against the live database,
* snapshot collection works on real PostgreSQL statistics,
* analysis and before/after comparison run successfully on stored snapshots.

The main remaining improvement beyond MVP is methodological, not infrastructural:

* increase workload intensity,
* tune thresholds,
* or add an explicit stats-reset command to make future experiments easier to reproduce.
