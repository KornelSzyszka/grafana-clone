from collections import Counter

from db_monitor.models import StatsSnapshot
from db_monitor.services.query_classification import classify_sql_operation, is_read_operation, is_write_operation


def _truncate(text, limit=120):
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _metric_block(before_value, after_value):
    before_value = before_value or 0
    after_value = after_value or 0
    scale = max(abs(before_value), abs(after_value))
    if scale <= 0:
        scale = 1
    return {
        "before": before_value,
        "after": after_value,
        "delta": after_value - before_value,
        "scale_max": scale,
        "before_percent": round((abs(before_value) / scale) * 100, 2),
        "after_percent": round((abs(after_value) / scale) * 100, 2),
    }


def _snapshot_descriptor(snapshot):
    metadata = snapshot.metadata_json or {}
    return {
        "id": snapshot.id,
        "label": snapshot.label,
        "environment": snapshot.environment,
        "status": snapshot.status,
        "database_vendor": snapshot.database_vendor,
        "database_name": snapshot.database_name,
        "created_at": snapshot.created_at.isoformat(),
        "index_experiment": metadata.get("index_experiment", {}),
    }


def _summarize_index_experiment(snapshot_a, snapshot_b):
    before = (snapshot_a.metadata_json or {}).get("index_experiment", {})
    after = (snapshot_b.metadata_json or {}).get("index_experiment", {})
    before_indexes = {item["name"]: item for item in before.get("indexes", [])}
    after_indexes = {item["name"]: item for item in after.get("indexes", [])}
    changes = []

    for index_name in sorted(set(before_indexes) | set(after_indexes)):
        before_item = before_indexes.get(index_name, {})
        after_item = after_indexes.get(index_name, {})
        before_present = bool(before_item.get("present"))
        after_present = bool(after_item.get("present"))
        if before_present == after_present:
            change = "unchanged"
        elif after_present:
            change = "added"
        else:
            change = "removed"

        changes.append(
            {
                "name": index_name,
                "description": after_item.get("description") or before_item.get("description") or "",
                "table": after_item.get("table") or before_item.get("table") or "",
                "columns": after_item.get("columns") or before_item.get("columns") or "",
                "before_present": before_present,
                "after_present": after_present,
                "change": change,
            }
        )

    return {
        "before_mode": before.get("mode", ""),
        "after_mode": after.get("mode", ""),
        "changes": changes,
        "added_count": sum(1 for change in changes if change["change"] == "added"),
        "removed_count": sum(1 for change in changes if change["change"] == "removed"),
    }


def _query_key(query_stat):
    normalized_text = " ".join((query_stat.query_text_normalized or "").split())
    if normalized_text:
        return f"text:{normalized_text}"
    if query_stat.queryid:
        return f"queryid:{query_stat.queryid}"
    return "text:"


def _row_operation(row):
    operation = getattr(row, "operation_type", "") or ""
    if not operation or operation == "UNKNOWN":
        return classify_sql_operation(row.query_text_normalized)
    return operation


def _finding_key(finding):
    return finding.type, finding.object_name or finding.title


def _query_entry(before_stat, after_stat):
    queryid = ""
    preview_source = ""
    if before_stat:
        queryid = before_stat.queryid
        preview_source = before_stat.query_text_normalized
    if after_stat:
        queryid = after_stat.queryid or queryid
        preview_source = after_stat.query_text_normalized or preview_source

    display_name = _truncate(preview_source, limit=90) or queryid or "Query without fingerprint"
    operation_type = getattr(after_stat, "operation_type", "") or getattr(before_stat, "operation_type", "")
    if not operation_type or operation_type == "UNKNOWN":
        operation_type = classify_sql_operation(preview_source)

    return {
        "queryid": queryid,
        "operation_type": operation_type,
        "query_preview": _truncate(preview_source, limit=160),
        "query_label": display_name,
        "calls": _metric_block(getattr(before_stat, "calls", 0), getattr(after_stat, "calls", 0)),
        "total_exec_time": _metric_block(
            getattr(before_stat, "total_exec_time", 0),
            getattr(after_stat, "total_exec_time", 0),
        ),
        "mean_exec_time": _metric_block(
            getattr(before_stat, "mean_exec_time", 0),
            getattr(after_stat, "mean_exec_time", 0),
        ),
        "max_exec_time": _metric_block(
            getattr(before_stat, "max_exec_time", 0),
            getattr(after_stat, "max_exec_time", 0),
        ),
        "rows": _metric_block(getattr(before_stat, "rows", 0), getattr(after_stat, "rows", 0)),
    }


def _is_transaction_control_query(entry):
    preview = (entry.get("query_preview") or "").strip().upper()
    return preview in {
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "START TRANSACTION",
    }


def _is_meaningful_delta(metric, epsilon=0.001):
    return abs(metric["delta"]) > epsilon


def _is_meaningful_query_comparison(entry):
    return (
        entry["state"] == "changed"
        and not _is_transaction_control_query(entry)
        and (
            _is_meaningful_delta(entry["total_exec_time"])
            or _is_meaningful_delta(entry["mean_exec_time"])
            or abs(entry["calls"]["delta"]) > 0
        )
    )


def _entry_matches_index_change(entry, index_change):
    preview = (entry.get("query_preview") or "").lower()
    table_name = (index_change.get("table") or "").split(".")[-1].lower()
    column_tokens = [
        token.strip().lower()
        for token in (index_change.get("columns") or "").replace("DESC", "").replace("ASC", "").split()
        if token.strip() and token.strip().lower() not in {"using", "gin", "btree"}
    ]
    return bool(
        preview
        and (
            (table_name and table_name in preview)
            or any(token in preview for token in column_tokens)
        )
    )


def _table_key(table_stat):
    return f"{table_stat.schema_name}.{table_stat.table_name}"


def _table_entry(before_stat, after_stat):
    schema_name = getattr(after_stat, "schema_name", getattr(before_stat, "schema_name", ""))
    table_name = getattr(after_stat, "table_name", getattr(before_stat, "table_name", ""))
    return {
        "table": f"{schema_name}.{table_name}",
        "seq_scan": _metric_block(getattr(before_stat, "seq_scan", 0), getattr(after_stat, "seq_scan", 0)),
        "idx_scan": _metric_block(getattr(before_stat, "idx_scan", 0), getattr(after_stat, "idx_scan", 0)),
        "seq_tup_read": _metric_block(getattr(before_stat, "seq_tup_read", 0), getattr(after_stat, "seq_tup_read", 0)),
        "idx_tup_fetch": _metric_block(getattr(before_stat, "idx_tup_fetch", 0), getattr(after_stat, "idx_tup_fetch", 0)),
        "n_live_tup": _metric_block(
            getattr(before_stat, "n_live_tup", 0),
            getattr(after_stat, "n_live_tup", 0),
        ),
        "n_dead_tup": _metric_block(
            getattr(before_stat, "n_dead_tup", 0),
            getattr(after_stat, "n_dead_tup", 0),
        ),
        "table_size_bytes": _metric_block(
            getattr(before_stat, "table_size_bytes", 0),
            getattr(after_stat, "table_size_bytes", 0),
        ),
    }


def _index_key(index_stat):
    return f"{index_stat.schema_name}.{index_stat.index_name}"


def _index_entry(before_stat, after_stat):
    schema_name = getattr(after_stat, "schema_name", getattr(before_stat, "schema_name", ""))
    table_name = getattr(after_stat, "table_name", getattr(before_stat, "table_name", ""))
    index_name = getattr(after_stat, "index_name", getattr(before_stat, "index_name", ""))
    return {
        "index": f"{schema_name}.{index_name}",
        "table": f"{schema_name}.{table_name}",
        "idx_scan": _metric_block(getattr(before_stat, "idx_scan", 0), getattr(after_stat, "idx_scan", 0)),
        "idx_tup_read": _metric_block(getattr(before_stat, "idx_tup_read", 0), getattr(after_stat, "idx_tup_read", 0)),
        "idx_tup_fetch": _metric_block(getattr(before_stat, "idx_tup_fetch", 0), getattr(after_stat, "idx_tup_fetch", 0)),
        "index_size_bytes": _metric_block(
            getattr(before_stat, "index_size_bytes", 0),
            getattr(after_stat, "index_size_bytes", 0),
        ),
    }


def _summarize_queries(snapshot_a, snapshot_b, top):
    index_experiment = _summarize_index_experiment(snapshot_a, snapshot_b)
    before_map = {_query_key(row): row for row in snapshot_a.query_stats.all()}
    after_map = {_query_key(row): row for row in snapshot_b.query_stats.all()}
    entries = []

    for key in sorted(set(before_map) | set(after_map)):
        before_row = before_map.get(key)
        after_row = after_map.get(key)
        entry = _query_entry(before_row, after_row)
        entry["state"] = "changed"
        if before_row is None:
            entry["state"] = "added"
        elif after_row is None:
            entry["state"] = "removed"
        entries.append(entry)

    comparable_entries = [entry for entry in entries if _is_meaningful_query_comparison(entry)]

    regressions = sorted(
        [
            entry
            for entry in comparable_entries
            if entry["total_exec_time"]["delta"] > 0.001
            or (
                abs(entry["total_exec_time"]["delta"]) <= 0.001
                and entry["mean_exec_time"]["delta"] > 0.001
            )
        ],
        key=lambda item: (
            item["total_exec_time"]["delta"],
            item["mean_exec_time"]["delta"],
            item["calls"]["delta"],
        ),
        reverse=True,
    )[:top]
    improvements = sorted(
        [
            entry
            for entry in comparable_entries
            if entry["total_exec_time"]["delta"] < -0.001
            or (
                abs(entry["total_exec_time"]["delta"]) <= 0.001
                and entry["mean_exec_time"]["delta"] < -0.001
            )
        ],
        key=lambda item: (
            item["total_exec_time"]["delta"],
            item["mean_exec_time"]["delta"],
            item["calls"]["delta"],
        ),
    )

    added_indexes = [change for change in index_experiment["changes"] if change["change"] == "added"]
    prioritized_improvements = []
    if (
        index_experiment["before_mode"] == "without_indexes"
        and index_experiment["after_mode"] == "with_indexes"
        and added_indexes
    ):
        prioritized_improvements = [
            entry
            for entry in improvements
            if any(_entry_matches_index_change(entry, change) for change in added_indexes)
        ]

    merged_improvements = []
    seen_labels = set()
    for entry in prioritized_improvements + improvements:
        label = entry["query_label"]
        if label in seen_labels:
            continue
        seen_labels.add(label)
        merged_improvements.append(entry)
        if len(merged_improvements) >= top:
            break

    operation_totals = {}
    for operation in sorted({entry["operation_type"] for entry in entries} | {"SELECT", "INSERT", "UPDATE", "DELETE"}):
        before_rows = [row for row in before_map.values() if _row_operation(row) == operation]
        after_rows = [row for row in after_map.values() if _row_operation(row) == operation]
        operation_totals[operation] = {
            "calls": _metric_block(sum(row.calls for row in before_rows), sum(row.calls for row in after_rows)),
            "total_exec_time": _metric_block(
                sum(row.total_exec_time for row in before_rows),
                sum(row.total_exec_time for row in after_rows),
            ),
            "rows": _metric_block(sum(row.rows for row in before_rows), sum(row.rows for row in after_rows)),
        }

    read_before = [row for row in before_map.values() if is_read_operation(_row_operation(row))]
    read_after = [row for row in after_map.values() if is_read_operation(_row_operation(row))]
    write_before = [row for row in before_map.values() if is_write_operation(_row_operation(row))]
    write_after = [row for row in after_map.values() if is_write_operation(_row_operation(row))]

    top_by_operation = {}
    for operation in ["SELECT", "INSERT", "UPDATE", "DELETE"]:
        top_by_operation[operation] = sorted(
            [entry for entry in entries if entry["operation_type"] == operation],
            key=lambda item: (
                item["total_exec_time"]["after"],
                item["calls"]["after"],
                item["mean_exec_time"]["after"],
            ),
            reverse=True,
        )[:top]

    return {
        "totals": {
            "before": {
                "calls": sum(row.calls for row in before_map.values()),
                "total_exec_time": sum(row.total_exec_time for row in before_map.values()),
                "rows": sum(row.rows for row in before_map.values()),
            },
            "after": {
                "calls": sum(row.calls for row in after_map.values()),
                "total_exec_time": sum(row.total_exec_time for row in after_map.values()),
                "rows": sum(row.rows for row in after_map.values()),
            },
        },
        "read_totals": {
            "calls": _metric_block(sum(row.calls for row in read_before), sum(row.calls for row in read_after)),
            "total_exec_time": _metric_block(
                sum(row.total_exec_time for row in read_before),
                sum(row.total_exec_time for row in read_after),
            ),
        },
        "write_totals": {
            "calls": _metric_block(sum(row.calls for row in write_before), sum(row.calls for row in write_after)),
            "total_exec_time": _metric_block(
                sum(row.total_exec_time for row in write_before),
                sum(row.total_exec_time for row in write_after),
            ),
        },
        "by_operation": operation_totals,
        "top_by_operation": top_by_operation,
        "counts": {
            "before": len(before_map),
            "after": len(after_map),
            "added": sum(1 for entry in entries if entry["state"] == "added"),
            "removed": sum(1 for entry in entries if entry["state"] == "removed"),
        },
        "top_regressions": regressions,
        "top_improvements": merged_improvements,
    }


def _summarize_tables(snapshot_a, snapshot_b, top):
    before_map = {_table_key(row): row for row in snapshot_a.table_stats.all()}
    after_map = {_table_key(row): row for row in snapshot_b.table_stats.all()}
    entries = [_table_entry(before_map.get(key), after_map.get(key)) for key in sorted(set(before_map) | set(after_map))]

    return {
        "totals": {
            "before": {
                "seq_scan": sum(row.seq_scan for row in before_map.values()),
                "idx_scan": sum(row.idx_scan for row in before_map.values()),
                "seq_tup_read": sum(row.seq_tup_read for row in before_map.values()),
                "idx_tup_fetch": sum(row.idx_tup_fetch for row in before_map.values()),
                "n_live_tup": sum(row.n_live_tup for row in before_map.values()),
                "n_dead_tup": sum(row.n_dead_tup for row in before_map.values()),
                "table_size_bytes": sum(row.table_size_bytes for row in before_map.values()),
            },
            "after": {
                "seq_scan": sum(row.seq_scan for row in after_map.values()),
                "idx_scan": sum(row.idx_scan for row in after_map.values()),
                "seq_tup_read": sum(row.seq_tup_read for row in after_map.values()),
                "idx_tup_fetch": sum(row.idx_tup_fetch for row in after_map.values()),
                "n_live_tup": sum(row.n_live_tup for row in after_map.values()),
                "n_dead_tup": sum(row.n_dead_tup for row in after_map.values()),
                "table_size_bytes": sum(row.table_size_bytes for row in after_map.values()),
            },
        },
        "counts": {
            "before": len(before_map),
            "after": len(after_map),
        },
        "top_seq_scan_increases": sorted(entries, key=lambda item: item["seq_scan"]["delta"], reverse=True)[:top],
        "top_seq_scan_decreases": sorted(entries, key=lambda item: item["seq_scan"]["delta"])[:top],
    }


def _summarize_indexes(snapshot_a, snapshot_b, top):
    before_map = {_index_key(row): row for row in snapshot_a.index_stats.all()}
    after_map = {_index_key(row): row for row in snapshot_b.index_stats.all()}
    entries = [_index_entry(before_map.get(key), after_map.get(key)) for key in sorted(set(before_map) | set(after_map))]

    return {
        "totals": {
            "before": {
                "idx_scan": sum(row.idx_scan for row in before_map.values()),
                "idx_tup_read": sum(row.idx_tup_read for row in before_map.values()),
                "idx_tup_fetch": sum(row.idx_tup_fetch for row in before_map.values()),
                "index_size_bytes": sum(row.index_size_bytes for row in before_map.values()),
            },
            "after": {
                "idx_scan": sum(row.idx_scan for row in after_map.values()),
                "idx_tup_read": sum(row.idx_tup_read for row in after_map.values()),
                "idx_tup_fetch": sum(row.idx_tup_fetch for row in after_map.values()),
                "index_size_bytes": sum(row.index_size_bytes for row in after_map.values()),
            },
        },
        "counts": {
            "before": len(before_map),
            "after": len(after_map),
        },
        "top_usage_increases": sorted(entries, key=lambda item: item["idx_scan"]["delta"], reverse=True)[:top],
        "top_usage_decreases": sorted(entries, key=lambda item: item["idx_scan"]["delta"])[:top],
    }


def _summarize_findings(snapshot_a, snapshot_b):
    before_findings = list(snapshot_a.findings.all())
    after_findings = list(snapshot_b.findings.all())
    before_by_type = Counter(finding.type for finding in before_findings)
    after_by_type = Counter(finding.type for finding in after_findings)
    before_by_severity = Counter(finding.severity for finding in before_findings)
    after_by_severity = Counter(finding.severity for finding in after_findings)

    before_keys = {_finding_key(finding): finding for finding in before_findings}
    after_keys = {_finding_key(finding): finding for finding in after_findings}

    resolved = [
        {
            "type": before_keys[key].type,
            "severity": before_keys[key].severity,
            "title": before_keys[key].title,
            "object_name": before_keys[key].object_name,
            "display_name": before_keys[key].evidence_json.get("query_preview")
            or before_keys[key].object_name
            or before_keys[key].title,
        }
        for key in sorted(set(before_keys) - set(after_keys))
    ]
    new = [
        {
            "type": after_keys[key].type,
            "severity": after_keys[key].severity,
            "title": after_keys[key].title,
            "object_name": after_keys[key].object_name,
            "display_name": after_keys[key].evidence_json.get("query_preview")
            or after_keys[key].object_name
            or after_keys[key].title,
        }
        for key in sorted(set(after_keys) - set(before_keys))
    ]

    by_type = {}
    for finding_type in sorted(set(before_by_type) | set(after_by_type)):
        by_type[finding_type] = _metric_block(before_by_type[finding_type], after_by_type[finding_type])

    by_severity = {}
    for severity in sorted(set(before_by_severity) | set(after_by_severity)):
        by_severity[severity] = _metric_block(before_by_severity[severity], after_by_severity[severity])

    return {
        "totals": _metric_block(len(before_findings), len(after_findings)),
        "by_type": by_type,
        "by_severity": by_severity,
        "resolved": resolved,
        "new": new,
    }


def compare_snapshots(snapshot_a, snapshot_b, top=5):
    if isinstance(snapshot_a, int):
        snapshot_a = StatsSnapshot.objects.get(id=snapshot_a)
    if isinstance(snapshot_b, int):
        snapshot_b = StatsSnapshot.objects.get(id=snapshot_b)

    top = max(int(top), 1)
    snapshot_a = StatsSnapshot.objects.prefetch_related("query_stats", "table_stats", "index_stats", "findings").get(
        id=snapshot_a.id
    )
    snapshot_b = StatsSnapshot.objects.prefetch_related("query_stats", "table_stats", "index_stats", "findings").get(
        id=snapshot_b.id
    )

    return {
        "snapshot_a": _snapshot_descriptor(snapshot_a),
        "snapshot_b": _snapshot_descriptor(snapshot_b),
        "index_experiment": _summarize_index_experiment(snapshot_a, snapshot_b),
        "queries": _summarize_queries(snapshot_a, snapshot_b, top),
        "tables": _summarize_tables(snapshot_a, snapshot_b, top),
        "indexes": _summarize_indexes(snapshot_a, snapshot_b, top),
        "findings": _summarize_findings(snapshot_a, snapshot_b),
    }
