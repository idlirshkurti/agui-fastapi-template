from typing import AsyncIterator
from app.agents.base import BaseAgent
from app.tools.search_tool import SearchTool


class ResearchAgent(BaseAgent):
    """Specialist agent that runs a search tool and streams results."""

    async def run(self, payload: dict) -> AsyncIterator[str]:  # type: ignore[override]
        query: str = payload.get("query", "")

        new_state = self.store.state.model_copy(
            update={"status": "researching", "current_agent": "research"}
        )
        yield self.emitter.state_delta(self.store.apply(new_state))

        tool = SearchTool(emitter=self.emitter, store=self.store)
        async for event in tool.run(query=query):
            yield event

        response = f"Research complete for query: {query!r}"

        # Record the assistant reply in history
        if self.history is not None:
            self.history.add("assistant", response)

        yield self.emitter.text_message(response)
