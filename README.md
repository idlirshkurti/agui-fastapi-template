# AG-UI FastAPI Template

A production-ready Python template for building AG-UI-compatible agent backends with FastAPI. It demonstrates:

- Streaming agent responses over Server-Sent Events (SSE)
- Tool execution events with incremental progress bars
- Shared state snapshots and JSON Patch deltas
- Multi-turn conversation history with sliding-window context trimming
- Session management (in-memory or Redis-backed)
- Modular agent composition ready for multi-agent handoffs
- Typed Pydantic request/response models
- Rate limiting per IP (slowapi)
- Graceful SSE cancellation on client disconnect
- Web search via Tavily
- Document QA with an in-memory FAISS vector store
- Optional tracing via Langfuse
- Tests and CI

## Architecture

```text
app/
  api/routes.py                # FastAPI /awp endpoint (rate limiting, cancellation)
  agui/emitter.py              # Thin AG-UI event emitter wrapper
  agui/state.py                # Shared state store + JSON Patch generation
  agents/base.py               # Base agent abstraction (emitter, store, history)
  agents/router.py             # Top-level router agent
  agents/research.py           # Example specialist agent
  config.py                    # Environment variable helpers (API keys)
  context/session_store.py     # Session store (in-memory default; Redis-backed optional)
  context/redis_session_store.py  # Redis-backed session store implementation
  context/document_store.py    # Per-session FAISS vector store + loader protocol
  schemas/messages.py          # Message + ConversationHistory models
  schemas/requests.py          # AWPRequest — validated /awp request body
  schemas/search.py            # SearchHit + SearchResult models
  schemas/documents.py         # DocumentPassage + DocumentQAResult models
  schemas/state.py             # Shared UI-visible state
  tools/base.py                # BaseTool abstraction
  tools/search_tool.py         # Web search via Tavily (async, typed)
  tools/document_qa_tool.py    # Retrieval-augmented QA over ingested documents
  tracing/base.py              # Tracer + Span abstractions
  tracing/noop.py              # No-op tracer (default, zero overhead)
  tracing/langfuse.py          # Langfuse tracer backend
  tracing/provider.py          # get_tracer() factory (reads TRACING_BACKEND env var)
  main.py                      # FastAPI app entrypoint
tests/
  test_routes.py               # /awp endpoint integration tests
  test_conversation_history.py # History + session store unit tests
  test_cancellation.py         # SSE disconnect cancellation tests
  test_search_tool.py          # SearchTool unit tests (mocked Tavily)
  test_document_qa_tool.py     # DocumentStore + DocumentQATool unit tests
  test_redis_session_store.py  # RedisSessionStore unit tests (mocked Redis)
  test_tracing.py              # Tracer unit tests
  test_session_store.py        # Session store protocol + backend-switching tests
  test_output_filter.py        # PII / toxicity output filter tests
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]          # core deps + dev/test tools
cp .env.example .env          # fill in TAVILY_API_KEY and OPENAI_API_KEY
uvicorn app.main:app --reload
```

The AG-UI endpoint is available at `POST /awp`. Interactive API docs at `http://localhost:8000/docs`.

### Optional extras

Install additional extras depending on which features you want to use:

| Extra | Installs | When to use |
|---|---|---|
| `redis` | `redis[asyncio]>=5.0` | Redis-backed session store (`RedisSessionStore`) |
| `tracing` | `langfuse>=2.0` | Langfuse tracing backend |

```bash
# Redis session store only
pip install -e .[dev,redis]

# Langfuse tracing only
pip install -e .[dev,tracing]

# Both
pip install -e .[dev,redis,tracing]
```

## Request schema

`POST /awp` expects a JSON body matching `AWPRequest`:

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | ✅ | User input for this turn (min length 1) |
| `session_id` | `string` | ❌ | Conversation session ID. Auto-generated UUID if omitted |
| `thread_id` | `string` | ❌ | Optional AG-UI thread identifier |
| `metadata` | `object` | ❌ | Arbitrary key/value pairs forwarded to agents/tools |

**Example:**

```json
{
  "query": "What is the latest news on AI?",
  "session_id": "user-abc-123",
  "thread_id": "thread-1",
  "metadata": { "locale": "en", "tier": "pro" }
}
```

Invalid requests (missing `query`, empty string) return `422 Unprocessable Entity`.

## Conversation history

Each `session_id` maps to a `ConversationHistory` object that accumulates messages across turns. Pass the same `session_id` in every request to maintain context:

```
Turn 1: POST /awp  { "session_id": "abc", "query": "Hello" }
Turn 2: POST /awp  { "session_id": "abc", "query": "Follow up question" }
```

History is trimmed to the last 20 non-system messages before being passed to the LLM (configurable via `ConversationHistory.trimmed(max_messages=N)`). The system prompt is always preserved.

## Session storage

By default, session history is held **in-memory** via `InMemorySessionStore`. It is lost on process restart and is not shared across multiple workers or replicas.

For production multi-replica deployments, use the included **`RedisSessionStore`**:

```python
from app.context.redis_session_store import RedisSessionStore
from app.context import session_store

session_store.set_backend(RedisSessionStore(url="redis://localhost:6379"))
```

Requires the `redis` extra: `pip install -e .[redis]`.

The `get_or_create / get / delete` interface is identical between backends, so switching is a one-line change with no impact on agents or tools.

## Rate limiting

The `/awp` endpoint is limited to **10 requests per minute per IP** using [slowapi](https://github.com/laurentS/slowapi). Clients that exceed the limit receive `429 Too Many Requests` with a `Retry-After` header.

To change the limit, update the decorator in `app/api/routes.py`:

```python
@limiter.limit("30/minute")  # e.g. for authenticated users
```

For multi-replica deployments, configure a shared Redis storage backend:

```python
from limits.storage import RedisStorage
limiter = Limiter(key_func=get_remote_address, storage_uri="redis://redis:6379")
```

## SSE cancellation

If the client disconnects mid-stream (browser tab closed, network drop), the server detects it via `request.is_disconnected()` and stops the agent run cleanly. No further LLM or tool calls are made after a disconnect.

## Tools

### SearchTool — web search via Tavily

Runs an async Tavily search and emits `TOOL_CALL_START → TOOL_CALL_RESULT → STATE_DELTA`. Results are typed as `SearchResult` (list of `SearchHit` with `title`, `url`, `content`, `score`). Requires `TAVILY_API_KEY`.

### DocumentQATool — retrieval-augmented QA

Ingests documents into a per-session in-memory FAISS vector store, then retrieves the most relevant passages for a given query.

**Supported formats:** `.txt`, `.md`, `.pdf`

**Embedding model:** `text-embedding-3-small` (OpenAI). Vectors are L2-normalised before indexing so inner-product search is equivalent to cosine similarity. Requires `OPENAI_API_KEY`.

**Usage from an agent:**

```python
from app.context.document_store import get_or_create_document_store
from app.tools.document_qa_tool import DocumentQATool

store = get_or_create_document_store(session_id)
tool = DocumentQATool(emitter=emitter, store=state_store, document_store=store)

async for event in tool.run(query="What are the key findings?", file_path="report.pdf", top_k=4):
    yield event
```

Omit `file_path` if the session's document store has already been populated in a previous turn. The tool always returns a `DocumentQAResult` (never raises), so the agent stream stays alive even if ingestion or retrieval fails.

**Adding a new document format:**

Implement the `DocumentLoader` protocol in `app/context/document_store.py` and register it:

```python
class DocxLoader:
    def load(self, path: pathlib.Path) -> str:
        ...

_LOADERS[".docx"] = DocxLoader()
```

## Tracing

The template ships with a lightweight tracing abstraction (`app/tracing/`) that instruments agent spans with zero overhead by default.

**Backends:**

| `TRACING_BACKEND` | Behaviour |
|---|---|
| `noop` (default) | No-op — zero overhead, nothing is sent anywhere |
| `langfuse` | Sends spans to [Langfuse](https://cloud.langfuse.com); requires `LANGFUSE_SECRET_KEY` + `LANGFUSE_PUBLIC_KEY` |

To enable Langfuse tracing:

```bash
pip install -e .[tracing]
export TRACING_BACKEND=langfuse
export LANGFUSE_SECRET_KEY=sk-...
export LANGFUSE_PUBLIC_KEY=pk-...
```

If the `langfuse` package is missing or misconfigured, the server automatically falls back to the no-op tracer — it never fails to start due to tracing misconfiguration.

**Instrumenting an agent:**

```python
from app.tracing.provider import get_tracer

tracer = get_tracer()
async with tracer.span("router", trace_id=session_id, metadata={"query": query}):
    # agent work here
    ...
```

## Example event flow

1. Request arrives with `query` and optional `session_id`.
2. Backend emits `RUN_STARTED` and a `STATE_SNAPSHOT`.
3. The router agent appends the user message to conversation history and updates shared state.
4. A specialist agent picks up the query and delegates to a tool.
5. The tool emits `TOOL_CALL_START`, incremental `TOOL_CALL_PROGRESS` events, and `TOOL_CALL_RESULT`.
6. State changes are mirrored through `STATE_DELTA` events.
7. The assistant reply is appended to conversation history.
8. The run ends with a `TEXT_MESSAGE_CONTENT` event and `RUN_FINISHED`.

## Extending the template

- **Add an agent** — subclass `BaseAgent` in `app/agents/`, implement `run()`, and wire it into `RouterAgent`.
- **Add a tool** — subclass `BaseTool` in `app/tools/`, implement `run()`, and call it from an agent.
- **Add a document format** — implement the `DocumentLoader` protocol and add an entry to `_LOADERS` in `app/context/document_store.py`.
- **Extend shared state** — add fields to `AppState` in `app/schemas/state.py`.
- **Persist history** — swap `InMemorySessionStore` for `RedisSessionStore` via `session_store.set_backend()`.
- **Add tracing** — set `TRACING_BACKEND=langfuse` and instrument agents with `get_tracer().span(...)`.
