"""Unit tests for tool adapters."""
import tempfile
from pathlib import Path
from src.tools.search_tool import run as search_run
from src.tools.scraper_tool import run as scraper_run
from src.tools.summarizer_tool import run as summarizer_run
from src.tools.email_tool import run as email_run
from src.tools.logger_tool import run as logger_run
from src.tools.resume_parser_tool import run as parser_run
from src.tools.resume_analyzer_tool import run as analyzer_run
from src.tools.job_matcher_tool import run as matcher_run


def test_search_tool_fallback():
    logs, output = search_run({"query": "python developer", "limit": 3}, {})
    assert "results" in output
    assert len(output["results"]) == 3
    assert output["results"][0]["title"]
    assert output["results"][0]["url"]


def test_scraper_tool_with_context():
    context = {
        "step_1_output": {
            "results": [
                {"title": "Example", "url": "https://example.com"}
            ]
        }
    }
    # Basic scraping without network failure or fallback
    logs, output = scraper_run({"top_k": 1}, context)
    assert "pages" in output


def test_summarizer_tool_extractive():
    context = {
        "step_1_output": {
            "results": [
                {"snippet": "Python is a popular programming language. It is used in web and AI. Great community."}
            ]
        }
    }
    logs, output = summarizer_run({"max_sentences": 2}, context)
    assert "summary" in output
    assert "Python" in output["summary"]


def test_email_tool_simulation():
    context = {"step_1_output": {"summary": "Here are the top jobs found."}}
    logs, output = email_run({"to": "test@example.com", "subject": "Test Jobs"}, context)
    assert output.get("email_sent") is False  # Simulated when SMTP is not configured
    assert output.get("to") == "test@example.com"


def test_logger_tool():
    logs, output = logger_run({"message": "Task complete"}, {})
    assert output["logged"] == "Task complete"
    assert "LOG: Task complete" in logs[0]


def test_resume_parser_txt():
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as tf:
        tf.write("Jane Doe\nSenior Python Engineer\nSkills: Python, FastAPI, Docker")
        temp_path = tf.name

    try:
        logs, output = parser_run({"file_path": temp_path}, {})
        assert output.get("resume_text")
        assert "Jane Doe" in output["resume_text"]
        assert output["word_count"] > 0
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_resume_analyzer_basic():
    context = {
        "parsed": {
            "resume_text": "Jane Doe. Experienced Python and Docker engineer. Computer Science degree."
        }
    }
    logs, output = analyzer_run({}, context)
    assert "analysis" in output
    analysis = output["analysis"]
    assert "skills" in analysis
    assert any("python" in s.lower() for s in analysis["skills"])


def test_job_matcher():
    context = {
        "resume_analysis": {
            "analysis": {
                "field_of_study": "Python Engineer",
                "skills": ["Python", "FastAPI"],
                "job_keywords": ["python", "backend"],
            }
        }
    }
    logs, output = matcher_run({"limit": 5}, context)
    assert "job_matches" in output
    assert len(output["job_matches"]) > 0
