import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from faker import Faker

from load_simulator.models import DemoCart
from shop.models import Category, Order, OrderItem, Product, Review


@dataclass(frozen=True)
class SeedProfile:
    users: int
    categories: int
    products: int
    orders: int
    max_items_per_order: int
    reviews: int
    batch_size: int = 1000


PROFILES = {
    "small": SeedProfile(users=120, categories=10, products=90, orders=320, max_items_per_order=4, reviews=180),
    "medium": SeedProfile(users=800, categories=24, products=700, orders=3500, max_items_per_order=5, reviews=1800),
    "large": SeedProfile(users=3000, categories=40, products=2200, orders=16000, max_items_per_order=6, reviews=7500),
    "huge": SeedProfile(
        users=100000,
        categories=120,
        products=180000,
        orders=260000,
        max_items_per_order=4,
        reviews=220000,
        batch_size=5000,
    ),
}
PROFILE_NAMES = sorted(PROFILES.keys())


def _recent_datetime(rng, max_days=365):
    days_ago = int((rng.random() ** 2) * max_days)
    minutes_ago = rng.randint(0, 24 * 60 - 1)
    return timezone.now() - timedelta(days=days_ago, minutes=minutes_ago)


def _build_product_weights(products):
    hot_zone = max(1, int(len(products) * 0.2))
    weights = []
    for index, product in enumerate(products):
        base_weight = 18 if index < hot_zone else 3
        weights.append(base_weight + max(product.popularity_score // 20, 1))
    return weights


def _chunks(total, size):
    for start in range(0, total, size):
        yield start, min(start + size, total)


def _log(progress_callback, message):
    if progress_callback:
        progress_callback(message)


def _clear_existing_demo_data(progress_callback=None):
    _log(progress_callback, "Clearing existing demo data...")
    DemoCart.objects.filter(user__username__startswith="demo_user_").delete()
    Review.objects.filter(user__username__startswith="demo_user_").delete()
    Order.objects.filter(user__username__startswith="demo_user_").delete()
    Product.objects.filter(slug__startswith="product-").delete()
    Category.objects.filter(slug__startswith="category-").delete()
    get_user_model().objects.filter(username__startswith="demo_user_").delete()


def _weighted_choice_id(rng, ids):
    if not ids:
        raise ValueError("Cannot choose from an empty id list.")
    hot_zone = max(1, len(ids) // 5)
    if len(ids) > hot_zone and rng.random() < 0.7:
        return ids[rng.randrange(0, hot_zone)]
    return ids[rng.randrange(0, len(ids))]


def _build_product_reference(products):
    hot_zone = max(1, int(len(products) * 0.2))
    weighted_ids = []
    price_by_id = {}
    for index, product in enumerate(products):
        repeat = 18 if index < hot_zone else 3
        repeat += max(product.popularity_score // 20, 1)
        weighted_ids.extend([product.id] * repeat)
        price_by_id[product.id] = product.price
    return weighted_ids, price_by_id


def _seed_categories(profile, faker):
    categories = [
        Category(
            name=f"{faker.word().capitalize()} {index}",
            slug=f"category-{index}",
        )
        for index in range(profile.categories)
    ]
    Category.objects.bulk_create(categories, batch_size=200)
    return list(Category.objects.filter(slug__startswith="category-").order_by("id"))


def _seed_users(profile, rng, faker, progress_callback):
    User = get_user_model()
    for start, end in _chunks(profile.users, profile.batch_size):
        users = [
            User(
                username=f"demo_user_{index}",
                email=f"demo_user_{index}@example.com",
                first_name=faker.first_name(),
                last_name=faker.last_name(),
                is_active=rng.random() > 0.08,
            )
            for index in range(start, end)
        ]
        User.objects.bulk_create(users, batch_size=profile.batch_size)
        _log(progress_callback, f"Seeded users {end}/{profile.users}")
    return list(User.objects.filter(username__startswith="demo_user_").order_by("id").values_list("id", flat=True))


def _seed_products(profile, rng, faker, categories, progress_callback):
    category_ids = [category.id for category in categories]
    category_weights = [max(profile.categories - idx, 1) for idx, _ in enumerate(categories)]
    for start, end in _chunks(profile.products, profile.batch_size):
        products = []
        for index in range(start, end):
            category_id = rng.choices(category_ids, weights=category_weights, k=1)[0]
            products.append(
                Product(
                    name=f"{faker.word().capitalize()} {faker.word().capitalize()} {index}",
                    slug=f"product-{index}",
                    description=faker.paragraph(nb_sentences=rng.randint(2, 5)),
                    price=Decimal(rng.randint(1999, 24999)) / Decimal("100"),
                    stock=rng.randint(0, 250),
                    category_id=category_id,
                    is_active=rng.random() > 0.04,
                    popularity_score=max(1, int((1 - rng.random() ** 1.7) * 100)),
                    created_at=_recent_datetime(rng, max_days=720),
                )
            )
        Product.objects.bulk_create(products, batch_size=profile.batch_size)
        _log(progress_callback, f"Seeded products {end}/{profile.products}")

    return list(
        Product.objects.filter(slug__startswith="product-")
        .only("id", "price", "popularity_score")
        .order_by("-popularity_score", "id")
    )


def _seed_orders_and_items(profile, rng, user_ids, product_ids, price_by_id, progress_callback):
    statuses = [
        (Order.Status.DELIVERED, 52),
        (Order.Status.PAID, 18),
        (Order.Status.SHIPPED, 12),
        (Order.Status.PLACED, 11),
        (Order.Status.CANCELLED, 5),
        (Order.Status.DRAFT, 2),
    ]
    status_values = [status for status, _ in statuses]
    status_weights = [weight for _, weight in statuses]
    total_items = 0

    for start, end in _chunks(profile.orders, profile.batch_size):
        orders = []
        for _ in range(start, end):
            orders.append(
                Order(
                    user_id=_weighted_choice_id(rng, user_ids),
                    status=rng.choices(status_values, weights=status_weights, k=1)[0],
                    total_amount=Decimal("0.00"),
                    created_at=_recent_datetime(rng),
                )
            )
        Order.objects.bulk_create(orders, batch_size=profile.batch_size)

        order_items = []
        orders_to_update = []
        for order in orders:
            item_count = rng.randint(1, profile.max_items_per_order)
            order_total = Decimal("0.00")
            for product_id in rng.choices(product_ids, k=item_count):
                unit_price = price_by_id[product_id]
                quantity = rng.randint(1, 3)
                line_total = unit_price * quantity
                order_total += line_total
                order_items.append(
                    OrderItem(
                        order_id=order.id,
                        product_id=product_id,
                        quantity=quantity,
                        unit_price=unit_price,
                        line_total=line_total,
                    )
                )
            order.total_amount = order_total
            orders_to_update.append(order)

        OrderItem.objects.bulk_create(order_items, batch_size=profile.batch_size)
        Order.objects.bulk_update(orders_to_update, ["total_amount"], batch_size=profile.batch_size)
        total_items += len(order_items)
        _log(progress_callback, f"Seeded orders {end}/{profile.orders} with {total_items} order items")

    return total_items


def _seed_reviews(profile, rng, faker, user_ids, product_ids, progress_callback):
    for start, end in _chunks(profile.reviews, profile.batch_size):
        reviews = []
        for _ in range(start, end):
            reviews.append(
                Review(
                    user_id=user_ids[rng.randrange(0, len(user_ids))],
                    product_id=rng.choice(product_ids),
                    rating=rng.choices([3, 4, 5, 2, 1], weights=[20, 32, 30, 12, 6], k=1)[0],
                    content=faker.paragraph(nb_sentences=rng.randint(1, 4)),
                    created_at=_recent_datetime(rng, max_days=540),
                )
            )
        Review.objects.bulk_create(reviews, batch_size=profile.batch_size)
        _log(progress_callback, f"Seeded reviews {end}/{profile.reviews}")


def seed_demo_data(size="small", seed=42, clear_existing=True, progress_callback=None):
    if size not in PROFILES:
        raise ValueError(f"Unknown profile: {size}")

    if clear_existing:
        _clear_existing_demo_data(progress_callback=progress_callback)

    profile = PROFILES[size]
    rng = random.Random(seed)
    faker = Faker("pl_PL")
    faker.seed_instance(seed)

    categories = _seed_categories(profile, faker)
    user_ids = _seed_users(profile, rng, faker, progress_callback)
    products = _seed_products(profile, rng, faker, categories, progress_callback)
    product_ids, price_by_id = _build_product_reference(products)
    order_items_count = _seed_orders_and_items(profile, rng, user_ids, product_ids, price_by_id, progress_callback)
    _seed_reviews(profile, rng, faker, user_ids, product_ids, progress_callback)

    return {
        "profile": size,
        "users": len(user_ids),
        "categories": len(categories),
        "products": len(products),
        "orders": profile.orders,
        "order_items": order_items_count,
        "reviews": profile.reviews,
    }
