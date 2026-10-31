"""Enhanced Search Tool - unified with search_tool.py.

Maintained as an alias for backwards compatibility.
"""
from src.tools.search_tool import run, _serpapi_search, _google_custom_search, _fake_search

__all__ = ["run", "_serpapi_search", "_google_custom_search", "_fake_search"]
