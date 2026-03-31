"""Bad take detector — detect retakes, false starts, and filler sentences.

Three detection strategies:
1. Retake detection: Semantic similarity between consecutive paragraphs
   (cosine > threshold → the earlier one is a bad take)
2. False start detection: Paragraph interrupted and restarted
   (short paragraph followed by similar but longer one)
3. Filler sentence detection: Entire sentences with no substantive content
   (rule-based patterns for common filler sentences)
"""

import logging
import re
from typing import List, Optional, Set

from modules.review_engine.contracts import (
    FillerMark,
    Paragraph,
    RetakeMark,
    TranscriptDoc,
)

logger = logging.getLogger(__name__)

# Try to import sentence-transformers for semantic similarity
try:
    from sentence_transformers import SentenceTransformer, util as st_util
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

# Retake detection thresholds
RETAKE_SIMILARITY_THRESHOLD = 0.85  # cosine similarity
FALSE_START_MAX_WORDS = 8  # paragraphs shorter than this might be false starts
FALSE_START_SIMILARITY_THRESHOLD = 0.7

# Filler sentence patterns (regex)
FILLER_SENTENCE_PATTERNS_ZH = [
    r"^(对+|嗯+|啊+|哦+|噢+)$",           # 纯语气词
    r"^就是(那个|这个)?$",                   # "就是" "就是那个"
    r"^然后(呢|吧)?$",                      # "然后" "然后呢"
    r"^所以(说|呢)?$",                      # "所以" "所以说"
    r"^怎么说呢$",
    r"^不是.{0,2}$",                        # "不是" (short)
    r"^(那|那个)$",
    r"^(好|好的|OK|ok)$",
]

FILLER_SENTENCE_PATTERNS_EN = [
    r"^(yeah|yes|no|ok|okay|right|sure|uh huh)$",
    r"^(so|well|like|anyway)$",
    r"^you know$",
    r"^i mean$",
]


def _get_paragraph_text(para: Paragraph) -> str:
    """Get the full text of a paragraph from its words."""
    return "".join(w.text for w in para.words)


def _compute_similarity_batch(texts: List[str]) -> Optional[list]:
    """Compute pairwise cosine similarity for consecutive texts.

    Returns list of similarities [(i, i+1, sim)] or None if no model.
    """
    if not HAS_SENTENCE_TRANSFORMERS or len(texts) < 2:
        return None

    try:
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        embeddings = model.encode(texts, convert_to_tensor=True)

        results = []
        for i in range(len(texts) - 1):
            sim = float(st_util.cos_sim(embeddings[i], embeddings[i + 1])[0][0])
            results.append((i, i + 1, sim))
        return results
    except Exception as e:
        logger.warning("Sentence transformer failed: %s", e)
        return None


def detect_retakes(
    doc: TranscriptDoc,
    similarity_threshold: float = RETAKE_SIMILARITY_THRESHOLD,
) -> List[RetakeMark]:
    """Detect retake segments (speaker says the same thing twice).

    Uses semantic similarity between consecutive paragraphs.
    Falls back to simple text overlap if no sentence transformer.

    Args:
        doc: TranscriptDoc with paragraphs.
        similarity_threshold: Cosine similarity threshold.

    Returns:
        List of RetakeMark objects.
    """
    paragraphs = [p for p in doc.paragraphs if not p.is_deleted]
    if len(paragraphs) < 2:
        return []

    texts = [_get_paragraph_text(p) for p in paragraphs]
    marks = []

    # Try semantic similarity
    sims = _compute_similarity_batch(texts)

    if sims is not None:
        for i, j, sim in sims:
            if sim >= similarity_threshold:
                # Keep the later (usually better) take
                mark = RetakeMark(
                    paragraph_idx=paragraphs[i].idx,
                    start_ms=paragraphs[i].start_ms,
                    end_ms=paragraphs[i].end_ms,
                    retake_type="semantic_repeat",
                    keep_idx=paragraphs[j].idx,
                    similarity=round(sim, 3),
                )
                paragraphs[i].retake_marks.append(mark)
                marks.append(mark)
    else:
        # Fallback: simple character overlap
        for i in range(len(texts) - 1):
            overlap = _text_overlap_ratio(texts[i], texts[i + 1])
            if overlap >= similarity_threshold:
                mark = RetakeMark(
                    paragraph_idx=paragraphs[i].idx,
                    start_ms=paragraphs[i].start_ms,
                    end_ms=paragraphs[i].end_ms,
                    retake_type="semantic_repeat",
                    keep_idx=paragraphs[i + 1].idx,
                    similarity=round(overlap, 3),
                )
                paragraphs[i].retake_marks.append(mark)
                marks.append(mark)

    logger.info("Detected %d retake segments", len(marks))
    return marks


def _text_overlap_ratio(text_a: str, text_b: str) -> float:
    """Simple character-level overlap ratio (fallback for no ML)."""
    if not text_a or not text_b:
        return 0.0
    set_a = set(text_a)
    set_b = set(text_b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def detect_false_starts(
    doc: TranscriptDoc,
    max_words: int = FALSE_START_MAX_WORDS,
    similarity_threshold: float = FALSE_START_SIMILARITY_THRESHOLD,
) -> List[RetakeMark]:
    """Detect false starts (short interrupted paragraphs).

    Pattern: short paragraph (< max_words) followed by a longer paragraph
    that starts with similar content → the short one is a false start.

    Args:
        doc: TranscriptDoc.
        max_words: Maximum words for a paragraph to be a false start candidate.
        similarity_threshold: Overlap threshold.

    Returns:
        List of RetakeMark objects.
    """
    paragraphs = [p for p in doc.paragraphs if not p.is_deleted]
    marks = []

    for i in range(len(paragraphs) - 1):
        current = paragraphs[i]
        next_para = paragraphs[i + 1]

        # Current must be short
        if len(current.words) > max_words:
            continue

        # Next must be longer
        if len(next_para.words) <= len(current.words):
            continue

        # Check if the start of next_para overlaps with current
        current_text = _get_paragraph_text(current)
        next_prefix = "".join(w.text for w in next_para.words[:len(current.words) + 2])

        overlap = _text_overlap_ratio(current_text, next_prefix)
        if overlap >= similarity_threshold:
            mark = RetakeMark(
                paragraph_idx=current.idx,
                start_ms=current.start_ms,
                end_ms=current.end_ms,
                retake_type="false_start",
                keep_idx=next_para.idx,
                similarity=round(overlap, 3),
            )
            current.retake_marks.append(mark)
            marks.append(mark)

    logger.info("Detected %d false starts", len(marks))
    return marks


def detect_filler_sentences(
    doc: TranscriptDoc,
) -> List[FillerMark]:
    """Detect entire paragraphs that are filler sentences.

    Rule-based: matches common patterns like "对对对", "嗯嗯", "就是那个".

    Returns:
        List of FillerMark objects for filler sentences.
    """
    if doc.language.startswith("zh"):
        patterns = [re.compile(p) for p in FILLER_SENTENCE_PATTERNS_ZH]
    elif doc.language.startswith("en"):
        patterns = [re.compile(p, re.IGNORECASE) for p in FILLER_SENTENCE_PATTERNS_EN]
    else:
        patterns = [re.compile(p) for p in FILLER_SENTENCE_PATTERNS_ZH] + \
                   [re.compile(p, re.IGNORECASE) for p in FILLER_SENTENCE_PATTERNS_EN]

    marks = []

    for para in doc.paragraphs:
        if para.is_deleted:
            continue

        text = _get_paragraph_text(para).strip()

        for pattern in patterns:
            if pattern.match(text):
                mark = FillerMark(
                    word_idx=-1,
                    start_ms=para.start_ms,
                    end_ms=para.end_ms,
                    filler_type="filler_sentence",
                    text=text,
                    auto_marked=True,
                )
                para.filler_marks.append(mark)
                marks.append(mark)
                break  # One mark per paragraph

    logger.info("Detected %d filler sentences", len(marks))
    return marks


def auto_detect_bad_takes(doc: TranscriptDoc) -> TranscriptDoc:
    """Run all bad take detection on a TranscriptDoc.

    Runs: retakes + false starts + filler sentences.

    Returns:
        The same TranscriptDoc with retake_marks and filler_marks populated.
    """
    detect_retakes(doc)
    detect_false_starts(doc)
    detect_filler_sentences(doc)
    return doc
