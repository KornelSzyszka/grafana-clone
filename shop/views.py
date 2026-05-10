from django.shortcuts import render
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET

from shop.services import get_order_history, get_product_detail, get_product_listing, get_sales_report, get_users


def _bar_chart_rows(rows, value_key, label_key, suffix="", top=6):
    rows = list(rows[:top])
    if not rows:
        return []
    max_value = max((row.get(value_key, 0) or 0) for row in rows) or 1
    chart = []
    for row in rows:
        value = row.get(value_key, 0) or 0
        chart.append(
            {
                "label": row.get(label_key, ""),
                "value": value,
                "width": round((value / max_value) * 100, 2),
                "suffix": suffix,
            }
        )
    return chart


def _build_products_page_context(request):
    created_after_days = request.GET.get("created_after_days")
    context = get_product_listing(
        category_slug=request.GET.get("category"),
        search=request.GET.get("search"),
        sort=request.GET.get("sort", "popular"),
        page=int(request.GET.get("page", 1)),
        page_size=min(int(request.GET.get("page_size", 20)), 100),
        created_after_days=int(created_after_days) if created_after_days else None,
    )
    items = context["items"]
    low_stock = sum(1 for item in items if item["stock"] <= 10)
    high_stock = sum(1 for item in items if item["stock"] > 10)
    categories = {}
    for item in items:
        categories[item["category"]] = categories.get(item["category"], 0) + 1

    ranked_categories = sorted(
        [{"category": name, "count": count} for name, count in categories.items()],
        key=lambda row: (-row["count"], row["category"]),
    )
    context["summary"] = {
        "low_stock": low_stock,
        "high_stock": high_stock,
        "avg_popularity": round(sum(item["popularity_score"] for item in items) / max(len(items), 1), 1) if items else 0,
    }
    context["charts"] = {
        "popular_products": _bar_chart_rows(items, "popularity_score", "name", suffix="%"),
        "categories": _bar_chart_rows(ranked_categories, "count", "category"),
    }
    return context


def _build_users_page_context():
    context = get_users() or {"users": []}
    users = context["users"]
    context["summary"] = {
        "count": len(users),
        "with_email": sum(1 for user in users if user["email"]),
        "without_email": sum(1 for user in users if not user["email"]),
    }
    context["charts"] = {
        "user_ids": _bar_chart_rows(
            [{"label": user["username"], "value": user["id"]} for user in users],
            "value",
            "label",
            top=8,
        )
    }
    return context


def _build_sales_page_context(days):
    context = get_sales_report(days=days)
    categories = sorted(context["categories"], key=lambda row: float(row["revenue"]), reverse=True)
    context["summary"] = {
        "top_category": categories[0]["category"] if categories else "n/a",
        "top_revenue": categories[0]["revenue"] if categories else "0",
    }
    context["charts"] = {
        "revenue": _bar_chart_rows(
            [{"label": row["category"], "value": float(row["revenue"])} for row in categories],
            "value",
            "label",
            suffix=" PLN",
            top=8,
        ),
        "orders": _bar_chart_rows(
            [{"label": row["category"], "value": row["order_count"]} for row in categories],
            "value",
            "label",
            top=8,
        ),
    }
    return context


@require_GET
def api_root(_request):
    context = {
        "service": "grafana-clone-foundation",
        "endpoints": {
            "products": "/products/",
            "monitoring": "/monitoring/",
            "users": "/users/",
            "sales_report": "/reports/sales/",
        },
    }
    return render(_request, "shop/root.html", context)

    '''
    return JsonResponse(
        {
            "service": "grafana-clone-foundation",
            "endpoints": {
                "products": "/api/products/",
                "product_detail": "/api/products/<slug:slug>/",
                "order_history": "/api/users/<int:user_id>/orders/",
                "sales_report": "/api/reports/sales/",
            },
        }
    )
    '''


@require_GET
def product_list_view(_request):
    return JsonResponse(_build_products_page_context(_request) | {})


@require_GET
def products_page(_request):
    context = _build_products_page_context(_request)
    return render(_request, "shop/products.html", context)


@require_GET
def users_api(_request):
    return JsonResponse(get_users() or {"users": []})


@require_GET
def users_page(_request):
    context = _build_users_page_context()
    return render(_request, "shop/users.html", context)


@require_GET
def product_detail_view(_request, slug):
    payload = get_product_detail(slug)
    if not payload:
        raise Http404("Product not found")
    return JsonResponse(payload)


@require_GET
def order_history_view(_request, user_id):
    payload = get_order_history(user_id=user_id)
    if not payload:
        raise Http404("User or orders not found")
    return JsonResponse(payload)


@require_GET
def sales_report_api(_request):
    days = int(_request.GET.get("days", 30))
    return JsonResponse(get_sales_report(days=days))


@require_GET
def sales_report_page(_request):
    days = int(_request.GET.get("days", 30))
    context = _build_sales_page_context(days=days)
    return render(_request, "shop/sales_report.html", context)
