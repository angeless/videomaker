#!/usr/bin/env python3
"""Library/media ingestion routes extracted from server.py."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict
import uuid

from flask import Blueprint, jsonify, request, send_file, abort

from modules.app_api.param_utils import parse_int_param, safe_error_response

logger = logging.getLogger(__name__)


def create_library_blueprint(
    *,
    library_getter: Callable[[], Any],
    jobs_getter: Callable[[], Dict[str, Dict[str, Any]]],
    run_in_bg: Callable[..., str],
    running_heavy_jobs_getter: Callable[[], list],
    system_load_snapshot_getter: Callable[[], Dict[str, Any]],
    task_queue_snapshot_getter: Callable[[], Dict[str, Any]],
    cancel_token_getter: Callable[[], str],
    job_cancelled_error_getter: Callable[[], type],
) -> Blueprint:
    bp = Blueprint("library_api", __name__)

    def _library():
        return library_getter()

    def _jobs():
        src = jobs_getter()
        return src if isinstance(src, dict) else {}

    def _cancel_token() -> str:
        return str(cancel_token_getter() or "__CANCELLED__")

    def _cancel_exc(*args, **kwargs):
        return job_cancelled_error_getter()(*args, **kwargs)

    def _set_progress(job_id: str, progress: int, line: str = ""):
        jobs = _jobs()
        if job_id not in jobs or not isinstance(jobs.get(job_id), dict):
            return
        jobs[job_id]["progress"] = max(0, min(100, int(progress)))
        if line:
            jobs[job_id]["log"].append(str(line))
            jobs[job_id]["log"] = jobs[job_id]["log"][-220:]

    def _cancel_requested(job_id: str) -> bool:
        jobs = _jobs()
        return bool(jobs.get(job_id, {}).get("cancel_requested"))

    @bp.route("/api/library/thumbnail/<uid>")
    def api_library_thumbnail(uid):
        lib = _library()
        thumb_path = lib.thumbnail_path(uid)
        if not thumb_path or not Path(thumb_path).exists():
            abort(404)
        return send_file(str(thumb_path), mimetype="image/jpeg", max_age=3600)

    @bp.route("/api/library/thumbnails/generate", methods=["POST"])
    def api_library_thumbnails_generate():
        job_id = str(uuid.uuid4())[:8]

        def _do_thumbs():
            def _progress(pct):
                _set_progress(job_id, pct, f"缩略图生成 {pct}%")
            result = _library().generate_missing_thumbnails(progress_cb=_progress)
            return {"ok": True, "result": result}

        run_in_bg(job_id, _do_thumbs, kind="library_thumbnails_generate")
        return jsonify({"ok": True, "job_id": job_id, "mode": "async"})

    @bp.route("/api/library/stats")
    def api_library_stats():
        return jsonify(_library().stats())

    @bp.route("/api/library/search")
    def api_library_search():
        query = (request.args.get("q", "") or "").strip()
        if len(query) > 500:
            return jsonify({"error": "query 长度超出限制（最大 500 字符）"}), 400
        retrieval_mode = (request.args.get("mode", "hybrid") or "hybrid").strip().lower()
        media_type = (request.args.get("media_type", "all") or "all").strip().lower()
        if media_type not in {"all", "video", "image"}:
            media_type = "all"
        if retrieval_mode not in {"hybrid", "keyword", "vector", "visual", "fusion"}:
            retrieval_mode = "hybrid"
        default_limit = 120 if not query else 150
        limit = parse_int_param(request.args.get("limit", default_limit), default=default_limit, min_val=1, max_val=500)
        offset = parse_int_param(request.args.get("offset", "0"), default=0, min_val=0)
        effective_mode = retrieval_mode if query else "browse"
        lib = _library()
        results = lib.search_assets(
            query=query,
            limit=limit,
            offset=offset,
            retrieval_mode=retrieval_mode,
            media_type=media_type,
        )
        total_matches = lib.count_matching_assets(
            query=query,
            retrieval_mode=retrieval_mode,
            media_type=media_type,
        )
        stats = lib.stats()
        has_more = (offset + len(results)) < total_matches
        return jsonify(
            {
                "query": query,
                "media_type": media_type,
                "retrieval_mode": effective_mode,
                "limit": limit,
                "offset": offset,
                "count": len(results),
                "total_matches": total_matches,
                "total_assets": stats.get("total_assets", 0),
                "hybrid_search_enabled": bool(stats.get("hybrid_search_enabled", False)),
                "embedding_enabled": bool(stats.get("embedding_enabled", False)),
                "embedding_status": stats.get("embedding_status", ""),
                "embedding_status_message": stats.get("embedding_status_message", ""),
                "embedding_ready_assets": int(stats.get("embedding_ready_assets", 0)),
                "visual_search_enabled": bool(stats.get("visual_search_enabled", False)),
                "visual_embeddings_count": int(stats.get("visual_embeddings_count", 0)),
                "truncated": has_more,
                "has_more": has_more,
                "results": results,
            }
        )

    # ── Phase 3: tag tree / tag search / evidence chain ──

    @bp.route("/api/library/tags")
    def api_library_tags():
        return jsonify({"categories": _library().get_tag_tree()})

    @bp.route("/api/library/tags/search")
    def api_library_tags_search():
        q = (request.args.get("q", "") or "").strip()
        limit = parse_int_param(request.args.get("limit", "20"), default=20, min_val=1, max_val=100)
        return jsonify({"results": _library().search_tags(q, limit=limit)})

    @bp.route("/api/library/evidence")
    def api_library_evidence():
        asset_id = (request.args.get("asset_id", "") or "").strip()
        if not asset_id:
            return jsonify({"error": "asset_id is required"}), 400
        tag_id_str = request.args.get("tag_id")
        tag_id = int(tag_id_str) if tag_id_str else None
        return jsonify(_library().get_evidence_chain(asset_id, tag_id=tag_id))

    # ── Phase 5: Custom Tag CRUD ──

    @bp.route("/api/library/custom-tags", methods=["GET"])
    def api_library_custom_tags_list():
        include_archived = request.args.get("include_archived", "").lower() in ("1", "true")
        return jsonify({"custom_tags": _library().list_custom_tags(include_archived=include_archived)})

    @bp.route("/api/library/custom-tags", methods=["POST"])
    def api_library_custom_tags_create():
        data = request.json or {}
        result = _library().create_custom_tag(data)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify(result), 201

    @bp.route("/api/library/custom-tags/<int:ct_id>", methods=["PUT"])
    def api_library_custom_tags_update(ct_id):
        data = request.json or {}
        result = _library().update_custom_tag(ct_id, data)
        if result.get("error"):
            return jsonify(result), 400 if "not found" not in result["error"] else (jsonify(result), 404)
        return jsonify(result)

    @bp.route("/api/library/custom-tags/<int:ct_id>", methods=["DELETE"])
    def api_library_custom_tags_delete(ct_id):
        from modules.app_api.services.audit_log import audit as _audit
        result = _library().archive_custom_tag(ct_id)
        if result.get("error"):
            _audit("delete", "custom_tag", str(ct_id), actor=f"local:{request.remote_addr}", status="error", detail={"error": result["error"]})
            return jsonify(result), 404
        _audit("delete", "custom_tag", str(ct_id), actor=f"local:{request.remote_addr}")
        return jsonify(result)

    # ── Phase 5: Feedback ──

    @bp.route("/api/library/feedback", methods=["POST"])
    def api_library_feedback():
        data = request.json or {}
        result = _library().submit_feedback(data)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify(result)

    @bp.route("/api/library/feedback/<asset_id>")
    def api_library_feedback_history(asset_id):
        limit = parse_int_param(request.args.get("limit", "50"), default=50, min_val=1, max_val=200)
        return jsonify({"events": _library().get_feedback_history(asset_id, limit=limit)})

    # ── Search analytics ──

    @bp.route("/api/library/search-analytics")
    def api_library_search_analytics():
        days = parse_int_param(request.args.get("days", "30"), default=30, min_val=1, max_val=365)
        limit = parse_int_param(request.args.get("limit", "50"), default=50, min_val=1, max_val=200)
        return jsonify(_library().get_search_analytics(days=days, limit=limit))

    @bp.route("/api/library/search-analytics/zero-hits")
    def api_library_zero_hits():
        days = parse_int_param(request.args.get("days", "30"), default=30, min_val=1, max_val=365)
        limit = parse_int_param(request.args.get("limit", "50"), default=50, min_val=1, max_val=200)
        return jsonify({"zero_hit_queries": _library().get_zero_hit_queries(days=days, limit=limit)})

    @bp.route("/api/library/search-analytics/popular")
    def api_library_popular_searches():
        days = parse_int_param(request.args.get("days", "30"), default=30, min_val=1, max_val=365)
        limit = parse_int_param(request.args.get("limit", "20"), default=20, min_val=1, max_val=100)
        return jsonify({"popular_queries": _library().get_popular_searches(days=days, limit=limit)})

    @bp.route("/api/library/learning-candidates")
    def api_library_learning_candidates():
        source_kind = (request.args.get("source_kind", "") or "").strip() or None
        status = (request.args.get("status", "pending") or "pending").strip()
        limit = parse_int_param(request.args.get("limit", "50"), default=50, min_val=1, max_val=200)
        return jsonify({"candidates": _library().get_learning_candidates(
            source_kind=source_kind, status=status, limit=limit)})

    @bp.route("/api/library/learning-candidates/<int:cid>/review", methods=["POST"])
    def api_library_review_candidate(cid):
        data = request.json or {}
        action = (data.get("action", "") or "").strip()
        if not action:
            return jsonify({"error": "action required (approve/reject/block)"}), 400
        result = _library().review_learning_candidate(cid, action)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify(result)

    @bp.route("/api/library/learning-candidates/classify", methods=["POST"])
    def api_library_classify_candidates():
        data = request.json or {}
        limit = parse_int_param(data.get("limit", "200"), default=200, min_val=1, max_val=1000)
        result = _library().classify_learning_candidates(limit=limit)
        return jsonify(result)

    @bp.route("/api/library/learning-candidates/<int:cid>/promote", methods=["POST"])
    def api_library_promote_candidate(cid):
        result = _library().promote_candidate(cid)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify(result)

    @bp.route("/api/library/learning-candidates/batch-reject-noise", methods=["POST"])
    def api_library_batch_reject_noise():
        data = request.json or {}
        limit = parse_int_param(data.get("limit", "100"), default=100, min_val=1, max_val=500)
        result = _library().batch_reject_noise(limit=limit)
        return jsonify(result)

    @bp.route("/api/library/health")
    def api_library_health():
        return jsonify(_library().get_library_health())

    # ── Existing ──

    @bp.route("/api/library/assets", methods=["POST"])
    def api_library_assets():
        data = request.json or {}
        uids = data.get("uids") or []
        if not isinstance(uids, list):
            return jsonify({"error": "uids 必须是数组"}), 400
        return jsonify({"assets": _library().get_assets(uids)})

    @bp.route("/api/library/preview/local", methods=["POST"])
    def api_library_preview_local():
        data = request.json or {}
        source_path = (data.get("path", "") or "").strip()
        max_results = parse_int_param(data.get("max_results", 30), default=30, min_val=1, max_val=200)
        if not source_path:
            return jsonify({"error": "path 不能为空"}), 400
        running = running_heavy_jobs_getter()
        if running:
            return (
                jsonify(
                    {
                        "error": "已有重任务运行中，请等待完成后再预览",
                        "running_jobs": running,
                        "system": system_load_snapshot_getter(),
                    }
                ),
                409,
            )

        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            return jsonify({"error": f"路径不存在: {root}"}), 400

        videos = _library().discover_videos(root)
        sample = []
        for p in videos[:max_results]:
            try:
                rel = str(p.relative_to(root))
            except Exception:
                rel = str(p)
            sample.append(rel)

        return jsonify(
            {
                "ok": True,
                "preview": {
                    "path": str(root),
                    "video_candidates": len(videos),
                    "max_results": max_results,
                    "sample_videos": sample,
                },
            }
        )

    @bp.route("/api/library/ingest/local", methods=["POST"])
    def api_library_ingest_local():
        data = request.json or {}
        source_path = (data.get("path", "") or "").strip()
        max_videos = parse_int_param(data.get("max_videos", 600), default=600, min_val=1, max_val=5000)

        if not source_path:
            return jsonify({"error": "path 不能为空"}), 400
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            return jsonify({"error": f"路径不存在: {root}"}), 400

        job_id = str(uuid.uuid4())[:8]

        def _do_local():
            logger.info("[素材分析] 开始本地分析: %s (max_videos=%d)", source_path, max_videos)

            def _should_cancel():
                return _cancel_requested(job_id)

            def _progress(done, total, current_path):
                if _should_cancel():
                    raise _cancel_exc(_cancel_token())
                if total <= 0:
                    _set_progress(job_id, 0)
                    return
                name = Path(current_path).name if current_path else ""
                pct = int(done * 100 / max(total, 1))
                _set_progress(job_id, pct, f"已处理 {done}/{total} {name}")
                jobs = _jobs()
                if job_id in jobs and isinstance(jobs[job_id], dict):
                    jobs[job_id]["ingest_meta"] = {
                        "processed": done, "total": total,
                        "current_file": name, "percent": round(pct, 1),
                    }

            result = _library().ingest_local_path(
                source_path,
                max_videos=max_videos,
                progress_callback=_progress,
                should_cancel=_should_cancel,
            )
            if result.get("cancelled"):
                raise _cancel_exc(
                    _cancel_token(),
                    {"ok": False, "cancelled": True, "result": result, "stats": _library().stats()},
                )
            logger.info(
                "[素材分析] 本地分析完成: 扫描 %s，入库 %s，重复 %s，失败 %s",
                result.get("scanned", 0), result.get("indexed", 0),
                result.get("dedup_hits", 0), result.get("failed", 0),
            )
            return {"ok": True, "result": result, "stats": _library().stats()}

        run_in_bg(job_id, _do_local, kind="library_ingest_local")
        from modules.app_api.services.audit_log import audit as _audit
        _audit("ingest", "library", job_id, actor=f"local:{request.remote_addr}", detail={"source": source_path, "type": "video", "max_videos": max_videos})
        return jsonify(
            {
                "ok": True,
                "job_id": job_id,
                "mode": "async",
                "max_videos": max_videos,
                "system": system_load_snapshot_getter(),
                "task_queue": task_queue_snapshot_getter(),
            }
        )

    @bp.route("/api/library/preview/local/images", methods=["POST"])
    def api_library_preview_local_images():
        data = request.json or {}
        source_path = (data.get("path", "") or "").strip()
        max_results = parse_int_param(data.get("max_results", 30), default=30, min_val=1, max_val=300)
        if not source_path:
            return jsonify({"error": "path 不能为空"}), 400
        running = running_heavy_jobs_getter()
        if running:
            return (
                jsonify(
                    {
                        "error": "已有重任务运行中，请等待完成后再预览",
                        "running_jobs": running,
                        "system": system_load_snapshot_getter(),
                    }
                ),
                409,
            )

        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            return jsonify({"error": f"路径不存在: {root}"}), 400

        images = _library().discover_images(root)
        sample = []
        for p in images[:max_results]:
            try:
                rel = str(p.relative_to(root))
            except Exception:
                rel = str(p)
            sample.append(rel)

        return jsonify(
            {
                "ok": True,
                "preview": {
                    "path": str(root),
                    "image_candidates": len(images),
                    "max_results": max_results,
                    "sample_images": sample,
                },
            }
        )

    @bp.route("/api/library/ingest/local/images", methods=["POST"])
    def api_library_ingest_local_images():
        data = request.json or {}
        source_path = (data.get("path", "") or "").strip()
        max_images = parse_int_param(data.get("max_images", 1200), default=1200, min_val=1, max_val=8000)

        if not source_path:
            return jsonify({"error": "path 不能为空"}), 400
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            return jsonify({"error": f"路径不存在: {root}"}), 400

        job_id = str(uuid.uuid4())[:8]

        def _do_local_images():
            logger.info("[图片分析] 开始本地分析: %s (max_images=%d)", source_path, max_images)

            def _should_cancel():
                return _cancel_requested(job_id)

            def _progress(done, total, current_path):
                if _should_cancel():
                    raise _cancel_exc(_cancel_token())
                if total <= 0:
                    _set_progress(job_id, 0)
                    return
                name = Path(current_path).name if current_path else ""
                _set_progress(job_id, int(done * 100 / max(total, 1)), f"已处理 {done}/{total} {name}")

            result = _library().ingest_local_images(
                source_path,
                max_images=max_images,
                progress_callback=_progress,
                should_cancel=_should_cancel,
            )
            if result.get("cancelled"):
                raise _cancel_exc(
                    _cancel_token(),
                    {"ok": False, "cancelled": True, "result": result, "stats": _library().stats()},
                )
            logger.info(
                "[图片分析] 本地分析完成: 扫描 %s，入库 %s，重复 %s，失败 %s",
                result.get("scanned", 0), result.get("indexed", 0),
                result.get("dedup_hits", 0), result.get("failed", 0),
            )
            return {"ok": True, "result": result, "stats": _library().stats()}

        run_in_bg(job_id, _do_local_images, kind="library_ingest_local_images")
        from modules.app_api.services.audit_log import audit as _audit
        _audit("ingest", "library", job_id, actor=f"local:{request.remote_addr}", detail={"source": source_path, "type": "image", "max_images": max_images})
        return jsonify(
            {
                "ok": True,
                "job_id": job_id,
                "mode": "async",
                "max_images": max_images,
                "system": system_load_snapshot_getter(),
                "task_queue": task_queue_snapshot_getter(),
            }
        )

    @bp.route("/api/library/ingest/local/preview", methods=["POST"])
    def api_library_ingest_local_preview():
        """Vue 前端素材导入面板：预览本地视频目录（不启动入库任务）"""
        data = request.json or {}
        source_path = (data.get("path", "") or "").strip()
        max_videos = parse_int_param(data.get("max_videos", 30), default=30, min_val=1, max_val=200)
        if not source_path:
            return jsonify({"error": "path 不能为空"}), 400
        running = running_heavy_jobs_getter()
        if running:
            return jsonify({"error": "已有重任务运行中，请等待完成后再预览", "running_jobs": running}), 409
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            return jsonify({"error": f"路径不存在: {root}"}), 400
        videos = _library().discover_videos(root)
        sample = []
        for p in videos[:max_videos]:
            try:
                rel = str(p.relative_to(root))
            except Exception:
                rel = str(p)
            sample.append(rel)
        return jsonify({"ok": True, "sample_videos": sample, "total": len(videos), "path": str(root)})

    @bp.route("/api/library/ingest/local/start", methods=["POST"])
    def api_library_ingest_local_start():
        """Vue 前端素材导入面板：启动本地视频入库任务"""
        data = request.json or {}
        source_path = (data.get("path", "") or "").strip()
        max_videos = parse_int_param(data.get("max_videos", 600), default=600, min_val=1, max_val=5000)
        if not source_path:
            return jsonify({"error": "path 不能为空"}), 400
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            return jsonify({"error": f"路径不存在: {root}"}), 400
        job_id = str(uuid.uuid4())[:8]

        def _do():
            _set_progress(job_id, 1, "正在扫描文件夹…")

            def _should_cancel():
                return _cancel_requested(job_id)

            def _progress(done, total, current_path):
                if _should_cancel():
                    raise _cancel_exc(_cancel_token())
                if total <= 0:
                    _set_progress(job_id, 0, "正在扫描…")
                    return
                name = Path(current_path).name if current_path else ""
                pct = int(done * 100 / max(total, 1))
                _set_progress(job_id, pct, f"已处理 {done}/{total} {name}")
                jobs = _jobs()
                if job_id in jobs and isinstance(jobs[job_id], dict):
                    jobs[job_id]["ingest_meta"] = {
                        "processed": done, "total": total,
                        "current_file": name, "percent": round(pct, 1),
                    }

            result = _library().ingest_local_path(
                source_path, max_videos=max_videos,
                progress_callback=_progress, should_cancel=_should_cancel,
            )
            if result.get("cancelled"):
                raise _cancel_exc(_cancel_token(), {"ok": False, "cancelled": True, "result": result})
            return {"ok": True, "result": result, "stats": _library().stats()}

        run_in_bg(job_id, _do, kind="library_ingest_local")
        from modules.app_api.services.audit_log import audit as _audit
        _audit("ingest", "library", job_id, actor=f"local:{request.remote_addr}", detail={"source": source_path, "type": "video", "max_videos": max_videos})
        return jsonify({"ok": True, "job_id": job_id, "mode": "async"})

    @bp.route("/api/library/ingest/image/preview", methods=["POST"])
    def api_library_ingest_image_preview():
        """Vue 前端素材导入面板：预览本地图片目录（不启动入库任务）"""
        data = request.json or {}
        source_path = (data.get("path", "") or "").strip()
        max_items = parse_int_param(data.get("max_items", 30), default=30, min_val=1, max_val=300)
        if not source_path:
            return jsonify({"error": "path 不能为空"}), 400
        running = running_heavy_jobs_getter()
        if running:
            return jsonify({"error": "已有重任务运行中，请等待完成后再预览", "running_jobs": running}), 409
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            return jsonify({"error": f"路径不存在: {root}"}), 400
        images = _library().discover_images(root)
        sample = []
        for p in images[:max_items]:
            try:
                rel = str(p.relative_to(root))
            except Exception:
                rel = str(p)
            sample.append(rel)
        return jsonify({"ok": True, "sample_images": sample, "total": len(images), "path": str(root)})

    @bp.route("/api/library/ingest/image/start", methods=["POST"])
    def api_library_ingest_image_start():
        """Vue 前端素材导入面板：启动本地图片入库任务"""
        data = request.json or {}
        source_path = (data.get("path", "") or "").strip()
        max_images = parse_int_param(data.get("max_images", 1200), default=1200, min_val=1, max_val=8000)
        if not source_path:
            return jsonify({"error": "path 不能为空"}), 400
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            return jsonify({"error": f"路径不存在: {root}"}), 400
        job_id = str(uuid.uuid4())[:8]

        def _do():
            def _should_cancel():
                return _cancel_requested(job_id)

            def _progress(done, total, current_path):
                if _should_cancel():
                    raise _cancel_exc(_cancel_token())
                if total > 0:
                    name = Path(current_path).name if current_path else ""
                    _set_progress(job_id, int(done * 100 / max(total, 1)), f"已处理 {done}/{total} {name}")

            result = _library().ingest_local_images(
                source_path, max_images=max_images,
                progress_callback=_progress, should_cancel=_should_cancel,
            )
            if result.get("cancelled"):
                raise _cancel_exc(_cancel_token(), {"ok": False, "cancelled": True, "result": result})
            return {"ok": True, "result": result, "stats": _library().stats()}

        run_in_bg(job_id, _do, kind="library_ingest_local_images")
        from modules.app_api.services.audit_log import audit as _audit
        _audit("ingest", "library", job_id, actor=f"local:{request.remote_addr}", detail={"source": source_path, "type": "image", "max_images": max_images})
        return jsonify({"ok": True, "job_id": job_id, "mode": "async"})

    @bp.route("/api/library/ingest/gdrive", methods=["POST"])
    def api_library_ingest_gdrive():
        data = request.json or {}
        url = (data.get("url", "") or "").strip()
        refresh = bool(data.get("refresh", False))
        priority_subdirs = data.get("priority_subdirs", "")
        max_videos = parse_int_param(data.get("max_videos", 500), default=500, min_val=1, max_val=5000)
        max_scan_folders = parse_int_param(data.get("max_scan_folders", 120), default=120, min_val=1, max_val=2000)
        if not url:
            return jsonify({"error": "url 不能为空"}), 400

        job_id = str(uuid.uuid4())[:8]

        def _do_gdrive():
            logger.info(
                "[素材分析] 开始 Google Drive 分析: max_videos=%d, max_scan_folders=%d, refresh=%s",
                max_videos, max_scan_folders, refresh,
            )

            def _should_cancel():
                return _cancel_requested(job_id)

            def _progress(done, total, current_path):
                if _should_cancel():
                    raise _cancel_exc(_cancel_token())
                if total <= 0:
                    _set_progress(job_id, 0)
                    return
                name = Path(current_path).name if current_path else ""
                _set_progress(job_id, int(done * 100 / max(total, 1)), f"已处理 {done}/{total} {name}")

            result = _library().ingest_google_drive(
                url,
                refresh=refresh,
                max_videos=max_videos,
                priority_subdirs=priority_subdirs,
                max_scan_folders=max_scan_folders,
                progress_callback=_progress,
                should_cancel=_should_cancel,
            )
            if result.get("cancelled"):
                raise _cancel_exc(
                    _cancel_token(),
                    {"ok": False, "cancelled": True, "result": result, "stats": _library().stats()},
                )
            logger.info(
                "[素材分析] Google Drive 分析完成: 列出 %s，候选 %s，入库 %s",
                result.get("listed_files", 0), result.get("video_candidates", 0),
                result.get("indexed", 0),
            )
            return {"ok": True, "result": result, "stats": _library().stats()}

        run_in_bg(job_id, _do_gdrive, kind="library_ingest_gdrive")
        from modules.app_api.services.audit_log import audit as _audit
        _audit("ingest", "library", job_id, actor=f"local:{request.remote_addr}", detail={"type": "gdrive", "max_videos": max_videos})
        return jsonify(
            {
                "ok": True,
                "job_id": job_id,
                "mode": "async",
                "max_videos": max_videos,
                "max_scan_folders": max_scan_folders,
                "system": system_load_snapshot_getter(),
                "task_queue": task_queue_snapshot_getter(),
            }
        )

    @bp.route("/api/library/preview/gdrive", methods=["POST"])
    def api_library_preview_gdrive():
        data = request.json or {}
        url = (data.get("url", "") or "").strip()
        priority_subdirs = data.get("priority_subdirs", "")
        max_scan_folders = parse_int_param(data.get("max_scan_folders", 120), default=120, min_val=1, max_val=2000)
        max_results = parse_int_param(data.get("max_results", 30), default=30, min_val=1, max_val=200)
        if not url:
            return jsonify({"error": "url 不能为空"}), 400
        running = running_heavy_jobs_getter()
        if running:
            return (
                jsonify(
                    {
                        "error": "已有重任务运行中，请等待完成后再预览",
                        "running_jobs": running,
                        "system": system_load_snapshot_getter(),
                    }
                ),
                409,
            )
        try:
            preview = _library().preview_google_drive(
                url=url,
                priority_subdirs=priority_subdirs,
                max_scan_folders=max_scan_folders,
                max_results=max_results,
            )
        except Exception as exc:
            return jsonify({"error": safe_error_response(exc, "导入预览失败")}), 400
        return jsonify({"ok": True, "preview": preview})

    @bp.route("/api/library/ingest/gdrive/images", methods=["POST"])
    def api_library_ingest_gdrive_images():
        data = request.json or {}
        url = (data.get("url", "") or "").strip()
        refresh = bool(data.get("refresh", False))
        priority_subdirs = data.get("priority_subdirs", "")
        max_images = parse_int_param(data.get("max_images", 1200), default=1200, min_val=1, max_val=8000)
        max_scan_folders = parse_int_param(data.get("max_scan_folders", 120), default=120, min_val=1, max_val=2000)
        if not url:
            return jsonify({"error": "url 不能为空"}), 400

        job_id = str(uuid.uuid4())[:8]

        def _do_gdrive_images():
            logger.info(
                "[图片分析] 开始 Google Drive 分析: max_images=%d, max_scan_folders=%d, refresh=%s",
                max_images, max_scan_folders, refresh,
            )

            def _should_cancel():
                return _cancel_requested(job_id)

            def _progress(done, total, current_path):
                if _should_cancel():
                    raise _cancel_exc(_cancel_token())
                if total <= 0:
                    _set_progress(job_id, 0)
                    return
                name = Path(current_path).name if current_path else ""
                _set_progress(job_id, int(done * 100 / max(total, 1)), f"已处理 {done}/{total} {name}")

            result = _library().ingest_google_drive_images(
                url,
                refresh=refresh,
                max_images=max_images,
                priority_subdirs=priority_subdirs,
                max_scan_folders=max_scan_folders,
                progress_callback=_progress,
                should_cancel=_should_cancel,
            )
            if result.get("cancelled"):
                raise _cancel_exc(
                    _cancel_token(),
                    {"ok": False, "cancelled": True, "result": result, "stats": _library().stats()},
                )
            logger.info(
                "[图片分析] Google Drive 分析完成: 列出 %s，候选 %s，入库 %s",
                result.get("listed_files", 0), result.get("image_candidates", 0),
                result.get("indexed", 0),
            )
            return {"ok": True, "result": result, "stats": _library().stats()}

        run_in_bg(job_id, _do_gdrive_images, kind="library_ingest_gdrive_images")
        return jsonify(
            {
                "ok": True,
                "job_id": job_id,
                "mode": "async",
                "max_images": max_images,
                "max_scan_folders": max_scan_folders,
                "system": system_load_snapshot_getter(),
                "task_queue": task_queue_snapshot_getter(),
            }
        )

    @bp.route("/api/library/preview/gdrive/images", methods=["POST"])
    def api_library_preview_gdrive_images():
        data = request.json or {}
        url = (data.get("url", "") or "").strip()
        priority_subdirs = data.get("priority_subdirs", "")
        max_scan_folders = parse_int_param(data.get("max_scan_folders", 120), default=120, min_val=1, max_val=2000)
        max_results = parse_int_param(data.get("max_results", 30), default=30, min_val=1, max_val=200)
        if not url:
            return jsonify({"error": "url 不能为空"}), 400
        running = running_heavy_jobs_getter()
        if running:
            return (
                jsonify(
                    {
                        "error": "已有重任务运行中，请等待完成后再预览",
                        "running_jobs": running,
                        "system": system_load_snapshot_getter(),
                    }
                ),
                409,
            )
        try:
            preview = _library().preview_google_drive_images(
                url=url,
                priority_subdirs=priority_subdirs,
                max_scan_folders=max_scan_folders,
                max_results=max_results,
            )
        except Exception as exc:
            return jsonify({"error": safe_error_response(exc, "导入预览失败")}), 400
        return jsonify({"ok": True, "preview": preview})

    # ── v0.7 Fingerprint / Path Relocation / Dedup endpoints ──

    @bp.route("/api/library/fingerprint/health")
    def api_fingerprint_health():
        return jsonify(_library().get_fingerprint_health())

    @bp.route("/api/library/fingerprint/backfill", methods=["POST"])
    def api_fingerprint_backfill():
        data = request.json or {}
        limit = parse_int_param(data.get("limit", "0"), default=0, min_val=0, max_val=10000)
        job_id = str(uuid.uuid4())[:8]

        def _do_backfill():
            result = _library().backfill_fingerprints(limit=limit)
            return {"ok": True, "result": result}

        run_in_bg(job_id, _do_backfill, kind="fingerprint_backfill")
        return jsonify({"ok": True, "job_id": job_id, "mode": "async"})

    @bp.route("/api/library/locations/roots", methods=["GET"])
    def api_locations_roots_list():
        active_only = request.args.get("active_only", "1").lower() in ("1", "true")
        return jsonify({"roots": _library().list_known_roots(active_only=active_only)})

    @bp.route("/api/library/locations/roots", methods=["POST"])
    def api_locations_roots_add():
        data = request.json or {}
        root_path = (data.get("root_path", "") or "").strip()
        label = (data.get("label", "") or "").strip() or None
        if not root_path:
            return jsonify({"error": "root_path is required"}), 400
        result = _library().add_known_root(root_path, label=label)
        return jsonify({"ok": True, "root": result}), 201

    @bp.route("/api/library/locations/roots/<int:root_id>", methods=["DELETE"])
    def api_locations_roots_delete(root_id):
        from modules.app_api.services.audit_log import audit as _audit
        removed = _library().remove_known_root(root_id)
        if not removed:
            _audit("delete", "location_root", str(root_id), actor=f"local:{request.remote_addr}", status="error", detail={"error": "not found"})
            return jsonify({"error": "root not found"}), 404
        _audit("delete", "location_root", str(root_id), actor=f"local:{request.remote_addr}")
        return jsonify({"ok": True, "removed": root_id})

    @bp.route("/api/library/locations/scan", methods=["POST"])
    def api_locations_scan():
        job_id = str(uuid.uuid4())[:8]

        def _do_scan():
            result = _library().scan_asset_availability()
            return {"ok": True, "result": result}

        run_in_bg(job_id, _do_scan, kind="locations_scan")
        return jsonify({"ok": True, "job_id": job_id, "mode": "async"})

    @bp.route("/api/library/locations/relocate", methods=["POST"])
    def api_locations_relocate():
        data = request.json or {}
        root_paths = data.get("root_paths") or []
        job_id = str(uuid.uuid4())[:8]

        def _do_relocate():
            result = _library().batch_relocate(root_paths=root_paths if root_paths else None)
            return {"ok": True, "result": result}

        run_in_bg(job_id, _do_relocate, kind="locations_relocate")
        from modules.app_api.services.audit_log import audit as _audit
        _audit("relocate", "library", job_id, actor=f"local:{request.remote_addr}")
        return jsonify({"ok": True, "job_id": job_id, "mode": "async"})

    @bp.route("/api/library/duplicates")
    def api_duplicates_list():
        status = (request.args.get("status", "") or "").strip() or None
        return jsonify({"groups": _library().list_duplicate_groups(status=status)})

    @bp.route("/api/library/duplicates/detect", methods=["POST"])
    def api_duplicates_detect():
        data = request.json or {}
        threshold = parse_int_param(data.get("threshold", "6"), default=6, min_val=1, max_val=20)
        job_id = str(uuid.uuid4())[:8]

        def _do_detect():
            result = _library().detect_duplicates(threshold=threshold)
            return {"ok": True, "result": result}

        run_in_bg(job_id, _do_detect, kind="duplicates_detect")
        from modules.app_api.services.audit_log import audit as _audit
        _audit("detect", "duplicates", job_id, actor=f"local:{request.remote_addr}", detail={"threshold": threshold})
        return jsonify({"ok": True, "job_id": job_id, "mode": "async"})

    @bp.route("/api/library/relink-report")
    def api_relink_report():
        uids_str = (request.args.get("uids", "") or "").strip()
        since = (request.args.get("since", "") or "").strip() or None
        uids = [u.strip() for u in uids_str.split(",") if u.strip()] if uids_str else None
        return jsonify({"report": _library().relink_report(uids=uids, since=since)})

    # ── Phase B: Duplicate resolution + Location health ──

    @bp.route("/api/library/duplicates/<int:group_id>/resolve", methods=["POST"])
    def api_duplicates_resolve(group_id):
        from modules.app_api.services.audit_log import audit as _audit
        result = _library().resolve_duplicate_group(group_id)
        if result.get("error"):
            _audit("resolve", "duplicates", str(group_id), actor=f"local:{request.remote_addr}", status="error", detail={"error": result["error"]})
            return jsonify(result), 404
        _audit("resolve", "duplicates", str(group_id), actor=f"local:{request.remote_addr}")
        return jsonify(result)

    @bp.route("/api/library/duplicates/<int:group_id>/ignore", methods=["POST"])
    def api_duplicates_ignore(group_id):
        result = _library().ignore_duplicate_group(group_id)
        if result.get("error"):
            return jsonify(result), 404
        return jsonify(result)

    @bp.route("/api/library/duplicates/<int:group_id>/primary", methods=["POST"])
    def api_duplicates_set_primary(group_id):
        from modules.app_api.services.audit_log import audit as _audit
        data = request.json or {}
        uid = (data.get("uid", "") or "").strip()
        if not uid:
            return jsonify({"error": "uid is required"}), 400
        result = _library().set_duplicate_primary(group_id, uid)
        if result.get("error"):
            _audit("set_primary", "duplicates", str(group_id), actor=f"local:{request.remote_addr}", status="error", detail={"uid": uid, "error": result["error"]})
            return jsonify(result), 400
        _audit("set_primary", "duplicates", str(group_id), actor=f"local:{request.remote_addr}", detail={"uid": uid})
        return jsonify(result)

    @bp.route("/api/library/duplicates/<int:group_id>/members/<int:member_id>/decision", methods=["POST"])
    def api_duplicates_member_decision(group_id, member_id):
        from modules.app_api.services.audit_log import audit as _audit
        data = request.json or {}
        decision = (data.get("decision", "") or "").strip()
        if not decision:
            return jsonify({"error": "decision is required (keep|remove|undecided)"}), 400
        result = _library().set_member_decision(group_id, member_id, decision)
        if result.get("error"):
            _audit("member_decision", "duplicates", f"{group_id}/{member_id}", actor=f"local:{request.remote_addr}", status="error", detail={"decision": decision, "error": result["error"]})
            return jsonify(result), 400
        _audit("member_decision", "duplicates", f"{group_id}/{member_id}", actor=f"local:{request.remote_addr}", detail={"decision": decision})
        return jsonify(result)

    @bp.route("/api/library/locations/unavailable")
    def api_locations_unavailable():
        return jsonify({"assets": _library().list_unavailable_assets()})

    @bp.route("/api/library/relink-report", methods=["POST"])
    def api_relink_report_post():
        """POST variant for batch relink report — same return structure as GET."""
        data = request.json or {}
        uids = data.get("uids") or []
        since = (data.get("since", "") or "").strip() or None
        if not isinstance(uids, list):
            return jsonify({"error": "uids must be a list"}), 400
        return jsonify({"report": _library().relink_report(uids=uids if uids else None, since=since)})

    # ------------------------------------------------------------------
    # v0.7 Phase C-1 – Project Relink
    # ------------------------------------------------------------------

    @bp.route("/api/library/project-relink", methods=["POST"])
    def api_project_relink_create():
        """Create a project relink analysis job."""
        data = request.json or {}
        project_path = (data.get("project_path") or "").strip()
        project_type = (data.get("project_type") or "jianying").strip()
        if not project_path:
            return jsonify({"error": "project_path is required"}), 400
        result = _library().create_project_relink_job(project_path, project_type)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, **result})

    @bp.route("/api/library/project-relink/<int:job_id>")
    def api_project_relink_get(job_id):
        """Get a project relink job with items."""
        result = _library().get_project_relink_job(job_id)
        if result.get("error"):
            return jsonify(result), 404
        return jsonify({"job": result})

    @bp.route("/api/library/project-relink/<int:job_id>/export")
    def api_project_relink_export(job_id):
        """Export a relink map as JSON for download."""
        result = _library().export_project_relink_map(job_id)
        if result.get("error"):
            return jsonify(result), 404
        return jsonify({"relink_map": result})

    @bp.route("/api/library/project-relink/<int:job_id>/apply", methods=["POST"])
    def api_project_relink_apply(job_id):
        """Apply relink results to a project copy."""
        from modules.app_api.services.audit_log import audit as _audit
        data = request.json or {}
        output_path = (data.get("output_path") or "").strip() or None
        force = bool(data.get("force", False))
        naming_rule = (data.get("naming_rule") or "default").strip()
        result = _library().apply_project_relink(
            job_id, output_path, force=force, naming_rule=naming_rule
        )
        if result.get("error"):
            _audit("relink_apply", "project_relink", str(job_id), actor=f"local:{request.remote_addr}", status="error", detail={"error": result["error"]})
            code = 409 if result.get("already_applied") else 400
            return jsonify(result), code
        _audit("relink_apply", "project_relink", str(job_id), actor=f"local:{request.remote_addr}")
        return jsonify({"ok": True, "result": result})

    # ------------------------------------------------------------------
    # v0.7 Phase C-2 – Project Relink enhancements
    # ------------------------------------------------------------------

    @bp.route("/api/library/project-relink/list")
    def api_project_relink_list():
        """List recent relink jobs."""
        project_path = request.args.get("project_path", "").strip() or None
        limit = int(request.args.get("limit", 20))
        offset = int(request.args.get("offset", 0))
        jobs = _library().list_project_relink_jobs(project_path, limit, offset)
        return jsonify({"jobs": jobs})

    @bp.route("/api/library/project-relink/compare")
    def api_project_relink_compare():
        """Compare two relink jobs."""
        job_a = request.args.get("job_id_a", type=int)
        job_b = request.args.get("job_id_b", type=int)
        if not job_a or not job_b:
            return jsonify({"error": "job_id_a and job_id_b required"}), 400
        result = _library().compare_project_relink_jobs(job_a, job_b)
        if result.get("error"):
            return jsonify(result), 404
        return jsonify(result)

    @bp.route("/api/library/project-relink/validate", methods=["POST"])
    def api_project_relink_validate():
        """Validate a project file before analysis."""
        data = request.json or {}
        project_path = (data.get("project_path") or "").strip()
        project_type = (data.get("project_type") or "jianying").strip()
        if not project_path:
            return jsonify({"error": "project_path is required"}), 400
        result = _library().validate_project(project_path, project_type)
        return jsonify(result)

    # ------------------------------------------------------------------
    # v0.7 Phase D-1 – Task Center + Missing Fix
    # ------------------------------------------------------------------

    @bp.route("/api/library/project-relink/<int:job_id>/retry", methods=["POST"])
    def api_project_relink_retry(job_id):
        """Retry a failed relink job (creates new job, never overwrites)."""
        result = _library().retry_project_relink_job(job_id)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, **result})

    @bp.route("/api/library/project-relink/<int:job_id>/preview-apply")
    def api_project_relink_preview_apply(job_id):
        """Read-only preview of what apply would do."""
        result = _library().preview_project_relink_apply(job_id)
        if result.get("error"):
            code = 404 if "not found" in result["error"].lower() else 400
            return jsonify(result), code
        return jsonify(result)

    @bp.route("/api/library/project-relink/<int:job_id>/export-missing")
    def api_project_relink_export_missing(job_id):
        """Export missing + unmatched items as JSON or CSV."""
        fmt = request.args.get("format", "json").strip().lower()
        if fmt not in ("json", "csv"):
            fmt = "json"
        result = _library().export_missing_items(job_id, fmt=fmt)
        if result.get("error"):
            return jsonify(result), 404
        if fmt == "csv":
            from flask import Response
            return Response(
                result["csv_content"],
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={result['filename']}"},
            )
        return jsonify(result)

    @bp.route("/api/library/project-relink/<int:job_id>/suggest-candidates")
    def api_project_relink_suggest_candidates(job_id):
        """Suggest library assets for missing/unmatched items (read-only)."""
        max_candidates = request.args.get("max", 5, type=int)
        result = _library().suggest_candidates_for_missing(job_id, max_candidates)
        if result.get("error"):
            return jsonify(result), 404
        return jsonify(result)

    # ------------------------------------------------------------------
    # v0.7 Phase D-2 – Manual Binding Loop
    # ------------------------------------------------------------------

    @bp.route("/api/library/project-relink/item/<int:item_id>/bind", methods=["POST"])
    def api_project_relink_bind(item_id):
        """Bind a library asset to a missing/unmatched item."""
        data = request.json or {}
        uid = (data.get("uid") or "").strip()
        decision_source = (data.get("decision_source") or "candidate").strip()
        if not uid:
            return jsonify({"error": "uid is required"}), 400
        result = _library().bind_project_relink_item(item_id, uid, decision_source)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, "item": result})

    @bp.route("/api/library/project-relink/item/<int:item_id>/unbind", methods=["POST"])
    def api_project_relink_unbind(item_id):
        """Remove manual binding from an item, restoring system match."""
        result = _library().unbind_project_relink_item(item_id)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, "item": result})

    @bp.route("/api/library/project-relink/<int:job_id>/refresh-items", methods=["POST"])
    def api_project_relink_refresh_items(job_id):
        """Refresh all item paths for a job (path refresh only, no re-parse)."""
        result = _library().refresh_project_relink_items(job_id)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, "result": result})

    @bp.route("/api/library/project-relink/missing-stats")
    def api_project_relink_missing_stats():
        """Aggregate missing stats across all jobs for a project path."""
        project_path = request.args.get("project_path", "").strip()
        if not project_path:
            return jsonify({"error": "project_path is required"}), 400
        result = _library().get_project_missing_stats(project_path)
        return jsonify(result)

    # ── D-3: Batch bind ──
    @bp.route("/api/library/project-relink/batch-bind", methods=["POST"])
    def api_project_relink_batch_bind():
        """Batch-bind multiple items in one call."""
        data = request.json or {}
        bindings = data.get("bindings", [])
        decision_source = data.get("decision_source", "candidate")
        if not bindings:
            return jsonify({"error": "bindings list is required"}), 400
        result = _library().batch_bind_project_relink_items(bindings, decision_source)
        return jsonify({"ok": True, **result})

    # ── D-3: Item history ──
    @bp.route("/api/library/project-relink/item/<int:item_id>/history")
    def api_project_relink_item_history(item_id):
        """Get bind/unbind history for a specific item."""
        history = _library().list_project_relink_item_history(item_id)
        return jsonify({"history": history})

    # ── D-3: Undo last bind ──
    @bp.route("/api/library/project-relink/item/<int:item_id>/undo-bind", methods=["POST"])
    def api_project_relink_undo_bind(item_id):
        """Undo the most recent manual bind on an item."""
        result = _library().undo_last_project_relink_action(item_id)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, "item": result})

    # ── D-3: Output copies list ──
    @bp.route("/api/library/project-relink/<int:job_id>/outputs")
    def api_project_relink_outputs(job_id):
        """List all output copies generated for a job."""
        outputs = _library().list_project_relink_outputs(job_id)
        return jsonify({"outputs": outputs})

    # ── D-3: Workbench data ──
    @bp.route("/api/library/project-relink/<int:job_id>/workbench")
    def api_project_relink_workbench(job_id):
        """Get workbench-grouped item data for a job."""
        result = _library().get_project_relink_workbench(job_id)
        if result.get("error"):
            return jsonify(result), 404
        return jsonify(result)

    # ── Phase D-4: Long-term sync + Handover closure ──

    @bp.route("/api/library/project-relink/reanalyze", methods=["POST"])
    def api_project_relink_reanalyze():
        """Re-analyze a project, carrying forward manual bindings."""
        data = request.json or {}
        project_path = data.get("project_path", "").strip()
        if not project_path:
            return jsonify({"error": "project_path is required"}), 400
        project_type = data.get("project_type", "jianying")
        result = _library().reanalyze_project_relink(project_path, project_type)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, **result})

    @bp.route("/api/library/project-relink/job-chain")
    def api_project_relink_job_chain():
        """Get the chronological chain of jobs for a project path."""
        project_path = request.args.get("project_path", "").strip()
        if not project_path:
            return jsonify({"error": "project_path is required"}), 400
        result = _library().get_project_job_chain(project_path)
        return jsonify(result)

    @bp.route("/api/library/project-relink/<int:job_id>/verify", methods=["POST"])
    def api_project_relink_verify(job_id):
        """Verify all resolved item paths still exist on disk."""
        result = _library().verify_project_relink_state(job_id)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, **result})

    @bp.route("/api/library/project-relink/<int:job_id>/handover", methods=["POST"])
    def api_project_relink_handover(job_id):
        """Generate handover closure report."""
        data = request.json or {}
        auto_verify = data.get("auto_verify", True)
        result = _library().generate_handover_report(job_id, auto_verify=auto_verify)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify({"ok": True, "report": result})

    @bp.route("/api/library/project-relink/<int:job_id>/export-handover")
    def api_project_relink_export_handover(job_id):
        """Export handover report as JSON or Markdown."""
        fmt = request.args.get("format", "json").strip().lower()
        if fmt not in ("json", "markdown"):
            fmt = "json"
        result = _library().export_handover_report(job_id, fmt=fmt)
        if result.get("error"):
            return jsonify(result), 404
        if fmt == "markdown":
            from flask import Response
            return Response(
                result["markdown_content"],
                mimetype="text/markdown",
                headers={"Content-Disposition": f"attachment; filename={result['filename']}"},
            )
        return jsonify(result)

    return bp
