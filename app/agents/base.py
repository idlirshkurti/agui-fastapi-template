from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore


class BaseAgent(ABC):
    """Abstract base for all agents."""

    def __init__(self, emitter: AGUIEmitter, store: StateStore) -> None:
        self.emitter = emitter
        self.store = store

    @abstractmethod
    async def run(self, payload: dict) -> AsyncIterator[str]:
        """Yield SSE strings."""
        ...
