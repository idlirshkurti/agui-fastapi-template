from __future__ import annotations

from typing import Any, AsyncIterator
import uuid

from app.agents.base import BaseAgent
from app.agents.research import ResearchAgent


class RouterAgent(BaseAgent):
    """Top-level router that delegates to specialist agents."""

    async def run(self, payload: dict[str, Any]) -> AsyncIterator[str]:  # type: ignore[override,misc]
        run_id = str(uuid.uuid4())
        query: str = payload.get("query", "")

        yield self.emitter.run_started(run_id)
        yield self.emitter.state_snapshot(self.store.snapshot())

        # Record the incoming user message in history
        if self.history is not None:
            self.history.add("user", query)

        # Update state: routing
        new_state = self.store.state.model_copy(update={"status": "routing", "current_agent": "router"})
        patch = self.store.apply(new_state)
        yield self.emitter.state_delta(patch)

        # Hand off to research agent, passing history along
        specialist = ResearchAgent(
            emitter=self.emitter,
            store=self.store,
            history=self.history,
        )
        async for event in specialist.run(payload):
            yield event

        # Finalise
        final_state = self.store.state.model_copy(update={"status": "done", "progress": 100})
        patch = self.store.apply(final_state)
        yield self.emitter.state_delta(patch)
        yield self.emitter.run_finished(run_id)
