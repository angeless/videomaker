"""Tests for L3 — _call_vlm_text + _call_anthropic_text.

Per dev-plan-v0.19.0.md Feature L Task L3 (text-only sibling of L2):
> `_call_openai_text` 同上抽象为 `_call_vlm_text`
> 调用点全部切换；grep `_call_openai_` 在 library/ 下 = 0

Single existing consumer: _llm_refine_index_layers (core_mixin.py:2321).
Returns plain string, "" on failure (vs L2's dict, {} on failure).
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
    reason="anthropic SDK not installed in this Python env",
)


@pytest.fixture
def library(tmp_path: Path) -> GlobalMediaLibrary:
    return GlobalMediaLibrary(db_path=tmp_path / "library.db")


# ── L3-T1: dispatcher returns "" when no keys ──────────────────────────────


def test_call_vlm_text_no_keys(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert library._call_vlm_text([{"role": "user", "content": "x"}]) == ""


# ── L3-T2: dispatcher prefers OpenAI ───────────────────────────────────────


def test_call_vlm_text_prefers_openai(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with patch.object(library, "_call_openai_text", return_value="from_openai") as mock_oai, \
         patch.object(library, "_call_anthropic_text", return_value="from_anthropic") as mock_ant:
        result = library._call_vlm_text([{"role": "user", "content": "x"}])
    mock_oai.assert_called_once()
    mock_ant.assert_not_called()
    assert result == "from_openai"


# ── L3-T3: dispatcher falls back to Anthropic ──────────────────────────────


def test_call_vlm_text_falls_back_to_anthropic(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with patch.object(library, "_call_openai_text", return_value="should-not-be-used") as mock_oai, \
         patch.object(library, "_call_anthropic_text", return_value="from_anthropic") as mock_ant:
        result = library._call_vlm_text([{"role": "user", "content": "x"}])
    mock_oai.assert_not_called()
    mock_ant.assert_called_once()
    assert result == "from_anthropic"


# ── L3-T4: _call_anthropic_text returns "" without key ────────────────────


def test_call_anthropic_text_no_key(library, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert library._call_anthropic_text([{"role": "user", "content": "x"}]) == ""


# ── L3-T5: _call_anthropic_text returns aggregated text ───────────────────


@requires_anthropic_sdk
def test_call_anthropic_text_returns_text(library, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="Hello from Claude")]
    fake_response.model = "claude-sonnet-4-20250514"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = library._call_anthropic_text([
            {"role": "user", "content": "Hi"}
        ])

    assert result == "Hello from Claude"


# ── L3-T6: _call_anthropic_text handles system message ────────────────────


@requires_anthropic_sdk
def test_call_anthropic_text_extracts_system_role(library, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.model = "claude-sonnet-4-20250514"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("anthropic.Anthropic", return_value=fake_client):
        library._call_anthropic_text([
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Reply."},
        ])

    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs.get("system") == "You are concise."
    # Only user message in messages[]
    assert len(kwargs["messages"]) == 1
    assert kwargs["messages"][0]["role"] == "user"


# ── L3-T7: _call_anthropic_text returns "" on exception ───────────────────


@requires_anthropic_sdk
def test_call_anthropic_text_handles_exception(library, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = ConnectionError("net down")

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = library._call_anthropic_text([{"role": "user", "content": "x"}])

    assert result == ""


# ── L3-T8: aggregates multiple text content blocks ────────────────────────


@requires_anthropic_sdk
def test_call_anthropic_text_aggregates_blocks(library, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_response = MagicMock()
    fake_response.content = [
        MagicMock(text="Hello "),
        MagicMock(text="World"),
    ]
    fake_response.model = "claude-sonnet-4-20250514"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = library._call_anthropic_text([{"role": "user", "content": "x"}])

    assert result == "Hello World"
