import copy
import jsonpatch
from app.schemas.state import AppState


class StateStore:
    """Holds the current shared state and computes JSON Patch deltas."""

    def __init__(self, initial: AppState) -> None:
        self._state = initial

    @property
    def state(self) -> AppState:
        return self._state

    def apply(self, updated: AppState) -> list[dict]:
        """Replace current state with *updated* and return the JSON Patch delta."""
        old = self._state.model_dump()
        new = updated.model_dump()
        patch = jsonpatch.make_patch(old, new).patch
        self._state = updated
        return patch

    def snapshot(self) -> dict:
        return self._state.model_dump()
