"""Unit tests for atomic RunStore execution records."""
import tempfile
from pathlib import Path
from src.agent.run_store import RunStore


def test_run_store_save_and_get():
    with tempfile.TemporaryDirectory() as temp_dir:
        store_path = Path(temp_dir) / "test_runs.json"
        store = RunStore(str(store_path))

        assert store.list() == []
        assert store.get("non-existent") is None

        record = {
            "run_id": "run-123",
            "goal": "Test goal",
            "status": "completed",
            "created_at": "2026-10-31T20:00:00Z",
        }
        store.save(record)

        fetched = store.get("run-123")
        assert fetched is not None
        assert fetched["goal"] == "Test goal"
        assert fetched["status"] == "completed"

        runs = store.list()
        assert len(runs) == 1
        assert runs[0]["run_id"] == "run-123"


def test_run_store_metrics():
    with tempfile.TemporaryDirectory() as temp_dir:
        store_path = Path(temp_dir) / "test_runs.json"
        store = RunStore(str(store_path))

        store.save({"run_id": "1", "status": "completed", "created_at": "2026-01-01T00:00:00Z"})
        store.save({"run_id": "2", "status": "completed", "created_at": "2026-01-02T00:00:00Z"})
        store.save({"run_id": "3", "status": "failed", "created_at": "2026-01-03T00:00:00Z"})

        metrics = store.metrics()
        assert metrics["total_runs"] == 3
        assert metrics["completed_runs"] == 2
        assert metrics["failed_runs"] == 1
        assert abs(metrics["success_rate"] - (2 / 3)) < 0.001
