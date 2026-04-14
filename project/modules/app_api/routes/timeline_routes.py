"""Timeline API route: compile project script + materials into a timeline view.

Legacy endpoints (GET /api/timeline, etc.) use project_dir_getter.
Multi-track endpoints (C4: /api/review/{id}/timeline/*) use TimelineStore + TimelineOps.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import Blueprint, jsonify, request


def _error_response(message: str, error_code: str, status: int = 400):
    """Standardized error format per coding-standards §4.3."""
    return jsonify({
        "success": False,
        "error": error_code,
        "message": message,
        "code": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": uuid.uuid4().hex[:16],
    }), status


def _ok(data: dict, status: int = 200):
    return jsonify({"success": True, **data}), status


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
        transition_dur = max(0.0, min(float(config.get("transition_duration", 0.35) or 0.35), 5.0))
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
                "fps": max(1, min(int(config.get("fps", 30) or 30), 120)),
                "resolution": {
                    "width": max(1, min(int(config.get("width", 1080) or 1080), 7680)),
                    "height": max(1, min(int(config.get("height", 1920) or 1920), 7680)),
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

    @bp.route("/api/timeline/edit-by-prompt", methods=["POST"])
    def api_timeline_edit_by_prompt():
        """Apply a natural language editing command to the timeline."""
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({"error": "no project"}), 400

        body = request.get_json(silent=True) or {}
        prompt = str(body.get("prompt", "") or "").strip()
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400
        if len(prompt) > 500:
            return jsonify({"error": "prompt too long (max 500 chars)"}), 400

        script_path = project_dir / "data" / "script_matched.json"
        if not script_path.exists():
            return jsonify({"error": "script_matched.json not found"}), 404

        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception as e:
            return jsonify({"error": f"failed to read script: {e}"}), 500

        clips = script.get("clips", [])
        if not clips:
            return jsonify({"error": "no clips in timeline"}), 400

        from modules.prompt_editing import parse_edit_command, execute_edit_command

        command = parse_edit_command(prompt)
        if not command.valid:
            return jsonify({
                "ok": False,
                "error": "无法理解该编辑指令",
                "raw": prompt,
                "hint": "支持的指令：删除/移动/裁剪/倒序/加速减速 + 片段编号",
            }), 400

        new_clips, summary = execute_edit_command(clips, command)
        if "error" in summary:
            return jsonify({"ok": False, "error": summary["error"]}), 400

        # Persist
        script["clips"] = new_clips
        script_path.write_text(
            json.dumps(script, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return jsonify({
            "ok": True,
            "command": {
                "action": command.action,
                "targets": command.targets,
                "params": command.params,
            },
            "summary": summary,
            "clips_count": len(new_clips),
        })

    @bp.route("/api/timeline/reorder", methods=["POST"])
    def api_timeline_reorder():
        """Reorder clips in script_matched.json by new clip_index order."""
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({"error": "no project"}), 400

        body = request.get_json(silent=True) or {}
        new_order = body.get("order")
        if not isinstance(new_order, list) or not new_order:
            return jsonify({"error": "order must be a non-empty list of clip_index values"}), 400

        script_path = project_dir / "data" / "script_matched.json"
        if not script_path.exists():
            return jsonify({"error": "script_matched.json not found"}), 404

        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception as e:
            return jsonify({"error": f"failed to read script: {e}"}), 500

        clips = script.get("clips", [])
        if not clips:
            return jsonify({"error": "no clips in script"}), 400

        # Build index map: clip_index → clip dict
        by_index = {}
        for clip in clips:
            if isinstance(clip, dict):
                idx = clip.get("clip_index")
                if idx is not None:
                    by_index[idx] = clip

        # Validate all requested indices exist
        for idx in new_order:
            if idx not in by_index:
                return jsonify({"error": f"clip_index {idx} not found"}), 400

        # Reorder clips and reassign clip_index
        reordered = []
        for new_idx, old_idx in enumerate(new_order, start=1):
            clip = dict(by_index[old_idx])
            clip["clip_index"] = new_idx
            reordered.append(clip)

        script["clips"] = reordered
        script_path.write_text(
            json.dumps(script, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return jsonify({"ok": True, "reordered_count": len(reordered)})

    @bp.route("/api/timeline/trim", methods=["POST"])
    def api_timeline_trim():
        """Trim a clip's source_start/source_end in script_matched.json."""
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({"error": "no project"}), 400

        body = request.get_json(silent=True) or {}
        clip_index = body.get("clip_index")
        source_start = body.get("source_start")
        source_end = body.get("source_end")

        if clip_index is None:
            return jsonify({"error": "clip_index required"}), 400
        if source_start is None or source_end is None:
            return jsonify({"error": "source_start and source_end required"}), 400

        try:
            source_start = float(source_start)
            source_end = float(source_end)
        except (ValueError, TypeError):
            return jsonify({"error": "source_start/source_end must be numbers"}), 400

        if source_end <= source_start:
            return jsonify({"error": "source_end must be > source_start"}), 400

        script_path = project_dir / "data" / "script_matched.json"
        if not script_path.exists():
            return jsonify({"error": "script_matched.json not found"}), 404

        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception as e:
            return jsonify({"error": f"failed to read script: {e}"}), 500

        clips = script.get("clips", [])
        updated = False
        for clip in clips:
            if isinstance(clip, dict) and clip.get("clip_index") == clip_index:
                clip["source_start"] = round(source_start, 3)
                clip["source_end"] = round(source_end, 3)
                clip["duration"] = round(source_end - source_start, 3)
                updated = True
                break

        if not updated:
            return jsonify({"error": f"clip_index {clip_index} not found"}), 404

        script_path.write_text(
            json.dumps(script, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return jsonify({"ok": True})

    # ── R7: Three-track timeline (video/subtitle/audio) ─────────

    def _build_tracks(project_dir: Path) -> dict:
        """Build three-track structure from script + config (delegates to shared builder)."""
        from modules.exporters.track_builder import build_tracks_from_script
        script = _read_script(project_dir) or {}
        ws = workflow_state_getter()
        config = ws.config if ws and hasattr(ws, "config") else {}
        return build_tracks_from_script(script, config)

    @bp.route("/api/timeline/tracks", methods=["GET"])
    def api_timeline_tracks_get():
        """Return three-track timeline (video/subtitle/audio)."""
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({"error": "no project"}), 400
        tracks = _build_tracks(project_dir)
        return jsonify({"ok": True, "tracks": tracks})

    @bp.route("/api/timeline/tracks", methods=["PUT"])
    def api_timeline_tracks_put():
        """Save three-track timeline back to script file."""
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({"error": "no project"}), 400

        body = request.get_json(silent=True) or {}
        tracks = body.get("tracks")
        if not isinstance(tracks, dict):
            return jsonify({"error": "tracks must be an object with video/subtitle/audio"}), 400

        script_path = project_dir / "data" / "script_matched.json"
        if not script_path.exists():
            return jsonify({"error": "script_matched.json not found"}), 404

        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception as e:
            return jsonify({"error": f"failed to read script: {e}"}), 500

        MAX_MS = 86400000  # 24 hours

        def _clamp_ms(val: Any) -> int:
            try:
                v = int(val or 0)
            except (ValueError, TypeError):
                v = 0
            return max(0, min(v, MAX_MS))

        # Update clips from video track (duration + order by start_ms)
        video_items = tracks.get("video", [])
        if isinstance(video_items, list):
            clips = script.get("clips", [])
            clip_by_vid = {}
            for c in clips:
                if isinstance(c, dict):
                    clip_by_vid[str(c.get("video_id", ""))] = c
            for item in video_items:
                if not isinstance(item, dict):
                    continue
                uid = str(item.get("uid", ""))
                if uid in clip_by_vid:
                    start_ms = _clamp_ms(item.get("start_ms"))
                    end_ms = _clamp_ms(item.get("end_ms"))
                    if end_ms <= start_ms:
                        continue
                    dur_s = (end_ms - start_ms) / 1000.0
                    clip_by_vid[uid]["duration"] = round(dur_s, 3)
            # Persist clip order: sort by start_ms from frontend, reassign clip_index
            sorted_uids = [str(it.get("uid", "")) for it in sorted(
                [v for v in video_items if isinstance(v, dict)],
                key=lambda v: _clamp_ms(v.get("start_ms"))
            )]
            reordered = []
            for new_idx, uid in enumerate(sorted_uids, start=1):
                if uid in clip_by_vid:
                    clip = clip_by_vid[uid]
                    clip["clip_index"] = new_idx
                    reordered.append(clip)
            # Append any clips not in the video track (shouldn't happen, but defensive)
            seen = {str(c.get("video_id", "")) for c in reordered}
            for c in clips:
                if isinstance(c, dict) and str(c.get("video_id", "")) not in seen:
                    reordered.append(c)
            script["clips"] = reordered

        # Update subtitles
        sub_items = tracks.get("subtitle", [])
        if isinstance(sub_items, list):
            new_subs = []
            for item in sub_items:
                if not isinstance(item, dict):
                    continue
                start_ms = _clamp_ms(item.get("start_ms"))
                end_ms = _clamp_ms(item.get("end_ms"))
                if end_ms <= start_ms:
                    continue
                new_subs.append({
                    "cn_text": str(item.get("text", "")),
                    "en_text": "",
                    "start_time": round(start_ms / 1000.0, 3),
                    "end_time": round(end_ms / 1000.0, 3),
                })
            script["subtitles"] = new_subs

        # Persist audio track edits to workflow config
        audio_save_warning = ""
        audio_items = tracks.get("audio", [])
        if isinstance(audio_items, list):
            ws = workflow_state_getter()
            if ws and hasattr(ws, "data") and isinstance(ws.data.get("config"), dict):
                for item in audio_items:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("label", "")).strip().lower()
                    s = _clamp_ms(item.get("start_ms"))
                    e = _clamp_ms(item.get("end_ms"))
                    if e <= s:
                        continue
                    if label == "bgm":
                        ws.data["config"]["bgm_trim_start_ms"] = s
                        ws.data["config"]["bgm_trim_end_ms"] = e
                        if "volume" in item:
                            try:
                                vol = float(item["volume"])
                                ws.data["config"]["bgm_volume"] = round(max(0.0, min(vol, 2.0)), 2)
                            except (ValueError, TypeError):
                                pass
                    elif label == "narration":
                        ws.data["config"]["narration_trim_start_ms"] = s
                        ws.data["config"]["narration_trim_end_ms"] = e
                try:
                    ws.save()
                except Exception:
                    audio_save_warning = "音频配置保存失败，其他轨道已保存"

        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        resp = {"ok": True}
        if audio_save_warning:
            resp["audio_save_warning"] = audio_save_warning
        return jsonify(resp)

    # ── C4: Multi-track timeline CRUD (9 endpoints) ──────────────

    def _get_store():
        """Lazy-load TimelineStore.

        Reads db_path from env VIDEOEDITOR_TIMELINE_DB, falling back to
        project_dir/data/review.db if a project is open.
        """
        from modules.review_engine.timeline_store import TimelineStore
        db_path = os.environ.get("VIDEOEDITOR_TIMELINE_DB")
        if not db_path:
            pdir = project_dir_getter()
            if pdir:
                db_path = str(pdir / "data" / "review.db")
            else:
                db_path = "data/review.db"
        return TimelineStore(db_path)

    def _get_ops():
        """Lazy-load TimelineOps."""
        from modules.review_engine.timeline_ops import TimelineOps
        return TimelineOps(_get_store())

    @bp.route("/api/review/<session_id>/timeline", methods=["POST"])
    def api_multitrack_create(session_id: str):
        """Create or ensure a multi-track timeline for a review session.

        Uses session_id as timeline_id (1:1 mapping). Idempotent —
        returns existing timeline_id if tracks already exist.
        """
        store = _get_store()
        existing = store.get_timeline(session_id)
        if existing is not None:
            return _ok({"timeline_id": existing.timeline_id}, 200)
        timeline_id = store.create_timeline(session_id)
        return _ok({"timeline_id": timeline_id}, 201)

    @bp.route("/api/review/<session_id>/timeline", methods=["GET"])
    def api_multitrack_get(session_id: str):
        """Get the full multi-track timeline (nested: tracks → clips)."""
        store = _get_store()
        timeline = store.get_timeline(session_id)
        if timeline is None:
            return _error_response(
                f"No timeline for session {session_id}",
                "TIMELINE_NOT_FOUND", 404,
            )
        # Serialize to nested dict
        tracks_out = []
        for t in timeline.tracks:
            clips_out = [
                {
                    "clip_id": c.clip_id,
                    "track_id": c.track_id,
                    "start_ms": c.start_ms,
                    "end_ms": c.end_ms,
                    "source_path": c.source_path,
                    "source_in_ms": c.source_in_ms,
                    "source_out_ms": c.source_out_ms,
                    "label": c.label,
                }
                for c in t.clips
            ]
            tracks_out.append({
                "track_id": t.track_id,
                "track_type": t.track_type,
                "label": t.label,
                "sort_order": t.sort_order,
                "muted": t.muted,
                "locked": t.locked,
                "volume": t.volume,
                "clips": clips_out,
            })
        return _ok({
            "timeline_id": timeline.timeline_id,
            "session_id": session_id,
            "duration_ms": timeline.duration_ms,
            "tracks": tracks_out,
        })

    @bp.route("/api/review/<session_id>/timeline/tracks", methods=["POST"])
    def api_multitrack_add_track(session_id: str):
        """Add a track to the timeline (auto-creates timeline if needed)."""
        store = _get_store()
        ops = _get_ops()
        timeline = store.get_timeline(session_id)
        timeline_id = timeline.timeline_id if timeline else store.create_timeline(session_id)
        body = request.get_json(silent=True) or {}
        track_type = str(body.get("track_type", "")).strip()
        label = str(body.get("label", "")).strip()
        if not track_type:
            return _error_response("track_type is required", "MISSING_PARAM")
        try:
            track_id = ops.add_track(timeline_id, session_id, track_type, label)
        except ValueError as e:
            return _error_response(str(e), "TRACK_LIMIT_EXCEEDED")
        return _ok({"track_id": track_id}, 201)

    @bp.route("/api/review/<session_id>/timeline/tracks/<track_id>", methods=["PATCH"])
    def api_multitrack_update_track(session_id: str, track_id: str):
        """Update a track's properties (label, muted, locked, volume)."""
        store = _get_store()
        body = request.get_json(silent=True) or {}
        allowed_keys = {"label", "sort_order", "muted", "locked", "volume"}
        updates = {k: v for k, v in body.items() if k in allowed_keys}
        if not updates:
            return _error_response("No valid fields to update", "NO_UPDATES")
        ok = store.update_track(track_id, **updates)
        if not ok:
            return _error_response(f"Track {track_id} not found", "TRACK_NOT_FOUND", 404)
        return _ok({"updated": True})

    @bp.route("/api/review/<session_id>/timeline/tracks/<track_id>", methods=["DELETE"])
    def api_multitrack_delete_track(session_id: str, track_id: str):
        """Delete a track and all its clips. Fails if locked."""
        from modules.review_engine.exceptions import LockedTrackError
        ops = _get_ops()
        try:
            removed = ops.remove_track(track_id, session_id)
        except LockedTrackError:
            return _error_response(
                f"Track {track_id} is locked", "TRACK_LOCKED", 403,
            )
        if not removed:
            return _error_response(f"Track {track_id} not found", "TRACK_NOT_FOUND", 404)
        return _ok({"deleted": True})

    @bp.route("/api/review/<session_id>/timeline/clips", methods=["POST"])
    def api_multitrack_add_clip(session_id: str):
        """Add a clip to a track. Enforces locked-track + video-overlap invariants."""
        from modules.review_engine.exceptions import LockedTrackError, OverlapError
        ops = _get_ops()
        body = request.get_json(silent=True) or {}
        track_id = str(body.get("track_id", "")).strip()
        start_ms = body.get("start_ms")
        end_ms = body.get("end_ms")

        if not track_id or start_ms is None or end_ms is None:
            return _error_response("track_id, start_ms, end_ms are required", "MISSING_PARAM")
        try:
            start_ms = int(start_ms)
            end_ms = int(end_ms)
        except (ValueError, TypeError):
            return _error_response("start_ms/end_ms must be integers", "INVALID_PARAM")

        # Default source_out_ms to clip duration so render segments are not zero-length
        source_in_ms = int(body.get("source_in_ms", 0))
        source_out_ms = body.get("source_out_ms")
        if source_out_ms is not None:
            source_out_ms = int(source_out_ms)

        try:
            clip_id = ops.add_clip(
                track_id=track_id,
                session_id=session_id,
                start_ms=start_ms,
                end_ms=end_ms,
                source_path=str(body.get("source_path", "")),
                source_in_ms=source_in_ms,
                source_out_ms=source_out_ms,
                label=str(body.get("label", "")),
            )
        except ValueError as exc:
            # Track-not-found is the only ValueError raised here
            return _error_response(str(exc), "TRACK_NOT_FOUND", 404)
        except LockedTrackError:
            return _error_response(f"Track {track_id} is locked", "TRACK_LOCKED", 403)
        except OverlapError as exc:
            return _error_response(str(exc), "CLIP_OVERLAP", 409)
        return _ok({"clip_id": clip_id}, 201)

    @bp.route("/api/review/<session_id>/timeline/clips/<clip_id>", methods=["PATCH"])
    def api_multitrack_update_clip(session_id: str, clip_id: str):
        """Update a clip's properties. Fails if clip is on a locked track."""
        from modules.review_engine.exceptions import LockedTrackError
        ops = _get_ops()
        store = _get_store()
        body = request.get_json(silent=True) or {}
        allowed = {"start_ms", "end_ms", "source_path", "source_in_ms", "source_out_ms", "label", "track_id"}
        updates = {k: v for k, v in body.items() if k in allowed}
        if not updates:
            return _error_response("No valid fields to update", "NO_UPDATES")
        # Enforce locked-track constraint before any mutation
        try:
            ops._assert_clip_not_on_locked_track(clip_id, session_id)
        except LockedTrackError as e:
            return _error_response(str(e), "TRACK_LOCKED", 403)
        ok = store.update_clip(clip_id, **updates)
        if not ok:
            return _error_response(f"Clip {clip_id} not found", "CLIP_NOT_FOUND", 404)
        return _ok({"updated": True})

    @bp.route("/api/review/<session_id>/timeline/clips/<clip_id>", methods=["DELETE"])
    def api_multitrack_delete_clip(session_id: str, clip_id: str):
        """Delete a clip. Fails if clip is on a locked track."""
        from modules.review_engine.exceptions import LockedTrackError
        ops = _get_ops()
        try:
            removed = ops.remove_clip(clip_id, session_id)
        except LockedTrackError as e:
            return _error_response(str(e), "TRACK_LOCKED", 403)
        if not removed:
            return _error_response(f"Clip {clip_id} not found", "CLIP_NOT_FOUND", 404)
        return _ok({"deleted": True})

    @bp.route("/api/review/<session_id>/timeline/clips/<clip_id>/split", methods=["POST"])
    def api_multitrack_split_clip(session_id: str, clip_id: str):
        """Split a clip at a given timestamp. Returns IDs of the two new clips."""
        from modules.review_engine.exceptions import LockedTrackError
        ops = _get_ops()
        body = request.get_json(silent=True) or {}
        at_ms = body.get("at_ms")
        if at_ms is None:
            return _error_response("at_ms is required", "MISSING_PARAM")
        try:
            at_ms = int(at_ms)
        except (ValueError, TypeError):
            return _error_response("at_ms must be an integer", "INVALID_PARAM")
        try:
            left_id, right_id = ops.split_clip(clip_id, at_ms, session_id)
        except LockedTrackError:
            return _error_response("Clip is on a locked track", "TRACK_LOCKED", 403)
        except ValueError as e:
            return _error_response(str(e), "SPLIT_ERROR")
        return _ok({"left_clip_id": left_id, "right_clip_id": right_id})

    return bp
