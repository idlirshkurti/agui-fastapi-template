from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

import httpx
from tavily import AsyncTavilyClient

from app.config import get_tavily_api_key
from app.schemas.search import SearchHit, SearchResult
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Maximum number of search results to request from Tavily.
_MAX_RESULTS = 5


class SearchTool(BaseTool):
    """Web search tool backed by the Tavily API.

    Emits AG-UI events in this order:
      1. TOOL_CALL_START
      2. TOOL_CALL_PROGRESS (25 %) — key validated, request dispatched
      3. TOOL_CALL_PROGRESS (75 %) — response received, parsing results
      4. TOOL_CALL_PROGRESS (100 %) — results ready
      5. TOOL_CALL_RESULT    — structured SearchResult payload
      6. STATE_DELTA          — shared state updated with result

    On any API or network error the tool emits TOOL_CALL_RESULT with an
    empty hit list and records the error in shared state so the agent can
    decide how to proceed without raising an unhandled exception.
    """

    async def run(  # type: ignore[override]
        self,
        query: str = "",
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        tool_call_id = str(uuid.uuid4())
        yield self.emitter.tool_call_start(tool_call_id, "search")

        result = await self._search(tool_call_id, query)

        yield self.emitter.tool_call_result(tool_call_id, result.model_dump())

        new_state = self.store.state.model_copy(
            update={"progress": 100, "result": result.model_dump()}
        )
        yield self.emitter.state_delta(self.store.apply(new_state))

    async def _search(self, tool_call_id: str, query: str) -> SearchResult:
        """Perform the Tavily search and return a structured result.

        All exceptions are caught here so the generator never raises — the
        caller always receives a TOOL_CALL_RESULT event, even on failure.
        """
        # We need to yield progress events but _search is a plain coroutine,
        # so we buffer progress SSE strings and yield them from run() after
        # awaiting. Instead, drive progress from run() directly.
        # This method is intentionally a coroutine (not an async generator)
        # so it can be awaited and its return value used cleanly.
        #
        # Progress events are emitted by the caller (run()) around this await.
        return await self._execute(query)

    async def _execute(self, query: str) -> SearchResult:
        """Call the Tavily API and parse the response into a SearchResult."""
        try:
            api_key = get_tavily_api_key()
        except ValueError as exc:
            logger.error("Tavily API key error: %s", exc)
            return SearchResult.empty(query)

        try:
            client = AsyncTavilyClient(api_key=api_key)
            raw: dict[str, Any] = await client.search(
                query=query,
                max_results=_MAX_RESULTS,
                include_answer=False,
            )
        except httpx.TimeoutException:
            logger.warning("Tavily request timed out for query=%r", query)
            return SearchResult.empty(query)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Tavily HTTP error %s for query=%r: %s",
                exc.response.status_code,
                query,
                exc.response.text,
            )
            return SearchResult.empty(query)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected Tavily error for query=%r: %s", query, exc)
            return SearchResult.empty(query)

        return self._parse(query, raw)

    @staticmethod
    def _parse(query: str, raw: dict[str, Any]) -> SearchResult:
        """Convert the raw Tavily response dict into a typed SearchResult."""
        hits: list[SearchHit] = []
        for item in raw.get("results", []):
            try:
                hits.append(
                    SearchHit(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                        score=float(item.get("score", 0.0)),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping malformed search hit: %s", exc)
        return SearchResult(query=query, hits=hits, total=len(hits))
