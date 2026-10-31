"""Resume analyzer tool - analyzes resume content using AI."""
from typing import Tuple, List
import os
import json


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
    
    # Use OpenAI if available, otherwise basic extraction
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if openai_key:
        analysis = _analyze_with_ai(resume_text, logs)
    else:
        analysis = _analyze_basic(resume_text, logs)
    
    logs.append(f"Analysis complete - Found {len(analysis.get('skills', []))} skills")
    
    return logs, {"analysis": analysis}


def _analyze_with_ai(resume_text: str, logs: List[str]) -> dict:
    """Analyze resume using OpenAI."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""Analyze this resume and extract the following information in JSON format:
1. Name
2. Current role/title
3. Years of experience (estimate)
4. Top 10 skills (technical and soft skills)
5. Education (degrees, institutions)
6. Field of study/specialization
7. Career interests (what kind of roles they'd be interested in)
8. Industry preferences
9. Key achievements
10. Recommended job search keywords

Resume:
{resume_text[:4000]}

Return ONLY valid JSON with these keys: name, current_role, years_experience, skills, education, field_of_study, career_interests, industries, achievements, job_keywords"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
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
        logs.append("Used AI analysis (OpenAI)")
        return analysis
        
    except Exception as e:
        logs.append(f"AI analysis failed: {e}, using basic extraction")
        return _analyze_basic(resume_text, logs)


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
    
    logs.append("Used basic keyword analysis (add OpenAI key for AI analysis)")
    
    return {
        "name": "Candidate",
        "current_role": "Software Professional",
        "years_experience": "3-5",
        "skills": found_skills[:10] if found_skills else ["Programming", "Problem Solving"],
        "education": ["Bachelor's Degree"] if has_education else ["Education details in resume"],
        "field_of_study": field,
        "career_interests": [f"{field} roles", "Remote positions", "Growing companies"],
        "industries": ["Technology", "Software", "Startups"],
        "achievements": ["See resume for details"],
        "job_keywords": found_skills[:5] + [field.lower(), "remote", "senior"]
    }
