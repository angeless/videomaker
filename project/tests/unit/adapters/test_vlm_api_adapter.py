"""Tests for API Vision adapters — OpenAI/Claude (v0.17.0 R3)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from modules.adapters.vlm_adapter import VLMResponse


class TestOpenAIVisionAdapter:
    def test_unavailable_without_api_key(self):
        from modules.adapters._vlm_openai import OpenAIVisionAdapter

        with patch.dict("os.environ", {}, clear=True):
            adapter = OpenAIVisionAdapter()
            assert adapter.is_available() is False

    def test_available_with_api_key(self):
        from modules.adapters._vlm_openai import OpenAIVisionAdapter

        with patch.dict("os.environ", {"VIDEOEDITOR_OPENAI_API_KEY": "sk-test"}):
            adapter = OpenAIVisionAdapter()
            assert adapter.is_available() is True

    def test_describe_image_success(self):
        from modules.adapters._vlm_openai import OpenAIVisionAdapter

        with patch.dict("os.environ", {"VIDEOEDITOR_OPENAI_API_KEY": "sk-test"}):
            adapter = OpenAIVisionAdapter()
            # Mock the HTTP call
            mock_resp = {
                "choices": [{"message": {"content": "A red car on a highway"}}],
                "usage": {"completion_tokens": 8},
            }
            adapter._call_api = MagicMock(return_value=mock_resp)

            try:
                from PIL import Image
                img = Image.new("RGB", (100, 100), "red")
            except ImportError:
                pytest.skip("PIL not available")

            resp = adapter.describe_image(image=img, prompt="What is this?")
            assert isinstance(resp, VLMResponse)
            assert "red car" in resp.text.lower()
            assert resp.model == "openai"
            adapter._call_api.assert_called_once()

    def test_describe_image_unavailable(self):
        from modules.adapters._vlm_openai import OpenAIVisionAdapter

        with patch.dict("os.environ", {}, clear=True):
            adapter = OpenAIVisionAdapter()
            resp = adapter.describe_image(image=None, prompt="test")
            assert resp is None

    def test_get_model_info(self):
        from modules.adapters._vlm_openai import OpenAIVisionAdapter

        adapter = OpenAIVisionAdapter()
        info = adapter.get_model_info()
        assert info["provider"] == "openai"


class TestClaudeVisionAdapter:
    def test_unavailable_without_api_key(self):
        from modules.adapters._vlm_claude import ClaudeVisionAdapter

        with patch.dict("os.environ", {}, clear=True):
            adapter = ClaudeVisionAdapter()
            assert adapter.is_available() is False

    def test_available_with_api_key(self):
        from modules.adapters._vlm_claude import ClaudeVisionAdapter

        with patch.dict("os.environ", {"VIDEOEDITOR_CLAUDE_API_KEY": "sk-ant-test"}):
            adapter = ClaudeVisionAdapter()
            assert adapter.is_available() is True

    def test_describe_image_success(self):
        from modules.adapters._vlm_claude import ClaudeVisionAdapter

        with patch.dict("os.environ", {"VIDEOEDITOR_CLAUDE_API_KEY": "sk-ant-test"}):
            adapter = ClaudeVisionAdapter()
            mock_resp = {
                "content": [{"type": "text", "text": "A blue sky with clouds"}],
                "usage": {"output_tokens": 7},
            }
            adapter._call_api = MagicMock(return_value=mock_resp)

            try:
                from PIL import Image
                img = Image.new("RGB", (100, 100), "blue")
            except ImportError:
                pytest.skip("PIL not available")

            resp = adapter.describe_image(image=img, prompt="Describe")
            assert isinstance(resp, VLMResponse)
            assert "sky" in resp.text.lower() or "cloud" in resp.text.lower()
            assert resp.model == "claude"

    def test_get_model_info(self):
        from modules.adapters._vlm_claude import ClaudeVisionAdapter

        adapter = ClaudeVisionAdapter()
        info = adapter.get_model_info()
        assert info["provider"] == "claude"
