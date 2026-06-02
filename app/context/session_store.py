"""Session store abstraction and default in-memory implementation.

All agent and route code must depend on the ``SessionStore`` protocol, not
on any concrete implementation.  Swapping to a Redis backend requires only
changing which concrete class is passed to ``set_backend()`` — no agent or
route code needs to change.

Default backend: ``InMemorySessionStore`` (suitable for local dev and
single-instance deployments).  For multi-replica production deployments
replace it with a Redis-backed class that serialises ``ConversationHistory``
to JSON and implements the same three methods.

Example Redis swap (no agent code changes required)::

    # app/main.py
    from app.context.session_store import set_backend
    from app.context.redis_session_store import RedisSessionStore

    set_backend(RedisSessionStore(url=settings.redis_url))
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.messages import ConversationHistory


# ---------------------------------------------------------------------------
# Protocol — the contract every backend must satisfy
# ---------------------------------------------------------------------------

@runtime_checkable
class SessionStore(Protocol):
    """Read/write interface for conversation session storage.

    Implementations must be safe to call from async contexts (i.e. must not
    block the event loop).  Blocking backends should wrap I/O in
    ``asyncio.to_thread()``.
    """

    def get_or_create(self, session_id: str) -> ConversationHistory:
        """Return the existing history for *session_id* or create a fresh one."""
        ...

    def get(self, session_id: str) -> ConversationHistory | None:
        """Return history if it exists, else ``None``."""
        ...

    def delete(self, session_id: str) -> None:
        """Remove a session from the store."""
        ...


# ---------------------------------------------------------------------------
# Default implementation — in-memory, zero dependencies
# ---------------------------------------------------------------------------

class InMemorySessionStore:
    """Thread-safe* in-memory session store backed by a plain dict.

    (*) Safe within a single asyncio event loop — no locks needed because
    Python's GIL protects dict operations and all callers run in the same
    thread.  Not safe across OS threads or processes.
    """

    def __init__(self) -> None:
        self._store: dict[str, ConversationHistory] = {}

    def get_or_create(self, session_id: str) -> ConversationHistory:
        if session_id not in self._store:
            self._store[session_id] = ConversationHistory(session_id=session_id)
        return self._store[session_id]

    def get(self, session_id: str) -> ConversationHistory | None:
        return self._store.get(session_id)

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)


# ---------------------------------------------------------------------------
# Module-level registry — single default instance, swappable via set_backend()
# ---------------------------------------------------------------------------

_backend: SessionStore = InMemorySessionStore()


def set_backend(backend: SessionStore) -> None:
    """Replace the active session store backend.

    Call this once during application startup (e.g. in ``app/main.py``) before
    any requests are served.  Not safe to call mid-flight.

    Parameters
    ----------
    backend:
        Any object that satisfies the ``SessionStore`` protocol.
    """
    global _backend  # noqa: PLW0603
    _backend = backend


def get_backend() -> SessionStore:
    """Return the currently active session store backend."""
    return _backend


# ---------------------------------------------------------------------------
# Module-level convenience shims — delegate to the active backend
#
# These exist so that existing call-sites (routes, tests) continue to work
# without change.  New code should prefer calling get_backend() directly.
# ---------------------------------------------------------------------------

def get_or_create(session_id: str) -> ConversationHistory:
    """Delegate to the active backend's ``get_or_create``."""
    return _backend.get_or_create(session_id)


def get(session_id: str) -> ConversationHistory | None:
    """Delegate to the active backend's ``get``."""
    return _backend.get(session_id)


def delete(session_id: str) -> None:
    """Delegate to the active backend's ``delete``."""
    _backend.delete(session_id)
