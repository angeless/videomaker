"""Unit tests for mixed_editor module."""

import pytest
from modules.review_engine.contracts import Paragraph, Segment, TranscriptDoc, Word
from modules.review_engine.mixed_editor import (
    BROLL_GAP_THRESHOLD_MS,
    merge_segments,
    separate_segments,
)


def _make_doc(paragraphs):
    return TranscriptDoc(
        video_path="/test/video.mp4",
        duration_ms=60000,
        paragraphs=paragraphs,
        language="zh",
    )


def _make_para(idx, start_ms, end_ms):
    word = Word(text="测试", start_ms=start_ms, end_ms=end_ms)
    return Paragraph(idx=idx, speaker=None, start_ms=start_ms, end_ms=end_ms, words=[word])


class TestSeparateSegments:
    """Test speech/B-roll separation."""

    def test_mixed_editor_no_paragraphs_all_broll(self):
        doc = _make_doc([])
        result = separate_segments(doc, "/v.mp4", 10000)
        assert len(result["speech_segments"]) == 0
        assert len(result["broll_segments"]) == 1
        assert result["broll_segments"][0].end_ms == 10000

    def test_mixed_editor_single_paragraph_with_leading_broll(self):
        para = _make_para(0, 5000, 8000)
        doc = _make_doc([para])
        result = separate_segments(doc, "/v.mp4", 10000)

        assert len(result["speech_segments"]) == 1
        assert result["speech_segments"][0].start_ms == 5000

        # Leading B-roll: 0→5000 (> threshold)
        broll = [s for s in result["broll_segments"] if s.start_ms == 0]
        assert len(broll) == 1
        assert broll[0].end_ms == 5000

    def test_mixed_editor_trailing_broll(self):
        para = _make_para(0, 1000, 3000)
        doc = _make_doc([para])
        # total=10000, last_end=3000, gap=7000 > threshold
        result = separate_segments(doc, "/v.mp4", 10000)

        trailing = [s for s in result["broll_segments"] if s.start_ms == 3000]
        assert len(trailing) == 1
        assert trailing[0].end_ms == 10000

    def test_mixed_editor_gap_between_paragraphs(self):
        p1 = _make_para(0, 1000, 3000)
        p2 = _make_para(1, 8000, 10000)
        doc = _make_doc([p1, p2])
        # Gap: 3000→8000 = 5000ms > threshold
        result = separate_segments(doc, "/v.mp4", 12000)

        assert len(result["speech_segments"]) == 2
        gap_broll = [s for s in result["broll_segments"] if s.start_ms == 3000]
        assert len(gap_broll) == 1
        assert gap_broll[0].end_ms == 8000

    def test_mixed_editor_small_gap_not_broll(self):
        p1 = _make_para(0, 1000, 3000)
        p2 = _make_para(1, 3500, 5000)
        doc = _make_doc([p1, p2])
        # Gap: 3000→3500 = 500ms < threshold (2000)
        result = separate_segments(doc, "/v.mp4", 5000)

        gap_broll = [s for s in result["broll_segments"]
                     if s.start_ms == 3000 and s.end_ms == 3500]
        assert len(gap_broll) == 0

    def test_mixed_editor_labels_correct(self):
        para = _make_para(0, 3000, 6000)
        doc = _make_doc([para])
        result = separate_segments(doc, "/v.mp4", 10000)

        for seg in result["speech_segments"]:
            assert seg.label == "speech"
        for seg in result["broll_segments"]:
            assert seg.label == "broll"


class TestMergeSegments:
    """Test merging speech + B-roll in time order."""

    def test_mixed_editor_merge_sorts_by_start(self):
        s1 = Segment(source_path="/v", start_ms=5000, end_ms=8000, segment_type="keep", label="speech")
        s2 = Segment(source_path="/v", start_ms=0, end_ms=3000, segment_type="keep", label="broll")
        s3 = Segment(source_path="/v", start_ms=3000, end_ms=5000, segment_type="keep", label="broll")

        merged = merge_segments([s1], [s2, s3])
        assert [s.start_ms for s in merged] == [0, 3000, 5000]

    def test_mixed_editor_merge_empty_lists(self):
        assert merge_segments([], []) == []
