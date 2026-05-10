from django.db import DatabaseError, connection, transaction

from db_monitor.models import ActivitySnapshot, IndexStatSnapshot, QueryStatSnapshot, StatsSnapshot, TableStatSnapshot
from db_monitor.services.index_experiments import get_experiment_index_state
from db_monitor.services.query_classification import classify_sql_operation
from load_simulator.services.runs import link_latest_unattached_workload_run


def _fetch_all(cursor, sql, params=None):
    cursor.execute(sql, params or [])
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _extension_exists(cursor, extension_name):
    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = %s)", [extension_name])
    return bool(cursor.fetchone()[0])


def _safe_collect(notes, callback):
    try:
        return callback(), None
    except DatabaseError as exc:
        notes.append(str(exc))
        return [], str(exc)


@transaction.atomic
def collect_stats_snapshot(label="", environment="", query_limit=200, activity_limit=50, include_activity=True):
    notes = []
    database_settings = connection.settings_dict
    snapshot = StatsSnapshot.objects.create(
        label=label,
        environment=environment,
        database_vendor=connection.vendor,
        database_name=database_settings.get("NAME", "") or "",
        status=StatsSnapshot.Status.COMPLETED,
    )

    summary = {
        "query_stats": 0,
        "table_stats": 0,
        "index_stats": 0,
        "activities": 0,
        "notes": notes,
    }

    if connection.vendor != "postgresql":
        message = f"Statistics collection requires PostgreSQL; current backend is {connection.vendor}."
        workload_run = link_latest_unattached_workload_run(snapshot)
        snapshot.status = StatsSnapshot.Status.SKIPPED
        snapshot.notes = message
        snapshot.metadata_json = {
            "reason": "non_postgresql_backend",
            "workload_run": {
                "id": workload_run.id,
                "scenario": workload_run.scenario,
                "seed": workload_run.seed,
                "operations": workload_run.operations,
                "concurrency": workload_run.concurrency,
                "mutates_data": workload_run.mutates_data,
            }
            if workload_run
            else {},
        }
        snapshot.save(update_fields=["status", "notes", "metadata_json"])
        notes.append(message)
        return snapshot, summary

    with connection.cursor() as cursor:
        query_rows = []
        if _extension_exists(cursor, "pg_stat_statements"):
            query_rows, query_error = _safe_collect(
                notes,
                lambda: _fetch_all(
                    cursor,
                    """
                    SELECT
                        queryid::text AS queryid,
                        query,
                        calls,
                        total_exec_time,
                        mean_exec_time,
                        min_exec_time,
                        max_exec_time,
                        rows
                    FROM pg_stat_statements
                    ORDER BY total_exec_time DESC
                    LIMIT %s
                    """,
                    [query_limit],
                ),
            )
            if query_error:
                snapshot.status = StatsSnapshot.Status.DEGRADED
        else:
            notes.append("Extension `pg_stat_statements` is not enabled; query statistics were skipped.")
            snapshot.status = StatsSnapshot.Status.DEGRADED

        table_rows, table_error = _safe_collect(
            notes,
            lambda: _fetch_all(
                cursor,
                """
                SELECT
                    schemaname AS schema_name,
                    relname AS table_name,
                    seq_scan,
                    idx_scan,
                    seq_tup_read,
                    idx_tup_fetch,
                    n_live_tup,
                    n_dead_tup,
                    pg_total_relation_size(relid) AS table_size_bytes,
                    vacuum_count,
                    autovacuum_count,
                    analyze_count,
                    autoanalyze_count
                FROM pg_stat_user_tables
                ORDER BY seq_scan DESC, n_live_tup DESC
                """,
            ),
        )
        if table_error:
            snapshot.status = StatsSnapshot.Status.DEGRADED

        index_rows, index_error = _safe_collect(
            notes,
            lambda: _fetch_all(
                cursor,
                """
                SELECT
                    ui.schemaname AS schema_name,
                    ui.relname AS table_name,
                    ui.indexrelname AS index_name,
                    ui.idx_scan,
                    ui.idx_tup_read,
                    ui.idx_tup_fetch,
                    pg_relation_size(ui.indexrelid) AS index_size_bytes
                FROM pg_stat_user_indexes ui
                ORDER BY ui.idx_scan ASC, pg_relation_size(ui.indexrelid) DESC
                """,
            ),
        )
        if index_error:
            snapshot.status = StatsSnapshot.Status.DEGRADED

        activity_rows = []
        if include_activity:
            activity_rows, activity_error = _safe_collect(
                notes,
                lambda: _fetch_all(
                    cursor,
                    """
                    SELECT
                        pid,
                        COALESCE(state, '') AS state,
                        COALESCE(wait_event_type, '') AS wait_event_type,
                        COALESCE(wait_event, '') AS wait_event,
                        COALESCE(query, '') AS query,
                        COALESCE(EXTRACT(EPOCH FROM (clock_timestamp() - query_start)) * 1000, 0) AS duration_ms
                    FROM pg_stat_activity
                    WHERE pid <> pg_backend_pid()
                      AND datname = current_database()
                    ORDER BY duration_ms DESC NULLS LAST
                    LIMIT %s
                    """,
                    [activity_limit],
                ),
            )
            if activity_error:
                snapshot.status = StatsSnapshot.Status.DEGRADED

    QueryStatSnapshot.objects.bulk_create(
        [
            QueryStatSnapshot(
                snapshot=snapshot,
                queryid=row.get("queryid") or "",
                query_text_normalized=row.get("query") or "",
                operation_type=classify_sql_operation(row.get("query") or ""),
                calls=row.get("calls") or 0,
                total_exec_time=row.get("total_exec_time") or 0,
                mean_exec_time=row.get("mean_exec_time") or 0,
                min_exec_time=row.get("min_exec_time") or 0,
                max_exec_time=row.get("max_exec_time") or 0,
                rows=row.get("rows") or 0,
            )
            for row in query_rows
        ],
        batch_size=500,
    )
    TableStatSnapshot.objects.bulk_create(
        [
            TableStatSnapshot(
                snapshot=snapshot,
                schema_name=row.get("schema_name") or "",
                table_name=row.get("table_name") or "",
                seq_scan=row.get("seq_scan") or 0,
                idx_scan=row.get("idx_scan") or 0,
                seq_tup_read=row.get("seq_tup_read") or 0,
                idx_tup_fetch=row.get("idx_tup_fetch") or 0,
                n_live_tup=row.get("n_live_tup") or 0,
                n_dead_tup=row.get("n_dead_tup") or 0,
                table_size_bytes=row.get("table_size_bytes") or 0,
                vacuum_count=row.get("vacuum_count") or 0,
                autovacuum_count=row.get("autovacuum_count") or 0,
                analyze_count=row.get("analyze_count") or 0,
                autoanalyze_count=row.get("autoanalyze_count") or 0,
            )
            for row in table_rows
        ],
        batch_size=500,
    )
    IndexStatSnapshot.objects.bulk_create(
        [
            IndexStatSnapshot(
                snapshot=snapshot,
                schema_name=row.get("schema_name") or "",
                table_name=row.get("table_name") or "",
                index_name=row.get("index_name") or "",
                idx_scan=row.get("idx_scan") or 0,
                idx_tup_read=row.get("idx_tup_read") or 0,
                idx_tup_fetch=row.get("idx_tup_fetch") or 0,
                index_size_bytes=row.get("index_size_bytes") or 0,
            )
            for row in index_rows
        ],
        batch_size=500,
    )
    ActivitySnapshot.objects.bulk_create(
        [
            ActivitySnapshot(
                snapshot=snapshot,
                pid=row.get("pid") or 0,
                state=row.get("state") or "",
                wait_event_type=row.get("wait_event_type") or "",
                wait_event=row.get("wait_event") or "",
                query=row.get("query") or "",
                duration_ms=row.get("duration_ms") or 0,
            )
            for row in activity_rows
        ],
        batch_size=500,
    )

    summary["query_stats"] = len(query_rows)
    summary["table_stats"] = len(table_rows)
    summary["index_stats"] = len(index_rows)
    summary["activities"] = len(activity_rows)
    experiment_state = get_experiment_index_state()
    workload_run = link_latest_unattached_workload_run(snapshot)
    snapshot.notes = "\n".join(notes)
    snapshot.metadata_json = {
        "query_limit": query_limit,
        "activity_limit": activity_limit,
        "include_activity": include_activity,
        "index_experiment": experiment_state,
        "workload_run": {
            "id": workload_run.id,
            "scenario": workload_run.scenario,
            "seed": workload_run.seed,
            "operations": workload_run.operations,
            "concurrency": workload_run.concurrency,
            "mutates_data": workload_run.mutates_data,
        }
        if workload_run
        else {},
        "counts": {
            "query_stats": summary["query_stats"],
            "table_stats": summary["table_stats"],
            "index_stats": summary["index_stats"],
            "activities": summary["activities"],
        },
    }
    snapshot.save(update_fields=["status", "notes", "metadata_json"])
    return snapshot, summary
