from app.schemas.messages import ConversationHistory
from app.context.session_store import get_or_create, get, delete


# --- ConversationHistory unit tests ---

def test_add_and_retrieve_messages():
    h = ConversationHistory(session_id="test-1")
    h.add("user", "Hello")
    h.add("assistant", "Hi there")
    assert len(h.messages) == 2
    assert h.messages[0].role == "user"
    assert h.messages[1].content == "Hi there"


def test_to_llm_format_excludes_none():
    h = ConversationHistory(session_id="test-2")
    h.add("user", "Hello")
    fmt = h.to_llm_format()
    assert fmt == [{"role": "user", "content": "Hello"}]
    assert "tool_call_id" not in fmt[0]


def test_trimmed_preserves_system_prompt():
    h = ConversationHistory(session_id="test-3")
    h.add("system", "You are a helpful assistant.")
    for i in range(25):
        h.add("user", f"message {i}")
    trimmed = h.trimmed(max_messages=10)
    # System prompt always first
    assert trimmed[0]["role"] == "system"
    # Only 10 non-system messages kept
    non_system = [m for m in trimmed if m["role"] != "system"]
    assert len(non_system) == 10


def test_trimmed_short_history_unchanged():
    h = ConversationHistory(session_id="test-4")
    h.add("user", "Hi")
    h.add("assistant", "Hello")
    trimmed = h.trimmed(max_messages=20)
    assert len(trimmed) == 2


# --- SessionStore unit tests ---

def test_get_or_create_returns_same_instance():
    delete("sess-1")  # clean up if exists
    h1 = get_or_create("sess-1")
    h2 = get_or_create("sess-1")
    assert h1 is h2


def test_get_returns_none_for_missing_session():
    delete("sess-missing")
    assert get("sess-missing") is None


def test_delete_removes_session():
    get_or_create("sess-del")
    delete("sess-del")
    assert get("sess-del") is None


def test_history_persists_across_get_or_create_calls():
    delete("sess-2")
    h = get_or_create("sess-2")
    h.add("user", "first message")
    h2 = get_or_create("sess-2")
    assert len(h2.messages) == 1
    assert h2.messages[0].content == "first message"
