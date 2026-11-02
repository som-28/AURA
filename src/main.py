import asyncio
import base64
import binascii
import ipaddress
import json
import os
import re
import socket
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.local", override=False)
load_dotenv(PROJECT_ROOT / ".env", override=False)

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import requests
from urllib.parse import quote, urlsplit
from typing import Optional, Any
from src.agent.planner import Planner as RulePlanner
from src.agent.planner_llm import LLMPlanner
from src.agent.controller import Controller
from src.agent.evaluator import evaluate_runs
from src.agent.run_store import RunStore
from src.agent.memory import Memory
from src.agent.career_store import CareerStore
from src.agent.world_store import WorldStore, CATEGORIES as WORLD_CATEGORIES
from src.agent.state_store import get_request_owner_id, reset_request_owner_id, set_request_owner_id
from src.auth import auth_is_required, clerk_is_configured, public_asset_or_route, verify_clerk_request
from src.utils.career_matching import score_role, build_skill_plan
from src.utils.email_utils import usable_recipient
from src.utils.config import load_config

app = FastAPI(title="AURA Autonomous Task Agent")


@app.middleware("http")
async def clerk_authentication(request, call_next):
    if public_asset_or_route(request) or not auth_is_required():
        return await call_next(request)
    if not clerk_is_configured():
        return JSONResponse(
            status_code=503,
            content={"detail": "Clerk authentication is not configured on this server"},
        )
    user_id = await asyncio.to_thread(verify_clerk_request, request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Sign in to continue"})
    owner_token = set_request_owner_id(user_id)
    try:
        return await call_next(request)
    finally:
        reset_request_owner_id(owner_token)

cfg = load_config()
# Shared memory store for preferences and long-term state
memory = Memory()
# Use LLM planner if configured, else rule-based
planner_mode = os.getenv("PLANNER_MODE", "rule")
planner = LLMPlanner(cfg, memory=memory) if planner_mode == "llm" else RulePlanner(cfg, memory=memory)
controller = Controller(cfg, memory=memory)
run_store = RunStore()
career_store = CareerStore()
world_store = WorldStore()


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


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None


class ResumeStudioRequest(BaseModel):
    resume: dict[str, Any]


class ResumeAuditRequest(BaseModel):
    resume_text: str
    job_description: str = ""


class ResumeMatchRequest(BaseModel):
    analysis: dict
    location: Optional[str] = None
    target_role: Optional[str] = None
    keywords: Optional[str] = None
    work_mode: Optional[str] = None
    min_salary: Optional[float] = None
    limit: int = 10


class LinkCheckRequest(BaseModel):
    urls: list[str]


class CareerPreferencesRequest(BaseModel):
    target_role: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None
    keywords: Optional[str] = None
    min_salary: Optional[float] = None
    digest_email: Optional[str] = None
    digest_frequency: Optional[str] = None


class CareerRoleRequest(BaseModel):
    title: str
    url: str
    source: Optional[str] = ""
    company: Optional[str] = ""
    location: Optional[str] = ""
    snippet: Optional[str] = ""
    salary: Optional[str] = ""
    work_mode: Optional[str] = ""
    employment_type: Optional[str] = ""
    fit_score: Optional[int] = None
    fit_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


class CareerRoleUpdateRequest(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None
    follow_up_on: Optional[str] = None


class CareerJobRequest(BaseModel):
    job: dict


class CareerDigestRequest(BaseModel):
    target_role: Optional[str] = None
    location: Optional[str] = None
    limit: int = 10


class WorldMissionRequest(BaseModel):
    title: str
    category: str = "discovery"
    note: str = ""


class WorldArtifactRequest(BaseModel):
    title: str
    category: str = "making"
    content: str = ""
    url: str = ""


class WorldDiscoveryRequest(BaseModel):
    title: str
    category: str
    choice: str
    insight: str
    categories: list[str] = Field(default_factory=list)


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


@app.get("/auth/config")
async def clerk_client_config():
    return {
        "publishable_key": os.getenv("CLERK_PUBLISHABLE_KEY", "").strip(),
        "configured": clerk_is_configured(),
        "required": auth_is_required(),
    }


@app.get("/auth/me")
async def clerk_current_user():
    user_id = get_request_owner_id()
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return {"user_id": user_id}


@app.post("/links/check")
async def check_links(req: LinkCheckRequest):
    urls = list(dict.fromkeys(url.strip() for url in req.urls if isinstance(url, str) and url.strip()))[:15]
    results = await asyncio.gather(*(asyncio.to_thread(check_public_link, url) for url in urls))
    return {"checked_at": utc_now(), "results": results}


@app.get("/profile")
async def get_profile_page_data():
    return {"profile": career_store.profile(), "resume": career_store.resume_info()}


@app.put("/profile")
async def update_profile(req: ProfileUpdateRequest):
    email = str(req.email or "").strip()
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    profile = career_store.save_identity(req.model_dump())
    return {"profile": profile}


@app.get("/resume/studio")
async def get_resume_studio():
    return {"resume": career_store.resume_studio()}


@app.put("/resume/studio")
async def save_resume_studio(req: ResumeStudioRequest):
    try:
        resume = career_store.save_resume_studio(req.resume)
    except ValueError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    return {"resume": resume}


@app.post("/profile/resume")
async def upload_profile_resume(req: ResumeAnalyzeRequest):
    return await analyze_resume(req)


@app.get("/profile/resume")
async def download_profile_resume():
    info = career_store.resume_info()
    saved_file = career_store.resume_file()
    if not info or not saved_file:
        raise HTTPException(status_code=404, detail="No saved resume is available")
    filename, content_type, content = saved_file
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(content, media_type=content_type, headers={"Content-Disposition": disposition})


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
    try:
        saved_resume = career_store.save_resume(content, req.file_name)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

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
        analyzed["analysis"]["links"] = parsed.get("links", [])[:25]
        career_store.save_profile(analyzed["analysis"])
        return {
            "file_name": req.file_name,
            "parse_logs": parse_logs,
            "analysis_logs": analyze_logs,
            "parsed": parsed,
            "analysis": analyzed["analysis"],
            "profile_saved": True,
            "resume_saved": True,
            "saved_resume": saved_resume,
        }
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


@app.post("/resume/parse")
async def parse_resume_for_studio(req: ResumeAnalyzeRequest):
    """Extract resume text for the browser editor without waiting on an LLM."""
    extension = Path(req.file_name).suffix.lower()
    if extension not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(status_code=422, detail="Only PDF, DOCX, and TXT files are supported")
    try:
        content = base64.b64decode(req.content_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=422, detail="Resume file could not be read")
    if not content:
        raise HTTPException(status_code=422, detail="Resume file is empty")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Resume file exceeds the 10 MB limit")

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temporary_file:
            temporary_file.write(content)
            temporary_path = temporary_file.name
        from src.tools.resume_parser_tool import run as parse_tool

        logs, parsed = await asyncio.to_thread(parse_tool, {"file_path": temporary_path}, {})
        if parsed.get("error"):
            raise HTTPException(status_code=422, detail=parsed["error"])
        return {"file_name": req.file_name, "parse_logs": logs, "parsed": parsed}
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


@app.post("/resume/ats-audit")
async def resume_ats_audit(req: ResumeAuditRequest):
    """Run transparent text-level resume checks and optional literal JD matching."""
    if len(req.resume_text) > 40000 or len(req.job_description) > 40000:
        raise HTTPException(status_code=413, detail="Resume text and job description must each be under 40,000 characters")
    from src.utils.ats_audit import audit_resume

    return audit_resume(req.resume_text, req.job_description)


@app.post("/resume/match")
async def match_resume(req: ResumeMatchRequest):
    if not 1 <= req.limit <= 50:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 50")
    from src.tools.job_matcher_tool import run as match_tool

    preferences = career_store.preferences()
    location = str(req.location or preferences.get("location") or "remote").strip()
    target_role = str(req.target_role or preferences.get("target_role") or "").strip()
    keywords = str(req.keywords or preferences.get("keywords") or "").strip()
    work_mode = str(req.work_mode or preferences.get("work_mode") or "").strip()
    min_salary = req.min_salary if req.min_salary is not None else preferences.get("min_salary")
    matching_analysis = dict(req.analysis)
    interests = matching_analysis.get("career_interests", [])
    interests = interests if isinstance(interests, list) else [interests]
    matching_analysis["career_interests"] = list(dict.fromkeys([*(str(item) for item in interests if str(item).strip()), *([target_role] if target_role else []), *(part.strip() for part in keywords.split(",") if part.strip())]))

    logs, output = await asyncio.to_thread(
        match_tool,
        {"location": location, "limit": req.limit, "target_role": target_role, "keywords": keywords, "work_mode": work_mode, "min_salary": min_salary},
        {"resume_analysis": {"analysis": matching_analysis}},
    )
    if output.get("error"):
        raise HTTPException(status_code=422, detail=output["error"])
    if min_salary and output.get("job_matches"):
        output["job_matches"] = [job for job in output["job_matches"] if _salary_inr_annual(job.get("salary", "")) is None or _salary_inr_annual(job.get("salary", "")) >= float(min_salary)]
    return {"logs": logs, **output}


@app.get("/career/profile")
async def get_career_profile():
    return {"profile": career_store.profile()}


@app.get("/career/preferences")
async def get_career_preferences():
    return {"preferences": career_store.preferences()}


@app.put("/career/preferences")
async def put_career_preferences(req: CareerPreferencesRequest):
    return {"preferences": career_store.save_preferences(req.model_dump(exclude_none=True))}


@app.get("/career/roles")
async def get_career_roles():
    roles = career_store.roles()
    today = date.today()
    through = (today + timedelta(days=7)).isoformat()
    today = today.isoformat()
    due = sorted(
        [role for role in roles if role.get("follow_up_on") and role["follow_up_on"] <= through and role.get("status") not in {"rejected", "offer"}],
        key=lambda role: role.get("follow_up_on", ""),
    )
    return {"roles": roles, "reminders_due": due}


@app.post("/career/roles")
async def save_career_role(req: CareerRoleRequest):
    if not 0 <= (req.fit_score if req.fit_score is not None else 0) <= 100:
        raise HTTPException(status_code=422, detail="fit_score must be between 0 and 100")
    try:
        parts = urlsplit(req.url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="A valid public job URL is required")
    role, created = career_store.save_role(req.model_dump())
    return {"role": role, "created": created}


@app.patch("/career/roles/{role_id}")
async def update_career_role(role_id: str, req: CareerRoleUpdateRequest):
    changes = req.model_dump(exclude_none=True)
    if "follow_up_on" in changes and changes["follow_up_on"]:
        try:
            date.fromisoformat(changes["follow_up_on"])
        except ValueError:
            raise HTTPException(status_code=422, detail="follow_up_on must use YYYY-MM-DD format")
    try:
        role = career_store.update_role(role_id, changes)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if not role:
        raise HTTPException(status_code=404, detail="Saved role not found")
    return {"role": role}


@app.post("/career/skill-plan")
async def career_skill_plan(req: CareerJobRequest):
    profile = career_store.profile()
    if not profile:
        raise HTTPException(status_code=409, detail="Analyze a resume first to build a personal skill-gap plan")
    job = dict(req.job)
    job["preferred_location"] = career_store.preferences().get("location", "")
    return build_skill_plan(job, profile)


@app.post("/career/application-kit")
async def career_application_kit(req: CareerJobRequest):
    profile = career_store.profile()
    if not profile:
        raise HTTPException(status_code=409, detail="Analyze a resume first to build a profile-grounded application kit")
    job = req.job
    fit = score_role(profile, job, str(career_store.preferences().get("location") or ""))
    title = str(job.get("title") or "the role")
    company = str(job.get("company") or "the team")
    display_name = str(profile.get("name") or "Candidate")
    matched_skills = fit["matched_skills"][:4]
    strengths = ", ".join(matched_skills) if matched_skills else ", ".join(str(skill) for skill in profile.get("skills", [])[:3])
    achievements = [
        str(item).strip() for item in profile.get("achievements", [])
        if str(item).strip() and str(item).strip().casefold() not in {"see resume for details", "not specified"}
    ][:3]
    bullets = achievements or [
        f"[Add a real example showing how you used {skill} and what result you achieved.]"
        for skill in (matched_skills or profile.get("skills", [])[:3])
    ]
    role_line = f"I am applying for the {title} role at {company}."
    experience = profile.get("years_experience")
    intro = f"My profile includes {strengths}." if strengths else "I am interested in contributing to this role."
    if experience is not None:
        intro = f"My profile records {experience} years of experience and includes {strengths}."
    evidence_sentence = f"Relevant experience includes: {achievements[0]}." if achievements else "I would welcome the opportunity to discuss relevant projects and experience."
    letter = "\n\n".join([
        "Dear Hiring Team,",
        f"{role_line} {intro}",
        evidence_sentence,
        f"I am interested in bringing this experience to {company} and learning more about the team's priorities.",
        "Thank you for your time.\n\nKind regards,\n" + display_name,
    ])
    return {
        "title": title,
        "company": company,
        "fit": fit,
        "resume_bullets": bullets,
        "cover_letter": letter,
        "notice": "Editable draft built from saved profile facts. Check every statement, replace bracketed prompts with real evidence, and tailor it before using.",
    }


def _salary_inr_annual(value: str) -> float | None:
    text = str(value or "").casefold()
    if not any(token in text for token in ("₹", "inr", "rs.")):
        return None
    matches = re.findall(r"(\d[\d,.]*)\s*(lakh|lakhs|lac|l|k|thousand)?", text)
    if not matches:
        return None
    amount = float(matches[0][0].replace(",", ""))
    suffix = matches[0][1]
    amount *= 100000 if suffix in {"lakh", "lakhs", "lac", "l"} else 1000 if suffix in {"k", "thousand"} else 1
    if "month" in text or "/mo" in text:
        amount *= 12
    elif any(token in text for token in ("hour", "/hr", "weekly", "per week")):
        return None
    return amount


def _collect_career_digest(role: str, location: str, keywords: str, work_mode: str, min_salary: float | None, limit: int) -> dict:
    profile = career_store.profile() or {}
    query = " ".join(part for part in (role, keywords, location, work_mode, "jobs") if part)
    from src.tools.search_tool import run as search_run
    logs, output = search_run({"query": query, "limit": max(1, min(limit, 15))}, {})
    if output.get("search_available") is False:
        return {"search_available": False, "message": output.get("message"), "query": query, "results": [], "logs": logs}
    seen = career_store.digest_urls() | {item.get("url") for item in career_store.roles()}
    new_results = []
    for item in output.get("results", []):
        if item.get("url") in seen:
            continue
        salary = _salary_inr_annual(item.get("salary", ""))
        if min_salary and salary is not None and salary < min_salary:
            continue
        item.update(score_role(profile, item, location) if profile else {})
        new_results.append(item)
    career_store.remember_digest([item.get("url") for item in output.get("results", []) if item.get("url")])
    checked_at = utc_now()
    career_store.save_latest_digest(query, new_results)
    return {"search_available": True, "query": query, "location": location, "results": new_results, "checked_at": checked_at, "logs": logs}


async def _send_latest_career_digest(recipient: str) -> dict:
    digest = career_store.last_digest()
    if not digest or not digest.get("results"):
        return {"email_sent": False, "message": "No new roles are available to email."}
    from src.tools.email_tool import run as email_run
    logs, output = await asyncio.to_thread(
        email_run,
        {"to": recipient, "subject": f"AURA career digest: {digest['query'][:90]}"},
        {"results": digest["results"], "plan_input": digest["query"]},
    )
    if output.get("email_sent"):
        career_store.mark_digest_checked()
    return {"email_sent": bool(output.get("email_sent")), "message": "Career digest emailed." if output.get("email_sent") else output.get("error", "Email could not be sent."), "logs": logs}


async def _weekly_career_digest_loop():
    while True:
        try:
            preferences = career_store.preferences()
            recipient = usable_recipient(preferences.get("digest_email"))
            role = str(preferences.get("target_role") or "").strip()
            last_checked = career_store.digest_last_checked()
            due = True
            if last_checked:
                try:
                    due = (datetime.now(timezone.utc) - datetime.fromisoformat(last_checked)).total_seconds() >= 7 * 24 * 60 * 60
                except ValueError:
                    due = True
            if preferences.get("digest_frequency") == "weekly" and recipient and role and due:
                result = await asyncio.to_thread(
                    _collect_career_digest,
                    role,
                    str(preferences.get("location") or "remote"),
                    str(preferences.get("keywords") or ""),
                    str(preferences.get("work_mode") or ""),
                    float(preferences["min_salary"]) if preferences.get("min_salary") else None,
                    10,
                )
                if result.get("search_available") and result.get("results"):
                    await _send_latest_career_digest(recipient)
                else:
                    # A weekly search with no new results is still a completed check.
                    career_store.mark_digest_checked()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A transient provider failure should not stop future scheduled checks.
            pass
        await asyncio.sleep(6 * 60 * 60)


@app.on_event("startup")
async def start_weekly_career_digest():
    app.state.career_digest_task = asyncio.create_task(_weekly_career_digest_loop())


@app.on_event("shutdown")
async def stop_weekly_career_digest():
    task = getattr(app.state, "career_digest_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.post("/career/digest")
async def career_digest(req: CareerDigestRequest):
    preferences = career_store.preferences()
    profile = career_store.profile() or {}
    role = str(req.target_role or preferences.get("target_role") or (profile.get("career_interests") or [""])[0]).strip()
    if not role:
        raise HTTPException(status_code=422, detail="Save a target role in Career preferences first")
    location = str(req.location or preferences.get("location") or "remote").strip()
    return await asyncio.to_thread(
        _collect_career_digest,
        role,
        location,
        str(preferences.get("keywords") or "").strip(),
        str(preferences.get("work_mode") or "").strip(),
        float(preferences["min_salary"]) if preferences.get("min_salary") else None,
        req.limit,
    )


@app.post("/career/digest/email")
async def email_career_digest():
    preferences = career_store.preferences()
    recipient = usable_recipient(preferences.get("digest_email"))
    if not recipient:
        raise HTTPException(status_code=409, detail="Add a valid digest email to your saved career preferences first")
    digest = career_store.last_digest()
    if not digest or not digest.get("results"):
        raise HTTPException(status_code=409, detail="Find new roles first; there are no new digest results to email")
    return await _send_latest_career_digest(recipient)


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


@app.get("/world")
async def get_world():
    return world_store.snapshot()


@app.post("/world/discoveries")
async def save_world_discovery(req: WorldDiscoveryRequest):
    if not req.title.strip() or not req.choice.strip() or not req.insight.strip():
        raise HTTPException(status_code=422, detail="A discovery needs its title, choice, and reveal")
    categories = req.categories or [req.category]
    if any(category not in WORLD_CATEGORIES for category in categories):
        raise HTTPException(status_code=422, detail="Choose a valid discovery theme")
    discovery = world_store.add_discovery(req.title, req.category, req.choice, req.insight, categories)
    return {"discovery": discovery, **world_store.snapshot()}


@app.post("/world/missions")
async def create_world_mission(req: WorldMissionRequest):
    if not req.title.strip():
        raise HTTPException(status_code=422, detail="Give your mission a name first")
    if req.category not in WORLD_CATEGORIES:
        raise HTTPException(status_code=422, detail="Choose a valid mission theme")
    mission = world_store.add_mission(req.title, req.category, req.note)
    return {"mission": mission, **world_store.snapshot()}


@app.patch("/world/missions/{mission_id}/complete")
async def complete_world_mission(mission_id: str):
    mission = world_store.complete_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"mission": mission, **world_store.snapshot()}


@app.post("/world/artifacts")
async def create_world_artifact(req: WorldArtifactRequest):
    if not req.title.strip():
        raise HTTPException(status_code=422, detail="Give your artifact a name first")
    if req.category not in WORLD_CATEGORIES:
        raise HTTPException(status_code=422, detail="Choose a valid artifact theme")
    if req.url.strip():
        try:
            parts = urlsplit(req.url.strip())
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail="Artifact link must be a valid HTTP(S) URL")
    artifact = world_store.add_artifact(req.title, req.category, req.content, req.url)
    return {"artifact": artifact, **world_store.snapshot()}


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
