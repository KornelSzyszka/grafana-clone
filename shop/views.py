from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET
from django.shortcuts import render

from shop.services import get_order_history, get_product_detail, get_product_listing, get_sales_report, get_users


@require_GET
def api_root(_request):
    context = {
            "service": "grafana-clone-foundation",
            "endpoints": {
                "products": "/api/products/",
                #"product_detail": "/api/products/<slug:slug>/",
                "users": "/api/users/",
                #"order_history": "/api/users/<int:user_id>/orders/",
                "sales_report": "/api/reports/sales/",
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
    created_after_days = _request.GET.get("created_after_days")
    payload = get_product_listing(
        category_slug=_request.GET.get("category"),
        search=_request.GET.get("search"),
        sort=_request.GET.get("sort", "popular"),
        page=int(_request.GET.get("page", 1)),
        page_size=min(int(_request.GET.get("page_size", 20)), 100),
        created_after_days=int(created_after_days) if created_after_days else None,
    )

    return render(_request, "shop/products.html", payload)

    '''
    return JsonResponse(payload)
    '''


@require_GET
def users(_request):
    context = get_users()
    return render(_request, "shop/users.html", context)


@require_GET
def product_detail_view(_request, slug):
    payload = get_product_detail(slug)
    if not payload:
        raise Http404("Product not found")
    
    return render(_request, "shop/product.html", payload)
    '''
    return JsonResponse(payload)
    '''


@require_GET
def order_history_view(_request, user_id):
    payload = get_order_history(user_id=user_id)
    if not payload:
        raise Http404("User or orders not found")
    
    return render(_request, "shop/user_orders.html", payload)
    '''
    return JsonResponse(payload)
    '''


@require_GET
def sales_report_view(_request):
    days = int(_request.GET.get("days", 30))
    context = get_sales_report(days=days)

    return render(_request, "shop/sales_report.html", context)

    '''
    return JsonResponse(get_sales_report(days=days))
    '''