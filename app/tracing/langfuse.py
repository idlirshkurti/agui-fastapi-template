from __future__ import annotations

import logging
import os
from typing import Any

from app.tracing.base import Span, Tracer

logger = logging.getLogger(__name__)


class LangfuseTracer(Tracer):
    """Tracer backend that sends spans to Langfuse.

    Requires the ``langfuse`` package::

        pip install langfuse

    Configuration via environment variables:

    * ``LANGFUSE_SECRET_KEY`` — required
    * ``LANGFUSE_PUBLIC_KEY`` — required
    * ``LANGFUSE_HOST``       — optional, defaults to Langfuse cloud
    """

    def __init__(self) -> None:
        try:
            from langfuse import Langfuse  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "langfuse package is required for LangfuseTracer. "
                "Install it with: pip install langfuse"
            ) from exc

        kwargs: dict[str, Any] = {
            "secret_key": _require_env("LANGFUSE_SECRET_KEY"),
            "public_key": _require_env("LANGFUSE_PUBLIC_KEY"),
        }
        host = os.environ.get("LANGFUSE_HOST", "").strip()
        if host:
            kwargs["host"] = host

        self._client: Any = Langfuse(**kwargs)
        # Map trace_id -> Langfuse trace object so child spans share the trace.
        self._traces: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Tracer hooks
    # ------------------------------------------------------------------

    async def _on_start(self, span: Span) -> None:
        try:
            if span.parent_id is None:
                # Root span — create a new Langfuse trace.
                trace = self._client.trace(
                    id=span.trace_id,
                    name=span.name,
                    metadata=span.metadata,
                )
                self._traces[span.trace_id] = trace
            else:
                # Child span — attach to the existing trace.
                trace = self._traces.get(span.trace_id)
                if trace is None:
                    logger.warning(
                        "LangfuseTracer: no parent trace found for trace_id=%s, span=%s",
                        span.trace_id,
                        span.name,
                    )
                    return
                trace.span(
                    id=span.span_id,
                    name=span.name,
                    parent_observation_id=span.parent_id,
                    metadata=span.metadata,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("LangfuseTracer._on_start failed: %s", exc)

    async def _on_end(self, span: Span) -> None:
        try:
            trace = self._traces.get(span.trace_id)
            if trace is None:
                return
            update_kwargs: dict[str, Any] = {
                "metadata": {
                    **span.metadata,
                    "duration_ms": span.duration_ms,
                    "status": span.status,
                }
            }
            if span.status == "error" and span.error_message:
                update_kwargs["level"] = "ERROR"
                update_kwargs["status_message"] = span.error_message
            if span.parent_id is None:
                # Root trace finalisation — update the trace-level record.
                trace.update(**update_kwargs)
                # Clean up so we don’t leak memory across runs.
                self._traces.pop(span.trace_id, None)
        except Exception as exc:  # noqa: BLE001
            logger.error("LangfuseTracer._on_end failed: %s", exc)

    async def flush(self) -> None:
        """Flush buffered Langfuse events synchronously."""
        try:
            self._client.flush()
        except Exception as exc:  # noqa: BLE001
            logger.error("LangfuseTracer.flush failed: %s", exc)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(
            f"{name} is required for LangfuseTracer. "
            "See .env.example for reference."
        )
    return value
