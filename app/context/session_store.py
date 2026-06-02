from __future__ import annotations

from app.schemas.messages import ConversationHistory

# In-memory store: maps session_id -> ConversationHistory.
# This is intentionally simple and suitable for single-instance / local dev.
#
# For multi-replica / production deployments, replace this module with a
# Redis-backed implementation that serialises ConversationHistory to JSON.
# The interface (get_or_create / get / delete) should stay the same so that
# agent code does not need to change.
_store: dict[str, ConversationHistory] = {}


def get_or_create(session_id: str) -> ConversationHistory:
    """Return the existing history for *session_id* or create a fresh one."""
    if session_id not in _store:
        _store[session_id] = ConversationHistory(session_id=session_id)
    return _store[session_id]


def get(session_id: str) -> ConversationHistory | None:
    """Return history if it exists, else None."""
    return _store.get(session_id)


def delete(session_id: str) -> None:
    """Remove a session from the store."""
    _store.pop(session_id, None)
