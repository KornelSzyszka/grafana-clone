from django.conf import settings
from django.db import models

from db_monitor.models import StatsSnapshot
from shop.models import Product


class WorkloadRun(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    scenario = models.CharField(max_length=80)
    profile = models.CharField(max_length=80, blank=True)
    seed = models.IntegerField(default=42)
    iterations = models.IntegerField(null=True, blank=True)
    duration = models.IntegerField(default=30)
    concurrency = models.IntegerField(default=1)
    intensity = models.IntegerField(default=1)
    warmup = models.IntegerField(default=0)
    mutates_data = models.BooleanField(default=False)
    operations = models.IntegerField(default=0)
    duration_seconds = models.FloatField(default=0)
    breakdown_json = models.JSONField(default=dict, blank=True)
    command_options_json = models.JSONField(default=dict, blank=True)
    git_commit = models.CharField(max_length=64, blank=True)
    snapshot = models.ForeignKey(
        StatsSnapshot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workload_runs",
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.scenario} #{self.pk}"


class DemoCart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demo_carts")
    token = models.CharField(max_length=80, unique=True)
    status = models.CharField(max_length=20, default="active")
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"], name="load_cart_status_exp_idx"),
            models.Index(fields=["user", "created_at"], name="load_cart_user_created_idx"),
        ]
        ordering = ["expires_at", "id"]

    def __str__(self):
        return self.token


class DemoCartItem(models.Model):
    cart = models.ForeignKey(DemoCart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="demo_cart_items")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=["cart"], name="load_cart_item_cart_idx"),
            models.Index(fields=["product"], name="load_cart_item_product_idx"),
        ]
