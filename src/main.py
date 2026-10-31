import asyncio
import base64
import binascii
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from src.agent.planner import Planner as RulePlanner
from src.agent.planner_llm import LLMPlanner
from src.agent.controller import Controller
from src.agent.evaluator import evaluate_runs
from src.agent.run_store import RunStore
from src.agent.memory import Memory
from src.utils.config import load_config

app = FastAPI(title="AURA Autonomous Task Agent")

cfg = load_config()
# Shared memory store for preferences and long-term state
memory = Memory()
# Use LLM planner if configured, else rule-based
planner_mode = os.getenv("PLANNER_MODE", "rule")
planner = LLMPlanner(cfg, memory=memory) if planner_mode == "llm" else RulePlanner(cfg, memory=memory)
controller = Controller(cfg, memory=memory)
run_store = RunStore()


class PreferenceRequest(BaseModel):
    key: str
    value: Any


class RunRequest(BaseModel):
    command: Optional[str] = None
    goal: Optional[str] = None
    email: Optional[str] = None
    planner: Optional[str] = None


class ResumeAnalyzeRequest(BaseModel):
    file_name: str
    content_base64: str


class ResumeMatchRequest(BaseModel):
    analysis: dict
    location: str = "remote"
    limit: int = 10


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_events(events) -> list[dict]:
    return [event.model_dump(mode="json") for event in events]


def run_status(events: list[dict]) -> str:
    task_states = {}
    terminal_events = {"task_completed", "task_failed", "task_skipped"}
    for event in events:
        if event.get("task_id") and event.get("event_type") in terminal_events:
            task_states[event["task_id"]] = event["event_type"]
    if any(state == "task_failed" for state in task_states.values()):
        return "failed"
    return "completed"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aura"}


@app.post("/resume/analyze")
async def analyze_resume(req: ResumeAnalyzeRequest):
    extension = Path(req.file_name).suffix.lower()
    if extension not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(status_code=422, detail="Only PDF, DOCX, and TXT files are supported")
    try:
        content = base64.b64decode(req.content_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=422, detail="content_base64 is invalid")
    if not content:
        raise HTTPException(status_code=422, detail="Resume file is empty")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Resume file exceeds the 10MB limit")

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temporary_file:
            temporary_file.write(content)
            temporary_path = temporary_file.name

        from src.tools.resume_analyzer_tool import run as analyze_tool
        from src.tools.resume_parser_tool import run as parse_tool

        parse_logs, parsed = await asyncio.to_thread(
            parse_tool, {"file_path": temporary_path}, {}
        )
        if parsed.get("error"):
            raise HTTPException(status_code=422, detail=parsed["error"])
        analyze_logs, analyzed = await asyncio.to_thread(
            analyze_tool, {}, {"resume_data": parsed, "parsed_resume": parsed}
        )
        if analyzed.get("error"):
            raise HTTPException(status_code=422, detail=analyzed["error"])
        return {
            "file_name": req.file_name,
            "parse_logs": parse_logs,
            "analysis_logs": analyze_logs,
            "parsed": parsed,
            "analysis": analyzed["analysis"],
        }
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


@app.post("/resume/match")
async def match_resume(req: ResumeMatchRequest):
    if not 1 <= req.limit <= 50:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 50")
    from src.tools.job_matcher_tool import run as match_tool

    logs, output = await asyncio.to_thread(
        match_tool,
        {"location": req.location, "limit": req.limit},
        {"resume_analysis": {"analysis": req.analysis}},
    )
    if output.get("error"):
        raise HTTPException(status_code=422, detail=output["error"])
    return {"logs": logs, **output}


@app.post("/run")
async def run_task(req: RunRequest):
    goal = (req.goal or req.command or "").strip()
    if not goal:
        raise HTTPException(status_code=422, detail="A goal or command is required")

    run_id = str(uuid4())
    created_at = utc_now()
    try:
        active_planner = planner
        if req.planner == "rule":
            active_planner = RulePlanner(cfg, memory=memory)
        elif req.planner == "llm":
            active_planner = LLMPlanner(cfg, memory=memory)

        plan = active_planner.plan(goal, target_email=req.email)
        logs = await controller.execute_plan(plan, run_id=run_id)
        events = serialize_events(controller.get_events())
        status = run_status(events)
        record = {
            "run_id": run_id,
            "goal": goal,
            "status": status,
            "planner": req.planner or planner_mode,
            "plan": plan,
            "logs": logs,
            "events": events,
            "created_at": created_at,
            "completed_at": utc_now(),
            "tasks_completed": sum(event.get("event_type") == "task_completed" for event in events),
            "verification_events": sum(event.get("event_type") == "task_verified" for event in events),
        }
        run_store.save(record)
        return record
    except Exception as e:
        record = {
            "run_id": run_id,
            "goal": goal,
            "status": "failed",
            "planner": req.planner or planner_mode,
            "error": str(e),
            "created_at": created_at,
            "completed_at": utc_now(),
        }
        run_store.save(record)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs")
async def list_runs():
    return {"runs": run_store.list()}


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    record = run_store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    return record


@app.get("/tools")
async def list_tools():
    return {"tools": [tool.model_dump() for tool in controller.registry.describe()]}


@app.get("/metrics")
async def metrics():
    return run_store.metrics()


@app.get("/evaluation")
async def evaluation():
    return evaluate_runs(run_store.list())


@app.get("/memory")
async def get_memory():
    return memory.to_dict()


@app.post("/memory/preference")
async def set_preference(req: PreferenceRequest):
    memory.set_preference(req.key, req.value)
    return {"status": "ok", "key": req.key, "value": req.value}


@app.delete("/memory")
async def clear_memory():
    memory.clear()
    return {"status": "ok", "message": "Memory reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
