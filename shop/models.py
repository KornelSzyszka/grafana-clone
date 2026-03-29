from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    is_active = models.BooleanField(default=True)
    popularity_score = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-popularity_score", "name"]
        indexes = [
            models.Index(fields=["category"], name="shop_product_category_idx"),
            models.Index(fields=["is_active"], name="shop_product_active_idx"),
            # This index is intentionally weakly used in the workload so it can be flagged later.
            models.Index(fields=["stock"], name="shop_product_stock_idx"),
        ]

    def __str__(self):
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PLACED = "placed", "Placed"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"], name="shop_order_user_idx"),
            models.Index(fields=["status"], name="shop_order_status_idx"),
        ]

    def __str__(self):
        return f"Order #{self.pk} ({self.status})"

    def recalculate_total(self):
        total = sum((item.line_total for item in self.items.all()), Decimal("0.00"))
        self.total_amount = total
        self.save(update_fields=["total_amount", "updated_at"])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=["order"], name="shop_order_item_order_idx"),
            models.Index(fields=["product"], name="shop_order_item_product_idx"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    content = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product"], name="shop_review_product_idx"),
            models.Index(fields=["user"], name="shop_review_user_idx"),
        ]

    def __str__(self):
        return f"Review {self.product.name} ({self.rating}/5)"
