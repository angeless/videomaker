"""Unit tests for speaker_diarizer module."""

import pytest
from modules.review_engine.speaker_diarizer import (
    _assign_speakers_by_overlap,
    _fallback_single_speaker,
    diarize_transcript,
)
from modules.review_engine.contracts import Paragraph, TranscriptDoc, Word


def _make_doc(paragraphs=None):
    """Helper to create a TranscriptDoc for testing."""
    return TranscriptDoc(
        video_path="/test/video.mp4",
        duration_ms=10000,
        paragraphs=paragraphs or [],
    )


def _make_para(idx, start_ms, end_ms, words=None):
    """Helper to create a Paragraph."""
    return Paragraph(
        idx=idx,
        speaker=None,
        start_ms=start_ms,
        end_ms=end_ms,
        words=words or [Word(text="test", start_ms=start_ms, end_ms=end_ms)],
    )


class TestAssignSpeakersByOverlap:
    """Test speaker assignment based on diarization overlap."""

    def test_speaker_diarizer_assigns_correct_speaker(self):
        """Speaker with most overlap wins."""
        paras = [
            _make_para(0, 0, 3000),
            _make_para(1, 4000, 7000),
        ]
        diarization = [
            (0.0, 3.5, "SPEAKER_A"),
            (3.5, 8.0, "SPEAKER_B"),
        ]

        _assign_speakers_by_overlap(paras, diarization)

        assert paras[0].speaker == "SPEAKER_A"
        assert paras[1].speaker == "SPEAKER_B"

    def test_speaker_diarizer_handles_overlapping_speakers(self):
        """When two speakers overlap, the one with more overlap wins."""
        paras = [_make_para(0, 2000, 5000)]
        diarization = [
            (0.0, 3.0, "SPEAKER_A"),   # overlap: 1s (2-3)
            (2.5, 6.0, "SPEAKER_B"),  # overlap: 2.5s (2.5-5)
        ]

        _assign_speakers_by_overlap(paras, diarization)

        assert paras[0].speaker == "SPEAKER_B"


class TestFallbackSingleSpeaker:
    """Test single-speaker fallback."""

    def test_speaker_diarizer_fallback_labels_all_speaker_0(self):
        """Fallback assigns SPEAKER_0 to all paragraphs."""
        paras = [_make_para(0, 0, 1000), _make_para(1, 2000, 3000)]

        _fallback_single_speaker(paras)

        assert all(p.speaker == "SPEAKER_0" for p in paras)


class TestDiarizeTranscript:
    """Test the main diarize_transcript function."""

    def test_speaker_diarizer_no_pyannote_uses_fallback(self):
        """Without pyannote and no audio → fallback."""
        doc = _make_doc([_make_para(0, 0, 5000)])

        result = diarize_transcript(doc)

        assert result.speakers == ["SPEAKER_0"]
        assert result.paragraphs[0].speaker == "SPEAKER_0"
