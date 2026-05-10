from django.db import models


class StatsSnapshot(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        DEGRADED = "degraded", "Degraded"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    created_at = models.DateTimeField(auto_now_add=True)
    label = models.CharField(max_length=120, blank=True)
    environment = models.CharField(max_length=120, blank=True)
    database_vendor = models.CharField(max_length=40)
    database_name = models.CharField(max_length=120, blank=True)
    collector_version = models.CharField(max_length=40, default="foundation-v1")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    notes = models.TextField(blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        base = self.label or f"snapshot-{self.pk}"
        return f"{base} [{self.status}]"


class ExperimentIndexGroup(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ExperimentIndexDefinition(models.Model):
    name = models.CharField(max_length=120, unique=True)
    table_name = models.CharField(max_length=120)
    using = models.CharField(max_length=40, blank=True)
    columns = models.TextField()
    include = models.TextField(blank=True)
    extensions_json = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    match_all_json = models.JSONField(default=list, blank=True)
    groups = models.ManyToManyField(ExperimentIndexGroup, related_name="index_definitions", blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class QueryStatSnapshot(models.Model):
    class OperationType(models.TextChoices):
        SELECT = "SELECT", "SELECT"
        INSERT = "INSERT", "INSERT"
        UPDATE = "UPDATE", "UPDATE"
        DELETE = "DELETE", "DELETE"
        OTHER = "OTHER", "Other"
        UNKNOWN = "UNKNOWN", "Unknown"

    snapshot = models.ForeignKey(StatsSnapshot, on_delete=models.CASCADE, related_name="query_stats")
    queryid = models.CharField(max_length=128, blank=True)
    query_text_normalized = models.TextField()
    operation_type = models.CharField(max_length=20, choices=OperationType.choices, default=OperationType.UNKNOWN)
    calls = models.BigIntegerField(default=0)
    total_exec_time = models.FloatField(default=0)
    mean_exec_time = models.FloatField(default=0)
    min_exec_time = models.FloatField(default=0)
    max_exec_time = models.FloatField(default=0)
    rows = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["-total_exec_time", "-calls"]


class TableStatSnapshot(models.Model):
    snapshot = models.ForeignKey(StatsSnapshot, on_delete=models.CASCADE, related_name="table_stats")
    schema_name = models.CharField(max_length=120)
    table_name = models.CharField(max_length=120)
    seq_scan = models.BigIntegerField(default=0)
    idx_scan = models.BigIntegerField(default=0)
    seq_tup_read = models.BigIntegerField(default=0)
    idx_tup_fetch = models.BigIntegerField(default=0)
    n_live_tup = models.BigIntegerField(default=0)
    n_dead_tup = models.BigIntegerField(default=0)
    table_size_bytes = models.BigIntegerField(default=0)
    vacuum_count = models.BigIntegerField(default=0)
    autovacuum_count = models.BigIntegerField(default=0)
    analyze_count = models.BigIntegerField(default=0)
    autoanalyze_count = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["-seq_scan", "-n_live_tup"]


class IndexStatSnapshot(models.Model):
    snapshot = models.ForeignKey(StatsSnapshot, on_delete=models.CASCADE, related_name="index_stats")
    schema_name = models.CharField(max_length=120)
    table_name = models.CharField(max_length=120)
    index_name = models.CharField(max_length=120)
    idx_scan = models.BigIntegerField(default=0)
    idx_tup_read = models.BigIntegerField(default=0)
    idx_tup_fetch = models.BigIntegerField(default=0)
    index_size_bytes = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["idx_scan", "-index_size_bytes"]


class ActivitySnapshot(models.Model):
    snapshot = models.ForeignKey(StatsSnapshot, on_delete=models.CASCADE, related_name="activities")
    pid = models.IntegerField()
    state = models.CharField(max_length=64, blank=True)
    wait_event_type = models.CharField(max_length=64, blank=True)
    wait_event = models.CharField(max_length=128, blank=True)
    query = models.TextField(blank=True)
    duration_ms = models.FloatField(default=0)

    class Meta:
        ordering = ["-duration_ms", "pid"]


class QueryPlanSnapshot(models.Model):
    snapshot = models.ForeignKey(StatsSnapshot, on_delete=models.CASCADE, related_name="query_plans")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    sql = models.TextField()
    plan_json = models.JSONField(default=dict, blank=True)
    total_cost = models.FloatField(default=0)
    plan_rows = models.BigIntegerField(default=0)
    execution_time_ms = models.FloatField(default=0)
    planning_time_ms = models.FloatField(default=0)
    uses_index_only_scan = models.BooleanField(default=False)
    uses_seq_scan = models.BooleanField(default=False)
    uses_index_scan = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]


class AnalysisFinding(models.Model):
    snapshot = models.ForeignKey(StatsSnapshot, on_delete=models.CASCADE, related_name="findings")
    type = models.CharField(max_length=64)
    severity = models.CharField(max_length=20)
    title = models.CharField(max_length=180)
    description = models.TextField()
    object_type = models.CharField(max_length=64, blank=True)
    object_name = models.CharField(max_length=180, blank=True)
    evidence_json = models.JSONField(default=dict, blank=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["severity", "-id"]
