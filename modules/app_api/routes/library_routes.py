#!/usr/bin/env python3
"""Library/media ingestion routes extracted from server.py."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict
import uuid

from flask import Blueprint, jsonify, request, send_file, abort

from modules.app_api.param_utils import parse_int_param

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
        retrieval_mode = (request.args.get("mode", "hybrid") or "hybrid").strip().lower()
        media_type = (request.args.get("media_type", "all") or "all").strip().lower()
        if media_type not in {"all", "video", "image"}:
            media_type = "all"
        if retrieval_mode not in {"hybrid", "keyword", "vector"}:
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
                "truncated": has_more,
                "has_more": has_more,
                "results": results,
            }
        )

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
                _set_progress(job_id, int(done * 100 / max(total, 1)), f"已处理 {done}/{total} {name}")

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
            return jsonify({"error": str(exc)}), 400
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
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "preview": preview})

    return bp
