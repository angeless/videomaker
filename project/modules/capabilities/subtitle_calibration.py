"""Bilingual subtitle calibration with optional timeline alignment and translation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple
import math


Translator = Callable[[str, str], str]


@dataclass(frozen=True)
class SubtitleItem:
    """Normalized subtitle item."""

    index: int
    start_time: float
    end_time: float
    cn_text: str
    en_text: str


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _estimate_duration(text: str, fallback: float = 1.6) -> float:
    t = str(text or "").strip()
    if not t:
        return fallback
    # For mixed CJK/EN subtitles, a small deterministic estimate is enough for fallback.
    est = max(len(t) / 8.0, 0.6)
    return min(est, 8.0)


def _fallback_translate(text: str, target_lang: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if target_lang == "en":
        return f"[EN] {raw}"
    return f"[中] {raw}"


def _coerce_subtitles(subtitles: Iterable[Dict]) -> List[SubtitleItem]:
    out: List[SubtitleItem] = []
    cursor = 0.0
    for idx, item in enumerate(subtitles or [], start=1):
        if not isinstance(item, dict):
            continue
        cn_text = str(item.get("cn_text") or "").strip()
        en_text = str(item.get("en_text") or "").strip()
        text = str(item.get("text") or "").strip()
        if not cn_text and text:
            cn_text = text
        if not cn_text and not en_text:
            continue

        st = _safe_float(item.get("start_time"), cursor)
        et = _safe_float(item.get("end_time"), st + _estimate_duration(cn_text or en_text))
        if et <= st:
            et = st + _estimate_duration(cn_text or en_text)
        st = max(st, 0.0)
        et = max(et, st + 0.1)
        cursor = et

        out.append(
            SubtitleItem(
                index=idx,
                start_time=round(st, 3),
                end_time=round(et, 3),
                cn_text=cn_text,
                en_text=en_text,
            )
        )
    return out


def _count_overlaps(subs: List[SubtitleItem]) -> int:
    if len(subs) <= 1:
        return 0
    hits = 0
    prev_end = subs[0].end_time
    for it in subs[1:]:
        if it.start_time < prev_end:
            hits += 1
        prev_end = max(prev_end, it.end_time)
    return hits


def _align_timeline(subs: List[SubtitleItem]) -> Tuple[List[SubtitleItem], List[Dict]]:
    if not subs:
        return [], []
    aligned: List[SubtitleItem] = []
    changes: List[Dict] = []
    cursor = 0.0
    min_gap = 0.03
    for it in sorted(subs, key=lambda x: (x.start_time, x.end_time, x.index)):
        original_start = it.start_time
        original_end = it.end_time
        duration = max(original_end - original_start, 0.1)

        start = max(original_start, cursor)
        if start > original_start:
            reason = "resolve_overlap"
        else:
            reason = "keep"
        end = max(start + duration, start + 0.1)
        cursor = end + min_gap

        updated = SubtitleItem(
            index=it.index,
            start_time=round(start, 3),
            end_time=round(end, 3),
            cn_text=it.cn_text,
            en_text=it.en_text,
        )
        aligned.append(updated)
        if not math.isclose(updated.start_time, original_start, abs_tol=1e-3) or not math.isclose(
            updated.end_time, original_end, abs_tol=1e-3
        ):
            changes.append(
                {
                    "index": it.index,
                    "reason": reason,
                    "before": {"start_time": round(original_start, 3), "end_time": round(original_end, 3)},
                    "after": {"start_time": updated.start_time, "end_time": updated.end_time},
                }
            )
    return aligned, changes


def _apply_translation(
    subs: List[SubtitleItem],
    translation: str,
    translator: Optional[Translator],
) -> Tuple[List[SubtitleItem], List[Dict]]:
    if not subs:
        return [], []
    mode = str(translation or "off").strip().lower()
    if mode not in {"off", "zh2en", "en2zh", "bilingual"}:
        mode = "off"

    out: List[SubtitleItem] = []
    changes: List[Dict] = []
    for it in subs:
        cn = it.cn_text
        en = it.en_text
        before = {"cn_text": cn, "en_text": en}

        if mode == "zh2en" and cn and not en:
            en = translator(cn, "en") if callable(translator) else _fallback_translate(cn, "en")
        elif mode == "en2zh" and en and not cn:
            cn = translator(en, "zh") if callable(translator) else _fallback_translate(en, "zh")
        elif mode == "bilingual":
            if cn and not en:
                en = translator(cn, "en") if callable(translator) else _fallback_translate(cn, "en")
            elif en and not cn:
                cn = translator(en, "zh") if callable(translator) else _fallback_translate(en, "zh")

        updated = SubtitleItem(
            index=it.index,
            start_time=it.start_time,
            end_time=it.end_time,
            cn_text=cn,
            en_text=en,
        )
        out.append(updated)
        if cn != before["cn_text"] or en != before["en_text"]:
            changes.append(
                {
                    "index": it.index,
                    "reason": f"translation:{mode}",
                    "before": before,
                    "after": {"cn_text": cn, "en_text": en},
                }
            )
    return out, changes


def calibrate_subtitles(
    subtitles: Iterable[Dict],
    *,
    mode: str = "text_only",
    translation: str = "off",
    source_audio: str = "",
    translator: Optional[Translator] = None,
) -> Dict[str, object]:
    """
    Calibrate subtitle payload.

    `mode`:
      - `text_only`: keep original timeline unless invalid.
      - `timeline_align`: enforce monotonic timeline and resolve overlap.
    """
    normalized = _coerce_subtitles(subtitles)
    overlaps_before = _count_overlaps(normalized)
    timeline_changes: List[Dict] = []
    mode_norm = str(mode or "text_only").strip().lower()
    if mode_norm not in {"text_only", "timeline_align"}:
        mode_norm = "text_only"

    if mode_norm == "timeline_align":
        normalized, timeline_changes = _align_timeline(normalized)

    translated, text_changes = _apply_translation(normalized, translation=translation, translator=translator)
    overlaps_after = _count_overlaps(translated)

    calibrated = [
        {
            "index": it.index,
            "start_time": it.start_time,
            "end_time": it.end_time,
            "cn_text": it.cn_text,
            "en_text": it.en_text,
        }
        for it in translated
    ]
    durations = [max(float(x["end_time"]) - float(x["start_time"]), 0.0) for x in calibrated]
    avg_duration = round(sum(durations) / len(durations), 3) if durations else 0.0
    untranslated = 0
    for it in translated:
        if not it.cn_text or not it.en_text:
            untranslated += 1

    return {
        "mode": mode_norm,
        "translation": str(translation or "off").strip().lower() or "off",
        "source_audio": str(source_audio or "").strip(),
        "calibrated_subtitles": calibrated,
        "timeline_changes": timeline_changes,
        "text_changes": text_changes,
        "quality_report": {
            "total_subtitles": len(calibrated),
            "timeline_changed_count": len(timeline_changes),
            "text_changed_count": len(text_changes),
            "overlap_before": overlaps_before,
            "overlap_after": overlaps_after,
            "bilingual_incomplete_count": untranslated,
            "average_duration_s": avg_duration,
        },
    }

