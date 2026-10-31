"""LLM-based planner using OpenAI to decompose complex tasks.

Falls back to rule-based planning if no OpenAI key is configured.
"""
from __future__ import annotations
import os
import json
from typing import Optional
from src.utils.config import load_config
from src.agent.memory import Memory

# Import the rule-based planner logic
from src.agent.planner import Planner as RulePlanner


class LLMPlanner:
    def __init__(self, cfg=None, memory: Optional[Memory] = None):
        self.cfg = cfg or load_config()
        self.memory = memory or Memory()
        self.rule_planner = RulePlanner(self.cfg, memory=self.memory)

    def plan(self, command: str, target_email: str | None = None) -> dict:
        """Generate plan using LLM if available, else rule-based."""
        planner_mode = os.getenv("PLANNER_MODE", "rule")

        resolved_email = (
            target_email
            or self.memory.get_preference("default_email")
            or self.memory.get_preference("email")
            or None
        )

        if planner_mode == "llm" and os.getenv("OPENAI_API_KEY"):
            return self._plan_with_llm(command, resolved_email)
        else:
            return self.rule_planner.plan(command, resolved_email)

    def _plan_with_llm(self, command: str, target_email: str | None = None) -> dict:
        """Use OpenAI to generate a detailed execution plan."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            system_prompt = """You are a task planning agent. Given a user command, break it down into ordered steps using these tools:

Available tools:
- search: Search the web for information. Args: {"query": str, "limit": int}
- scrape: Scrape web pages for details. Args: {"top_k": int} or {"url": str}
- summarize: Summarize gathered information. Args: {"mode": "bullet"|"comparison", "max_sentences": int}
- email: Send email with results. Args: {"to": str, "subject": str, "body": str (optional)}
- logger: Log completion message. Args: {"message": str}

Return ONLY a valid JSON object with this structure:
{
  "input": "<original command>",
  "steps": [
    {"id": 1, "tool": "search", "args": {...}, "dependencies": []},
    {"id": 2, "tool": "scrape", "args": {...}, "dependencies": [1]},
    ...
  ]
}

Be specific with queries and arguments. Do not include markdown formatting or explanations."""

            user_prompt = f"Command: {command}"
            if target_email:
                user_prompt += f"\nTarget email: {target_email}"

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800,
            )

            content = response.choices[0].message.content.strip()

            # Extract JSON from potential markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            plan = json.loads(content)

            # Ensure plan has required structure
            if "input" not in plan:
                plan["input"] = command
            if "steps" not in plan or not isinstance(plan["steps"], list):
                raise ValueError("Invalid plan structure")

            # Ensure each step has dependencies key
            prev_id = None
            for s in plan["steps"]:
                if "dependencies" not in s:
                    s["dependencies"] = [prev_id] if prev_id is not None else []
                prev_id = s.get("id")

            # Add target email if provided and not already in plan
            if target_email:
                has_email_step = any(s.get("tool") == "email" for s in plan["steps"])
                if has_email_step:
                    for step in plan["steps"]:
                        if step.get("tool") == "email" and "to" in step.get("args", {}):
                            if not step["args"]["to"]:
                                step["args"]["to"] = target_email

            return plan

        except Exception as e:
            print(f"LLM planning failed: {e}, falling back to rule-based planner")
            return self.rule_planner.plan(command, target_email)
