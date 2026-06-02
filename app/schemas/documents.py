from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentPassage(BaseModel):
    """A single retrieved chunk with its provenance metadata."""

    content: str
    source: str = Field(description="File name or identifier of the source document")
    page: int = Field(ge=0, description="Zero-based page or chunk index")
    score: float = Field(ge=0.0, description="Cosine similarity score (higher → more relevant)")


class DocumentQAResult(BaseModel):
    """Full result payload emitted as TOOL_CALL_RESULT for document QA."""

    query: str
    passages: list[DocumentPassage]
    total: int

    @classmethod
    def empty(cls, query: str) -> "DocumentQAResult":
        """Return an empty result for error / no-results paths."""
        return cls(query=query, passages=[], total=0)
