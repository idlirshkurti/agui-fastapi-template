from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FilterResult:
    """Result of running an output filter over agent response text."""

    text: str
    """The filtered / redacted text (identical to input when nothing was changed)."""

    redacted: bool = False
    """True when at least one substitution or block was applied."""

    reasons: list[str] = field(default_factory=list)
    """Human-readable tags describing what was changed, e.g. ``['pii:email', 'toxicity']``."""


class GuardrailBase(Protocol):
    """Protocol that every guardrail must satisfy."""

    async def apply(self, text: str) -> FilterResult:
        """Apply the guardrail to *text* and return a :class:`FilterResult`."""
        ...
