"""VLM API routes — describe + diagnose endpoints (v0.17.0 R16).

POST /api/review/<id>/vlm/describe  — Analyze annotated region
POST /api/review/<id>/vlm/diagnose  — Run full-frame diagnostics (async)
GET  /api/review/<id>/vlm/diagnostics — Get diagnosis results
GET  /api/vlm/status                 — VLM availability status
"""

import base64
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


def _error_response(message, code, status=400):
    return jsonify({
        "success": False, "error": code, "message": message,
        "code": status, "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": uuid.uuid4().hex[:16],
    }), status


def _ok(data, status=200):
    return jsonify({"success": True, **data}), status


def create_vlm_blueprint(*, review_store_getter, vlm_adapter_getter):
    """Create VLM API blueprint.

    Args:
        review_store_getter: Callable that returns ReviewStore.
        vlm_adapter_getter: Callable that returns the active VLM adapter (or None).
    """
    bp = Blueprint("vlm_api", __name__)

    def _get_adapter():
        return vlm_adapter_getter()

    def _require_session(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return None, _error_response("Session not found", "SESSION_NOT_FOUND", 404)
        return session, None

    # POST /api/review/<id>/vlm/describe
    @bp.route("/api/review/<session_id>/vlm/describe", methods=["POST"])
    def describe_region(session_id):
        session, err = _require_session(session_id)
        if err:
            return err

        data = request.get_json(silent=True) or {}
        frame_b64 = data.get("frame_base64")
        strokes = data.get("strokes", [])
        timestamp_ms = data.get("timestamp_ms", 0)

        if not frame_b64:
            return _error_response("Missing frame_base64", "MISSING_FRAME")

        # Size check
        if len(frame_b64) > MAX_IMAGE_SIZE * 1.37:  # base64 overhead
            return _error_response(
                f"Image too large (max {MAX_IMAGE_SIZE // 1024 // 1024}MB)",
                "IMAGE_TOO_LARGE",
            )

        adapter = _get_adapter()
        if adapter is None:
            return _error_response("VLM not configured", "VLM_UNAVAILABLE", 503)

        try:
            from PIL import Image as PILImage

            img_bytes = base64.b64decode(frame_b64)
            frame = PILImage.open(io.BytesIO(img_bytes))
        except Exception as exc:
            return _error_response(f"Invalid image: {exc}", "INVALID_IMAGE")

        from modules.review_engine.region_extractor import RegionExtractor
        from modules.review_engine.vlm_analyzer import AnalysisContext, VLMAnalyzer

        extractor = RegionExtractor()
        extraction = extractor.extract(frame, strokes)

        analyzer = VLMAnalyzer(adapter=adapter)
        ctx = AnalysisContext(
            video_type=session.get("video_type", ""),
            timestamp_ms=timestamp_ms,
        )
        description = analyzer.describe_region(extraction.region_image, ctx)

        return _ok({
            "description": {
                "summary": description.summary,
                "objects": description.objects,
                "scene_type": description.scene_type,
                "visual_issues": description.visual_issues,
            },
            "bbox": list(extraction.bbox),
            "tool_type": extraction.tool_type,
        })

    # POST /api/review/<id>/vlm/diagnose
    @bp.route("/api/review/<session_id>/vlm/diagnose", methods=["POST"])
    def diagnose_frame(session_id):
        session, err = _require_session(session_id)
        if err:
            return err

        data = request.get_json(silent=True) or {}
        frame_b64 = data.get("frame_base64")

        if not frame_b64:
            return _error_response("Missing frame_base64", "MISSING_FRAME")

        adapter = _get_adapter()

        try:
            from PIL import Image as PILImage
            img_bytes = base64.b64decode(frame_b64)
            frame = PILImage.open(io.BytesIO(img_bytes))
        except Exception as exc:
            return _error_response(f"Invalid image: {exc}", "INVALID_IMAGE")

        from modules.review_engine.frame_diagnostics import FrameDiagnostics

        diag = FrameDiagnostics(vlm_adapter=adapter)
        issues = diag.diagnose_frame(frame)

        return _ok({
            "diagnostics": [
                {
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in issues
            ],
            "total_issues": len(issues),
        })

    # GET /api/review/<id>/vlm/diagnostics
    @bp.route("/api/review/<session_id>/vlm/diagnostics", methods=["GET"])
    def get_diagnostics(session_id):
        session, err = _require_session(session_id)
        if err:
            return err

        store = review_store_getter()
        ai_comments = store.list_comments(session_id, filter_ai=True)
        return _ok({
            "diagnostics": ai_comments,
            "total": len(ai_comments),
        })

    # GET /api/vlm/status
    @bp.route("/api/vlm/status", methods=["GET"])
    def vlm_status():
        adapter = _get_adapter()
        if adapter is None:
            return _ok({
                "available": False,
                "provider": None,
                "model": None,
            })

        info = adapter.get_model_info()
        return _ok({
            "available": info.get("available", False),
            "provider": info.get("provider", "unknown"),
            "model": info.get("model", "unknown"),
        })

    return bp
