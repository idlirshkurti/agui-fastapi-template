"""Unit tests for the pluggable session store abstraction."""
from __future__ import annotations

from app.context.session_store import (
    InMemorySessionStore,
    SessionStore,
    delete,
    get,
    get_backend,
    get_or_create,
    set_backend,
)
from app.schemas.messages import ConversationHistory


# ---------------------------------------------------------------------------
# SessionStore protocol compliance
# ---------------------------------------------------------------------------

def test_in_memory_store_satisfies_protocol() -> None:
    """InMemorySessionStore must be recognised as a SessionStore at runtime."""
    assert isinstance(InMemorySessionStore(), SessionStore)


# ---------------------------------------------------------------------------
# InMemorySessionStore behaviour
# ---------------------------------------------------------------------------

def test_get_or_create_returns_conversation_history() -> None:
    store = InMemorySessionStore()
    h = store.get_or_create("s1")
    assert isinstance(h, ConversationHistory)
    assert h.session_id == "s1"


def test_get_or_create_returns_same_instance() -> None:
    store = InMemorySessionStore()
    h1 = store.get_or_create("s2")
    h2 = store.get_or_create("s2")
    assert h1 is h2


def test_get_returns_none_for_missing_session() -> None:
    store = InMemorySessionStore()
    assert store.get("nonexistent") is None


def test_get_returns_existing_session() -> None:
    store = InMemorySessionStore()
    store.get_or_create("s3")
    assert store.get("s3") is not None


def test_delete_removes_session() -> None:
    store = InMemorySessionStore()
    store.get_or_create("s4")
    store.delete("s4")
    assert store.get("s4") is None


def test_delete_nonexistent_session_is_a_noop() -> None:
    store = InMemorySessionStore()
    store.delete("never-existed")  # must not raise


def test_history_persists_across_calls() -> None:
    store = InMemorySessionStore()
    h = store.get_or_create("s5")
    h.add("user", "hello")
    h2 = store.get_or_create("s5")
    assert len(h2.messages) == 1
    assert h2.messages[0].content == "hello"


# ---------------------------------------------------------------------------
# Module-level shims delegate to the active backend
# ---------------------------------------------------------------------------

def test_module_shims_delegate_to_backend() -> None:
    """The module-level get/get_or_create/delete must proxy to the active backend."""
    fresh = InMemorySessionStore()
    original = get_backend()
    try:
        set_backend(fresh)
        h = get_or_create("shim-1")
        assert isinstance(h, ConversationHistory)
        assert get("shim-1") is h
        delete("shim-1")
        assert get("shim-1") is None
    finally:
        set_backend(original)


# ---------------------------------------------------------------------------
# set_backend / get_backend
# ---------------------------------------------------------------------------

def test_set_backend_replaces_active_store() -> None:
    original = get_backend()
    try:
        new_store = InMemorySessionStore()
        set_backend(new_store)
        assert get_backend() is new_store
    finally:
        set_backend(original)


def test_custom_backend_satisfying_protocol_is_accepted() -> None:
    """A minimal hand-rolled backend satisfying the protocol is accepted."""

    class MinimalStore:
        def __init__(self) -> None:
            self._d: dict[str, ConversationHistory] = {}

        def get_or_create(self, session_id: str) -> ConversationHistory:
            if session_id not in self._d:
                self._d[session_id] = ConversationHistory(session_id=session_id)
            return self._d[session_id]

        def get(self, session_id: str) -> ConversationHistory | None:
            return self._d.get(session_id)

        def delete(self, session_id: str) -> None:
            self._d.pop(session_id, None)

    assert isinstance(MinimalStore(), SessionStore)

    original = get_backend()
    try:
        set_backend(MinimalStore())
        h = get_or_create("custom-1")
        assert isinstance(h, ConversationHistory)
    finally:
        set_backend(original)
