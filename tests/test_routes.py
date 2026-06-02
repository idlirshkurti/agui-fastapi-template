import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_awp_streams_events():
    """Happy path: valid request streams the expected AG-UI events."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream("POST", "/awp", json={"query": "test"}) as response:
            assert response.status_code == 200
            events = []
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    events.append(line.split("event: ", 1)[1])

    assert "RUN_STARTED" in events
    assert "RUN_FINISHED" in events
    assert "STATE_SNAPSHOT" in events


@pytest.mark.asyncio
async def test_awp_missing_query_returns_422():
    """Missing required 'query' field must return HTTP 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/awp", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_awp_empty_query_returns_422():
    """Empty string for 'query' must fail the min_length=1 constraint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/awp", json={"query": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_awp_session_id_defaults_when_omitted():
    """A request without session_id should still succeed (UUID auto-generated)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream("POST", "/awp", json={"query": "hello"}) as response:
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_awp_accepts_optional_fields():
    """thread_id and metadata are optional and must not cause errors when provided."""
    payload = {
        "query": "test with extras",
        "session_id": "my-session-123",
        "thread_id": "thread-abc",
        "metadata": {"locale": "en", "tier": "pro"},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream("POST", "/awp", json=payload) as response:
            assert response.status_code == 200
