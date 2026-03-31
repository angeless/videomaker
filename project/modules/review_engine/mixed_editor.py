"""Mixed path editor — separate speech and B-roll segments.

For videos classified as "mixed" (0.15 <= speech_ratio <= 0.6),
this module splits the video into speech segments (processed by
transcript editor) and B-roll segments (processed by scene segmenter),
then merges them back in time order.
"""

import logging
from typing import Dict, List, Tuple

from modules.review_engine.contracts import (
    Paragraph,
    Segment,
    TranscriptDoc,
)

logger = logging.getLogger(__name__)

# Minimum gap to consider a segment as B-roll (ms)
BROLL_GAP_THRESHOLD_MS = 2000


def separate_segments(
    doc: TranscriptDoc,
    video_path: str,
    total_duration_ms: int,
) -> Dict:
    """Separate video into speech and B-roll segments.

    Speech segments: where paragraphs exist (voice active).
    B-roll segments: gaps between paragraphs > threshold.

    Args:
        doc: TranscriptDoc with paragraphs.
        video_path: Source video path.
        total_duration_ms: Total video duration in ms.

    Returns:
        Dict with keys:
        - speech_segments: List[Segment] — voice-active regions
        - broll_segments: List[Segment] — non-voice regions
    """
    if not doc.paragraphs:
        return {
            "speech_segments": [],
            "broll_segments": [Segment(
                source_path=video_path,
                start_ms=0,
                end_ms=total_duration_ms,
                segment_type="keep",
                label="broll",
            )],
        }

    speech_segments = []
    broll_segments = []

    # Leading B-roll (before first speech)
    first_start = doc.paragraphs[0].start_ms
    if first_start > BROLL_GAP_THRESHOLD_MS:
        broll_segments.append(Segment(
            source_path=video_path,
            start_ms=0,
            end_ms=first_start,
            segment_type="keep",
            label="broll",
        ))

    # Process paragraphs and gaps
    for i, para in enumerate(doc.paragraphs):
        # Speech segment
        speech_segments.append(Segment(
            source_path=video_path,
            start_ms=para.start_ms,
            end_ms=para.end_ms,
            segment_type="keep",
            paragraph_idx=para.idx,
            label="speech",
        ))

        # Check gap to next paragraph
        if i < len(doc.paragraphs) - 1:
            gap_start = para.end_ms
            gap_end = doc.paragraphs[i + 1].start_ms
            gap_ms = gap_end - gap_start

            if gap_ms >= BROLL_GAP_THRESHOLD_MS:
                broll_segments.append(Segment(
                    source_path=video_path,
                    start_ms=gap_start,
                    end_ms=gap_end,
                    segment_type="keep",
                    label="broll",
                ))

    # Trailing B-roll (after last speech)
    last_end = doc.paragraphs[-1].end_ms
    if total_duration_ms - last_end > BROLL_GAP_THRESHOLD_MS:
        broll_segments.append(Segment(
            source_path=video_path,
            start_ms=last_end,
            end_ms=total_duration_ms,
            segment_type="keep",
            label="broll",
        ))

    logger.info(
        "Separated: %d speech segments, %d B-roll segments",
        len(speech_segments), len(broll_segments),
    )

    return {
        "speech_segments": speech_segments,
        "broll_segments": broll_segments,
    }


def merge_segments(
    speech_segments: List[Segment],
    broll_segments: List[Segment],
) -> List[Segment]:
    """Merge speech and B-roll segments in time order.

    Args:
        speech_segments: Voice-active segments.
        broll_segments: Non-voice segments.

    Returns:
        Merged list sorted by start_ms.
    """
    all_segments = speech_segments + broll_segments
    all_segments.sort(key=lambda s: s.start_ms)
    return all_segments
