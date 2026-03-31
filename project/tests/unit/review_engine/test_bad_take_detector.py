"""Unit tests for bad_take_detector module."""

import pytest
from modules.review_engine.bad_take_detector import (
    detect_retakes,
    detect_false_starts,
    detect_filler_sentences,
    _text_overlap_ratio,
    auto_detect_bad_takes,
)
from modules.review_engine.contracts import (
    Paragraph,
    TranscriptDoc,
    Word,
)


def _make_doc(paragraphs, language="zh"):
    return TranscriptDoc(
        video_path="/test/video.mp4",
        duration_ms=60000,
        paragraphs=paragraphs,
        language=language,
    )


def _make_para(idx, text_parts, start_ms=None, end_ms=None):
    """Create paragraph from list of word strings."""
    words = []
    t = start_ms or (idx * 5000)
    for text in text_parts:
        words.append(Word(text=text, start_ms=t, end_ms=t + 300))
        t += 400
    return Paragraph(
        idx=idx,
        speaker=None,
        start_ms=words[0].start_ms,
        end_ms=words[-1].end_ms,
        words=words,
    )


class TestTextOverlapRatio:
    """Test character-level overlap utility."""

    def test_bad_take_detector_identical_texts_ratio_1(self):
        assert _text_overlap_ratio("测试文本", "测试文本") == 1.0

    def test_bad_take_detector_no_overlap_ratio_0(self):
        assert _text_overlap_ratio("abc", "xyz") == 0.0

    def test_bad_take_detector_empty_returns_0(self):
        assert _text_overlap_ratio("", "test") == 0.0


class TestDetectRetakes:
    """Test retake detection (semantic repeats)."""

    def test_bad_take_detector_retake_detected_via_overlap(self):
        """Two similar paragraphs → earlier marked as retake (fallback)."""
        # Same characters → overlap = 1.0
        para1 = _make_para(0, ["我", "在", "把", "它", "当", "放", "大", "器", "用"])
        para2 = _make_para(1, ["我", "在", "把", "它", "当", "放", "大", "器", "用"])

        doc = _make_doc([para1, para2])
        marks = detect_retakes(doc, similarity_threshold=0.85)

        assert len(marks) == 1
        assert marks[0].paragraph_idx == 0
        assert marks[0].keep_idx == 1
        assert marks[0].retake_type == "semantic_repeat"

    def test_bad_take_detector_no_retake_different_content(self):
        """Different content → no retake."""
        para1 = _make_para(0, ["今天", "天气", "很好"])
        para2 = _make_para(1, ["明天", "要", "下雨"])

        doc = _make_doc([para1, para2])
        marks = detect_retakes(doc, similarity_threshold=0.85)

        assert len(marks) == 0


class TestDetectFalseStarts:
    """Test false start detection."""

    def test_bad_take_detector_false_start_short_then_long(self):
        """Short paragraph followed by longer similar one → false start."""
        para1 = _make_para(0, ["我", "觉得"])
        para2 = _make_para(1, ["我", "觉得", "这个", "方案", "很好"])

        doc = _make_doc([para1, para2])
        marks = detect_false_starts(doc, max_words=8, similarity_threshold=0.4)

        assert len(marks) == 1
        assert marks[0].retake_type == "false_start"
        assert marks[0].paragraph_idx == 0

    def test_bad_take_detector_no_false_start_long_paragraph(self):
        """Long paragraph → not a false start candidate."""
        para1 = _make_para(0, ["这", "是", "一", "段", "很", "长", "的", "内", "容", "不会"])
        para2 = _make_para(1, ["另", "一", "段"])

        doc = _make_doc([para1, para2])
        marks = detect_false_starts(doc, max_words=8)

        assert len(marks) == 0


class TestDetectFillerSentences:
    """Test filler sentence detection."""

    def test_bad_take_detector_filler_sentence_detected(self):
        """Pure filler sentence (对对对) → detected."""
        para = _make_para(0, ["对", "对", "对"])
        doc = _make_doc([para])

        marks = detect_filler_sentences(doc)

        assert len(marks) == 1
        assert marks[0].filler_type == "filler_sentence"

    def test_bad_take_detector_substantive_sentence_not_filler(self):
        """Substantive content → not a filler sentence."""
        para = _make_para(0, ["这个", "功能", "做得", "很好"])
        doc = _make_doc([para])

        marks = detect_filler_sentences(doc)

        assert len(marks) == 0

    def test_bad_take_detector_english_filler_detected(self):
        """English filler sentence → detected."""
        para = _make_para(0, ["yeah"])
        doc = _make_doc([para], language="en")

        marks = detect_filler_sentences(doc)

        assert len(marks) == 1


class TestAutoDetectBadTakes:
    """Test combined bad take detection."""

    def test_bad_take_detector_auto_runs_all(self):
        """auto_detect_bad_takes populates marks."""
        para1 = _make_para(0, ["对", "对", "对"])
        para2 = _make_para(1, ["今天", "天气", "很好"])
        doc = _make_doc([para1, para2])

        auto_detect_bad_takes(doc)

        # At least the filler sentence should be detected
        assert len(para1.filler_marks) >= 1
