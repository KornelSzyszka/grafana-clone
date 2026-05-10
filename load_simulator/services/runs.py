import subprocess

from load_simulator.models import WorkloadRun


def get_current_git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def record_workload_run(summary, command_options=None):
    return WorkloadRun.objects.create(
        scenario=summary.get("scenario", ""),
        profile=summary.get("profile", ""),
        seed=summary.get("seed", 42),
        iterations=summary.get("iterations"),
        duration=summary.get("duration", 30),
        concurrency=summary.get("concurrency", 1),
        intensity=summary.get("intensity", 1),
        warmup=summary.get("warmup", 0),
        mutates_data=summary.get("mutates_data", False),
        operations=summary.get("operations", 0),
        duration_seconds=summary.get("duration_seconds", 0),
        breakdown_json=summary.get("breakdown", {}),
        command_options_json=command_options or {},
        git_commit=get_current_git_commit(),
    )


def link_latest_unattached_workload_run(snapshot):
    run = WorkloadRun.objects.filter(snapshot__isnull=True).order_by("-created_at", "-id").first()
    if not run:
        return None
    run.snapshot = snapshot
    run.save(update_fields=["snapshot"])
    return run
