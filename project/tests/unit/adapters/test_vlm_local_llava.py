"""Tests for LocalLlavaAdapter — local LLaVA inference (v0.17.0 R2)."""

from unittest.mock import MagicMock, patch

import pytest

from modules.adapters.vlm_adapter import VLMResponse


class TestLocalLlavaAdapter:
    """All tests mock the model to avoid downloading 4GB weights."""

    def test_unavailable_when_no_deps(self):
        """Without transformers/torch, is_available() returns False."""
        from modules.adapters._vlm_local_llava import LocalLlavaAdapter

        with patch("modules.adapters._vlm_local_llava._HAS_LLAVA", False):
            adapter = LocalLlavaAdapter()
            assert adapter.is_available() is False

    def test_available_when_deps_present(self):
        from modules.adapters._vlm_local_llava import LocalLlavaAdapter

        with patch("modules.adapters._vlm_local_llava._HAS_LLAVA", True):
            adapter = LocalLlavaAdapter()
            # Still False until model is loaded, but deps check passes
            assert adapter.is_available() is True

    def test_describe_image_with_mock_model(self):
        """Mock the pipeline to return a fixed answer."""
        from modules.adapters._vlm_local_llava import LocalLlavaAdapter

        with patch("modules.adapters._vlm_local_llava._HAS_LLAVA", True):
            adapter = LocalLlavaAdapter()
            # Mock the _generate method to skip actual model loading
            adapter._generate = MagicMock(
                return_value="A person standing near a coffee shop"
            )
            adapter._loaded = True

            # Create a simple dummy image (1x1 white pixel)
            try:
                from PIL import Image
                img = Image.new("RGB", (100, 100), "white")
            except ImportError:
                pytest.skip("PIL not available")

            resp = adapter.describe_image(image=img, prompt="Describe this image")
            assert isinstance(resp, VLMResponse)
            assert "coffee" in resp.text.lower()
            assert resp.model == "local_llava"
            adapter._generate.assert_called_once()

    def test_describe_image_unavailable_returns_none(self):
        from modules.adapters._vlm_local_llava import LocalLlavaAdapter

        with patch("modules.adapters._vlm_local_llava._HAS_LLAVA", False):
            adapter = LocalLlavaAdapter()
            resp = adapter.describe_image(image=None, prompt="test")
            assert resp is None

    def test_get_model_info(self):
        from modules.adapters._vlm_local_llava import LocalLlavaAdapter

        adapter = LocalLlavaAdapter()
        info = adapter.get_model_info()
        assert info["provider"] == "local_llava"
        assert "model" in info
        assert "available" in info

    def test_lazy_loading(self):
        """Model should not be loaded at __init__ time."""
        from modules.adapters._vlm_local_llava import LocalLlavaAdapter

        adapter = LocalLlavaAdapter()
        assert adapter._loaded is False
