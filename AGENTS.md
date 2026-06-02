# AGENTS.md — Instructions for AI Coding Assistants

This file describes the conventions, patterns, and rules that govern this codebase.
Read it in full before making any change.

---

## Project overview

A production-ready FastAPI backend template for [AG-UI](https://github.com/ag-ui-protocol/ag-ui)-compatible agents.
The backend streams Server-Sent Events (SSE) to a frontend, carrying AG-UI protocol events:
state snapshots, JSON Patch deltas, tool calls, and run lifecycle markers.

The entry point is `POST /awp` in `app/api/routes.py`.
All agent logic, tool execution, and state management happen inside the streaming generator
that this endpoint drives.

---

## Repo layout

```
app/
  api/routes.py                # FastAPI /awp endpoint — do not add business logic here
  agui/emitter.py              # AGUIEmitter — the only place SSE strings are formatted
  agui/state.py                # StateStore — the only place state mutations happen
  agents/base.py               # BaseAgent ABC — all agents extend this
  agents/router.py             # RouterAgent — top-level dispatcher, wire new agents here
  agents/research.py           # Example specialist agent
  config.py                    # _require_env(), get_tavily_api_key(), get_openai_api_key()
  context/session_store.py     # Per-session ConversationHistory registry
  context/document_store.py    # Per-session FAISS vector store + DocumentLoader protocol
  schemas/messages.py          # Message, ConversationHistory
  schemas/requests.py          # AWPRequest — validated /awp body
  schemas/search.py            # SearchHit, SearchResult
  schemas/documents.py         # DocumentPassage, DocumentQAResult
  schemas/state.py             # AppState — the single source of truth for shared UI state
  tools/base.py                # BaseTool ABC — all tools extend this
  tools/search_tool.py         # Web search via Tavily (async)
  tools/document_qa_tool.py    # Retrieval-augmented QA via FAISS + OpenAI embeddings
  main.py                      # FastAPI app factory — add middleware/routers here
tests/
  test_routes.py
  test_conversation_history.py
  test_cancellation.py
  test_search_tool.py
  test_document_qa_tool.py
```

---

## Language and tooling

| Concern | Choice |
|---|---|
| Python version | 3.11+ |
| Linter | `ruff` (`line-length = 100`) |
| Type checker | `mypy --strict` |
| Test runner | `pytest` with `asyncio_mode = "auto"` |
| Build backend | `hatchling` |

Run the full check suite before finishing any task:

```bash
ruff check app tests          # lint
mypy app                      # type-check
pytest tests -v               # tests
```

All three must pass with zero errors. Do not add `# type: ignore` without a comment explaining why.

---

## Core conventions

### 1. Every file starts with `from __future__ import annotations`

This enables PEP 604 union syntax (`X | Y`) and forward references on all Python 3.11 builds.
Do not omit it.

### 2. SSE strings come only from `AGUIEmitter`

`app/agui/emitter.py` is the single place where SSE lines are constructed.
Never write `f"event: ...\ndata: ...\n\n"` strings anywhere else.
All agents and tools hold a reference to an `AGUIEmitter` instance injected at construction time.

Available emitter methods:

```python
emitter.run_started(run_id)              # RUN_STARTED
emitter.run_finished(run_id)             # RUN_FINISHED
emitter.text_message(content)            # TEXT_MESSAGE_CONTENT
emitter.state_snapshot(state_dict)       # STATE_SNAPSHOT
emitter.state_delta(patch_list)          # STATE_DELTA
emitter.tool_call_start(id, name)        # TOOL_CALL_START
emitter.tool_call_result(id, result)     # TOOL_CALL_RESULT
emitter.progress(id, percent, message)   # TOOL_CALL_PROGRESS
emitter.tool_call_error(id, error)       # TOOL_CALL_ERROR
```

### 3. State mutations go through `StateStore.apply()`

`app/agui/state.py` is the single place where `AppState` is mutated.
The pattern is always:

```python
new_state = self.store.state.model_copy(update={"field": value})
yield self.emitter.state_delta(self.store.apply(new_state))
```

Never mutate `AppState` fields in place. Never emit `STATE_DELTA` with a hand-crafted patch list.

### 4. Tools never raise — they return empty result objects

Tools stream AG-UI events to a live SSE connection.
An unhandled exception kills the stream for the user.
All exception paths must be caught, logged, and resolved to an empty typed result.

Pattern:

```python
try:
    result = await do_something()
except (KnownError1, KnownError2) as exc:
    logger.error("Descriptive message: %s", exc)
    return ResultType.empty(query)
except Exception as exc:  # noqa: BLE001
    logger.error("Unexpected error: %s", exc)
    return ResultType.empty(query)
```

The `# noqa: BLE001` comment is **required** on any intentional broad `except Exception`.
Do not suppress exceptions silently — always `logger.error()`.

### 5. New environment variables go through `config.py`

Do not call `os.environ.get()` inline in tools or agents.
Add a getter to `app/config.py` using the shared `_require_env(name, hint)` helper:

```python
def get_my_service_api_key() -> str:
    return _require_env(
        "MY_SERVICE_API_KEY",
        "Add your key from https://example.com/api-keys.",
    )
```

The key is only read when the function is called, so the server starts without it.
Document the new variable in `.env.example`.

### 6. All models are Pydantic v2

Use `model_copy(update={...})` not `model.field = value`.
Use `model_dump()` not `.dict()`.
Use `model_validate(data)` not `.parse_obj(data)`.
Add field-level constraints (`Field(ge=0, le=1)`, `Field(min_length=1)`) wherever the domain warrants them.

### 7. Async everywhere

All I/O is async. Never call blocking I/O (file reads, HTTP requests, CPU-heavy ops) from a coroutine without wrapping in `asyncio.to_thread()`.
The `DocumentStore._embed()` and PDF loading already demonstrate this pattern.

---

## Adding an agent

1. Create `app/agents/<name>.py`.
2. Subclass `BaseAgent`; implement `async def run(self, payload: dict) -> AsyncIterator[str]`.
3. Yield only strings produced by `self.emitter.*` methods.
4. Wire the new agent into `RouterAgent` in `app/agents/router.py`.
5. Add at least one test in `tests/test_<name>_agent.py`.

```python
from __future__ import annotations

from typing import AsyncIterator
from app.agents.base import BaseAgent


class MyAgent(BaseAgent):
    async def run(self, payload: dict) -> AsyncIterator[str]:  # type: ignore[override]
        yield self.emitter.text_message("Hello from MyAgent")
```

---

## Adding a tool

1. Create `app/tools/<name>_tool.py`.
2. Subclass `BaseTool`; implement `async def run(self, **kwargs) -> AsyncIterator[str]`.
3. Define a typed result schema in `app/schemas/` with a `.empty()` factory.
4. Follow the event sequence: `TOOL_CALL_START → (TOOL_CALL_PROGRESS)* → TOOL_CALL_RESULT → STATE_DELTA`.
5. Catch all exceptions — the tool must never raise (see convention #4).
6. Add tests in `tests/test_<name>_tool.py`. Mock all external I/O.

---

## Adding a document format

Implement the `DocumentLoader` protocol and register it in `_LOADERS`:

```python
# app/context/document_store.py

class DocxLoader:
    def load(self, path: pathlib.Path) -> str:
        ...  # return raw text

_LOADERS[".docx"] = DocxLoader()
```

Add the new extension to `_SUPPORTED_EXTENSIONS` in the same file.
No other files need to change.

---

## Adding a new environment variable

1. Add a getter in `app/config.py` using `_require_env()`.
2. Add the variable to `.env.example` with a comment describing where to obtain it.
3. Do not add it to any other file — always call the getter from `config.py`.

---

## Testing rules

- Every new module gets a corresponding test file.
- All external I/O (HTTP calls, OpenAI, Tavily, file system) is mocked — no real network calls in tests.
- Use `pytest-mock` or `unittest.mock.patch` / `AsyncMock`; do not reach for `monkeypatch` for async code.
- Tests are `async def` functions decorated with nothing — `asyncio_mode = "auto"` handles it.
- Test the error paths explicitly: missing API key, network timeout, bad input, empty store.
- Do not assert on exact SSE string formats; assert on substrings like `"TOOL_CALL_RESULT"` and field names like `"passages"`.

---

## What not to do

- **Do not add business logic to `app/api/routes.py`.** The route handler constructs the emitter, store, and history, then hands off to `RouterAgent`. Keep it that way.
- **Do not import from `app.api` inside `app.agents` or `app.tools`.** The dependency direction is one-way: routes → agents/tools → agui/schemas/context/config.
- **Do not write raw `json.dumps` SSE strings outside `AGUIEmitter`.**
- **Do not mutate `AppState` fields directly** — always go through `StateStore.apply()`.
- **Do not add `localStorage` or any browser-side persistence** — this is a server-only repo.
- **Do not commit `.env`** — it is gitignored. Only `.env.example` is committed.
- **Do not use `print()` for logging** — use `logging.getLogger(__name__)` and the appropriate level.
- **Do not widen `mypy` ignores** — if mypy flags something, fix the type, don't suppress it unless absolutely necessary and justified by a comment.
