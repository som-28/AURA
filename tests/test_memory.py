"""Unit tests for atomic persistent Memory manager."""
import tempfile
from pathlib import Path
from src.agent.memory import Memory


def test_memory_preferences_and_context():
    with tempfile.TemporaryDirectory() as temp_dir:
        mem_path = Path(temp_dir) / "test_memory.json"
        mem = Memory(str(mem_path))

        # Check default state
        assert mem.get_preferences() == {}
        assert mem.get("missing", default="default_val") == "default_val"

        # Preferences
        mem.set_preference("email", "dev@example.com")
        assert mem.get_preference("email") == "dev@example.com"
        assert mem.get_preferences() == {"email": "dev@example.com"}

        # Context
        mem.set("last_query", "remote python jobs")
        assert mem.get("last_query") == "remote python jobs"


def test_memory_recent_runs_and_clear():
    with tempfile.TemporaryDirectory() as temp_dir:
        mem_path = Path(temp_dir) / "test_memory.json"
        mem = Memory(str(mem_path))

        mem.record_run("run-1", "Goal 1", "completed")
        mem.record_run("run-2", "Goal 2", "failed")

        recent = mem.get_recent_runs(limit=10)
        assert len(recent) == 2
        assert recent[0]["run_id"] == "run-2"  # Latest first
        assert recent[1]["run_id"] == "run-1"

        mem.clear()
        assert mem.get_recent_runs() == []
        assert mem.get_preferences() == {}
