#!/usr/bin/env python3
"""Settings/session routes extracted from monolithic server module."""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Callable, Dict, Optional

from flask import Blueprint, jsonify, request

import threading
from html import escape as _html_escape

from modules.app_api.param_utils import parse_str_param, safe_error_response

logger = logging.getLogger(__name__)

# In-memory OAuth state store (short-lived, cleared after use).
# Mutated from Flask worker threads on /authorize (insert + stale cleanup)
# AND concurrently on /callback (pop). Without the lock two concurrent
# callbacks with the same state (or an /authorize cleanup pass racing
# with a /callback pop) can raise KeyError → 500 to the user, or worse
# leak OAuth tokens if the state dict corruption exposes pending entries.
_oauth_pending: Dict[str, dict] = {}
_oauth_pending_lock = threading.Lock()


def _is_safe_outbound_url(url: str) -> tuple[bool, str]:
    """SSRF guard: reject URLs pointing at loopback / link-local / private
    networks. Used for user-supplied webhook URLs where the server will make
    an outbound HTTP request — prevents the server being weaponized as a
    probe into the local network (e.g. AWS metadata 169.254.169.254, local
    Ollama, internal admin panels, etc.).

    Returns (ok, reason) where reason is empty on success.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception as exc:
        return False, f"URL 格式无效: {exc}"
    if parsed.scheme not in ("http", "https"):
        return False, f"仅支持 http/https (got {parsed.scheme})"
    host = parsed.hostname
    if not host:
        return False, "URL 缺少主机名"
    # Resolve all A/AAAA records; block if ANY is private/loopback/link-local.
    # (Otherwise a DNS-rebind attack could flip the record between check
    # and fetch; we're best-effort here since urllib does its own resolution.)
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return False, f"DNS 解析失败: {exc}"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError):
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_multicast or ip.is_reserved:
            return False, f"禁止连接内网/回环地址: {ip}"
    return True, ""


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
    secret_store_getter: Optional[Callable] = None,
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
                "token": parse_str_param(local_token_getter()) if require_local_token_getter() else "",
                "csrf_token": parse_str_param(local_csrf_token_getter()),
            }
        )

    @bp.route("/api/settings", methods=["GET"])
    def api_get_settings_aggregated():
        from modules.app_api.services.settings_service import _mask_secret
        ai = load_ai_settings()
        ai_public = public_ai_settings(ai)
        ui = load_ui_settings()
        return jsonify({"ok": True, "ai": ai_public, "ui": ui})

    @bp.route("/api/settings/ai", methods=["GET"])
    def api_get_ai_settings():
        ai = load_ai_settings()
        return jsonify({"ok": True, **public_ai_settings(ai)})

    @bp.route("/api/settings/ai", methods=["POST"])
    def api_save_ai_settings():
        from modules.app_api.services.audit_log import audit as _audit
        from modules.app_api.services.settings_service import _AI_PROVIDER_CATALOG, _AI_PROVIDER_ALIASES
        data = request.json or {}
        raw_provider = parse_str_param(data.get("provider", "")).lower()
        if raw_provider:
            normalized = _AI_PROVIDER_ALIASES.get(raw_provider)
            if normalized is None or normalized not in _AI_PROVIDER_CATALOG:
                valid = sorted(_AI_PROVIDER_CATALOG.keys())
                return jsonify({"error": f"provider 不合法，合法值为：{' / '.join(valid)}"}), 400
        ai = save_ai_settings(data)
        apply_ai_env(ai)
        _audit("config_change", "settings", "ai", actor=f"local:{request.remote_addr}", detail={"keys_changed": sorted(data.keys())})
        return jsonify({"ok": True, **public_ai_settings(ai)})

    @bp.route("/api/settings/ai/test", methods=["POST"])
    def api_test_ai_connection():
        import socket
        ai = load_ai_settings()
        provider = ai.get("provider", "")
        api_key = ai.get("openai_api_key", "") or ai.get("anthropic_api_key", "")
        if not provider:
            return jsonify({"ok": False, "error": "未配置 AI 服务商"})
        if not api_key:
            return jsonify({"ok": False, "error": "未配置 API Key"})
        base_url = ai.get("ai_base_url", "") or ""
        try:
            import urllib.request
            import urllib.error
            test_url = base_url.rstrip("/") + "/models" if base_url else ""
            if not test_url:
                from modules.app_api.services.settings_service import _AI_PROVIDER_CATALOG
                cat = _AI_PROVIDER_CATALOG.get(provider, {})
                test_url = (cat.get("default_base_url", "") or "").rstrip("/") + "/models"
            if not test_url:
                return jsonify({"ok": False, "error": f"无法确定 {provider} 的 API 地址"})
            req = urllib.request.Request(test_url, method="GET")
            req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return jsonify({"ok": True})
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return jsonify({"ok": False, "error": "API Key 无效（401 认证失败）"})
            if e.code == 403:
                return jsonify({"ok": False, "error": "API Key 权限不足（403）"})
            return jsonify({"ok": False, "error": f"服务端返回 HTTP {e.code}"})
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            return jsonify({"ok": False, "error": f"连接失败：{e}"})
        except Exception as e:
            return jsonify({"ok": False, "error": f"连接失败：{e}"})

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
        from modules.app_api.services.audit_log import audit as _audit
        data = request.json or {}
        settings = save_publish_settings(data)
        _audit("config_change", "settings", "publish", actor=f"local:{request.remote_addr}", detail={"keys_changed": sorted(data.keys())})
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

    # ── YouTube OAuth 2.0 ──────────────────────────────────────

    def _get_secret_store():
        if secret_store_getter:
            return secret_store_getter()
        return None

    def _read_youtube_token() -> Optional[dict]:
        store = _get_secret_store()
        if not store:
            return None
        raw = store.get("youtube_oauth")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def _write_youtube_token(token_data: dict) -> bool:
        store = _get_secret_store()
        if not store:
            return False
        return store.set("youtube_oauth", json.dumps(token_data, ensure_ascii=False))

    def _delete_youtube_token() -> bool:
        store = _get_secret_store()
        if not store:
            return False
        return store.delete("youtube_oauth")

    @bp.route("/api/settings/oauth/youtube/start", methods=["POST"])
    def api_oauth_youtube_start():
        """Generate OAuth URL and open browser for YouTube authorization."""
        data = request.json or {}
        redirect_uri = parse_str_param(data.get("redirect_uri", ""))
        if not redirect_uri:
            port = request.host.split(":")[-1] if ":" in request.host else "9527"
            redirect_uri = f"http://localhost:{port}/api/settings/oauth/youtube/callback"

        state = secrets.token_urlsafe(32)
        # Lock the insert + stale cleanup pair so concurrent /authorize
        # requests don't race on dict mutation (was causing occasional
        # KeyError 500 under two-tab OAuth flows).
        cutoff = time.time() - 600
        with _oauth_pending_lock:
            _oauth_pending[state] = {"created_at": time.time(), "redirect_uri": redirect_uri}
            stale = [k for k, v in _oauth_pending.items() if v.get("created_at", 0) < cutoff]
            for k in stale:
                _oauth_pending.pop(k, None)

        client_id = _resolve_google_client_id()
        if not client_id:
            return jsonify({"error": "未配置 Google OAuth Client ID。请在设置中配置 GOOGLE_CLIENT_ID 环境变量。"}), 400

        import urllib.parse
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        auth_url = f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"

        # Open system browser
        try:
            import webbrowser
            webbrowser.open(auth_url)
        except Exception as exc:
            logger.warning("Failed to open browser for OAuth: %s", exc)

        return jsonify({"ok": True, "auth_url": auth_url})

    @bp.route("/api/settings/oauth/youtube/callback", methods=["GET"])
    def api_oauth_youtube_callback():
        """Handle Google OAuth callback — exchange code for tokens."""
        code = request.args.get("code", "")
        state = request.args.get("state", "")
        error = request.args.get("error", "")

        html_wrap = lambda title, body: (
            f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>body{{font-family:system-ui;display:flex;justify-content:center;align-items:center;"
            f"min-height:100vh;margin:0;background:#1a1a2e;color:#e0e0e0}}"
            f".card{{background:#16213e;border-radius:12px;padding:40px;max-width:480px;text-align:center}}"
            f"h2{{color:#5a8dee}}p{{color:#a0a0a0;line-height:1.6}}</style></head>"
            f"<body><div class='card'>{body}</div></body></html>"
        )

        if error:
            # XSS prevention: error is attacker-controlled URL param reflected
            # back as HTML. `<img src=x onerror=fetch(...)>` would execute as
            # script on the app origin. Escape before interpolation.
            return html_wrap("授权失败", f"<h2>授权失败</h2><p>{_html_escape(error)}</p><p>请关闭此页面并重试。</p>"), 400

        # Race-safe state check — use pop(state, None) inside the lock to
        # atomically validate+consume. Previously two concurrent callbacks
        # with the same state could both pass `state not in _oauth_pending`
        # then race on `.pop(state)` where the loser hit KeyError (500).
        with _oauth_pending_lock:
            pending = _oauth_pending.pop(state, None) if state else None
        if pending is None:
            return html_wrap("授权失败", "<h2>授权失败</h2><p>无效请求（state 不匹配）</p><p>请关闭此页面并重新发起授权。</p>"), 400

        redirect_uri = pending.get("redirect_uri", "")

        if not code:
            return html_wrap("授权失败", "<h2>授权失败</h2><p>未收到授权码</p>"), 400

        # Exchange code for tokens
        client_id = _resolve_google_client_id()
        client_secret = _resolve_google_client_secret()
        if not client_id or not client_secret:
            return html_wrap("授权失败", "<h2>配置错误</h2><p>未配置 Google OAuth Client ID/Secret</p>"), 500

        try:
            import urllib.request
            import urllib.parse
            token_data = urllib.parse.urlencode({
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_resp = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.error("YouTube OAuth token exchange failed: %s", exc)
            # Escape: urllib HTTPError __str__ can contain attacker-influenced
            # URL fragments (e.g. from upstream redirect chains).
            return html_wrap("授权失败", f"<h2>Token 交换失败</h2><p>{_html_escape(str(exc))}</p>"), 500

        access_token = token_resp.get("access_token", "")
        refresh_token = token_resp.get("refresh_token", "")
        expires_in = int(token_resp.get("expires_in", 3600))
        expires_at = time.time() + expires_in

        if not access_token:
            return html_wrap("授权失败", "<h2>未获得 access_token</h2>"), 500

        # Fetch channel info
        channel_name = ""
        try:
            ch_req = urllib.request.Request(
                "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            with urllib.request.urlopen(ch_req, timeout=10) as ch_resp:
                ch_data = json.loads(ch_resp.read().decode("utf-8"))
                items = ch_data.get("items", [])
                if items:
                    channel_name = items[0].get("snippet", {}).get("title", "")
        except Exception as exc:
            logger.warning("Failed to fetch YouTube channel info: %s", exc)

        # Persist token
        stored = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "channel_name": channel_name,
            "connected_at": time.time(),
        }
        _write_youtube_token(stored)

        # Audit log
        try:
            from modules.app_api.services.audit_log import audit as _audit
            _audit("oauth_connect", "youtube", channel_name or "unknown", actor=f"local:{request.remote_addr}")
        except Exception:
            pass

        # Escape channel_name — users can rename their YouTube channel to
        # arbitrary Unicode/HTML; even though this is THEIR own channel
        # (self-XSS), a malicious channel handoff scenario could weaponize it.
        safe_channel = _html_escape(channel_name) if channel_name else "(未知频道)"
        return html_wrap(
            "授权成功",
            f"<h2>授权成功！</h2>"
            f"<p>已连接频道：<strong>{safe_channel}</strong></p>"
            f"<p>请返回应用继续操作。此页面可安全关闭。</p>",
        )

    @bp.route("/api/settings/oauth/youtube/status", methods=["GET"])
    def api_oauth_youtube_status():
        """Check YouTube OAuth connection status."""
        token = _read_youtube_token()
        if not token or not token.get("access_token"):
            return jsonify({"connected": False})
        return jsonify({
            "connected": True,
            "channel_name": token.get("channel_name", ""),
            "expires_at": token.get("expires_at", 0),
            "connected_at": token.get("connected_at", 0),
        })

    @bp.route("/api/settings/oauth/youtube/disconnect", methods=["POST"])
    def api_oauth_youtube_disconnect():
        """Disconnect YouTube OAuth — remove stored token."""
        token = _read_youtube_token()
        channel = token.get("channel_name", "") if token else ""
        _delete_youtube_token()
        try:
            from modules.app_api.services.audit_log import audit as _audit
            _audit("oauth_disconnect", "youtube", channel or "unknown", actor=f"local:{request.remote_addr}")
        except Exception:
            pass
        return jsonify({"ok": True})

    # ── Webhook Connector Configuration ────────────────────────

    @bp.route("/api/settings/connectors", methods=["GET"])
    def api_get_connectors():
        """List all configured webhook connectors."""
        settings = load_publish_settings()
        connectors = settings.get("connectors", {})
        if not isinstance(connectors, dict):
            connectors = {}
        return jsonify({"ok": True, "connectors": mask_publish_connectors(connectors)})

    @bp.route("/api/settings/connectors/<platform_id>", methods=["PUT"])
    def api_put_connector(platform_id):
        """Configure or update a webhook connector for a platform."""
        from modules.app_api.services.audit_log import audit as _audit
        pid = parse_str_param(platform_id).strip().lower()
        if not pid:
            return jsonify({"error": "platform_id 不能为空"}), 400

        data = request.json or {}
        url = parse_str_param(data.get("url", data.get("endpoint", ""))).strip()
        if not url:
            return jsonify({"error": "Webhook URL 不能为空"}), 400

        import re
        if not re.match(r'^https?://.+', url, re.IGNORECASE):
            return jsonify({"error": "Webhook URL 格式不正确，需要 http:// 或 https:// 开头"}), 400

        headers = data.get("headers", {})
        if not isinstance(headers, dict):
            headers = {}

        timeout_s = 30
        if "timeout_s" in data:
            try:
                timeout_s = max(5, min(120, int(data["timeout_s"])))
            except (ValueError, TypeError):
                timeout_s = 30

        connector_entry = {
            "kind": "webhook",
            "endpoint": url,
            "headers": headers,
            "timeout_s": timeout_s,
        }

        settings = load_publish_settings()
        connectors = settings.get("connectors", {})
        if not isinstance(connectors, dict):
            connectors = {}
        connectors[pid] = connector_entry
        save_publish_settings({"connectors": connectors})

        _audit("connector_config", "webhook", pid, actor=f"local:{request.remote_addr}",
               detail={"action": "upsert", "url_prefix": url[:30]})
        return jsonify({"ok": True})

    @bp.route("/api/settings/connectors/<platform_id>", methods=["DELETE"])
    def api_delete_connector(platform_id):
        """Delete a webhook connector for a platform."""
        from modules.app_api.services.audit_log import audit as _audit
        pid = parse_str_param(platform_id).strip().lower()
        if not pid:
            return jsonify({"error": "platform_id 不能为空"}), 400

        settings = load_publish_settings()
        connectors = settings.get("connectors", {})
        if not isinstance(connectors, dict):
            connectors = {}
        removed = connectors.pop(pid, None)
        save_publish_settings({"connectors": connectors})

        _audit("connector_config", "webhook", pid, actor=f"local:{request.remote_addr}",
               detail={"action": "delete", "had_config": removed is not None})
        return jsonify({"ok": True})

    @bp.route("/api/settings/connectors/<platform_id>/test", methods=["POST"])
    def api_test_connector(platform_id):
        """Test a webhook connector by sending a test payload."""
        pid = parse_str_param(platform_id).strip().lower()
        if not pid:
            return jsonify({"error": "platform_id 不能为空"}), 400

        settings = load_publish_settings()
        connectors = settings.get("connectors", {})
        if not isinstance(connectors, dict):
            connectors = {}
        connector = connectors.get(pid)
        if not isinstance(connector, dict) or not connector:
            return jsonify({"error": "该平台尚未配置连接器"}), 404

        url = str(connector.get("endpoint", connector.get("url", "")) or "").strip()
        if not url:
            return jsonify({"error": "连接器缺少 URL"}), 400

        # SSRF guard — see _is_safe_outbound_url. This is a server-side
        # fetch with user-configurable URL; without this check the server
        # could be used to probe local/cloud-metadata services.
        safe, reason = _is_safe_outbound_url(url)
        if not safe:
            return jsonify({"error": f"URL 校验失败: {reason}"}), 400

        headers = connector.get("headers", {})
        if not isinstance(headers, dict):
            headers = {}
        timeout_s = int(connector.get("timeout_s", 30) or 30)

        import urllib.request
        test_payload = json.dumps({"test": True, "platform_id": pid}).encode("utf-8")
        req_headers = {"Content-Type": "application/json"}
        for hk, hv in headers.items():
            req_headers[str(hk)] = str(hv)

        try:
            req = urllib.request.Request(url, data=test_payload, headers=req_headers, method="POST")
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=min(timeout_s, 30)) as resp:
                latency_ms = int((time.time() - t0) * 1000)
                return jsonify({"ok": True, "status_code": resp.status, "latency_ms": latency_ms})
        except Exception as exc:
            return jsonify({"error": safe_error_response(exc, "连接测试失败")}), 502

    # ── R9: Subscription feature gate ──

    def _feature_gate():
        from modules.subscription import FeatureGate
        from modules.app_api.services.settings_service import _settings_path
        return FeatureGate(settings_path=_settings_path())

    @bp.route("/api/subscription/status", methods=["GET"])
    def api_subscription_status():
        gate = _feature_gate()
        return jsonify({
            "tier": gate.tier.value,
            "features": gate.all_features(),
        })

    @bp.route("/api/subscription/gate", methods=["GET"])
    def api_subscription_gate():
        feature = (request.args.get("feature", "") or "").strip()
        if not feature:
            return jsonify({"error": "feature param required"}), 400
        gate = _feature_gate()
        return jsonify(gate.gate(feature))

    @bp.route("/api/subscription/upgrade", methods=["POST"])
    def api_subscription_upgrade():
        from modules.subscription import Tier
        body = request.get_json(silent=True) or {}
        tier_str = str(body.get("tier", "") or "").lower()
        if tier_str not in ("free", "pro"):
            return jsonify({"error": "tier must be 'free' or 'pro'"}), 400
        gate = _feature_gate()
        gate.set_tier(Tier(tier_str))
        return jsonify({"ok": True, "tier": tier_str})

    # ── R6c: CLIP model settings ──────────────────────────────────

    @bp.route("/api/settings/clip-model", methods=["GET"])
    def api_get_clip_model():
        from modules.library._constants import DEFAULT_CLIP_MODEL, DEFAULT_CLIP_DIM
        from modules.library.vision.clip_encoder import _CLIP_MODEL_DIMS
        settings = _load_json_setting("clip_model")
        model_id = settings.get("model_id", DEFAULT_CLIP_MODEL) if settings else DEFAULT_CLIP_MODEL
        dim = _CLIP_MODEL_DIMS.get(model_id, DEFAULT_CLIP_DIM)
        return jsonify({"model_id": model_id, "dim": dim, "available_models": list(_CLIP_MODEL_DIMS.keys())})

    @bp.route("/api/settings/clip-model", methods=["POST"])
    def api_set_clip_model():
        from modules.library.vision.clip_encoder import _CLIP_MODEL_DIMS
        data = request.json or {}
        model_id = (data.get("model_id") or "").strip()
        if model_id not in _CLIP_MODEL_DIMS:
            return jsonify({"error": f"不支持的模型: {model_id}。可选: {list(_CLIP_MODEL_DIMS.keys())}"}), 400
        _save_json_setting("clip_model", {"model_id": model_id})
        return jsonify({"ok": True, "model_id": model_id, "dim": _CLIP_MODEL_DIMS[model_id],
                        "warning": "切换模型后需重建视觉索引"})

    return bp


import re as _re
_SETTING_KEY_RE = _re.compile(r'[^a-zA-Z0-9_]')


def _sanitize_setting_key(key: str) -> str:
    return _SETTING_KEY_RE.sub('', key)


def _load_json_setting(key: str):
    """Load a JSON setting from the settings directory."""
    import os
    key = _sanitize_setting_key(key)
    if not key:
        return None
    settings_dir = os.environ.get("VE_SETTINGS_DIR", "")
    if not settings_dir:
        return None
    p = Path(settings_dir) / f"{key}.json"
    if not p.exists():
        return None
    try:
        import json as _json
        return _json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_json_setting(key: str, value: dict):
    """Save a JSON setting to the settings directory."""
    import os, json as _json
    key = _sanitize_setting_key(key)
    if not key:
        return
    settings_dir = os.environ.get("VE_SETTINGS_DIR", "")
    if not settings_dir:
        return
    d = Path(settings_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(_json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _resolve_google_client_id() -> str:
    """Resolve Google OAuth Client ID from environment."""
    import os
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def _resolve_google_client_secret() -> str:
    """Resolve Google OAuth Client Secret from environment."""
    import os
    return os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

