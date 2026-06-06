from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.tracing.base import Tracer
from app.tracing.noop import NoopTracer


class BaseTool(ABC):
    """Abstract base for all tools."""

    def __init__(
        self,
        emitter: AGUIEmitter,
        store: StateStore,
        tracer: Tracer | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> None:
        self.emitter = emitter
        self.store = store
        self.tracer: Tracer = tracer if tracer is not None else NoopTracer()
        self.trace_id = trace_id or "unknown"
        self.parent_span_id = parent_span_id

    @abstractmethod
    async def run(self, **kwargs: Any) -> AsyncIterator[str]:
        ...
