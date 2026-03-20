#!/usr/bin/env python3
"""Tests for YouTube OAuth 2.0 endpoints (T-0801)."""

import json
import pytest
from unittest.mock import MagicMock, patch

from modules.app_api.routes.settings_routes import create_settings_blueprint, _oauth_pending
from modules.app_api.secure_store import NullSecretStore


@pytest.fixture
def mock_store():
    """In-memory secret store for testing."""
    store = MagicMock()
    store.get.return_value = ""
    store.set.return_value = True
    store.delete.return_value = True
    return store


@pytest.fixture
def app(mock_store):
    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True
    bp = create_settings_blueprint(
        request_is_local=lambda: True,
        require_local_token_getter=lambda: False,
        require_csrf_getter=lambda: False,
        local_token_getter=lambda: "",
        local_csrf_token_getter=lambda: "",
        load_ai_settings=lambda: {},
        save_ai_settings=lambda p: p,
        apply_ai_env=lambda p: None,
        public_ai_settings=lambda p: p,
        load_ui_settings=lambda: {},
        save_ui_settings=lambda p: p,
        load_publish_settings=lambda: {},
        save_publish_settings=lambda p: p,
        mask_publish_connectors=lambda p: p,
        secret_store_getter=lambda: mock_store,
    )
    app.register_blueprint(bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestYouTubeOAuthStatus:
    def test_not_connected_when_no_token(self, client, mock_store):
        mock_store.get.return_value = ""
        resp = client.get("/api/settings/oauth/youtube/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["connected"] is False

    def test_connected_when_token_exists(self, client, mock_store):
        mock_store.get.return_value = json.dumps({
            "access_token": "ya29.test",
            "refresh_token": "1//test",
            "channel_name": "TestChannel",
            "expires_at": 9999999999,
            "connected_at": 1000000000,
        })
        resp = client.get("/api/settings/oauth/youtube/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["connected"] is True
        assert data["channel_name"] == "TestChannel"


class TestYouTubeOAuthStart:
    def test_start_without_client_id_fails(self, client):
        with patch.dict("os.environ", {}, clear=True):
            resp = client.post("/api/settings/oauth/youtube/start", json={})
            assert resp.status_code == 400
            data = resp.get_json()
            assert "error" in data

    @patch("webbrowser.open")
    def test_start_with_client_id_opens_browser(self, mock_open, client):
        with patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com"}):
            resp = client.post("/api/settings/oauth/youtube/start", json={})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert "auth_url" in data
            assert "test-client-id" in data["auth_url"]
            mock_open.assert_called_once()


class TestYouTubeOAuthCallback:
    def test_callback_invalid_state(self, client):
        resp = client.get("/api/settings/oauth/youtube/callback?code=test&state=invalid")
        assert resp.status_code == 400
        assert "state" in resp.data.decode("utf-8").lower()

    def test_callback_missing_code(self, client):
        _oauth_pending["teststate"] = {"created_at": 9999999999, "redirect_uri": "http://localhost:9527/callback"}
        resp = client.get("/api/settings/oauth/youtube/callback?state=teststate")
        assert resp.status_code == 400
        # State should be consumed
        assert "teststate" not in _oauth_pending

    def test_callback_error_from_google(self, client):
        resp = client.get("/api/settings/oauth/youtube/callback?error=access_denied&state=x")
        assert resp.status_code == 400
        assert "access_denied" in resp.data.decode("utf-8")


class TestYouTubeOAuthDisconnect:
    def test_disconnect_clears_token(self, client, mock_store):
        mock_store.get.return_value = json.dumps({"access_token": "ya29.test", "channel_name": "Ch"})
        resp = client.post("/api/settings/oauth/youtube/disconnect")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        mock_store.delete.assert_called_with("youtube_oauth")
