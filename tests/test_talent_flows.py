"""Focused regression tests for the Talent page's resume and matching flows."""
import unittest
import sys
import os
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.agent.career_store import CareerStore
from src.tools import resume_analyzer_tool
from src.tools.resume_analyzer_tool import _analyze_basic, _analyze_with_ai, _merge_grounded_analysis, _validate_experience
from src.tools.job_matcher_tool import run as match_resume


SAMPLE_RESUME = """Somnath Chaudhary
somnath@example.com | +91 98765 43210 | Delhi
Cybersecurity Student

SUMMARY
Computer Science student building hands-on cybersecurity labs and CTF write-ups.

SKILLS
Wireshark, Bettercap, Kali Linux, VMware, Python, Bash, Networking

EXPERIENCE
Cybersecurity Intern | SecureCo | Jan 2024 - Dec 2024
- Investigated 25 network alerts using Wireshark and documented findings.

EDUCATION
B.Tech Computer Science | 2022 - 2026

PROJECTS
Cybersecurity Home Lab | 2024
- Built a VMware lab with Kali Linux and Windows for controlled traffic analysis.
"""


class TalentResumeExtractionTests(unittest.TestCase):
    def test_extracts_contact_skills_summary_and_dated_work_only(self):
        analysis = _analyze_basic(SAMPLE_RESUME, [])
        self.assertEqual(analysis["name"], "Somnath Chaudhary")
        self.assertEqual(analysis["email"], "somnath@example.com")
        self.assertIn("98765", analysis["phone"])
        self.assertEqual(analysis["years_experience"], 1.0)
        self.assertEqual(analysis["experience_evidence"], "Cybersecurity Intern | SecureCo | Jan 2024 - Dec 2024")
        self.assertTrue({"wireshark", "bettercap", "kali linux", "vmware", "python", "bash"}.issubset({skill.casefold() for skill in analysis["skills"]}))
        self.assertIn("hands-on cybersecurity labs", analysis["summary"])
        self.assertNotIn("remote positions", analysis["career_interests"])

    def test_degree_years_are_not_misread_as_work_experience(self):
        text = "Somnath Chaudhary\nB.Tech Computer Science\nEDUCATION\n2022 - 2026"
        analysis = _analyze_basic(text, [])
        self.assertIsNone(analysis["years_experience"])
        self.assertIsNone(analysis["experience_evidence"])

    def test_ai_enrichment_cannot_replace_grounded_fields_with_placeholders(self):
        base = _analyze_basic(SAMPLE_RESUME, [])
        bad_ai = {"name": "Candidate", "skills": ["Unicorn framework"], "career_interests": ["Senior remote roles"]}
        merged = _merge_grounded_analysis(base, bad_ai, SAMPLE_RESUME)
        self.assertEqual(merged["name"], "Somnath Chaudhary")
        self.assertNotIn("Unicorn framework", merged["skills"])
        self.assertEqual(merged["career_interests"], [])

    def test_unverified_model_experience_is_removed(self):
        analysis = {"years_experience": 4, "experience_evidence": "B.Tech 2022-2026"}
        logs = []
        _validate_experience(analysis, SAMPLE_RESUME, logs)
        self.assertIsNone(analysis["years_experience"])
        self.assertTrue(logs)

    def test_ai_request_uses_a_short_single_attempt_timeout(self):
        class Client:
            def __init__(self):
                self.options = None
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def with_options(self, **options):
                self.options = options
                return self

            def create(self, **kwargs):
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"name":"Somnath Chaudhary","skills":["Python"]}'))])

        client = Client()
        logs = []
        with patch.dict(os.environ, {"RESUME_ANALYSIS_TIMEOUT": "9"}):
            result = _analyze_with_ai(SAMPLE_RESUME, logs, (client, "qwen2.5:3b", "Ollama/Qwen"))
        self.assertEqual(client.options, {"timeout": 9.0, "max_retries": 0})
        self.assertEqual(result["name"], "Somnath Chaudhary")

    def test_ai_timeout_falls_back_to_useful_extraction(self):
        class SlowClient:
            def with_options(self, **options):
                raise TimeoutError("simulated slow local model")

        with patch.object(resume_analyzer_tool, "get_llm_client", return_value=(SlowClient(), "qwen2.5:3b", "Ollama/Qwen")):
            logs, output = resume_analyzer_tool.run({}, {"resume_data": {"resume_text": SAMPLE_RESUME}})
        self.assertEqual(output["analysis"]["email"], "somnath@example.com")
        self.assertIn("wireshark", {skill.casefold() for skill in output["analysis"]["skills"]})
        self.assertTrue(any("AI enrichment unavailable" in entry for entry in logs))


class TalentMatchingTests(unittest.TestCase):
    def test_matching_uses_target_role_and_keywords_before_academic_field(self):
        seen = {}

        def fake_search(args, context):
            seen.update(args)
            return ["stubbed provider"], {"search_available": True, "results": [{
                "title": "SOC Analyst - Entry Level", "url": "https://jobs.example/soc",
                "snippet": "SOC Analyst using SIEM, Splunk, Python and incident response.",
                "company": "Example Security", "location": "Delhi", "work_mode": "Hybrid",
            }]}

        profile = {"field_of_study": "Computer Science", "skills": ["Python", "SIEM"], "job_keywords": ["networking"], "career_interests": []}
        with patch.dict(sys.modules, {"src.tools.search_tool": type("SearchStub", (), {"run": staticmethod(fake_search)})}):
            logs, result = match_resume({"location": "Delhi", "target_role": "SOC Analyst Fresher", "keywords": "SIEM, Splunk", "work_mode": "hybrid", "min_salary": 400000, "limit": 10}, {"resume_analysis": {"analysis": profile}})

        self.assertEqual(seen["query"], "SOC Analyst Fresher SIEM Splunk Python hybrid 4 LPA jobs Delhi")
        self.assertNotIn("Computer Science", seen["query"])
        self.assertEqual(len(result["job_matches"]), 1)
        self.assertEqual(result["job_matches"][0]["matched_skills"], ["Python", "SIEM"])

    def test_no_target_role_falls_back_to_profile_keywords_not_empty_query(self):
        seen = {}

        def fake_search(args, context):
            seen.update(args)
            return [], {"search_available": False, "message": "Provider not configured", "results": []}

        with patch.dict(sys.modules, {"src.tools.search_tool": type("SearchStub", (), {"run": staticmethod(fake_search)})}):
            _, result = match_resume({}, {"resume_analysis": {"analysis": {"skills": ["Wireshark"], "job_keywords": ["SOC analyst", "SIEM"]}}})

        self.assertIn("SOC analyst", seen["query"])
        self.assertIn("Wireshark", seen["query"])
        self.assertFalse(result["job_matches"])
        self.assertIn("Provider not configured", result["message"])


class TalentPreferenceStoreTests(unittest.TestCase):
    def test_preferences_round_trip_and_salary_type(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            store = CareerStore(f"{directory}/career.json")
            saved = store.save_preferences({"target_role": "SOC Analyst Fresher", "location": "Delhi", "keywords": "SIEM, Splunk", "min_salary": 400000, "work_mode": "hybrid"})
            self.assertEqual(saved["target_role"], "SOC Analyst Fresher")
            self.assertEqual(store.preferences()["min_salary"], 400000.0)
            profile = store.save_profile({"name": "Test Person", "email": "person@example.com", "phone": "+91 1234567890", "links": [{"label": "Portfolio", "url": "https://example.com"}], "unused": "discarded"})
            self.assertEqual(profile["email"], "person@example.com")
            self.assertEqual(profile["links"][0]["label"], "Portfolio")
            self.assertNotIn("unused", profile)

    def test_resume_and_contact_details_persist_across_store_instances(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            store_path = f"{directory}/career.json"
            store = CareerStore(store_path)
            first = store.save_resume(b"First resume version", "somnath_resume.txt")
            self.assertEqual(first["original_name"], "somnath_resume.txt")
            self.assertEqual(store.resume_path().read_bytes(), b"First resume version")
            store.save_identity({"name": "Somnath", "email": "somnath@example.com", "phone": "+91 9876543210"})

            restarted_store = CareerStore(store_path)
            self.assertEqual(restarted_store.profile()["email"], "somnath@example.com")
            self.assertEqual(restarted_store.resume_info()["original_name"], "somnath_resume.txt")
            self.assertEqual(restarted_store.resume_path().read_bytes(), b"First resume version")

            second = restarted_store.save_resume(b"Replacement resume", "updated_resume.txt")
            self.assertEqual(second["original_name"], "updated_resume.txt")
            self.assertEqual(restarted_store.resume_path().read_bytes(), b"Replacement resume")
            self.assertEqual(len(list(restarted_store.resume_directory.iterdir())), 1)


class SearchProviderDiagnosticsTests(unittest.TestCase):
    def _load_search_tool(self, fake_requests):
        module_path = Path(__file__).resolve().parents[1] / "src" / "tools" / "search_tool.py"
        spec = importlib.util.spec_from_file_location("isolated_search_tool_test", module_path)
        search_module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"requests": fake_requests}):
            spec.loader.exec_module(search_module)
        return search_module

    def test_provider_quota_failure_is_explained_without_exposing_credentials(self):
        fake_requests = SimpleNamespace(get=lambda *args, **kwargs: SimpleNamespace(status_code=429, json=lambda: {}))
        with patch.dict(sys.modules, {"requests": fake_requests}), patch.dict(os.environ, {"SERPAPI_KEY": "secret-test-value", "GOOGLE_SEARCH_API_KEY": "", "GOOGLE_SEARCH_ENGINE_ID": ""}):
            search_module = self._load_search_tool(fake_requests)
            _, result = search_module.run({"query": "SOC Analyst jobs Delhi", "limit": 2}, {})
        self.assertFalse(result["search_available"])
        self.assertIn("quota or rate limit", result["message"])
        self.assertNotIn("secret-test-value", result["message"])

    def test_job_search_results_exclude_board_search_pages_but_keep_openings(self):
        search_module = self._load_search_tool(SimpleNamespace())
        items = [
            {"title": "SOC Analyst jobs in Delhi", "url": "https://in.indeed.com/q-soc-analyst-l-delhi-jobs.html", "snippet": "Browse SOC Analyst positions"},
            {"title": "SOC Analyst openings", "url": "https://www.shine.com/job-search/soc-analyst-l1-permanent-jobs", "snippet": "Search current SOC Analyst openings"},
            {"title": "SOC Analyst", "url": "https://in.indeed.com/viewjob?jk=abc123", "snippet": "SOC Analyst hiring for SIEM monitoring in Delhi"},
        ]
        results = search_module._curate_results("SOC Analyst jobs Delhi", items, 5, "test")
        self.assertEqual([item["url"] for item in results], ["https://in.indeed.com/viewjob?jk=abc123"])


if __name__ == "__main__":
    unittest.main()
