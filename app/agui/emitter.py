import json
from typing import AsyncIterator


class AGUIEmitter:
    """Thin wrapper that formats AG-UI events as SSE lines."""

    @staticmethod
    def _sse(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    def run_started(self, run_id: str) -> str:
        return self._sse("RUN_STARTED", {"runId": run_id})

    def run_finished(self, run_id: str) -> str:
        return self._sse("RUN_FINISHED", {"runId": run_id})

    def text_message(self, content: str) -> str:
        return self._sse("TEXT_MESSAGE_CONTENT", {"content": content})

    def state_snapshot(self, state: dict) -> str:
        return self._sse("STATE_SNAPSHOT", {"snapshot": state})

    def state_delta(self, patch: list[dict]) -> str:
        return self._sse("STATE_DELTA", {"patch": patch})

    def tool_call_start(self, tool_call_id: str, name: str) -> str:
        return self._sse("TOOL_CALL_START", {"toolCallId": tool_call_id, "toolName": name})

    def tool_call_result(self, tool_call_id: str, result: dict) -> str:
        return self._sse("TOOL_CALL_RESULT", {"toolCallId": tool_call_id, "result": result})

    def progress(self, tool_call_id: str, percent: int, message: str = "") -> str:
        return self._sse(
            "TOOL_CALL_PROGRESS",
            {"toolCallId": tool_call_id, "percent": percent, "message": message},
        )
