"""Style API routes — list, save, load style presets."""

import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from modules.review_engine.exceptions import ReviewEngineError

logger = logging.getLogger(__name__)


def _error_response(message, code, status=400):
    return jsonify({
        "success": False, "error": code, "message": message,
        "code": status, "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": uuid.uuid4().hex[:16],
    }), status


def _ok(data, status=200):
    return jsonify({"success": True, **data}), status


def create_style_blueprint(*, project_dir_getter):
    bp = Blueprint("style_api", __name__)

    def _styles_dir():
        return os.path.join(project_dir_getter() or "/tmp", "styles")

    @bp.route("/api/review/styles", methods=["GET"])
    def list_styles():
        try:
            from modules.review_engine.style_skills import list_styles as do_list
            styles = do_list(_styles_dir())
            return _ok({
                "styles": [
                    {
                        "name": s.name,
                        "color_grade": s.color_grade,
                        "font": s.font,
                        "transition": s.transition,
                        "audio_preset": s.audio_preset,
                        "pacing": s.pacing,
                    }
                    for s in styles
                ]
            })
        except ReviewEngineError as e:
            return _error_response(str(e), "STYLE_LIST_FAILED", 500)

    @bp.route("/api/review/styles", methods=["POST"])
    def save_style():
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        if not name:
            return _error_response("name required", "MISSING_PARAM", 400)

        try:
            from modules.review_engine.style_skills import (
                StyleConfig, save_style as do_save,
            )
            style = StyleConfig(
                name=name,
                color_grade=data.get("color_grade", "natural"),
                font=data.get("font", "PingFang SC"),
                transition=data.get("transition", "cross_dissolve"),
                audio_preset=data.get("audio_preset", "voice"),
                pacing=data.get("pacing", "medium"),
                bgm_volume_db=data.get("bgm_volume_db", -12.0),
            )
            path = do_save(style, _styles_dir())
            return _ok({"style_id": name, "path": path}, 201)
        except ReviewEngineError as e:
            return _error_response(str(e), "STYLE_SAVE_FAILED", 500)

    return bp
