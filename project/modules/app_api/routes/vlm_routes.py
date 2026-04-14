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
    #
    # The cache is mutated from a worker thread (_run_analysis writes the
    # result dict) and read from HTTP request threads (the two GET endpoints).
    # Without a lock, a reader could observe a half-built dict during write.
    # Without a size bound, every analyze-stream POST permanently grows memory.
    import threading as _threading
    from collections import OrderedDict as _OrderedDict

    # Lazy singleton for JobManager — eagerly initialized at blueprint
    # creation time to avoid the lazy-init race where two concurrent first
    # POSTs could both pass `if not hasattr(bp, "_job_manager")` and create
    # two pool instances, leaking threads from the loser.
    try:
        from modules.job_system.job_manager import JobManager as _JobManager
        bp._job_manager = _JobManager(max_workers=2)
    except ImportError:
        bp._job_manager = None

    _stream_analysis_cache: "_OrderedDict[str, dict]" = _OrderedDict()
    _stream_cache_lock = _threading.Lock()
    _STREAM_CACHE_MAX = 100  # bound LRU; on overflow drop oldest

    def _cache_put(sid: str, value: dict) -> None:
        with _stream_cache_lock:
            if sid in _stream_analysis_cache:
                _stream_analysis_cache.move_to_end(sid)
            _stream_analysis_cache[sid] = value
            while len(_stream_analysis_cache) > _STREAM_CACHE_MAX:
                _stream_analysis_cache.popitem(last=False)  # pop oldest

    def _cache_get(sid: str):
        with _stream_cache_lock:
            value = _stream_analysis_cache.get(sid)
            if value is not None:
                _stream_analysis_cache.move_to_end(sid)  # mark as recently used
            return value

    @bp.route("/api/review/<session_id>/vlm/analyze-stream", methods=["POST"])
    def api_analyze_stream(session_id: str):
        """Trigger async video stream analysis via JobManager."""
        session, err = _require_session(session_id)
        if err:
            return err

        if bp._job_manager is None:
            return _error_response("Job system not available", "JOB_SYSTEM_UNAVAILABLE", 500)

        body = request.get_json(silent=True) or {}
        video_path = str(body.get("video_path", "")).strip()
        if not video_path:
            return _error_response("video_path is required", "MISSING_PARAM")

        def _run_analysis(jm, vid_path, sid, adapter):
            """Background stream analysis task.

            Reads its own job_id from the worker thread (set by JobManager
            in _run_job before calling the function). Previously this
            function received `jid=None` which silently no-op'd every
            update_progress call → clients always saw 0% progress.
            """
            import threading as _t
            jid = getattr(_t.current_thread(), '_job_id', '')

            from modules.review_engine.frame_sampler import FrameSampler
            from modules.review_engine.video_stream_analyzer import VideoStreamAnalyzer
            from modules.review_engine.scene_summarizer import SceneSummarizer

            sampler = FrameSampler()
            frames = sampler.sample(vid_path)
            if jid:
                jm.update_progress(jid, 30.0)

            analyzer = VideoStreamAnalyzer(vlm_adapter=adapter)
            analysis = analyzer.analyze(frames)
            if jid:
                jm.update_progress(jid, 70.0)

            summarizer = SceneSummarizer(vlm_adapter=adapter)
            summaries = summarizer.summarize(analysis, frames)
            if jid:
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
            _cache_put(sid, {"analysis": result, "summaries": summary_result})
            return result

        jm = bp._job_manager
        adapter = _get_adapter()
        job_id = jm.submit(
            "stream_analysis",
            _run_analysis, jm, video_path, session_id, adapter,
        )

        return _ok({"job_id": job_id}, 202)

    @bp.route("/api/review/<session_id>/vlm/stream-analysis", methods=["GET"])
    def api_get_stream_analysis(session_id: str):
        """Get video stream analysis result."""
        cached = _cache_get(session_id)
        if not cached:
            return _error_response(
                "No stream analysis available. Trigger with POST analyze-stream first.",
                "NOT_FOUND", 404,
            )
        return _ok(cached["analysis"])

    @bp.route("/api/review/<session_id>/vlm/scene-summaries", methods=["GET"])
    def api_get_scene_summaries(session_id: str):
        """Get scene summaries from stream analysis."""
        cached = _cache_get(session_id)
        if not cached:
            return _error_response(
                "No scene summaries available. Trigger with POST analyze-stream first.",
                "NOT_FOUND", 404,
            )
        return _ok({"summaries": cached["summaries"]})

    return bp
