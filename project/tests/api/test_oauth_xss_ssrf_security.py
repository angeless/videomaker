"""Regression tests for round-9 security findings in settings_routes.

Covers:
- XSS via attacker-controlled `error` param reflected in OAuth callback HTML
- SSRF via user-configurable connector URL pointing at loopback/RFC1918
"""

from unittest.mock import MagicMock

import pytest
from flask import Flask


def _make_app(publish_settings=None):
    flask_app = Flask(__name__)
    from modules.app_api.routes.settings_routes import create_settings_blueprint

    _store = {"publish": publish_settings or {"connectors": {}}}

    # Minimal stubs — the XSS/SSRF paths don't need real dependencies
    bp = create_settings_blueprint(
        request_is_local=lambda: True,
        require_local_token_getter=lambda: False,
        require_csrf_getter=lambda: False,
        local_token_getter=lambda: "",
        local_csrf_token_getter=lambda: "",
        load_ai_settings=lambda: {},
        save_ai_settings=lambda d: None,
        apply_ai_env=lambda d: None,
        public_ai_settings=lambda d: d,
        load_ui_settings=lambda: {},
        save_ui_settings=lambda d: None,
        load_publish_settings=lambda: _store["publish"],
        save_publish_settings=lambda d: _store.update({"publish": {**_store["publish"], **d}}),
        mask_publish_connectors=lambda c: c,
    )
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True
    return flask_app


def test_oauth_callback_escapes_error_param_to_prevent_xss():
    """Attacker-controlled ?error=<script>alert(1)</script> must be escaped."""
    app = _make_app()
    client = app.test_client()
    payload = "<script>alert('XSS')</script>"
    resp = client.get(f"/api/settings/oauth/youtube/callback?error={payload}")
    # The raw <script> tag must NOT appear — it should be escaped to &lt;script&gt;
    body = resp.get_data(as_text=True)
    assert "<script>alert" not in body, "raw <script> reflected — XSS vulnerability"
    # The escaped form should appear
    assert "&lt;script&gt;" in body or "&lt;/script&gt;" in body


def test_oauth_callback_escapes_img_onerror_payload():
    """The img onerror payload (round-9 finding example) must be escaped."""
    app = _make_app()
    client = app.test_client()
    payload = "<img src=x onerror=fetch('//evil')>"
    resp = client.get(f"/api/settings/oauth/youtube/callback?error={payload}")
    body = resp.get_data(as_text=True)
    assert "onerror" not in body or "&lt;img" in body, (
        "img onerror reflected unescaped — XSS vulnerability"
    )


def test_connector_test_rejects_loopback_url():
    """User-supplied URL pointing at 127.0.0.1 must be rejected (SSRF)."""
    app = _make_app({
        "connectors": {"evil": {"endpoint": "http://127.0.0.1:22/ssh-probe"}}
    })
    client = app.test_client()
    resp = client.post("/api/settings/connectors/evil/test")
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.get_data(as_text=True)}"
    data = resp.get_json()
    err = data.get("error", "")
    assert "内网" in err or "loopback" in err.lower() or "禁止" in err, (
        f"expected SSRF rejection message, got: {err}"
    )


def test_connector_test_rejects_aws_metadata_url():
    """URL pointing at AWS metadata service (169.254.169.254) must be rejected."""
    app = _make_app({
        "connectors": {"aws": {"endpoint": "http://169.254.169.254/latest/meta-data/"}}
    })
    client = app.test_client()
    resp = client.post("/api/settings/connectors/aws/test")
    assert resp.status_code == 400


def test_connector_test_rejects_non_http_scheme():
    """file:// and other schemes must be rejected."""
    app = _make_app({
        "connectors": {"file": {"endpoint": "file:///etc/passwd"}}
    })
    client = app.test_client()
    resp = client.post("/api/settings/connectors/file/test")
    assert resp.status_code == 400
