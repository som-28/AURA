"""LLM-based planner with local Ollama and optional hosted OpenAI support."""
from __future__ import annotations
import os
import json
from typing import Optional
from src.utils.config import load_config
from src.agent.memory import Memory
from src.utils.llm_client import get_llm_client

# Import the rule-based planner logic
from src.agent.planner import Planner as RulePlanner
from src.utils.email_utils import usable_recipient


class LLMPlanner:
    def __init__(self, cfg=None, memory: Optional[Memory] = None):
        self.cfg = cfg or load_config()
        self.memory = memory or Memory()
        self.rule_planner = RulePlanner(self.cfg, memory=self.memory)

    def plan(self, command: str, target_email: str | None = None) -> dict:
        """Generate plan using LLM if available, else rule-based."""
        planner_mode = os.getenv("PLANNER_MODE", "rule")

        if target_email:
            resolved_email = usable_recipient(target_email)
        else:
            resolved_email = (
                usable_recipient(self.memory.get_preference("default_email"))
                or usable_recipient(self.memory.get_preference("email"))
            )

        if planner_mode == "llm":
            return self._plan_with_llm(command, resolved_email)
        else:
            return self.rule_planner.plan(command, resolved_email)

    def _plan_with_llm(self, command: str, target_email: str | None = None) -> dict:
        """Use the configured LLM to generate a detailed execution plan."""
        try:
            configured = get_llm_client()
            if configured is None:
                raise RuntimeError("No LLM is configured; set LLM_PROVIDER=ollama or add OPENAI_API_KEY")
            client, model, _provider_name = configured

            system_prompt = """You are a task planning agent. Given a user command, break it down into ordered steps using these tools:

Available tools:
- search: Search the web for information. Args: {"query": str, "limit": int}
- scrape: Scrape web pages for details. Args: {"top_k": int} or {"url": str}
- summarize: Summarize gathered information. Args: {"mode": "bullet"|"comparison", "max_sentences": int}
- email: Send email with results. Args: {"to": str, "subject": str, "body": str (optional)}
- logger: Log completion message. Args: {"message": str}

Never invent or guess an email address. Only include an email step when a real target email is supplied below. If no target email is supplied, do not include an email step.

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
                model=model,
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

            # The UI's optional email field means: send these results there.
            # Discard model-invented recipients and create exactly one step only
            # when a validated recipient was supplied by the user or memory.
            original_email_ids = {
                str(step.get("id")) for step in plan["steps"]
                if step.get("tool") == "email"
            }
            non_email_steps = [s for s in plan["steps"] if s.get("tool") != "email"]
            for step in non_email_steps:
                step["dependencies"] = [
                    dep for dep in step.get("dependencies", [])
                    if str(dep) not in original_email_ids
                ]
            if target_email:
                logger_steps = [s for s in non_email_steps if s.get("tool") == "logger"]
                work_steps = [s for s in non_email_steps if s.get("tool") != "logger"]
                referenced = {
                    str(dep)
                    for step in work_steps
                    for dep in step.get("dependencies", [])
                }
                terminal_ids = [
                    step.get("id") for step in work_steps
                    if str(step.get("id")) not in referenced
                ]
                numeric_ids = [
                    step.get("id") for step in plan["steps"]
                    if isinstance(step.get("id"), int)
                ]
                email_id = max(numeric_ids, default=0) + 1
                email_step = {
                    "id": email_id,
                    "tool": "email",
                    "args": {
                        "to": target_email,
                        "subject": f"AURA results: {command[:100]}",
                    },
                    "dependencies": terminal_ids,
                }
                for logger_step in logger_steps:
                    logger_step["dependencies"] = [email_id]
                plan["steps"] = work_steps + [email_step] + logger_steps
            else:
                referenced = {
                    str(dep)
                    for step in non_email_steps
                    for dep in step.get("dependencies", [])
                }
                terminal_ids = [
                    step.get("id") for step in non_email_steps
                    if str(step.get("id")) not in referenced
                ]
                for step in non_email_steps:
                    if step.get("tool") == "logger":
                        step["dependencies"] = terminal_ids
                plan["steps"] = non_email_steps

            return plan

        except Exception as e:
            print(f"LLM planning failed: {e}, falling back to rule-based planner")
            return self.rule_planner.plan(command, target_email)
