from pydantic import BaseModel, Field


class AppState(BaseModel):
    """UI-visible shared state. Extend with your own fields."""

    status: str = "idle"
    current_agent: str = ""
    progress: int = 0
    result: dict = Field(default_factory=dict)
