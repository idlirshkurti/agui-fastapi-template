from __future__ import annotations

from typing import Any, AsyncGenerator

from app.agents.base import BaseAgent
from app.guardrails.output_filter import OutputFilterGuardrail
from app.schemas.search import SearchResult
from app.tools.search_tool import SearchTool


class ResearchAgent(BaseAgent):
    """Specialist agent that runs a web search and streams the results."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._output_filter = OutputFilterGuardrail()

    async def run(self, payload: dict[str, Any]) -> AsyncGenerator[str, None]:
        query: str = payload.get("query", "")
        trace_id: str = payload.get("_trace_id", "unknown")
        parent_id: str | None = payload.get("_parent_id")

        new_state = self.store.state.model_copy(
            update={"status": "researching", "current_agent": "research"}
        )
        yield self.emitter.state_delta(self.store.apply(new_state))

        async with self.tracer.span(
            "research",
            trace_id=trace_id,
            parent_id=parent_id,
            metadata={"query": query},
        ) as research_span:
            tool = SearchTool(
                emitter=self.emitter,
                store=self.store,
                tracer=self.tracer,
                trace_id=trace_id,
                parent_span_id=research_span.span_id,
            )
            async for event in tool.run(query=query):
                yield event

            # Build a human-readable summary from search results stored in state.
            result_data = self.store.state.result
            search_result = SearchResult.model_validate(result_data) if result_data else None

            if search_result and search_result.hits:
                lines = [f"Found {search_result.total} result(s) for {query!r}:"]
                for i, hit in enumerate(search_result.hits, start=1):
                    lines.append(f"  {i}. {hit.title} — {hit.url}")
                raw_response = "\n".join(lines)
            else:
                raw_response = f"No results found for {query!r}."

            research_span.metadata["result_count"] = (
                search_result.total if search_result else 0
            )

        # Apply output filter before adding to history or emitting to client.
        filter_result = await self._output_filter.apply(raw_response)

        if filter_result.redacted:
            warning_patch = [
                {
                    "op": "add",
                    "path": "/output_filter_warning",
                    "value": {
                        "redacted": True,
                        "reasons": filter_result.reasons,
                    },
                }
            ]
            yield self.emitter.state_delta(warning_patch)

        if self.history is not None:
            self.history.add("assistant", filter_result.text)

        yield self.emitter.text_message(filter_result.text)
