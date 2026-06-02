from __future__ import annotations

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    """A single result returned by the search tool."""

    title: str
    url: str
    content: str
    score: float = Field(ge=0.0, le=1.0)


class SearchResult(BaseModel):
    """The full result payload emitted as TOOL_CALL_RESULT."""

    query: str
    hits: list[SearchHit]
    total: int

    @classmethod
    def empty(cls, query: str) -> "SearchResult":
        return cls(query=query, hits=[], total=0)
