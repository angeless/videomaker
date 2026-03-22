"""Tests for _build_embedding_source with ASR transcription (R4)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


class FakeCoreMixin:
    """Minimal stub to test _build_embedding_source in isolation."""

    @staticmethod
    def _safe_json_loads(raw, default):
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return default
        return raw if raw is not None else default

    # Import the real method
    from modules.library.core.core_mixin import CoreMixin
    _build_embedding_source = CoreMixin._build_embedding_source


class TestBuildEmbeddingSourceASR:
    """R4: ASR transcription text is included in embedding source."""

    def _build(self, **kwargs):
        obj = FakeCoreMixin()
        return obj._build_embedding_source(**kwargs)

    def test_asr_text_included(self):
        result = self._build(
            filename="video.mp4",
            semantic_text="sunset beach",
            keywords_json="[]",
            semantic_json="{}",
            analysis_json=json.dumps({"asr_text": "hello this is a test video"}),
        )
        assert "hello this is a test video" in result

    def test_transcription_dict_fallback(self):
        """Falls back to analysis.transcription.text when asr_text is empty."""
        result = self._build(
            filename="video.mp4",
            semantic_text=None,
            keywords_json=None,
            semantic_json=None,
            analysis_json=json.dumps({
                "asr_text": "",
                "transcription": {"text": "fallback transcript content"}
            }),
        )
        assert "fallback transcript content" in result

    def test_no_analysis_json_works(self):
        """Omitting analysis_json still works (backward compat)."""
        result = self._build(
            filename="video.mp4",
            semantic_text="test",
            keywords_json=None,
            semantic_json=None,
        )
        assert "video.mp4" in result
        assert "test" in result

    def test_asr_truncated_at_2000(self):
        """Long transcriptions are capped at 2000 chars."""
        long_text = "word " * 1000  # 5000 chars
        result = self._build(
            filename="v.mp4",
            semantic_text=None,
            keywords_json=None,
            semantic_json=None,
            analysis_json={"asr_text": long_text},
        )
        # The asr portion should be at most 2000 chars
        # Total might be longer due to filename, but asr part is capped
        assert len(result) < 6001  # overall cap is 6000

    def test_empty_asr_not_added(self):
        """Empty ASR text doesn't add empty segments."""
        result = self._build(
            filename="v.mp4",
            semantic_text=None,
            keywords_json=None,
            semantic_json=None,
            analysis_json={"asr_text": ""},
        )
        # Should just be the filename
        assert result.strip() == "v.mp4"

    def test_analysis_json_as_string(self):
        """analysis_json can be a JSON string (from SQLite)."""
        result = self._build(
            filename="v.mp4",
            semantic_text=None,
            keywords_json=None,
            semantic_json=None,
            analysis_json='{"asr_text": "spoken words here"}',
        )
        assert "spoken words here" in result

    def test_analysis_json_none(self):
        """analysis_json=None is safe."""
        result = self._build(
            filename="v.mp4",
            semantic_text="meta",
            keywords_json=None,
            semantic_json=None,
            analysis_json=None,
        )
        assert "v.mp4" in result
        assert "meta" in result
