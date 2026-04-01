"""Review API routes — sessions, comments, versions, thumbnails/waveform stubs.

Implements R26-R28 of dev-plan-v0.14.0.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from flask import Blueprint, jsonify, request

from modules.review_engine.exceptions import ReviewEngineError, ArtifactNotFoundError


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


def create_review_blueprint(
    *,
    review_store_getter: Callable,
    artifact_store_getter: Callable,
) -> Blueprint:
    """Create review API blueprint.

    Args:
        review_store_getter: Returns ReviewStore instance.
        artifact_store_getter: Returns ArtifactStore instance (or None).
    """
    bp = Blueprint("review_api", __name__)

    # ── R26: Sessions + Comments ──

    @bp.route("/api/review/init", methods=["POST"])
    def review_init():
        data = request.get_json(silent=True) or {}
        project_path = data.get("project_path")
        video_path = data.get("video_path")
        video_type = data.get("video_type")

        if not all([project_path, video_path, video_type]):
            return _error_response(
                "Missing required fields: project_path, video_path, video_type",
                "MISSING_FIELDS", 400,
            )

        store = review_store_getter()
        session_id = store.create_session(
            project_path=project_path,
            video_path=video_path,
            video_type=video_type,
            speech_ratio=float(data.get("speech_ratio", 0)),
        )
        return _ok({"session_id": session_id}, 201)

    @bp.route("/api/review/<session_id>/state", methods=["GET"])
    def review_state(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)
        return _ok({"session": dict(session)})

    @bp.route("/api/review/<session_id>/comments", methods=["GET"])
    def review_list_comments(session_id):
        store = review_store_getter()
        version = request.args.get("version", type=int)
        comments = store.list_comments(session_id, version=version)
        return _ok({"comments": comments})

    @bp.route("/api/review/<session_id>/comments", methods=["POST"])
    def review_add_comment(session_id):
        data = request.get_json(silent=True) or {}
        required = ["time_start_ms", "comment_type", "text"]
        missing = [f for f in required if f not in data]
        if missing:
            return _error_response(
                f"Missing fields: {', '.join(missing)}",
                "MISSING_FIELDS", 400,
            )

        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        comment_id = store.add_comment(
            session_id=session_id,
            version=int(data.get("version", session["current_version"])),
            time_start_ms=int(data["time_start_ms"]),
            comment_type=data["comment_type"],
            text=data["text"],
            time_end_ms=data.get("time_end_ms"),
            drawing_data=data.get("drawing_data"),
        )
        return _ok({"comment_id": comment_id}, 201)

    @bp.route("/api/review/comments/<comment_id>", methods=["PATCH"])
    def review_update_comment(comment_id):
        data = request.get_json(silent=True) or {}
        # Whitelist updatable fields at API boundary
        allowed = {"text", "comment_type", "status", "ai_reply", "resolved_in_version"}
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return _error_response("No valid fields to update", "MISSING_FIELDS", 400)

        store = review_store_getter()
        updated = store.update_comment(comment_id, **updates)
        if not updated:
            return _error_response(
                "Comment not found",
                "COMMENT_NOT_FOUND", 404,
            )
        return _ok({"updated": True})

    @bp.route("/api/review/comments/<comment_id>", methods=["DELETE"])
    def review_delete_comment(comment_id):
        store = review_store_getter()
        deleted = store.delete_comment(comment_id)
        if not deleted:
            return _error_response("Comment not found", "COMMENT_NOT_FOUND", 404)
        return _ok({"deleted": True})

    # ── R27: Versions + Diff + Rollback ──

    @bp.route("/api/review/<session_id>/versions", methods=["GET"])
    def review_list_versions(session_id):
        store = review_store_getter()
        versions = store.list_versions(session_id)
        return _ok({"versions": versions})

    @bp.route("/api/review/<session_id>/versions/<int:version_number>", methods=["GET"])
    def review_get_version(session_id, version_number):
        store = review_store_getter()
        version = store.get_version(session_id, version_number)
        if not version:
            return _error_response("Version not found", "VERSION_NOT_FOUND", 404)
        return _ok({"version": dict(version)})

    @bp.route("/api/review/<session_id>/diff/<int:v1>/<int:v2>", methods=["GET"])
    def review_diff(session_id, v1, v2):
        store = review_store_getter()
        diff = store.diff_versions(session_id, v1, v2)
        if "error" in diff:
            return _error_response(diff["error"], "DIFF_FAILED", 404)
        return _ok({"diff": diff})

    @bp.route("/api/review/<session_id>/rollback/<int:version_number>", methods=["POST"])
    def review_rollback(session_id, version_number):
        store = review_store_getter()
        try:
            new_version = store.rollback_to(session_id, version_number)
        except ReviewEngineError as e:
            return _error_response(str(e), "ROLLBACK_FAILED", 404)
        return _ok({"new_version": new_version})

    # ── R28: Thumbnails + Waveform ──

    @bp.route("/api/review/<session_id>/thumbnails", methods=["POST"])
    def review_generate_thumbnails(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        video_path = session.get("video_path")
        if not video_path:
            return _error_response("No video path in session", "MISSING_VIDEO", 400)

        try:
            from modules.review_engine.thumbnail_generator import generate_thumbnails
            import os
            output_dir = os.path.join(
                session.get("project_path", "/tmp"),
                "data", "review", session_id, "thumbnails",
            )
            result = generate_thumbnails(video_path, output_dir)
            return _ok({"thumbnails": result})
        except ReviewEngineError as e:
            return _error_response(str(e), "THUMBNAIL_FAILED", 500)

    @bp.route("/api/review/<session_id>/waveform", methods=["POST"])
    def review_generate_waveform(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        video_path = session.get("video_path")
        if not video_path:
            return _error_response("No video path in session", "MISSING_VIDEO", 400)

        try:
            from modules.review_engine.waveform_generator import generate_waveform
            import os
            output_dir = os.path.join(
                session.get("project_path", "/tmp"),
                "data", "review", session_id, "waveform",
            )
            result = generate_waveform(video_path, output_dir)
            return _ok({"waveform": result})
        except ReviewEngineError as e:
            return _error_response(str(e), "WAVEFORM_FAILED", 500)

    return bp
