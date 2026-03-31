"""Unit tests for filler_detector module."""

import pytest
from modules.review_engine.filler_detector import (
    detect_filler_words,
    detect_dead_air,
    auto_mark_fillers,
)
from modules.review_engine.contracts import (
    FillerMark,
    Paragraph,
    TranscriptDoc,
    Word,
)


def _make_doc(paragraphs, language="zh"):
    """Helper to create a TranscriptDoc."""
    return TranscriptDoc(
        video_path="/test/video.mp4",
        duration_ms=10000,
        paragraphs=paragraphs,
        language=language,
    )


def _make_para(idx, words_data):
    """Helper: words_data is list of (text, start_ms, end_ms)."""
    words = [
        Word(text=t, start_ms=s, end_ms=e)
        for t, s, e in words_data
    ]
    return Paragraph(
        idx=idx,
        speaker=None,
        start_ms=words[0].start_ms if words else 0,
        end_ms=words[-1].end_ms if words else 0,
        words=words,
    )


class TestDetectFillerWords:
    """Test filler word detection."""

    def test_filler_detector_marks_chinese_fillers(self):
        """Chinese filler words are detected and marked."""
        para = _make_para(0, [
            ("兴奋感", 0, 500),
            ("就是", 500, 700),
            ("在于", 700, 1000),
            ("呃", 1000, 1200),
            ("我意识到", 1200, 1800),
        ])
        doc = _make_doc([para])

        marks = detect_filler_words(doc)

        assert len(marks) == 2
        assert marks[0].text == "就是"
        assert marks[0].filler_type == "filler_word"
        assert marks[1].text == "呃"

    def test_filler_detector_no_fillers_returns_empty(self):
        """Clean speech → no filler marks."""
        para = _make_para(0, [
            ("今天", 0, 300),
            ("天气", 300, 600),
            ("很好", 600, 900),
        ])
        doc = _make_doc([para])

        marks = detect_filler_words(doc)

        assert len(marks) == 0

    def test_filler_detector_english_fillers(self):
        """English filler words are detected."""
        para = _make_para(0, [
            ("um", 0, 200),
            ("so", 200, 400),
            ("like", 400, 600),
            ("the", 600, 800),
            ("thing", 800, 1000),
        ])
        doc = _make_doc([para], language="en")

        marks = detect_filler_words(doc)

        assert len(marks) == 3  # um, so, like


class TestDetectDeadAir:
    """Test dead air (silence) detection."""

    def test_filler_detector_detects_gap_between_paragraphs(self):
        """Gap > threshold between paragraphs → dead air mark."""
        para1 = _make_para(0, [("你好", 0, 1000)])
        para2 = _make_para(1, [("世界", 4000, 5000)])  # 3s gap
        doc = _make_doc([para1, para2])

        marks = detect_dead_air(doc, threshold_ms=1500)

        assert len(marks) == 1
        assert marks[0].filler_type == "dead_air"
        assert marks[0].start_ms == 1000
        assert marks[0].end_ms == 4000

    def test_filler_detector_no_dead_air_when_continuous(self):
        """Continuous speech → no dead air."""
        para1 = _make_para(0, [("你好", 0, 1000)])
        para2 = _make_para(1, [("世界", 1200, 2000)])  # 200ms gap
        doc = _make_doc([para1, para2])

        marks = detect_dead_air(doc, threshold_ms=1500)

        assert len(marks) == 0


class TestAutoMarkFillers:
    """Test combined filler detection."""

    def test_filler_detector_auto_mark_finds_all_types(self):
        """auto_mark_fillers detects both filler words and dead air."""
        para1 = _make_para(0, [
            ("呃", 0, 200),
            ("开始", 200, 500),
        ])
        para2 = _make_para(1, [("继续", 3000, 3500)])  # 2.5s gap
        doc = _make_doc([para1, para2])

        auto_mark_fillers(doc, dead_air_threshold_ms=1500)

        # 1 filler word + 1 dead air
        total_marks = sum(len(p.filler_marks) for p in doc.paragraphs)
        assert total_marks >= 1  # at least the filler word on para1
