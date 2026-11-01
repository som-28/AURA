import asyncio
import base64
import binascii
import ipaddress
import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
from urllib.parse import urlsplit
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


class LinkCheckRequest(BaseModel):
    urls: list[str]


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
    states = set(task_states.values())
    completed = "task_completed" in states
    if "task_failed" in states:
        return "partial" if completed else "failed"
    if "task_skipped" in states:
        return "partial" if completed else "failed"
    return "completed" if completed or not states else "failed"


def user_facing_outputs(outputs: dict[str, dict]) -> dict:
    """Keep only compact, safe-to-display summaries and real HTTP links."""
    results = []
    seen_urls = set()
    summary = None
    search_message = None
    search_available = None
    email_status = None

    for item in outputs.values():
        data = item.get("data") or {}
        if not isinstance(data, dict):
            continue
        if data.get("summary"):
            summary = str(data["summary"])
        if data.get("search_available") is False:
            search_available = False
            search_message = data.get("message") or "Live search is not configured."
        elif data.get("search_available") is True:
            search_available = True
        if "email_sent" in data:
            if data.get("email_sent"):
                email_status = "Results emailed successfully."
            elif data.get("reason") == "missing_recipient":
                email_status = "Email skipped: add a recipient address to the email field."
            elif data.get("error"):
                email_status = str(data["error"])
        candidates = list(data.get("job_matches") or data.get("results") or [])
        for page in data.get("pages", []) or []:
            if isinstance(page, dict) and page.get("url"):
                try:
                    host = urlsplit(str(page["url"])).hostname or "Source page"
                except ValueError:
                    host = "Source page"
                candidates.append({
                    "title": page.get("title") or host.removeprefix("www."),
                    "url": page["url"],
                    "snippet": str(page.get("text") or "")[:280],
                    "source": host.removeprefix("www."),
                    "provider": "AURA page reader",
                })
        if not isinstance(candidates, list):
            continue
        for result in candidates:
            if not isinstance(result, dict):
                continue
            url = str(result.get("url") or result.get("link") or "").strip()
            if not url.startswith(("https://", "http://")) or "example.com/" in url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({
                "title": str(result.get("title") or "Opportunity"),
                "snippet": str(result.get("snippet") or ""),
                "url": url,
                "relevance": str(result.get("relevance") or ""),
                "source": str(result.get("source") or urlsplit(url).hostname or "Web"),
                "provider": str(result.get("provider") or "Web search"),
                "found_at": result.get("found_at"),
                "published_at": result.get("published_at"),
                "company": str(result.get("company") or ""),
                "location": str(result.get("location") or ""),
                "work_mode": str(result.get("work_mode") or ""),
                "salary": str(result.get("salary") or ""),
                "employment_type": str(result.get("employment_type") or ""),
            })

    return {
        "results": results[:15],
        "summary": summary,
        "search_available": search_available,
        "search_message": search_message,
        "email_status": email_status,
    }


def check_public_link(raw_url: str) -> dict:
    """Check an external result URL without following redirects or fetching content."""
    try:
        parts = urlsplit(raw_url)
        host = parts.hostname
        if parts.scheme not in {"http", "https"} or not host or parts.username or parts.password:
            return {"url": raw_url, "status": "unsafe", "message": "Unsupported or unsafe link"}
        if host.lower() in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
            return {"url": raw_url, "status": "unsafe", "message": "Private address blocked"}
        addresses = [ipaddress.ip_address(host)] if _is_ip_address(host) else [
            ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        ]
        if not addresses or any(not address.is_global for address in addresses):
            return {"url": raw_url, "status": "unsafe", "message": "Private address blocked"}
    except (ValueError, OSError):
        return {"url": raw_url, "status": "unavailable", "message": "Could not resolve this link"}

    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.head(raw_url, timeout=(3, 5), allow_redirects=False,
                                    headers={"User-Agent": "AURA-Link-Check/1.0"})
            if response.status_code in {403, 405, 501}:
                response.close()
                response = session.get(raw_url, timeout=(3, 5), allow_redirects=False, stream=True,
                                       headers={"User-Agent": "AURA-Link-Check/1.0", "Range": "bytes=0-0"})
            code = response.status_code
            response.close()
        if 200 <= code < 300:
            return {"url": raw_url, "status": "reachable", "message": "Link is reachable", "http_status": code}
        if 300 <= code < 400:
            return {"url": raw_url, "status": "redirect", "message": "Link redirects; open to confirm destination", "http_status": code}
        if code in {404, 410}:
            return {"url": raw_url, "status": "broken", "message": f"Link returned HTTP {code}", "http_status": code}
        if code >= 400:
            return {"url": raw_url, "status": "unavailable", "message": f"Site returned HTTP {code}; open to confirm", "http_status": code}
    except requests.RequestException:
        pass
    return {"url": raw_url, "status": "unavailable", "message": "Link could not be checked right now"}


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aura"}


@app.post("/links/check")
async def check_links(req: LinkCheckRequest):
    urls = list(dict.fromkeys(url.strip() for url in req.urls if isinstance(url, str) and url.strip()))[:15]
    results = await asyncio.gather(*(asyncio.to_thread(check_public_link, url) for url in urls))
    return {"checked_at": utc_now(), "results": results}


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


async def _execute_run(req: RunRequest, progress_queue=None):
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

        if progress_queue is not None:
            progress_queue.put_nowait({"event_type": "planning", "message": "Preparing your journey"})
        plan = await asyncio.to_thread(active_planner.plan, goal, target_email=req.email)
        run_controller = Controller(
            cfg,
            memory=memory,
            on_event=(progress_queue.put_nowait if progress_queue is not None else None),
        )
        logs = await run_controller.execute_plan(plan, run_id=run_id)
        events = serialize_events(run_controller.get_events())
        status = run_status(events)
        display_outputs = user_facing_outputs(run_controller.outputs)
        failed_event = next((event for event in reversed(events) if event.get("event_type") == "task_failed"), None)
        failure_reason = None
        if failed_event:
            failure_reason = (failed_event.get("metadata") or {}).get("error") or failed_event.get("message")
        completed_at = utc_now()
        record = {
            "run_id": run_id,
            "goal": goal,
            "status": status,
            "planner": req.planner or planner_mode,
            "plan": plan,
            "logs": logs,
            "events": events,
            **display_outputs,
            "failure_reason": failure_reason,
            "created_at": created_at,
            "completed_at": completed_at,
            "duration_ms": round((datetime.fromisoformat(completed_at) - datetime.fromisoformat(created_at)).total_seconds() * 1000),
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


@app.post("/run")
async def run_task(req: RunRequest):
    return await _execute_run(req)


@app.post("/run/stream")
async def run_task_stream(req: RunRequest):
    async def event_stream():
        queue = asyncio.Queue()
        task = asyncio.create_task(_execute_run(req, queue))
        while not task.done() or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
                yield f"event: progress\ndata: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                continue
        try:
            result = task.result()
            yield f"event: result\ndata: {json.dumps(result)}\n\n"
        except HTTPException as error:
            payload = {"message": error.detail}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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


# Serve the browser-native frontend from the same origin as the existing API.
# API routes above keep their behavior; the static mount only handles UI assets.
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True),
    name="aura-web",
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
