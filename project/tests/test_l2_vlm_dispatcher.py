"""Tests for L2 — _call_vlm_json dispatcher + _call_anthropic_json.

Per dev-plan-v0.19.0.md Feature L Task L2:
> 抽象 `_call_openai_json` → `_call_vlm_json`（路由 `vlm_adapter.get_vlm_adapter(provider)`）
> 单测：mock OpenAI/Claude/Llava adapter 各跑一次，返回 schema 一致

Implementation note: `vlm_adapter` is image-specific; library tagging needs
chat-completion-style call (text-only refine + vision tagging). L2 implements
provider-routing via `_call_vlm_json` dispatcher which delegates to
`_call_openai_json` (existing) or new `_call_anthropic_json` (parallel impl
using Anthropic SDK directly). Result schema unified: dict with `_model` key
populated by the call, never overwritten by upstream.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from modules.library.global_media_library import GlobalMediaLibrary

# Mark tests that require `patch("anthropic.Anthropic", ...)` — the SDK
# must be importable for unittest.mock to find the target. In production,
# missing SDK → silent {} return (tested separately via dispatcher mocks).
_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None
requires_anthropic_sdk = pytest.mark.skipif(
    not _HAS_ANTHROPIC,
    reason="anthropic SDK not installed in this Python env",
)


@pytest.fixture
def library(tmp_path: Path) -> GlobalMediaLibrary:
    return GlobalMediaLibrary(db_path=tmp_path / "library.db")


# ── L2-T1: dispatcher returns {} when neither key set ──────────────────────


def test_call_vlm_json_no_keys(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = library._call_vlm_json([{"role": "user", "content": "test"}])
    assert result == {}


# ── L2-T2: dispatcher prefers OpenAI when both set ─────────────────────────


def test_call_vlm_json_prefers_openai(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    with patch.object(library, "_call_openai_json", return_value={"x": 1, "_model": "gpt-4o"}) as mock_oai, \
         patch.object(library, "_call_anthropic_json", return_value={"_model": "claude"}) as mock_ant:
        result = library._call_vlm_json([{"role": "user", "content": "x"}])

    mock_oai.assert_called_once()
    mock_ant.assert_not_called()
    assert result == {"x": 1, "_model": "gpt-4o"}


# ── L2-T3: dispatcher falls back to Anthropic when only Anthropic set ─────


def test_call_vlm_json_falls_back_to_anthropic(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    with patch.object(library, "_call_openai_json", return_value={}) as mock_oai, \
         patch.object(library, "_call_anthropic_json", return_value={"y": 2, "_model": "claude-sonnet"}) as mock_ant:
        result = library._call_vlm_json([{"role": "user", "content": "x"}])

    mock_oai.assert_not_called()
    mock_ant.assert_called_once()
    assert result == {"y": 2, "_model": "claude-sonnet"}


# ── L2-T4: _call_anthropic_json returns {} without key ─────────────────────


def test_call_anthropic_json_no_key(library, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = library._call_anthropic_json([{"role": "user", "content": "x"}])
    assert result == {}


# ── L2-T5: _call_anthropic_json injects _model from response ──────────────


@requires_anthropic_sdk
def test_call_anthropic_json_injects_model(library, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text='{"answer": "yes"}', type="text")]
    fake_response.model = "claude-sonnet-4-20250514"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = library._call_anthropic_json([
            {"role": "user", "content": "Are you Claude?"}
        ])

    assert result.get("answer") == "yes"
    assert result.get("_model") == "claude-sonnet-4-20250514"


# ── L2-T6: _call_anthropic_json converts OpenAI image_url to Anthropic format ─


@requires_anthropic_sdk
def test_call_anthropic_json_converts_image_url(library, monkeypatch):
    """OpenAI format: {type: image_url, image_url: {url: data:image/jpeg;base64,XXX}}
    Anthropic format: {type: image, source: {type: base64, media_type: image/jpeg, data: XXX}}
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text='{"ok": true}')]
    fake_response.model = "claude-sonnet-4-20250514"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    messages = [
        {"role": "system", "content": "You are a tagger."},
        {"role": "user", "content": [
            {"type": "text", "text": "Tag this:"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,FAKEB64"}},
        ]},
    ]

    with patch("anthropic.Anthropic", return_value=fake_client):
        library._call_anthropic_json(messages)

    call_kwargs = fake_client.messages.create.call_args.kwargs
    # System message becomes top-level kwarg
    assert call_kwargs.get("system") == "You are a tagger."
    # User message images converted
    user_msg = call_kwargs["messages"][0]
    user_content = user_msg["content"]
    image_parts = [c for c in user_content if c.get("type") == "image"]
    assert len(image_parts) == 1
    assert image_parts[0]["source"]["type"] == "base64"
    assert image_parts[0]["source"]["media_type"] == "image/jpeg"
    assert image_parts[0]["source"]["data"] == "FAKEB64"


# ── L2-T7: _call_anthropic_json swallows exceptions to {} ─────────────────


@requires_anthropic_sdk
def test_call_anthropic_json_handles_exception(library, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("API down")

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = library._call_anthropic_json([{"role": "user", "content": "x"}])

    assert result == {}


# ── L2-T8: _call_openai_json now also injects _model (regression) ─────────


def test_call_openai_json_injects_model(library, monkeypatch):
    """L2 unified contract: both _call_*_json populate _model; upstream
    no longer overwrites."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    fake_message = MagicMock()
    fake_message.content = '{"foo": "bar"}'
    fake_choice = MagicMock(message=fake_message)
    fake_response = MagicMock(choices=[fake_choice])

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with patch.object(library, "_openai_client", return_value=fake_client):
        result = library._call_openai_json([{"role": "user", "content": "x"}])

    assert result.get("foo") == "bar"
    assert result.get("_model") == "gpt-4o-mini"
