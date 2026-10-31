"""Unified Scraper Tool with Requests and Playwright support.

Supports:
1. Fast HTTP scraping with Requests + BeautifulSoup
2. Headless browser scraping with Playwright for JS-rendered dynamic web pages
3. Configurable via args or SCRAPER_MODE environment variable ('requests' or 'playwright')
"""
from __future__ import annotations
from typing import Tuple, List
import os
import requests
from bs4 import BeautifulSoup


def _extract_text_bs4(html: str) -> str:
    """Extract clean, readable text from HTML markup using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style elements
    for element in soup(["script", "style", "noscript", "header", "footer"]):
        element.decompose()

    # Get visible paragraph text
    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
    if paragraphs:
        return "\n\n".join(paragraphs[:20])

    # Fallback to body lines
    text = soup.get_text(separator="\n", strip=True)
    lines = [line for line in text.split("\n") if line.strip()]
    return "\n".join(lines[:50])


def _scrape_with_requests(url: str) -> str:
    """Scrape using standard HTTP requests + BeautifulSoup."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return _extract_text_bs4(resp.text)
        return f"(HTTP {resp.status_code})"
    except Exception as e:
        return f"(Error: {e})"


def _scrape_with_playwright(url: str) -> str:
    """Scrape using Playwright for JavaScript-rendered dynamic content."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=20000)
            page.wait_for_timeout(2000)  # Wait for JS hydration
            content = page.content()
            browser.close()
            return _extract_text_bs4(content)
    except ImportError:
        # Graceful fallback to requests if Playwright is not installed
        return _scrape_with_requests(url)
    except Exception as e:
        return f"(Playwright error: {e})"


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    logs = []
    outputs = []
    scraper_mode = args.get("mode") or os.getenv("SCRAPER_MODE", "requests").lower()

    # Determine URLs to scrape
    if "url" in args and args["url"]:
        urls = [args["url"]]
    else:
        # Pull URLs from previous search results in context
        results = None
        for v in context.values():
            if isinstance(v, dict) and v.get("results"):
                results = v.get("results")
                break
        if not results:
            return ["No URLs or search results available to scrape"], {"pages": []}

        top_k = int(args.get("top_k", 3))
        urls = [r.get("url") for r in results[:top_k] if r.get("url")]

    # Scrape each URL
    for url in urls:
        logs.append(f"Fetching {url} (mode: {scraper_mode})")

        if scraper_mode == "playwright":
            text = _scrape_with_playwright(url)
        else:
            text = _scrape_with_requests(url)

        outputs.append({"url": url, "text": text or "(no text)"})
        logs.append(f"Scraped {url} ({len(text)} chars)")

    return logs, {"pages": outputs}
