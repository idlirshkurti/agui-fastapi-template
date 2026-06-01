from typing import AsyncIterator
from app.agents.base import BaseAgent
from app.tools.search_tool import SearchTool


class ResearchAgent(BaseAgent):
    """Specialist agent that runs a search tool and streams results."""

    async def run(self, payload: dict) -> AsyncIterator[str]:  # type: ignore[override]
        query = payload.get("query", "")

        new_state = self.store.state.model_copy(
            update={"status": "researching", "current_agent": "research"}
        )
        yield self.emitter.state_delta(self.store.apply(new_state))

        tool = SearchTool(emitter=self.emitter, store=self.store)
        async for event in tool.run(query=query):
            yield event

        yield self.emitter.text_message(f"Research complete for query: {query!r}")
