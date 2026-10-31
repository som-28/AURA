"""Enhanced Scraper Tool - unified with scraper_tool.py.

Maintained as an alias for backwards compatibility.
"""
from src.tools.scraper_tool import (
    run,
    _extract_text_bs4,
    _scrape_with_requests,
    _scrape_with_playwright,
)

__all__ = [
    "run",
    "_extract_text_bs4",
    "_scrape_with_requests",
    "_scrape_with_playwright",
]
