"""Evidence-based career fit scoring and transparent skill-gap plans."""
from __future__ import annotations

import re


SKILL_CATALOG = (
    "python", "javascript", "typescript", "java", "c++", "sql", "excel", "linux", "windows",
    "aws", "azure", "gcp", "docker", "kubernetes", "git", "react", "node.js", "fastapi",
    "django", "machine learning", "data analysis", "pandas", "networking", "tcp/ip", "siem",
    "splunk", "qradar", "microsoft sentinel", "arcsight", "soar", "incident response",
    "threat hunting", "vulnerability management", "soc 2", "nist", "mitre att&ck", "cybersecurity",
    "communication", "project management", "power bi", "tableau", "html", "css", "rest api",
)


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9+#. ]+", " ", text.casefold()).strip()


def _has_phrase(text: str, phrase: str) -> bool:
    target = _normal(phrase)
    return bool(target and re.search(rf"(?<![a-z0-9]){re.escape(target)}(?![a-z0-9])", _normal(text)))


def required_skills(job: dict) -> list[str]:
    text = " ".join(str(job.get(key) or "") for key in ("title", "snippet", "company"))
    return [skill for skill in SKILL_CATALOG if _has_phrase(text, skill)]


def score_role(profile: dict, job: dict, preferred_location: str = "") -> dict:
    skills = [str(item) for item in profile.get("skills", []) if str(item).strip()]
    interests = [str(item) for item in profile.get("career_interests", []) if str(item).strip()]
    requirements = required_skills(job)
    matched_requirements = [skill for skill in requirements if any(_has_phrase(candidate, skill) or _has_phrase(skill, candidate) for candidate in skills)]
    matched = []
    for requirement in matched_requirements:
        candidate = next((item for item in skills if _has_phrase(item, requirement) or _has_phrase(requirement, item)), requirement)
        if candidate not in matched:
            matched.append(candidate)
    missing = [skill for skill in requirements if skill not in matched_requirements]

    skill_score = (len(matched_requirements) / len(requirements) * 55) if requirements else min(35, len(skills) * 5)
    role_text = _normal(f"{job.get('title', '')} {job.get('snippet', '')}")
    interest_terms = [term for interest in interests for term in re.findall(r"[a-z0-9+#.]+", _normal(interest)) if len(term) > 2]
    role_hits = sorted({term for term in interest_terms if term in role_text})
    role_score = min(25, (len(role_hits) / max(1, min(4, len(set(interest_terms)))) * 25)) if interest_terms else 8

    requested_location = preferred_location.strip().casefold()
    job_location = str(job.get("location") or "").casefold()
    work_mode = str(job.get("work_mode") or "").casefold()
    if not requested_location or requested_location in {"anywhere", "any location"}:
        location_score = 10
        location_reason = "No location constraint"
    elif requested_location in job_location or requested_location in work_mode or (requested_location == "remote" and "remote" in f"{job_location} {work_mode} {job.get('snippet', '')}".casefold()):
        location_score = 10
        location_reason = f"Location aligns with {preferred_location}"
    elif not job_location and not work_mode:
        location_score = 5
        location_reason = "Location is not stated"
    else:
        location_score = 0
        location_reason = f"Location may not match {preferred_location}"

    candidate_years = profile.get("years_experience")
    job_text = " ".join(str(job.get(key) or "") for key in ("title", "snippet"))
    min_years = None
    match = re.search(r"(?:minimum|min\.?|at least|\b)(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of\s+experience)?", job_text, re.I)
    if match:
        min_years = float(match.group(1))
    experience_reason = "Experience requirement is not explicit"
    experience_score = 10
    if min_years is not None and candidate_years is None:
        experience_reason = f"Role asks for {min_years:g}+ years; profile experience is unverified"
        experience_score = 4
    elif min_years is not None:
        candidate_value = float(candidate_years)
        if candidate_value >= min_years:
            experience_reason = f"Experience meets the stated {min_years:g}+ year requirement"
        else:
            experience_score = max(0, round(10 * candidate_value / max(min_years, 1)))
            experience_reason = f"Role asks for {min_years:g}+ years; profile shows {candidate_value:g}"

    total = round(max(0, min(100, skill_score + role_score + location_score + experience_score)))
    reasons = []
    reasons.append(f"{len(matched)} of {len(requirements)} stated skills match" if requirements else "Job description has no clearly listed skills to compare")
    if role_hits:
        reasons.append(f"Role aligns with: {', '.join(role_hits[:4])}")
    reasons.append(location_reason)
    reasons.append(experience_reason)
    return {
        "fit_score": total,
        "fit_label": "Strong fit" if total >= 75 else "Potential fit" if total >= 50 else "Stretch role",
        "matched_skills": matched,
        "missing_skills": missing,
        "required_skills": requirements,
        "fit_reasons": reasons,
        "fit_confidence": "provisional" if not requirements or candidate_years is None else "based on stated requirements",
    }


def build_skill_plan(job: dict, profile: dict) -> dict:
    scored = score_role(profile, job, str(job.get("preferred_location") or ""))
    gaps = scored["missing_skills"]
    title = str(job.get("title") or "your target role")
    if not gaps:
        return {
            "title": title,
            "status": "No explicit skill gaps found",
            "note": "This is based only on skills stated in the profile and job description; it does not confirm practical proficiency.",
            "steps": [{"title": "Validate with evidence", "detail": f"Choose one real project or work example for each matched skill before using it in an application for {title}."}],
        }
    steps = []
    for index, skill in enumerate(gaps, 1):
        steps.append({
            "title": f"Build evidence for {skill}",
            "detail": f"Learn the core workflow for {skill}, then create one small project or lab that demonstrates it in a context relevant to {title}. Keep a link and a short explanation of what you personally completed.",
            "order": index,
        })
    steps.append({
        "title": "Update your profile honestly",
        "detail": "Add a skill to your resume only after you have completed work that supports the claim; link the project or evidence where possible.",
        "order": len(steps) + 1,
    })
    return {"title": title, "status": f"{len(gaps)} stated skill gaps", "note": "Gaps are detected from the job text and your extracted resume skills; this is a practical draft, not a qualification verdict.", "steps": steps}
