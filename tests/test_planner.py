"""Unit tests for deterministic and LLM planners."""
from src.agent.planner import Planner
from src.agent.planner_llm import LLMPlanner
from src.agent.memory import Memory
import tempfile
from pathlib import Path


def test_rule_planner_search_scrape_email():
    with tempfile.TemporaryDirectory() as td:
        mem = Memory(str(Path(td) / "mem.json"))
        planner = Planner(memory=mem)

        cmd = "Find top Python jobs and email them to me"
        plan = planner.plan(cmd, target_email="user@example.com")

        assert plan["input"] == cmd
        tools = [step["tool"] for step in plan["steps"]]
        assert "search" in tools
        assert "email" in tools
        assert "logger" in tools

        # Verify dependency chain is properly populated
        for step in plan["steps"]:
            assert "dependencies" in step
            if step["tool"] == "search":
                assert step["dependencies"] == []


def test_rule_planner_memory_preference_email():
    with tempfile.TemporaryDirectory() as td:
        mem = Memory(str(Path(td) / "mem.json"))
        mem.set_preference("default_email", "auto@example.com")
        planner = Planner(memory=mem)

        # User did not provide email in command or arg
        cmd = "Find python jobs and email summary"
        plan = planner.plan(cmd)

        email_step = next(s for s in plan["steps"] if s["tool"] == "email")
        assert email_step["args"]["to"] == "auto@example.com"


def test_llm_planner_fallback_without_api_key():
    with tempfile.TemporaryDirectory() as td:
        mem = Memory(str(Path(td) / "mem.json"))
        llm_planner = LLMPlanner(memory=mem)
        # Should gracefully fall back to rule-based planner when no key is set
        plan = llm_planner.plan("Find remote react jobs")
        assert plan is not None
        assert any(s["tool"] == "search" for s in plan["steps"])
