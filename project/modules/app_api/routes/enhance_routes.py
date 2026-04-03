"""Enhance API routes — audio/tts/bgm/transition/reframe.

All enhancement operations are async (202 + job_id).
"""

import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)


def _error_response(message, code, status=400):
    return jsonify({
        "success": False, "error": code, "message": message,
        "code": status, "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": uuid.uuid4().hex[:16],
    }), status


def _ok(data, status=200):
    return jsonify({"success": True, **data}), status


def create_enhance_blueprint(*, review_store_getter, jobs_getter):
    bp = Blueprint("enhance_api", __name__)

    def _require_session(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return None, _error_response("Session not found", "SESSION_NOT_FOUND", 404)
        return session, None

    def _create_job(enhance_type, session_id, params):
        job_id = uuid.uuid4().hex[:8]
        jobs = jobs_getter()
        jobs[job_id] = {
            "type": f"enhance_{enhance_type}",
            "session_id": session_id,
            "params": params,
            "status": "queued",
        }
        return job_id

    @bp.route("/api/review/enhance/audio", methods=["POST"])
    def enhance_audio_endpoint():
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if not session_id:
            return _error_response("session_id required", "MISSING_PARAM", 400)

        session, err = _require_session(session_id)
        if err:
            return err

        job_id = _create_job("audio", session_id, {
            "denoise": data.get("denoise", True),
            "equalizer": data.get("equalizer", True),
            "compressor": data.get("compressor", True),
            "loudnorm": data.get("loudnorm", True),
        })
        return _ok({"job_id": job_id, "status": "queued"}, 202)

    @bp.route("/api/review/enhance/tts", methods=["POST"])
    def enhance_tts_endpoint():
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if not session_id:
            return _error_response("session_id required", "MISSING_PARAM", 400)

        session, err = _require_session(session_id)
        if err:
            return err

        job_id = _create_job("tts", session_id, {
            "voice": data.get("voice", "zh-female"),
            "segments": data.get("segments", []),
        })
        return _ok({"job_id": job_id, "status": "queued"}, 202)

    @bp.route("/api/review/enhance/bgm", methods=["POST"])
    def enhance_bgm_endpoint():
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if not session_id:
            return _error_response("session_id required", "MISSING_PARAM", 400)

        session, err = _require_session(session_id)
        if err:
            return err

        job_id = _create_job("bgm", session_id, {
            "bgm_path": data.get("bgm_path", ""),
            "volume_db": data.get("volume_db", -12.0),
            "beat_sync": data.get("beat_sync", False),
        })
        return _ok({"job_id": job_id, "status": "queued"}, 202)

    @bp.route("/api/review/enhance/transition", methods=["POST"])
    def enhance_transition_endpoint():
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if not session_id:
            return _error_response("session_id required", "MISSING_PARAM", 400)

        session, err = _require_session(session_id)
        if err:
            return err

        job_id = _create_job("transition", session_id, {
            "effect": data.get("effect", "cross_dissolve"),
            "duration_s": data.get("duration_s", 0.5),
            "positions": data.get("positions", []),
        })
        return _ok({"job_id": job_id, "status": "queued"}, 202)

    @bp.route("/api/review/enhance/reframe", methods=["POST"])
    def enhance_reframe_endpoint():
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if not session_id:
            return _error_response("session_id required", "MISSING_PARAM", 400)

        session, err = _require_session(session_id)
        if err:
            return err

        job_id = _create_job("reframe", session_id, {
            "platform": data.get("platform", "tiktok"),
        })
        return _ok({"job_id": job_id, "status": "queued"}, 202)

    return bp
