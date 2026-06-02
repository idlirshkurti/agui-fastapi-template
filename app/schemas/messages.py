from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single turn in a conversation."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None  # only relevant for role="tool"


class ConversationHistory(BaseModel):
    """Session-scoped list of messages passed to the LLM each turn.

    Storage note
    ------------
    This object lives in the in-memory SessionStore by default. That means
    history is lost on process restart and is NOT shared across multiple
    workers or replicas. For production multi-replica deployments, swap
    SessionStore for a Redis-backed implementation (see session_store.py).
    """

    session_id: str
    messages: list[Message] = Field(default_factory=list)

    def add(self, role: Literal["system", "user", "assistant", "tool"], content: str, **kwargs: str) -> None:
        """Append a message to the history."""
        self.messages.append(Message(role=role, content=content, **kwargs))

    def trimmed(self, max_messages: int = 20) -> list[dict[str, Any]]:
        """Return a token-safe slice of the history for LLM consumption.

        Strategy: always preserve the system prompt (first message if
        role=="system"), then keep the last *max_messages* non-system turns.
        Adjust *max_messages* based on your model's context window and
        average message length.
        """
        system = [m for m in self.messages if m.role == "system"]
        rest = [m for m in self.messages if m.role != "system"]
        trimmed = system + rest[-max_messages:]
        return [m.model_dump(exclude_none=True) for m in trimmed]

    def to_llm_format(self) -> list[dict[str, Any]]:
        """Return the full history in LLM message-list format (no trimming)."""
        return [m.model_dump(exclude_none=True) for m in self.messages]
