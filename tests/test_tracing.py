"""Tests for the tracing module — covers all acceptance criteria from issue #5."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tracing.base import Span, Tracer
from app.tracing.noop import NoopTracer
from app.tracing.provider import get_tracer


# ---------------------------------------------------------------------------
# Span dataclass
# ---------------------------------------------------------------------------

def test_span_defaults() -> None:
    s = Span(name="test", trace_id="trace-1")
    assert s.name == "test"
    assert s.trace_id == "trace-1"
    assert s.parent_id is None
    assert s.status == "ok"
    assert s.error_message is None
    assert s.end_time is None
    assert s.duration_ms is None


def test_span_duration_ms() -> None:
    s = Span(name="test", trace_id="t")
    s.start_time = 0.0
    s.end_time = 0.5
    assert abs(s.duration_ms - 500.0) < 0.001


# ---------------------------------------------------------------------------
# NoopTracer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_noop_tracer_is_transparent() -> None:
    tracer = NoopTracer()
    async with tracer.span("op", trace_id="t1") as span:
        span.metadata["key"] = "value"
    assert span.status == "ok"
    assert span.end_time is not None
    assert span.duration_ms is not None


@pytest.mark.asyncio
async def test_noop_tracer_records_error() -> None:
    tracer = NoopTracer()
    with pytest.raises(ValueError, match="boom"):
        async with tracer.span("op", trace_id="t1") as span:
            raise ValueError("boom")
    assert span.status == "error"
    assert span.error_message == "boom"
    assert span.end_time is not None


@pytest.mark.asyncio
async def test_noop_tracer_flush_is_noop() -> None:
    tracer = NoopTracer()
    await tracer.flush()  # must not raise


@pytest.mark.asyncio
async def test_noop_nested_spans() -> None:
    tracer = NoopTracer()
    async with tracer.span("parent", trace_id="t") as parent:
        async with tracer.span("child", trace_id="t", parent_id=parent.span_id) as child:
            pass
    assert child.parent_id == parent.span_id
    assert child.status == "ok"
    assert parent.status == "ok"


# ---------------------------------------------------------------------------
# Base Tracer hooks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tracer_on_start_and_on_end_called() -> None:
    class RecordingTracer(Tracer):
        def __init__(self) -> None:
            self.started: list[str] = []
            self.ended: list[str] = []

        async def _on_start(self, span: Span) -> None:
            self.started.append(span.name)

        async def _on_end(self, span: Span) -> None:
            self.ended.append(span.name)

    tracer = RecordingTracer()
    async with tracer.span("work", trace_id="t"):
        pass

    assert tracer.started == ["work"]
    assert tracer.ended == ["work"]


@pytest.mark.asyncio
async def test_tracer_on_end_called_on_error() -> None:
    class RecordingTracer(Tracer):
        def __init__(self) -> None:
            self.ended_statuses: list[str] = []

        async def _on_end(self, span: Span) -> None:
            self.ended_statuses.append(span.status)

    tracer = RecordingTracer()
    with pytest.raises(RuntimeError):
        async with tracer.span("failing", trace_id="t"):
            raise RuntimeError("fail")

    assert tracer.ended_statuses == ["error"]


# ---------------------------------------------------------------------------
# get_tracer() provider
# ---------------------------------------------------------------------------

def test_get_tracer_default_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRACING_BACKEND", raising=False)
    tracer = get_tracer()
    assert isinstance(tracer, NoopTracer)


def test_get_tracer_noop_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACING_BACKEND", "noop")
    tracer = get_tracer()
    assert isinstance(tracer, NoopTracer)


def test_get_tracer_unknown_backend_falls_back_to_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACING_BACKEND", "opentelemetry")
    tracer = get_tracer()
    assert isinstance(tracer, NoopTracer)


def test_get_tracer_langfuse_import_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACING_BACKEND", "langfuse")
    with patch("app.tracing.provider.LangfuseTracer", side_effect=ImportError("no langfuse")):
        # Patch inside provider module
        import app.tracing.provider as pmod
        original = pmod.__dict__.get("LangfuseTracer")
        try:
            pmod.__dict__["LangfuseTracer"] = MagicMock(side_effect=ImportError("no langfuse"))
            tracer = get_tracer()
            assert isinstance(tracer, NoopTracer)
        finally:
            if original is not None:
                pmod.__dict__["LangfuseTracer"] = original
            else:
                del pmod.__dict__["LangfuseTracer"]


# ---------------------------------------------------------------------------
# LangfuseTracer (mocked client)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_langfuse_tracer_root_span(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")

    mock_trace = MagicMock()
    mock_langfuse = MagicMock()
    mock_langfuse.trace.return_value = mock_trace

    with patch("app.tracing.langfuse.Langfuse", return_value=mock_langfuse):
        from app.tracing.langfuse import LangfuseTracer
        tracer = LangfuseTracer.__new__(LangfuseTracer)
        tracer._client = mock_langfuse
        tracer._traces = {}

        async with tracer.span("router", trace_id="run-1", metadata={"session_id": "s1"}):
            pass

    mock_langfuse.trace.assert_called_once()
    call_kwargs = mock_langfuse.trace.call_args
    assert call_kwargs.kwargs["id"] == "run-1"
    assert call_kwargs.kwargs["name"] == "router"


@pytest.mark.asyncio
async def test_langfuse_tracer_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_langfuse = MagicMock()

    from app.tracing.langfuse import LangfuseTracer
    tracer = LangfuseTracer.__new__(LangfuseTracer)
    tracer._client = mock_langfuse
    tracer._traces = {}

    await tracer.flush()
    mock_langfuse.flush.assert_called_once()


@pytest.mark.asyncio
async def test_langfuse_tracer_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)

    with patch("app.tracing.langfuse.Langfuse"):
        from app.tracing.langfuse import _require_env
        with pytest.raises(ValueError, match="LANGFUSE_SECRET_KEY"):
            _require_env("LANGFUSE_SECRET_KEY")
