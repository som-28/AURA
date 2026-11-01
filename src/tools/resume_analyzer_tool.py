"""Resume analyzer tool - analyzes resume content using AI."""
from typing import Tuple, List
import json
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
    
    # Use the configured local or hosted LLM, otherwise basic extraction.
    try:
        configured = get_llm_client()
    except Exception as exc:
        configured = None
        logs.append(f"LLM unavailable: {exc}")

    if configured:
        analysis = _analyze_with_ai(resume_text, logs, configured)
        _validate_experience(analysis, resume_text, logs)
    else:
        analysis = _analyze_basic(resume_text, logs)
    
    logs.append(f"Analysis complete - Found {len(analysis.get('skills', []))} skills")
    
    return logs, {"analysis": analysis}


def _analyze_with_ai(resume_text: str, logs: List[str], configured=None) -> dict:
    """Analyze resume using the configured LLM."""
    try:
        configured = configured or get_llm_client()
        if configured is None:
            raise RuntimeError("No LLM is configured")
        client, model, provider_name = configured
        
        prompt = f"""Analyze this resume and extract the following information in JSON format:
1. Name
2. Current role/title
3. Years of professional work experience, based ONLY on explicit employment or internship history and its dates. Exclude the duration of degrees/courses, school, academic years, projects, and time since graduation. If there is no explicit work history, use null. Do not infer experience from education dates.
4. Top 10 skills (technical and soft skills)
5. Education (degrees, institutions)
6. Field of study/specialization
7. Career interests (what kind of roles they'd be interested in)
8. Industry preferences
9. Key achievements
10. Recommended job search keywords

Resume:
{resume_text[:4000]}

For experience, also return experience_evidence: one short, exact verbatim excerpt from the resume's employment/internship history that includes the role and its dates and supports years_experience, or null if there is no such dated work-history evidence. Do not use education text as experience_evidence.

Return ONLY valid JSON with these keys: name, current_role, years_experience (number or null), experience_evidence (string or null), skills, education, field_of_study, career_interests, industries, achievements, job_keywords"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
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
        logs.append(f"AI analysis failed: {e}, using basic extraction")
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
    """Basic keyword-based resume analysis."""
    text_lower = resume_text.lower()
    
    # Common technical skills
    tech_skills = ['python', 'java', 'javascript', 'react', 'node', 'sql', 'aws', 
                   'docker', 'kubernetes', 'machine learning', 'ai', 'data science',
                   'frontend', 'backend', 'fullstack', 'devops', 'cloud']
    
    found_skills = [skill for skill in tech_skills if skill in text_lower]
    
    # Extract education keywords
    education_keywords = ['bachelor', 'master', 'phd', 'mba', 'degree', 'university', 'college']
    has_education = any(keyword in text_lower for keyword in education_keywords)
    
    # Determine field
    field = "Technology"
    if any(word in text_lower for word in ['data', 'analytics', 'ml', 'ai']):
        field = "Data Science / AI"
    elif any(word in text_lower for word in ['web', 'frontend', 'backend', 'fullstack']):
        field = "Web Development"
    elif any(word in text_lower for word in ['devops', 'cloud', 'infrastructure']):
        field = "DevOps / Cloud"
    
    logs.append("Used basic keyword analysis (configure Ollama/Qwen or an OpenAI key for AI analysis)")
    
    return {
        "name": "Candidate",
        "current_role": "Not specified",
        "years_experience": None,
        "experience_evidence": None,
        "skills": found_skills[:10] if found_skills else ["Programming", "Problem Solving"],
        "education": ["Bachelor's Degree"] if has_education else ["Education details in resume"],
        "field_of_study": field,
        "career_interests": [f"{field} roles", "Remote positions", "Growing companies"],
        "industries": ["Technology", "Software", "Startups"],
        "achievements": ["See resume for details"],
        "job_keywords": found_skills[:5] + [field.lower(), "remote", "senior"]
    }
