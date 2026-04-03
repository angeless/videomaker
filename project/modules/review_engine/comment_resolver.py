"""CommentResolver — map comment timestamps to edit segments.

Provides two capabilities:
1. Time→segment mapping: binary search to find which segment(s) a comment targets
2. Gap detection: identify when a comment points to deleted content between segments
"""

import bisect
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .contracts import Segment, Word

logger = logging.getLogger(__name__)


@dataclass
class GapInfo:
    """Info about a gap (deleted content) between two segments."""
    gap_start_ms: int
    gap_end_ms: int
    original_text: str
    removed_segments: List[Dict] = field(default_factory=list)


@dataclass
class ResolvedComment:
    """Result of resolving a comment's time range to segments."""
    matched_segments: List[int]  # indices into the edits list
    gap_info: Optional[GapInfo] = None
    suggested_action: Optional[str] = None  # "extend" | "restore" | None


def resolve_comment(
    time_start_ms: int,
    time_end_ms: Optional[int],
    edits: List[Segment],
) -> ResolvedComment:
    """Map a comment's time range to segments in the edit list.

    Uses binary search on segment start times for O(log n) lookup.
    """
    if not edits:
        return ResolvedComment(matched_segments=[], suggested_action=None)

    if time_end_ms is None:
        time_end_ms = time_start_ms

    # Build cumulative timeline: segments are placed sequentially in output
    # Each segment occupies [cumulative_start, cumulative_start + duration)
    cum_starts = []
    cum_ends = []
    offset = 0
    for seg in edits:
        dur = seg.end_ms - seg.start_ms
        cum_starts.append(offset)
        cum_ends.append(offset + dur)
        offset += dur

    matched = []
    for i, (cs, ce) in enumerate(zip(cum_starts, cum_ends)):
        # Overlap check: comment range [time_start_ms, time_end_ms]
        # overlaps segment range [cs, ce)
        if time_start_ms < ce and time_end_ms >= cs:
            matched.append(i)

    if not matched:
        # Find nearest segment
        idx = bisect.bisect_right(cum_starts, time_start_ms) - 1
        idx = max(0, min(idx, len(edits) - 1))
        # Check if it's in a gap between segments
        if 0 <= idx < len(edits) - 1:
            gap_start = cum_ends[idx]
            gap_end = cum_starts[idx + 1]
            if gap_start <= time_start_ms < gap_end:
                return ResolvedComment(
                    matched_segments=[],
                    gap_info=GapInfo(
                        gap_start_ms=gap_start,
                        gap_end_ms=gap_end,
                        original_text="",
                    ),
                    suggested_action="restore",
                )
        # Time out of range — return nearest
        return ResolvedComment(
            matched_segments=[idx] if edits else [],
            suggested_action=None,
        )

    return ResolvedComment(matched_segments=matched)


def detect_gaps(edits: List[Segment]) -> List[Dict]:
    """Detect gaps between consecutive segments in source timeline.

    A gap exists when segment[i].end_ms < segment[i+1].start_ms
    in the original source (not the output timeline).
    """
    gaps = []
    for i in range(len(edits) - 1):
        curr_end = edits[i].end_ms
        next_start = edits[i + 1].start_ms
        if curr_end < next_start and edits[i].source_path == edits[i + 1].source_path:
            gaps.append({
                "after_segment_idx": i,
                "gap_start_ms": curr_end,
                "gap_end_ms": next_start,
                "gap_duration_ms": next_start - curr_end,
            })
    return gaps


def find_original_content(
    gap_start_ms: int,
    gap_end_ms: int,
    original_words: List[Word],
) -> str:
    """Find the original transcribed text that was in a gap region."""
    words_in_gap = [
        w for w in original_words
        if w.start_ms >= gap_start_ms and w.end_ms <= gap_end_ms
    ]
    return " ".join(w.text for w in words_in_gap)


def resolve_with_gap_detection(
    time_start_ms: int,
    time_end_ms: Optional[int],
    edits: List[Segment],
    original_words: Optional[List[Word]] = None,
) -> ResolvedComment:
    """Full resolution: map time to segments, detect gaps, find original content."""
    result = resolve_comment(time_start_ms, time_end_ms, edits)

    if result.gap_info is not None and original_words:
        # Enrich gap info with original text
        # Map output timeline gap back to source timeline
        gaps = detect_gaps(edits)
        for gap in gaps:
            text = find_original_content(
                gap["gap_start_ms"], gap["gap_end_ms"], original_words,
            )
            if text:
                result.gap_info.original_text = text
                result.gap_info.gap_start_ms = gap["gap_start_ms"]
                result.gap_info.gap_end_ms = gap["gap_end_ms"]
                result.suggested_action = "restore"
                break

    if not result.matched_segments and result.gap_info is None:
        result.suggested_action = None

    return result
