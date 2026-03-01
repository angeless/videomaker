#!/usr/bin/env python3
"""Step6 rough cut builder."""

from pathlib import Path
from typing import Callable, Dict, List, Optional
import shutil
import subprocess
import tempfile

from modules.capabilities.short_clip import HighlightCandidate, pick_highlights
from modules.capabilities.text_rough_cut import TranscriptSpan, build_text_rough_cut_plan


def build_rough_cut(
    script: Dict,
    materials: Dict,
    rough_path: Path,
    ffmpeg: str,
    render_config: Dict,
    resolve_video_path: Callable[[str], Optional[str]],
    check_cancel: Optional[Callable[[], None]] = None,
    emit_progress: Optional[Callable[[float, str], None]] = None,
) -> Dict:
    """
    Build rough-cut preview from matched script clips.

    Returns:
        {
          "used_seconds": float,
          "segment_count": int,
          "strategy": str,
          "planned_segments": int,
          "segment_plan": [...]
        }
    """
    rough_path = Path(rough_path)
    rough_path.parent.mkdir(parents=True, exist_ok=True)

    def _check_cancel():
        if callable(check_cancel):
            check_cancel()

    def _emit(progress: float, message: str):
        if callable(emit_progress):
            emit_progress(progress, message)

    rc = render_config or {}
    crf = rc.get("crf_rough", 28)
    preset = rc.get("preset_rough", "ultrafast")
    fps = rc.get("fps", 30)
    w, h = rc.get("width", 1080), rc.get("height", 1920)
    budget = _to_float(rc.get("rough_target_seconds", 15.0), 15.0)

    tmp = Path(tempfile.mkdtemp(prefix="rough_"))
    segs = []
    used = 0.0
    plan = build_rough_segment_plan(script=script, render_config=rc)
    segment_plan = plan.get("segment_plan", [])

    try:
        for seg in segment_plan:
            _check_cancel()
            if used >= budget:
                break

            vid_id = seg.get("video_id")
            if not vid_id:
                continue

            vid_path = resolve_video_path(str(vid_id))
            if not vid_path:
                continue

            ss = _to_float(seg.get("source_start", 0), 0.0)
            se = _to_float(seg.get("source_end", ss + seg.get("duration", 3)), ss + 3.0)
            allot = min(se - ss, budget - used)
            if allot <= 0:
                continue
            seg_out = tmp / f"seg_{len(segs):03d}.mp4"

            vf = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}"
            )
            cmd = [
                ffmpeg,
                "-y",
                "-ss",
                str(ss),
                "-i",
                vid_path,
                "-t",
                str(allot),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-preset",
                preset,
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-pix_fmt",
                "yuv420p",
                str(seg_out),
            ]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=3600)
            except subprocess.TimeoutExpired:
                print(f"  ⚠️  粗剪片段编码超时，跳过")
                continue
            if r.returncode == 0:
                segs.append(str(seg_out))
                used += allot
                _emit(
                    20 + min(used / max(budget, 1.0), 1.0) * 10,
                    f"粗剪时长 {used:.1f}/{budget:.1f}s",
                )

        if not segs:
            raise RuntimeError("没有可用片段生成粗剪")

        concat_list = tmp / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p}'" for p in segs), encoding="utf-8")
        cmd2 = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(rough_path)]
        _check_cancel()
        subprocess.run(cmd2, capture_output=True, check=True, timeout=3600)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return {
        "used_seconds": round(used, 3),
        "segment_count": len(segs),
        "strategy": str(plan.get("strategy", "fallback")),
        "planned_segments": len(segment_plan),
        "segment_plan": segment_plan,
        "text_plan": plan.get("text_plan", {}),
        "highlight_plan": plan.get("highlight_plan", {}),
    }


def build_rough_segment_plan(script: Dict, render_config: Optional[Dict] = None) -> Dict:
    """
    Build rough-cut segment plan using:
    1) text-based rough cut from subtitles
    2) highlight selection from clip-level scoring
    """
    rc = render_config or {}
    budget = _to_float(rc.get("rough_target_seconds", 15.0), 15.0)
    max_clips = int(max(1, _to_float(rc.get("rough_max_clips", 8), 8)))
    min_gap_s = _to_float(rc.get("rough_min_gap_s", 0.25), 0.25)
    merge_gap_s = _to_float(rc.get("rough_merge_gap_s", 0.15), 0.15)
    removed_phrases = _normalize_removed_phrases(rc.get("rough_remove_phrases"))

    timeline_clips = _build_clip_timeline(script)
    if not timeline_clips:
        return {
            "strategy": "empty",
            "segment_plan": [],
            "text_plan": {},
            "highlight_plan": {"clips": [], "total_duration_s": 0.0},
        }

    highlights = pick_highlights(
        [
            HighlightCandidate(
                start=clip["timeline_start"],
                end=clip["timeline_end"],
                score=clip["score"],
                reason=clip.get("scene_description", ""),
            )
            for clip in timeline_clips
        ],
        target_duration_s=budget,
        max_clips=max_clips,
        min_gap_s=min_gap_s,
    )
    highlight_windows = [{"start": h.start, "end": h.end, "score": h.score} for h in highlights]
    highlight_plan = {
        "clips": highlight_windows,
        "total_duration_s": round(sum(max(h.end - h.start, 0.0) for h in highlights), 3),
    }

    spans: List[TranscriptSpan] = []
    for sub in script.get("subtitles", []):
        text = str(sub.get("cn_text") or sub.get("text") or "").strip()
        if not text:
            continue
        start = sub.get("start_time")
        end = sub.get("end_time")
        if start is None or end is None:
            continue
        try:
            st = float(start)
            et = float(end)
        except Exception:
            continue
        if et <= st:
            continue
        spans.append(TranscriptSpan(start=st, end=et, text=text, confidence=1.0))

    text_plan = build_text_rough_cut_plan(
        spans=spans,
        removed_phrases=removed_phrases,
        target_duration_s=budget,
        merge_gap_s=merge_gap_s,
    )
    text_windows = text_plan.get("segments", [])

    if highlight_windows and text_windows:
        combined = _intersect_windows(highlight_windows, text_windows, min_len_s=0.25)
        strategy = "text+highlight"
        if not combined:
            combined = _trim_windows(highlight_windows, budget)
            strategy = "highlight"
    elif highlight_windows:
        combined = _trim_windows(highlight_windows, budget)
        strategy = "highlight"
    else:
        combined = _trim_windows(text_windows, budget)
        strategy = "text"

    segment_plan = _map_windows_to_source(combined, timeline_clips, budget)
    return {
        "strategy": strategy if segment_plan else "fallback",
        "segment_plan": segment_plan,
        "text_plan": text_plan,
        "highlight_plan": highlight_plan,
        "budget_seconds": budget,
    }


def _build_clip_timeline(script: Dict) -> List[Dict]:
    timeline: List[Dict] = []
    cursor = 0.0
    subtitle_by_clip = {}
    for sub in script.get("subtitles", []):
        key = sub.get("clip_index")
        if key is None:
            continue
        subtitle_by_clip.setdefault(key, []).append(sub)

    for idx, clip in enumerate(script.get("clips", []), start=1):
        source_start = _to_float(clip.get("source_start", 0), 0.0)
        source_end = clip.get("source_end")
        if source_end is None:
            source_end = source_start + _to_float(clip.get("duration", 5), 5.0)
        source_end = _to_float(source_end, source_start + 5.0)
        duration = max(source_end - source_start, 0.1)
        t_start = cursor
        t_end = cursor + duration
        cursor = t_end

        clip_idx = clip.get("clip_index", idx)
        score = _estimate_clip_score(
            clip=clip,
            clip_order=idx,
            subtitle_lines=subtitle_by_clip.get(clip_idx, []),
        )

        timeline.append(
            {
                "clip_index": clip_idx,
                "video_id": clip.get("video_id"),
                "source_start": source_start,
                "source_end": source_end,
                "timeline_start": round(t_start, 3),
                "timeline_end": round(t_end, 3),
                "duration": round(duration, 3),
                "score": score,
                "scene_description": str(clip.get("scene_description", "") or ""),
            }
        )
    return timeline


def _estimate_clip_score(clip: Dict, clip_order: int, subtitle_lines: List[Dict]) -> float:
    score = _to_float(clip.get("highlight_score"), 0.0)
    if score <= 0:
        score = 0.55
    if clip_order == 1:
        score += 0.12
    if clip.get("has_face"):
        score += 0.08

    text_blob = " ".join(
        str(sub.get("cn_text") or sub.get("text") or "")
        for sub in subtitle_lines
    )
    if text_blob:
        if any(p in text_blob for p in ("！", "!", "?", "？")):
            score += 0.06
        if len(text_blob) <= 16:
            score += 0.04

    scene = str(clip.get("scene_description", "") or "")
    if any(k in scene for k in ("特写", "航拍", "夜景", "日出", "转场", "高光")):
        score += 0.05
    return round(min(max(score, 0.05), 1.5), 3)


def _normalize_removed_phrases(value) -> List[str]:
    default = ["嗯", "啊", "然后", "就是", "那个"]
    if value is None:
        return default
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
        return out or default
    text = str(value).strip()
    if not text:
        return default
    parts = [x.strip() for x in text.replace("，", ",").split(",") if x.strip()]
    return parts or default


def _intersect_windows(primary: List[Dict], secondary: List[Dict], min_len_s: float = 0.25) -> List[Dict]:
    out: List[Dict] = []
    for a in primary:
        a_start = _to_float(a.get("start"), 0.0)
        a_end = _to_float(a.get("end"), 0.0)
        if a_end <= a_start:
            continue
        for b in secondary:
            b_start = _to_float(b.get("start"), 0.0)
            b_end = _to_float(b.get("end"), 0.0)
            st = max(a_start, b_start)
            et = min(a_end, b_end)
            if et - st >= min_len_s:
                out.append({"start": round(st, 3), "end": round(et, 3), "score": _to_float(a.get("score"), 0.0)})
    out.sort(key=lambda x: x["start"])
    return _merge_adjacent(out, gap_s=0.08)


def _trim_windows(windows: List[Dict], budget: float) -> List[Dict]:
    out: List[Dict] = []
    used = 0.0
    for w in sorted(windows, key=lambda x: _to_float(x.get("start"), 0.0)):
        start = _to_float(w.get("start"), 0.0)
        end = _to_float(w.get("end"), start)
        if end <= start:
            continue
        duration = end - start
        if used + duration <= budget:
            out.append({"start": round(start, 3), "end": round(end, 3), "score": _to_float(w.get("score"), 0.0)})
            used += duration
            continue
        remaining = budget - used
        if remaining <= 0:
            break
        out.append({"start": round(start, 3), "end": round(start + remaining, 3), "score": _to_float(w.get("score"), 0.0)})
        break
    return out


def _merge_adjacent(windows: List[Dict], gap_s: float = 0.08) -> List[Dict]:
    if not windows:
        return []
    merged = [dict(windows[0])]
    for cur in windows[1:]:
        prev = merged[-1]
        if _to_float(cur.get("start"), 0.0) - _to_float(prev.get("end"), 0.0) <= gap_s:
            prev["end"] = round(max(_to_float(prev.get("end"), 0.0), _to_float(cur.get("end"), 0.0)), 3)
            prev["score"] = max(_to_float(prev.get("score"), 0.0), _to_float(cur.get("score"), 0.0))
        else:
            merged.append(dict(cur))
    return merged


def _map_windows_to_source(windows: List[Dict], timeline_clips: List[Dict], budget: float) -> List[Dict]:
    segments: List[Dict] = []
    used = 0.0
    for w in windows:
        w_start = _to_float(w.get("start"), 0.0)
        w_end = _to_float(w.get("end"), w_start)
        if w_end <= w_start:
            continue
        for clip in timeline_clips:
            c_start = clip["timeline_start"]
            c_end = clip["timeline_end"]
            st = max(w_start, c_start)
            et = min(w_end, c_end)
            if et <= st:
                continue

            duration = et - st
            if used + duration > budget:
                duration = budget - used
                if duration <= 0:
                    return segments
                et = st + duration

            source_start = clip["source_start"] + (st - c_start)
            source_end = source_start + duration
            segments.append(
                {
                    "video_id": clip.get("video_id"),
                    "clip_index": clip.get("clip_index"),
                    "timeline_start": round(st, 3),
                    "timeline_end": round(et, 3),
                    "source_start": round(source_start, 3),
                    "source_end": round(source_end, 3),
                    "duration": round(duration, 3),
                    "score": _to_float(w.get("score"), clip.get("score", 0.0)),
                    "scene_description": clip.get("scene_description", ""),
                }
            )
            used += duration
            if used >= budget:
                return segments
    return segments


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)
