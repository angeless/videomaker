"""Tests for image_semantic check_ai_status and degradation signalling."""

import pytest

from modules.capabilities.image_semantic import check_ai_status


class _FakeLibraryNoKey:
    @staticmethod
    def _vision_enrich_enabled():
        return False

    @staticmethod
    def _embedding_runtime_status():
        return {"enabled": False, "reason": "missing_api_key", "message": "未配置 OpenAI API Key"}


class _FakeLibraryReady:
    _clip_encoder = True  # R6: simulate CLIP available

    @staticmethod
    def _vision_enrich_enabled():
        return True

    @staticmethod
    def _embedding_runtime_status():
        return {"enabled": True, "reason": "ready", "message": "向量能力已启用"}


class _FakeLibraryVisionOnlyNoVector:
    @staticmethod
    def _vision_enrich_enabled():
        return True

    @staticmethod
    def _embedding_runtime_status():
        return {"enabled": False, "reason": "missing_numpy", "message": "未安装 numpy"}


# --- Tests ---


def test_no_library():
    result = check_ai_status(None)
    assert result["degraded"] is True
    assert result["vision_available"] is False
    assert result["vector_available"] is False
    assert result["keyword_available"] is True
    assert len(result["reasons"]) > 0


def test_library_no_key():
    result = check_ai_status(_FakeLibraryNoKey())
    assert result["degraded"] is True
    assert result["vision_available"] is False
    assert result["vector_available"] is False
    assert "API Key" in result["message"]


def test_library_ready():
    result = check_ai_status(_FakeLibraryReady())
    assert result["degraded"] is False
    assert result["vision_available"] is True
    assert result["vector_available"] is True
    assert result["message"] == ""


def test_library_vision_ok_vector_missing():
    result = check_ai_status(_FakeLibraryVisionOnlyNoVector())
    assert result["degraded"] is True
    assert result["vision_available"] is True
    assert result["vector_available"] is False
    assert "numpy" in result["message"]


def test_keyword_always_available():
    for lib in [None, _FakeLibraryNoKey(), _FakeLibraryReady()]:
        result = check_ai_status(lib)
        assert result["keyword_available"] is True
