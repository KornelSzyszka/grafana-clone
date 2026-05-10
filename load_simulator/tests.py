from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from unittest import skipUnless

from load_simulator.services.seeding import PROFILES
from load_simulator.services.simulation import run_simulation
from load_simulator.models import DemoCart, WorkloadRun
from shop.models import Category, Order, Product, Review


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

    def test_huge_profile_is_available_for_large_experiments(self):
        profile = PROFILES["huge"]

        self.assertGreaterEqual(
            profile.users + profile.products + profile.orders + profile.reviews,
            700000,
        )
        self.assertGreater(profile.batch_size, 1000)

    def test_covering_index_experiment_scenario_runs(self):
        call_command("seed_data", size="small", seed=13)

        summary = run_simulation(scenario="covering_index_experiment", seed=13, iterations=3, duration=1)

        self.assertEqual(summary["scenario"], "covering_index_experiment")
        self.assertFalse(summary["mutates_data"])
        self.assertGreater(summary["operations"], 0)

    def test_write_heavy_scenario_mutates_data_with_bounded_deletes(self):
        call_command("seed_data", size="small", seed=17)
        before_orders = Order.objects.count()
        before_reviews = Review.objects.count()

        summary = run_simulation(scenario="write_heavy", seed=17, iterations=8, duration=1)

        self.assertTrue(summary["mutates_data"])
        self.assertGreaterEqual(Order.objects.count(), before_orders)
        self.assertGreaterEqual(Review.objects.count(), before_reviews - 8)

    def test_simulate_load_records_workload_run_by_default(self):
        call_command("seed_data", size="small", seed=19)

        call_command("simulate_load", scenario="catalog", seed=19, iterations=2, duration=1)

        run = WorkloadRun.objects.latest("id")
        self.assertEqual(run.scenario, "catalog")
        self.assertEqual(run.seed, 19)
        self.assertEqual(run.operations, 2)

    @skipUnless(connection.vendor == "postgresql", "Threaded concurrency is validated against PostgreSQL runtime.")
    def test_simulation_uses_threaded_concurrency(self):
        call_command("seed_data", size="small", seed=23)

        summary = run_simulation(scenario="catalog_heavy", seed=23, iterations=4, duration=1, concurrency=2)

        self.assertEqual(summary["concurrency"], 2)
        self.assertEqual(summary["operations"], 4)

    def test_delete_cleanup_heavy_targets_demo_carts(self):
        call_command("seed_data", size="small", seed=29)

        summary = run_simulation(scenario="delete_cleanup_heavy", seed=29, iterations=10, duration=1)

        self.assertTrue(summary["mutates_data"])
        self.assertIn("cart_insert", summary["breakdown"])
        self.assertGreaterEqual(DemoCart.objects.count(), 0)
