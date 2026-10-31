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
    
    # Combine into search query
    search_terms = []
    if field:
        search_terms.append(field)
    search_terms.extend(skills[:3])  # Top 3 skills
    search_terms.extend(keywords[:2])  # Top 2 keywords
    
    location = args.get("location", "remote")
    search_query = f"{' '.join(search_terms[:5])} jobs {location}"
    
    logs.append(f"Searching for: {search_query}")
    
    # Use the search tool
    from src.tools.search_tool import run as search_run
    
    limit = int(args.get("limit", 10))
    search_args = {"query": search_query, "limit": limit}
    search_logs, search_output = search_run(search_args, context)
    
    logs.extend(search_logs)
    
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
            "relevance": "high" if is_job else "medium",
            "matched_skills": [skill for skill in skills if skill.lower() in snippet_lower]
        })
    
    logs.append(f"Found {len(job_matches)} potential job matches")
    
    return logs, {
        "job_matches": job_matches,
        "search_query": search_query,
        "matched_field": field,
        "matched_skills": skills[:5]
    }
