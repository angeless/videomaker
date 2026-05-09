"""Tests for L4 (error classification) + L7 (llm_status health surface).

Per dev-plan-v0.19.0.md Feature L Tasks L4 + L7:
- L4: replace `except Exception: return {}` with categorized errors
  (auth/rate_limit/network/timeout/parse) + log + UI-visible
- L7: /api/library/llm-status returns last_error so UI can show
  *why* AI tagging failed (not just "missing key")

Design: instance-level error registry on GlobalMediaLibrary recording
the most recent LLM error. _llm_tagging_status() exposes it. M2 banner
extends to show degradation reason; future L4 hooks let _call_*_*
record errors before silent {} return.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from modules.library.global_media_library import GlobalMediaLibrary

_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None
requires_anthropic_sdk = pytest.mark.skipif(
    not _HAS_ANTHROPIC,
    reason="anthropic SDK not installed",
)


@pytest.fixture
def library(tmp_path: Path) -> GlobalMediaLibrary:
    return GlobalMediaLibrary(db_path=tmp_path / "library.db")


# ── L4-T1: classifier maps exception class names to reason ────────────────


@pytest.mark.parametrize("class_name,expected_reason", [
    # Anthropic SDK
    ("AuthenticationError", "auth_failed"),
    ("PermissionDeniedError", "auth_failed"),
    ("RateLimitError", "rate_limited"),
    ("APITimeoutError", "timeout"),
    ("APIConnectionError", "network"),
    # OpenAI SDK
    ("BadRequestError", "bad_request"),
    # Generic
    ("TimeoutError", "timeout"),
    ("ConnectionError", "network"),
    ("JSONDecodeError", "parse"),
    ("ValueError", "unknown"),
])
def test_classify_llm_exception(class_name, expected_reason):
    fake_exc = type(class_name, (Exception,), {})()
    result = GlobalMediaLibrary._classify_llm_exception(fake_exc)
    assert result == expected_reason


# ── L4-T2: error recording stores reason + provider + message ─────────────


def test_record_llm_error_stores_fields(library):
    library._record_llm_error("auth_failed", "401 unauthorized", "anthropic")
    err = library._llm_last_error
    assert err is not None
    assert err["reason"] == "auth_failed"
    assert err["message"] == "401 unauthorized"
    assert err["provider"] == "anthropic"
    assert "timestamp" in err


# ── L4-T3: clearing error resets state ────────────────────────────────────


def test_clear_llm_error_resets(library):
    library._record_llm_error("rate_limited", "429", "openai")
    library._clear_llm_error()
    assert library._llm_last_error is None


# ── L4-T4: _call_anthropic_json records error before returning {} ─────────


@requires_anthropic_sdk
def test_call_anthropic_json_records_auth_error(library, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_client = MagicMock()
    # Simulate auth error (use a class with the right name)
    auth_err = type("AuthenticationError", (Exception,), {})("401 invalid")
    fake_client.messages.create.side_effect = auth_err

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = library._call_anthropic_json([{"role": "user", "content": "x"}])

    assert result == {}  # contract preserved
    assert library._llm_last_error is not None
    assert library._llm_last_error["reason"] == "auth_failed"
    assert library._llm_last_error["provider"] == "anthropic"


# ── L4-T5: _call_openai_json records error too ───────────────────────────


def test_call_openai_json_records_rate_limit(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    fake_client = MagicMock()
    rate_err = type("RateLimitError", (Exception,), {})("429 too many")
    fake_client.chat.completions.create.side_effect = rate_err

    with patch.object(library, "_openai_client", return_value=fake_client):
        result = library._call_openai_json([{"role": "user", "content": "x"}])

    assert result == {}
    assert library._llm_last_error is not None
    assert library._llm_last_error["reason"] == "rate_limited"
    assert library._llm_last_error["provider"] == "openai"


# ── L7-T1: _llm_tagging_status includes last_error key ───────────────────


def test_llm_tagging_status_includes_last_error_field(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    status = library._llm_tagging_status()
    # last_error is a stable field in the contract (None when no error)
    assert "last_error" in status
    assert status["last_error"] is None


# ── L7-T2: _llm_tagging_status surfaces recorded error ────────────────────


def test_llm_tagging_status_surfaces_recent_error(library, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    library._record_llm_error("rate_limited", "429 from anthropic", "anthropic")

    status = library._llm_tagging_status()

    # Even though enabled (key present), the last_error reflects degradation
    assert status["enabled"] is True
    assert status["reason"] == "ready"
    assert status["last_error"]["reason"] == "rate_limited"
    assert status["last_error"]["provider"] == "anthropic"


# ── L7-T3: success clears error state ────────────────────────────────────


def test_successful_call_clears_error(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    library._record_llm_error("network", "timeout earlier", "openai")

    fake_message = MagicMock(content='{"ok": 1}')
    fake_choice = MagicMock(message=fake_message)
    fake_response = MagicMock(choices=[fake_choice])
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with patch.object(library, "_openai_client", return_value=fake_client):
        library._call_openai_json([{"role": "user", "content": "x"}])

    assert library._llm_last_error is None
