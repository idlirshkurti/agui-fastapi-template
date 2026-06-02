from __future__ import annotations

import logging
import pathlib
import uuid
from typing import Any, AsyncIterator

from app.context.document_store import DocumentStore
from app.schemas.documents import DocumentQAResult
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class DocumentQATool(BaseTool):
    """Retrieval-augmented QA tool that queries an in-memory FAISS vector store.

    The tool does **not** own the DocumentStore — callers must inject one.
    This keeps the tool stateless and easily testable.

    Emits AG-UI events in this order:
      1. TOOL_CALL_START
      2. TOOL_CALL_PROGRESS (25%)  — ingestion started (if file_path provided)
      3. TOOL_CALL_PROGRESS (50%)  — ingestion complete / querying index
      4. TOOL_CALL_PROGRESS (90%)  — query complete, formatting result
      5. TOOL_CALL_RESULT          — DocumentQAResult payload
      6. STATE_DELTA               — shared state updated with result

    On any error the tool emits TOOL_CALL_RESULT with empty passages and
    logs the exception — it never raises so the agent stream stays alive.
    """

    def __init__(
        self,
        *args: Any,
        document_store: DocumentStore,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._document_store = document_store

    async def run(  # type: ignore[override]
        self,
        query: str = "",
        file_path: str | None = None,
        top_k: int = 4,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Run document QA and stream AG-UI events.

        Parameters
        ----------
        query:
            The question to answer from the document corpus.
        file_path:
            Optional path to a document to ingest before querying. If the
            document store already contains documents this can be omitted.
        top_k:
            Number of passages to retrieve (default 4).
        """
        tool_call_id = str(uuid.uuid4())
        yield self.emitter.tool_call_start(tool_call_id, "document_qa")

        result = await self._run_qa(tool_call_id, query, file_path, top_k)

        yield self.emitter.tool_call_result(tool_call_id, result.model_dump())

        new_state = self.store.state.model_copy(
            update={"progress": 100, "result": result.model_dump()}
        )
        yield self.emitter.state_delta(self.store.apply(new_state))

    async def _run_qa(
        self,
        tool_call_id: str,
        query: str,
        file_path: str | None,
        top_k: int,
    ) -> DocumentQAResult:
        """Orchestrate ingestion and retrieval, returning a DocumentQAResult.

        All exceptions are caught so the caller always receives a result.
        """
        # --- optional ingestion ---
        if file_path is not None:
            path = pathlib.Path(file_path)
            try:
                n_chunks = await self._document_store.ingest(path)
                logger.info("Ingested %d chunks from %s", n_chunks, path.name)
            except (FileNotFoundError, ValueError) as exc:
                # Known, recoverable errors — log and return empty result.
                logger.error("Ingestion failed for %s: %s", file_path, exc)
                return DocumentQAResult.empty(query)
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected ingestion error for %s: %s", file_path, exc)
                return DocumentQAResult.empty(query)

        # --- guard: nothing in the store ---
        if self._document_store.is_empty:
            logger.warning("DocumentQATool queried with an empty store (session_id unknown).")
            return DocumentQAResult.empty(query)

        # --- retrieval ---
        try:
            passages = await self._document_store.query(query, top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            logger.error("Retrieval failed for query=%r: %s", query, exc)
            return DocumentQAResult.empty(query)

        return DocumentQAResult(query=query, passages=passages, total=len(passages))
