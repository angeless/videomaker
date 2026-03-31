"""API tests for roughcut_routes (R20-R22)."""

import json

import pytest
from flask import Flask

from modules.review_engine.review_store import ReviewStore
from modules.app_api.routes.roughcut_routes import create_roughcut_blueprint


@pytest.fixture
def app(tmp_path):
    db_path = str(tmp_path / "roughcut.db")
    store = ReviewStore(db_path)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True

    bp = create_roughcut_blueprint(review_store_getter=lambda: store)
    flask_app.register_blueprint(bp)

    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ── R20: init + detect-type + stats ──

class TestRoughcutInit:
    def test_roughcut_api_init_fallback(self, client):
        """Init with detection failure falls back to 'mixed'."""
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/tmp/proj",
            "video_path": "/nonexistent/video.mp4",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert "session_id" in data
        assert data["video_type"] == "mixed"  # fallback

    def test_roughcut_api_init_missing_fields(self, client):
        resp = client.post("/api/roughcut/init", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "MISSING_FIELDS"


class TestRoughcutDetectType:
    def test_roughcut_api_detect_type(self, client):
        # Create session first
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/p", "video_path": "/v.mp4",
        })
        sid = resp.get_json()["session_id"]

        resp2 = client.get(f"/api/roughcut/{sid}/detect-type")
        assert resp2.status_code == 200
        assert "video_type" in resp2.get_json()

    def test_roughcut_api_detect_type_not_found(self, client):
        resp = client.get("/api/roughcut/nonexistent/detect-type")
        assert resp.status_code == 404


class TestRoughcutStats:
    def test_roughcut_api_stats(self, client):
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/p", "video_path": "/v.mp4",
        })
        sid = resp.get_json()["session_id"]

        resp2 = client.get(f"/api/roughcut/{sid}/stats")
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert data["total_comments"] == 0
        assert data["total_versions"] == 0


# ── R21: transcript + fillers ──

class TestRoughcutTranscript:
    def test_roughcut_api_transcript_no_engine(self, client):
        """Without a real video, transcription fails gracefully."""
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/p", "video_path": "/nonexistent.mp4",
        })
        sid = resp.get_json()["session_id"]

        resp2 = client.get(f"/api/roughcut/{sid}/transcript")
        # Should fail with TRANSCRIPTION_FAILED since file doesn't exist
        assert resp2.status_code == 500

    def test_roughcut_api_fillers_no_transcript(self, client):
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/p", "video_path": "/v.mp4",
        })
        sid = resp.get_json()["session_id"]

        resp2 = client.get(f"/api/roughcut/{sid}/fillers")
        assert resp2.status_code == 200
        assert resp2.get_json()["fillers"] == []


# ── R22: scenes + select + generate ──

class TestRoughcutScenes:
    def test_roughcut_api_scenes_not_found(self, client):
        resp = client.get("/api/roughcut/nonexistent/scenes")
        assert resp.status_code == 404

    def test_roughcut_api_generate_no_edits(self, client):
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/p", "video_path": "/v.mp4",
        })
        sid = resp.get_json()["session_id"]

        resp2 = client.post(f"/api/roughcut/{sid}/generate", json={})
        assert resp2.status_code == 400
        assert resp2.get_json()["error"] == "NO_EDITS"

    def test_roughcut_api_scenes_select_no_scenes(self, client):
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/p", "video_path": "/v.mp4",
        })
        sid = resp.get_json()["session_id"]

        resp2 = client.post(f"/api/roughcut/{sid}/scenes/select", json={
            "selected": [0, 2],
        })
        assert resp2.status_code == 400
        assert resp2.get_json()["error"] == "NO_SCENES"
