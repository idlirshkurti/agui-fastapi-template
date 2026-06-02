from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AppState(BaseModel):
    """UI-visible shared state. Extend with your own fields."""

    status: str = "idle"
    current_agent: str = ""
    progress: int = 0
    result: dict[str, Any] = Field(default_factory=dict)
