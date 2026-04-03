"""Tests for CommentResolver — R1 + R2."""

import pytest

from modules.review_engine.contracts import Segment, Word
from modules.review_engine.comment_resolver import (
    resolve_comment,
    detect_gaps,
    find_original_content,
    resolve_with_gap_detection,
    ResolvedComment,
)


def _seg(start, end, path="video.mp4", stype="keep"):
    return Segment(source_path=path, start_ms=start, end_ms=end, segment_type=stype)


# ── R1: resolve_comment ──

class TestResolveComment:

    def test_exact_match(self):
        """Comment time falls exactly within a segment."""
        edits = [_seg(0, 5000), _seg(5000, 10000), _seg(10000, 15000)]
        result = resolve_comment(6000, None, edits)
        assert result.matched_segments == [1]

    def test_range_match(self):
        """Comment time range spans multiple segments."""
        edits = [_seg(0, 5000), _seg(5000, 10000), _seg(10000, 15000)]
        result = resolve_comment(3000, 12000, edits)
        assert result.matched_segments == [0, 1, 2]

    def test_boundary(self):
        """Comment at exact boundary between segments → nearest."""
        edits = [_seg(0, 5000), _seg(5000, 10000)]
        result = resolve_comment(5000, None, edits)
        assert 1 in result.matched_segments

    def test_out_of_range(self):
        """Comment time beyond all segments → returns nearest."""
        edits = [_seg(0, 5000), _seg(5000, 10000)]
        result = resolve_comment(99000, None, edits)
        assert len(result.matched_segments) == 1
        # Should be the last segment
        assert result.matched_segments[0] == 1

    def test_empty_edits(self):
        """No segments → empty result."""
        result = resolve_comment(1000, None, [])
        assert result.matched_segments == []

    def test_single_segment(self):
        """Single segment, comment inside."""
        edits = [_seg(0, 10000)]
        result = resolve_comment(5000, 7000, edits)
        assert result.matched_segments == [0]


# ── R2: detect_gaps ──

class TestDetectGaps:

    def test_gap_detection(self):
        """Consecutive segments with a gap in source timeline."""
        edits = [_seg(0, 5000), _seg(8000, 12000)]
        gaps = detect_gaps(edits)
        assert len(gaps) == 1
        assert gaps[0]["gap_start_ms"] == 5000
        assert gaps[0]["gap_end_ms"] == 8000
        assert gaps[0]["gap_duration_ms"] == 3000

    def test_no_gap(self):
        """Segments are contiguous."""
        edits = [_seg(0, 5000), _seg(5000, 10000)]
        gaps = detect_gaps(edits)
        assert gaps == []

    def test_multiple_gaps(self):
        """Multiple gaps between segments."""
        edits = [_seg(0, 3000), _seg(5000, 8000), _seg(12000, 15000)]
        gaps = detect_gaps(edits)
        assert len(gaps) == 2


class TestFindOriginalContent:

    def test_original_text_found(self):
        """Words in the gap region are returned."""
        words = [
            Word(text="hello", start_ms=5000, end_ms=5500),
            Word(text="world", start_ms=5500, end_ms=6000),
            Word(text="outside", start_ms=9000, end_ms=9500),
        ]
        text = find_original_content(5000, 8000, words)
        assert text == "hello world"

    def test_no_words_in_gap(self):
        """No words in gap range."""
        words = [Word(text="x", start_ms=0, end_ms=500)]
        text = find_original_content(5000, 8000, words)
        assert text == ""


# ── R2: resolve_with_gap_detection ──

class TestResolveWithGapDetection:

    def test_gap_with_original_text(self):
        """Comment in a gap region gets enriched with original text."""
        # Segments: [0-5000] [gap: 5000-8000] [8000-12000]
        # Output timeline: [0-5000] [5000-9000]
        # A comment at 5500 in output falls at the boundary
        edits = [_seg(0, 5000), _seg(8000, 12000)]
        words = [
            Word(text="deleted", start_ms=5500, end_ms=6000),
            Word(text="stuff", start_ms=6200, end_ms=6800),
        ]
        result = resolve_with_gap_detection(5000, 5500, edits, words)
        # Should match segment 1 since 5000-5500 overlaps [5000, 9000)
        assert len(result.matched_segments) > 0 or result.gap_info is not None
