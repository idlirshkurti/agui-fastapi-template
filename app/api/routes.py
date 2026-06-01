from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.agents.router import RouterAgent
from app.schemas.state import AppState

router = APIRouter()


@router.post("/awp")
async def awp_endpoint(payload: dict) -> StreamingResponse:
    """AG-UI run endpoint – streams Server-Sent Events."""
    store = StateStore(AppState())
    emitter = AGUIEmitter()
    agent = RouterAgent(emitter=emitter, store=store)

    async def event_stream():
        async for event in agent.run(payload):
            yield event

    return StreamingResponse(event_stream(), media_type="text/event-stream")
