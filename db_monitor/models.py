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


class QueryStatSnapshot(models.Model):
    snapshot = models.ForeignKey(StatsSnapshot, on_delete=models.CASCADE, related_name="query_stats")
    queryid = models.CharField(max_length=128, blank=True)
    query_text_normalized = models.TextField()
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
    n_live_tup = models.BigIntegerField(default=0)
    n_dead_tup = models.BigIntegerField(default=0)
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
