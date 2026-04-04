"""Web search tool — Tavily (primary) + DDG (fallback)."""
from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "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")


def _search_tavily(query: str, max_results: int = 5) -> list[dict]:
    """Search using Tavily API — optimized for AI agents."""
    from tavily import TavilyClient

    client = TavilyClient(api_key=TAVILY_API_KEY)
    response = client.search(query, max_results=max_results)
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in response.get("results", [])
    ]


def _search_ddgs(query: str, max_results: int = 5) -> list[dict]:
    """Fallback: DuckDuckGo search."""
    from ddgs import DDGS

    ddgs = DDGS(timeout=30)
    results = list(ddgs.text(query, max_results=max_results))
    return [
        {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
        for r in results
    ]


@tool("web_search", parse_docstring=True)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information. Use this tool to find current information, news, articles, and facts.

    Args:
        query: Search keywords describing what you want to find. Be specific for better results.
        max_results: Maximum number of results to return. Default is 5.
    """
    for search_fn in [_search_tavily, _search_ddgs]:
        try:
            results = search_fn(query, max_results)
            if results:
                return json.dumps(
                    {"query": query, "total_results": len(results), "results": results},
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            logger.warning(f"{search_fn.__name__} failed: {e}")
            continue

    return json.dumps({"error": "All search backends failed", "query": query}, ensure_ascii=False)
