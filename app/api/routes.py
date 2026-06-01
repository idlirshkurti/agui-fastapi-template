from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.agents.router import RouterAgent
from app.schemas.state import AppState

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/awp")
@limiter.limit("10/minute")
async def awp_endpoint(request: Request, payload: dict) -> StreamingResponse:
    """AG-UI run endpoint – streams Server-Sent Events.

    Rate limit: 10 requests per minute per IP (in-memory).
    For multi-replica deployments swap the Limiter storage backend to Redis.
    """
    store = StateStore(AppState())
    emitter = AGUIEmitter()
    agent = RouterAgent(emitter=emitter, store=store)

    async def event_stream():
        async for event in agent.run(payload):
            yield event

    return StreamingResponse(event_stream(), media_type="text/event-stream")
