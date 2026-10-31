"""Planner: convert natural language tasks into a JSON execution plan.

This planner is rule-based for offline deterministic use. If an OpenAI key
is provided, LLMPlanner can optionally be used instead.
"""
from __future__ import annotations
import re
from typing import Optional
from src.utils.config import load_config
from src.agent.memory import Memory


class Planner:
    def __init__(self, cfg=None, memory: Optional[Memory] = None):
        self.cfg = cfg or load_config()
        self.memory = memory or Memory()

    def plan(self, command: str, target_email: str | None = None) -> dict:
        """Produce a JSON plan with ordered steps and explicit dependencies."""
        cmd = command.lower()
        steps = []
        sid = 1
        last_step_id = None

        # Resolve email: explicit arg > memory preference > empty
        resolved_email = (
            target_email
            or self.memory.get_preference("default_email")
            or self.memory.get_preference("email")
            or ""
        )

        # 1. detect 'search' intent
        if any(k in cmd for k in ["find", "search", "look for", "top", "list"]):
            q = self._extract_search_query(command)
            steps.append({
                "id": sid,
                "tool": "search",
                "args": {"query": q, "limit": 5},
                "dependencies": [],
            })
            last_step_id = sid
            sid += 1

        # 2. detect 'scrape' intent
        if any(k in cmd for k in ["scrape", "details", "summarize", "summary", "compare"]) or "internship" in cmd or "course" in cmd:
            deps = [last_step_id] if last_step_id else []
            steps.append({
                "id": sid,
                "tool": "scrape",
                "args": {"top_k": 3},
                "dependencies": deps,
            })
            last_step_id = sid
            sid += 1

        # 3. detect summarization
        if any(k in cmd for k in ["summarize", "summary", "bullet", "compare", "comparison"]):
            deps = [last_step_id] if last_step_id else []
            steps.append({
                "id": sid,
                "tool": "summarize",
                "args": {"mode": "bullet", "max_sentences": 8},
                "dependencies": deps,
            })
            last_step_id = sid
            sid += 1

        # 4. email
        if resolved_email or "email" in cmd or "send" in cmd:
            deps = [last_step_id] if last_step_id else []
            steps.append({
                "id": sid,
                "tool": "email",
                "args": {
                    "to": resolved_email,
                    "subject": f"Automation result for: {command}",
                },
                "dependencies": deps,
            })
            last_step_id = sid
            sid += 1

        # 5. always log completion
        deps = [last_step_id] if last_step_id else []
        steps.append({
            "id": sid,
            "tool": "logger",
            "args": {"message": f"Completed task: {command}"},
            "dependencies": deps,
        })

        plan = {"input": command, "steps": steps}
        return plan

    def _extract_search_query(self, command: str) -> str:
        patterns = [r"find me (.+)", r"search for (.+)", r"look for (.+)", r"find (.+)"]
        for p in patterns:
            m = re.search(p, command, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return command.strip()
