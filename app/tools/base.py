from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore


class BaseTool(ABC):
    """Abstract base for all tools."""

    def __init__(self, emitter: AGUIEmitter, store: StateStore) -> None:
        self.emitter = emitter
        self.store = store

    @abstractmethod
    async def run(self, **kwargs: Any) -> AsyncIterator[str]:
        ...
