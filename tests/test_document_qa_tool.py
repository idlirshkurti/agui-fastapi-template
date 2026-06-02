"""Unit tests for DocumentQATool and DocumentStore.

All OpenAI API calls are mocked so no real network calls are made.
FAISS is exercised with real in-process calls (it is CPU-only and fast).
"""
from __future__ import annotations

import pathlib
import tempfile

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.context.document_store import (
    DocumentStore,
    _chunk_text,
    delete_document_store,
    get_or_create_document_store,
)
from app.schemas.documents import DocumentPassage, DocumentQAResult
from app.schemas.state import AppState
from app.tools.document_qa_tool import DocumentQATool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_embedding_mock(dim: int = 1536) -> AsyncMock:
    """Return a mock AsyncOpenAI client whose embeddings.create returns
    normalised random unit vectors of the expected dimension."""
    mock_client = AsyncMock()

    async def fake_create(model: str, input: list[str]) -> MagicMock:  # noqa: A002
        data = []
        for _ in input:
            vec = np.random.rand(dim).astype(np.float32)
            vec /= np.linalg.norm(vec)
            item = MagicMock()
            item.embedding = vec.tolist()
            data.append(item)
        result = MagicMock()
        result.data = data
        return result

    mock_client.embeddings.create = fake_create
    return mock_client


def _make_tool(store: DocumentStore) -> DocumentQATool:
    return DocumentQATool(
        emitter=AGUIEmitter(),
        store=StateStore(AppState()),
        document_store=store,
    )


async def _collect(tool: DocumentQATool, **kwargs: object) -> list[str]:
    return [event async for event in tool.run(**kwargs)]  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _chunk_text unit tests
# ---------------------------------------------------------------------------

def test_chunk_text_basic_split() -> None:
    text = "a" * 1200
    chunks = _chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) == 3  # 0-500, 450-950, 900-1200
    assert all(len(c) <= 500 for c in chunks)


def test_chunk_text_empty_input_returns_empty_list() -> None:
    assert _chunk_text("") == []
    assert _chunk_text("   ") == []


def test_chunk_text_short_text_returns_single_chunk() -> None:
    chunks = _chunk_text("Hello world", chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0] == "Hello world"


# ---------------------------------------------------------------------------
# DocumentStore unit tests (real FAISS, mocked OpenAI)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_txt_file_and_query() -> None:
    """Ingest a .txt file and verify query returns passages."""
    store = DocumentStore(session_id="test-ingest-txt")
    mock_client = _make_embedding_mock()

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("The quick brown fox jumps over the lazy dog. " * 30)
        tmp_path = pathlib.Path(f.name)

    try:
        with patch.object(store, "_get_client", return_value=mock_client):
            n = await store.ingest(tmp_path)
            assert n > 0
            passages = await store.query("fox", top_k=2)

        assert len(passages) <= 2
        assert all(isinstance(p, DocumentPassage) for p in passages)
        assert all(p.source == tmp_path.name for p in passages)
    finally:
        tmp_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_ingest_md_file() -> None:
    """Markdown files are treated identically to plain text."""
    store = DocumentStore(session_id="test-ingest-md")
    mock_client = _make_embedding_mock()

    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write("# Title\n\n" + "Some content. " * 40)
        tmp_path = pathlib.Path(f.name)

    try:
        with patch.object(store, "_get_client", return_value=mock_client):
            n = await store.ingest(tmp_path)
            assert n > 0
    finally:
        tmp_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_unsupported_extension_raises_value_error() -> None:
    store = DocumentStore(session_id="test-unsupported")
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        tmp_path = pathlib.Path(f.name)
    try:
        with pytest.raises(ValueError, match="Unsupported file type"):
            await store.ingest(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_missing_file_raises_file_not_found_error() -> None:
    store = DocumentStore(session_id="test-missing-file")
    with pytest.raises(FileNotFoundError):
        await store.ingest(pathlib.Path("/nonexistent/path/file.txt"))


@pytest.mark.asyncio
async def test_query_empty_store_returns_empty_list() -> None:
    store = DocumentStore(session_id="test-empty")
    passages = await store.query("anything")
    assert passages == []


def test_is_empty_before_ingest() -> None:
    store = DocumentStore(session_id="test-is-empty")
    assert store.is_empty is True


# ---------------------------------------------------------------------------
# DocumentStore registry tests
# ---------------------------------------------------------------------------

def test_registry_get_or_create_returns_same_instance() -> None:
    delete_document_store("reg-test-1")
    s1 = get_or_create_document_store("reg-test-1")
    s2 = get_or_create_document_store("reg-test-1")
    assert s1 is s2


def test_registry_delete_removes_entry() -> None:
    get_or_create_document_store("reg-test-2")
    delete_document_store("reg-test-2")
    # After deletion a fresh store is created
    s = get_or_create_document_store("reg-test-2")
    assert s.is_empty


# ---------------------------------------------------------------------------
# DocumentQATool tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_emits_expected_events_on_happy_path() -> None:
    """Happy path: TOOL_CALL_START, TOOL_CALL_RESULT, STATE_DELTA all emitted."""
    store = DocumentStore(session_id="tool-happy")
    mock_client = _make_embedding_mock()
    tool = _make_tool(store)

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("Deep learning is a subset of machine learning. " * 20)
        tmp_path = pathlib.Path(f.name)

    try:
        with patch.object(store, "_get_client", return_value=mock_client):
            events = await _collect(tool, query="deep learning", file_path=str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    joined = "".join(events)
    assert "TOOL_CALL_START" in joined
    assert "TOOL_CALL_RESULT" in joined
    assert "STATE_DELTA" in joined


@pytest.mark.asyncio
async def test_tool_returns_empty_result_for_missing_file() -> None:
    """A missing file must not raise — TOOL_CALL_RESULT with empty passages."""
    store = DocumentStore(session_id="tool-missing")
    tool = _make_tool(store)

    events = await _collect(
        tool,
        query="anything",
        file_path="/nonexistent/file.txt",
    )
    joined = "".join(events)
    assert "TOOL_CALL_RESULT" in joined
    assert '"passages": []' in joined


@pytest.mark.asyncio
async def test_tool_returns_empty_result_for_unsupported_format() -> None:
    """An unsupported file type must not raise — TOOL_CALL_RESULT with empty passages."""
    store = DocumentStore(session_id="tool-unsupported")
    tool = _make_tool(store)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        tmp_path = pathlib.Path(f.name)

    try:
        events = await _collect(tool, query="anything", file_path=str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    joined = "".join(events)
    assert "TOOL_CALL_RESULT" in joined
    assert '"passages": []' in joined


@pytest.mark.asyncio
async def test_tool_returns_empty_result_when_store_is_empty_and_no_file() -> None:
    """Querying an empty store with no file_path returns empty passages cleanly."""
    store = DocumentStore(session_id="tool-empty-store")
    tool = _make_tool(store)

    events = await _collect(tool, query="anything")
    joined = "".join(events)
    assert "TOOL_CALL_RESULT" in joined
    assert '"passages": []' in joined


@pytest.mark.asyncio
async def test_tool_result_contains_passage_fields() -> None:
    """TOOL_CALL_RESULT payload contains content, source, page, and score fields."""
    store = DocumentStore(session_id="tool-fields")
    mock_client = _make_embedding_mock()
    tool = _make_tool(store)

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("Artificial intelligence and neural networks. " * 20)
        tmp_path = pathlib.Path(f.name)

    try:
        with patch.object(store, "_get_client", return_value=mock_client):
            events = await _collect(tool, query="neural networks", file_path=str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    result_event = next(e for e in events if "TOOL_CALL_RESULT" in e)
    assert "content" in result_event
    assert "source" in result_event
    assert "page" in result_event
    assert "score" in result_event
