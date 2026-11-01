"""Metrics calculated from persisted AURA execution records."""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Iterable


def evaluate_runs(records: Iterable[dict]) -> dict:
    runs = list(records)
    total = len(runs)
    completed = sum(record.get("status") == "completed" for record in runs)
    partial = sum(record.get("status") == "partial" for record in runs)
    failed = sum(record.get("status") == "failed" for record in runs)
    task_counts = [record.get("tasks_completed", 0) for record in runs]
    verified_counts = [record.get("verification_events", 0) for record in runs]
    recovery_counts = [
        sum(event.get("event_type") == "recovery_started" for event in record.get("events", []))
        for record in runs
    ]

    planner_runs = defaultdict(list)
    for record in runs:
        planner_runs[record.get("planner", "unknown")].append(record)

    planner_comparison = {}
    for planner, planner_records in planner_runs.items():
        planner_comparison[planner] = {
            "runs": len(planner_records),
            "partial_runs": sum(record.get("status") == "partial" for record in planner_records),
            "success_rate": sum(
                record.get("status") == "completed" for record in planner_records
            ) / len(planner_records),
        }

    return {
        "total_runs": total,
        "completed_runs": completed,
        "partial_runs": partial,
        "failed_runs": failed,
        "success_rate": completed / total if total else 0.0,
        "recovery_rate": sum(count > 0 for count in recovery_counts) / total if total else 0.0,
        "average_tasks_completed": mean(task_counts) if task_counts else 0.0,
        "verification_coverage": (
            sum(verified_counts) / sum(task_counts) if sum(task_counts) else 0.0
        ),
        "failure_categories": dict(Counter(
            event.get("event_type", "unknown")
            for record in runs
            for event in record.get("events", [])
            if event.get("event_type") in {"task_failed", "task_skipped"}
        )),
        "planner_comparison": planner_comparison,
    }
