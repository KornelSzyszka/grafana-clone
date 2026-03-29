from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone

from shop.models import Order, Product


def get_product_listing(category_slug=None, search=None, sort="popular", page=1, page_size=20, created_after_days=None):
    queryset = Product.objects.filter(is_active=True).select_related("category")

    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)

    if search:
        if settings.ENABLE_CONTROLLED_PERFORMANCE_ISSUES:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        else:
            queryset = queryset.filter(name__icontains=search)

    # There is intentionally no index on Product.created_at so this filter becomes a workload hotspot.
    if created_after_days is not None:
        cutoff = timezone.now() - timedelta(days=created_after_days)
        queryset = queryset.filter(created_at__gte=cutoff)

    if sort == "price":
        queryset = queryset.order_by("price", "name")
    elif sort == "newest":
        queryset = queryset.order_by("-created_at", "name")
    else:
        queryset = queryset.order_by("-popularity_score", "name")

    total = queryset.count()
    offset = max(page - 1, 0) * page_size
    items = list(queryset[offset : offset + page_size])

    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": product.id,
                "name": product.name,
                "slug": product.slug,
                "price": str(product.price),
                "stock": product.stock,
                "category": product.category.slug,
                "popularity_score": product.popularity_score,
            }
            for product in items
        ],
    }


def get_product_detail(slug):
    product = (
        Product.objects.filter(slug=slug, is_active=True)
        .select_related("category")
        .prefetch_related("reviews__user")
        .first()
    )
    if not product:
        return None

    similar_products = list(
        Product.objects.filter(category=product.category, is_active=True)
        .exclude(id=product.id)
        .order_by("-popularity_score", "name")[:4]
    )

    reviews = list(product.reviews.all()[:5])
    average_rating = product.reviews.aggregate(avg=Avg("rating"))["avg"]

    return {
        "product": {
            "id": product.id,
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "price": str(product.price),
            "stock": product.stock,
            "category": product.category.slug,
            "average_rating": average_rating,
        },
        "reviews": [
            {
                "user": review.user.username,
                "rating": review.rating,
                "content": review.content,
                "created_at": review.created_at.isoformat(),
            }
            for review in reviews
        ],
        "similar_products": [
            {
                "slug": similar.slug,
                "name": similar.name,
                "price": str(similar.price),
            }
            for similar in similar_products
        ],
    }


def get_order_history(user_id, limit=10):
    user = get_user_model().objects.filter(id=user_id).first()
    if not user:
        return None

    orders_queryset = Order.objects.filter(user_id=user_id).order_by("-created_at")
    if not settings.ENABLE_CONTROLLED_PERFORMANCE_ISSUES:
        orders_queryset = orders_queryset.select_related("user").prefetch_related("items__product")
    orders = orders_queryset[:limit]

    if not orders:
        return None

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        "orders": [
            {
                "id": order.id,
                "status": order.status,
                "created_at": order.created_at.isoformat(),
                "total_amount": str(order.total_amount),
                "items": [
                    {
                        "product_slug": item.product.slug,
                        "product_name": item.product.name,
                        "quantity": item.quantity,
                        "line_total": str(item.line_total),
                    }
                    # Without prefetch_related this becomes an intentional N+1 hotspot.
                    for item in order.items.all()
                ],
            }
            for order in orders
        ],
    }


def get_sales_report(days=30):
    since = timezone.now() - timedelta(days=days)
    rows = (
        Order.objects.filter(
            created_at__gte=since,
            status__in=[Order.Status.PAID, Order.Status.SHIPPED, Order.Status.DELIVERED],
        )
        .values(category_name=F("items__product__category__name"))
        .annotate(
            order_count=Count("id", distinct=True),
            revenue=Sum("items__line_total"),
        )
        .order_by("-revenue", "category_name")
    )

    totals = defaultdict(int)
    for row in rows:
        totals["orders"] += row["order_count"] or 0

    return {
        "window_days": days,
        "totals": {
            "orders": totals["orders"],
            "categories": len(rows),
        },
        "categories": [
            {
                "category": row["category_name"] or "uncategorized",
                "order_count": row["order_count"] or 0,
                "revenue": str(row["revenue"] or 0),
            }
            for row in rows
        ],
    }
