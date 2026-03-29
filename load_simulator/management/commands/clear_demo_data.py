from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from shop.models import Category, Order, Product, Review


class Command(BaseCommand):
    help = "Remove seeded demo data from the local project."

    @transaction.atomic
    def handle(self, *args, **options):
        review_count = Review.objects.filter(user__username__startswith="demo_user_").count()
        order_count = Order.objects.filter(user__username__startswith="demo_user_").count()
        product_count = Product.objects.filter(slug__startswith="product-").count()
        category_count = Category.objects.filter(slug__startswith="category-").count()
        user_count = get_user_model().objects.filter(username__startswith="demo_user_").count()

        Review.objects.filter(user__username__startswith="demo_user_").delete()
        Order.objects.filter(user__username__startswith="demo_user_").delete()
        Product.objects.filter(slug__startswith="product-").delete()
        Category.objects.filter(slug__startswith="category-").delete()
        get_user_model().objects.filter(username__startswith="demo_user_").delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted demo data: users={user_count}, categories={category_count}, products={product_count}, "
                f"orders={order_count}, reviews={review_count}"
            )
        )
