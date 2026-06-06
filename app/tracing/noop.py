from __future__ import annotations

from app.tracing.base import Span, Tracer


class NoopTracer(Tracer):
    """Transparent pass-through tracer — zero overhead, no external calls.

    This is the default when ``TRACING_BACKEND`` is unset or ``noop``.
    All span lifecycle hooks are intentional no-ops.
    """

    async def _on_start(self, span: Span) -> None:
        pass

    async def _on_end(self, span: Span) -> None:
        pass
