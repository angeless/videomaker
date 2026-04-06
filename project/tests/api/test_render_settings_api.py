"""API tests for render settings endpoints (D5)."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask


@pytest.fixture
def app(tmp_path):
    """Flask app with system blueprint (render settings in temp dir)."""
    # Point render settings to temp dir
    settings_file = str(tmp_path / "render_settings.json")

    from modules.app_api.routes import system_routes
    original = system_routes._RENDER_SETTINGS_FILE

    flask_app = Flask(__name__)
    from modules.app_api.routes.system_routes import create_system_blueprint
    bp = create_system_blueprint(
        state_dict_getter=lambda: {},
        system_load_snapshot_getter=lambda: {},
        overloaded_getter=lambda: False,
        running_heavy_jobs_getter=lambda: [],
        task_queue_snapshot_getter=lambda: {},
        preflight_snapshot_getter=lambda force: {},
    )
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True

    # Monkey-patch the settings file path
    system_routes._RENDER_SETTINGS_FILE = settings_file
    yield flask_app
    system_routes._RENDER_SETTINGS_FILE = original


@pytest.fixture
def client(app):
    return app.test_client()


def test_encoder_options(client):
    """GET /api/settings/render returns available encoders based on hardware."""
    with patch("modules.hardware.detector.get_system_profile") as mock_profile:
        profile = MagicMock()
        profile.gpu.has_videotoolbox = True
        profile.gpu.has_nvenc = False
        profile.gpu.has_vaapi = False
        mock_profile.return_value = profile

        resp = client.get("/api/settings/render")
        data = resp.get_json()
        assert data["ok"] is True
        assert "libx264" in data["available_encoders"]
        assert "h264_videotoolbox" in data["available_encoders"]
        assert "h264_nvenc" not in data["available_encoders"]


def test_quality_mapping(client):
    """Quality presets map to specific CRF values."""
    resp = client.get("/api/settings/render")
    data = resp.get_json()
    presets = data["quality_presets"]
    assert presets["high"]["crf"] == 15
    assert presets["balanced"]["crf"] == 18
    assert presets["fast"]["crf"] == 23


def test_persist(client):
    """PUT /api/settings/render persists settings across requests."""
    # Save new settings
    resp = client.put(
        "/api/settings/render",
        json={"encoder": "h264_videotoolbox", "quality_preset": "high"},
    )
    assert resp.get_json()["ok"] is True

    # Load and verify
    resp2 = client.get("/api/settings/render")
    data = resp2.get_json()
    assert data["settings"]["encoder"] == "h264_videotoolbox"
    assert data["settings"]["quality_preset"] == "high"
    # Default values preserved
    assert data["settings"]["resolution"] == "1080x1920"
    assert data["settings"]["parallel_render"] is True
