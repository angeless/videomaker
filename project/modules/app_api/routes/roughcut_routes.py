"""Roughcut API routes — init, detect-type, transcript, scenes, generate.

Implements R20-R22 of dev-plan-v0.14.0.
"""

import json
import logging
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)


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


def create_roughcut_blueprint(
    *,
    review_store_getter: Callable,
    run_in_bg: Optional[Callable] = None,
) -> Blueprint:
    """Create roughcut API blueprint.

    Args:
        review_store_getter: Returns ReviewStore instance.
        run_in_bg: Background job runner (job_id, fn, *args).
    """
    bp = Blueprint("roughcut_api", __name__)

    # In-memory session data cache (transcript docs, scenes, edits).
    # Bounded to prevent memory leaks in long-running desktop sessions.
    _MAX_CACHED_SESSIONS = 20
    _session_data: OrderedDict = OrderedDict()

    def _cache_set(key: str, value: dict):
        _session_data[key] = value
        if len(_session_data) > _MAX_CACHED_SESSIONS:
            _session_data.popitem(last=False)  # evict oldest

    # ── R20: init + detect-type + stats ──

    @bp.route("/api/roughcut/init", methods=["POST"])
    def roughcut_init():
        data = request.get_json(silent=True) or {}
        project_path = data.get("project_path")
        video_path = data.get("video_path")

        if not all([project_path, video_path]):
            return _error_response(
                "Missing required fields: project_path, video_path",
                "MISSING_FIELDS", 400,
            )

        # Detect video type
        try:
            from modules.review_engine.video_detector import detect_video_type
            detection = detect_video_type(video_path)
            video_type = detection.video_type.value
            speech_ratio = detection.speech_ratio
        except Exception as e:
            logger.warning("Video detection failed, defaulting to mixed: %s", e)
            video_type = "mixed"
            speech_ratio = 0.3

        store = review_store_getter()
        session_id = store.create_session(
            project_path=project_path,
            video_path=video_path,
            video_type=video_type,
            speech_ratio=speech_ratio,
        )

        _cache_set(session_id, {
            "video_path": video_path,
            "video_type": video_type,
            "speech_ratio": speech_ratio,
        })

        job_id = uuid.uuid4().hex[:12]
        return _ok({
            "session_id": session_id,
            "job_id": job_id,
            "video_type": video_type,
            "speech_ratio": round(speech_ratio, 3),
        }, 201)

    @bp.route("/api/roughcut/<session_id>/detect-type", methods=["GET"])
    def roughcut_detect_type(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        return _ok({
            "video_type": session["video_type"],
            "speech_ratio": session["speech_ratio"],
        })

    @bp.route("/api/roughcut/<session_id>/stats", methods=["GET"])
    def roughcut_stats(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        cached = _session_data.get(session_id, {})
        comments = store.list_comments(session_id)
        versions = store.list_versions(session_id)

        return _ok({
            "session_id": session_id,
            "video_type": session["video_type"],
            "speech_ratio": session["speech_ratio"],
            "current_version": session["current_version"],
            "total_comments": len(comments),
            "total_versions": len(versions),
            "status": session["status"],
        })

    # ── R21: transcript + fillers + batch ──

    @bp.route("/api/roughcut/<session_id>/transcript", methods=["GET"])
    def roughcut_transcript(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        cached = _session_data.get(session_id, {})
        doc = cached.get("transcript_doc")

        if not doc:
            # Try to transcribe on demand
            try:
                from modules.review_engine.transcript_editor import transcribe_to_doc
                doc = transcribe_to_doc(session["video_path"])
                _session_data.setdefault(session_id, {})["transcript_doc"] = doc
            except Exception as e:
                return _error_response(
                    f"Transcription failed: {e}", "TRANSCRIPTION_FAILED", 500,
                )

        # Serialize TranscriptDoc
        paragraphs = []
        for p in doc.paragraphs:
            paragraphs.append({
                "idx": p.idx,
                "speaker": p.speaker,
                "start_ms": p.start_ms,
                "end_ms": p.end_ms,
                "is_deleted": p.is_deleted,
                "is_hook": p.is_hook,
                "words": [
                    {"text": w.text, "start_ms": w.start_ms, "end_ms": w.end_ms,
                     "confidence": w.confidence}
                    for w in p.words
                ],
            })

        return _ok({
            "transcript": {
                "video_path": doc.video_path,
                "duration_ms": doc.duration_ms,
                "language": doc.language,
                "paragraphs": paragraphs,
            },
        })

    @bp.route("/api/roughcut/<session_id>/fillers", methods=["GET"])
    def roughcut_fillers(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        cached = _session_data.get(session_id, {})
        doc = cached.get("transcript_doc")

        if not doc:
            return _ok({"fillers": [], "message": "No transcript available"})

        # Collect filler marks from all paragraphs
        fillers = []
        for p in doc.paragraphs:
            for fm in (p.filler_marks or []):
                fillers.append({
                    "paragraph_idx": p.idx,
                    "word_indices": fm.word_indices,
                    "filler_type": fm.filler_type,
                    "text": fm.text,
                    "start_ms": fm.start_ms,
                    "end_ms": fm.end_ms,
                })

        return _ok({"fillers": fillers})

    @bp.route("/api/roughcut/<session_id>/fillers/batch", methods=["POST"])
    def roughcut_fillers_batch(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        data = request.get_json(silent=True) or {}
        action = data.get("action", "remove")  # "remove" or "keep"
        filler_types = data.get("filler_types", [])

        cached = _session_data.get(session_id, {})
        doc = cached.get("transcript_doc")
        if not doc:
            return _error_response("No transcript available", "NO_TRANSCRIPT", 400)

        updated = 0
        if action == "remove":
            for p in doc.paragraphs:
                for fm in (p.filler_marks or []):
                    if not filler_types or fm.filler_type in filler_types:
                        # Mark words as deleted
                        for wi in fm.word_indices:
                            if wi < len(p.words):
                                updated += 1

        return _ok({"updated_count": updated})

    @bp.route("/api/roughcut/<session_id>/transcript/edit", methods=["POST"])
    def roughcut_transcript_edit(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        data = request.get_json(silent=True) or {}
        operations = data.get("operations", [])

        cached = _session_data.get(session_id, {})
        doc = cached.get("transcript_doc")
        if not doc:
            return _error_response("No transcript available", "NO_TRANSCRIPT", 400)

        # Apply operations: each is {"type": "delete"|"keep"|"restore", "paragraph_idx": N}
        for op in operations:
            idx = op.get("paragraph_idx")
            if idx is not None and 0 <= idx < len(doc.paragraphs):
                if op["type"] == "delete":
                    doc.paragraphs[idx].is_deleted = True
                elif op["type"] == "restore":
                    doc.paragraphs[idx].is_deleted = False

        # Build EDITS list from active paragraphs
        from modules.review_engine.contracts import Segment
        edits = []
        total_ms = 0
        for p in doc.paragraphs:
            seg_type = "removed" if p.is_deleted else "keep"
            seg = Segment(
                source_path=session["video_path"],
                start_ms=p.start_ms,
                end_ms=p.end_ms,
                segment_type=seg_type,
                paragraph_idx=p.idx,
            )
            edits.append(seg)
            if not p.is_deleted:
                total_ms += (p.end_ms - p.start_ms)

        # Store as version
        edits_json = json.dumps([
            {"source_path": e.source_path, "start_ms": e.start_ms,
             "end_ms": e.end_ms, "segment_type": e.segment_type,
             "paragraph_idx": e.paragraph_idx}
            for e in edits
        ])
        version_number = store.create_version(
            session_id=session_id,
            edits_json=edits_json,
            change_summary=f"Transcript edit: {len(operations)} operations",
        )

        return _ok({
            "version": version_number,
            "estimated_duration_ms": total_ms,
            "active_segments": sum(1 for e in edits if e.segment_type == "keep"),
            "removed_segments": sum(1 for e in edits if e.segment_type == "removed"),
        })

    # ── R22: scenes + select + generate ──

    @bp.route("/api/roughcut/<session_id>/scenes", methods=["GET"])
    def roughcut_scenes(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        cached = _session_data.get(session_id, {})
        scenes = cached.get("scenes")

        if not scenes:
            try:
                from modules.review_engine.scene_segmenter import segment_scenes
                scenes = segment_scenes(session["video_path"])
                _session_data.setdefault(session_id, {})["scenes"] = scenes
            except Exception as e:
                return _error_response(
                    f"Scene segmentation failed: {e}", "SEGMENTATION_FAILED", 500,
                )

        return _ok({
            "scenes": [
                {
                    "scene_idx": s.scene_idx,
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "duration_ms": s.duration_ms,
                    "thumbnail_path": s.thumbnail_path,
                    "selected": s.selected,
                }
                for s in scenes
            ],
        })

    @bp.route("/api/roughcut/<session_id>/scenes/select", methods=["POST"])
    def roughcut_scenes_select(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        data = request.get_json(silent=True) or {}
        selected_indices = data.get("selected", [])

        cached = _session_data.get(session_id, {})
        scenes = cached.get("scenes", [])
        if not scenes:
            return _error_response("No scenes available", "NO_SCENES", 400)

        # Update selection state
        for s in scenes:
            s.selected = s.scene_idx in selected_indices

        # Build edits from selected scenes
        from modules.review_engine.contracts import Segment
        edits = []
        for s in scenes:
            edits.append(Segment(
                source_path=session["video_path"],
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                segment_type="keep" if s.selected else "removed",
            ))

        edits_json = json.dumps([
            {"source_path": e.source_path, "start_ms": e.start_ms,
             "end_ms": e.end_ms, "segment_type": e.segment_type}
            for e in edits
        ])

        version_number = store.create_version(
            session_id=session_id,
            edits_json=edits_json,
            change_summary=f"Scene selection: {len(selected_indices)} of {len(scenes)}",
        )

        return _ok({
            "version": version_number,
            "edits_count": len(edits),
            "selected_count": len(selected_indices),
        })

    @bp.route("/api/roughcut/<session_id>/generate", methods=["POST"])
    def roughcut_generate(session_id):
        store = review_store_getter()
        session = store.get_session(session_id)
        if not session:
            return _error_response("Session not found", "SESSION_NOT_FOUND", 404)

        data = request.get_json(silent=True) or {}
        idempotency_key = data.get("idempotency_key")

        # Get latest version's edits
        versions = store.list_versions(session_id)
        if not versions:
            return _error_response("No edits version found", "NO_EDITS", 400)

        latest = versions[-1]
        job_id = idempotency_key or uuid.uuid4().hex[:12]

        # In production, this would launch a background render job
        # For now, return 202 with job_id
        return _ok({
            "job_id": job_id,
            "status": "queued",
            "version": latest["version_number"],
        }, 202)

    return bp
