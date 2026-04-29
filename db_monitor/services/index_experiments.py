from db_monitor.models import StatsSnapshot
from django.db import connection


INDEX_CANDIDATE_RULES = [
    {
        "name": "shop_product_created_at_idx",
        "table": "shop_product",
        "columns": "created_at DESC",
        "description": "Recent product filtering and newest-product sorting",
        "match_all": ["shop_product", "created_at"],
    },
    {
        "name": "shop_product_active_created_at_idx",
        "table": "shop_product",
        "columns": "is_active, created_at DESC",
        "description": "Active catalog listing ordered by newest products",
        "match_all": ["shop_product", "is_active", "created_at"],
    },
    {
        "name": "shop_product_name_trgm_idx",
        "table": "shop_product",
        "using": "USING gin",
        "columns": "name gin_trgm_ops",
        "extensions": ["pg_trgm"],
        "description": "ILIKE search on Product.name",
        "match_all": ["shop_product", "ilike", "name"],
    },
    {
        "name": "shop_product_description_trgm_idx",
        "table": "shop_product",
        "using": "USING gin",
        "columns": "description gin_trgm_ops",
        "extensions": ["pg_trgm"],
        "description": "ILIKE search on Product.description",
        "match_all": ["shop_product", "ilike", "description"],
    },
    {
        "name": "shop_order_user_created_at_idx",
        "table": "shop_order",
        "columns": "user_id, created_at DESC",
        "description": "Order history lookup by user sorted by newest orders",
        "match_all": ["shop_order", "user_id", "created_at"],
    },
    {
        "name": "shop_order_status_created_at_idx",
        "table": "shop_order",
        "columns": "status, created_at DESC",
        "description": "Sales report filtering by order status and date window",
        "match_all": ["shop_order", "status", "created_at"],
    },
    {
        "name": "shop_review_product_created_at_idx",
        "table": "shop_review",
        "columns": "product_id, created_at DESC",
        "description": "Recent product review lookup ordered by newest reviews",
        "match_all": ["shop_review", "product_id", "created_at"],
    },
]

DEFAULT_INDEX_NAMES = {
    "shop_product_created_at_idx",
    "shop_product_name_trgm_idx",
}


def _normalize_query_text(text):
    return " ".join((text or "").split()).lower()


def _index_sql(index_definition):
    using = f" {index_definition['using']}" if index_definition.get("using") else ""
    return (
        f"CREATE INDEX {index_definition['name']} "
        f"ON {index_definition['table']}{using} ({index_definition['columns']})"
    )


def _extension_exists(cursor, extension_name):
    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = %s)", [extension_name])
    return bool(cursor.fetchone()[0])


def _index_exists(cursor, index_name):
    cursor.execute("SELECT to_regclass(%s)", [index_name])
    return bool(cursor.fetchone()[0])


def _resolve_snapshot(snapshot=None):
    if snapshot is None:
        return (
            StatsSnapshot.objects.filter(query_stats__isnull=False)
            .prefetch_related("query_stats")
            .distinct()
            .order_by("-created_at", "-id")
            .first()
        )
    if isinstance(snapshot, StatsSnapshot):
        return StatsSnapshot.objects.prefetch_related("query_stats").get(id=snapshot.id)
    if isinstance(snapshot, int):
        return StatsSnapshot.objects.prefetch_related("query_stats").get(id=snapshot)
    if isinstance(snapshot, str) and snapshot.strip():
        return (
            StatsSnapshot.objects.filter(label=snapshot.strip())
            .prefetch_related("query_stats")
            .order_by("-created_at", "-id")
            .first()
        )
    return None


def _matches_rule(query_text, rule):
    match_all = [token.lower() for token in rule.get("match_all", [])]
    return bool(query_text and all(token in query_text for token in match_all))


def recommend_experiment_indexes(snapshot=None, limit=5):
    resolved_snapshot = _resolve_snapshot(snapshot)
    if not resolved_snapshot:
        return [rule for rule in INDEX_CANDIDATE_RULES if rule["name"] in DEFAULT_INDEX_NAMES][:limit]

    selected = []
    selected_names = set()
    query_rows = sorted(
        resolved_snapshot.query_stats.all(),
        key=lambda row: (row.total_exec_time or 0, row.mean_exec_time or 0, row.calls or 0),
        reverse=True,
    )

    for row in query_rows:
        normalized_query = _normalize_query_text(row.query_text_normalized)
        for rule in INDEX_CANDIDATE_RULES:
            if rule["name"] in selected_names:
                continue
            if not _matches_rule(normalized_query, rule):
                continue
            selected.append(
                {
                    **rule,
                    "source_queryid": row.queryid or "",
                    "source_query": " ".join((row.query_text_normalized or "").split()),
                    "source_total_exec_time": row.total_exec_time or 0,
                    "source_mean_exec_time": row.mean_exec_time or 0,
                }
            )
            selected_names.add(rule["name"])
            if len(selected) >= limit:
                return selected

    if not selected:
        return [rule for rule in INDEX_CANDIDATE_RULES if rule["name"] in DEFAULT_INDEX_NAMES][:limit]

    return selected


def _managed_index_definitions(snapshot=None, limit=5):
    selected = recommend_experiment_indexes(snapshot=snapshot, limit=limit)
    selected_names = {item["name"] for item in selected}
    remaining = [rule for rule in INDEX_CANDIDATE_RULES if rule["name"] not in selected_names]
    return selected + remaining


def _collect_index_state(cursor, definitions):
    state = []
    for definition in definitions:
        state.append(
            {
                "name": definition["name"],
                "table": definition["table"],
                "columns": definition["columns"],
                "description": definition["description"],
                "source_query": definition.get("source_query", ""),
                "source_total_exec_time": definition.get("source_total_exec_time", 0),
                "present": _index_exists(cursor, definition["name"]),
            }
        )
    return state


def get_experiment_index_state(snapshot=None, limit=5):
    if connection.vendor != "postgresql":
        return {
            "database_vendor": connection.vendor,
            "mode": "unsupported",
            "indexes": [],
            "notes": ["Index experiment tooling requires PostgreSQL."],
            "selection_strategy": "top longest-running queries from before snapshot",
        }

    definitions = _managed_index_definitions(snapshot=snapshot, limit=limit)
    with connection.cursor() as cursor:
        state = _collect_index_state(cursor, definitions)

    return {
        "database_vendor": connection.vendor,
        "mode": "with_indexes" if any(item["present"] for item in state) else "without_indexes",
        "indexes": state,
        "notes": [],
        "selection_strategy": "top longest-running queries from before snapshot",
    }


def configure_experiment_indexes(mode, snapshot=None, limit=5):
    if mode not in {"with_indexes", "without_indexes"}:
        raise ValueError("Mode must be either `with_indexes` or `without_indexes`.")

    if connection.vendor != "postgresql":
        raise ValueError("Index experiment tooling requires PostgreSQL.")

    notes = []
    changed = []
    selected_definitions = recommend_experiment_indexes(snapshot=snapshot, limit=limit)
    selected_names = {definition["name"] for definition in selected_definitions}
    all_definitions = _managed_index_definitions(snapshot=snapshot, limit=limit)

    with connection.cursor() as cursor:
        for definition in all_definitions:
            if mode == "with_indexes":
                if definition["name"] not in selected_names:
                    continue

                missing_extensions = [
                    extension
                    for extension in definition.get("extensions", [])
                    if not _extension_exists(cursor, extension)
                ]
                if missing_extensions:
                    notes.append(
                        f"Skipped {definition['name']} because missing extension(s): {', '.join(missing_extensions)}."
                    )
                    continue

                if _index_exists(cursor, definition["name"]):
                    notes.append(f"Index {definition['name']} already present.")
                    continue

                cursor.execute(_index_sql(definition))
                changed.append({"name": definition["name"], "action": "created"})
            else:
                if not _index_exists(cursor, definition["name"]):
                    continue
                cursor.execute(f"DROP INDEX {definition['name']}")
                changed.append({"name": definition["name"], "action": "dropped"})

        state = _collect_index_state(cursor, all_definitions)

    return {
        "database_vendor": connection.vendor,
        "mode": mode,
        "indexes": state,
        "changed": changed,
        "notes": notes,
        "selection_strategy": "top longest-running queries from before snapshot",
        "selected_indexes": [item for item in state if item["name"] in selected_names],
    }
