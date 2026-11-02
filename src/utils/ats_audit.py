"""Transparent, text-based resume checks inspired by public ATS tooling.

This reports heuristic parseability and writing checks, not a vendor ATS score.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")
DATE_RE = re.compile(r"\b(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s*)?(?:19|20)\d{2}(?:\s*(?:-|–|—|to)\s*(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s*)?(?:(?:19|20)\d{2}|present|current))?\b", re.I)
BULLET_RE = re.compile(r"^\s*[•●▪◦*\-–—]\s+\S")
SECTION_PATTERNS = {
    "summary": re.compile(r"^(?:professional\s+)?(?:summary|profile|objective|about(?:\s+me)?)$", re.I),
    "experience": re.compile(r"^(?:(?:professional|work|employment)\s+)?(?:experience|history|internships?)(?:\s*&\s*internships?)?$", re.I),
    "education": re.compile(r"^(?:education|academic(?:\s+background)?|qualifications?)$", re.I),
    "skills": re.compile(r"^(?:(?:technical|core|key)\s+)?skills(?:\s*&\s*tools)?$", re.I),
    "projects": re.compile(r"^(?:selected\s+)?(?:personal\s+|academic\s+|technical\s+)?projects?(?:\s*&\s*(?:research|work))?$", re.I),
    "certifications": re.compile(r"^(?:certifications?|licenses?)$", re.I),
}
ACTION_VERBS = set("achieved analyzed automated built created delivered designed developed established improved implemented launched led maintained optimized organized reduced researched secured streamlined tested upgraded wrote configured deployed documented investigated resolved integrated".split())
BUZZWORDS = set("hardworking go-getter guru ninja rockstar passionate results-driven team-player self-starter".split())
STOP_WORDS = set("a an and are as at be been being by can could did do does for from had has have in into is it its may might of on or our should that the their then there these they this to was were will with would your required responsibilities requirements skills ability strong experience role candidate company team looking work job ideal preferred nice must including using".split())


def _check(check_id: str, category: str, title: str, status: str, detail: str) -> dict[str, str]:
    return {"id": check_id, "category": category, "title": title, "status": status, "detail": detail}


def _category_score(checks: list[dict[str, str]]) -> int | None:
    points = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    applicable = [item for item in checks if item["status"] != "not_applicable"]
    if not applicable:
        return None
    return round(sum(points.get(item["status"], 0.0) for item in applicable) / len(applicable) * 100)


def _job_keywords(job_description: str) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9+#.-]{1,}", job_description.casefold())
    counts = Counter(token.strip(".-") for token in tokens)
    return [word for word, _ in counts.most_common() if len(word) >= 2 and word not in STOP_WORDS][:30]


def audit_resume(resume_text: str, job_description: str = "") -> dict[str, Any]:
    """Return transparent text-level checks. Does not claim to emulate a vendor ATS."""
    text = str(resume_text or "")
    lines = [line.strip() for line in text.replace("\r", "").splitlines() if line.strip()]
    words = re.findall(r"\b[\w+#.-]+\b", text, re.UNICODE)
    word_count = len(words)
    bullets = [line for line in lines if BULLET_RE.match(line)]
    headings = {name for name, pattern in SECTION_PATTERNS.items() if any(pattern.fullmatch(line.strip().rstrip(":")) for line in lines)}
    email_found = bool(EMAIL_RE.search(text))
    phone_found = any(10 <= len(re.sub(r"\D", "", candidate)) <= 14 for candidate in PHONE_RE.findall(text))
    link_found = bool(re.search(r"(?:https?://|www\.)\S+", text, re.I))
    sections = {}
    active_section = None
    for line in lines:
        matched_section = next((name for name, pattern in SECTION_PATTERNS.items() if pattern.fullmatch(line.strip().rstrip(":"))), None)
        if matched_section:
            active_section = matched_section
            sections.setdefault(active_section, [])
        elif active_section:
            sections[active_section].append(line)
    experience_present = "experience" in sections and bool(sections["experience"])
    date_found = bool(DATE_RE.search("\n".join(sections.get("experience", []))))
    corrupted = any(char == "\ufffd" or "\ue000" <= char <= "\uf8ff" or (ord(char) < 32 and char not in "\n\t\r") for char in text)
    action_bullets = [line for line in bullets if re.sub(r"^\s*[•●▪◦*\-–—]+\s*", "", line).split(maxsplit=1) and re.sub(r"^\s*[•●▪◦*\-–—]+\s*", "", line).split(maxsplit=1)[0].strip(".,:;()[]{}\"'").casefold() in ACTION_VERBS]
    quantified_bullets = [line for line in bullets if re.search(r"(?:\d|%|\$|₹|\b(?:million|thousand|hours?|users?|clients?)\b)", line, re.I)]
    long_bullets = [line for line in bullets if len(line) > 220]
    first_person = bool(re.search(r"\b(?:I|me|my|mine|we|our|ours)\b", text, re.I))
    buzzword_hits = sorted({word for word in BUZZWORDS if re.search(r"\b" + re.escape(word) + r"\b", text, re.I)})

    checks = [
        _check("extractable_text", "parseability", "Readable text", "pass" if word_count >= 40 else "warn" if word_count >= 10 else "fail", f"{word_count} words are available to check."),
        _check("readable_characters", "parseability", "Text encoding", "not_applicable" if not text.strip() else "fail" if corrupted else "pass", "No resume text to inspect." if not text.strip() else "Replacement, private-use, or control characters were found." if corrupted else "No corrupted or private-use characters found."),
        _check("standard_headings", "structure", "Recognized section headings", "pass" if len(headings) >= 3 else "warn" if len(headings) else "fail", f"Recognized {len(headings)} standard section headings."),
        _check("contact_details", "structure", "Contact details", "pass" if email_found and (phone_found or link_found) else "warn" if email_found or phone_found or link_found else "fail", "Email, phone, or public profile link detected." if email_found or phone_found or link_found else "No email, phone, or public profile link detected."),
        _check("bullet_structure", "structure", "Scannable achievement bullets", "pass" if len(bullets) >= 3 else "warn" if bullets else "fail", f"Found {len(bullets)} bullet lines; 3 or more are easier to scan."),
        _check("dated_experience", "structure", "Machine-readable experience dates", "pass" if date_found else "warn" if experience_present else "not_applicable", "Date-like ranges were detected." if date_found else "Experience is listed but no recognizable year/date was found." if experience_present else "No work-experience section to date-check."),
        _check("reasonable_length", "structure", "Resume length", "warn" if word_count < 80 or word_count > 1200 else "pass", f"{word_count} words extracted; this is a broad readability check, not a hard ATS limit."),
        _check("action_verbs", "content", "Action-led bullets", "pass" if len(action_bullets) >= 2 else "warn" if bullets else "not_applicable", f"{len(action_bullets)} of {len(bullets)} bullets begin with a recognized action verb."),
        _check("quantified_impact", "content", "Measurable impact", "pass" if quantified_bullets else "warn" if bullets else "not_applicable", f"{len(quantified_bullets)} bullets contain a number, percentage, currency, or scale indicator."),
        _check("bullet_length", "content", "Single-idea bullet length", "not_applicable" if not bullets else "warn" if long_bullets else "pass", f"{len(long_bullets)} bullet(s) exceed 220 characters." if long_bullets else "No bullet exceeds 220 characters."),
        _check("first_person", "content", "Resume-style phrasing", "not_applicable" if not text.strip() else "warn" if first_person else "pass", "First-person pronouns found; resume bullets usually read more clearly without them." if first_person else "No first-person pronouns detected."),
        _check("generic_buzzwords", "content", "Specific language", "not_applicable" if not text.strip() else "warn" if buzzword_hits else "pass", "Consider replacing: " + ", ".join(buzzword_hits) + "." if buzzword_hits else "No common empty buzzwords detected."),
    ]
    categories = {}
    for category in ("parseability", "structure", "content"):
        category_checks = [item for item in checks if item["category"] == category]
        categories[category] = {"score": _category_score(category_checks), "checks": category_checks}
    findings = [item for item in checks if item["status"] in {"warn", "fail"}]
    keyword_match = None
    if job_description.strip():
        keywords = _job_keywords(job_description)
        resume_words = set(re.findall(r"[a-z][a-z0-9+#.-]{1,}", text.casefold()))
        matched = [word for word in keywords if word in resume_words]
        keyword_match = {"score": round(len(matched) / len(keywords) * 100) if keywords else 0, "matched": matched, "missing": [word for word in keywords if word not in resume_words], "matched_count": len(matched), "total": len(keywords), "method": "literal token overlap; no semantic inference"}
    return {
        "label": "AURA rule-based checks",
        "vendor_score": False,
        "categories": categories,
        "keyword_match": keyword_match,
        "word_count": word_count,
        "bullet_count": len(bullets),
        "recognized_sections": sorted(headings),
        "finding_count": len(findings),
        "pass_count": sum(item["status"] == "pass" for item in checks),
        "check_count": sum(item["status"] != "not_applicable" for item in checks),
        "findings": findings,
        "limitations": ["These rules assess extracted text, not any specific ATS vendor.", "A high parseability result does not mean the resume matches a job.", "Keyword match is literal; synonyms and meaning are not inferred."],
    }
