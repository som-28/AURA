"""Regression tests for AURA's transparent resume checks."""
import unittest

from src.utils.ats_audit import audit_resume

CLEAN_RESUME = """Jordan Example
jordan@example.com | +91 9876543210 | https://github.com/jordan

SUMMARY
Cybersecurity graduate focused on network defense and automation.

EXPERIENCE
Security Intern | Example Labs | Jan 2024 – Aug 2024
• Built a Python scanner that identified 42 exposed services.
• Reduced manual triage time by 30% through automated reports.
• Documented incident response steps for a 5-person team.

EDUCATION
B.Tech in Computer Science | Example Institute | 2020 – 2024

SKILLS
Python, Linux, Wireshark, SIEM, Networking

PROJECTS
Home Lab
• Configured virtual machines for safe security practice.
• Analyzed traffic with Wireshark and wrote detection notes.
"""


class ResumeAuditTests(unittest.TestCase):
    def test_clean_resume_has_transparent_dimension_scores_and_no_findings(self):
        report = audit_resume(CLEAN_RESUME)
        self.assertFalse(report["vendor_score"])
        self.assertEqual(report["finding_count"], 0)
        self.assertEqual(report["categories"]["parseability"]["score"], 100)
        self.assertEqual(report["categories"]["structure"]["score"], 100)
        self.assertEqual(report["categories"]["content"]["score"], 100)
        self.assertIsNone(report["keyword_match"])

    def test_sparse_or_image_only_text_fails_extractability_and_contact(self):
        report = audit_resume("SCAN")
        by_id = {item["id"]: item for item in report["findings"]}
        self.assertEqual(by_id["extractable_text"]["status"], "fail")
        self.assertEqual(by_id["contact_details"]["status"], "fail")
        self.assertEqual(by_id["standard_headings"]["status"], "fail")

    def test_education_dates_do_not_satisfy_missing_work_dates(self):
        text = "EDUCATION\nB.Tech | Example College | 2020 – 2024\nEXPERIENCE\nBuilt a tool for users."
        report = audit_resume(text)
        by_id = {item["id"]: item for item in report["findings"]}
        self.assertEqual(by_id["dated_experience"]["status"], "warn")

    def test_corrupted_symbol_font_characters_are_flagged(self):
        report = audit_resume(CLEAN_RESUME.replace("Configured", "Con\ue000figured"))
        by_id = {item["id"]: item for item in report["findings"]}
        self.assertEqual(by_id["readable_characters"]["status"], "fail")

    def test_long_bullet_and_first_person_are_actionable_warnings(self):
        text = CLEAN_RESUME.replace("Built a Python scanner", "I built a Python scanner") + "\n• " + ("Detailed work " * 30)
        report = audit_resume(text)
        by_id = {item["id"]: item for item in report["findings"]}
        self.assertEqual(by_id["first_person"]["status"], "warn")
        self.assertEqual(by_id["bullet_length"]["status"], "warn")

    def test_job_description_match_is_literal_and_separate_from_parseability(self):
        report = audit_resume(CLEAN_RESUME, "Python Python PostgreSQL Kubernetes")
        self.assertEqual(report["keyword_match"]["score"], 33)
        self.assertEqual(report["keyword_match"]["matched"], ["python"])
        self.assertIn("kubernetes", report["keyword_match"]["missing"])
        self.assertEqual(report["categories"]["parseability"]["score"], 100)


    def test_empty_editor_has_no_inflated_writing_score(self):
        report = audit_resume("")
        self.assertIsNone(report["categories"]["content"]["score"])
        self.assertLessEqual(report["categories"]["structure"]["score"], 15)



if __name__ == "__main__":
    unittest.main()
