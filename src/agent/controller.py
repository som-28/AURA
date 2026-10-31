"""Controller: executes a plan with topological concurrency, verification, and recovery.

Supports:
- DAG-based concurrent execution of independent steps within topological tiers
- Dynamic tool invocation with timeout handling
- Deterministic verification and bounded retry recovery
- Long-term memory integration
- Detailed execution event logging
"""
from __future__ import annotations
import asyncio
import importlib
from typing import List, Optional
from src.agent.models import TaskEvent, validate_plan, PlanStep
from src.agent.task_graph import TaskGraph
from src.agent.verifier import verify_tool_output
from src.agent.tool_registry import default_tool_registry
from src.agent.recovery import should_retry
from src.agent.memory import Memory
from src.utils.config import load_config


class Controller:
    def __init__(self, cfg=None, memory: Optional[Memory] = None, use_enhanced=True):
        self.cfg = cfg or load_config()
        self.memory = memory or Memory()
        self.events: List[TaskEvent] = []
        self.registry = default_tool_registry(use_enhanced=use_enhanced)
        self.tool_map = {
            name: self.registry.get(name).module_path
            for name in self.registry.names()
        }

    def get_events(self) -> List[TaskEvent]:
        return list(self.events)

    def _emit_event(self, event_type: str, message: str, task_id=None, **metadata):
        self.events.append(
            TaskEvent(
                event_type=event_type,
                task_id=str(task_id) if task_id is not None else None,
                message=message,
                metadata=metadata,
            )
        )

    async def execute_plan(self, plan: dict, run_id: Optional[str] = None) -> List[str]:
        validated_plan = validate_plan(plan, self.registry)
        task_graph = TaskGraph(validated_plan.steps)
        tiers = task_graph.execution_tiers()

        logs: List[str] = []
        task_status: dict[str, str] = {}
        context = {
            "plan_input": validated_plan.input,
            "preferences": self.memory.get_preferences(),
        }
        self.events = []
        self._emit_event("plan_started", "Plan execution started")

        lock = asyncio.Lock()

        async def _execute_single_step(step: PlanStep) -> None:
            tool_name = step.tool
            args = step.args
            task_id = step.id
            task_key = str(task_id)

            # Check if any dependencies failed or were skipped
            async with lock:
                blocked_by = [
                    str(dependency)
                    for dependency in step.dependencies
                    if task_status.get(str(dependency)) != "COMPLETED"
                ]
                if blocked_by:
                    task_status[task_key] = "SKIPPED"
                    skip_msg = f"Skipped step {task_id} -> {tool_name}: dependency did not complete"
                    logs.append(skip_msg)
                    self._emit_event(
                        "task_skipped",
                        skip_msg,
                        task_id=task_id,
                        tool=tool_name,
                        blocked_by=blocked_by,
                    )
                    return

                start_msg = f"Starting step {task_id} -> {tool_name}"
                logs.append(start_msg)
                self._emit_event(
                    "task_started",
                    f"Started {tool_name}",
                    task_id=task_id,
                    tool=tool_name,
                )

            tool_spec = self.registry.get(tool_name)
            retry_count = 0
            max_retries = tool_spec.max_retries if tool_spec else 1

            while True:
                try:
                    tool_logs, output = await self._invoke_tool(tool_name, args, context)
                    verification = verify_tool_output(tool_name, output)

                    if not verification.verified:
                        issues_str = "; ".join(verification.issues)
                        raise ValueError(f"Verification failed: {issues_str}")

                    async with lock:
                        for line in tool_logs:
                            logs.append(line)

                        self._emit_event(
                            "task_verified",
                            f"Verified {tool_name} output"
                            if retry_count == 0
                            else f"Verified {tool_name} output after retry",
                            task_id=task_id,
                            tool=tool_name,
                            confidence=verification.confidence,
                            evidence=verification.evidence,
                        )

                        if output is not None:
                            context[f"step_{task_id}_output"] = output

                        task_status[task_key] = "COMPLETED"
                        completion_label = "Finished step" if retry_count == 0 else "Finished retry step"
                        logs.append(f"{completion_label} {task_id} -> {tool_name}")
                        self._emit_event(
                            "task_completed",
                            f"Completed {tool_name}" if retry_count == 0 else f"Completed {tool_name} after retry",
                            task_id=task_id,
                            tool=tool_name,
                            retry_count=retry_count,
                        )
                    break

                except Exception as error:
                    failure_message = f"Error in step {task_id} ({tool_name}): {error}"
                    async with lock:
                        logs.append(failure_message)
                        self._emit_event(
                            "task_failed",
                            failure_message,
                            task_id=task_id,
                            tool=tool_name,
                            retry_count=retry_count,
                            error=str(error),
                        )

                    if not should_retry(error, retry_count, max_retries):
                        async with lock:
                            task_status[task_key] = "FAILED"
                        break

                    retry_count += 1
                    retry_msg = f"Retrying step {task_id} -> {tool_name} ({retry_count}/{max_retries})"
                    async with lock:
                        logs.append(retry_msg)
                        self._emit_event(
                            "recovery_started",
                            f"Retrying {tool_name}",
                            task_id=task_id,
                            tool=tool_name,
                            retry_count=retry_count,
                            max_retries=max_retries,
                        )

        # Execute topological tiers with concurrency within each tier
        for tier in tiers:
            if len(tier) == 1:
                await _execute_single_step(tier[0])
            else:
                await asyncio.gather(*(_execute_single_step(step) for step in tier))

        overall_status = "failed" if any(s == "FAILED" for s in task_status.values()) else "completed"
        self._emit_event("plan_completed", f"Plan execution {overall_status}")

        # Record in memory
        if run_id:
            self.memory.record_run(
                run_id=run_id,
                goal=validated_plan.input,
                status=overall_status,
            )

        return logs

    async def _invoke_tool(self, tool_name: str, args: dict, context: dict):
        tool = self.registry.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_name}")
        module_path = tool.module_path

        module = importlib.import_module(module_path)
        if hasattr(module, "run"):
            fn = getattr(module, "run")
            if asyncio.iscoroutinefunction(fn):
                return await fn(args, context)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: fn(args, context))
        elif hasattr(module, "Tool"):
            ToolCls = getattr(module, "Tool")
            inst = ToolCls(self.cfg)
            if asyncio.iscoroutinefunction(inst.run):
                return await inst.run(args, context)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: inst.run(args, context))
        else:
            raise ValueError(f"Tool module {module_path} missing run() or Tool class")
