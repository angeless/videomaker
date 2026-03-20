"""Timeline API route: compile project script + materials into a timeline view."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import Blueprint, jsonify


def create_timeline_blueprint(
    *,
    project_dir_getter: Callable[[], Optional[Path]],
    workflow_state_getter: Callable[[], Any],
) -> Blueprint:
    bp = Blueprint("timeline_api", __name__)

    def _read_json(project_dir: Path, name: str) -> Optional[dict]:
        p = project_dir / "data" / name
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _read_script(project_dir: Path) -> Optional[dict]:
        for name in ("script_matched.json", "script_draft.json"):
            data = _read_json(project_dir, name)
            if data and isinstance(data, dict):
                return data
        return None

    def _clip_processing_status(project_dir: Path, ws: Any) -> str:
        """Infer processing status from workflow state."""
        if ws is None:
            return "pending"
        current_step = 1
        try:
            current_step = int(ws.data.get("current_step", 1))
        except Exception:
            pass
        step7 = ws.get_step(7) if hasattr(ws, "get_step") else {}
        if isinstance(step7, dict) and step7.get("status") == "completed":
            return "rendered"
        if current_step >= 4:
            return "matched"
        return "pending"

    @bp.route("/api/timeline", methods=["GET"])
    def api_timeline():
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({"error": "no project"}), 400

        script = _read_script(project_dir)
        if not script:
            return jsonify({"ok": True, "timeline": None})

        materials = _read_json(project_dir, "materials.json") or {}
        ws = workflow_state_getter()
        config = ws.config if ws and hasattr(ws, "config") else {}

        clips_raw = script.get("clips", [])
        subtitles_raw = script.get("subtitles", [])
        transition_dur = float(config.get("transition_duration", 0.35) or 0.35)
        status = _clip_processing_status(project_dir, ws)

        # Build timeline clips with absolute positions
        timeline_clips: List[Dict[str, Any]] = []
        cursor = 0.0
        for i, clip in enumerate(clips_raw):
            if not isinstance(clip, dict):
                continue
            duration = float(clip.get("duration", 0) or 0)
            if duration <= 0:
                # Try to compute from source_start/source_end
                s_start = float(clip.get("source_start", 0) or 0)
                s_end = float(clip.get("source_end", 0) or 0)
                if s_end > s_start:
                    duration = s_end - s_start

            vid = str(clip.get("video_id", "") or "")
            mat = materials.get(vid, {}) if isinstance(materials, dict) else {}
            filename = str(mat.get("filename", "") or vid or "")

            tc = {
                "clip_index": clip.get("clip_index", i + 1),
                "video_id": vid,
                "filename": filename,
                "source_start": float(clip.get("source_start", 0) or 0),
                "source_end": float(clip.get("source_end", 0) or 0),
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
                "duration": round(duration, 3),
                "scene_description": str(clip.get("scene_description", "") or ""),
                "has_face": bool(clip.get("has_face", False)),
                "processing_status": status,
            }
            timeline_clips.append(tc)

            # Next clip: overlap by transition duration
            if i < len(clips_raw) - 1:
                cursor += max(0, duration - transition_dur)
            else:
                cursor += duration

        total_duration = round(cursor, 3)

        # Audio info
        bgm_path = str(config.get("bgm_path", "") or "").strip()
        narration_path = str(config.get("narration_path", "") or "").strip()
        audio = {
            "bgm": {
                "label": "BGM",
                "volume": float(config.get("bgm_volume", 0.35) or 0.35),
            } if bgm_path else None,
            "narration": {
                "label": "Narration",
            } if narration_path else None,
        }

        return jsonify({
            "ok": True,
            "timeline": {
                "total_duration": total_duration,
                "fps": int(config.get("fps", 30) or 30),
                "resolution": {
                    "width": int(config.get("width", 1080) or 1080),
                    "height": int(config.get("height", 1920) or 1920),
                },
                "transition": {
                    "style": str(config.get("transition_style", "fade") or "fade"),
                    "duration": transition_dur,
                },
                "clips": timeline_clips,
                "subtitles": [s for s in subtitles_raw if isinstance(s, dict)],
                "audio": audio,
            },
        })

    return bp
