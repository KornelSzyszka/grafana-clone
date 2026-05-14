import csv
from dataclasses import dataclass
from pathlib import Path

from django.db import connection
from django.utils import timezone

from db_monitor.collectors import collect_stats_snapshot
from db_monitor.models import StatsSnapshot
from db_monitor.services.index_experiments import configure_experiment_indexes, sync_experiment_index_catalog
from db_monitor.services.query_plans import capture_representative_query_plans
from load_simulator.services.runs import record_workload_run
from load_simulator.services.seeding import seed_demo_data
from load_simulator.services.simulation import run_simulation


COVERING_GROUPS = [
    "catalog_covering",
    "product_detail_covering",
    "order_history_covering",
    "sales_report",
    "cleanup_covering",
]

REGULAR_INDEX_DEFINITIONS = [
    {"name": "bench_product_active_category_created_idx", "table": "shop_product", "columns": "is_active, category_id, created_at DESC"},
    {"name": "bench_product_active_category_price_idx", "table": "shop_product", "columns": "is_active, category_id, price, name"},
    {"name": "bench_product_active_category_pop_idx", "table": "shop_product", "columns": "is_active, category_id, popularity_score DESC, name"},
    {"name": "bench_product_slug_active_idx", "table": "shop_product", "columns": "slug, is_active"},
    {"name": "bench_order_user_created_idx", "table": "shop_order", "columns": "user_id, created_at DESC"},
    {"name": "bench_order_status_created_idx", "table": "shop_order", "columns": "status, created_at DESC"},
    {"name": "bench_orderitem_order_idx", "table": "shop_orderitem", "columns": "order_id"},
    {"name": "bench_orderitem_product_idx", "table": "shop_orderitem", "columns": "product_id"},
    {"name": "bench_review_product_created_idx", "table": "shop_review", "columns": "product_id, created_at DESC"},
    {"name": "bench_review_created_idx", "table": "shop_review", "columns": "created_at"},
    {"name": "bench_cart_expires_status_idx", "table": "load_simulator_democart", "columns": "expires_at, status"},
    {"name": "bench_cartitem_cart_idx", "table": "load_simulator_democartitem", "columns": "cart_id"},
]

TRAFFIC_RUNS = [
    {"scenario": "covering_index_experiment", "seed_offset": 11, "intensity": 2},
    {"scenario": "catalog_heavy", "seed_offset": 23, "intensity": 2},
    {"scenario": "catalog", "seed_offset": 31, "intensity": 1},
    {"scenario": "order_history_heavy", "seed_offset": 47, "intensity": 1},
    {"scenario": "sales_report_heavy", "seed_offset": 53, "intensity": 1},
    {"scenario": "mixed_heavy", "seed_offset": 61, "intensity": 2},
    {"scenario": "mixed_read_write", "seed_offset": 71, "intensity": 2},
    {"scenario": "write_heavy", "seed_offset": 83, "intensity": 1},
    {"scenario": "order_write_heavy", "seed_offset": 97, "intensity": 1},
    {"scenario": "inventory_update_heavy", "seed_offset": 101, "intensity": 1},
    {"scenario": "delete_cleanup_heavy", "seed_offset": 113, "intensity": 1},
    {"scenario": "default", "seed_offset": 127, "intensity": 1},
    {"scenario": "details", "seed_offset": 139, "intensity": 1},
    {"scenario": "reporting", "seed_offset": 149, "intensity": 1},
    {"scenario": "order_history", "seed_offset": 157, "intensity": 1},
    {"scenario": "covering_index_experiment", "seed_offset": 167, "intensity": 3},
    {"scenario": "mixed_read_write", "seed_offset": 179, "intensity": 3},
    {"scenario": "catalog_heavy", "seed_offset": 191, "intensity": 3},
    {"scenario": "sales_report_heavy", "seed_offset": 199, "intensity": 2},
    {"scenario": "delete_cleanup_heavy", "seed_offset": 211, "intensity": 1},
]

QUERY_COVERAGE_TRAFFIC_RUNS = [
    {"scenario": "covering_index_experiment", "seed_offset": 11, "intensity": 2},
    {"scenario": "catalog_heavy", "seed_offset": 23, "intensity": 2},
    {"scenario": "details", "seed_offset": 31, "intensity": 1},
    {"scenario": "order_history_heavy", "seed_offset": 47, "intensity": 1},
    {"scenario": "sales_report_heavy", "seed_offset": 53, "intensity": 1},
    {"scenario": "mixed_read_write", "seed_offset": 71, "intensity": 2},
    {"scenario": "inventory_update_heavy", "seed_offset": 101, "intensity": 1},
    {"scenario": "delete_cleanup_heavy", "seed_offset": 113, "intensity": 1},
]

TRAFFIC_PRESETS = {
    "query_coverage": QUERY_COVERAGE_TRAFFIC_RUNS,
    "full": TRAFFIC_RUNS,
}

CSV_COLUMNS = [
    "benchmark_started_at",
    "profile",
    "traffic_run",
    "scenario",
    "seed",
    "index_mode",
    "iterations",
    "concurrency",
    "intensity",
    "warmup",
    "snapshot_id",
    "snapshot_label",
    "row_kind",
    "query_type",
    "query_name",
    "calls",
    "total_exec_time_ms",
    "mean_exec_time_ms",
    "max_exec_time_ms",
    "rows",
    "planning_time_ms",
    "plan_execution_time_ms",
    "plan_total_cost",
    "plan_rows",
    "uses_index_only_scan",
    "uses_index_scan",
    "uses_seq_scan",
]


@dataclass(frozen=True)
class BenchmarkOptions:
    profiles: list
    runs: int
    iterations: int
    concurrency: int
    warmup: int
    seed: int
    output: str
    preset: str = "query_coverage"
    include_query_plans: bool = True
    reseed_each_mode: bool = True
    use_concurrently: bool = False


def _quote_index_name(name):
    return connection.ops.quote_name(name)


def _regular_index_sql(definition, concurrently=False):
    concurrently_sql = " CONCURRENTLY" if concurrently else ""
    return (
        f"CREATE INDEX{concurrently_sql} IF NOT EXISTS {_quote_index_name(definition['name'])} "
        f"ON {definition['table']} ({definition['columns']})"
    )


def _drop_regular_index_sql(definition, concurrently=False):
    concurrently_sql = " CONCURRENTLY" if concurrently else ""
    return f"DROP INDEX{concurrently_sql} IF EXISTS {_quote_index_name(definition['name'])}"


def apply_regular_indexes(concurrently=False):
    if connection.vendor != "postgresql":
        raise ValueError("Regular benchmark indexes require PostgreSQL.")
    changed = []
    with connection.cursor() as cursor:
        for definition in REGULAR_INDEX_DEFINITIONS:
            cursor.execute(_regular_index_sql(definition, concurrently=concurrently))
            changed.append(definition["name"])
    return changed


def drop_regular_indexes(concurrently=False):
    if connection.vendor != "postgresql":
        raise ValueError("Regular benchmark indexes require PostgreSQL.")
    changed = []
    with connection.cursor() as cursor:
        for definition in REGULAR_INDEX_DEFINITIONS:
            cursor.execute(_drop_regular_index_sql(definition, concurrently=concurrently))
            changed.append(definition["name"])
    return changed


def reset_pg_stats():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_stat_reset()")
        cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = %s)", ["pg_stat_statements"])
        if cursor.fetchone()[0]:
            cursor.execute("SELECT pg_stat_statements_reset()")


def prepare_index_mode(index_mode, concurrently=False):
    drop_regular_indexes(concurrently=concurrently)
    configure_experiment_indexes(
        "without_indexes",
        groups=COVERING_GROUPS,
        limit=100,
        concurrently=concurrently,
        apply_all=True,
    )
    if index_mode == "none":
        return
    if index_mode == "regular":
        apply_regular_indexes(concurrently=concurrently)
        return
    if index_mode == "covering":
        configure_experiment_indexes(
            "with_indexes",
            groups=COVERING_GROUPS,
            limit=100,
            concurrently=concurrently,
            apply_all=True,
        )
        return
    raise ValueError(f"Unknown index benchmark mode: {index_mode}")


def _operation_rows(snapshot, base_row):
    operations = ["SELECT", "INSERT", "UPDATE", "DELETE", "OTHER", "UNKNOWN"]
    query_stats = list(snapshot.query_stats.all())
    rows = []
    for operation in operations:
        matching = [query for query in query_stats if query.operation_type == operation]
        if not matching:
            continue
        calls = sum(query.calls for query in matching)
        total_exec_time = sum(query.total_exec_time for query in matching)
        rows.append(
            {
                **base_row,
                "row_kind": "operation_total",
                "query_type": operation,
                "query_name": f"{operation}_total",
                "calls": calls,
                "total_exec_time_ms": round(total_exec_time, 6),
                "mean_exec_time_ms": round(total_exec_time / max(calls, 1), 6),
                "max_exec_time_ms": round(max((query.max_exec_time for query in matching), default=0), 6),
                "rows": sum(query.rows for query in matching),
            }
        )
    return rows


def _top_query_rows(snapshot, base_row, limit_per_operation=5):
    rows = []
    for operation in ["SELECT", "INSERT", "UPDATE", "DELETE"]:
        matching = sorted(
            [query for query in snapshot.query_stats.all() if query.operation_type == operation],
            key=lambda query: (query.total_exec_time, query.calls),
            reverse=True,
        )[:limit_per_operation]
        for query in matching:
            rows.append(
                {
                    **base_row,
                    "row_kind": "top_query",
                    "query_type": operation,
                    "query_name": " ".join((query.query_text_normalized or query.queryid).split())[:240],
                    "calls": query.calls,
                    "total_exec_time_ms": round(query.total_exec_time, 6),
                    "mean_exec_time_ms": round(query.mean_exec_time, 6),
                    "max_exec_time_ms": round(query.max_exec_time, 6),
                    "rows": query.rows,
                }
            )
    return rows


def _plan_rows(snapshot, base_row):
    rows = []
    for plan in snapshot.query_plans.all():
        rows.append(
            {
                **base_row,
                "row_kind": "query_plan",
                "query_type": "SELECT",
                "query_name": plan.name,
                "planning_time_ms": round(plan.planning_time_ms, 6),
                "plan_execution_time_ms": round(plan.execution_time_ms, 6),
                "plan_total_cost": round(plan.total_cost, 6),
                "plan_rows": plan.plan_rows,
                "uses_index_only_scan": plan.uses_index_only_scan,
                "uses_index_scan": plan.uses_index_scan,
                "uses_seq_scan": plan.uses_seq_scan,
            }
        )
    return rows


def _snapshot_to_csv_rows(snapshot, base_row):
    snapshot = StatsSnapshot.objects.prefetch_related("query_stats", "query_plans").get(id=snapshot.id)
    rows = []
    rows.extend(_operation_rows(snapshot, base_row))
    rows.extend(_top_query_rows(snapshot, base_row))
    rows.extend(_plan_rows(snapshot, base_row))
    return rows


def _write_rows(output, rows, append=False):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if append else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if not append:
            writer.writeheader()
        writer.writerows(rows)


def _effective_concurrency(profile, scenario, requested_concurrency):
    heavy_reporting = scenario in {"sales_report_heavy", "reporting"}
    if profile == "huge" and heavy_reporting:
        return 1
    if profile == "huge" and scenario == "mixed_heavy":
        return min(requested_concurrency, 2)
    return requested_concurrency


def run_index_benchmark(options, progress_callback=None):
    if connection.vendor != "postgresql":
        raise ValueError(f"Index benchmark requires PostgreSQL; current backend is {connection.vendor}.")

    sync_experiment_index_catalog()
    started_at = timezone.now().isoformat()
    traffic_runs = TRAFFIC_PRESETS[options.preset][: max(1, options.runs)]
    wrote_header = False
    total_rows = 0
    snapshots = []

    for profile in options.profiles:
        if progress_callback:
            progress_callback(f"Preparing dataset profile `{profile}`...")
        seed_demo_data(size=profile, seed=options.seed, clear_existing=True, progress_callback=progress_callback)

        for index_mode in ["none", "regular", "covering"]:
            if options.reseed_each_mode and index_mode != "none":
                seed_demo_data(size=profile, seed=options.seed, clear_existing=True, progress_callback=progress_callback)
            if progress_callback:
                progress_callback(f"Preparing index mode `{index_mode}` for profile `{profile}`...")
            prepare_index_mode(index_mode, concurrently=options.use_concurrently)

            for run_number, traffic in enumerate(traffic_runs, start=1):
                seed = options.seed + traffic["seed_offset"] + run_number
                scenario = traffic["scenario"]
                intensity = traffic["intensity"]
                effective_concurrency = _effective_concurrency(profile, scenario, options.concurrency)
                label = f"bench-{profile}-{index_mode}-{run_number:02d}-{scenario}"
                if progress_callback:
                    progress_callback(f"Running {label} with concurrency={effective_concurrency}...")

                reset_pg_stats()
                summary = run_simulation(
                    scenario=scenario,
                    duration=30,
                    seed=seed,
                    iterations=options.iterations,
                    concurrency=effective_concurrency,
                    warmup=options.warmup,
                    intensity=intensity,
                    profile=profile,
                    progress_callback=progress_callback,
                )
                record_workload_run(summary, command_options={"benchmark": True, "index_mode": index_mode})
                snapshot, _ = collect_stats_snapshot(label=label, environment=f"benchmark-{profile}-{index_mode}")
                if options.include_query_plans:
                    capture_representative_query_plans(snapshot)

                base_row = {
                    "benchmark_started_at": started_at,
                    "profile": profile,
                    "traffic_run": run_number,
                    "scenario": scenario,
                    "seed": seed,
                    "index_mode": index_mode,
                    "iterations": options.iterations,
                    "concurrency": effective_concurrency,
                    "intensity": intensity,
                    "warmup": options.warmup,
                    "snapshot_id": snapshot.id,
                    "snapshot_label": snapshot.label,
                }
                rows = _snapshot_to_csv_rows(snapshot, base_row)
                _write_rows(options.output, rows, append=wrote_header)
                wrote_header = True
                total_rows += len(rows)
                snapshots.append(snapshot.id)

    return {
        "output": options.output,
        "rows": total_rows,
        "snapshots": snapshots,
        "profiles": options.profiles,
        "runs": len(traffic_runs),
        "preset": options.preset,
        "index_modes": ["none", "regular", "covering"],
    }
