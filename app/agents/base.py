from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.schemas.messages import ConversationHistory
from app.tracing.base import Tracer
from app.tracing.noop import NoopTracer


class BaseAgent(ABC):
    """Abstract base for all agents."""

    def __init__(
        self,
        emitter: AGUIEmitter,
        store: StateStore,
        history: ConversationHistory | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.emitter = emitter
        self.store = store
        self.history = history
        self.tracer: Tracer = tracer if tracer is not None else NoopTracer()

    @abstractmethod
    async def run(self, payload: dict[str, Any]) -> AsyncGenerator[str, None]:
        """Yield SSE strings. Implementations must be async generators."""
        return
        yield  # pragma: no cover
