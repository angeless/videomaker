"""Tests for TTSVoiceover — R15."""

import pytest
from unittest.mock import AsyncMock

from modules.review_engine.tts_voiceover import (
    generate_voiceover,
    VoiceoverSegment,
)
from modules.review_engine.exceptions import RenderError


class MockTTSAdapter:
    """Mock TTS adapter for testing."""

    def __init__(self):
        self.calls = []

    async def synthesize(self, text, voice, output_path):
        self.calls.append({"text": text, "voice": voice, "path": output_path})
        # Create a fake file
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            f.write("fake audio")
        return output_path


class TestTTSVoiceover:

    def test_generates_audio(self, tmp_path):
        adapter = MockTTSAdapter()
        segments = [
            {"text": "Hello world", "start_ms": 0, "end_ms": 2000},
            {"text": "How are you", "start_ms": 2000, "end_ms": 4000},
        ]
        result = generate_voiceover(segments, str(tmp_path), adapter=adapter)
        assert len(result) == 2
        assert result[0].text == "Hello world"
        assert result[0].audio_path is not None
        assert len(adapter.calls) == 2

    def test_alignment_correct(self, tmp_path):
        adapter = MockTTSAdapter()
        segments = [
            {"text": "测试", "start_ms": 5000, "end_ms": 8000},
        ]
        result = generate_voiceover(segments, str(tmp_path), adapter=adapter)
        assert result[0].start_ms == 5000
        assert result[0].end_ms == 8000

    def test_empty_text_skipped(self, tmp_path):
        adapter = MockTTSAdapter()
        segments = [
            {"text": "", "start_ms": 0, "end_ms": 1000},
            {"text": "valid", "start_ms": 1000, "end_ms": 2000},
        ]
        result = generate_voiceover(segments, str(tmp_path), adapter=adapter)
        assert len(result) == 1
