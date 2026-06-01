import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_awp_streams_events():
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
