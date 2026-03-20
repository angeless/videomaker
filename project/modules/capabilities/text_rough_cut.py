"""Text-driven rough cut planning utilities."""

from dataclasses import asdict, dataclass
import re
from typing import Dict, Iterable, List, Optional, Sequence


@dataclass
class TranscriptSpan:
    """Single transcript span aligned to source media time."""

    start: float
    end: float
    text: str
    confidence: float = 1.0


def normalize_spans(spans: Iterable[TranscriptSpan]) -> List[TranscriptSpan]:
    """Sort spans and remove invalid ranges."""
    normalized: List[TranscriptSpan] = []
    for span in sorted(spans, key=lambda x: x.start):
        start = max(float(span.start), 0.0)
        end = max(float(span.end), start)
        if end <= start:
            continue
        normalized.append(
            TranscriptSpan(
                start=start,
                end=end,
                text=str(span.text or "").strip(),
                confidence=float(span.confidence or 0.0),
            )
        )
    return normalized


def build_text_rough_cut_plan(
    spans: Sequence[TranscriptSpan],
    removed_phrases: Optional[Sequence[str]] = None,
    target_duration_s: Optional[float] = None,
    merge_gap_s: float = 0.12,
    keep_span_indexes: Optional[Sequence[int]] = None,
    drop_span_indexes: Optional[Sequence[int]] = None,
    apply_removed_phrases: bool = True,
) -> Dict:
    """
    Convert transcript edits into timeline segments.

    Returns:
        {
            "segments": [{"start": 0.0, "end": 1.8}, ...],
            "duration_s": 13.4,
            "kept_span_count": 10
        }
    """
    normalized = normalize_spans(spans)
    phrase_set = {p.strip().lower() for p in (removed_phrases or []) if p and p.strip()}
    keep_set = {int(x) for x in (keep_span_indexes or []) if int(x) > 0}
    drop_set = {int(x) for x in (drop_span_indexes or []) if int(x) > 0}

    filtered: List[TranscriptSpan] = []
    decisions: List[Dict] = []
    removed_by_phrase = 0
    removed_by_selection = 0

    for idx, span in enumerate(normalized, start=1):
        text_lower = span.text.lower()
        reasons: List[str] = []
        keep = True

        if keep_set and idx not in keep_set:
            keep = False
            reasons.append("not_in_keep_set")

        if idx in drop_set:
            keep = False
            reasons.append("in_drop_set")

        if apply_removed_phrases and phrase_set and any(p in text_lower for p in phrase_set):
            keep = False
            reasons.append("contains_removed_phrase")

        if keep:
            filtered.append(span)
        else:
            if any(r in {"not_in_keep_set", "in_drop_set"} for r in reasons):
                removed_by_selection += 1
            if "contains_removed_phrase" in reasons:
                removed_by_phrase += 1

        decisions.append(
            {
                "index": idx,
                "start": round(float(span.start), 3),
                "end": round(float(span.end), 3),
                "text": span.text,
                "kept": keep,
                "reasons": reasons,
            }
        )

    segments = _merge_to_segments(filtered, max(float(merge_gap_s), 0.0))
    if target_duration_s is not None:
        segments = _trim_segments_to_duration(segments, max(float(target_duration_s), 0.1))

    duration = round(sum(seg["end"] - seg["start"] for seg in segments), 3)
    return {
        "segments": segments,
        "duration_s": duration,
        "total_span_count": len(normalized),
        "kept_span_count": len(filtered),
        "removed_by_phrase_count": removed_by_phrase,
        "removed_by_selection_count": removed_by_selection,
        "apply_removed_phrases": bool(apply_removed_phrases),
        "keep_span_indexes": sorted(keep_set),
        "drop_span_indexes": sorted(drop_set),
        "kept_spans": [asdict(span) for span in filtered],
        "decisions": decisions,
    }


def parse_span_index_expr(expr: str, max_index: Optional[int] = None) -> List[int]:
    """
    Parse span indexes/ranges from text, e.g. '1,2,5-8'.

    Non-numeric tokens are ignored.
    """
    raw = str(expr or "").strip()
    if not raw:
        return []
    raw = re.sub(r"[，；;、\s]+", ",", raw)
    out = set()
    for token in raw.split(","):
        part = token.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            try:
                start = int(left)
                end = int(right)
            except Exception:
                continue
            if start <= 0 and end <= 0:
                continue
            lo = max(min(start, end), 1)
            hi = max(start, end)
            if max_index is not None:
                hi = min(hi, int(max_index))
            if hi < lo:
                continue
            for i in range(lo, hi + 1):
                out.add(i)
            continue
        try:
            idx = int(part)
        except Exception:
            continue
        if idx <= 0:
            continue
        if max_index is not None and idx > int(max_index):
            continue
        out.add(idx)
    return sorted(out)


def coerce_span_indexes(value, max_index: Optional[int] = None) -> List[int]:
    """Coerce text/list payload to span index list."""
    if value is None:
        return []
    if isinstance(value, str):
        return parse_span_index_expr(value, max_index=max_index)
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            try:
                idx = int(item)
            except Exception:
                continue
            if idx <= 0:
                continue
            if max_index is not None and idx > int(max_index):
                continue
            out.append(idx)
        return sorted(set(out))
    return []


def _merge_to_segments(spans: Sequence[TranscriptSpan], merge_gap_s: float) -> List[Dict[str, float]]:
    if not spans:
        return []

    segments: List[Dict[str, float]] = []
    cur_start = spans[0].start
    cur_end = spans[0].end

    for span in spans[1:]:
        if span.start - cur_end <= merge_gap_s:
            cur_end = max(cur_end, span.end)
            continue
        segments.append({"start": round(cur_start, 3), "end": round(cur_end, 3)})
        cur_start = span.start
        cur_end = span.end

    segments.append({"start": round(cur_start, 3), "end": round(cur_end, 3)})
    return segments


def _trim_segments_to_duration(segments: Sequence[Dict[str, float]], target_duration_s: float) -> List[Dict[str, float]]:
    trimmed: List[Dict[str, float]] = []
    used = 0.0
    for seg in segments:
        seg_duration = max(float(seg["end"] - seg["start"]), 0.0)
        if used + seg_duration <= target_duration_s:
            trimmed.append({"start": seg["start"], "end": seg["end"]})
            used += seg_duration
            continue
        remaining = target_duration_s - used
        if remaining <= 0:
            break
        trimmed.append({"start": seg["start"], "end": round(seg["start"] + remaining, 3)})
        break
    return trimmed
