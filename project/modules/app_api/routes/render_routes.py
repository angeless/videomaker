"""Render API routes — trigger / progress / cancel / download (D4a).

POST /api/review/{id}/render          — Trigger async render
GET  /api/review/{id}/render/progress — Query render progress
POST /api/review/{id}/render/cancel   — Cancel render
GET  /api/review/{id}/render/download — Download rendered file
"""

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file


def _error_response(message, code, status=400):
    return jsonify({
        "success": False, "error": code, "message": message,
        "code": status, "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": uuid.uuid4().hex[:16],
    }), status


def _ok(data, status=200):
    return jsonify({"success": True, **data}), status


def create_render_blueprint(*, timeline_store_getter, job_manager_getter, review_store_getter=None):
    """Create render API blueprint.

    Args:
        timeline_store_getter: Returns TimelineStore instance.
        job_manager_getter: Returns JobManager instance.
    """
    bp = Blueprint("render_api", __name__)

    # In-memory render state per session
    _render_state = {}  # session_id → {job_id, start_time, encoder, output_path}

    @bp.route("/api/review/<session_id>/render", methods=["POST"])
    def api_render_trigger(session_id: str):
        """Trigger async render. Returns 202 + job_id."""
        jm = job_manager_getter()
        if jm is None:
            return _error_response("Job manager not available", "JOB_UNAVAILABLE", 500)

        store = timeline_store_getter()
        timeline = store.get_timeline(session_id)
        if timeline is None:
            return _error_response("No timeline for session", "TIMELINE_NOT_FOUND", 404)

        body = request.get_json(silent=True) or {}

        # Determine the allowed output directory first (server-controlled)
        project_path = None
        if review_store_getter is not None:
            try:
                session_row = review_store_getter().get_session(session_id)
                if session_row:
                    project_path = session_row.get("project_path")
            except Exception:
                pass
        out_dir = Path(project_path) / "output" if project_path else Path.home() / "Movies" / "VideoEditor" / "output"
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        # If caller supplied a custom path, it MUST resolve inside out_dir (no traversal).
        if "output_path" in body:
            candidate = Path(str(body["output_path"])).expanduser().resolve()
            try:
                candidate.relative_to(out_dir)
            except ValueError:
                return _error_response(
                    f"output_path must be inside {out_dir}", "PATH_NOT_ALLOWED", 400
                )
            if candidate.suffix.lower() != ".mp4":
                return _error_response("output_path must end with .mp4", "PATH_INVALID", 400)
            output_path = str(candidate)
        else:
            output_path = str(out_dir / f"render_{session_id}.mp4")

        # Collect clips from all video tracks
        clips = []
        for track in timeline.tracks:
            if track.track_type == "video":
                clips.extend(track.clips)
        clips.sort(key=lambda c: c.start_ms)

        if not clips:
            return _error_response("No video clips to render", "NO_CLIPS")

        def _do_render(jm_ref, clips_list, out_path, sid):
            import threading
            jid = getattr(threading.current_thread(), '_job_id', '')
            from modules.hardware.detector import get_system_profile
            from modules.render_engine.render_manager import RenderManager

            profile = get_system_profile()
            manager = RenderManager(profile)

            def _progress(done, total):
                pct = (done / total) * 100.0 if total > 0 else 0
                if jid:
                    jm_ref.update_progress(jid, pct)

            result_path = manager.render_timeline(clips_list, out_path, progress_callback=_progress)
            _render_state[sid]["status"] = "done"
            _render_state[sid]["output_path"] = result_path
            return result_path

        # Get encoder label
        encoder_label = "libx264 (CPU)"
        try:
            from modules.hardware.detector import get_system_profile
            from modules.hardware.encoding_strategy import choose_encoder
            profile = get_system_profile()
            enc = choose_encoder(profile)
            encoder_label = enc.label
        except Exception:
            pass

        # Initialize state BEFORE submitting so the worker can't race past it
        # (if render completes extremely fast, setting state after submit could
        # overwrite the worker's status="done" with status="rendering").
        start_time = time.time()
        _render_state[session_id] = {
            "job_id": "",  # set after submit
            "start_time": start_time,
            "encoder": encoder_label,
            "output_path": output_path,
            "status": "rendering",
            "segments_total": len(clips),
        }
        job_id = jm.submit("render", _do_render, jm, clips, output_path, session_id)
        _render_state[session_id]["job_id"] = job_id

        return _ok({"job_id": job_id}, 202)

    @bp.route("/api/review/<session_id>/render/progress", methods=["GET"])
    def api_render_progress(session_id: str):
        """Query real-time render progress."""
        state = _render_state.get(session_id)
        if not state:
            return _error_response("No render in progress", "NOT_FOUND", 404)

        jm = job_manager_getter()
        job_status = jm.get_status(state["job_id"]) if jm else {}
        pct = job_status.get("progress_pct", 0.0)
        status = job_status.get("status", state["status"])
        elapsed = time.time() - state["start_time"]
        eta = (elapsed / pct * (100 - pct)) if pct > 0 else 0

        result = {
            "status": status,
            "segments_total": state["segments_total"],
            "segments_done": int(state["segments_total"] * pct / 100),
            "percent": round(pct, 1),
            "encoder": state["encoder"],
            "elapsed_s": round(elapsed, 1),
            "eta_s": round(eta, 1),
        }
        if status == "done":
            result["output_path"] = state.get("output_path", "")
        if status == "failed":
            result["error"] = job_status.get("error", "unknown error")
        return _ok(result)

    @bp.route("/api/review/<session_id>/render/cancel", methods=["POST"])
    def api_render_cancel(session_id: str):
        """Cancel an in-progress render."""
        state = _render_state.get(session_id)
        if not state:
            return _error_response("No render in progress", "NOT_FOUND", 404)

        jm = job_manager_getter()
        if jm is None:
            return _error_response("Job manager not available", "JOB_UNAVAILABLE", 500)

        cancelled = jm.cancel(state["job_id"])
        if cancelled:
            state["status"] = "cancelled"
            return _ok({"cancelled": True})
        return _error_response(
            "Cannot cancel — render may have already completed",
            "CANCEL_FAILED",
        )

    @bp.route("/api/review/<session_id>/render/download", methods=["GET"])
    def api_render_download(session_id: str):
        """Download the rendered output file."""
        state = _render_state.get(session_id)
        if not state:
            return _error_response("No render found for this session", "NOT_FOUND", 404)
        if state.get("status") != "done":
            return _error_response("Render not yet complete", "NOT_READY", 409)
        output_path = state.get("output_path", "")
        if not output_path or not os.path.isfile(output_path):
            return _error_response("Rendered file not found on disk", "FILE_MISSING", 404)
        # Double-check the resolved path is a .mp4 — defence in depth.
        if Path(output_path).suffix.lower() != ".mp4":
            return _error_response("Invalid output format", "PATH_INVALID", 403)
        filename = Path(output_path).name
        try:
            return send_file(output_path, as_attachment=True, download_name=filename, mimetype="video/mp4")
        except (FileNotFoundError, OSError) as exc:
            return _error_response(f"File read error: {exc}", "FILE_READ_ERROR", 500)

    return bp
