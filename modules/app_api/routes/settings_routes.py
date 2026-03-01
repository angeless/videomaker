#!/usr/bin/env python3
"""Settings/session routes extracted from monolithic server module."""

from __future__ import annotations

from typing import Any, Callable, Dict

from flask import Blueprint, jsonify, request


def create_settings_blueprint(
    *,
    request_is_local: Callable[[], bool],
    require_local_token_getter: Callable[[], bool],
    require_csrf_getter: Callable[[], bool],
    local_token_getter: Callable[[], str],
    local_csrf_token_getter: Callable[[], str],
    load_ai_settings: Callable[[], Dict[str, Any]],
    save_ai_settings: Callable[[Dict[str, Any]], Dict[str, Any]],
    apply_ai_env: Callable[[Dict[str, Any]], None],
    public_ai_settings: Callable[[Dict[str, Any]], Dict[str, Any]],
    load_ui_settings: Callable[[], Dict[str, Any]],
    save_ui_settings: Callable[[Dict[str, Any]], Dict[str, Any]],
    load_publish_settings: Callable[[], Dict[str, Any]],
    save_publish_settings: Callable[[Dict[str, Any]], Dict[str, Any]],
    mask_publish_connectors: Callable[[Dict[str, Dict[str, Any]]], Dict[str, Dict[str, Any]]],
) -> Blueprint:
    bp = Blueprint("settings_api", __name__)

    @bp.route("/api/session/bootstrap", methods=["GET"])
    def api_session_bootstrap():
        if not request_is_local():
            return jsonify({"error": "仅允许本机握手"}), 403
        return jsonify(
            {
                "ok": True,
                "auth_required": bool(require_local_token_getter()),
                "csrf_required": bool(require_csrf_getter()),
                "token": str(local_token_getter() or "").strip() if require_local_token_getter() else "",
                "csrf_token": str(local_csrf_token_getter() or "").strip(),
            }
        )

    @bp.route("/api/settings/ai", methods=["GET"])
    def api_get_ai_settings():
        ai = load_ai_settings()
        return jsonify({"ok": True, **public_ai_settings(ai)})

    @bp.route("/api/settings/ai", methods=["POST"])
    def api_save_ai_settings():
        data = request.json or {}
        ai = save_ai_settings(data)
        apply_ai_env(ai)
        return jsonify({"ok": True, **public_ai_settings(ai)})

    @bp.route("/api/settings/ui", methods=["GET"])
    def api_get_ui_settings():
        return jsonify({"ok": True, **load_ui_settings()})

    @bp.route("/api/settings/ui", methods=["POST"])
    def api_save_ui_settings():
        data = request.json or {}
        ui = save_ui_settings(data)
        return jsonify({"ok": True, **ui})

    @bp.route("/api/settings/publish", methods=["GET"])
    def api_get_publish_settings():
        settings = load_publish_settings()
        connectors = settings.get("connectors", {})
        if not isinstance(connectors, dict):
            connectors = {}
        return jsonify(
            {
                "ok": True,
                "connectors": mask_publish_connectors(connectors),
                "connector_count": len(connectors),
            }
        )

    @bp.route("/api/settings/publish", methods=["POST"])
    def api_save_publish_settings():
        data = request.json or {}
        settings = save_publish_settings(data)
        connectors = settings.get("connectors", {})
        if not isinstance(connectors, dict):
            connectors = {}
        return jsonify(
            {
                "ok": True,
                "connectors": mask_publish_connectors(connectors),
                "connector_count": len(connectors),
            }
        )

    return bp

