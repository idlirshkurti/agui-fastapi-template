"""Unit tests for SearchTool.

All tests mock the Tavily client so no real network calls are made.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.schemas.state import AppState
from app.tools.search_tool import SearchTool


RAW_TAVILY_RESPONSE = {
    "results": [
        {
            "title": "AI News Today",
            "url": "https://example.com/ai-news",
            "content": "Latest developments in artificial intelligence.",
            "score": 0.95,
        },
        {
            "title": "Machine Learning Weekly",
            "url": "https://example.com/ml-weekly",
            "content": "Weekly ML digest.",
            "score": 0.87,
        },
    ]
}


def _make_tool() -> SearchTool:
    return SearchTool(emitter=AGUIEmitter(), store=StateStore(AppState()))


async def _collect(tool: SearchTool, query: str) -> list[str]:
    return [event async for event in tool.run(query=query)]


@pytest.mark.asyncio
async def test_happy_path_emits_expected_events():
    """A successful search emits TOOL_CALL_START, TOOL_CALL_RESULT, STATE_DELTA."""
    tool = _make_tool()
    with (
        patch("app.tools.search_tool.get_tavily_api_key", return_value="fake-key"),
        patch(
            "app.tools.search_tool.AsyncTavilyClient",
            return_value=AsyncMock(search=AsyncMock(return_value=RAW_TAVILY_RESPONSE)),
        ),
    ):
        events = await _collect(tool, "AI news")

    joined = "".join(events)
    assert "TOOL_CALL_START" in joined
    assert "TOOL_CALL_RESULT" in joined
    assert "STATE_DELTA" in joined


@pytest.mark.asyncio
async def test_happy_path_result_contains_hits():
    """The TOOL_CALL_RESULT event contains the parsed hits from Tavily."""
    tool = _make_tool()
    with (
        patch("app.tools.search_tool.get_tavily_api_key", return_value="fake-key"),
        patch(
            "app.tools.search_tool.AsyncTavilyClient",
            return_value=AsyncMock(search=AsyncMock(return_value=RAW_TAVILY_RESPONSE)),
        ),
    ):
        events = await _collect(tool, "AI news")

    result_event = next(e for e in events if "TOOL_CALL_RESULT" in e)
    assert "AI News Today" in result_event
    assert "https://example.com/ai-news" in result_event
    assert "total" in result_event


@pytest.mark.asyncio
async def test_missing_api_key_returns_empty_result():
    """A missing API key must not raise — it returns an empty SearchResult."""
    tool = _make_tool()
    with patch(
        "app.tools.search_tool.get_tavily_api_key",
        side_effect=ValueError("TAVILY_API_KEY is not set."),
    ):
        events = await _collect(tool, "test query")

    joined = "".join(events)
    assert "TOOL_CALL_RESULT" in joined
    assert '"hits": []' in joined
    assert '"total": 0' in joined


@pytest.mark.asyncio
async def test_timeout_returns_empty_result():
    """A network timeout must not raise — it returns an empty SearchResult."""
    import httpx

    tool = _make_tool()
    with (
        patch("app.tools.search_tool.get_tavily_api_key", return_value="fake-key"),
        patch(
            "app.tools.search_tool.AsyncTavilyClient",
            return_value=AsyncMock(
                search=AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            ),
        ),
    ):
        events = await _collect(tool, "test query")

    joined = "".join(events)
    assert "TOOL_CALL_RESULT" in joined
    assert '"hits": []' in joined


@pytest.mark.asyncio
async def test_http_error_returns_empty_result():
    """An HTTP error from Tavily must not raise — it returns an empty SearchResult."""
    import httpx

    tool = _make_tool()
    mock_response = AsyncMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"

    with (
        patch("app.tools.search_tool.get_tavily_api_key", return_value="fake-key"),
        patch(
            "app.tools.search_tool.AsyncTavilyClient",
            return_value=AsyncMock(
                search=AsyncMock(
                    side_effect=httpx.HTTPStatusError(
                        "429", request=AsyncMock(), response=mock_response
                    )
                )
            ),
        ),
    ):
        events = await _collect(tool, "test query")

    joined = "".join(events)
    assert "TOOL_CALL_RESULT" in joined
    assert '"hits": []' in joined


@pytest.mark.asyncio
async def test_malformed_hit_is_skipped():
    """A result item with a score outside [0, 1] is silently skipped."""
    bad_response = {
        "results": [
            {"title": "Good", "url": "https://good.com", "content": "ok", "score": 0.9},
            {"title": "Bad", "url": "https://bad.com", "content": "bad", "score": 99.0},
        ]
    }
    tool = _make_tool()
    with (
        patch("app.tools.search_tool.get_tavily_api_key", return_value="fake-key"),
        patch(
            "app.tools.search_tool.AsyncTavilyClient",
            return_value=AsyncMock(search=AsyncMock(return_value=bad_response)),
        ),
    ):
        events = await _collect(tool, "test")

    result_event = next(e for e in events if "TOOL_CALL_RESULT" in e)
    assert "Good" in result_event
    assert "Bad" not in result_event


def test_parse_empty_results() -> None:
    """_parse handles an empty results list without error."""
    result = SearchTool._parse("q", {"results": []})
    assert result.total == 0
    assert result.hits == []


def test_parse_missing_results_key() -> None:
    """_parse handles a response with no 'results' key without error."""
    result = SearchTool._parse("q", {})
    assert result.total == 0
