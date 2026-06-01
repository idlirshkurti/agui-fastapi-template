import asyncio
import uuid
from typing import AsyncIterator
from app.tools.base import BaseTool


class SearchTool(BaseTool):
    """Example long-running tool that emits progress events."""

    async def run(self, query: str = "", **kwargs) -> AsyncIterator[str]:  # type: ignore[override]
        tool_call_id = str(uuid.uuid4())
        yield self.emitter.tool_call_start(tool_call_id, "search")

        # Simulate incremental work with progress updates
        for step, pct in enumerate([25, 50, 75, 100], start=1):
            await asyncio.sleep(0.1)  # replace with real async I/O
            yield self.emitter.progress(tool_call_id, pct, f"Step {step}/4")

        result = {"query": query, "hits": [], "total": 0}
        yield self.emitter.tool_call_result(tool_call_id, result)

        # Mirror result into shared state
        new_state = self.store.state.model_copy(
            update={"progress": 100, "result": result}
        )
        yield self.emitter.state_delta(self.store.apply(new_state))
