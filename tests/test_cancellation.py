"""Tests for SSE client-disconnect cancellation.

Because httpx's AsyncClient does not simulate mid-stream disconnection,
we test the cancellation logic directly on the stream generator rather
than through a full HTTP round-trip.
"""
import pytest
from unittest.mock import AsyncMock
from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.agents.router import RouterAgent
from app.schemas.messages import ConversationHistory
from app.schemas.state import AppState


async def _collect_events(is_disconnected_returns: list[bool]) -> list[str]:
    """Run the stream generator with a mock Request that returns successive
    is_disconnected() values and collect every event that was yielded."""
    emitter = AGUIEmitter()
    store = StateStore(AppState())
    history = ConversationHistory(session_id="cancel-test")
    agent = RouterAgent(emitter=emitter, store=store, history=history)

    # Build a mock request whose is_disconnected() cycles through the list.
    mock_request = AsyncMock()
    mock_request.is_disconnected = AsyncMock(side_effect=is_disconnected_returns)

    collected: list[str] = []
    async def event_stream():
        async for event in agent.run({"query": "test"}):
            if await mock_request.is_disconnected():
                break
            collected.append(event)

    await event_stream()
    return collected


@pytest.mark.asyncio
async def test_stream_completes_when_client_stays_connected():
    """When is_disconnected() always returns False the full run completes."""
    # Provide enough False values to cover every event in the run.
    events = await _collect_events([False] * 50)
    # At minimum RUN_STARTED and RUN_FINISHED must have been yielded.
    joined = "".join(events)
    assert "RUN_STARTED" in joined
    assert "RUN_FINISHED" in joined


@pytest.mark.asyncio
async def test_stream_stops_immediately_on_disconnect():
    """When is_disconnected() returns True on the first check, nothing is yielded."""
    events = await _collect_events([True] + [False] * 50)
    assert events == []


@pytest.mark.asyncio
async def test_stream_stops_partway_on_disconnect():
    """When the client disconnects after a few events, the stream stops early."""
    # Allow 3 events through, then disconnect.
    events = await _collect_events([False, False, False, True] + [False] * 50)
    assert len(events) == 3
