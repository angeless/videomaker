#!/usr/bin/env python3
"""System/status routes extracted from server.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_int_param, parse_str_param

# D5: Render settings file path (module-level for testability)
_RENDER_SETTINGS_FILE = "data/render_settings.json"


def create_system_blueprint(
    *,
    state_dict_getter: Callable[[], Dict[str, Any]],
    system_load_snapshot_getter: Callable[[], Dict[str, Any]],
    overloaded_getter: Callable[[], bool],
    running_heavy_jobs_getter: Callable[[], list],
    task_queue_snapshot_getter: Callable[[], Dict[str, Any]],
    preflight_snapshot_getter: Callable[[bool], Dict[str, Any]],
    queue_max_running_getter: Callable[[], int] = lambda: 2,
    queue_max_running_setter: Callable[[int], None] = lambda v: None,
) -> Blueprint:
    bp = Blueprint("system_api", __name__)

    @bp.route("/api/system/health", methods=["GET"])
    def api_system_health():
        version = "unknown"
        try:
            vp = Path(__file__).resolve().parents[3] / "VERSION"
            if vp.exists():
                version = vp.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return jsonify({"status": "ok", "version": version})

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

    @bp.route("/api/system/hardware", methods=["GET"])
    def api_system_hardware():
        try:
            from modules.hardware.detector import get_system_profile
            from modules.hardware.encoding_strategy import choose_encoder, suggest_max_concurrent
            profile = get_system_profile()
            enc = choose_encoder(profile)
            return jsonify({
                "ok": True,
                "cpu": {
                    "physical_cores": profile.cpu.physical_cores,
                    "logical_cores": profile.cpu.logical_cores,
                    "architecture": profile.cpu.architecture,
                    "model": profile.cpu.model,
                },
                "memory": {
                    "total_gb": profile.memory.total_gb,
                    "available_gb": profile.memory.available_gb,
                },
                "gpu": {
                    "vendor": profile.gpu.vendor,
                    "model": profile.gpu.model,
                    "has_videotoolbox": profile.gpu.has_videotoolbox,
                    "has_nvenc": profile.gpu.has_nvenc,
                    "has_vaapi": profile.gpu.has_vaapi,
                },
                "ffmpeg": {
                    "path": profile.ffmpeg_path,
                    "hwaccels": profile.ffmpeg_hwaccels,
                },
                "encoding": {
                    "encoder": enc.video_encoder,
                    "hwaccel": enc.hwaccel,
                    "label": enc.label,
                },
                "suggested_max_concurrent": suggest_max_concurrent(profile),
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @bp.route("/api/system/audit", methods=["GET"])
    def api_system_audit():
        from modules.app_api.services.audit_log import query as audit_query, count as audit_count
        operation = parse_str_param(request.args.get("operation"))
        resource_type = parse_str_param(request.args.get("resource_type"))
        actor = parse_str_param(request.args.get("actor"))
        since = parse_str_param(request.args.get("since"))
        limit = parse_int_param(request.args.get("limit"), default=200, min_val=1, max_val=1000)
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
        fmt = parse_str_param(payload.get("format"), default="text").lower()
        tail_lines = parse_int_param(payload.get("tail"), default=500, min_val=0, max_val=50000)
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

    @bp.route("/api/system/queue-config", methods=["GET", "POST"])
    def api_system_queue_config():
        if request.method == "GET":
            return jsonify({"ok": True, "max_running": queue_max_running_getter()})
        payload = request.json or {}
        val = payload.get("max_running")
        if val is None or not isinstance(val, int) or val < 1 or val > 4:
            return jsonify({"error": "max_running 必须是 1-4 的整数"}), 400
        queue_max_running_setter(val)
        return jsonify({"ok": True, "max_running": val})

    # ── D5: Render settings ────────────────────────────────────────

    def _load_render_settings() -> dict:
        """Load render settings from JSON file."""
        import json
        try:
            with open(_RENDER_SETTINGS_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "encoder": "auto",
                "quality_preset": "balanced",
                "resolution": "1080x1920",
                "parallel_render": True,
            }

    def _save_render_settings(settings: dict) -> None:
        """Save render settings to JSON file."""
        import json, os
        os.makedirs(os.path.dirname(_RENDER_SETTINGS_FILE) or ".", exist_ok=True)
        with open(_RENDER_SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)

    @bp.route("/api/settings/render", methods=["GET"])
    def api_render_settings_get():
        """Get render settings + available encoder options from hardware."""
        settings = _load_render_settings()
        # Enrich with available encoders from hardware detection
        available_encoders = ["libx264"]  # always available
        try:
            from modules.hardware.detector import get_system_profile
            profile = get_system_profile()
            if profile.gpu.has_videotoolbox:
                available_encoders.append("h264_videotoolbox")
            if profile.gpu.has_nvenc:
                available_encoders.append("h264_nvenc")
            if profile.gpu.has_vaapi:
                available_encoders.append("h264_vaapi")
        except Exception:
            pass
        return jsonify({
            "ok": True,
            "settings": settings,
            "available_encoders": available_encoders,
            "quality_presets": {
                "high": {"crf": 15, "label": "高质量"},
                "balanced": {"crf": 18, "label": "平衡"},
                "fast": {"crf": 23, "label": "快速"},
            },
        })

    @bp.route("/api/settings/render", methods=["PUT"])
    def api_render_settings_put():
        """Save render settings."""
        body = request.get_json(silent=True) or {}
        allowed = {"encoder", "quality_preset", "resolution", "parallel_render"}
        settings = _load_render_settings()
        for k, v in body.items():
            if k in allowed:
                settings[k] = v
        _save_render_settings(settings)
        return jsonify({"ok": True, "settings": settings})

    return bp
