"""Tests for VLM adapter — provider abstraction layer (v0.17.0 R1)."""

import time
from unittest.mock import patch

import pytest

from modules.adapters.vlm_adapter import (
    StubVLMAdapter,
    VLMResponse,
    get_vlm_adapter,
)


# ---------------------------------------------------------------------------
# VLMResponse dataclass
# ---------------------------------------------------------------------------

class TestVLMResponse:
    def test_response_fields(self):
        resp = VLMResponse(
            text="A coffee cup on a table",
            model="stub",
            latency_ms=42,
            tokens_used=15,
        )
        assert resp.text == "A coffee cup on a table"
        assert resp.model == "stub"
        assert resp.latency_ms == 42
        assert resp.tokens_used == 15

    def test_response_defaults(self):
        resp = VLMResponse(text="hello")
        assert resp.model == ""
        assert resp.latency_ms == 0
        assert resp.tokens_used == 0


# ---------------------------------------------------------------------------
# StubVLMAdapter
# ---------------------------------------------------------------------------

class TestStubVLMAdapter:
    def test_stub_is_available(self):
        adapter = StubVLMAdapter()
        assert adapter.is_available() is True

    def test_stub_describe_image(self):
        adapter = StubVLMAdapter()
        # Pass None as image — stub doesn't use it
        resp = adapter.describe_image(image=None, prompt="Describe this")
        assert isinstance(resp, VLMResponse)
        assert len(resp.text) > 0
        assert resp.model == "stub"

    def test_stub_custom_response(self):
        adapter = StubVLMAdapter(fixed_response="custom output")
        resp = adapter.describe_image(image=None, prompt="anything")
        assert resp.text == "custom output"

    def test_stub_get_model_info(self):
        adapter = StubVLMAdapter()
        info = adapter.get_model_info()
        assert info["provider"] == "stub"
        assert "model" in info
        assert info["available"] is True


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

class TestGetVlmAdapter:
    def test_factory_returns_stub(self):
        adapter = get_vlm_adapter("stub")
        assert isinstance(adapter, StubVLMAdapter)
        assert adapter.is_available() is True

    def test_factory_unknown_provider_returns_none(self):
        adapter = get_vlm_adapter("nonexistent_provider_xyz")
        assert adapter is None

    def test_factory_default_provider(self):
        """Default provider without env should return something or None gracefully."""
        # Without any env/settings, get_vlm_adapter("local_llava") should
        # return None if LLaVA is not installed
        adapter = get_vlm_adapter("local_llava")
        # Should not raise, just return None or adapter
        assert adapter is None or hasattr(adapter, "describe_image")

    def test_factory_none_provider_returns_none(self):
        adapter = get_vlm_adapter(None)
        assert adapter is None
