from django.contrib import admin

from .models import ActivitySnapshot, AnalysisFinding, IndexStatSnapshot, QueryStatSnapshot, StatsSnapshot, TableStatSnapshot


class QueryStatInline(admin.TabularInline):
    model = QueryStatSnapshot
    extra = 0
    fields = ("queryid", "calls", "mean_exec_time", "total_exec_time")
    readonly_fields = fields
    show_change_link = True


class TableStatInline(admin.TabularInline):
    model = TableStatSnapshot
    extra = 0
    fields = ("schema_name", "table_name", "seq_scan", "idx_scan", "n_live_tup", "n_dead_tup")
    readonly_fields = fields
    show_change_link = True


@admin.register(StatsSnapshot)
class StatsSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "label", "environment", "database_vendor", "status")
    list_filter = ("status", "database_vendor", "environment")
    search_fields = ("label", "environment", "notes")
    inlines = [QueryStatInline, TableStatInline]


@admin.register(QueryStatSnapshot)
class QueryStatSnapshotAdmin(admin.ModelAdmin):
    list_display = ("snapshot", "queryid", "calls", "mean_exec_time", "total_exec_time")
    search_fields = ("queryid", "query_text_normalized")
    list_filter = ("snapshot__status",)


@admin.register(TableStatSnapshot)
class TableStatSnapshotAdmin(admin.ModelAdmin):
    list_display = ("snapshot", "schema_name", "table_name", "seq_scan", "idx_scan", "n_live_tup", "n_dead_tup")
    search_fields = ("schema_name", "table_name")


@admin.register(IndexStatSnapshot)
class IndexStatSnapshotAdmin(admin.ModelAdmin):
    list_display = ("snapshot", "schema_name", "table_name", "index_name", "idx_scan", "index_size_bytes")
    search_fields = ("schema_name", "table_name", "index_name")


@admin.register(ActivitySnapshot)
class ActivitySnapshotAdmin(admin.ModelAdmin):
    list_display = ("snapshot", "pid", "state", "wait_event_type", "duration_ms")
    search_fields = ("query", "wait_event", "state")


@admin.register(AnalysisFinding)
class AnalysisFindingAdmin(admin.ModelAdmin):
    list_display = ("snapshot", "type", "severity", "object_type", "object_name", "is_resolved")
    list_filter = ("severity", "type", "is_resolved")
    search_fields = ("title", "description", "object_name")
