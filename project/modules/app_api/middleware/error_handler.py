"""Error handler middleware extracted from server.py."""

import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

logger = logging.getLogger(__name__)

# ── Module-level state (injected via init()) ──
_app = None


def init(*, app=None):
    global _app
    if app is not None:
        _app = app


def handle_request_entity_too_large(_exc):
    app = _app
    limit_mb = int(max(app.config.get("MAX_CONTENT_LENGTH", 0), 0) / (1024 * 1024)) if app else 0
    return (
        jsonify(
            {
                "error": f"请求内容过大（上限约 {limit_mb}MB）。请减少单次提交内容，或按批次执行。"
            }
        ),
        413,
    )


def handle_not_found(_exc):
    return jsonify({"error": "路由不存在", "code": "not_found"}), 404


def handle_method_not_allowed(_exc):
    return jsonify({"error": "HTTP 方法不允许", "code": "method_not_allowed"}), 405


def handle_unexpected_error(exc):
    if isinstance(exc, HTTPException):
        return jsonify({"error": str(exc.description), "code": exc.name}), exc.code
    logger.exception("未捕获异常: %s", exc)
    return (
        jsonify(
            {
                "error": "系统发生异常，已记录日志。请重试；若持续失败，请在设置中导出诊断信息。"
            }
        ),
        500,
    )
