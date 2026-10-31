"""API Integration tests for FastAPI endpoints."""
import pytest
import base64
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "aura"}


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


def test_resume_analyze_valid_txt(client):
    sample_text = "John Smith\nSenior Python Backend Engineer\nSkills: Python, FastAPI, Docker"
    encoded = base64.b64encode(sample_text.encode("utf-8")).decode("ascii")
    response = client.post(
        "/resume/analyze",
        json={"file_name": "resume.txt", "content_base64": encoded}
    )
    assert response.status_code == 200
    data = response.json()
    assert "analysis" in data
    assert data["file_name"] == "resume.txt"


def test_resume_match_limits(client):
    # Invalid limit > 50
    response = client.post(
        "/resume/match",
        json={"analysis": {"skills": ["Python"]}, "limit": 100}
    )
    assert response.status_code == 422
