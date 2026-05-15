from dataclasses import dataclass

from django.db import transaction

from db_monitor.models import AnalysisFinding, StatsSnapshot

DEFAULT_THRESHOLDS = {
    "slow_query_mean_ms": 150.0,
    "slow_query_max_ms": 500.0,
    "hot_query_total_ms": 5000.0,
    "hot_query_calls": 200,
    "unused_index_idx_scan_max": 5,
    "unused_index_size_min_bytes": 1024 * 1024,
    "seq_scan_table_min": 100,
    "seq_scan_live_rows_min": 1000,
    "seq_scan_ratio_min": 3.0,
    "covering_index_total_ms": 1000.0,
    "covering_index_calls": 25,
}


@dataclass(frozen=True)
class FindingCandidate:
    type: str
    severity: str
    title: str
    description: str
    object_type: str
    object_name: str
    evidence_json: dict


def _truncate_query(query_text, limit=180):
    if len(query_text) <= limit:
        return query_text
    return f"{query_text[: limit - 3]}..."


def _query_display_name(queryid, preview):
    return _truncate_query(preview or queryid or "Query without fingerprint", limit=90)


def _query_object_name(queryid, preview):
    return _truncate_query(preview or queryid or "Query without fingerprint", limit=180)


def _severity_for_slow_query(mean_ms, max_ms):
    if mean_ms >= 500 or max_ms >= 1500:
        return "high"
    if mean_ms >= 250 or max_ms >= 1000:
        return "medium"
    return "low"


def _severity_for_hot_query(total_ms, calls):
    if total_ms >= 20000 or calls >= 2000:
        return "high"
    if total_ms >= 10000 or calls >= 800:
        return "medium"
    return "low"


def _severity_for_unused_index(index_size_bytes):
    if index_size_bytes >= 50 * 1024 * 1024:
        return "high"
    if index_size_bytes >= 10 * 1024 * 1024:
        return "medium"
    return "low"


def _severity_for_seq_scan(seq_scan, n_live_tup, ratio):
    if seq_scan >= 1000 or n_live_tup >= 100000 or ratio >= 10:
        return "high"
    if seq_scan >= 300 or n_live_tup >= 20000 or ratio >= 5:
        return "medium"
    return "low"


def _slow_query_candidates(snapshot, thresholds):
    candidates = []
    for query_stat in snapshot.query_stats.all():
        if query_stat.mean_exec_time <= thresholds["slow_query_mean_ms"] and query_stat.max_exec_time <= thresholds["slow_query_max_ms"]:
            continue
        preview = _truncate_query(query_stat.query_text_normalized.replace("\n", " "))
        candidates.append(
            FindingCandidate(
                type="slow_query",
                severity=_severity_for_slow_query(query_stat.mean_exec_time, query_stat.max_exec_time),
                title=f"Slow query detected: {_query_display_name(query_stat.queryid, preview)}",
                description=(
                    "The query exceeds the configured execution-time threshold and should be reviewed for indexes, "
                    "join strategy, or application-side batching."
                ),
                object_type="query",
                object_name=_query_object_name(query_stat.queryid, preview),
                evidence_json={
                    "queryid": query_stat.queryid,
                    "query_preview": preview,
                    "calls": query_stat.calls,
                    "mean_exec_time": query_stat.mean_exec_time,
                    "max_exec_time": query_stat.max_exec_time,
                    "thresholds": {
                        "mean_ms": thresholds["slow_query_mean_ms"],
                        "max_ms": thresholds["slow_query_max_ms"],
                    },
                },
            )
        )
    return candidates


def _hot_query_candidates(snapshot, thresholds):
    candidates = []
    for query_stat in snapshot.query_stats.all():
        if query_stat.total_exec_time < thresholds["hot_query_total_ms"] and query_stat.calls < thresholds["hot_query_calls"]:
            continue
        preview = _truncate_query(query_stat.query_text_normalized.replace("\n", " "))
        candidates.append(
            FindingCandidate(
                type="hot_query",
                severity=_severity_for_hot_query(query_stat.total_exec_time, query_stat.calls),
                title=f"High-cost hot query: {_query_display_name(query_stat.queryid, preview)}",
                description=(
                    "The query contributes a large cumulative execution cost. Even if single runs are acceptable, "
                    "its frequency makes it a likely optimization target."
                ),
                object_type="query",
                object_name=_query_object_name(query_stat.queryid, preview),
                evidence_json={
                    "queryid": query_stat.queryid,
                    "query_preview": preview,
                    "calls": query_stat.calls,
                    "total_exec_time": query_stat.total_exec_time,
                    "mean_exec_time": query_stat.mean_exec_time,
                    "thresholds": {
                        "total_ms": thresholds["hot_query_total_ms"],
                        "calls": thresholds["hot_query_calls"],
                    },
                },
            )
        )
    return candidates


def _unused_index_candidates(snapshot, thresholds):
    candidates = []
    for index_stat in snapshot.index_stats.all():
        if index_stat.idx_scan > thresholds["unused_index_idx_scan_max"]:
            continue
        if index_stat.index_size_bytes < thresholds["unused_index_size_min_bytes"]:
            continue
        candidates.append(
            FindingCandidate(
                type="unused_index",
                severity=_severity_for_unused_index(index_stat.index_size_bytes),
                title=f"Candidate unused index `{index_stat.index_name}`",
                description=(
                    "The index has very low scan count relative to its size, so it may be unused or not worth its "
                    "maintenance cost."
                ),
                object_type="index",
                object_name=f"{index_stat.schema_name}.{index_stat.index_name}",
                evidence_json={
                    "schema_name": index_stat.schema_name,
                    "table_name": index_stat.table_name,
                    "index_name": index_stat.index_name,
                    "idx_scan": index_stat.idx_scan,
                    "index_size_bytes": index_stat.index_size_bytes,
                    "thresholds": {
                        "idx_scan_max": thresholds["unused_index_idx_scan_max"],
                        "size_min_bytes": thresholds["unused_index_size_min_bytes"],
                    },
                },
            )
        )
    return candidates


def _seq_scan_candidates(snapshot, thresholds):
    candidates = []
    for table_stat in snapshot.table_stats.all():
        if table_stat.seq_scan < thresholds["seq_scan_table_min"]:
            continue
        if table_stat.n_live_tup < thresholds["seq_scan_live_rows_min"]:
            continue
        ratio = table_stat.seq_scan / max(table_stat.idx_scan, 1)
        if ratio < thresholds["seq_scan_ratio_min"]:
            continue
        candidates.append(
            FindingCandidate(
                type="seq_scan_heavy_table",
                severity=_severity_for_seq_scan(table_stat.seq_scan, table_stat.n_live_tup, ratio),
                title=f"Seq-scan-heavy table `{table_stat.table_name}`",
                description=(
                    "The table shows heavy sequential scans compared with index scans, which may indicate missing "
                    "indexes or inefficient filter patterns."
                ),
                object_type="table",
                object_name=f"{table_stat.schema_name}.{table_stat.table_name}",
                evidence_json={
                    "schema_name": table_stat.schema_name,
                    "table_name": table_stat.table_name,
                    "seq_scan": table_stat.seq_scan,
                    "idx_scan": table_stat.idx_scan,
                    "n_live_tup": table_stat.n_live_tup,
                    "n_dead_tup": table_stat.n_dead_tup,
                    "seq_to_idx_ratio": ratio,
                    "thresholds": {
                        "seq_scan_min": thresholds["seq_scan_table_min"],
                        "live_rows_min": thresholds["seq_scan_live_rows_min"],
                        "ratio_min": thresholds["seq_scan_ratio_min"],
                    },
                },
            )
        )
    return candidates


def _covering_index_candidates(snapshot, thresholds):
    rules = [
        {
            "name": "shop_product_covering_catalog_idx",
            "table": "shop_product",
            "tokens": ["shop_product", "is_active", "created_at"],
            "columns": ["is_active", "category_id", "created_at DESC"],
            "include": ["id", "name", "slug", "price", "stock", "popularity_score"],
            "reason": "active catalog listings filter and sort on a narrow column set and return only listing fields",
        },
        {
            "name": "shop_product_active_price_covering_idx",
            "table": "shop_product",
            "tokens": ["shop_product", "is_active", "price"],
            "columns": ["is_active", "category_id", "price", "name"],
            "include": ["id", "slug", "stock", "popularity_score"],
            "reason": "price-sorted catalog listings can be served from a covering B-tree index",
        },
        {
            "name": "shop_product_popularity_covering_idx",
            "table": "shop_product",
            "tokens": ["shop_product", "is_active", "popularity_score"],
            "columns": ["is_active", "category_id", "popularity_score DESC", "name"],
            "include": ["id", "slug", "price", "stock", "created_at"],
            "reason": "popular catalog listings repeatedly sort active/category products by popularity",
        },
        {
            "name": "shop_product_slug_detail_covering_idx",
            "table": "shop_product",
            "tokens": ["shop_product", "slug", "is_active"],
            "columns": ["slug", "is_active"],
            "include": ["id", "name", "description", "price", "stock", "category_id", "popularity_score"],
            "reason": "product detail lookup uses slug and returns a compact detail projection",
        },
        {
            "name": "shop_product_similar_covering_idx",
            "table": "shop_product",
            "tokens": ["shop_product", "category_id", "popularity_score"],
            "columns": ["category_id", "is_active", "popularity_score DESC", "name"],
            "include": ["id", "slug", "price", "stock"],
            "reason": "similar product lookup filters by category and sorts by popularity",
        },
        {
            "name": "shop_order_user_created_at_covering_idx",
            "table": "shop_order",
            "tokens": ["shop_order", "user_id", "created_at"],
            "columns": ["user_id", "created_at DESC"],
            "include": ["id", "status", "total_amount"],
            "reason": "order history repeatedly filters by user and returns summary fields ordered by newest order",
        },
        {
            "name": "shop_orderitem_order_covering_idx",
            "table": "shop_orderitem",
            "tokens": ["shop_orderitem", "order_id"],
            "columns": ["order_id"],
            "include": ["product_id", "quantity", "unit_price", "line_total"],
            "reason": "order history renders order item fields after selecting orders",
        },
        {
            "name": "shop_order_status_created_at_covering_idx",
            "table": "shop_order",
            "tokens": ["shop_order", "status", "created_at"],
            "columns": ["status", "created_at DESC"],
            "include": ["id", "user_id", "total_amount"],
            "reason": "sales reports repeatedly filter orders by status and time window",
        },
        {
            "name": "shop_review_product_created_at_covering_idx",
            "table": "shop_review",
            "tokens": ["shop_review", "product_id", "created_at"],
            "columns": ["product_id", "created_at DESC"],
            "include": ["id", "user_id", "rating", "content"],
            "reason": "product detail pages read recent reviews for one product",
        },
        {
            "name": "load_cart_cleanup_covering_idx",
            "table": "load_simulator_democart",
            "tokens": ["load_simulator_democart", "expires_at"],
            "columns": ["expires_at", "status"],
            "include": ["id", "user_id"],
            "reason": "cleanup workload scans bounded expired carts before DELETE",
        },
    ]

    candidates = []
    for query_stat in snapshot.query_stats.all():
        normalized = " ".join((query_stat.query_text_normalized or "").split()).lower()
        if query_stat.total_exec_time < thresholds["covering_index_total_ms"] and query_stat.calls < thresholds["covering_index_calls"]:
            continue
        for rule in rules:
            if not all(token in normalized for token in rule["tokens"]):
                continue
            preview = _truncate_query(query_stat.query_text_normalized.replace("\n", " "))
            candidates.append(
                FindingCandidate(
                    type="covering_index_candidate",
                    severity=_severity_for_hot_query(query_stat.total_exec_time, query_stat.calls),
                    title=f"Covering index candidate `{rule['name']}`",
                    description=(
                        "This query pattern is a candidate for a PostgreSQL B-tree index with INCLUDE columns. "
                        "The goal is to reduce heap fetches and make index-only scans possible after VACUUM visibility improves."
                    ),
                    object_type="query",
                    object_name=_query_object_name(query_stat.queryid, preview),
                    evidence_json={
                        "queryid": query_stat.queryid,
                        "query_preview": preview,
                        "calls": query_stat.calls,
                        "total_exec_time": query_stat.total_exec_time,
                        "mean_exec_time": query_stat.mean_exec_time,
                        "suggested_index": rule["name"],
                        "table": rule["table"],
                        "columns": rule["columns"],
                        "include": rule["include"],
                        "reason": rule["reason"],
                    },
                )
            )
            break
    return candidates


def _build_candidates(snapshot, thresholds):
    candidates = []
    candidates.extend(_slow_query_candidates(snapshot, thresholds))
    candidates.extend(_hot_query_candidates(snapshot, thresholds))
    candidates.extend(_unused_index_candidates(snapshot, thresholds))
    candidates.extend(_seq_scan_candidates(snapshot, thresholds))
    candidates.extend(_covering_index_candidates(snapshot, thresholds))
    return candidates


@transaction.atomic
def analyze_snapshot(snapshot, thresholds=None, replace_existing=True):
    if isinstance(snapshot, int):
        snapshot = StatsSnapshot.objects.get(id=snapshot)

    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    if replace_existing:
        snapshot.findings.all().delete()

    candidates = _build_candidates(snapshot, thresholds)
    AnalysisFinding.objects.bulk_create(
        [
            AnalysisFinding(
                snapshot=snapshot,
                type=candidate.type,
                severity=candidate.severity,
                title=candidate.title,
                description=candidate.description,
                object_type=candidate.object_type,
                object_name=candidate.object_name,
                evidence_json=candidate.evidence_json,
            )
            for candidate in candidates
        ],
        batch_size=500,
    )

    summary = {
        "created": len(candidates),
        "by_type": {},
        "thresholds": thresholds,
    }
    for candidate in candidates:
        summary["by_type"][candidate.type] = summary["by_type"].get(candidate.type, 0) + 1
    return snapshot, summary
