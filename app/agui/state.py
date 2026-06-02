from __future__ import annotations

from typing import Any

import jsonpatch  # type: ignore[import-untyped]
from app.schemas.state import AppState


class StateStore:
    """Holds the current shared state and computes JSON Patch deltas."""

    def __init__(self, initial: AppState) -> None:
        self._state = initial

    @property
    def state(self) -> AppState:
        return self._state

    def apply(self, updated: AppState) -> list[dict[str, Any]]:
        """Replace current state with *updated* and return the JSON Patch delta."""
        old = self._state.model_dump()
        new = updated.model_dump()
        patch: list[dict[str, Any]] = jsonpatch.make_patch(old, new).patch
        self._state = updated
        return patch

    def snapshot(self) -> dict[str, Any]:
        return self._state.model_dump()
