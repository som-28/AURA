"""Unit tests for run evaluator metrics calculation."""
from src.agent.evaluator import evaluate_runs


def test_evaluate_empty_runs():
    res = evaluate_runs([])
    assert res["total_runs"] == 0
    assert res["success_rate"] == 0.0
    assert res["average_tasks_completed"] == 0.0


def test_evaluate_runs_metrics():
    records = [
        {
            "run_id": "1",
            "status": "completed",
            "planner": "rule",
            "tasks_completed": 3,
            "verification_events": 3,
            "events": [
                {"event_type": "task_completed"},
                {"event_type": "task_completed"},
                {"event_type": "task_completed"},
            ],
        },
        {
            "run_id": "2",
            "status": "completed",
            "planner": "llm",
            "tasks_completed": 2,
            "verification_events": 2,
            "events": [
                {"event_type": "task_started"},
                {"event_type": "recovery_started"},
                {"event_type": "task_completed"},
            ],
        },
        {
            "run_id": "3",
            "status": "failed",
            "planner": "rule",
            "tasks_completed": 1,
            "verification_events": 1,
            "events": [
                {"event_type": "task_failed"},
            ],
        },
    ]

    ev = evaluate_runs(records)
    assert ev["total_runs"] == 3
    assert ev["completed_runs"] == 2
    assert ev["failed_runs"] == 1
    assert abs(ev["success_rate"] - (2 / 3)) < 0.001
    assert abs(ev["recovery_rate"] - (1 / 3)) < 0.001
    assert ev["average_tasks_completed"] == 2.0
    assert "rule" in ev["planner_comparison"]
    assert "llm" in ev["planner_comparison"]
    assert ev["failure_categories"].get("task_failed") == 1
