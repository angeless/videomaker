"""Filler word and dead air detector.

Rule-based detection of:
1. Filler words (语气词): 呃/嗯/就是/对/然后/所以说/反正/那个 etc.
2. Dead air (长静音): gaps > threshold between words/paragraphs.

Results are stored as FillerMark objects on paragraphs.
"""

import logging
import re
from typing import List, Set, Tuple

from modules.review_engine.contracts import (
    FillerMark,
    Paragraph,
    TranscriptDoc,
)

logger = logging.getLogger(__name__)

# Chinese filler words (common in spoken Chinese)
FILLER_WORDS_ZH: Set[str] = {
    "呃", "嗯", "啊", "哦", "噢", "哎",
    "就是", "就是说", "然后", "然后呢",
    "所以", "所以说", "所以呢",
    "对", "对对对", "对对", "对吧",
    "那个", "这个", "那种", "什么",
    "反正", "其实", "基本上",
}

# English filler words
FILLER_WORDS_EN: Set[str] = {
    "um", "uh", "er", "ah", "like", "you know",
    "i mean", "so", "well", "actually", "basically",
    "literally", "right", "okay",
}

# Dead air threshold (ms)
DEFAULT_DEAD_AIR_THRESHOLD_MS = 1500


def detect_filler_words(
    doc: TranscriptDoc,
    custom_fillers: Set[str] = None,
) -> List[FillerMark]:
    """Detect filler words in transcript paragraphs.

    Marks individual words that match known filler patterns.
    Returns list of FillerMark objects (also attached to paragraphs).

    Args:
        doc: TranscriptDoc with word-level paragraphs.
        custom_fillers: Additional filler words to detect.

    Returns:
        List of all FillerMark objects found.
    """
    # Select filler set based on language
    if doc.language.startswith("zh"):
        fillers = FILLER_WORDS_ZH.copy()
    elif doc.language.startswith("en"):
        fillers = FILLER_WORDS_EN.copy()
    else:
        fillers = FILLER_WORDS_ZH | FILLER_WORDS_EN

    if custom_fillers:
        fillers |= custom_fillers

    all_marks = []

    for para in doc.paragraphs:
        para_marks = []
        for i, word in enumerate(para.words):
            text_lower = word.text.lower().strip()
            if text_lower in fillers:
                mark = FillerMark(
                    word_idx=i,
                    start_ms=word.start_ms,
                    end_ms=word.end_ms,
                    filler_type="filler_word",
                    text=word.text,
                    auto_marked=True,
                )
                para_marks.append(mark)

        para.filler_marks.extend(para_marks)
        all_marks.extend(para_marks)

    logger.info("Detected %d filler words", len(all_marks))
    return all_marks


def detect_dead_air(
    doc: TranscriptDoc,
    threshold_ms: int = DEFAULT_DEAD_AIR_THRESHOLD_MS,
) -> List[FillerMark]:
    """Detect dead air (long silence) between paragraphs.

    Args:
        doc: TranscriptDoc with paragraphs.
        threshold_ms: Minimum silence duration to flag (default 1500ms).

    Returns:
        List of FillerMark objects for dead air segments.
    """
    all_marks = []

    for i in range(len(doc.paragraphs) - 1):
        current = doc.paragraphs[i]
        next_para = doc.paragraphs[i + 1]

        gap_ms = next_para.start_ms - current.end_ms

        if gap_ms >= threshold_ms:
            mark = FillerMark(
                word_idx=-1,  # Not a word
                start_ms=current.end_ms,
                end_ms=next_para.start_ms,
                filler_type="dead_air",
                text=f"[silence {gap_ms}ms]",
                auto_marked=True,
            )
            all_marks.append(mark)

    # Also check within paragraphs (word-level gaps)
    for para in doc.paragraphs:
        for i in range(len(para.words) - 1):
            gap_ms = para.words[i + 1].start_ms - para.words[i].end_ms
            if gap_ms >= threshold_ms:
                mark = FillerMark(
                    word_idx=i,
                    start_ms=para.words[i].end_ms,
                    end_ms=para.words[i + 1].start_ms,
                    filler_type="dead_air",
                    text=f"[silence {gap_ms}ms]",
                    auto_marked=True,
                )
                para.filler_marks.append(mark)
                all_marks.append(mark)

    logger.info("Detected %d dead air segments (>%dms)", len(all_marks), threshold_ms)
    return all_marks


def auto_mark_fillers(
    doc: TranscriptDoc,
    dead_air_threshold_ms: int = DEFAULT_DEAD_AIR_THRESHOLD_MS,
    custom_fillers: Set[str] = None,
) -> TranscriptDoc:
    """Run all filler detection on a TranscriptDoc.

    Convenience function that runs filler words + dead air detection.

    Returns:
        The same TranscriptDoc with filler_marks populated.
    """
    detect_filler_words(doc, custom_fillers)
    detect_dead_air(doc, dead_air_threshold_ms)
    return doc
