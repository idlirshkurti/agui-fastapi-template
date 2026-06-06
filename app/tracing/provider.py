from __future__ import annotations

import logging
import os

from app.tracing.base import Tracer
from app.tracing.noop import NoopTracer

logger = logging.getLogger(__name__)

_BACKENDS = {"noop", "langfuse"}


def get_tracer() -> Tracer:
    """Return the configured tracer instance.

    Reads ``TRACING_BACKEND`` from the environment:

    * ``noop`` (default) — :class:`NoopTracer`, zero overhead
    * ``langfuse``       — :class:`LangfuseTracer`, requires
      ``LANGFUSE_SECRET_KEY`` and ``LANGFUSE_PUBLIC_KEY``

    Any import or configuration error falls back to :class:`NoopTracer`
    so the application never fails to start due to tracing misconfiguration.
    """
    backend = os.environ.get("TRACING_BACKEND", "noop").strip().lower()

    if backend not in _BACKENDS:
        logger.warning(
            "Unknown TRACING_BACKEND=%r, falling back to noop. Valid options: %s",
            backend,
            ", ".join(sorted(_BACKENDS)),
        )
        return NoopTracer()

    if backend == "noop":
        return NoopTracer()

    if backend == "langfuse":
        try:
            from app.tracing.langfuse import LangfuseTracer
            return LangfuseTracer()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to initialise LangfuseTracer (%s), falling back to noop.", exc
            )
            return NoopTracer()

    return NoopTracer()  # unreachable, but satisfies type checkers
