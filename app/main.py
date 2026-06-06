from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.routes import router
from app.context.session_store import set_backend

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="AG-UI FastAPI Template", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # type: ignore[arg-type]
)
app.include_router(router)


@app.on_event("startup")
async def _configure_session_store() -> None:
    """Wire the Redis session store when REDIS_URL is set, else keep in-memory."""
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        logger.info("REDIS_URL not set — using in-memory session store.")
        return

    try:
        from app.context.redis_session_store import RedisSessionStore
        store = RedisSessionStore(url=redis_url)
        # Smoke-test the connection.
        import redis.asyncio as aioredis
        client = aioredis.from_url(redis_url)
        await client.ping()
        await client.aclose()
        set_backend(store)
        logger.info("Redis session store active (url=%s).", redis_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Redis unavailable (%s) — falling back to in-memory session store.", exc
        )
