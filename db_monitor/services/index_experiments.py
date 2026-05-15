from django.db.utils import OperationalError, ProgrammingError

from db_monitor.models import ExperimentIndexDefinition, ExperimentIndexGroup, StatsSnapshot
from django.db import connection


EXPERIMENT_GROUPS = [
    "catalog_covering",
    "product_detail_covering",
    "order_history_covering",
    "search",
    "sales_report",
    "cleanup_covering",
    "write_cost",
]
EXPERIMENT_GROUP_DESCRIPTIONS = {
    "catalog_covering": "Covering indexes for product catalog listing flows.",
    "product_detail_covering": "Covering indexes for product detail, similar products, and review flows.",
    "order_history_covering": "Covering indexes for user order history flows.",
    "search": "Indexes for text-heavy catalog search flows.",
    "sales_report": "Indexes for reporting and aggregate windows.",
    "cleanup_covering": "Covering indexes for bounded cleanup and DELETE-heavy flows.",
    "write_cost": "Indexes included when measuring write-side maintenance overhead.",
}

INDEX_CANDIDATE_RULES = [
    {
        "name": "shop_product_covering_catalog_idx",
        "groups": ["catalog_covering", "write_cost"],
        "table": "shop_product",
        "columns": "is_active, category_id, created_at DESC",
        "include": "id, name, slug, price, stock, popularity_score",
        "description": "Covering index for active product catalog filtering by category and newest sorting",
        "match_all": ["shop_product", "is_active", "created_at"],
    },
    {
        "name": "shop_product_active_price_covering_idx",
        "groups": ["catalog_covering", "write_cost"],
        "table": "shop_product",
        "columns": "is_active, category_id, price, name",
        "include": "id, slug, stock, popularity_score",
        "description": "Covering index for active product catalog filtering by category and price sorting",
        "match_all": ["shop_product", "is_active", "price"],
    },
    {
        "name": "shop_product_popularity_covering_idx",
        "groups": ["catalog_covering", "write_cost"],
        "table": "shop_product",
        "columns": "is_active, category_id, popularity_score DESC, name",
        "include": "id, slug, price, stock, created_at",
        "description": "Covering index for active product catalog sorting by popularity",
        "match_all": ["shop_product", "is_active", "popularity_score"],
    },
    {
        "name": "shop_product_slug_detail_covering_idx",
        "groups": ["product_detail_covering", "write_cost"],
        "table": "shop_product",
        "columns": "slug, is_active",
        "include": "id, name, description, price, stock, category_id, popularity_score, created_at",
        "description": "Covering index for product detail lookup by slug",
        "match_all": ["shop_product", "slug", "is_active"],
    },
    {
        "name": "shop_product_similar_covering_idx",
        "groups": ["product_detail_covering", "catalog_covering", "write_cost"],
        "table": "shop_product",
        "columns": "category_id, is_active, popularity_score DESC, name",
        "include": "id, slug, price, stock",
        "description": "Covering index for similar products lookup by category",
        "match_all": ["shop_product", "category_id", "is_active", "popularity_score"],
    },
    {
        "name": "shop_product_name_trgm_idx",
        "groups": ["search", "write_cost"],
        "table": "shop_product",
        "using": "USING gin",
        "columns": "name gin_trgm_ops",
        "extensions": ["pg_trgm"],
        "description": "ILIKE search on Product.name",
        "match_all": ["shop_product", "ilike", "name"],
    },
    {
        "name": "shop_product_description_trgm_idx",
        "groups": ["search", "write_cost"],
        "table": "shop_product",
        "using": "USING gin",
        "columns": "description gin_trgm_ops",
        "extensions": ["pg_trgm"],
        "description": "ILIKE search on Product.description",
        "match_all": ["shop_product", "ilike", "description"],
    },
    {
        "name": "shop_order_user_created_at_covering_idx",
        "groups": ["order_history_covering", "write_cost"],
        "table": "shop_order",
        "columns": "user_id, created_at DESC",
        "include": "id, status, total_amount",
        "description": "Covering index for order history lookup by user sorted by newest orders",
        "match_all": ["shop_order", "user_id", "created_at"],
    },
    {
        "name": "shop_orderitem_order_covering_idx",
        "groups": ["order_history_covering", "sales_report", "write_cost"],
        "table": "shop_orderitem",
        "columns": "order_id",
        "include": "product_id, quantity, unit_price, line_total",
        "description": "Covering index for order history item lookup and order-based report joins",
        "match_all": ["shop_orderitem", "order_id"],
    },
    {
        "name": "shop_order_status_created_at_covering_idx",
        "groups": ["sales_report", "write_cost"],
        "table": "shop_order",
        "columns": "status, created_at DESC",
        "include": "id, user_id, total_amount",
        "description": "Covering index for sales report filtering by order status and date window",
        "match_all": ["shop_order", "status", "created_at"],
    },
    {
        "name": "shop_orderitem_product_report_covering_idx",
        "groups": ["sales_report", "write_cost"],
        "table": "shop_orderitem",
        "columns": "product_id",
        "include": "order_id, line_total, quantity",
        "description": "Covering index for sales report joins from products to order items",
        "match_all": ["shop_orderitem", "product_id", "line_total"],
    },
    {
        "name": "shop_product_id_category_covering_idx",
        "groups": ["sales_report", "write_cost"],
        "table": "shop_product",
        "columns": "id",
        "include": "category_id",
        "description": "Covering index for sales report product-to-category lookup",
        "match_all": ["shop_product", "category_id"],
    },
    {
        "name": "shop_review_product_created_at_covering_idx",
        "groups": ["product_detail_covering", "catalog_covering", "write_cost"],
        "table": "shop_review",
        "columns": "product_id, created_at DESC",
        "include": "id, user_id, rating, content",
        "description": "Covering index for recent product review lookup ordered by newest reviews",
        "match_all": ["shop_review", "product_id", "created_at"],
    },
    {
        "name": "shop_review_created_at_cleanup_covering_idx",
        "groups": ["cleanup_covering", "write_cost"],
        "table": "shop_review",
        "columns": "created_at",
        "include": "id, product_id, user_id",
        "description": "Covering index for bounded old-review cleanup queries",
        "match_all": ["shop_review", "created_at"],
    },
    {
        "name": "load_cart_cleanup_covering_idx",
        "groups": ["cleanup_covering", "write_cost"],
        "table": "load_simulator_democart",
        "columns": "expires_at, status",
        "include": "id, user_id",
        "description": "Covering index for expired demo-cart cleanup queries",
        "match_all": ["load_simulator_democart", "expires_at"],
    },
    {
        "name": "load_cart_item_cart_covering_idx",
        "groups": ["cleanup_covering", "write_cost"],
        "table": "load_simulator_democartitem",
        "columns": "cart_id",
        "include": "product_id, quantity, unit_price",
        "description": "Covering index for cart item lookup before cart cleanup",
        "match_all": ["load_simulator_democartitem", "cart_id"],
    },
]

DEFAULT_INDEX_NAMES = {
    "shop_product_covering_catalog_idx",
    "shop_product_slug_detail_covering_idx",
    "shop_order_user_created_at_covering_idx",
    "shop_product_name_trgm_idx",
}


def _normalize_query_text(text):
    return " ".join((text or "").split()).lower()


def _index_sql(index_definition):
    using = f" {index_definition['using']}" if index_definition.get("using") else ""
    include = f" INCLUDE ({index_definition['include']})" if index_definition.get("include") else ""
    return (
        f"CREATE INDEX {index_definition['name']} "
        f"ON {index_definition['table']}{using} ({index_definition['columns']}){include}"
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


def _definition_to_rule(definition):
    return {
        "name": definition.name,
        "groups": list(definition.groups.values_list("name", flat=True)),
        "table": definition.table_name,
        "using": definition.using,
        "columns": definition.columns,
        "include": definition.include,
        "extensions": definition.extensions_json or [],
        "description": definition.description,
        "match_all": definition.match_all_json or [],
        "is_default": definition.is_default,
    }


def sync_experiment_index_catalog():
    groups_by_name = {}
    for group_name in EXPERIMENT_GROUPS:
        group, _ = ExperimentIndexGroup.objects.update_or_create(
            name=group_name,
            defaults={"description": EXPERIMENT_GROUP_DESCRIPTIONS.get(group_name, "")},
        )
        groups_by_name[group_name] = group

    for rule in INDEX_CANDIDATE_RULES:
        definition, _ = ExperimentIndexDefinition.objects.update_or_create(
            name=rule["name"],
            defaults={
                "table_name": rule["table"],
                "using": rule.get("using", ""),
                "columns": rule["columns"],
                "include": rule.get("include", ""),
                "extensions_json": rule.get("extensions", []),
                "description": rule["description"],
                "match_all_json": rule.get("match_all", []),
                "is_default": rule["name"] in DEFAULT_INDEX_NAMES,
            },
        )
        definition.groups.set(groups_by_name[group] for group in rule.get("groups", []) if group in groups_by_name)


def _catalog_rules():
    try:
        if ExperimentIndexDefinition.objects.exists():
            return [
                _definition_to_rule(definition)
                for definition in ExperimentIndexDefinition.objects.prefetch_related("groups").all()
            ]
        sync_experiment_index_catalog()
        return [
            _definition_to_rule(definition)
            for definition in ExperimentIndexDefinition.objects.prefetch_related("groups").all()
        ]
    except (OperationalError, ProgrammingError):
        return list(INDEX_CANDIDATE_RULES)


def _normalize_groups(groups=None):
    if not groups:
        return []
    normalized = []
    for group in groups:
        if group not in EXPERIMENT_GROUPS:
            raise ValueError(f"Unknown experiment index group: {group}")
        normalized.append(group)
    return normalized


def _filter_by_groups(definitions, groups=None):
    normalized_groups = _normalize_groups(groups)
    if not normalized_groups:
        return list(definitions)
    selected_groups = set(normalized_groups)
    return [definition for definition in definitions if selected_groups.intersection(definition.get("groups", []))]


def recommend_experiment_indexes(snapshot=None, limit=5, groups=None):
    candidate_rules = _filter_by_groups(_catalog_rules(), groups=groups)
    resolved_snapshot = _resolve_snapshot(snapshot)
    if not resolved_snapshot:
        return [rule for rule in candidate_rules if rule["name"] in DEFAULT_INDEX_NAMES][:limit] or candidate_rules[:limit]

    selected = []
    selected_names = set()
    query_rows = sorted(
        resolved_snapshot.query_stats.all(),
        key=lambda row: (row.total_exec_time or 0, row.mean_exec_time or 0, row.calls or 0),
        reverse=True,
    )

    for row in query_rows:
        normalized_query = _normalize_query_text(row.query_text_normalized)
        for rule in candidate_rules:
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
        return [rule for rule in candidate_rules if rule["name"] in DEFAULT_INDEX_NAMES][:limit] or candidate_rules[:limit]

    return selected


def _managed_index_definitions(snapshot=None, limit=5, groups=None):
    selected = recommend_experiment_indexes(snapshot=snapshot, limit=limit, groups=groups)
    selected_names = {item["name"] for item in selected}
    remaining = [rule for rule in _filter_by_groups(_catalog_rules(), groups=groups) if rule["name"] not in selected_names]
    return selected + remaining


def _collect_index_state(cursor, definitions):
    state = []
    for definition in definitions:
        state.append(
            {
                "name": definition["name"],
                "table": definition["table"],
                "columns": definition["columns"],
                "include": definition.get("include", ""),
                "description": definition["description"],
                "groups": definition.get("groups", []),
                "source_query": definition.get("source_query", ""),
                "source_total_exec_time": definition.get("source_total_exec_time", 0),
                "present": _index_exists(cursor, definition["name"]),
            }
        )
    return state


def get_experiment_index_state(snapshot=None, limit=5, groups=None):
    if connection.vendor != "postgresql":
        return {
            "database_vendor": connection.vendor,
            "mode": "unsupported",
            "indexes": [],
            "notes": ["Index experiment tooling requires PostgreSQL."],
            "selection_strategy": "top longest-running queries from before snapshot",
        }

    definitions = _managed_index_definitions(snapshot=snapshot, limit=limit, groups=groups)
    with connection.cursor() as cursor:
        state = _collect_index_state(cursor, definitions)

    return {
        "database_vendor": connection.vendor,
        "mode": "with_indexes" if any(item["present"] for item in state) else "without_indexes",
        "indexes": state,
        "notes": [],
        "groups": _normalize_groups(groups),
        "selection_strategy": "top longest-running queries from before snapshot",
    }


def configure_experiment_indexes(mode, snapshot=None, limit=5, concurrently=False, groups=None, apply_all=False):
    if mode not in {"with_indexes", "without_indexes"}:
        raise ValueError("Mode must be either `with_indexes` or `without_indexes`.")

    if connection.vendor != "postgresql":
        raise ValueError("Index experiment tooling requires PostgreSQL.")

    notes = []
    changed = []
    if apply_all:
        selected_definitions = _filter_by_groups(_catalog_rules(), groups=groups)
    else:
        selected_definitions = recommend_experiment_indexes(snapshot=snapshot, limit=limit, groups=groups)
    selected_names = {definition["name"] for definition in selected_definitions}
    all_definitions = _managed_index_definitions(snapshot=snapshot, limit=limit, groups=groups)

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

                sql = _index_sql(definition)
                if concurrently:
                    sql = sql.replace("CREATE INDEX", "CREATE INDEX CONCURRENTLY", 1)
                cursor.execute(sql)
                changed.append({"name": definition["name"], "action": "created"})
            else:
                if not _index_exists(cursor, definition["name"]):
                    continue
                concurrently_sql = " CONCURRENTLY" if concurrently else ""
                cursor.execute(f"DROP INDEX{concurrently_sql} {definition['name']}")
                changed.append({"name": definition["name"], "action": "dropped"})

        state = _collect_index_state(cursor, all_definitions)

    return {
        "database_vendor": connection.vendor,
        "mode": mode,
        "indexes": state,
        "changed": changed,
        "notes": notes,
        "groups": _normalize_groups(groups),
        "selection_strategy": "top longest-running queries from before snapshot",
        "selected_indexes": [item for item in state if item["name"] in selected_names],
        "concurrently": concurrently,
        "apply_all": apply_all,
    }
