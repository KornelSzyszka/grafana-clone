from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from shop.models import Category, Order, OrderItem, Product, Review


class ShopApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="demo_user",
            email="demo@example.com",
            password="testpass123",
        )
        self.category = Category.objects.create(name="Monitors", slug="monitors")
        self.product = Product.objects.create(
            name="24-inch Monitor",
            slug="24-inch-monitor",
            description="A monitor for testing.",
            price=Decimal("799.99"),
            stock=10,
            category=self.category,
            popularity_score=50,
            created_at=timezone.now(),
        )
        self.order = Order.objects.create(
            user=self.user,
            status=Order.Status.DELIVERED,
            total_amount=Decimal("799.99"),
            created_at=timezone.now(),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=Decimal("799.99"),
            line_total=Decimal("799.99"),
        )
        Review.objects.create(
            user=self.user,
            product=self.product,
            rating=5,
            content="Works great",
            created_at=timezone.now(),
        )

    def test_product_list_endpoint(self):
        response = self.client.get(reverse("shop:product-list"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["slug"], self.product.slug)

    def test_product_detail_endpoint(self):
        response = self.client.get(reverse("shop:product-detail", kwargs={"slug": self.product.slug}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["product"]["slug"], self.product.slug)
        self.assertEqual(payload["reviews"][0]["rating"], 5)

    def test_order_history_endpoint(self):
        response = self.client.get(reverse("shop:order-history", kwargs={"user_id": self.user.id}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["username"], self.user.username)
        self.assertEqual(payload["orders"][0]["items"][0]["product_slug"], self.product.slug)
