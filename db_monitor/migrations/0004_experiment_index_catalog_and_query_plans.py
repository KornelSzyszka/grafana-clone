from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("db_monitor", "0003_table_and_index_extra_metrics"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExperimentIndexGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("description", models.TextField(blank=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="QueryPlanSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("sql", models.TextField()),
                ("plan_json", models.JSONField(blank=True, default=dict)),
                ("total_cost", models.FloatField(default=0)),
                ("plan_rows", models.BigIntegerField(default=0)),
                ("execution_time_ms", models.FloatField(default=0)),
                ("planning_time_ms", models.FloatField(default=0)),
                ("uses_index_only_scan", models.BooleanField(default=False)),
                ("uses_seq_scan", models.BooleanField(default=False)),
                ("uses_index_scan", models.BooleanField(default=False)),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="query_plans",
                        to="db_monitor.statssnapshot",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="ExperimentIndexDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("table_name", models.CharField(max_length=120)),
                ("using", models.CharField(blank=True, max_length=40)),
                ("columns", models.TextField()),
                ("include", models.TextField(blank=True)),
                ("extensions_json", models.JSONField(blank=True, default=list)),
                ("description", models.TextField(blank=True)),
                ("match_all_json", models.JSONField(blank=True, default=list)),
                ("is_default", models.BooleanField(default=False)),
                ("groups", models.ManyToManyField(blank=True, related_name="index_definitions", to="db_monitor.experimentindexgroup")),
            ],
            options={"ordering": ["name"]},
        ),
    ]
