from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from db_monitor.services import get_comparison_report, get_dashboard_overview, get_snapshot_report


SNAPSHOT_SECTIONS = {
    "queries": "queries",
    "tables": "tables",
    "indexes": "indexes",
    "activity": "activities",
    "findings": "findings",
}


@require_GET
def overview(request):
    context = get_dashboard_overview(limit=5)
    return render(request, "db_monitor/overview.html", context)


@require_GET
def snapshot_overview(request, snapshot_id):
    context = get_snapshot_report(snapshot_id)
    return render(request, "db_monitor/snapshot_overview.html", context)


@require_GET
def snapshot_section(request, snapshot_id, section):
    if section not in SNAPSHOT_SECTIONS:
        raise Http404("Unknown reporting section")

    context = get_snapshot_report(snapshot_id)
    context["active_section"] = section
    context["section_key"] = SNAPSHOT_SECTIONS[section]
    return render(request, "db_monitor/snapshot_section.html", context)


@require_GET
def compare_view(request):
    snapshot_a = request.GET.get("snapshot_a")
    snapshot_b = request.GET.get("snapshot_b")
    if not snapshot_a or not snapshot_b:
        overview_context = get_dashboard_overview(limit=5)
        if overview_context["comparison"]:
            summary = overview_context["comparison"]["summary"]
            return redirect(
                f"{request.path}?snapshot_a={summary['snapshot_a']['id']}&snapshot_b={summary['snapshot_b']['id']}"
            )

        return render(
            request,
            "db_monitor/compare.html",
            {
                "summary": None,
                "snapshot_options": overview_context["snapshot_options"],
                "snapshot_a": None,
                "snapshot_b": None,
            },
        )

    context = get_comparison_report(snapshot_a, snapshot_b, top=10)
    return render(request, "db_monitor/compare.html", context)
