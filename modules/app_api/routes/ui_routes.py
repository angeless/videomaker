#!/usr/bin/env python3
"""UI static file routes."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from flask import Blueprint, abort, send_file

_DOCS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "api"


def create_ui_blueprint(*, app_ui_dir_getter: Callable[[], Path]) -> Blueprint:
    bp = Blueprint("ui_api", __name__)

    @bp.route("/api/docs/publish")
    def serve_publish_openapi():
        yaml_path = _DOCS_DIR / "openapi-publish.yaml"
        if not yaml_path.exists():
            abort(404)
        resp = send_file(str(yaml_path), mimetype="application/x-yaml")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.route("/")
    def serve_index():
        ui_dir = app_ui_dir_getter()
        resp = send_file(str(ui_dir / "index.html"))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @bp.route("/<path:filename>")
    def serve_static(filename):
        ui_dir = app_ui_dir_getter()
        target = (ui_dir / filename).resolve()
        if not str(target).startswith(str(ui_dir.resolve())):
            abort(403)
        if not target.exists():
            abort(404)
        resp = send_file(str(target))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    return bp
