from __future__ import annotations

import asyncio
import logging
import pathlib
from typing import Any, Protocol, runtime_checkable

import faiss  # type: ignore[import-untyped]
import numpy as np
from openai import AsyncOpenAI

from app.config import get_openai_api_key
from app.schemas.documents import DocumentPassage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable constants
# ---------------------------------------------------------------------------
_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 50
_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 1536
_DEFAULT_TOP_K = 4
_SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


# ---------------------------------------------------------------------------
# Loader protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class DocumentLoader(Protocol):
    """Read a file and return its raw text content."""

    def load(self, path: pathlib.Path) -> str:
        ...


class PlainTextLoader:
    """Loader for .txt and .md files."""

    def load(self, path: pathlib.Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")


class PDFLoader:
    """Loader for .pdf files using pypdf."""

    def load(self, path: pathlib.Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError(
                "pypdf is required for PDF support. Run: pip install pypdf"
            ) from exc

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)


_LOADERS: dict[str, DocumentLoader] = {
    ".txt": PlainTextLoader(),
    ".md": PlainTextLoader(),
    ".pdf": PDFLoader(),
}


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
def _chunk_text(
    text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP
) -> list[str]:
    """Split *text* into overlapping fixed-size character chunks."""
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


# ---------------------------------------------------------------------------
# In-memory FAISS document store, scoped per session
# ---------------------------------------------------------------------------
class DocumentStore:
    """Ingests documents, embeds them via OpenAI, and retrieves top-k passages."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._index: faiss.IndexFlatIP | None = None
        self._chunks: list[tuple[str, str, int]] = []
        self._client: AsyncOpenAI | None = None

    async def ingest(self, path: pathlib.Path) -> int:
        """Load *path*, chunk it, embed the chunks, and add them to the index."""
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        suffix = path.suffix.lower()
        if suffix not in _SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type {suffix!r}. "
                f"Supported types: {sorted(_SUPPORTED_EXTENSIONS)}"
            )

        loader = _LOADERS[suffix]
        text = await asyncio.to_thread(loader.load, path)
        chunks = _chunk_text(text)

        if not chunks:
            logger.warning("Document %s produced no chunks after splitting.", path.name)
            return 0

        embeddings = await self._embed(chunks)
        self._add_to_index(chunks, embeddings, source=path.name)
        logger.info(
            "Ingested %d chunks from %s into session=%s",
            len(chunks),
            path.name,
            self._session_id,
        )
        return len(chunks)

    async def query(
        self, query: str, top_k: int = _DEFAULT_TOP_K
    ) -> list[DocumentPassage]:
        """Return the *top_k* most relevant passages for *query*."""
        if self._index is None or not self._chunks:
            return []

        query_vec = await self._embed([query])
        k = min(top_k, len(self._chunks))
        scores, indices = self._index.search(query_vec, k)

        passages: list[DocumentPassage] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            content, source, page = self._chunks[idx]
            passages.append(
                DocumentPassage(
                    content=content,
                    source=source,
                    page=page,
                    score=float(score),
                )
            )
        return passages

    @property
    def is_empty(self) -> bool:
        return self._index is None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=get_openai_api_key())
        return self._client

    async def _embed(
        self, texts: list[str]
    ) -> np.ndarray[Any, np.dtype[np.float32]]:
        """Call the OpenAI embeddings API and return an (N, D) float32 array."""
        response = await self._get_client().embeddings.create(
            model=_EMBEDDING_MODEL,
            input=texts,
        )
        vectors = np.array(
            [item.embedding for item in response.data], dtype=np.float32
        )
        norms: np.ndarray[Any, np.dtype[np.float32]] = np.linalg.norm(
            vectors, axis=1, keepdims=True
        ).astype(np.float32)
        norms = np.where(norms == 0, np.float32(1.0), norms)
        return (vectors / norms).astype(np.float32)

    def _add_to_index(
        self,
        chunks: list[str],
        embeddings: np.ndarray[Any, np.dtype[np.float32]],
        source: str,
    ) -> None:
        """Initialise the FAISS index on first call, then add new vectors."""
        if self._index is None:
            self._index = faiss.IndexFlatIP(_EMBEDDING_DIM)
        self._index.add(embeddings)
        for i, chunk in enumerate(chunks):
            self._chunks.append((chunk, source, i))


# ---------------------------------------------------------------------------
# Session-scoped registry
# ---------------------------------------------------------------------------
_registry: dict[str, DocumentStore] = {}


def get_or_create_document_store(session_id: str) -> DocumentStore:
    """Return the existing DocumentStore for *session_id* or create a new one."""
    if session_id not in _registry:
        _registry[session_id] = DocumentStore(session_id=session_id)
    return _registry[session_id]


def delete_document_store(session_id: str) -> None:
    """Remove the DocumentStore for *session_id* from the registry."""
    _registry.pop(session_id, None)
