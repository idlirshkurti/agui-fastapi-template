from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.agents.router import RouterAgent
from app.context.session_store import get_or_create
from app.schemas.requests import AWPRequest
from app.schemas.state import AppState
from app.tracing.provider import get_tracer

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
_tracer = get_tracer()


@router.post("/awp")
@limiter.limit("10/minute")
async def awp_endpoint(request: Request, body: AWPRequest) -> StreamingResponse:
    """AG-UI run endpoint – streams Server-Sent Events.

    Rate limit: 10 requests per minute per IP (in-memory).
    For multi-replica deployments swap the Limiter storage backend to Redis.

    Cancellation: the generator checks for client disconnection before
    yielding each event. When the client drops (tab closed, network blip)
    the loop exits cleanly so no further LLM/tool work is performed.
    """
    history = get_or_create(body.session_id)
    store = StateStore(AppState())
    emitter = AGUIEmitter()
    agent = RouterAgent(
        emitter=emitter,
        store=store,
        history=history,
        tracer=_tracer,
    )

    async def event_stream() -> AsyncIterator[str]:
        async for event in agent.run(body.model_dump()):
            if await request.is_disconnected():
                logger.info(
                    "Client disconnected mid-stream, stopping run for session=%s",
                    body.session_id,
                )
                break
            yield event
        await _tracer.flush()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
