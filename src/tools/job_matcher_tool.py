"""Job matcher tool - searches for jobs based on resume analysis."""
from typing import Tuple, List


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    """Search for jobs matching the analyzed resume.
    
    Args:
        args: {"location": str (optional), "limit": int (optional)}
        context: Must contain analysis from resume_analyzer
    
    Returns:
        logs, {"job_matches": list, "search_query": str}
    """
    logs = []
    
    # Get analysis from context
    analysis = None
    for key, value in context.items():
        if isinstance(value, dict) and "analysis" in value:
            analysis = value["analysis"]
            break
    
    if not analysis:
        logs.append("Error: No resume analysis found in context")
        return logs, {"error": "No analysis available"}
    
    # Build search query from analysis
    field = analysis.get("field_of_study", "")
    skills = analysis.get("skills", [])
    interests = analysis.get("career_interests", [])
    keywords = analysis.get("job_keywords", [])
    
    # Prefer role intent over degree names, then add a couple of skills.
    search_terms = []
    search_terms.extend(interests[:2])
    if not search_terms:
        search_terms.extend(keywords[:2])
    if not search_terms and field:
        search_terms.append(field)
    search_terms.extend(skills[:2])
    deduped_terms = []
    for term in search_terms:
        term = str(term).strip()
        if term and term.casefold() not in {item.casefold() for item in deduped_terms}:
            deduped_terms.append(term)
    
    location = args.get("location", "remote")
    search_query = f"{' '.join(deduped_terms[:4])} jobs {location}".strip()
    
    logs.append(f"Searching for: {search_query}")
    
    # Use the search tool
    from src.tools.search_tool import run as search_run
    
    limit = int(args.get("limit", 10))
    search_args = {"query": search_query, "limit": limit}
    search_logs, search_output = search_run(search_args, context)
    
    logs.extend(search_logs)

    if not search_output.get("search_available", True):
        return logs, {
            "job_matches": [],
            "search_query": search_query,
            "matched_field": field,
            "matched_skills": skills[:5],
            "message": search_output.get("message", "Live job search is unavailable."),
        }
    
    job_results = search_output.get("results", [])
    
    # Filter and enhance results
    job_matches = []
    for result in job_results:
        # Basic filtering for job-related results
        title_lower = result.get("title", "").lower()
        snippet_lower = result.get("snippet", "").lower()
        
        is_job = any(keyword in title_lower or keyword in snippet_lower 
                    for keyword in ["job", "career", "hiring", "position", "opening"])
        
        job_matches.append({
            "title": result.get("title"),
            "url": result.get("url"),
            "snippet": result.get("snippet"),
            "source": result.get("source"),
            "provider": result.get("provider"),
            "found_at": result.get("found_at"),
            "published_at": result.get("published_at"),
            "company": result.get("company"),
            "location": result.get("location"),
            "work_mode": result.get("work_mode"),
            "salary": result.get("salary"),
            "employment_type": result.get("employment_type"),
            "relevance": result.get("relevance") or ("Strong match" if is_job else "Related"),
            "matched_skills": [skill for skill in skills if skill.lower() in snippet_lower]
        })
    
    logs.append(f"Found {len(job_matches)} potential job matches")
    
    return logs, {
        "job_matches": job_matches,
        "search_query": search_query,
        "matched_field": field,
        "matched_skills": skills[:5]
    }
