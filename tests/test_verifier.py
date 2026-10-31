"""Unit tests for tool output verifier."""
from src.agent.verifier import verify_tool_output


def test_verify_non_dict_output():
    res = verify_tool_output("search", "not-a-dict")
    assert not res.verified
    assert "not a mapping" in res.issues[0]


def test_verify_error_in_output():
    res = verify_tool_output("search", {"error": "Connection timed out"})
    assert not res.verified
    assert "Connection timed out" in res.issues[0]


def test_verify_search_valid():
    output = {
        "results": [
            {"title": "Job 1", "url": "https://example.com/1"},
            {"title": "Job 2", "url": "https://example.com/2"},
        ]
    }
    res = verify_tool_output("search", output)
    assert res.verified
    assert res.confidence >= 0.9
    assert len(res.evidence) > 0


def test_verify_search_empty():
    res = verify_tool_output("search", {"results": []})
    assert not res.verified
    assert "no results" in res.issues[0].lower()


def test_verify_search_missing_fields():
    output = {
        "results": [
            {"title": "Job 1"},  # missing url
        ]
    }
    res = verify_tool_output("search", output)
    assert not res.verified
    assert "missing url" in res.issues[0].lower()


def test_verify_scrape_valid():
    output = {
        "pages": [
            {"url": "https://example.com/1", "text": "Some scraped content"}
        ]
    }
    res = verify_tool_output("scrape", output)
    assert res.verified


def test_verify_scrape_empty():
    res = verify_tool_output("scrape", {"pages": []})
    assert not res.verified
    assert "no pages" in res.issues[0].lower()


def test_verify_job_matcher():
    output = {
        "job_matches": [
            {"title": "Dev", "url": "https://jobs.example.com/1"}
        ]
    }
    res = verify_tool_output("job_matcher", output)
    assert res.verified


def test_verify_resume_analyzer():
    res_valid = verify_tool_output("resume_analyzer", {"analysis": {"skills": ["Python"]}})
    assert res_valid.verified

    res_invalid = verify_tool_output("resume_analyzer", {"analysis": "not-a-dict"})
    assert not res_invalid.verified


def test_verify_generic_tool():
    res = verify_tool_output("logger", {"logged": "All done"})
    assert res.verified
