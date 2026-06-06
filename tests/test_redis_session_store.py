"""Unit tests for RedisSessionStore — all Redis I/O is mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.messages import ConversationHistory, Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(mock_client: MagicMock):
    """Build a RedisSessionStore with a fully mocked redis client."""
    from app.context.redis_session_store import RedisSessionStore

    with patch("redis.asyncio.from_url", return_value=mock_client):
        store = RedisSessionStore(url="redis://localhost:6379")
    store._client = mock_client
    return store


def _mock_redis_client() -> MagicMock:
    client = MagicMock()
    client.lrange = AsyncMock(return_value=[])
    client.expire = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    pipe = MagicMock()
    pipe.delete = MagicMock()
    pipe.rpush = MagicMock()
    pipe.ltrim = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, 1, 1, 1])
    client.pipeline = MagicMock(return_value=pipe)
    return client


# ---------------------------------------------------------------------------
# get_or_create (sync shim)
# ---------------------------------------------------------------------------

def test_get_or_create_returns_fresh_history() -> None:
    client = _mock_redis_client()
    store = _make_store(client)
    history = store.get_or_create("session-1")
    assert isinstance(history, ConversationHistory)
    assert history.session_id == "session-1"
    assert history.messages == []


# ---------------------------------------------------------------------------
# get_or_create_async
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_or_create_async_empty_session() -> None:
    client = _mock_redis_client()
    client.lrange = AsyncMock(return_value=[])
    store = _make_store(client)

    history = await store.get_or_create_async("sess-new")
    assert history.session_id == "sess-new"
    assert history.messages == []


@pytest.mark.asyncio
async def test_get_or_create_async_loads_existing_messages() -> None:
    msg = Message(role="user", content="Hello")
    client = _mock_redis_client()
    client.lrange = AsyncMock(return_value=[msg.model_dump_json()])
    store = _make_store(client)

    history = await store.get_or_create_async("sess-existing")
    assert len(history.messages) == 1
    assert history.messages[0].role == "user"
    assert history.messages[0].content == "Hello"


@pytest.mark.asyncio
async def test_get_or_create_async_renews_ttl() -> None:
    client = _mock_redis_client()
    client.lrange = AsyncMock(return_value=[])
    store = _make_store(client)

    await store.get_or_create_async("sess-ttl")
    client.expire.assert_awaited_once_with("session:sess-ttl", store._ttl)


# ---------------------------------------------------------------------------
# save_async
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_async_writes_messages_to_pipeline() -> None:
    client = _mock_redis_client()
    store = _make_store(client)
    pipe = client.pipeline.return_value

    history = ConversationHistory(session_id="sess-save")
    history.add("user", "Hi")
    history.add("assistant", "Hello!")

    await store.save_async(history)

    pipe.delete.assert_called_once_with("session:sess-save")
    assert pipe.rpush.call_count == 2
    pipe.ltrim.assert_called_once_with("session:sess-save", -store._max_messages, -1)
    pipe.expire.assert_called_once_with("session:sess-save", store._ttl)
    pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_async_trims_to_max_messages() -> None:
    client = _mock_redis_client()
    store = _make_store(client)
    pipe = client.pipeline.return_value

    history = ConversationHistory(session_id="sess-trim")
    for i in range(60):
        history.add("user", f"message {i}")

    await store.save_async(history)

    # ltrim should always be called regardless of message count
    pipe.ltrim.assert_called_once_with("session:sess-trim", -store._max_messages, -1)


# ---------------------------------------------------------------------------
# Malformed message handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_malformed_messages_are_skipped() -> None:
    client = _mock_redis_client()
    good_msg = Message(role="assistant", content="OK").model_dump_json()
    client.lrange = AsyncMock(return_value=["not-json-{", good_msg])
    store = _make_store(client)

    history = await store.get_or_create_async("sess-malformed")
    # Only the valid message should be loaded
    assert len(history.messages) == 1
    assert history.messages[0].content == "OK"


# ---------------------------------------------------------------------------
# Redis error resilience
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lrange_error_returns_empty_history() -> None:
    client = _mock_redis_client()
    client.lrange = AsyncMock(side_effect=ConnectionError("Redis down"))
    store = _make_store(client)

    history = await store.get_or_create_async("sess-error")
    assert history.messages == []


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_async_removes_key() -> None:
    client = _mock_redis_client()
    store = _make_store(client)

    await store._delete_async("sess-del")
    client.delete.assert_awaited_once_with("session:sess-del")
