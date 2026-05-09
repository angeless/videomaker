"""Tests for `/api/library/llm-status` endpoint — M2 backend (Wave 1).

Per dev-plan-v0.19.0.md Feature M Task M2.

Endpoint contract:
- GET /api/library/llm-status
- Returns 200 with JSON: {enabled, reason, message, providers}
- Always returns 200 even when degraded — frontend banner uses fields, not status code.
"""

from __future__ import annotations

import json

import pytest


# ── M2-E1: endpoint exists and returns 200 ─────────────────────────────────


def test_llm_status_endpoint_exists(e2e_client):
    rsp = e2e_client.get("/api/library/llm-status")
    assert rsp.status_code == 200


# ── M2-E2: missing keys → enabled false + missing_api_key reason ───────────


def test_llm_status_endpoint_missing_keys(e2e_client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)

    rsp = e2e_client.get("/api/library/llm-status")
    payload = rsp.get_json()

    assert payload["enabled"] is False
    assert payload["reason"] == "missing_api_key"
    assert payload["providers"] == {"openai": False, "anthropic": False}


# ── M2-E3: anthropic-only → ready ──────────────────────────────────────────


def test_llm_status_endpoint_anthropic_only(e2e_client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", raising=False)

    rsp = e2e_client.get("/api/library/llm-status")
    payload = rsp.get_json()

    assert payload["enabled"] is True
    assert payload["reason"] == "ready"


# ── M2-E4: kill-switch → disabled ──────────────────────────────────────────


def test_llm_status_endpoint_killswitch(e2e_client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", "1")

    rsp = e2e_client.get("/api/library/llm-status")
    payload = rsp.get_json()

    assert payload["enabled"] is False
    assert payload["reason"] == "disabled"


# ── M2-E5: response shape stable (UI contract) ─────────────────────────────


def test_llm_status_endpoint_shape(e2e_client):
    rsp = e2e_client.get("/api/library/llm-status")
    payload = rsp.get_json()

    for key in ("enabled", "reason", "message", "providers"):
        assert key in payload
    assert "openai" in payload["providers"]
    assert "anthropic" in payload["providers"]


# ── M2-E6: cache headers — banner should re-poll, not cache ───────────────


def test_llm_status_endpoint_no_cache(e2e_client):
    rsp = e2e_client.get("/api/library/llm-status")
    cache_control = rsp.headers.get("Cache-Control", "")
    assert "no-store" in cache_control or "no-cache" in cache_control
