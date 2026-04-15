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


# Map HTTP status codes to fixed, non-reflective user-facing messages.
# Previously we returned `str(exc.description)` verbatim, which could reflect
# attacker-controlled content from any `abort(400, description=f"...{user_input}...")`
# call site, AND could leak internal paths/IDs from werkzeug's default
# descriptions. Round-12 P0 finding (XSS + info disclosure).
_HTTP_ERROR_MESSAGES = {
    400: "请求参数无效",
    401: "未授权",
    403: "权限被拒绝",
    404: "资源不存在",
    405: "HTTP 方法不允许",
    409: "与当前状态冲突",
    413: "请求内容过大",
    415: "不支持的内容类型",
    422: "请求无法处理",
    429: "请求过于频繁",
    500: "系统发生异常",
    502: "上游服务不可用",
    503: "服务暂时不可用",
}


def handle_unexpected_error(exc):
    if isinstance(exc, HTTPException):
        # Use a fixed message per status code. The exception's description is
        # logged server-side (via logger.info) for debugging, never reflected
        # to the client.
        fixed_msg = _HTTP_ERROR_MESSAGES.get(exc.code, "请求失败")
        if exc.description and str(exc.description) != fixed_msg:
            logger.info("HTTP %s suppressed description: %s", exc.code, exc.description)
        return jsonify({"error": fixed_msg, "code": exc.name}), exc.code
    logger.exception("未捕获异常: %s", exc)
    return (
        jsonify(
            {
                "error": "系统发生异常，已记录日志。请重试；若持续失败，请在设置中导出诊断信息。"
            }
        ),
        500,
    )
