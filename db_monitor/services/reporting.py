from collections import Counter

from django.db.models import Prefetch

from db_monitor.models import (
    ActivitySnapshot,
    AnalysisFinding,
    IndexStatSnapshot,
    QueryStatSnapshot,
    StatsSnapshot,
    TableStatSnapshot,
)
from db_monitor.services.comparison import compare_snapshots


def _metric_delta(before, after):
    return {
        "before": before,
        "after": after,
        "delta": after - before,
    }


def _normalize_query(text, limit=160):
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _severity_counts(findings):
    counts = Counter(finding.severity for finding in findings)
    return [
        {"severity": severity, "count": counts[severity]}
        for severity in ["high", "medium", "low"]
        if counts.get(severity)
    ]


def _snapshot_queryset():
    return StatsSnapshot.objects.prefetch_related(
        Prefetch("query_stats", queryset=QueryStatSnapshot.objects.order_by("-total_exec_time", "-calls")),
        Prefetch("table_stats", queryset=TableStatSnapshot.objects.order_by("-seq_scan", "-n_live_tup")),
        Prefetch("index_stats", queryset=IndexStatSnapshot.objects.order_by("idx_scan", "-index_size_bytes")),
        Prefetch("activities", queryset=ActivitySnapshot.objects.order_by("-duration_ms", "pid")),
        Prefetch("findings", queryset=AnalysisFinding.objects.order_by("severity", "-id")),
    )


def _query_rankings(snapshot, limit):
    query_stats = list(snapshot.query_stats.all())
    slowest = sorted(
        query_stats,
        key=lambda row: (row.mean_exec_time, row.max_exec_time, row.total_exec_time),
        reverse=True,
    )[:limit]
    hottest = sorted(
        query_stats,
        key=lambda row: (row.total_exec_time, row.calls, row.mean_exec_time),
        reverse=True,
    )[:limit]
    return {
        "slowest": [
            {
                "queryid": row.queryid,
                "preview": _normalize_query(row.query_text_normalized),
                "calls": row.calls,
                "total_exec_time": row.total_exec_time,
                "mean_exec_time": row.mean_exec_time,
                "max_exec_time": row.max_exec_time,
                "rows": row.rows,
            }
            for row in slowest
        ],
        "hottest": [
            {
                "queryid": row.queryid,
                "preview": _normalize_query(row.query_text_normalized),
                "calls": row.calls,
                "total_exec_time": row.total_exec_time,
                "mean_exec_time": row.mean_exec_time,
                "max_exec_time": row.max_exec_time,
                "rows": row.rows,
            }
            for row in hottest
        ],
        "all": query_stats,
    }


def _table_rankings(snapshot, limit):
    ranked = []
    for row in snapshot.table_stats.all():
        idx_scan = row.idx_scan or 0
        seq_ratio = row.seq_scan / max(idx_scan, 1)
        ranked.append(
            {
                "table": f"{row.schema_name}.{row.table_name}",
                "seq_scan": row.seq_scan,
                "idx_scan": row.idx_scan,
                "n_live_tup": row.n_live_tup,
                "n_dead_tup": row.n_dead_tup,
                "seq_to_idx_ratio": seq_ratio,
            }
        )
    problematic = sorted(
        ranked,
        key=lambda row: (row["seq_scan"], row["seq_to_idx_ratio"], row["n_live_tup"]),
        reverse=True,
    )[:limit]
    return {
        "problematic": problematic,
        "all": ranked,
    }


def _index_rankings(snapshot, limit):
    ranked = [
        {
            "index": f"{row.schema_name}.{row.index_name}",
            "table": f"{row.schema_name}.{row.table_name}",
            "idx_scan": row.idx_scan,
            "index_size_bytes": row.index_size_bytes,
        }
        for row in snapshot.index_stats.all()
    ]
    return {
        "underused": sorted(ranked, key=lambda row: (row["idx_scan"], -row["index_size_bytes"]))[:limit],
        "all": ranked,
    }


def _activity_rankings(snapshot, limit):
    activities = [
        {
            "pid": row.pid,
            "state": row.state,
            "wait_event_type": row.wait_event_type,
            "wait_event": row.wait_event,
            "duration_ms": row.duration_ms,
            "query": _normalize_query(row.query),
        }
        for row in snapshot.activities.all()
    ]
    return {
        "longest": activities[:limit],
        "all": activities,
    }


def _finding_rankings(snapshot, limit):
    findings = list(snapshot.findings.all())
    return {
        "by_severity": _severity_counts(findings),
        "top": [
            {
                "type": finding.type,
                "severity": finding.severity,
                "title": finding.title,
                "description": finding.description,
                "object_type": finding.object_type,
                "object_name": finding.object_name,
                "evidence_json": finding.evidence_json,
            }
            for finding in findings[:limit]
        ],
        "all": findings,
    }


def _snapshot_summary(snapshot):
    findings = list(snapshot.findings.all())
    query_stats = list(snapshot.query_stats.all())
    table_stats = list(snapshot.table_stats.all())
    index_stats = list(snapshot.index_stats.all())
    activities = list(snapshot.activities.all())
    metadata_counts = (snapshot.metadata_json or {}).get("counts", {})
    query_rankings = _query_rankings(snapshot, 5)

    return {
        "snapshot": snapshot,
        "counts": {
            "queries": metadata_counts.get("query_stats", len(query_stats)),
            "tables": metadata_counts.get("table_stats", len(table_stats)),
            "indexes": metadata_counts.get("index_stats", len(index_stats)),
            "activities": metadata_counts.get("activities", len(activities)),
            "findings": len(findings),
        },
        "metrics": {
            "total_calls": sum(row.calls for row in query_stats),
            "total_exec_time": sum(row.total_exec_time for row in query_stats),
            "total_seq_scans": sum(row.seq_scan for row in table_stats),
            "total_idx_scans": sum(row.idx_scan for row in table_stats),
        },
        "severity_counts": _severity_counts(findings),
        "top_slow_queries": query_rankings["slowest"],
        "top_hot_queries": query_rankings["hottest"],
        "problematic_tables": _table_rankings(snapshot, 5)["problematic"],
        "underused_indexes": _index_rankings(snapshot, 5)["underused"],
        "longest_activities": _activity_rankings(snapshot, 5)["longest"],
        "top_findings": _finding_rankings(snapshot, 5)["top"],
    }


def get_dashboard_overview(limit=5):
    snapshots = list(_snapshot_queryset()[: max(limit, 5)])
    latest_snapshot = snapshots[0] if snapshots else None
    comparison = None
    if len(snapshots) >= 2:
        older_snapshot = snapshots[1]
        summary = compare_snapshots(older_snapshot, latest_snapshot, top=limit)
        comparison = {
            "summary": summary,
            "findings_delta": summary["findings"]["totals"]["delta"],
            "query_total_exec_time": _metric_delta(
                summary["queries"]["totals"]["before"]["total_exec_time"],
                summary["queries"]["totals"]["after"]["total_exec_time"],
            ),
            "seq_scan_total": _metric_delta(
                summary["tables"]["totals"]["before"]["seq_scan"],
                summary["tables"]["totals"]["after"]["seq_scan"],
            ),
        }

    return {
        "latest_snapshot": _snapshot_summary(latest_snapshot) if latest_snapshot else None,
        "recent_snapshots": [_snapshot_summary(snapshot) for snapshot in snapshots],
        "comparison": comparison,
        "snapshot_options": snapshots,
    }


def get_snapshot_report(snapshot_id, ranking_limit=10):
    snapshot = _snapshot_queryset().get(id=snapshot_id)
    return {
        "snapshot": snapshot,
        "summary": _snapshot_summary(snapshot),
        "queries": _query_rankings(snapshot, ranking_limit),
        "tables": _table_rankings(snapshot, ranking_limit),
        "indexes": _index_rankings(snapshot, ranking_limit),
        "activities": _activity_rankings(snapshot, ranking_limit),
        "findings": _finding_rankings(snapshot, ranking_limit),
    }


def get_comparison_report(snapshot_a_id, snapshot_b_id, top=10):
    snapshot_a = StatsSnapshot.objects.get(id=snapshot_a_id)
    snapshot_b = StatsSnapshot.objects.get(id=snapshot_b_id)
    return {
        "snapshot_a": snapshot_a,
        "snapshot_b": snapshot_b,
        "summary": compare_snapshots(snapshot_a, snapshot_b, top=top),
        "snapshot_options": StatsSnapshot.objects.all()[:10],
    }
