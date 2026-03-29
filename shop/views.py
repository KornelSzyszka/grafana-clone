from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET

from shop.services import get_order_history, get_product_detail, get_product_listing, get_sales_report


@require_GET
def api_root(_request):
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


@require_GET
def product_list_view(request):
    created_after_days = request.GET.get("created_after_days")
    payload = get_product_listing(
        category_slug=request.GET.get("category"),
        search=request.GET.get("search"),
        sort=request.GET.get("sort", "popular"),
        page=int(request.GET.get("page", 1)),
        page_size=min(int(request.GET.get("page_size", 20)), 100),
        created_after_days=int(created_after_days) if created_after_days else None,
    )
    return JsonResponse(payload)


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
def sales_report_view(request):
    days = int(request.GET.get("days", 30))
    return JsonResponse(get_sales_report(days=days))
