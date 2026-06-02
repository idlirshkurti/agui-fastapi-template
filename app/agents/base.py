from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.agui.emitter import AGUIEmitter
from app.agui.state import StateStore
from app.schemas.messages import ConversationHistory


class BaseAgent(ABC):
    """Abstract base for all agents."""

    def __init__(
        self,
        emitter: AGUIEmitter,
        store: StateStore,
        history: ConversationHistory | None = None,
    ) -> None:
        self.emitter = emitter
        self.store = store
        self.history = history

    @abstractmethod
    async def run(self, payload: dict) -> AsyncIterator[str]:
        """Yield SSE strings."""
        ...
