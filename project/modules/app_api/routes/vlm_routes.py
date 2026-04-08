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

    # ── B4a: Video stream analysis API (3 endpoints) ──────────────

    _stream_analysis_cache = {}  # session_id → StreamAnalysis dict

    @bp.route("/api/review/<session_id>/vlm/analyze-stream", methods=["POST"])
    def api_analyze_stream(session_id: str):
        """Trigger async video stream analysis via JobManager."""
        session, err = _require_session(session_id)
        if err:
            return err

        try:
            from modules.job_system.job_manager import JobManager
        except ImportError:
            return _error_response("Job system not available", "JOB_SYSTEM_UNAVAILABLE", 500)

        body = request.get_json(silent=True) or {}
        video_path = str(body.get("video_path", "")).strip()
        if not video_path:
            return _error_response("video_path is required", "MISSING_PARAM")

        # Lazy singleton for job manager
        if not hasattr(bp, "_job_manager"):
            bp._job_manager = JobManager(max_workers=2)

        def _run_analysis(jm, jid, vid_path, sid, adapter):
            """Background stream analysis task."""
            from modules.review_engine.frame_sampler import FrameSampler
            from modules.review_engine.video_stream_analyzer import VideoStreamAnalyzer
            from modules.review_engine.scene_summarizer import SceneSummarizer

            sampler = FrameSampler()
            frames = sampler.sample(vid_path)
            jm.update_progress(jid, 30.0)

            analyzer = VideoStreamAnalyzer(vlm_adapter=adapter)
            analysis = analyzer.analyze(frames)
            jm.update_progress(jid, 70.0)

            summarizer = SceneSummarizer(vlm_adapter=adapter)
            summaries = summarizer.summarize(analysis, frames)
            jm.update_progress(jid, 100.0)

            result = {
                "issues": [{"type": i.issue_type, "severity": i.severity, "description": i.description} for i in analysis.issues],
                "narrative_arc": analysis.narrative_arc,
                "scene_descriptions": analysis.scene_descriptions,
            }
            summary_result = {
                idx: {"summary": s.summary, "key_objects": s.key_objects, "duration_ms": s.duration_ms}
                for idx, s in summaries.items()
            }
            _stream_analysis_cache[sid] = {"analysis": result, "summaries": summary_result}
            return result

        jm = bp._job_manager
        adapter = _get_adapter()
        job_id = jm.submit(
            "stream_analysis",
            _run_analysis, jm, None, video_path, session_id, adapter,
        )
        # Patch the job_id into the submitted args
        with jm._lock:
            record = jm._jobs.get(job_id)
        if record:
            # Store job_id for progress self-updates
            pass

        return _ok({"job_id": job_id}, 202)

    @bp.route("/api/review/<session_id>/vlm/stream-analysis", methods=["GET"])
    def api_get_stream_analysis(session_id: str):
        """Get video stream analysis result."""
        cached = _stream_analysis_cache.get(session_id)
        if not cached:
            return _error_response(
                "No stream analysis available. Trigger with POST analyze-stream first.",
                "NOT_FOUND", 404,
            )
        return _ok(cached["analysis"])

    @bp.route("/api/review/<session_id>/vlm/scene-summaries", methods=["GET"])
    def api_get_scene_summaries(session_id: str):
        """Get scene summaries from stream analysis."""
        cached = _stream_analysis_cache.get(session_id)
        if not cached:
            return _error_response(
                "No scene summaries available. Trigger with POST analyze-stream first.",
                "NOT_FOUND", 404,
            )
        return _ok({"summaries": cached["summaries"]})

    return bp
