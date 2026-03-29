import random
import time

from django.contrib.auth import get_user_model

from shop.models import Category, Product
from shop.services import get_order_history, get_product_detail, get_product_listing, get_sales_report

SCENARIO_NAMES = ["catalog", "default", "details", "order_history", "reporting"]


def _ensure_seeded_data():
    if not Product.objects.exists():
        raise ValueError("No products found. Run `python manage.py seed_data --size=small` first.")


def run_simulation(scenario="default", duration=30, seed=42, iterations=None, progress_callback=None):
    if scenario not in SCENARIO_NAMES:
        raise ValueError(f"Unknown scenario: {scenario}")

    _ensure_seeded_data()

    rng = random.Random(seed)
    categories = list(Category.objects.values_list("slug", flat=True))
    product_slugs = list(Product.objects.values_list("slug", flat=True))
    user_ids = list(get_user_model().objects.filter(username__startswith="demo_user_").values_list("id", flat=True))
    if not user_ids:
        raise ValueError("No demo users found. Run seed_data before simulate_load.")

    operation_counts = {
        "catalog": 0,
        "details": 0,
        "order_history": 0,
        "reporting": 0,
    }

    start = time.monotonic()
    completed = 0

    while True:
        if iterations is not None and completed >= iterations:
            break
        if iterations is None and time.monotonic() - start >= duration:
            break

        operation = scenario
        if scenario == "default":
            operation = rng.choices(
                ["catalog", "details", "order_history", "reporting"],
                weights=[55, 20, 15, 10],
                k=1,
            )[0]

        if operation == "catalog":
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
                page=rng.randint(1, 3),
                page_size=rng.choice([12, 20, 24]),
                created_after_days=created_after_days,
            )
        elif operation == "details":
            get_product_detail(rng.choice(product_slugs))
        elif operation == "order_history":
            get_order_history(rng.choice(user_ids), limit=rng.choice([5, 10]))
        elif operation == "reporting":
            get_sales_report(days=rng.choice([7, 14, 30, 90]))

        operation_counts[operation] += 1
        completed += 1

        if progress_callback and completed % 25 == 0:
            progress_callback(f"Completed {completed} operations...")

    return {
        "scenario": scenario,
        "operations": completed,
        "breakdown": operation_counts,
        "duration_seconds": round(time.monotonic() - start, 2),
    }
