# AG-UI FastAPI Template

A production-ready Python template for building AG-UI-compatible agent backends with FastAPI. It demonstrates:

- Streaming agent responses over Server-Sent Events (SSE)
- Tool execution events with incremental progress bars
- Shared state snapshots and JSON Patch deltas
- Multi-turn conversation history with sliding-window context trimming
- Session management (in-memory, Redis-ready)
- Modular agent composition ready for multi-agent handoffs
- Typed Pydantic request/response models
- Rate limiting per IP (slowapi)
- Graceful SSE cancellation on client disconnect
- Tests and CI

## Architecture

```text
app/
  api/routes.py           # FastAPI /awp endpoint (rate limiting, cancellation)
  agui/emitter.py         # Thin AG-UI event emitter wrapper
  agui/state.py           # Shared state store + JSON Patch generation
  agents/base.py          # Base agent abstraction (emitter, store, history)
  agents/router.py        # Top-level router agent
  agents/research.py      # Example specialist agent
  context/session_store.py # In-memory session store (swap to Redis for prod)
  schemas/messages.py     # Message + ConversationHistory models
  schemas/requests.py     # AWPRequest — validated /awp request body
  schemas/state.py        # Shared UI-visible state
  tools/base.py           # Tool runtime with progress updates
  tools/search_tool.py    # Example long-running tool
  main.py                 # FastAPI app entrypoint
tests/
  test_routes.py              # /awp endpoint integration tests
  test_conversation_history.py # History + session store unit tests
  test_cancellation.py        # SSE disconnect cancellation tests
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

The AG-UI endpoint is available at `POST /awp`. Interactive API docs at `http://localhost:8000/docs`.

## Run tests

```bash
pytest tests -v
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

> **Storage note:** History is held in-memory by default. It is lost on process restart and is not shared across multiple workers or replicas. For production multi-replica deployments, replace `InMemorySessionStore` with a Redis-backed implementation — the `get_or_create / get / delete` interface stays the same.

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
- **Extend shared state** — add fields to `AppState` in `app/schemas/state.py`.
- **Persist history** — replace the in-memory dict in `app/context/session_store.py` with a Redis or database backend.
- **Add tracing** — instrument `RouterAgent.run()` with Langfuse or OpenTelemetry spans.
