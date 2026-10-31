"""Unit tests for Controller execution, topological concurrency, and recovery."""
import pytest
import tempfile
from pathlib import Path
from src.agent.controller import Controller
from src.agent.memory import Memory


@pytest.mark.asyncio
async def test_controller_successful_execution():
    with tempfile.TemporaryDirectory() as td:
        mem = Memory(str(Path(td) / "mem.json"))
        controller = Controller(memory=mem)

        plan = {
            "input": "Search and log",
            "steps": [
                {"id": 1, "tool": "search", "args": {"query": "python"}, "dependencies": []},
                {"id": 2, "tool": "logger", "args": {"message": "done"}, "dependencies": [1]},
            ],
        }

        logs = await controller.execute_plan(plan, run_id="run-test-1")
        assert len(logs) > 0
        events = controller.get_events()
        event_types = [e.event_type for e in events]

        assert "plan_started" in event_types
        assert "task_started" in event_types
        assert "task_verified" in event_types
        assert "task_completed" in event_types
        assert "plan_completed" in event_types

        # Verify run was recorded in memory
        recent = mem.get_recent_runs()
        assert len(recent) == 1
        assert recent[0]["run_id"] == "run-test-1"
        assert recent[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_controller_concurrent_tiers():
    with tempfile.TemporaryDirectory() as td:
        mem = Memory(str(Path(td) / "mem.json"))
        controller = Controller(memory=mem)

        # Step 1 and Step 2 run in parallel in Tier 0, then Step 3 runs in Tier 1
        plan = {
            "input": "Parallel tasks",
            "steps": [
                {"id": 1, "tool": "logger", "args": {"message": "task 1"}, "dependencies": []},
                {"id": 2, "tool": "logger", "args": {"message": "task 2"}, "dependencies": []},
                {"id": 3, "tool": "logger", "args": {"message": "task 3"}, "dependencies": [1, 2]},
            ],
        }

        logs = await controller.execute_plan(plan)
        assert len(logs) > 0
        events = controller.get_events()
        completed_tasks = [e.task_id for e in events if e.event_type == "task_completed"]
        assert set(completed_tasks) == {"1", "2", "3"}


@pytest.mark.asyncio
async def test_controller_dependency_skipping():
    with tempfile.TemporaryDirectory() as td:
        mem = Memory(str(Path(td) / "mem.json"))
        controller = Controller(memory=mem)

        # Tool that fails verification or execution
        plan = {
            "input": "Failure test",
            "steps": [
                # Search with empty query or invalid output
                {"id": 1, "tool": "scrape", "args": {"url": "http://invalid-url-that-fails-999.xyz"}, "dependencies": []},
                {"id": 2, "tool": "logger", "args": {"message": "should be skipped"}, "dependencies": [1]},
            ],
        }

        logs = await controller.execute_plan(plan)
        events = controller.get_events()
        event_types = [e.event_type for e in events]
        assert "task_skipped" in event_types
