"""Unified Search Tool with multi-provider API support.

Supports:
1. SerpAPI (Google Search)
2. Google Custom Search Engine (CSE)
3. Deterministic offline fallback (when no API keys are configured)
"""
from __future__ import annotations
from typing import Tuple, List, Optional
import os
import requests


def _serpapi_search(query: str, limit: int = 5) -> Optional[List[dict]]:
    """Use SerpAPI for real Google search results."""
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return None

    try:
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": api_key,
            "num": limit,
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get("organic_results", [])[:limit]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results
    except Exception as e:
        print(f"SerpAPI error: {e}")
    return None


def _google_custom_search(query: str, limit: int = 5) -> Optional[List[dict]]:
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
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get("items", [])[:limit]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results
    except Exception as e:
        print(f"Google Custom Search error: {e}")
    return None


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

    # Try SerpAPI first
    results = _serpapi_search(query, limit)
    if results:
        logs.append(f"Search: found {len(results)} results using SerpAPI for '{query}'")
        return logs, {"results": results}

    # Try Google Custom Search
    results = _google_custom_search(query, limit)
    if results:
        logs.append(f"Search: found {len(results)} results using Google Custom Search for '{query}'")
        return logs, {"results": results}

    # Fallback to simulated search
    results = _fake_search(query, limit)
    logs.append(f"Search: found {len(results)} demo results for '{query}' (no API key configured)")
    return logs, {"results": results}
