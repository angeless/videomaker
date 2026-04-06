"""Shared track-building logic — converts script + config into three-track structure.

Used by timeline_routes, jianying export, and FCPXML export.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_tracks_from_script(
    script: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Build {video, subtitle, audio} tracks from script_matched.json + workflow config.

    Returns dict with keys "video", "subtitle", "audio", each a list of dicts.
    """
    clips_raw = script.get("clips", [])
    subs_raw = script.get("subtitles", [])
    transition_dur = max(0.0, min(float(config.get("transition_duration", 0.35) or 0.35), 5.0))

    # Video track
    video_track: List[Dict[str, Any]] = []
    cursor = 0.0
    for i, clip in enumerate(clips_raw):
        if not isinstance(clip, dict):
            continue
        duration = float(clip.get("duration", 0) or 0)
        if duration <= 0:
            s_start = float(clip.get("source_start", 0) or 0)
            s_end = float(clip.get("source_end", 0) or 0)
            if s_end > s_start:
                duration = s_end - s_start
        uid = str(clip.get("video_id", "") or "")
        start_ms = round(cursor * 1000)
        end_ms = round((cursor + duration) * 1000)
        video_track.append({
            "uid": uid,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "label": str(clip.get("scene_description", "") or f"clip_{i+1}"),
            "path": str(clip.get("video_path", "") or ""),
        })
        if i < len(clips_raw) - 1:
            cursor += max(0, duration - transition_dur)
        else:
            cursor += duration

    # Subtitle track
    subtitle_track: List[Dict[str, Any]] = []
    for sub in subs_raw:
        if not isinstance(sub, dict):
            continue
        start = float(sub.get("start_time", 0) or 0)
        end = float(sub.get("end_time", 0) or 0)
        text = str(sub.get("cn_text", "") or sub.get("text", "") or sub.get("en_text", "") or "")
        if end > start:
            subtitle_track.append({
                "text": text,
                "start_ms": round(start * 1000),
                "end_ms": round(end * 1000),
            })

    # Audio track
    audio_track: List[Dict[str, Any]] = []
    total_ms = round(cursor * 1000)
    bgm_path = str(config.get("bgm_path", "") or "").strip()
    narration_path = str(config.get("narration_path", "") or "").strip()
    if bgm_path:
        audio_track.append({
            "label": "BGM",
            "start_ms": 0,
            "end_ms": total_ms,
            "volume": float(config.get("bgm_volume", 0.35) or 0.35),
        })
    if narration_path:
        audio_track.append({
            "label": "Narration",
            "start_ms": 0,
            "end_ms": total_ms,
            "volume": 1.0,
        })

    result = {
        "video": video_track,
        "subtitle": subtitle_track,
        "audio": audio_track,
    }

    # C5: Multi-track extensions — extra tracks from config
    extra_audio = config.get("extra_audio_tracks", [])
    if extra_audio and isinstance(extra_audio, list):
        for i, ea in enumerate(extra_audio):
            if isinstance(ea, dict):
                result[f"audio_{i+2}"] = [{
                    "label": str(ea.get("label", f"Audio {i+2}")),
                    "start_ms": int(ea.get("start_ms", 0)),
                    "end_ms": int(ea.get("end_ms", total_ms)),
                    "volume": float(ea.get("volume", 1.0)),
                    "path": str(ea.get("path", "")),
                }]

    extra_video = config.get("extra_video_tracks", [])
    if extra_video and isinstance(extra_video, list):
        for i, ev in enumerate(extra_video):
            if isinstance(ev, dict):
                result[f"video_{i+2}"] = [{
                    "label": str(ev.get("label", f"PiP {i+1}")),
                    "start_ms": int(ev.get("start_ms", 0)),
                    "end_ms": int(ev.get("end_ms", total_ms)),
                    "path": str(ev.get("path", "")),
                }]

    return result
