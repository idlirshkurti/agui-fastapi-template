from __future__ import annotations

from typing import Any, AsyncIterator

from app.agents.base import BaseAgent
from app.schemas.search import SearchResult
from app.tools.search_tool import SearchTool


class ResearchAgent(BaseAgent):
    """Specialist agent that runs a web search and streams the results."""

    async def run(self, payload: dict[str, Any]) -> AsyncIterator[str]:  # type: ignore[override,misc]
        query: str = payload.get("query", "")

        new_state = self.store.state.model_copy(
            update={"status": "researching", "current_agent": "research"}
        )
        yield self.emitter.state_delta(self.store.apply(new_state))

        tool = SearchTool(emitter=self.emitter, store=self.store)
        async for event in tool.run(query=query):
            yield event

        # Build a human-readable summary from the search results stored in state.
        result_data = self.store.state.result
        search_result = SearchResult.model_validate(result_data) if result_data else None

        if search_result and search_result.hits:
            lines = [f"Found {search_result.total} result(s) for {query!r}:"]
            for i, hit in enumerate(search_result.hits, start=1):
                lines.append(f"  {i}. {hit.title} — {hit.url}")
            response = "\n".join(lines)
        else:
            response = f"No results found for {query!r}."

        if self.history is not None:
            self.history.add("assistant", response)

        yield self.emitter.text_message(response)
