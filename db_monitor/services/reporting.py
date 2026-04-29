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


def _normalize_query(text, limit=160):
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _query_label(preview, queryid, limit=88):
    return _normalize_query(preview, limit=limit) or queryid or "Query without fingerprint"


def _index_ddl(index_name, table_name, columns):
    return f"CREATE INDEX {index_name} ON {table_name} ({columns});"


def _chart_rows(rows, value_key, label_key="label", top=None):
    rows = list(rows[:top] if top else rows)
    if not rows:
        return []

    max_value = max((row.get(value_key, 0) or 0) for row in rows) or 1
    chart = []
    for row in rows:
        value = row.get(value_key, 0) or 0
        chart.append(
            {
                "label": row.get(label_key, ""),
                "value": value,
                "percent": round((value / max_value) * 100, 2),
                "meta": row.get("meta", ""),
            }
        )
    return chart


def _paired_chart_rows(rows):
    rows = list(rows)
    max_value = 1
    for row in rows:
        max_value = max(max_value, row.get("before", 0) or 0, row.get("after", 0) or 0)

    chart = []
    for row in rows:
        before = row.get("before", 0) or 0
        after = row.get("after", 0) or 0
        chart.append(
            {
                "label": row["label"],
                "before": before,
                "after": after,
                "before_percent": round((before / max_value) * 100, 2),
                "after_percent": round((after / max_value) * 100, 2),
                "delta": after - before,
            }
        )
    return chart


def _finding_display_name(finding):
    if finding.object_type == "query":
        return finding.evidence_json.get("query_preview") or finding.object_name or finding.title
    return finding.object_name or finding.title


def _build_index_advisories(summary):
    advisories = []
    query_entries = summary["queries"]["top_regressions"] + summary["queries"]["top_improvements"]
    table_entries = summary["tables"]["top_seq_scan_increases"]

    created_at_query = None
    for entry in query_entries:
        preview = entry.get("query_preview", "")
        if "shop_product" in preview and "created_at" in preview:
            created_at_query = entry
            break

    created_at_table = next(
        (entry for entry in table_entries if entry["table"] == "public.shop_product"),
        None,
    )

    if created_at_query or created_at_table:
        advisories.append(
            {
                "slug": "product-created-at",
                "title": "Index recommendation for recent product filtering",
                "reason": (
                    "The catalog flow filters or sorts by Product.created_at and the controlled-issues setup "
                    "intentionally leaves that column without an index."
                ),
                "target": {
                    "model": "shop.models.Product",
                    "field": "created_at",
                    "table": "public.shop_product",
                    "django_index": 'models.Index(fields=["-created_at"], name="shop_product_created_at_idx")',
                    "sql": _index_ddl(
                        "shop_product_created_at_idx",
                        "shop_product",
                        "created_at DESC",
                    ),
                    "recommended_location": "Product.Meta.indexes in shop/models.py",
                },
                "query_comparison": {
                    "label": (created_at_query or {}).get("query_label", "Recent product query"),
                    "before_total_ms": (created_at_query or {}).get("total_exec_time", {}).get("before", 0),
                    "after_total_ms": (created_at_query or {}).get("total_exec_time", {}).get("after", 0),
                    "delta_total_ms": (created_at_query or {}).get("total_exec_time", {}).get("delta", 0),
                    "before_mean_ms": (created_at_query or {}).get("mean_exec_time", {}).get("before", 0),
                    "after_mean_ms": (created_at_query or {}).get("mean_exec_time", {}).get("after", 0),
                    "delta_mean_ms": (created_at_query or {}).get("mean_exec_time", {}).get("delta", 0),
                    "before_calls": (created_at_query or {}).get("calls", {}).get("before", 0),
                    "after_calls": (created_at_query or {}).get("calls", {}).get("after", 0),
                },
                "table_comparison": {
                    "before_seq_scan": (created_at_table or {}).get("seq_scan", {}).get("before", 0),
                    "after_seq_scan": (created_at_table or {}).get("seq_scan", {}).get("after", 0),
                    "delta_seq_scan": (created_at_table or {}).get("seq_scan", {}).get("delta", 0),
                    "before_idx_scan": (created_at_table or {}).get("idx_scan", {}).get("before", 0),
                    "after_idx_scan": (created_at_table or {}).get("idx_scan", {}).get("after", 0),
                    "delta_idx_scan": (created_at_table or {}).get("idx_scan", {}).get("delta", 0),
                },
                "expected_impact": [
                    "fewer sequential scans on shop_product for recent-product listings",
                    "lower mean execution time for newest-product filters",
                    "more stable catalog latency when the dataset grows",
                ],
            }
        )

    text_search_query = next(
        (
            entry
            for entry in query_entries
            if "shop_product" in entry.get("query_preview", "")
            and "ILIKE" in entry.get("query_preview", "")
        ),
        None,
    )
    if text_search_query:
        advisories.append(
            {
                "slug": "product-search",
                "title": "Search indexing opportunity for product text lookup",
                "reason": "Repeated ILIKE search on product name/description is showing up in the workload.",
                "target": {
                    "model": "shop.models.Product",
                    "field": "name / description",
                    "table": "public.shop_product",
                    "django_index": "Prefer PostgreSQL trigram or full-text index added via migration.",
                    "sql": (
                        "CREATE INDEX shop_product_name_trgm_idx "
                        "ON shop_product USING gin (name gin_trgm_ops);"
                    ),
                    "recommended_location": "Dedicated PostgreSQL migration for text-search optimization",
                },
                "query_comparison": {
                    "label": text_search_query.get("query_label", "Product search query"),
                    "before_total_ms": text_search_query.get("total_exec_time", {}).get("before", 0),
                    "after_total_ms": text_search_query.get("total_exec_time", {}).get("after", 0),
                    "delta_total_ms": text_search_query.get("total_exec_time", {}).get("delta", 0),
                    "before_mean_ms": text_search_query.get("mean_exec_time", {}).get("before", 0),
                    "after_mean_ms": text_search_query.get("mean_exec_time", {}).get("after", 0),
                    "delta_mean_ms": text_search_query.get("mean_exec_time", {}).get("delta", 0),
                    "before_calls": text_search_query.get("calls", {}).get("before", 0),
                    "after_calls": text_search_query.get("calls", {}).get("after", 0),
                },
                "table_comparison": None,
                "expected_impact": [
                    "faster product search under repeated catalog filtering",
                    "less CPU cost from broad ILIKE scans",
                    "clearer separation between search and newest-product bottlenecks",
                ],
            }
        )

    return advisories


def _build_index_experiment_story(summary):
    experiment = summary.get("index_experiment", {})
    changes = experiment.get("changes", [])
    if not changes:
        return None

    return {
        "before_mode": experiment.get("before_mode") or "unknown",
        "after_mode": experiment.get("after_mode") or "unknown",
        "changes": changes,
        "is_valid_before_after": (
            experiment.get("before_mode") == "without_indexes"
            and experiment.get("after_mode") == "with_indexes"
        ),
    }


def _severity_counts(findings):
    counts = Counter(finding.severity for finding in findings)
    ordered = []
    for severity in ["high", "medium", "low"]:
        if counts.get(severity):
            ordered.append({"severity": severity, "count": counts[severity]})
    return ordered


def _snapshot_queryset():
    return StatsSnapshot.objects.order_by("-created_at", "-id").prefetch_related(
        Prefetch("query_stats", queryset=QueryStatSnapshot.objects.order_by("-total_exec_time", "-calls")),
        Prefetch("table_stats", queryset=TableStatSnapshot.objects.order_by("-seq_scan", "-n_live_tup")),
        Prefetch("index_stats", queryset=IndexStatSnapshot.objects.order_by("idx_scan", "-index_size_bytes")),
        Prefetch("activities", queryset=ActivitySnapshot.objects.order_by("-duration_ms", "pid")),
        Prefetch("findings", queryset=AnalysisFinding.objects.order_by("severity", "-id")),
    )


def _query_rankings(snapshot, limit):
    query_stats = list(snapshot.query_stats.all())
    ranked = [
        {
            "queryid": row.queryid,
            "label": _query_label(row.query_text_normalized, row.queryid),
            "preview": _normalize_query(row.query_text_normalized),
            "calls": row.calls,
            "total_exec_time": row.total_exec_time,
            "mean_exec_time": row.mean_exec_time,
            "max_exec_time": row.max_exec_time,
            "rows": row.rows,
        }
        for row in query_stats
    ]
    slowest = sorted(
        ranked,
        key=lambda row: (row["mean_exec_time"], row["max_exec_time"], row["total_exec_time"]),
        reverse=True,
    )[:limit]
    hottest = sorted(
        ranked,
        key=lambda row: (row["total_exec_time"], row["calls"], row["mean_exec_time"]),
        reverse=True,
    )[:limit]
    return {
        "slowest": slowest,
        "hottest": hottest,
        "all": ranked,
        "charts": {
            "hot_exec_time": _chart_rows(
                [
                    {
                        "label": row["label"],
                        "total_exec_time": row["total_exec_time"],
                        "meta": f"{row['calls']} calls | mean {row['mean_exec_time']:.2f} ms",
                    }
                    for row in hottest
                ],
                "total_exec_time",
            ),
            "slow_mean_time": _chart_rows(
                [
                    {
                        "label": row["label"],
                        "mean_exec_time": row["mean_exec_time"],
                        "meta": f"max {row['max_exec_time']:.2f} ms",
                    }
                    for row in slowest
                ],
                "mean_exec_time",
            ),
        },
    }


def _table_rankings(snapshot, limit):
    ranked = []
    for row in snapshot.table_stats.all():
        idx_scan = row.idx_scan or 0
        seq_ratio = row.seq_scan / max(idx_scan, 1)
        ranked.append(
            {
                "table": f"{row.schema_name}.{row.table_name}",
                "label": f"{row.table_name} ({row.schema_name})",
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
        "charts": {
            "seq_scans": _chart_rows(
                [
                    {
                        "label": row["label"],
                        "seq_scan": row["seq_scan"],
                        "meta": f"ratio {row['seq_to_idx_ratio']:.2f}",
                    }
                    for row in problematic
                ],
                "seq_scan",
            )
        },
    }


def _index_rankings(snapshot, limit):
    ranked = [
        {
            "index": f"{row.schema_name}.{row.index_name}",
            "label": row.index_name,
            "table": f"{row.schema_name}.{row.table_name}",
            "idx_scan": row.idx_scan,
            "index_size_bytes": row.index_size_bytes,
        }
        for row in snapshot.index_stats.all()
    ]
    underused = sorted(ranked, key=lambda row: (row["idx_scan"], -row["index_size_bytes"]))[:limit]
    return {
        "underused": underused,
        "all": ranked,
        "charts": {
            "underused_indexes": _chart_rows(
                [
                    {
                        "label": row["label"],
                        "index_size_bytes": row["index_size_bytes"],
                        "meta": f"idx_scan {row['idx_scan']}",
                    }
                    for row in underused
                ],
                "index_size_bytes",
            )
        },
    }


def _activity_rankings(snapshot, limit):
    activities = [
        {
            "pid": row.pid,
            "label": f"PID {row.pid}",
            "state": row.state,
            "wait_event_type": row.wait_event_type,
            "wait_event": row.wait_event,
            "duration_ms": row.duration_ms,
            "query": _normalize_query(row.query),
        }
        for row in snapshot.activities.all()
    ]
    longest = activities[:limit]
    return {
        "longest": longest,
        "all": activities,
        "charts": {
            "activity_duration": _chart_rows(
                [
                    {
                        "label": row["label"],
                        "duration_ms": row["duration_ms"],
                        "meta": row["state"] or "unknown state",
                    }
                    for row in longest
                ],
                "duration_ms",
            )
        },
    }


def _finding_rankings(snapshot, limit):
    findings = list(snapshot.findings.all())
    top = [
        {
            "type": finding.type,
            "severity": finding.severity,
            "title": finding.title,
            "description": finding.description,
            "object_type": finding.object_type,
            "object_name": finding.object_name,
            "display_name": _finding_display_name(finding),
            "evidence_json": finding.evidence_json,
        }
        for finding in findings[:limit]
    ]
    severity = _severity_counts(findings)
    return {
        "by_severity": severity,
        "top": top,
        "all": findings,
        "charts": {
            "severity": _chart_rows(
                [
                    {
                        "label": item["severity"],
                        "count": item["count"],
                        "meta": f"{item['count']} findings",
                    }
                    for item in severity
                ],
                "count",
            )
        },
    }


def _snapshot_summary(snapshot):
    findings = list(snapshot.findings.all())
    query_stats = list(snapshot.query_stats.all())
    table_stats = list(snapshot.table_stats.all())
    index_stats = list(snapshot.index_stats.all())
    activities = list(snapshot.activities.all())
    metadata_counts = (snapshot.metadata_json or {}).get("counts", {})
    query_rankings = _query_rankings(snapshot, 5)
    table_rankings = _table_rankings(snapshot, 5)
    finding_rankings = _finding_rankings(snapshot, 5)

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
        "severity_counts": finding_rankings["by_severity"],
        "top_slow_queries": query_rankings["slowest"],
        "top_hot_queries": query_rankings["hottest"],
        "problematic_tables": table_rankings["problematic"],
        "underused_indexes": _index_rankings(snapshot, 5)["underused"],
        "longest_activities": _activity_rankings(snapshot, 5)["longest"],
        "top_findings": finding_rankings["top"],
        "charts": {
            "hot_queries": query_rankings["charts"]["hot_exec_time"],
            "slow_queries": query_rankings["charts"]["slow_mean_time"],
            "table_scans": table_rankings["charts"]["seq_scans"],
            "finding_severity": finding_rankings["charts"]["severity"],
        },
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
            "index_experiment_story": _build_index_experiment_story(summary),
            "workload_chart": _paired_chart_rows(
                [
                    {
                        "label": "Total exec time",
                        "before": summary["queries"]["totals"]["before"]["total_exec_time"],
                        "after": summary["queries"]["totals"]["after"]["total_exec_time"],
                    },
                    {
                        "label": "Query calls",
                        "before": summary["queries"]["totals"]["before"]["calls"],
                        "after": summary["queries"]["totals"]["after"]["calls"],
                    },
                    {
                        "label": "Seq scans",
                        "before": summary["tables"]["totals"]["before"]["seq_scan"],
                        "after": summary["tables"]["totals"]["after"]["seq_scan"],
                    },
                    {
                        "label": "Index scans",
                        "before": summary["tables"]["totals"]["before"]["idx_scan"],
                        "after": summary["tables"]["totals"]["after"]["idx_scan"],
                    },
                ]
            ),
            "index_advisories": _build_index_advisories(summary),
        }

    return {
        "latest_snapshot": _snapshot_summary(latest_snapshot) if latest_snapshot else None,
        "recent_snapshots": [_snapshot_summary(snapshot) for snapshot in snapshots],
        "comparison": comparison,
        "snapshot_options": snapshots,
    }


def get_snapshot_report(snapshot_id, ranking_limit=10):
    snapshot = _snapshot_queryset().get(id=snapshot_id)
    queries = _query_rankings(snapshot, ranking_limit)
    tables = _table_rankings(snapshot, ranking_limit)
    indexes = _index_rankings(snapshot, ranking_limit)
    activities = _activity_rankings(snapshot, ranking_limit)
    findings = _finding_rankings(snapshot, ranking_limit)
    return {
        "snapshot": snapshot,
        "summary": _snapshot_summary(snapshot),
        "queries": queries,
        "tables": tables,
        "indexes": indexes,
        "activities": activities,
        "findings": findings,
    }


def get_comparison_report(snapshot_a_id, snapshot_b_id, top=10):
    snapshot_a = StatsSnapshot.objects.get(id=snapshot_a_id)
    snapshot_b = StatsSnapshot.objects.get(id=snapshot_b_id)
    summary = compare_snapshots(snapshot_a, snapshot_b, top=top)
    return {
        "snapshot_a": snapshot_a,
        "snapshot_b": snapshot_b,
        "summary": summary,
        "index_experiment_story": _build_index_experiment_story(summary),
        "snapshot_options": StatsSnapshot.objects.order_by("-created_at", "-id")[:10],
        "workload_chart": _paired_chart_rows(
            [
                {
                    "label": "Total exec time",
                    "before": summary["queries"]["totals"]["before"]["total_exec_time"],
                    "after": summary["queries"]["totals"]["after"]["total_exec_time"],
                },
                {
                    "label": "Query calls",
                    "before": summary["queries"]["totals"]["before"]["calls"],
                    "after": summary["queries"]["totals"]["after"]["calls"],
                },
                {
                    "label": "Seq scans",
                    "before": summary["tables"]["totals"]["before"]["seq_scan"],
                    "after": summary["tables"]["totals"]["after"]["seq_scan"],
                },
                {
                    "label": "Index scans",
                    "before": summary["tables"]["totals"]["before"]["idx_scan"],
                    "after": summary["tables"]["totals"]["after"]["idx_scan"],
                },
            ]
        ),
        "finding_severity_chart": _paired_chart_rows(
            [
                {
                    "label": severity.title(),
                    "before": metrics["before"],
                    "after": metrics["after"],
                }
                for severity, metrics in summary["findings"]["by_severity"].items()
            ]
        ),
        "index_advisories": _build_index_advisories(summary),
    }
