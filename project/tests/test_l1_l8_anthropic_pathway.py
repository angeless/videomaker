"""Tests for L1 + L8 — Anthropic key now drives library tagging end-to-end.

Per dev-plan-v0.19.0.md Feature L Tasks L1 + L8:
- L1: `_llm_tagging_enabled` accepts OpenAI **or** Anthropic key
- L8: env var bridge — settings_service writes `ANTHROPIC_API_KEY`, but
  ClaudeVisionAdapter (existing v0.17 code) reads `VIDEOEDITOR_CLAUDE_API_KEY`.
  Per plan-audit C-Critical-2: this bridge MUST be fixed or L1 is moot.

Decision (audit-recommended): keep settings_service writing the
**standard name** `ANTHROPIC_API_KEY`; make adapter read it preferentially,
fall back to `VIDEOEDITOR_CLAUDE_API_KEY` (legacy compat, 6-version retention).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# ── L1-T1: only OpenAI key set → enabled ───────────────────────────────────


def test_llm_tagging_enabled_with_only_openai(monkeypatch):
    from modules.library.global_media_library import GlobalMediaLibrary
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)
    assert GlobalMediaLibrary._llm_tagging_enabled() is True


# ── L1-T2: only Anthropic key set → enabled (NEW behavior) ─────────────────


def test_llm_tagging_enabled_with_only_anthropic(monkeypatch):
    from modules.library.global_media_library import GlobalMediaLibrary
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)
    # BEFORE L1: this would return False (only checked OPENAI_API_KEY).
    # AFTER L1: must return True.
    assert GlobalMediaLibrary._llm_tagging_enabled() is True


# ── L1-T3: neither key → disabled ──────────────────────────────────────────


def test_llm_tagging_enabled_with_no_keys(monkeypatch):
    from modules.library.global_media_library import GlobalMediaLibrary
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)
    assert GlobalMediaLibrary._llm_tagging_enabled() is False


# ── L1-T4: kill switch overrides any key ──────────────────────────────────


def test_llm_tagging_enabled_killswitch_overrides(monkeypatch):
    from modules.library.global_media_library import GlobalMediaLibrary
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", "1")
    assert GlobalMediaLibrary._llm_tagging_enabled() is False


# ── L8-T1: ClaudeVisionAdapter reads ANTHROPIC_API_KEY (standard) ─────────


def test_claude_adapter_available_via_anthropic_api_key(monkeypatch):
    from modules.adapters._vlm_claude import ClaudeVisionAdapter
    monkeypatch.delenv("VIDEOEDITOR_CLAUDE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    adapter = ClaudeVisionAdapter()
    # BEFORE L8: would return False (only read VIDEOEDITOR_CLAUDE_API_KEY).
    # AFTER L8: must return True.
    assert adapter.is_available() is True


# ── L8-T2: legacy env var still honored (backward compat) ──────────────────


def test_claude_adapter_legacy_env_still_works(monkeypatch):
    from modules.adapters._vlm_claude import ClaudeVisionAdapter
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("VIDEOEDITOR_CLAUDE_API_KEY", "sk-ant-legacy")
    adapter = ClaudeVisionAdapter()
    assert adapter.is_available() is True


# ── L8-T3: neither env → not available ────────────────────────────────────


def test_claude_adapter_not_available_without_keys(monkeypatch):
    from modules.adapters._vlm_claude import ClaudeVisionAdapter
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_CLAUDE_API_KEY", raising=False)
    adapter = ClaudeVisionAdapter()
    assert adapter.is_available() is False


# ── L1+L8 integration: Anthropic-only Settings UI flow ────────────────────


# ── H3-T1: OpenAI adapter reads OPENAI_API_KEY (standard, what Settings writes) ─


def test_openai_adapter_available_via_openai_api_key(monkeypatch):
    from modules.adapters._vlm_openai import OpenAIVisionAdapter
    monkeypatch.delenv("VIDEOEDITOR_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-realuser")
    adapter = OpenAIVisionAdapter()
    # BEFORE H3: would return False (only read VIDEOEDITOR_OPENAI_API_KEY).
    # AFTER H3: must return True.
    assert adapter.is_available() is True


# ── H3-T2: legacy env var still honored ────────────────────────────────────


def test_openai_adapter_legacy_env_still_works(monkeypatch):
    from modules.adapters._vlm_openai import OpenAIVisionAdapter
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VIDEOEDITOR_OPENAI_API_KEY", "sk-legacy")
    adapter = OpenAIVisionAdapter()
    assert adapter.is_available() is True


# ── H3-T3: neither env → not available ────────────────────────────────────


def test_openai_adapter_not_available_without_keys(monkeypatch):
    from modules.adapters._vlm_openai import OpenAIVisionAdapter
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_OPENAI_API_KEY", raising=False)
    adapter = OpenAIVisionAdapter()
    assert adapter.is_available() is False


def test_anthropic_only_setup_makes_claude_adapter_available(monkeypatch):
    """Simulates the user-reported scenario: user sets Anthropic key in
    Settings (writes ANTHROPIC_API_KEY) → ClaudeVisionAdapter is available
    + library LLM tagging is enabled.

    Before L1+L8: both fail — _llm_tagging_enabled returned False (L1) AND
    Claude adapter was unavailable (L8). After: both succeed.
    """
    from modules.library.global_media_library import GlobalMediaLibrary
    from modules.adapters._vlm_claude import ClaudeVisionAdapter

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_CLAUDE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-realuser")

    assert GlobalMediaLibrary._llm_tagging_enabled() is True, "L1 broken"
    assert ClaudeVisionAdapter().is_available() is True, "L8 broken"
