import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection, connections, transaction
from django.db.models import F
from django.utils import timezone

from load_simulator.models import DemoCart, DemoCartItem
from shop.models import Category, Order, OrderItem, Product, Review
from shop.services import get_order_history, get_product_detail, get_product_listing, get_sales_report

READ_OPERATIONS = ["catalog", "details", "order_history", "reporting", "covering_catalog"]
WRITE_OPERATIONS = [
    "order_insert",
    "review_insert",
    "order_status_update",
    "inventory_update",
    "price_update",
    "review_delete",
    "cart_insert",
    "cart_cleanup_delete",
]

SCENARIO_WEIGHTS = {
    "catalog": {"catalog": 1},
    "default": {"catalog": 55, "details": 20, "order_history": 15, "reporting": 10},
    "details": {"details": 1},
    "order_history": {"order_history": 1},
    "reporting": {"reporting": 1},
    "catalog_heavy": {"catalog": 80, "details": 20},
    "order_history_heavy": {"order_history": 85, "details": 15},
    "sales_report_heavy": {"reporting": 85, "catalog": 15},
    "mixed_heavy": {"catalog": 45, "details": 15, "order_history": 25, "reporting": 15},
    "covering_index_experiment": {"covering_catalog": 75, "catalog": 15, "order_history": 10},
    "write_heavy": {"order_insert": 30, "review_insert": 15, "cart_insert": 15, "order_status_update": 15, "inventory_update": 15, "price_update": 5, "cart_cleanup_delete": 5},
    "mixed_read_write": {"covering_catalog": 30, "catalog": 15, "order_history": 15, "reporting": 10, "order_insert": 8, "review_insert": 5, "cart_insert": 5, "order_status_update": 5, "inventory_update": 5, "cart_cleanup_delete": 2},
    "order_write_heavy": {"order_insert": 70, "order_status_update": 30},
    "inventory_update_heavy": {"inventory_update": 85, "price_update": 15},
    "delete_cleanup_heavy": {"cart_cleanup_delete": 80, "cart_insert": 20},
}
SCENARIO_NAMES = sorted(SCENARIO_WEIGHTS.keys())


def _ensure_seeded_data():
    if not Product.objects.exists():
        raise ValueError("No products found. Run `python manage.py seed_data --size=small` first.")


def _choose_operation(rng, scenario):
    weights = SCENARIO_WEIGHTS[scenario]
    operations = list(weights.keys())
    return rng.choices(operations, weights=[weights[name] for name in operations], k=1)[0]


def _run_catalog_read(rng, categories, product_slugs, intensity=1):
    maybe_search = None
    if rng.random() > 0.5:
        chosen_slug = rng.choice(product_slugs)
        maybe_search = chosen_slug.split("-")[-1]
    created_after_days = None
    selected_sort = rng.choice(["popular", "price", "newest"])
    if selected_sort == "newest" and rng.random() > 0.25:
        created_after_days = rng.choice([7, 14, 30, 90])
    get_product_listing(
        category_slug=rng.choice(categories) if rng.random() > 0.4 else None,
        search=maybe_search,
        sort=selected_sort,
        page=rng.randint(1, max(3, 3 + intensity)),
        page_size=rng.choice([12, 20, 24, 50]),
        created_after_days=created_after_days,
    )


def _run_covering_catalog_read(rng, categories, intensity=1):
    for _ in range(max(1, intensity)):
        get_product_listing(
            category_slug=rng.choice(categories) if rng.random() > 0.25 else None,
            search=None,
            sort=rng.choice(["newest", "price"]),
            page=rng.randint(1, 8),
            page_size=rng.choice([20, 50, 100]),
            created_after_days=rng.choice([7, 14, 30, 90, 180]),
        )


def _run_order_insert(rng, user_ids, product_price_rows, max_items=4):
    selected_products = rng.sample(product_price_rows, k=min(rng.randint(1, max_items), len(product_price_rows)))
    with transaction.atomic():
        order = Order.objects.create(
            user_id=rng.choice(user_ids),
            status=rng.choice([Order.Status.PLACED, Order.Status.PAID, Order.Status.SHIPPED]),
            total_amount=Decimal("0.00"),
            created_at=timezone.now() - timedelta(minutes=rng.randint(0, 60 * 24)),
        )
        items = []
        total = Decimal("0.00")
        for product_id, price in selected_products:
            quantity = rng.randint(1, 3)
            line_total = price * quantity
            total += line_total
            items.append(
                OrderItem(
                    order=order,
                    product_id=product_id,
                    quantity=quantity,
                    unit_price=price,
                    line_total=line_total,
                )
            )
        OrderItem.objects.bulk_create(items)
        Order.objects.filter(id=order.id).update(total_amount=total)


def _run_review_insert(rng, user_ids, product_ids):
    Review.objects.create(
        user_id=rng.choice(user_ids),
        product_id=rng.choice(product_ids),
        rating=rng.choices([5, 4, 3, 2, 1], weights=[32, 30, 20, 12, 6], k=1)[0],
        content=f"Generated workload review {rng.randint(1, 1000000)}",
        created_at=timezone.now() - timedelta(minutes=rng.randint(0, 60 * 24 * 30)),
    )


def _run_order_status_update(rng, order_ids):
    if not order_ids:
        return
    Order.objects.filter(id=rng.choice(order_ids)).update(
        status=rng.choice([Order.Status.PAID, Order.Status.SHIPPED, Order.Status.DELIVERED, Order.Status.CANCELLED]),
        updated_at=timezone.now(),
    )


def _run_inventory_update(rng, product_ids):
    delta = rng.choice([-2, -1, 1, 2, 3])
    queryset = Product.objects.filter(id=rng.choice(product_ids))
    if delta < 0:
        queryset = queryset.filter(stock__gte=abs(delta))
    queryset.update(stock=F("stock") + delta)


def _run_price_update(rng, product_ids):
    product_id = rng.choice(product_ids)
    current = Product.objects.filter(id=product_id).values_list("price", flat=True).first()
    if current is None:
        return
    multiplier = Decimal(rng.choice(["0.97", "0.99", "1.01", "1.03"]))
    Product.objects.filter(id=product_id).update(price=max(Decimal("1.00"), current * multiplier))


def _run_review_delete(rng, max_delete_per_run=1):
    cutoff = timezone.now() - timedelta(days=365)
    candidate_ids = list(
        Review.objects.filter(created_at__lt=cutoff)
        .order_by("id")
        .values_list("id", flat=True)[: max(max_delete_per_run * 20, 20)]
    )
    if not candidate_ids:
        return
    selected_ids = rng.sample(candidate_ids, k=min(max_delete_per_run, len(candidate_ids)))
    Review.objects.filter(id__in=selected_ids).delete()


def _run_cart_insert(rng, user_ids, product_price_rows, max_items=3):
    created_at = timezone.now() - timedelta(days=rng.choice([0, 1, 2, 14, 45]))
    expires_at = created_at + timedelta(days=rng.choice([1, 3, 7]))
    selected_products = rng.sample(product_price_rows, k=min(rng.randint(1, max_items), len(product_price_rows)))
    with transaction.atomic():
        cart = DemoCart.objects.create(
            user_id=rng.choice(user_ids),
            token=f"cart-{int(time.time() * 1000000)}-{rng.randint(1, 1000000)}",
            status=rng.choice(["active", "abandoned", "expired"]),
            created_at=created_at,
            expires_at=expires_at,
        )
        DemoCartItem.objects.bulk_create(
            [
                DemoCartItem(
                    cart=cart,
                    product_id=product_id,
                    quantity=rng.randint(1, 4),
                    unit_price=price,
                )
                for product_id, price in selected_products
            ]
        )


def _run_cart_cleanup_delete(rng, max_delete_per_run=10):
    cutoff = timezone.now() - timedelta(days=7)
    with transaction.atomic():
        candidates = DemoCart.objects.filter(expires_at__lt=cutoff).order_by("expires_at", "id")
        if connection.vendor == "postgresql":
            candidates = candidates.select_for_update(skip_locked=True)
        candidate_ids = list(candidates.values_list("id", flat=True)[: max(max_delete_per_run * 5, 20)])
        if not candidate_ids:
            return
        selected_ids = rng.sample(candidate_ids, k=min(max_delete_per_run, len(candidate_ids)))
        DemoCartItem.objects.filter(cart_id__in=selected_ids).delete()
        DemoCart.objects.filter(id__in=selected_ids).delete()


def _run_operation(operation, rng, context, intensity=1):
    if operation == "catalog":
        _run_catalog_read(rng, context["categories"], context["product_slugs"], intensity=intensity)
    elif operation == "covering_catalog":
        _run_covering_catalog_read(rng, context["categories"], intensity=intensity)
    elif operation == "details":
        get_product_detail(rng.choice(context["product_slugs"]))
    elif operation == "order_history":
        get_order_history(rng.choice(context["user_ids"]), limit=rng.choice([5, 10, 25]))
    elif operation == "reporting":
        get_sales_report(days=rng.choice([7, 14, 30, 90, 180]))
    elif operation == "order_insert":
        _run_order_insert(rng, context["user_ids"], context["product_price_rows"])
    elif operation == "review_insert":
        _run_review_insert(rng, context["user_ids"], context["product_ids"])
    elif operation == "order_status_update":
        _run_order_status_update(rng, context["order_ids"])
    elif operation == "inventory_update":
        _run_inventory_update(rng, context["product_ids"])
    elif operation == "price_update":
        _run_price_update(rng, context["product_ids"])
    elif operation == "review_delete":
        _run_review_delete(rng, max_delete_per_run=1)
    elif operation == "cart_insert":
        _run_cart_insert(rng, context["user_ids"], context["product_price_rows"])
    elif operation == "cart_cleanup_delete":
        _run_cart_cleanup_delete(rng, max_delete_per_run=10)


def _run_operation_threadsafe(operation, operation_seed, context, intensity):
    rng = random.Random(operation_seed)
    _run_operation(operation, rng, context, intensity=intensity)
    return operation


def _close_worker_connection():
    connections.close_all()
    return None


def _run_operation_batch(operation_batch, context, intensity, concurrency, executor=None):
    if concurrency <= 1:
        completed = []
        for operation, operation_seed in operation_batch:
            completed.append(_run_operation_threadsafe(operation, operation_seed, context, intensity))
        return completed

    completed = []
    futures = [
        executor.submit(_run_operation_threadsafe, operation, operation_seed, context, intensity)
        for operation, operation_seed in operation_batch
    ]
    for future in as_completed(futures):
        completed.append(future.result())
    return completed


def run_simulation(
    scenario="default",
    duration=30,
    seed=42,
    iterations=None,
    progress_callback=None,
    intensity=1,
    warmup=0,
    profile="",
    concurrency=1,
):
    if scenario not in SCENARIO_NAMES:
        raise ValueError(f"Unknown scenario: {scenario}")

    _ensure_seeded_data()

    rng = random.Random(seed)
    categories = list(Category.objects.values_list("slug", flat=True))
    product_slugs = list(Product.objects.values_list("slug", flat=True))
    product_ids = list(Product.objects.values_list("id", flat=True))
    product_price_rows = list(Product.objects.order_by("-popularity_score").values_list("id", "price")[:5000])
    user_ids = list(get_user_model().objects.filter(username__startswith="demo_user_").values_list("id", flat=True))
    order_ids = list(Order.objects.order_by("-created_at").values_list("id", flat=True)[:10000])
    if not user_ids:
        raise ValueError("No demo users found. Run seed_data before simulate_load.")
    if not product_price_rows:
        raise ValueError("No product price rows found. Run seed_data before simulate_load.")

    context = {
        "categories": categories,
        "product_slugs": product_slugs,
        "product_ids": product_ids,
        "product_price_rows": product_price_rows,
        "user_ids": user_ids,
        "order_ids": order_ids,
    }
    operation_counts = Counter()
    concurrency = max(int(concurrency), 1)
    if concurrency > 1 and progress_callback:
        progress_callback(f"Running workload with {concurrency} concurrent worker threads.")
    if profile and progress_callback:
        progress_callback(f"Workload profile hint: {profile}")

    for _ in range(max(warmup, 0)):
        operation = _choose_operation(rng, scenario)
        if operation in WRITE_OPERATIONS:
            continue
        _run_operation(operation, rng, context, intensity=intensity)

    start = time.monotonic()
    completed = 0
    executor = ThreadPoolExecutor(max_workers=concurrency) if concurrency > 1 else None

    try:
        while True:
            if iterations is not None and completed >= iterations:
                break
            if iterations is None and time.monotonic() - start >= duration:
                break

            batch_size = min(concurrency, (iterations - completed) if iterations is not None else concurrency)
            operation_batch = [
                (_choose_operation(rng, scenario), rng.randint(1, 2_000_000_000))
                for _ in range(max(batch_size, 1))
            ]
            for operation in _run_operation_batch(operation_batch, context, intensity, concurrency, executor=executor):
                operation_counts[operation] += 1
                completed += 1

            if progress_callback and completed % 25 == 0:
                progress_callback(f"Completed {completed} operations...")
    finally:
        if executor:
            close_futures = [executor.submit(_close_worker_connection) for _ in range(concurrency)]
            for future in as_completed(close_futures):
                future.result()
            executor.shutdown(wait=True)
        connections.close_all()

    return {
        "scenario": scenario,
        "seed": seed,
        "iterations": iterations,
        "duration": duration,
        "profile": profile,
        "intensity": intensity,
        "warmup": warmup,
        "concurrency": concurrency,
        "mutates_data": any(operation_counts[name] for name in WRITE_OPERATIONS),
        "operations": completed,
        "breakdown": {key: value for key, value in operation_counts.items() if value},
        "duration_seconds": round(time.monotonic() - start, 2),
    }
