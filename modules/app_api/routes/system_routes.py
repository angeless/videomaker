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

    return bp
