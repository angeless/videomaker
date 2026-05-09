"""Tests for `_llm_tagging_status()` — M2 backend (Wave 1).

Per dev-plan-v0.19.0.md Feature M Task M2:
> Library 顶部"AI 标签未启用"横幅 ... 操作：未设 key 时进 Library 看到横幅；设 key 后横幅消失

Backend contract:
- Method on GlobalMediaLibrary returning {enabled, reason, message, providers}
- States:
    * `missing_api_key` — neither OpenAI nor Anthropic key configured (Issue A scenario)
    * `disabled`       — `VIDEOEDITOR_DISABLE_SEMANTIC_LLM=1`
    * `ready`          — at least one provider available
- Anthropic-only acceptable (decoupled from L1 which lives in Wave 2;
  M2 only needs detection logic, not the actual gate flip).

Note: this is the **failing test first** stage of TDD per dev-governance §13.1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from modules.library.global_media_library import GlobalMediaLibrary


@pytest.fixture
def library(tmp_path: Path) -> GlobalMediaLibrary:
    db = tmp_path / "library.db"
    return GlobalMediaLibrary(db_path=db)


# ── M2-T1: missing_api_key when neither key set ────────────────────────────


def test_llm_tagging_status_missing_when_no_keys(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)

    status = library._llm_tagging_status()

    assert status["enabled"] is False
    assert status["reason"] == "missing_api_key"
    assert "API Key" in status["message"]
    assert status["providers"] == {"openai": False, "anthropic": False}


# ── M2-T2: ready when only Anthropic key set ───────────────────────────────


def test_llm_tagging_status_ready_when_only_anthropic(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)

    status = library._llm_tagging_status()

    assert status["enabled"] is True
    assert status["reason"] == "ready"
    assert status["providers"] == {"openai": False, "anthropic": True}


# ── M2-T3: ready when only OpenAI key set ──────────────────────────────────


def test_llm_tagging_status_ready_when_only_openai(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)

    status = library._llm_tagging_status()

    assert status["enabled"] is True
    assert status["reason"] == "ready"
    assert status["providers"] == {"openai": True, "anthropic": False}


# ── M2-T4: disabled when explicit kill-switch set ──────────────────────────


def test_llm_tagging_status_disabled_via_killswitch(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", "1")

    status = library._llm_tagging_status()

    assert status["enabled"] is False
    assert status["reason"] == "disabled"
    assert "禁用" in status["message"] or "disabled" in status["message"].lower()


# ── M2-T5: providers reflect actual state when both set ────────────────────


def test_llm_tagging_status_providers_both(library, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)

    status = library._llm_tagging_status()

    assert status["enabled"] is True
    assert status["providers"] == {"openai": True, "anthropic": True}


# ── M2-T6: response shape stable (UI contract) ─────────────────────────────


def test_llm_tagging_status_shape(library, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    status = library._llm_tagging_status()

    # Must have these 4 keys at minimum (UI binds to them)
    for key in ("enabled", "reason", "message", "providers"):
        assert key in status, f"missing key: {key}"
    assert isinstance(status["enabled"], bool)
    assert isinstance(status["reason"], str)
    assert isinstance(status["message"], str)
    assert isinstance(status["providers"], dict)
