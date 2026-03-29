import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from faker import Faker

from shop.models import Category, Order, OrderItem, Product, Review


@dataclass(frozen=True)
class SeedProfile:
    users: int
    categories: int
    products: int
    orders: int
    max_items_per_order: int
    reviews: int


PROFILES = {
    "small": SeedProfile(users=120, categories=10, products=90, orders=320, max_items_per_order=4, reviews=180),
    "medium": SeedProfile(users=800, categories=24, products=700, orders=3500, max_items_per_order=5, reviews=1800),
    "large": SeedProfile(users=3000, categories=40, products=2200, orders=16000, max_items_per_order=6, reviews=7500),
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


@transaction.atomic
def seed_demo_data(size="small", seed=42, clear_existing=True):
    if size not in PROFILES:
        raise ValueError(f"Unknown profile: {size}")

    if clear_existing:
        Review.objects.filter(user__username__startswith="demo_user_").delete()
        Order.objects.filter(user__username__startswith="demo_user_").delete()
        Product.objects.filter(slug__startswith="product-").delete()
        Category.objects.filter(slug__startswith="category-").delete()
        get_user_model().objects.filter(username__startswith="demo_user_").delete()

    profile = PROFILES[size]
    rng = random.Random(seed)
    faker = Faker("pl_PL")
    faker.seed_instance(seed)

    User = get_user_model()

    categories = []
    for index in range(profile.categories):
        categories.append(
            Category(
                name=f"{faker.word().capitalize()} {index}",
                slug=f"category-{index}",
            )
        )
    Category.objects.bulk_create(categories, batch_size=200)
    categories = list(Category.objects.order_by("id"))

    users = []
    for index in range(profile.users):
        users.append(
            User(
                username=f"demo_user_{index}",
                email=f"demo_user_{index}@example.com",
                first_name=faker.first_name(),
                last_name=faker.last_name(),
                is_active=rng.random() > 0.08,
            )
        )
    User.objects.bulk_create(users, batch_size=500)
    users = list(User.objects.filter(username__startswith="demo_user_").order_by("id"))

    category_weights = [max(profile.categories - idx, 1) for idx, _ in enumerate(categories)]
    products = []
    for index in range(profile.products):
        category = rng.choices(categories, weights=category_weights, k=1)[0]
        products.append(
            Product(
                name=f"{faker.word().capitalize()} {faker.word().capitalize()} {index}",
                slug=f"product-{index}",
                description=faker.paragraph(nb_sentences=rng.randint(2, 5)),
                price=Decimal(rng.randint(1999, 24999)) / Decimal("100"),
                stock=rng.randint(0, 250),
                category=category,
                is_active=rng.random() > 0.04,
                popularity_score=max(1, int((1 - rng.random() ** 1.7) * 100)),
                created_at=_recent_datetime(rng, max_days=720),
            )
        )
    Product.objects.bulk_create(products, batch_size=500)
    products = list(Product.objects.select_related("category").order_by("-popularity_score", "id"))
    product_weights = _build_product_weights(products)

    statuses = [
        (Order.Status.DELIVERED, 52),
        (Order.Status.PAID, 18),
        (Order.Status.SHIPPED, 12),
        (Order.Status.PLACED, 11),
        (Order.Status.CANCELLED, 5),
        (Order.Status.DRAFT, 2),
    ]
    user_weights = [8 if idx < max(1, len(users) // 5) else 2 for idx, _ in enumerate(users)]

    orders = []
    for _ in range(profile.orders):
        user = rng.choices(users, weights=user_weights, k=1)[0]
        status = rng.choices([status for status, _ in statuses], weights=[weight for _, weight in statuses], k=1)[0]
        orders.append(
            Order(
                user=user,
                status=status,
                total_amount=Decimal("0.00"),
                created_at=_recent_datetime(rng),
            )
        )
    Order.objects.bulk_create(orders, batch_size=500)
    orders = list(Order.objects.select_related("user").order_by("id"))

    order_items = []
    orders_to_update = []
    for order in orders:
        item_count = rng.randint(1, profile.max_items_per_order)
        selected_products = rng.choices(products, weights=product_weights, k=item_count)
        order_total = Decimal("0.00")
        for product in selected_products:
            quantity = rng.randint(1, 3)
            line_total = product.price * quantity
            order_total += line_total
            order_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=product.price,
                    line_total=line_total,
                )
            )
        order.total_amount = order_total
        orders_to_update.append(order)
    OrderItem.objects.bulk_create(order_items, batch_size=1000)
    Order.objects.bulk_update(orders_to_update, ["total_amount"], batch_size=500)

    reviews = []
    for _ in range(profile.reviews):
        product = rng.choices(products, weights=product_weights, k=1)[0]
        user = users[rng.randrange(0, len(users))]
        reviews.append(
            Review(
                user=user,
                product=product,
                rating=rng.choices([3, 4, 5, 2, 1], weights=[20, 32, 30, 12, 6], k=1)[0],
                content=faker.paragraph(nb_sentences=rng.randint(1, 4)),
                created_at=_recent_datetime(rng, max_days=540),
            )
        )
    Review.objects.bulk_create(reviews, batch_size=1000)

    return {
        "profile": size,
        "users": len(users),
        "categories": len(categories),
        "products": len(products),
        "orders": len(orders),
        "order_items": len(order_items),
        "reviews": len(reviews),
    }
