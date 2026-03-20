"""Security middleware extracted from server.py."""

from flask import jsonify, request


# ── Module-level state (injected via init()) ──
_REQUIRE_LOCAL_API_TOKEN = False
_REQUIRE_CSRF_PROTECTION = True
_LOCAL_API_TOKEN = ""
_LOCAL_CSRF_TOKEN = ""


def init(
    *,
    require_local_api_token=None,
    require_csrf_protection=None,
    local_api_token=None,
    local_csrf_token=None,
):
    global _REQUIRE_LOCAL_API_TOKEN, _REQUIRE_CSRF_PROTECTION, _LOCAL_API_TOKEN, _LOCAL_CSRF_TOKEN
    if require_local_api_token is not None:
        _REQUIRE_LOCAL_API_TOKEN = require_local_api_token
    if require_csrf_protection is not None:
        _REQUIRE_CSRF_PROTECTION = require_csrf_protection
    if local_api_token is not None:
        _LOCAL_API_TOKEN = local_api_token
    if local_csrf_token is not None:
        _LOCAL_CSRF_TOKEN = local_csrf_token


def _request_is_local() -> bool:
    remote = str(request.remote_addr or "").strip()
    if remote in {"127.0.0.1", "::1", "localhost", ""}:
        return True
    return False


def _is_mutating_method(method: str) -> bool:
    return str(method or "").strip().upper() in {"POST", "PUT", "PATCH", "DELETE"}


def _is_allowed_local_origin(origin: str) -> bool:
    text = str(origin or "").strip().lower()
    if not text:
        return True
    if text in {"null", "file://"}:
        return True
    allowed_prefixes = (
        "http://127.0.0.1",
        "https://127.0.0.1",
        "http://localhost",
        "https://localhost",
    )
    return any(text.startswith(prefix) for prefix in allowed_prefixes)


def _get_security_state():
    """Read security state from server module to stay in sync with tests."""
    try:
        from modules.app_api import server
        return (
            bool(getattr(server, '_REQUIRE_LOCAL_API_TOKEN', _REQUIRE_LOCAL_API_TOKEN)),
            bool(getattr(server, '_REQUIRE_CSRF_PROTECTION', _REQUIRE_CSRF_PROTECTION)),
            str(getattr(server, '_LOCAL_API_TOKEN', _LOCAL_API_TOKEN)),
            str(getattr(server, '_LOCAL_CSRF_TOKEN', _LOCAL_CSRF_TOKEN)),
        )
    except Exception:
        return (_REQUIRE_LOCAL_API_TOKEN, _REQUIRE_CSRF_PROTECTION, _LOCAL_API_TOKEN, _LOCAL_CSRF_TOKEN)


def _guard_local_api_token():
    if request.method == "OPTIONS":
        return None
    path = str(request.path or "")
    if not path.startswith("/api/"):
        return None
    req_token, req_csrf, api_token, csrf_token = _get_security_state()
    enforce_csrf = bool(req_csrf and req_token)
    origin = str(request.headers.get("Origin", "") or "").strip()
    if enforce_csrf and _is_mutating_method(request.method) and not _is_allowed_local_origin(origin):
        return jsonify({"error": "非法来源，请在本地应用内发起请求。", "code": "origin_forbidden"}), 403
    if path == "/api/session/bootstrap":
        return None
    if enforce_csrf and _is_mutating_method(request.method):
        provided_csrf = str(request.headers.get("X-VideoEditor-CSRF", "") or "").strip()
        if not provided_csrf:
            provided_csrf = str(request.args.get("_csrf", "") or "").strip()
        if provided_csrf != csrf_token:
            return (
                jsonify(
                    {
                        "error": "请求缺少安全校验，请刷新应用后重试。",
                        "code": "csrf_required",
                    }
                ),
                403,
            )
    if not req_token:
        return None
    if not _request_is_local():
        return jsonify({"error": "仅允许本机访问该 API"}), 403
    provided = str(request.headers.get("X-VideoEditor-Token", "") or "").strip()
    if not provided:
        provided = str(request.args.get("_vt", "") or "").strip()
    if provided != api_token:
        return (
            jsonify(
                {
                    "error": "未授权请求，请先完成本地会话握手。",
                    "code": "local_auth_required",
                }
            ),
            401,
        )
    return None
