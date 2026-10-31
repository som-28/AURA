"""Unit tests for TaskGraph dependency resolution and execution tiers."""
import pytest
from src.agent.models import PlanStep
from src.agent.task_graph import TaskGraph


def test_linear_task_graph():
    steps = [
        PlanStep(id=1, tool="search", dependencies=[]),
        PlanStep(id=2, tool="scrape", dependencies=[1]),
        PlanStep(id=3, tool="summarize", dependencies=[2]),
    ]
    graph = TaskGraph(steps)
    ordered = [step.id for step in graph.ordered_steps()]
    assert ordered == [1, 2, 3]

    tiers = graph.execution_tiers()
    assert len(tiers) == 3
    assert [s.id for s in tiers[0]] == [1]
    assert [s.id for s in tiers[1]] == [2]
    assert [s.id for s in tiers[2]] == [3]


def test_concurrent_execution_tiers():
    # 1 -> [2, 3] -> 4
    steps = [
        PlanStep(id=1, tool="search", dependencies=[]),
        PlanStep(id=2, tool="scrape", dependencies=[1]),
        PlanStep(id=3, tool="logger", dependencies=[1]),
        PlanStep(id=4, tool="summarize", dependencies=[2, 3]),
    ]
    graph = TaskGraph(steps)
    tiers = graph.execution_tiers()
    assert len(tiers) == 3
    assert [s.id for s in tiers[0]] == [1]
    # Tier 1 should contain both 2 and 3 ready to run in parallel
    tier_1_ids = sorted([s.id for s in tiers[1]])
    assert tier_1_ids == [2, 3]
    assert [s.id for s in tiers[2]] == [4]


def test_cycle_detection():
    # 1 -> 2 -> 3 -> 1
    steps = [
        PlanStep(id=1, tool="search", dependencies=[3]),
        PlanStep(id=2, tool="scrape", dependencies=[1]),
        PlanStep(id=3, tool="summarize", dependencies=[2]),
    ]
    with pytest.raises(ValueError, match="cycle"):
        TaskGraph(steps)


def test_self_cycle():
    steps = [PlanStep(id=1, tool="search", dependencies=[1])]
    with pytest.raises(ValueError, match="cycle"):
        TaskGraph(steps)


def test_unresolvable_dependency():
    steps = [
        PlanStep(id=1, tool="search", dependencies=[99]),
    ]
    graph = TaskGraph(steps)
    with pytest.raises(ValueError, match="cannot resolve"):
        graph.execution_tiers()
