from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class AWPRequest(BaseModel):
    """Validated request body for the /awp AG-UI endpoint.

    Fields
    ------
    session_id:
        Identifies the conversation session. If omitted, a fresh UUID is
        generated so every request still gets a valid session even from
        clients that do not manage session IDs.
    query:
        The user's natural-language input for this turn.
    thread_id:
        Optional AG-UI thread identifier. Useful when a single session
        contains multiple parallel conversation threads.
    metadata:
        Arbitrary key/value pairs forwarded to agents/tools without
        validation. Use for things like locale, user-tier, feature flags.
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str = Field(..., min_length=1, description="User input for this turn")
    thread_id: str | None = Field(default=None, description="Optional AG-UI thread ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary pass-through metadata")
