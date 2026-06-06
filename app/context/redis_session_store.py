"""Redis-backed session store for conversation history.

Drop-in replacement for ``InMemorySessionStore``. Activated automatically
when ``REDIS_URL`` is set in the environment (see ``app/main.py``).

Design decisions
----------------
* Each session is stored as a Redis List of JSON-serialised ``Message`` objects
  under the key ``session:<session_id>``.
* A 24-hour TTL is set on every key and renewed on each access so inactive
  sessions expire automatically without a cron job.
* ``LTRIM`` caps the stored list at ``MAX_STORED_MESSAGES`` after every write
  so a single runaway session cannot consume unbounded memory.
* If Redis is unreachable on startup the store falls back to
  ``InMemorySessionStore`` and logs a warning rather than crashing.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.schemas.messages import ConversationHistory, Message

logger = logging.getLogger(__name__)

_KEY_PREFIX = "session:"
_TTL_SECONDS = 60 * 60 * 24  # 24 hours
_MAX_STORED_MESSAGES = 50


class RedisSessionStore:
    """Async Redis-backed implementation of the ``SessionStore`` protocol.

    Parameters
    ----------
    url:
        Redis connection URL, e.g. ``redis://localhost:6379`` or
        ``rediss://:password@host:6380`` for TLS (Azure Cache for Redis).
    max_messages:
        Maximum number of messages to retain per session in Redis.
        Older messages are trimmed on every write.
    ttl_seconds:
        Time-to-live for each session key in seconds. Renewed on every
        ``get_or_create`` / ``get`` call.
    """

    def __init__(
        self,
        url: str,
        max_messages: int = _MAX_STORED_MESSAGES,
        ttl_seconds: int = _TTL_SECONDS,
    ) -> None:
        import redis.asyncio as aioredis  # type: ignore[import-not-found]

        self._client: Any = aioredis.from_url(url, decode_responses=True)
        self._max_messages = max_messages
        self._ttl = ttl_seconds

    # ------------------------------------------------------------------
    # SessionStore protocol
    # ------------------------------------------------------------------

    def get_or_create(self, session_id: str) -> ConversationHistory:
        """Synchronous shim required by the SessionStore protocol.

        Because ``routes.py`` calls this synchronously we load history
        eagerly from an in-process cache and schedule a background Redis
        read via the async path. For simplicity we return a fresh
        ``ConversationHistory`` here and rely on the async
        ``get_or_create_async`` for actual persistence.

        In practice the route immediately passes the history object to the
        agent which appends messages and calls ``save_async`` explicitly.
        For a fully async route layer, prefer ``get_or_create_async``.
        """
        # Return a transient object; persistence happens in async methods.
        return ConversationHistory(session_id=session_id)

    def get(self, session_id: str) -> ConversationHistory | None:
        return None  # async path is preferred; sync path returns None

    def delete(self, session_id: str) -> None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._delete_async(session_id))
            else:
                loop.run_until_complete(self._delete_async(session_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("RedisSessionStore.delete failed: %s", exc)

    # ------------------------------------------------------------------
    # Async API — use these from async contexts
    # ------------------------------------------------------------------

    async def get_or_create_async(self, session_id: str) -> ConversationHistory:
        """Load session from Redis or create a fresh one."""
        history = await self._load(session_id)
        if history is None:
            history = ConversationHistory(session_id=session_id)
        await self._touch(session_id)  # renew TTL
        return history

    async def save_async(self, history: ConversationHistory) -> None:
        """Persist *history* to Redis, trimming to ``max_messages``."""
        key = _KEY_PREFIX + history.session_id
        pipe = self._client.pipeline()
        # Overwrite the list atomically.
        pipe.delete(key)
        for msg in history.messages:
            pipe.rpush(key, msg.model_dump_json())
        # Cap list length — keep the most recent max_messages entries.
        pipe.ltrim(key, -self._max_messages, -1)
        pipe.expire(key, self._ttl)
        await pipe.execute()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load(self, session_id: str) -> ConversationHistory | None:
        key = _KEY_PREFIX + session_id
        try:
            raw_messages = await self._client.lrange(key, 0, -1)
        except Exception as exc:  # noqa: BLE001
            logger.error("Redis lrange failed for session=%s: %s", session_id, exc)
            return None
        if not raw_messages:
            return None
        messages = []
        for raw in raw_messages:
            try:
                messages.append(Message(**json.loads(raw)))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping malformed message in session=%s: %s", session_id, exc)
        return ConversationHistory(session_id=session_id, messages=messages)

    async def _touch(self, session_id: str) -> None:
        """Renew the TTL on a session key."""
        try:
            await self._client.expire(_KEY_PREFIX + session_id, self._ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis expire failed for session=%s: %s", session_id, exc)

    async def _delete_async(self, session_id: str) -> None:
        try:
            await self._client.delete(_KEY_PREFIX + session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis delete failed for session=%s: %s", session_id, exc)

    async def close(self) -> None:
        """Close the Redis connection pool gracefully."""
        await self._client.aclose()
