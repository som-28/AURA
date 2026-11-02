"""Resume analyzer tool - analyzes resume content using AI."""
from typing import Tuple, List
import json
import os
import re
from src.utils.llm_client import get_llm_client


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    """Analyze resume and extract key information.
    
    Args:
        args: {} - Reads resume_text from context
        context: Must contain resume_text from resume_parser
    
    Returns:
        logs, {"analysis": dict with skills, experience, interests, etc.}
    """
    logs = []
    
    # Get resume text from context
    resume_text = None
    for key, value in context.items():
        if isinstance(value, dict) and "resume_text" in value:
            resume_text = value["resume_text"]
            break
    
    if not resume_text:
        logs.append("Error: No resume text found in context")
        return logs, {"error": "No resume text available"}
    
    logs.append("Analyzing resume content...")
    
    # Always build a grounded local profile first. This makes analysis useful
    # even when a small local model is slow, unavailable, or returns weak JSON.
    analysis = _analyze_basic(resume_text, logs)

    # Use the configured local or hosted LLM to enrich the deterministic result.
    try:
        configured = get_llm_client()
    except Exception as exc:
        configured = None
        logs.append(f"LLM unavailable: {exc}")

    if configured:
        enriched = _analyze_with_ai(resume_text, logs, configured)
        _validate_experience(enriched, resume_text, logs)
        analysis = _merge_grounded_analysis(analysis, enriched, resume_text)
    
    logs.append(f"Analysis complete - Found {len(analysis.get('skills', []))} skills")
    
    return logs, {"analysis": analysis}


def _analyze_with_ai(resume_text: str, logs: List[str], configured=None) -> dict:
    """Analyze resume using the configured LLM."""
    try:
        configured = configured or get_llm_client()
        if configured is None:
            raise RuntimeError("No LLM is configured")
        client, model, provider_name = configured
        
        timeout = max(5, min(float(os.getenv("RESUME_ANALYSIS_TIMEOUT", "18")), 45))
        prompt = f"""Extract only facts clearly supported by this resume into JSON:
name, current_role, email, phone, years_experience, experience_evidence,
skills (up to 15), education, field_of_study, career_interests, industries,
achievements (up to 5), job_keywords (up to 10), summary.

Never infer work experience from education, course duration, school years,
projects, or time since graduation. Use null when years of paid/internship work
cannot be supported by explicit employment dates. Do not invent career interests;
use an empty list when unclear. Keep all extracted claims grounded in the text.

Resume:
{resume_text[:4000]}

For experience, also return experience_evidence: one short, exact verbatim excerpt from the resume's employment/internship history that includes the role and its dates and supports years_experience, or null if there is no such dated work-history evidence. Do not use education text as experience_evidence.

Return ONLY valid JSON with these keys: name, current_role, years_experience (number or null), experience_evidence (string or null), skills, education, field_of_study, career_interests, industries, achievements, job_keywords"""

        request_client = client.with_options(timeout=timeout, max_retries=0) if hasattr(client, "with_options") else client
        response = request_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=700,
            **({} if hasattr(client, "with_options") else {"timeout": timeout}),
        )
        
        content = response.choices[0].message.content.strip()
        
        # Extract JSON from markdown if needed
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        analysis = json.loads(content)
        if not isinstance(analysis, dict):
            raise ValueError("AI response must be a JSON object")
        logs.append(f"Used AI analysis ({provider_name})")
        return analysis
        
    except Exception as e:
        logs.append(f"AI enrichment unavailable ({type(e).__name__}); using grounded text extraction")
        return _analyze_basic(resume_text, logs)


def _validate_experience(analysis: dict, resume_text: str, logs: List[str]) -> None:
    """Discard work-year estimates without a verbatim, non-education resume quote."""
    evidence = analysis.get("experience_evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        analysis["years_experience"] = None
        logs.append("No explicit employment evidence found; work experience left unspecified")
        return

    def normalized(value: str) -> str:
        return re.sub(r"\W+", " ", value.casefold()).strip()

    normalized_evidence = normalized(evidence)
    normalized_resume = normalized(resume_text)
    education_terms = re.compile(
        r"\b(b[\W_]*tech|bachelor|degree|university|college|course|education|student|academic|semester)\b",
        re.IGNORECASE,
    )
    raw_years = analysis.get("years_experience")
    try:
        years = float(raw_years) if raw_years is not None and not isinstance(raw_years, bool) else 0
    except (TypeError, ValueError):
        years = 0

    evidence_is_grounded = normalized_evidence and normalized_evidence in normalized_resume
    evidence_has_work_dates = bool(re.search(r"\b(?:19|20)\d{2}\b", evidence))
    evidence_is_education = bool(education_terms.search(evidence))
    if not evidence_is_grounded or not evidence_has_work_dates or evidence_is_education or years <= 0:
        analysis["years_experience"] = None
        logs.append("Experience estimate lacked verified employment evidence and was removed")
        return

    analysis["years_experience"] = round(years, 1)


def _analyze_basic(resume_text: str, logs: List[str]) -> dict:
    """Fast, conservative extraction from resume text without model inference."""
    text = resume_text.strip()
    text_lower = text.casefold()
    lines = [re.sub(r"\s+", " ", line).strip(" \t|·") for line in text.splitlines()]
    lines = [line for line in lines if line]
    headings = {"summary", "profile", "objective", "experience", "work experience", "employment", "education", "skills", "technical skills", "projects", "certifications"}
    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    phone_match = re.search(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)", text)
    name = ""
    for line in lines[:8]:
        words = line.split()
        if (2 <= len(words) <= 4 and len(line) <= 60 and not re.search(r"[@\d]|https?://|www\.", line)
                and line.casefold() not in headings and not any(word.casefold() in {"engineer", "developer", "analyst", "student", "resume", "curriculum"} for word in words)):
            name = line
            break

    skill_catalog = (
        "python", "java", "javascript", "typescript", "c++", "sql", "html", "css", "react", "node.js", "fastapi", "django",
        "aws", "azure", "gcp", "docker", "kubernetes", "git", "linux", "windows", "kali linux", "vmware", "wireshark",
        "bettercap", "nmap", "burp suite", "metasploit", "bash", "powershell", "networking", "tcp/ip", "dns", "arp", "nat",
        "cybersecurity", "siem", "splunk", "qradar", "incident response", "threat hunting", "vulnerability management",
        "machine learning", "data analysis", "pandas", "communication", "project management", "tryhackme", "owasp",
    )
    found_skills = [skill for skill in skill_catalog if re.search(rf"(?<![\w+#]){re.escape(skill)}(?![\w+#])", text_lower)]
    skill_section = _section_text(lines, {"skills", "technical skills", "core skills", "technologies"})
    for candidate in re.split(r"[,;|•·\n]+", skill_section):
        candidate = re.sub(r"^\s*[-*]\s*", "", candidate).strip()
        if 1 < len(candidate) <= 40 and len(candidate.split()) <= 5 and not re.search(r"[@/]", candidate):
            if candidate.casefold() not in {item.casefold() for item in found_skills}:
                found_skills.append(candidate)

    education = _section_lines(lines, {"education", "academic background", "qualifications"})
    experience_lines = _section_lines(lines, {"experience", "work experience", "employment", "professional experience", "internships"})
    project_lines = _section_lines(lines, {"projects", "selected projects", "personal projects"})
    summary_lines = _section_lines(lines, {"summary", "profile", "professional summary", "objective"})
    title = next((line for line in lines[:10] if line != name and not re.search(r"[@]|https?://|\b\d{4}\b|\+?\d[\d ()-]{7,}", line) and line.casefold() not in headings and len(line) <= 90), "")
    field = "Cybersecurity" if any(word in text_lower for word in ("cybersecurity", "wireshark", "siem", "threat hunting")) else ""
    if not field and any(word in text_lower for word in ("computer science", "b.tech", "bachelor of technology")):
        field = "Computer Science"
    elif not field and any(word in text_lower for word in ("data analysis", "machine learning", "data science")):
        field = "Data Science"

    # Only dated work-history evidence counts; education and project dates are excluded.
    dated_work = [line for line in experience_lines if re.search(r"\b(?:19|20)\d{2}\b", line)]
    years_experience = None
    experience_evidence = None
    if dated_work:
        month_numbers = {name.casefold(): index for index, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
        month_numbers.update({name[:3].casefold(): index for index, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)})
        date_values = []
        month_precision = False
        for line in dated_work:
            matches = list(re.finditer(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)?\s*,?\s*((?:19|20)\d{2})\b", line, re.I))
            if len(matches) >= 2 and matches[0].group(1) and matches[-1].group(1):
                month_precision = True
            for match in matches:
                month = month_numbers.get((match.group(1) or "").casefold(), 1)
                date_values.append(int(match.group(2)) * 12 + month)
        if len(date_values) >= 2:
            elapsed_months = max(0, max(date_values) - min(date_values)) + int(month_precision)
            years_experience = round(elapsed_months / 12, 1)
            if years_experience > 0:
                experience_evidence = dated_work[0][:220]

    achievements = []
    for line in experience_lines + project_lines:
        bullet = re.sub(r"^\s*[-*•]\s*", "", line).strip()
        if len(bullet) >= 25 and bullet.casefold() not in headings:
            achievements.append(bullet)
    summary = " ".join(summary_lines[:4])[:700]
    logs.append("Used fast, grounded text extraction")
    return {
        "name": name or "", "current_role": title, "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "", "years_experience": years_experience,
        "experience_evidence": experience_evidence, "skills": found_skills[:20], "education": education[:8],
        "field_of_study": field, "career_interests": [], "industries": [], "achievements": achievements[:8],
        "job_keywords": found_skills[:12], "summary": summary,
    }


def _section_lines(lines: list[str], names: set[str]) -> list[str]:
    active = False
    result = []
    for line in lines:
        heading = re.sub(r"[^a-z ]", "", line.casefold()).strip()
        if heading in names:
            active = True
            continue
        if heading in {"summary", "profile", "objective", "experience", "work experience", "employment", "professional experience", "internships", "education", "academic background", "qualifications", "skills", "technical skills", "core skills", "technologies", "projects", "selected projects", "personal projects", "certifications"}:
            if active:
                break
        if active:
            result.append(line)
    return result


def _section_text(lines: list[str], names: set[str]) -> str:
    return "\n".join(_section_lines(lines, names))


def _merge_grounded_analysis(base: dict, enriched: dict, resume_text: str) -> dict:
    """Use model values only when they are useful and supported by the source text."""
    merged = dict(base)
    normalized_text = re.sub(r"\s+", " ", resume_text).casefold()
    for key in ("name", "current_role", "email", "phone", "field_of_study", "summary"):
        candidate = enriched.get(key)
        if isinstance(candidate, str) and candidate.strip() and candidate.strip().casefold() in normalized_text:
            merged[key] = candidate.strip()
    for key in ("skills", "education", "achievements", "job_keywords", "career_interests", "industries"):
        values = enriched.get(key)
        if isinstance(values, list):
            grounded = [str(value).strip() for value in values if isinstance(value, (str, int, float)) and str(value).strip() and str(value).strip().casefold() in normalized_text]
            if grounded:
                merged[key] = list(dict.fromkeys([*grounded, *merged.get(key, [])]))[:20]
    if enriched.get("years_experience") is not None and enriched.get("experience_evidence"):
        merged["years_experience"] = enriched["years_experience"]
        merged["experience_evidence"] = enriched["experience_evidence"]
    return merged
