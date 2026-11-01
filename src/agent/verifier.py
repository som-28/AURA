"""Deterministic, tool-specific output verification."""
from __future__ import annotations

from typing import Any, List

from src.agent.models import VerificationResult


def verify_tool_output(tool_name: str, output: Any) -> VerificationResult:
    if not isinstance(output, dict):
        return VerificationResult(
            verified=False,
            confidence=0.0,
            issues=["Tool output is not a mapping"],
        )

    if output.get("error"):
        return VerificationResult(
            verified=False,
            confidence=0.0,
            issues=[str(output["error"])],
        )

    if tool_name == "search":
        if output.get("search_available") is False:
            return VerificationResult(
                verified=False,
                confidence=0.0,
                issues=[output.get("message") or "Live search is unavailable"],
            )
        return _verify_items(output.get("results"), "Search returned no results", ("title", "url"))
    if tool_name == "scrape":
        return _verify_items(output.get("pages"), "Scraper returned no pages", ("url", "text"))
    if tool_name == "job_matcher":
        return _verify_items(
            output.get("job_matches"),
            "Job matcher returned no jobs",
            ("title", "url"),
        )
    if tool_name == "resume_analyzer":
        analysis = output.get("analysis")
        if isinstance(analysis, dict):
            return VerificationResult(verified=True, confidence=0.9, evidence=["analysis"])
        return VerificationResult(
            verified=False,
            confidence=0.0,
            issues=["Resume analysis is missing"],
        )

    return VerificationResult(verified=True, confidence=0.8, evidence=["structured output"])


def _verify_items(output: Any, empty_issue: str, required_fields: tuple[str, ...]) -> VerificationResult:
    if not isinstance(output, list) or not output:
        return VerificationResult(verified=False, confidence=0.0, issues=[empty_issue])

    issues: List[str] = []
    for index, item in enumerate(output):
        if not isinstance(item, dict):
            issues.append(f"Item {index + 1} is not an object")
            continue
        for field in required_fields:
            if not item.get(field):
                issues.append(f"Item {index + 1} is missing {field}")

    if issues:
        return VerificationResult(verified=False, confidence=0.3, issues=issues)
    return VerificationResult(
        verified=True,
        confidence=0.95,
        evidence=[f"{len(output)} valid items"],
    )
