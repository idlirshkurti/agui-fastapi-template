"""Tests for OutputFilterGuardrail — covers all acceptance criteria from issue #12."""
from __future__ import annotations

import pytest

from app.guardrails.base import FilterResult
from app.guardrails.output_filter import OutputFilterGuardrail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pii_filter() -> OutputFilterGuardrail:
    return OutputFilterGuardrail(enable_pii=True, enable_toxicity=False)


def _toxicity_filter() -> OutputFilterGuardrail:
    return OutputFilterGuardrail(enable_pii=False, enable_toxicity=True)


def _both_filters() -> OutputFilterGuardrail:
    return OutputFilterGuardrail(enable_pii=True, enable_toxicity=True)


def _no_filters() -> OutputFilterGuardrail:
    return OutputFilterGuardrail(enable_pii=False, enable_toxicity=False)


# ---------------------------------------------------------------------------
# FilterResult dataclass
# ---------------------------------------------------------------------------

def test_filter_result_defaults() -> None:
    r = FilterResult(text="hello")
    assert r.text == "hello"
    assert r.redacted is False
    assert r.reasons == []


# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_email_is_redacted() -> None:
    f = _pii_filter()
    result = await f.apply("Contact us at support@example.com for help.")
    assert "support@example.com" not in result.text
    assert "[REDACTED_EMAIL]" in result.text
    assert result.redacted is True
    assert "pii:email" in result.reasons


@pytest.mark.asyncio
async def test_phone_is_redacted() -> None:
    f = _pii_filter()
    result = await f.apply("Call me at +1 (555) 123-4567 anytime.")
    assert result.redacted is True
    assert "pii:phone" in result.reasons


@pytest.mark.asyncio
async def test_credit_card_is_redacted() -> None:
    f = _pii_filter()
    result = await f.apply("Card number: 4111 1111 1111 1111")
    assert "4111" not in result.text
    assert "[REDACTED_CARD]" in result.text
    assert result.redacted is True
    assert "pii:credit_card" in result.reasons


@pytest.mark.asyncio
async def test_multiple_pii_types_in_one_string() -> None:
    f = _pii_filter()
    text = "Email: alice@corp.io, phone: 555-867-5309, card: 5500 0000 0000 0004"
    result = await f.apply(text)
    assert result.redacted is True
    assert "pii:email" in result.reasons
    assert "pii:phone" in result.reasons
    assert "pii:credit_card" in result.reasons


@pytest.mark.asyncio
async def test_clean_text_passes_pii_filter_unchanged() -> None:
    f = _pii_filter()
    clean = "The Eiffel Tower is 330 metres tall."
    result = await f.apply(clean)
    assert result.text == clean
    assert result.redacted is False
    assert result.reasons == []


# ---------------------------------------------------------------------------
# Toxicity filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toxic_content_is_blocked() -> None:
    f = _toxicity_filter()
    result = await f.apply("You should kill yourself immediately.")
    assert result.redacted is True
    assert "toxicity" in result.reasons
    assert "BLOCKED" in result.text


@pytest.mark.asyncio
async def test_clean_text_passes_toxicity_filter_unchanged() -> None:
    f = _toxicity_filter()
    clean = "Paris is the capital of France."
    result = await f.apply(clean)
    assert result.text == clean
    assert result.redacted is False


# ---------------------------------------------------------------------------
# Both filters disabled — transparent pass-through
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_filters_is_transparent() -> None:
    f = _no_filters()
    text = "Email: ceo@example.com — kill yourself"
    result = await f.apply(text)
    assert result.text == text
    assert result.redacted is False
    assert result.reasons == []


# ---------------------------------------------------------------------------
# Env-var configuration
# ---------------------------------------------------------------------------

def test_env_var_pii_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_PII_FILTER", raising=False)
    monkeypatch.delenv("ENABLE_TOXICITY_FILTER", raising=False)
    f = OutputFilterGuardrail()
    assert f._pii is False
    assert f._toxicity is False


def test_env_var_enables_pii(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_PII_FILTER", "true")
    monkeypatch.delenv("ENABLE_TOXICITY_FILTER", raising=False)
    f = OutputFilterGuardrail()
    assert f._pii is True
    assert f._toxicity is False


def test_env_var_enables_toxicity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_PII_FILTER", raising=False)
    monkeypatch.setenv("ENABLE_TOXICITY_FILTER", "1")
    f = OutputFilterGuardrail()
    assert f._pii is False
    assert f._toxicity is True


# ---------------------------------------------------------------------------
# Integration: redacted content does not re-enter history
# (tested via the FilterResult text being the sanitised version)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redacted_text_is_what_goes_to_history() -> None:
    """The caller must use result.text (not the raw input) for history.add()."""
    f = _pii_filter()
    raw = "Reach the team at ops@company.com"
    result = await f.apply(raw)
    # Simulate what ResearchAgent does: only store result.text
    stored_in_history = result.text
    assert "ops@company.com" not in stored_in_history
