"""Tests for app.services.search — Tavily web search wrapper."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.search import (
    SearchResponse,
    SearchResult,
    _format_response,
    search_web,
)


# --- Unit tests for formatting ---


def test_format_response_with_answer_and_results():
    resp = SearchResponse(
        query="delfina menu",
        answer="Delfina serves Neapolitan-style pizza.",
        results=[
            SearchResult(
                title="Delfina Menu",
                url="https://example.com/delfina",
                snippet="Full menu with prices...",
                score=0.95,
            ),
        ],
    )
    formatted = _format_response(resp)
    assert "Summary: Delfina serves" in formatted
    assert "[1] Delfina Menu" in formatted
    assert "https://example.com/delfina" in formatted


def test_format_response_no_results():
    resp = SearchResponse(query="nonexistent place xyz", answer=None, results=[])
    formatted = _format_response(resp)
    assert "No results found" in formatted


def test_format_response_truncates_long_snippets():
    long_snippet = "x" * 500
    resp = SearchResponse(
        query="test",
        answer=None,
        results=[
            SearchResult(title="T", url="http://t.co", snippet=long_snippet, score=0.5),
        ],
    )
    formatted = _format_response(resp)
    # Snippet truncated to 300 chars
    assert "x" * 300 in formatted
    assert "x" * 301 not in formatted


# --- Integration-style tests (mocked HTTP) ---


MOCK_TAVILY_RESPONSE = {
    "query": "whole foods palo alto hours",
    "answer": "Whole Foods Palo Alto is open 8am-10pm daily.",
    "results": [
        {
            "title": "Whole Foods Market - Palo Alto",
            "url": "https://wholefoodsmarket.com/stores/paloalto",
            "content": "Open daily 8am to 10pm. Located at 774 Emerson St.",
            "score": 0.92,
        },
        {
            "title": "Whole Foods Palo Alto - Yelp",
            "url": "https://yelp.com/biz/whole-foods-palo-alto",
            "content": "Great selection. Hours: 8am-10pm every day.",
            "score": 0.85,
        },
    ],
}


@pytest.mark.asyncio
async def test_search_web_success():
    mock_response = httpx.Response(
        200,
        json=MOCK_TAVILY_RESPONSE,
        request=httpx.Request("POST", "https://api.tavily.com/search"),
    )

    with (
        patch("app.services.search.TAVILY_API_KEY", "test-key"),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
    ):
        result = await search_web("whole foods palo alto hours")

    assert "Whole Foods Palo Alto is open 8am-10pm" in result
    assert "[1] Whole Foods Market" in result
    assert "[2] Whole Foods Palo Alto - Yelp" in result


@pytest.mark.asyncio
async def test_search_web_no_api_key():
    with patch("app.services.search.TAVILY_API_KEY", ""):
        result = await search_web("test query")
    assert "not configured" in result


@pytest.mark.asyncio
async def test_search_web_timeout():
    with (
        patch("app.services.search.TAVILY_API_KEY", "test-key"),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")),
    ):
        result = await search_web("slow query")
    assert "timed out" in result


@pytest.mark.asyncio
async def test_search_web_http_error():
    error_response = httpx.Response(
        429,
        text="Rate limited",
        request=httpx.Request("POST", "https://api.tavily.com/search"),
    )

    with (
        patch("app.services.search.TAVILY_API_KEY", "test-key"),
        patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError("rate limited", request=error_response.request, response=error_response),
        ),
    ):
        result = await search_web("test query")
    assert "unavailable" in result
