from typing import AsyncIterator
import uuid
from app.agents.base import BaseAgent
from app.agents.research import ResearchAgent
from app.schemas.state import AppState


class RouterAgent(BaseAgent):
    """Top-level router that delegates to specialist agents."""

    async def run(self, payload: dict) -> AsyncIterator[str]:  # type: ignore[override]
        run_id = str(uuid.uuid4())
        yield self.emitter.run_started(run_id)
        yield self.emitter.state_snapshot(self.store.snapshot())

        # Update state: routing
        new_state = self.store.state.model_copy(update={"status": "routing", "current_agent": "router"})
        patch = self.store.apply(new_state)
        yield self.emitter.state_delta(patch)

        # Hand off to research agent
        specialist = ResearchAgent(emitter=self.emitter, store=self.store)
        async for event in specialist.run(payload):
            yield event

        # Finalise
        final_state = self.store.state.model_copy(update={"status": "done", "progress": 100})
        patch = self.store.apply(final_state)
        yield self.emitter.state_delta(patch)
        yield self.emitter.run_finished(run_id)
