from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Literal

SpanStatus = Literal["ok", "error"]


@dataclass
class Span:
    """Immutable record of a single traced operation."""

    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str | None = None
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    status: SpanStatus = "ok"
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1_000


class Tracer:
    """Base tracer — subclass to implement a real backend.

    Usage::

        async with tracer.span("router", trace_id=run_id, metadata={...}) as span:
            # work happens here
            ...
        # span is finalised (end_time set, backend notified) on exit
    """

    @asynccontextmanager
    async def span(
        self,
        name: str,
        *,
        trace_id: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncGenerator[Span, None]:
        s = Span(
            name=name,
            trace_id=trace_id,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        await self._on_start(s)
        try:
            yield s
        except Exception as exc:
            s.status = "error"
            s.error_message = str(exc)
            s.end_time = time.perf_counter()
            await self._on_end(s)
            raise
        else:
            s.end_time = time.perf_counter()
            await self._on_end(s)

    # ------------------------------------------------------------------
    # Override in subclasses
    # ------------------------------------------------------------------

    async def _on_start(self, span: Span) -> None:  # noqa: ARG002
        """Called immediately after a span is created."""

    async def _on_end(self, span: Span) -> None:  # noqa: ARG002
        """Called after a span finishes (success or error)."""

    async def flush(self) -> None:
        """Flush any buffered spans to the backend. No-op by default."""
