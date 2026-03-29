from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from shop.models import Category, Order, Product


class LoadSimulatorCommandTests(TestCase):
    def test_seed_data_populates_foundation_models(self):
        call_command("seed_data", size="small", seed=7)

        self.assertGreater(Category.objects.count(), 0)
        self.assertGreater(Product.objects.count(), 0)
        self.assertGreater(Order.objects.count(), 0)
        self.assertGreater(get_user_model().objects.filter(username__startswith="demo_user_").count(), 0)

    def test_simulate_load_runs_with_seeded_data(self):
        call_command("seed_data", size="small", seed=11)
        call_command("simulate_load", scenario="default", seed=11, iterations=5, duration=1)
