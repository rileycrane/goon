"""Web search via Tavily API.

Step 3 in the resolution ladder: find business info not available
in the fact cache or Google Places structured data.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Sensible defaults for business-info searches
DEFAULT_MAX_RESULTS = 5
DEFAULT_SEARCH_DEPTH = "basic"  # "basic" or "advanced"
REQUEST_TIMEOUT = 15.0  # seconds


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float


@dataclass
class SearchResponse:
    query: str
    results: list[SearchResult]
    answer: str | None  # Tavily's optional generated answer


async def search_web(query: str, *, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """Search the web for business information.

    Returns a formatted string suitable for the LLM to interpret.
    On failure, returns an error message the LLM can relay gracefully.
    """
    if not TAVILY_API_KEY:
        logger.error("TAVILY_API_KEY not set")
        return "Web search unavailable (not configured)."

    try:
        response = await _tavily_search(query, max_results=max_results)
    except httpx.TimeoutException:
        logger.warning("Tavily search timed out for query: %s", query)
        return "Web search timed out. Try a more specific query."
    except httpx.HTTPStatusError as exc:
        logger.error("Tavily HTTP error %d: %s", exc.response.status_code, exc.response.text[:200])
        return "Web search temporarily unavailable."
    except Exception:
        logger.exception("Unexpected error during web search")
        return "Web search failed."

    return _format_response(response)


async def _tavily_search(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    search_depth: str = DEFAULT_SEARCH_DEPTH,
) -> SearchResponse:
    """Call the Tavily search API."""
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": True,
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(TAVILY_SEARCH_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    results = [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content", ""),
            score=r.get("score", 0.0),
        )
        for r in data.get("results", [])
    ]

    return SearchResponse(
        query=query,
        results=results,
        answer=data.get("answer"),
    )


def _format_response(response: SearchResponse) -> str:
    """Format search results for the LLM context window."""
    parts: list[str] = []

    if response.answer:
        parts.append(f"Summary: {response.answer}")

    for i, r in enumerate(response.results, 1):
        snippet = r.snippet[:300] if r.snippet else "(no snippet)"
        parts.append(f"[{i}] {r.title}\n    {snippet}\n    Source: {r.url}")

    if not parts:
        return f"No results found for: {response.query}"

    return "\n\n".join(parts)
