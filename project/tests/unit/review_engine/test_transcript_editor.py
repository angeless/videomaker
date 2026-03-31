"""Unit tests for transcript_editor module."""

import pytest
from unittest.mock import patch, MagicMock

from modules.review_engine.transcript_editor import (
    _group_words_into_paragraphs,
    transcribe_to_doc,
)
from modules.review_engine.contracts import Paragraph, Word, TranscriptDoc
from modules.review_engine.exceptions import TranscriptError


class TestGroupWordsIntoParagraphs:
    """Test word-to-paragraph grouping logic."""

    def test_transcript_editor_groups_words_into_single_paragraph(self):
        """Continuous speech → single paragraph."""
        words = [
            {"text": "你好", "start": 0.0, "end": 0.5, "confidence": 0.9},
            {"text": "世界", "start": 0.6, "end": 1.0, "confidence": 0.9},
            {"text": "今天", "start": 1.1, "end": 1.5, "confidence": 0.8},
        ]
        paragraphs = _group_words_into_paragraphs(words, gap_threshold_ms=1500)

        assert len(paragraphs) == 1
        assert len(paragraphs[0].words) == 3
        assert paragraphs[0].start_ms == 0
        assert paragraphs[0].end_ms == 1500

    def test_transcript_editor_splits_on_gap(self):
        """Gap > threshold → new paragraph."""
        words = [
            {"text": "第一段", "start": 0.0, "end": 1.0, "confidence": 0.9},
            {"text": "还是", "start": 1.1, "end": 1.5, "confidence": 0.9},
            # 3 second gap here
            {"text": "第二段", "start": 4.5, "end": 5.0, "confidence": 0.8},
            {"text": "开始", "start": 5.1, "end": 5.5, "confidence": 0.8},
        ]
        paragraphs = _group_words_into_paragraphs(words, gap_threshold_ms=1500)

        assert len(paragraphs) == 2
        assert len(paragraphs[0].words) == 2
        assert len(paragraphs[1].words) == 2
        assert paragraphs[0].idx == 0
        assert paragraphs[1].idx == 1

    def test_transcript_editor_empty_words_returns_empty(self):
        """Empty input → empty output."""
        paragraphs = _group_words_into_paragraphs([])
        assert len(paragraphs) == 0

    def test_transcript_editor_word_timing_preserved(self):
        """Word start_ms and end_ms are correctly converted from seconds."""
        words = [
            {"text": "测试", "start": 2.345, "end": 2.890, "confidence": 0.95},
        ]
        paragraphs = _group_words_into_paragraphs(words)

        assert len(paragraphs) == 1
        word = paragraphs[0].words[0]
        assert word.start_ms == 2345
        assert word.end_ms == 2890
        assert word.text == "测试"
        assert word.confidence == 0.95


class TestTranscribeToDoc:
    """Test transcribe_to_doc function."""

    def test_transcript_editor_invalid_path_raises_error(self):
        """Non-existent path → TranscriptError."""
        with pytest.raises(TranscriptError, match="not found"):
            transcribe_to_doc("/nonexistent/video.mp4")

    @patch("modules.review_engine.transcript_editor.HAS_FASTER_WHISPER", False)
    @patch("modules.review_engine.transcript_editor.HAS_OPENAI_WHISPER", False)
    @patch("modules.review_engine.transcript_editor._extract_audio_wav")
    def test_transcript_editor_no_engine_raises_error(self, mock_extract, tmp_path):
        """No ASR engine available → TranscriptError."""
        video_file = tmp_path / "test.mp4"
        video_file.touch()

        with pytest.raises(TranscriptError, match="No ASR engine"):
            transcribe_to_doc(str(video_file))

    @patch("modules.review_engine.transcript_editor.HAS_FASTER_WHISPER", True)
    @patch("modules.review_engine.transcript_editor._extract_audio_wav")
    @patch("modules.review_engine.transcript_editor._transcribe_faster_whisper_words")
    def test_transcript_editor_produces_transcript_doc(
        self, mock_transcribe, mock_extract, tmp_path
    ):
        """Happy path: produces TranscriptDoc with paragraphs."""
        video_file = tmp_path / "test.mp4"
        video_file.touch()

        mock_transcribe.return_value = (
            [
                {"text": "你好", "start": 0.0, "end": 0.5, "confidence": 0.9},
                {"text": "世界", "start": 0.6, "end": 1.0, "confidence": 0.9},
            ],
            5.0,  # duration
            "zh",  # language
        )

        doc = transcribe_to_doc(str(video_file), model_size="base")

        assert isinstance(doc, TranscriptDoc)
        assert doc.duration_ms == 5000
        assert doc.language == "zh"
        assert len(doc.paragraphs) == 1
        assert len(doc.paragraphs[0].words) == 2
