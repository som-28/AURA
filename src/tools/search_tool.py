"""Unified live search tool with explicit unavailable status when unconfigured."""
from __future__ import annotations
from typing import Tuple, List, Optional
import os
import re
import requests
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _provider_error_label(provider: str, status: int | None = None, detail: object = "") -> str:
    text = str(detail or "").casefold()
    if status == 429 or any(word in text for word in ("quota", "rate limit", "monthly limit", "over the limit", "exceeded your limit")):
        return f"{provider} quota or rate limit reached" + (f" (HTTP {status})" if status else "")
    if status in {401, 403} or any(word in text for word in ("api key", "apikey", "unauthorized", "authentication", "access denied")):
        return f"{provider} rejected the configured credentials" + (f" (HTTP {status})" if status else "")
    if status:
        return f"{provider} request failed (HTTP {status})"
    return f"{provider} returned a provider error"


def _serpapi_search(query: str, limit: int = 5, engine: str = "google", diagnostics: list[str] | None = None) -> Optional[List[dict]]:
    """Use SerpAPI Google or Google Jobs results."""
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return None

    try:
        url = "https://serpapi.com/search"
        params = {
            "engine": engine,
            "q": query,
            "api_key": api_key,
            "num": limit,
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("error"):
                if diagnostics is not None:
                    diagnostics.append(_provider_error_label("SerpAPI", detail=data.get("error")))
                return None
            results = []
            source_items = data.get("jobs_results") if engine == "google_jobs" else data.get("organic_results", [])
            if source_items is None and engine == "google_jobs":
                return None
            source_items = source_items or []
            for item in source_items[:limit]:
                extensions = item.get("detected_extensions") or {}
                snippet = item.get("description") or item.get("snippet") or ""
                apply_options = item.get("apply_options") or []
                direct_apply = next((option.get("link") for option in apply_options if option.get("link")), "")
                results.append({
                    "title": item.get("title", ""),
                    "url": direct_apply or item.get("link") or item.get("share_link") or item.get("url", ""),
                    "snippet": snippet,
                    "company": item.get("company_name") or item.get("company") or "",
                    "location": item.get("location") or extensions.get("location") or "",
                    "work_mode": item.get("work_mode") or ("Remote" if extensions.get("work_from_home") else ""),
                    "salary": extensions.get("salary") or item.get("salary") or "",
                    "employment_type": extensions.get("schedule_type") or item.get("employment_type") or "",
                    "date": extensions.get("posted_at") or item.get("date") or "",
                    "source": item.get("via") or item.get("displayed_link") or "",
                })
            return results
        if diagnostics is not None:
            diagnostics.append(_provider_error_label("SerpAPI", status=resp.status_code))
    except Exception as e:
        if diagnostics is not None:
            diagnostics.append(f"SerpAPI request failed ({type(e).__name__})")
        print(f"SerpAPI error: {type(e).__name__}")
    return None


def _google_custom_search(query: str, limit: int = 5, diagnostics: list[str] | None = None) -> Optional[List[dict]]:
    """Use Google Custom Search API."""
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    if not api_key or not engine_id:
        return None

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": engine_id,
            "q": query,
            "num": limit,
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("error"):
                if diagnostics is not None:
                    diagnostics.append(_provider_error_label("Google Custom Search", detail=data.get("error")))
                return None
            results = []
            for item in data.get("items", [])[:limit]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results
        if diagnostics is not None:
            diagnostics.append(_provider_error_label("Google Custom Search", status=resp.status_code))
    except Exception as e:
        if diagnostics is not None:
            diagnostics.append(f"Google Custom Search request failed ({type(e).__name__})")
        print(f"Google Custom Search error: {type(e).__name__}")
    return None


def _is_job_search_landing_page(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().removeprefix("www.")
        path = parts.path.casefold()
    except ValueError:
        return False
    if host.endswith("indeed.com") and re.match(r"^/q-.+-jobs?\.html$", path):
        return True
    if host.endswith("shine.com") and path.startswith("/job-search/"):
        return True
    if host.endswith("linkedin.com") and path.startswith(("/jobs/search", "/jobs/collections")):
        return True
    if host.endswith("naukri.com") and path.startswith("/jobs-in-"):
        return True
    if host.endswith("glassdoor.com") and path in {"/job/jobs.htm", "/jobs.htm"}:
        return True
    return False


def _curate_results(query: str, items: List[dict], limit: int, provider: str) -> List[dict]:
    """Remove duplicate links, rank job intent matches, and attach provenance."""
    stop_words = {"the", "and", "for", "with", "from", "that", "this", "find", "search", "jobs", "job"}
    terms = {word.lower() for word in query.split() if len(word) > 2 and word.lower() not in stop_words}
    job_intent = any(word in query.lower() for word in ("job", "role", "intern", "career", "position", "vacanc", "fresher", "hiring", "opening"))
    seen = set()
    curated = []
    for item in items:
        raw_url = str(item.get("url") or item.get("link") or "").strip()
        try:
            parts = urlsplit(raw_url)
            if (parts.hostname or "").lower().removeprefix("www.") == "google.com" and parts.path in {"/url", "/goto"}:
                redirect_target = dict(parse_qsl(parts.query)).get("url") or dict(parse_qsl(parts.query)).get("q")
                if redirect_target and redirect_target.startswith(("https://", "http://")):
                    raw_url = redirect_target
                    parts = urlsplit(raw_url)
                else:
                    # Google Jobs sometimes returns opaque, encoded redirect IDs
                    # instead of a usable destination URL. Do not present those as
                    # direct job links in AURA's results.
                    continue
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                continue
            host = parts.hostname.lower().removeprefix("www.")
            if job_intent and _is_job_search_landing_page(raw_url):
                continue
            query_items = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                           if not key.lower().startswith(("utm_", "gclid", "fbclid"))]
            canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query_items), ""))
        except ValueError:
            continue
        dedupe_key = (host, parts.path.rstrip("/").lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        title = str(item.get("title") or "Opportunity").strip()
        snippet = str(item.get("snippet") or "").strip()
        haystack = f"{title} {snippet}".lower()
        work_mode = str(item.get("work_mode") or "").strip()
        if not work_mode:
            for phrase, label in (("work from home", "Remote"), ("remote", "Remote"), ("hybrid", "Hybrid"), ("on-site", "On-site"), ("onsite", "On-site")):
                if phrase in haystack:
                    work_mode = label
                    break
        salary = str(item.get("salary") or "").strip()
        if not salary:
            salary_match = re.search(r"(?:₹|INR|USD|\$|£|€)\s?\d[\d,.]*(?:\s*(?:-|–|to)\s*(?:₹|INR|USD|\$|£|€)?\s?\d[\d,.]*)?(?:\s*(?:per|/)\s?(?:month|year|hour|annum|mo|yr))?", snippet, re.IGNORECASE)
            salary = salary_match.group(0).strip() if salary_match else ""
        matched = len([term for term in terms if term in haystack])
        job_terms = sum(term in haystack for term in ("intern", "job", "role", "career", "hiring", "vacancy", "fresher", "opening"))
        if job_intent and not job_terms and matched == 0:
            continue
        relevance = "Strong match" if terms and matched >= max(2, len(terms) // 2) else "Related"
        curated.append({
            "title": title,
            "url": canonical,
            "snippet": snippet,
            "source": str(item.get("source") or host).strip(),
            "provider": provider,
            "relevance": relevance,
            "found_at": datetime.now(timezone.utc).isoformat(),
            "published_at": item.get("date"),
            "company": str(item.get("company") or "").strip(),
            "location": str(item.get("location") or "").strip(),
            "work_mode": work_mode,
            "salary": salary,
            "employment_type": str(item.get("employment_type") or "").strip(),
        })
    if job_intent:
        curated.sort(key=lambda item: (item["relevance"] == "Strong match", len(set(item["title"].lower().split()) & terms)), reverse=True)
    return curated[:max(1, min(int(limit), 15))]


def _fake_search(query: str, limit: int = 5) -> List[dict]:
    """Fallback fake search for demo and offline test environments."""
    results = []
    slug = query.replace(" ", "-") if query else "query"
    for i in range(1, limit + 1):
        results.append({
            "title": f"Result {i} for {query}",
            "url": f"https://example.com/{slug}/{i}",
            "snippet": f"This is a short snippet describing {query} result #{i}.",
        })
    return results


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    query = args.get("query", "").strip()
    limit = int(args.get("limit", 5))
    logs = []
    diagnostics = []

    has_serpapi = bool(os.getenv("SERPAPI_KEY"))
    has_google = bool(os.getenv("GOOGLE_SEARCH_API_KEY") and os.getenv("GOOGLE_SEARCH_ENGINE_ID"))

    # Prefer structured employer/location/apply links for jobs, then fall back
    # to regular web results when the Jobs engine has no matching listings.
    job_intent = any(word in query.lower() for word in ("job", "role", "intern", "career", "position", "vacanc", "fresher", "hiring", "opening"))
    results = _serpapi_search(query, limit, "google_jobs", diagnostics) if has_serpapi and job_intent else None
    if not results:
        results = _serpapi_search(query, limit, diagnostics=diagnostics)
    if results is not None:
        results = _curate_results(query, results, limit, "SerpAPI")
        logs.append(f"Search: found {len(results)} curated results using SerpAPI")
        return logs, {"results": results, "search_available": True}

    # Try Google Custom Search
    results = _google_custom_search(query, limit, diagnostics)
    if results is not None:
        results = _curate_results(query, results, limit, "Google Custom Search")
        logs.append(f"Search: found {len(results)} curated results using Google Custom Search")
        return logs, {"results": results, "search_available": True}

    if not has_serpapi and not has_google:
        message = "Live job search is not configured. Add SERPAPI_KEY or Google Custom Search credentials to .env."
    else:
        detail = diagnostics[0] if diagnostics else ""
        message = f"{detail}. Check the provider key, quota, and connection." if detail else "The configured search provider did not return results. Check its API key, quota, and connection."
    logs.append(message)
    return logs, {"results": [], "search_available": False, "message": message}
