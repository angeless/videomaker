#!/usr/bin/env python3
"""System/status routes extracted from server.py."""

from __future__ import annotations

from typing import Any, Callable, Dict

from flask import Blueprint, jsonify, request


def create_system_blueprint(
    *,
    state_dict_getter: Callable[[], Dict[str, Any]],
    system_load_snapshot_getter: Callable[[], Dict[str, Any]],
    overloaded_getter: Callable[[], bool],
    running_heavy_jobs_getter: Callable[[], list],
    task_queue_snapshot_getter: Callable[[], Dict[str, Any]],
    preflight_snapshot_getter: Callable[[bool], Dict[str, Any]],
) -> Blueprint:
    bp = Blueprint("system_api", __name__)

    @bp.route("/api/status", methods=["GET"])
    def api_status():
        return jsonify(state_dict_getter())

    @bp.route("/api/system/load", methods=["GET"])
    def api_system_load():
        preflight = preflight_snapshot_getter(False)
        preflight_summary = preflight.get("summary", {}) if isinstance(preflight, dict) else {}
        return jsonify(
            {
                "ok": True,
                "system": system_load_snapshot_getter(),
                "overloaded": bool(overloaded_getter()),
                "running_jobs": running_heavy_jobs_getter(),
                "task_queue": task_queue_snapshot_getter(),
                "preflight": {
                    "startup_ready": bool(preflight.get("startup_ready", False)) if isinstance(preflight, dict) else False,
                    "summary": preflight_summary,
                },
            }
        )

    @bp.route("/api/tasks/queue", methods=["GET"])
    def api_tasks_queue():
        return jsonify({"ok": True, "task_queue": task_queue_snapshot_getter()})

    @bp.route("/api/system/preflight", methods=["GET"])
    def api_system_preflight():
        force_raw = str(request.args.get("force", "0") or "0").strip().lower()
        force = force_raw in {"1", "true", "yes", "y", "on"}
        report = preflight_snapshot_getter(force)
        if not isinstance(report, dict):
            return jsonify({"error": "preflight 报告不可用"}), 500
        return jsonify({"ok": True, "preflight": report})

    # ── observability endpoints ────────────────────────────────────────

    @bp.route("/api/system/startup-timing", methods=["GET"])
    def api_system_startup_timing():
        from modules.app_api.services.startup_timing import snapshot
        return jsonify({"ok": True, "startup": snapshot()})

    @bp.route("/api/system/perf", methods=["GET"])
    def api_system_perf():
        from modules.app_api.services.perf_log import query_stats, recent
        operation = str(request.args.get("operation", "") or "").strip()
        since = str(request.args.get("since", "") or "").strip()
        return jsonify({
            "ok": True,
            "stats": query_stats(operation=operation, since=since),
            "recent": recent(limit=50),
        })

    @bp.route("/api/system/audit", methods=["GET"])
    def api_system_audit():
        from modules.app_api.services.audit_log import query as audit_query, count as audit_count
        operation = str(request.args.get("operation", "") or "").strip()
        resource_type = str(request.args.get("resource_type", "") or "").strip()
        actor = str(request.args.get("actor", "") or "").strip()
        since = str(request.args.get("since", "") or "").strip()
        limit = min(int(request.args.get("limit", 200) or 200), 1000)
        entries = audit_query(
            operation=operation,
            resource_type=resource_type,
            actor=actor,
            since=since,
            limit=limit,
        )
        return jsonify({
            "ok": True,
            "entries": entries,
            "count": len(entries),
            "total": audit_count(since=since),
            "filters": {
                "operation": operation or None,
                "resource_type": resource_type or None,
                "actor": actor or None,
                "since": since or None,
                "limit": limit,
            },
        })

    @bp.route("/api/system/logs/export", methods=["POST"])
    def api_system_logs_export():
        from modules.app_api.services.logging_service import current_log_file
        log_file = current_log_file()
        if not log_file or not log_file.exists():
            return jsonify({"error": "日志文件不可用"}), 404
        payload = request.json or {}
        fmt = str(payload.get("format", "text")).lower()
        tail_lines = int(payload.get("tail", 500))
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        picked = lines[-tail_lines:] if tail_lines > 0 else lines
        if fmt == "json":
            return jsonify({
                "ok": True,
                "lines": picked,
                "total_lines": len(lines),
                "log_file": str(log_file),
            })
        from flask import Response
        return Response(
            "\n".join(picked),
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=videoeditor_session.log"},
        )

    return bp
