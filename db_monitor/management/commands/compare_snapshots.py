import json

from django.core.management.base import BaseCommand, CommandError

from db_monitor.models import StatsSnapshot
from db_monitor.services.comparison import compare_snapshots


class Command(BaseCommand):
    help = "Compare two stored statistics snapshots and print before/after deltas."

    def add_arguments(self, parser):
        parser.add_argument("snapshot_a")
        parser.add_argument("snapshot_b")
        parser.add_argument("--top", type=int, default=5)
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        snapshot_a = self._resolve_snapshot(options["snapshot_a"])
        snapshot_b = self._resolve_snapshot(options["snapshot_b"])
        summary = compare_snapshots(snapshot_a, snapshot_b, top=options["top"])

        if options["format"] == "json":
            self.stdout.write(json.dumps(summary, indent=2))
            return

        self._write_text(summary, options["top"])

    def _resolve_snapshot(self, reference):
        if str(reference).isdigit():
            snapshot = StatsSnapshot.objects.filter(id=int(reference)).first()
        else:
            snapshot = StatsSnapshot.objects.filter(label=reference).order_by("-created_at").first()

        if snapshot is None:
            raise CommandError(f"Snapshot `{reference}` was not found.")
        return snapshot

    def _write_text(self, summary, top):
        snapshot_a = summary["snapshot_a"]
        snapshot_b = summary["snapshot_b"]
        findings = summary["findings"]
        queries = summary["queries"]
        tables = summary["tables"]
        indexes = summary["indexes"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Comparing snapshot #{snapshot_a['id']} ({snapshot_a['label'] or 'no-label'}) "
                f"-> #{snapshot_b['id']} ({snapshot_b['label'] or 'no-label'})"
            )
        )
        self.stdout.write(
            f"Statuses: {snapshot_a['status']} -> {snapshot_b['status']} | "
            f"environment: {snapshot_a['environment'] or '-'} -> {snapshot_b['environment'] or '-'}"
        )
        self.stdout.write(
            f"Findings: {findings['totals']['before']} -> {findings['totals']['after']} "
            f"(delta {findings['totals']['delta']:+d})"
        )
        for finding_type, metrics in findings["by_type"].items():
            self.stdout.write(
                f"- finding `{finding_type}`: {metrics['before']} -> {metrics['after']} (delta {metrics['delta']:+d})"
            )

        self.stdout.write(
            f"Query totals: calls {queries['totals']['before']['calls']} -> {queries['totals']['after']['calls']}, "
            f"total_exec_time {queries['totals']['before']['total_exec_time']:.2f} -> "
            f"{queries['totals']['after']['total_exec_time']:.2f} ms"
        )
        self.stdout.write(
            f"Read workload total_exec_time: {queries['read_totals']['total_exec_time']['before']:.2f} -> "
            f"{queries['read_totals']['total_exec_time']['after']:.2f} ms | "
            f"Write workload total_exec_time: {queries['write_totals']['total_exec_time']['before']:.2f} -> "
            f"{queries['write_totals']['total_exec_time']['after']:.2f} ms"
        )
        for operation in ["SELECT", "INSERT", "UPDATE", "DELETE"]:
            metrics = queries["by_operation"].get(operation)
            if not metrics:
                continue
            self.stdout.write(
                f"- {operation}: calls {metrics['calls']['before']} -> {metrics['calls']['after']}, "
                f"total_exec_time {metrics['total_exec_time']['before']:.2f} -> "
                f"{metrics['total_exec_time']['after']:.2f} ms"
            )
        self._write_query_section("Top query regressions", queries["top_regressions"], top)
        self._write_query_section("Top query improvements", queries["top_improvements"], top)
        for operation in ["SELECT", "INSERT", "UPDATE", "DELETE"]:
            self._write_query_section(f"Top {operation} queries after snapshot", queries["top_by_operation"][operation], top)

        self.stdout.write(
            f"Table totals: seq_scan {tables['totals']['before']['seq_scan']} -> "
            f"{tables['totals']['after']['seq_scan']}, idx_scan {tables['totals']['before']['idx_scan']} -> "
            f"{tables['totals']['after']['idx_scan']}"
        )
        self._write_table_section("Top seq-scan increases", tables["top_seq_scan_increases"], top)
        self._write_table_section("Top seq-scan decreases", tables["top_seq_scan_decreases"], top)

        self.stdout.write(
            f"Index totals: idx_scan {indexes['totals']['before']['idx_scan']} -> "
            f"{indexes['totals']['after']['idx_scan']}"
        )
        self._write_index_section("Top index usage increases", indexes["top_usage_increases"], top)
        self._write_index_section("Top index usage decreases", indexes["top_usage_decreases"], top)

        if findings["resolved"]:
            self.stdout.write("Resolved findings:")
            for finding in findings["resolved"][:top]:
                self.stdout.write(
                    f"- {finding['type']} [{finding['severity']}] {finding['object_name'] or finding['title']}"
                )
        if findings["new"]:
            self.stdout.write("New findings:")
            for finding in findings["new"][:top]:
                self.stdout.write(
                    f"- {finding['type']} [{finding['severity']}] {finding['object_name'] or finding['title']}"
                )

    def _write_query_section(self, title, entries, top):
        self.stdout.write(f"{title} (top {top}):")
        if not entries:
            self.stdout.write("- none")
            return
        for entry in entries:
            self.stdout.write(
                "- "
                f"[{entry.get('operation_type', 'UNKNOWN')}] {entry['queryid'] or entry['query_preview']} | "
                f"total_exec_time {entry['total_exec_time']['before']:.2f} -> {entry['total_exec_time']['after']:.2f} "
                f"(delta {entry['total_exec_time']['delta']:+.2f}) | "
                f"mean_exec_time {entry['mean_exec_time']['before']:.2f} -> {entry['mean_exec_time']['after']:.2f} "
                f"(delta {entry['mean_exec_time']['delta']:+.2f}) | "
                f"calls {entry['calls']['before']} -> {entry['calls']['after']}"
            )

    def _write_table_section(self, title, entries, top):
        self.stdout.write(f"{title} (top {top}):")
        if not entries:
            self.stdout.write("- none")
            return
        for entry in entries:
            self.stdout.write(
                "- "
                f"{entry['table']} | "
                f"seq_scan {entry['seq_scan']['before']} -> {entry['seq_scan']['after']} "
                f"(delta {entry['seq_scan']['delta']:+d}) | "
                f"idx_scan {entry['idx_scan']['before']} -> {entry['idx_scan']['after']} "
                f"(delta {entry['idx_scan']['delta']:+d})"
            )

    def _write_index_section(self, title, entries, top):
        self.stdout.write(f"{title} (top {top}):")
        if not entries:
            self.stdout.write("- none")
            return
        for entry in entries:
            self.stdout.write(
                "- "
                f"{entry['index']} | "
                f"idx_scan {entry['idx_scan']['before']} -> {entry['idx_scan']['after']} "
                f"(delta {entry['idx_scan']['delta']:+d})"
            )
