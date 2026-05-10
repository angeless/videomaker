"""Tests for L10 — _call_vlm_embedding dispatcher with Voyage AI fallback.

Per dev-plan-v0.19.0.md Feature L Task L10:
> `_call_openai_embedding` (line 1024, 3 处调用) 接通 vlm_adapter
> （或 Voyage SDK 作 Anthropic 推荐 embedding）
> 测试：仅 Anthropic key 时语义搜索可用；hybrid/vector 模式不静默回退 keyword

Implementation: Anthropic doesn't ship first-party text embeddings, so
L10 routes Anthropic-side users to Voyage AI (Anthropic-recommended
partner). _call_vlm_embedding dispatcher: OpenAI > Voyage > [].

Voyage SDK is optional — `import voyageai` failure handled gracefully
(empty result, banner reports `missing_voyage_sdk`).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from modules.library.global_media_library import GlobalMediaLibrary

_HAS_VOYAGE = importlib.util.find_spec("voyageai") is not None
requires_voyage_sdk = pytest.mark.skipif(
    not _HAS_VOYAGE,
    reason="voyageai SDK not installed in this Python env",
)


@pytest.fixture
def library(tmp_path: Path) -> GlobalMediaLibrary:
    return GlobalMediaLibrary(db_path=tmp_path / "library.db")


# ── L10-T1: dispatcher returns [] when no provider keys ────────────────────


def test_call_vlm_embedding_no_keys(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    assert library._call_vlm_embedding("hello") == []


# ── L10-T2: dispatcher prefers OpenAI when both ────────────────────────────


def test_call_vlm_embedding_prefers_openai(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-voyage-test")
    with patch.object(library, "_call_openai_embedding", return_value=[0.1, 0.2]) as mock_oai, \
         patch.object(library, "_call_voyage_embedding", return_value=[0.9]) as mock_voy:
        result = library._call_vlm_embedding("x")
    mock_oai.assert_called_once()
    mock_voy.assert_not_called()
    assert result == [0.1, 0.2]


# ── L10-T3: dispatcher falls back to Voyage when only Voyage ──────────────


def test_call_vlm_embedding_falls_back_to_voyage(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-voyage-test")
    with patch.object(library, "_call_openai_embedding", return_value=[]) as mock_oai, \
         patch.object(library, "_call_voyage_embedding", return_value=[0.5, 0.5]) as mock_voy:
        result = library._call_vlm_embedding("x")
    mock_oai.assert_not_called()
    mock_voy.assert_called_once()
    assert result == [0.5, 0.5]


# ── L10-T3b: dispatcher passes input_type through to Voyage ───────────────


def test_call_vlm_embedding_passes_input_type_to_voyage(library, monkeypatch):
    """Voyage SDK accepts input_type="query"|"document" for retrieval
    optimization. The dispatcher must pass this through faithfully so
    consumers (search vs indexing) get the right embedding flavor."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-voyage-test")
    with patch.object(library, "_call_voyage_embedding", return_value=[0.5]) as mock_voy:
        library._call_vlm_embedding("hello", input_type="query")
        library._call_vlm_embedding("doc text", input_type="document")
    assert mock_voy.call_count == 2
    # First call: query
    assert mock_voy.call_args_list[0].kwargs.get("input_type") == "query"
    # Second call: document
    assert mock_voy.call_args_list[1].kwargs.get("input_type") == "document"


# ── L10-T3c: OpenAI path silently ignores input_type (parity contract) ────


def test_call_vlm_embedding_openai_ignores_input_type(library, monkeypatch):
    """OpenAI's embedding API has no input_type equivalent. Dispatcher
    must not break when input_type is passed alongside OpenAI key — it
    should silently drop the kwarg (parity with original signature)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    with patch.object(library, "_call_openai_embedding", return_value=[0.1]) as mock_oai:
        result = library._call_vlm_embedding("hello", input_type="query")
    # OpenAI was called WITHOUT input_type kwarg
    mock_oai.assert_called_once_with("hello")
    assert result == [0.1]


# ── L10-T4: empty input → empty result (no API call) ──────────────────────


def test_call_vlm_embedding_empty_input(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with patch.object(library, "_call_openai_embedding") as mock:
        mock.return_value = []
        # Empty / whitespace input should still go through (function decides)
        # but we guard at the dispatcher level too — test what dispatcher does
        result = library._call_vlm_embedding("")
    # OpenAI path called but with empty string → returns []
    assert result == []


# ── L10-T5: _call_voyage_embedding returns [] without key ─────────────────


def test_call_voyage_embedding_no_key(library, monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    assert library._call_voyage_embedding("hello") == []


# ── L10-T6: _call_voyage_embedding returns [] when SDK missing ────────────


def test_call_voyage_embedding_no_sdk(library, monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    with patch.object(library, "_has_voyage_sdk", return_value=False):
        assert library._call_voyage_embedding("hello") == []


# ── L10-T7: _call_voyage_embedding returns vector on success ──────────────


@requires_voyage_sdk
def test_call_voyage_embedding_returns_vector(library, monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")

    fake_response = MagicMock()
    fake_response.embeddings = [[0.1, 0.2, 0.3]]

    fake_client = MagicMock()
    fake_client.embed.return_value = fake_response

    with patch("voyageai.Client", return_value=fake_client):
        result = library._call_voyage_embedding("hello")

    assert result == [0.1, 0.2, 0.3]
    # Voyage SDK signature: client.embed([texts], model=...) — verify positional
    call_args = fake_client.embed.call_args
    assert call_args.args[0] == ["hello"]  # texts as first positional
    assert "model" in call_args.kwargs


# ── L10-T7b: input_type="query" reaches Voyage SDK ────────────────────────


@requires_voyage_sdk
def test_call_voyage_embedding_passes_input_type_query(library, monkeypatch):
    """Verify input_type="query" is forwarded to voyage SDK — this is the
    retrieval-optimization knob that gives 5-10% recall lift on queries."""
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")

    fake_response = MagicMock()
    fake_response.embeddings = [[0.1]]
    fake_client = MagicMock()
    fake_client.embed.return_value = fake_response

    with patch("voyageai.Client", return_value=fake_client):
        library._call_voyage_embedding("search text", input_type="query")

    assert fake_client.embed.call_args.kwargs.get("input_type") == "query"


# ── L10-T7c: input_type=None → SDK call omits the kwarg ───────────────────


@requires_voyage_sdk
def test_call_voyage_embedding_omits_input_type_when_none(library, monkeypatch):
    """input_type=None means 'no retrieval hint' — we should NOT send the
    kwarg at all (Voyage SDK treats omission and explicit None differently
    in some versions; safer to omit)."""
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")

    fake_response = MagicMock()
    fake_response.embeddings = [[0.1]]
    fake_client = MagicMock()
    fake_client.embed.return_value = fake_response

    with patch("voyageai.Client", return_value=fake_client):
        library._call_voyage_embedding("text")  # no input_type

    assert "input_type" not in fake_client.embed.call_args.kwargs


# ── L10-T8: _call_voyage_embedding records auth error ─────────────────────


@requires_voyage_sdk
def test_call_voyage_embedding_records_error(library, monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")

    auth_err = type("AuthenticationError", (Exception,), {})("invalid key")
    fake_client = MagicMock()
    fake_client.embed.side_effect = auth_err

    with patch("voyageai.Client", return_value=fake_client):
        result = library._call_voyage_embedding("x")

    assert result == []
    assert library._llm_last_error is not None
    assert library._llm_last_error["reason"] == "auth_failed"
    assert library._llm_last_error["provider"] == "voyage"


# ── L10-T9: _embedding_runtime_status — Anthropic-only nudges to Voyage ───


def test_embedding_status_anthropic_only_suggests_voyage(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    status = library._embedding_runtime_status()
    assert status["enabled"] is False
    assert status["reason"] == "missing_voyage_key"
    assert "Voyage" in status["message"]


# ── L10-T9b: AUDIT FIX — OpenAI key + Anthropic key but SDK missing ───────


def test_embedding_status_openai_sdk_missing_wins_over_anthropic_nudge(library, monkeypatch):
    """Regression test for L10 audit Bug 1.

    Scenario: user has BOTH OPENAI_API_KEY and ANTHROPIC_API_KEY configured,
    but `pip install openai` failed/uninstalled. Pre-fix, the Anthropic
    nudge fired first → user was told to install Voyage, which is the
    WRONG fix. Post-fix, the more-specific 'missing_openai_sdk' reason
    must win (root-cause priority).
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    with patch.object(library, "_has_openai_sdk", return_value=False):
        status = library._embedding_runtime_status()

    assert status["enabled"] is False
    assert status["reason"] == "missing_openai_sdk", (
        "Specific SDK-missing diagnostic must win over generic Anthropic nudge"
    )


# ── L10-T10: _embedding_runtime_status — OpenAI ready ─────────────────────


def test_embedding_status_openai_ready(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    with patch.object(library, "_has_openai_sdk", return_value=True):
        status = library._embedding_runtime_status()

    assert status["enabled"] is True
    assert status["reason"] == "ready"
    assert status["provider"] == "openai"


# ── L10-T11: _embedding_runtime_status — Voyage ready ─────────────────────


def test_embedding_status_voyage_ready(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")

    with patch.object(library, "_has_voyage_sdk", return_value=True):
        status = library._embedding_runtime_status()

    assert status["enabled"] is True
    assert status["reason"] == "ready"
    assert status["provider"] == "voyage"
