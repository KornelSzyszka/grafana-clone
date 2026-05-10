import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone

from db_monitor.models import QueryPlanSnapshot, StatsSnapshot
from shop.models import Order, Product


def _walk_plan_nodes(node):
    yield node
    for child in node.get("Plans", []) or []:
        yield from _walk_plan_nodes(child)


def _plan_flags(plan_root):
    node_types = {node.get("Node Type", "") for node in _walk_plan_nodes(plan_root)}
    return {
        "uses_index_only_scan": "Index Only Scan" in node_types,
        "uses_seq_scan": "Seq Scan" in node_types,
        "uses_index_scan": bool({"Index Scan", "Bitmap Index Scan", "Index Only Scan"}.intersection(node_types)),
    }


def _record_plan(snapshot, name, description, queryset):
    rendered_sql = str(queryset.query)
    raw_plan = queryset.explain(analyze=True, buffers=True, format="json")
    parsed = json.loads(raw_plan)
    top = parsed[0] if parsed else {}
    plan_root = top.get("Plan", {})
    flags = _plan_flags(plan_root)
    return QueryPlanSnapshot.objects.create(
        snapshot=snapshot,
        name=name,
        description=description,
        sql=rendered_sql,
        plan_json=top,
        total_cost=plan_root.get("Total Cost") or 0,
        plan_rows=plan_root.get("Plan Rows") or 0,
        execution_time_ms=top.get("Execution Time") or 0,
        planning_time_ms=top.get("Planning Time") or 0,
        **flags,
    )


def _representative_queries():
    cutoff = timezone.now() - timedelta(days=90)
    product_base = Product.objects.filter(is_active=True, created_at__gte=cutoff)
    category_id = Product.objects.values_list("category_id", flat=True).first()
    if category_id:
        product_base = product_base.filter(category_id=category_id)

    yield (
        "catalog_newest_covering",
        "Catalog listing filtered by active/category/recent and sorted by newest products.",
        product_base.order_by("-created_at", "name").values("id", "name", "slug", "price", "stock", "popularity_score")[:50],
    )
    yield (
        "catalog_price_covering",
        "Catalog listing filtered by active/category/recent and sorted by price.",
        product_base.order_by("price", "name").values("id", "name", "slug", "price", "stock", "popularity_score")[:50],
    )

    user_id = get_user_model().objects.filter(username__startswith="demo_user_").values_list("id", flat=True).first()
    if user_id:
        yield (
            "order_history_covering",
            "Order history filtered by user and sorted by newest orders.",
            Order.objects.filter(user_id=user_id)
            .order_by("-created_at")
            .values("id", "status", "total_amount", "created_at")[:25],
        )


def capture_representative_query_plans(snapshot):
    if isinstance(snapshot, int):
        snapshot = StatsSnapshot.objects.get(id=snapshot)
    if connection.vendor != "postgresql":
        return {
            "captured": 0,
            "skipped": True,
            "reason": f"Query plan capture requires PostgreSQL; current backend is {connection.vendor}.",
        }

    QueryPlanSnapshot.objects.filter(snapshot=snapshot).delete()
    captured = []
    for name, description, queryset in _representative_queries():
        if not queryset.exists():
            continue
        captured.append(_record_plan(snapshot, name, description, queryset))

    return {
        "captured": len(captured),
        "skipped": False,
        "plans": [
            {
                "name": plan.name,
                "execution_time_ms": plan.execution_time_ms,
                "uses_index_only_scan": plan.uses_index_only_scan,
                "uses_seq_scan": plan.uses_seq_scan,
                "uses_index_scan": plan.uses_index_scan,
            }
            for plan in captured
        ],
    }
