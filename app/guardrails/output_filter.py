from __future__ import annotations

import os
import re

from app.guardrails.base import FilterResult

# ---------------------------------------------------------------------------
# PII patterns
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
_PHONE_RE = re.compile(
    r"(?:\+?\d[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?){1,2}\d{3}[\s.\-]?\d{4}"
)
_CREDIT_CARD_RE = re.compile(
    r"\b(?:\d[ \-]?){13,16}\b"
)

_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (_EMAIL_RE, "[REDACTED_EMAIL]", "pii:email"),
    (_PHONE_RE, "[REDACTED_PHONE]", "pii:phone"),
    (_CREDIT_CARD_RE, "[REDACTED_CARD]", "pii:credit_card"),
]

# ---------------------------------------------------------------------------
# Toxicity keyword blocklist (extend as needed)
# ---------------------------------------------------------------------------
_TOXIC_KEYWORDS: list[str] = [
    "kill yourself",
    "kys",
    "hate speech",
    "racial slur",
    "go die",
]


def _is_enabled(env_var: str) -> bool:
    """Return True when *env_var* is set to a truthy string value."""
    return os.environ.get(env_var, "").strip().lower() in {"1", "true", "yes"}


class OutputFilterGuardrail:
    """Screens agent response text before it is sent to the client.

    Each filter type is opt-in via environment variables:

    * ``ENABLE_PII_FILTER=true``  — redact emails, phone numbers, credit cards
    * ``ENABLE_TOXICITY_FILTER=true`` — block / redact toxic content

    When both flags are unset the guardrail is a transparent pass-through.
    """

    def __init__(
        self,
        *,
        enable_pii: bool | None = None,
        enable_toxicity: bool | None = None,
    ) -> None:
        self._pii = enable_pii if enable_pii is not None else _is_enabled("ENABLE_PII_FILTER")
        self._toxicity = (
            enable_toxicity
            if enable_toxicity is not None
            else _is_enabled("ENABLE_TOXICITY_FILTER")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def apply(self, text: str) -> FilterResult:
        """Run enabled filters over *text* and return a :class:`FilterResult`."""
        reasons: list[str] = []
        current = text

        if self._pii:
            current, pii_reasons = self._redact_pii(current)
            reasons.extend(pii_reasons)

        if self._toxicity:
            current, tox_reasons = self._filter_toxicity(current)
            reasons.extend(tox_reasons)

        return FilterResult(
            text=current,
            redacted=bool(reasons),
            reasons=reasons,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _redact_pii(text: str) -> tuple[str, list[str]]:
        reasons: list[str] = []
        for pattern, replacement, tag in _PII_PATTERNS:
            new_text, count = pattern.subn(replacement, text)
            if count:
                text = new_text
                reasons.append(tag)
        return text, reasons

    @staticmethod
    def _filter_toxicity(text: str) -> tuple[str, list[str]]:
        lower = text.lower()
        for keyword in _TOXIC_KEYWORDS:
            if keyword in lower:
                return "[RESPONSE BLOCKED: content policy violation]", ["toxicity"]
        return text, []
