"""API Integration tests for FastAPI endpoints."""
import pytest
import base64
from fastapi.testclient import TestClient
import src.main as main
from src.agent.career_store import CareerStore
from src.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_AUTH_REQUIRED", "false")
    monkeypatch.setattr(main, "career_store", CareerStore(str(tmp_path / "career.json")))
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "aura"}


def test_clerk_auth_blocks_api_requests_without_a_session(client, monkeypatch):
    monkeypatch.setenv("AURA_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_example")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(main, "verify_clerk_request", lambda request: None)
    response = client.get("/profile")
    assert response.status_code == 401


def test_clerk_auth_scopes_authenticated_user(client, monkeypatch):
    monkeypatch.setenv("AURA_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_example")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(main, "verify_clerk_request", lambda request: "user_aura_test")
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {"user_id": "user_aura_test"}


def test_tools_endpoint(client):
    response = client.get("/tools")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    tool_names = [t["name"] for t in data["tools"]]
    assert "search" in tool_names
    assert "scrape" in tool_names
    assert "email" in tool_names


def test_metrics_and_evaluation_endpoints(client):
    res_m = client.get("/metrics")
    assert res_m.status_code == 200
    assert "total_runs" in res_m.json()

    res_e = client.get("/evaluation")
    assert res_e.status_code == 200
    assert "total_runs" in res_e.json()


def test_memory_endpoints(client):
    # Set preference
    res = client.post("/memory/preference", json={"key": "theme", "value": "dark"})
    assert res.status_code == 200

    # Get memory
    res_get = client.get("/memory")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["preferences"].get("theme") == "dark"


def test_run_task_validation_error(client):
    response = client.post("/run", json={"goal": ""})
    assert response.status_code == 422


def test_run_task_success(client):
    response = client.post("/run", json={"goal": "Find python tutorials and log", "planner": "rule"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "run_id" in data
    assert len(data["logs"]) > 0

    # Check that run is retrievable
    run_id = data["run_id"]
    res_run = client.get(f"/runs/{run_id}")
    assert res_run.status_code == 200
    assert res_run.json()["run_id"] == run_id


def test_resume_analyze_invalid_extension(client):
    response = client.post(
        "/resume/analyze",
        json={"file_name": "resume.exe", "content_base64": "SGVsbG8="}
    )
    assert response.status_code == 422
    assert "PDF, DOCX, and TXT" in response.json()["detail"]


def test_resume_analyze_valid_txt(client, monkeypatch):
    from src.tools import resume_analyzer_tool
    monkeypatch.setattr(resume_analyzer_tool, "get_llm_client", lambda: None)
    sample_text = "John Smith\njohn@example.com\nSenior Python Backend Engineer\nSKILLS\nPython, FastAPI, Docker\nEDUCATION\nB.Tech Computer Science 2022-2026"
    encoded = base64.b64encode(sample_text.encode("utf-8")).decode("ascii")
    response = client.post(
        "/resume/analyze",
        json={"file_name": "resume.txt", "content_base64": encoded}
    )
    assert response.status_code == 200
    data = response.json()
    assert "analysis" in data
    assert data["file_name"] == "resume.txt"
    assert data["analysis"]["name"] == "John Smith"
    assert data["analysis"]["email"] == "john@example.com"
    assert {"python", "fastapi", "docker"}.issubset({skill.casefold() for skill in data["analysis"]["skills"]})
    assert data["analysis"]["years_experience"] is None
    assert data["profile_saved"] is True
    assert data["resume_saved"] is True
    saved_file = client.get("/profile/resume")
    assert saved_file.status_code == 200
    assert saved_file.content == sample_text.encode("utf-8")


def test_profile_page_saves_details_and_keeps_resume_for_download(client, monkeypatch):
    from src.tools import resume_analyzer_tool
    monkeypatch.setattr(resume_analyzer_tool, "get_llm_client", lambda: None)
    details = {"name": "Somnath Chaudhary", "email": "somnath@example.com", "phone": "+91 9876543210", "location": "Delhi"}
    saved_details = client.put("/profile", json=details)
    assert saved_details.status_code == 200
    assert client.get("/profile").json()["profile"]["email"] == "somnath@example.com"

    resume_text = "Somnath Chaudhary\nsomnath@example.com\nCybersecurity Student\nSKILLS\nPython, Wireshark\nEDUCATION\nB.Tech Computer Science 2022-2026"
    encoded = base64.b64encode(resume_text.encode("utf-8")).decode("ascii")
    uploaded = client.post("/profile/resume", json={"file_name": "somnath.txt", "content_base64": encoded})
    assert uploaded.status_code == 200
    assert uploaded.json()["resume_saved"] is True
    saved_profile = client.get("/profile").json()
    assert saved_profile["resume"]["original_name"] == "somnath.txt"
    assert saved_profile["profile"]["email"] == "somnath@example.com"
    assert client.get("/profile/resume").content == resume_text.encode("utf-8")


def test_resume_studio_draft_persists_through_profile_api(client):
    draft = {
        "name": "Taylor Example",
        "title": "Security Analyst",
        "links": [{"label": "Portfolio", "url": "https://example.org"}],
        "projects": [{"name": "Home lab", "detail": "Built a small test network"}],
    }
    saved = client.put("/resume/studio", json={"resume": draft})
    assert saved.status_code == 200
    assert saved.json()["resume"] == draft
    assert client.get("/resume/studio").json()["resume"] == draft


def test_career_preferences_and_profile_persist(client, monkeypatch):
    from src.tools import resume_analyzer_tool
    monkeypatch.setattr(resume_analyzer_tool, "get_llm_client", lambda: None)
    response = client.put("/career/preferences", json={
        "target_role": "SOC Analyst Fresher", "location": "Delhi", "keywords": "SIEM, Splunk",
        "work_mode": "hybrid", "min_salary": 400000,
    })
    assert response.status_code == 200
    assert client.get("/career/preferences").json()["preferences"]["target_role"] == "SOC Analyst Fresher"
    resume = base64.b64encode(b"Somnath Chaudhary\nsom@example.com\nCybersecurity Student\nSkills\nWireshark, Kali Linux, Python\nEducation\nB.Tech Computer Science 2022-2026").decode("ascii")
    analyzed = client.post("/resume/analyze", json={"file_name": "somnath.txt", "content_base64": resume})
    assert analyzed.status_code == 200
    profile = client.get("/career/profile").json()["profile"]
    assert profile["name"] == "Somnath Chaudhary"
    assert profile["years_experience"] is None


def test_resume_match_uses_saved_role_and_returns_ranked_jobs(client, monkeypatch):
    from src.tools import search_tool
    seen = {}
    def fake_search(args, context):
        seen.update(args)
        return ["Search test provider"], {"search_available": True, "results": [
            {"title": "SOC Analyst - Entry Level", "url": "https://jobs.example/soc", "snippet": "SOC Analyst role using SIEM, Splunk, Python and incident response.", "company": "Example Security", "location": "Delhi", "work_mode": "Hybrid", "salary": "₹5 LPA"},
            {"title": "SOC Analyst Trainee", "url": "https://jobs.example/soc-trainee", "snippet": "SOC Analyst role using SIEM and Python.", "company": "Example Security", "location": "Delhi", "work_mode": "Hybrid", "salary": "₹3 LPA"},
        ]}
    monkeypatch.setattr(search_tool, "run", fake_search)
    assert client.put("/career/preferences", json={"target_role": "SOC Analyst Fresher", "keywords": "SIEM, Splunk", "location": "Delhi", "min_salary": 400000}).status_code == 200
    response = client.post("/resume/match", json={
        "analysis": {"field_of_study": "Computer Science", "skills": ["Python", "SIEM"], "job_keywords": ["networking"], "career_interests": []},
        "location": "Delhi", "limit": 10,
    })
    assert response.status_code == 200
    result = response.json()
    assert "SOC Analyst Fresher" in seen["query"]
    assert "SIEM" in seen["query"]
    assert "Splunk" in seen["query"]
    assert "Computer Science" not in seen["query"]
    assert len(result["job_matches"]) == 1
    assert result["job_matches"][0]["url"] == "https://jobs.example/soc"
    assert result["job_matches"][0]["matched_skills"] == ["Python", "SIEM"]
    assert any("Role aligns with" in reason for reason in result["job_matches"][0]["fit_reasons"])


def test_talent_role_actions_cover_save_match_kit_skill_plan_and_pipeline(client):
    main.career_store.save_profile({
        "name": "Taylor Example", "skills": ["Python", "SIEM"], "career_interests": ["SOC Analyst"],
        "job_keywords": ["SOC Analyst", "SIEM"], "achievements": ["Investigated 25 simulated network alerts using Wireshark."],
        "years_experience": None,
    })
    job = {
        "title": "SOC Analyst", "url": "https://jobs.example/soc-analyst", "company": "Example Security",
        "location": "Delhi", "snippet": "Use SIEM and incident response to investigate security alerts.",
    }
    saved = client.post("/career/roles", json=job)
    assert saved.status_code == 200
    assert saved.json()["created"] is True
    role_id = saved.json()["role"]["id"]
    assert client.post("/career/roles", json=job).json()["created"] is False

    kit = client.post("/career/application-kit", json={"job": job})
    assert kit.status_code == 200
    assert "Taylor Example" in kit.json()["cover_letter"]
    assert "Investigated 25 simulated network alerts" in kit.json()["resume_bullets"][0]

    plan = client.post("/career/skill-plan", json={"job": job})
    assert plan.status_code == 200
    assert plan.json()["title"] == "SOC Analyst"
    assert plan.json()["steps"]

    updated = client.patch(f"/career/roles/{role_id}", json={"status": "interview", "follow_up_on": "2027-01-15", "note": "Prepare SIEM examples"})
    assert updated.status_code == 200
    assert updated.json()["role"]["status"] == "interview"
    listed = client.get("/career/roles").json()["roles"]
    assert listed[0]["note"] == "Prepare SIEM examples"
    assert client.patch(f"/career/roles/{role_id}", json={"follow_up_on": "not-a-date"}).status_code == 422


def test_talent_digest_and_email_actions_use_saved_brief(client, monkeypatch):
    from src.tools import search_tool
    main.career_store.save_profile({"name": "Taylor Example", "skills": ["Python"], "career_interests": ["SOC Analyst"], "achievements": []})
    preferences = {"target_role": "SOC Analyst Fresher", "location": "Delhi", "keywords": "SIEM", "digest_email": "student@example.com"}
    assert client.put("/career/preferences", json=preferences).status_code == 200
    seen = {}
    def fake_search(args, context):
        seen.update(args)
        return ["stubbed provider"], {"search_available": True, "results": [{
            "title": "SOC Analyst Fresher", "url": "https://jobs.example/digest-role",
            "snippet": "Entry role for Python and SIEM monitoring", "company": "Example", "location": "Delhi",
        }]}
    monkeypatch.setattr(search_tool, "run", fake_search)
    digest = client.post("/career/digest", json={"limit": 5})
    assert digest.status_code == 200
    assert "SOC Analyst Fresher" in seen["query"]
    assert len(digest.json()["results"]) == 1

    sent = {}
    async def fake_send(recipient):
        sent["recipient"] = recipient
        return {"email_sent": True, "message": "Digest email sent."}
    monkeypatch.setattr(main, "_send_latest_career_digest", fake_send)
    email = client.post("/career/digest/email")
    assert email.status_code == 200
    assert email.json()["email_sent"] is True
    assert sent["recipient"] == "student@example.com"
    assert client.post("/career/digest").json()["results"] == []


def test_resume_ats_audit_endpoint(client):
    response = client.post("/resume/ats-audit", json={"resume_text": "SUMMARY\nPython engineer\nEXPERIENCE\nBuilt tools.\nEDUCATION\nB.Tech"})
    assert response.status_code == 200
    data = response.json()
    assert data["vendor_score"] is False
    assert set(data["categories"]) == {"parseability", "structure", "content"}


def test_resume_match_limits(client):
    # Invalid limit > 50
    response = client.post(
        "/resume/match",
        json={"analysis": {"skills": ["Python"]}, "limit": 100}
    )
    assert response.status_code == 422
