from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("db_monitor", "0004_experiment_index_catalog_and_query_plans"),
        ("shop", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkloadRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("scenario", models.CharField(max_length=80)),
                ("profile", models.CharField(blank=True, max_length=80)),
                ("seed", models.IntegerField(default=42)),
                ("iterations", models.IntegerField(blank=True, null=True)),
                ("duration", models.IntegerField(default=30)),
                ("concurrency", models.IntegerField(default=1)),
                ("intensity", models.IntegerField(default=1)),
                ("warmup", models.IntegerField(default=0)),
                ("mutates_data", models.BooleanField(default=False)),
                ("operations", models.IntegerField(default=0)),
                ("duration_seconds", models.FloatField(default=0)),
                ("breakdown_json", models.JSONField(blank=True, default=dict)),
                ("command_options_json", models.JSONField(blank=True, default=dict)),
                ("git_commit", models.CharField(blank=True, max_length=64)),
                (
                    "snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workload_runs",
                        to="db_monitor.statssnapshot",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="DemoCart",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=80, unique=True)),
                ("status", models.CharField(default="active", max_length=20)),
                ("created_at", models.DateTimeField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="demo_carts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["expires_at", "id"]},
        ),
        migrations.CreateModel(
            name="DemoCartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "cart",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="load_simulator.democart",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="demo_cart_items",
                        to="shop.product",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="democart",
            index=models.Index(fields=["status", "expires_at"], name="load_cart_status_exp_idx"),
        ),
        migrations.AddIndex(
            model_name="democart",
            index=models.Index(fields=["user", "created_at"], name="load_cart_user_created_idx"),
        ),
        migrations.AddIndex(
            model_name="democartitem",
            index=models.Index(fields=["cart"], name="load_cart_item_cart_idx"),
        ),
        migrations.AddIndex(
            model_name="democartitem",
            index=models.Index(fields=["product"], name="load_cart_item_product_idx"),
        ),
    ]
