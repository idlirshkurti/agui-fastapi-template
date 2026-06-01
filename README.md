# AG-UI FastAPI Template

A production-ready Python template for building AG-UI-compatible agent backends with FastAPI. It demonstrates:

- Streaming agent status over Server-Sent Events
- Tool execution events with progress bars
- Shared state snapshots and JSON Patch deltas
- Modular agent composition ready for multi-agent handoffs
- Typed Pydantic state models that are easy to extend
- Basic tests and CI

## Architecture

```text
app/
  api/routes.py         # FastAPI AG-UI endpoint
  agui/emitter.py       # Thin AG-UI event emitter wrapper
  agui/state.py         # Shared state store + JSON Patch generation
  agents/base.py        # Base agent abstractions
  agents/router.py      # Top-level router agent
  agents/research.py    # Example specialist agent
  schemas/state.py      # Shared UI-visible state
  tools/base.py         # Tool runtime with progress updates
  tools/search_tool.py  # Example long-running tool
  main.py               # FastAPI app entrypoint
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

The AG-UI endpoint is available at `POST /awp`.

## Example flow

1. A request arrives as an AG-UI run input.
2. The backend emits `RUN_STARTED` and a `STATE_SNAPSHOT`.
3. The router agent updates shared state and hands off to a specialist agent.
4. A tool emits `TOOL_CALL_START`, incremental progress, and `TOOL_CALL_RESULT`.
5. State changes are mirrored through `STATE_DELTA` events.
6. The run ends with assistant text and `RUN_FINISHED`.
