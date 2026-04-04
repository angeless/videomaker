"""Integration test: enhance flow through Flask API.

Tests enhancement endpoints wired to real ReviewStore:
  audio / tts / bgm / transition / reframe
"""

import json
import os

import pytest
from flask import Flask

from modules.review_engine.review_store import ReviewStore
from modules.app_api.routes.enhance_routes import create_enhance_blueprint
from modules.app_api.routes.roughcut_routes import create_roughcut_blueprint


@pytest.fixture
def app(tmp_path):
    """Flask app with roughcut + enhance blueprints."""
    db_path = str(tmp_path / "enhance_integration.db")
    store = ReviewStore(db_path)
    jobs = {}

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True

    flask_app.register_blueprint(
        create_roughcut_blueprint(review_store_getter=lambda: store)
    )
    flask_app.register_blueprint(
        create_enhance_blueprint(
            review_store_getter=lambda: store,
            jobs_getter=lambda: jobs,
        )
    )
    flask_app.config["_jobs"] = jobs
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _init_session(client):
    resp = client.post("/api/roughcut/init", json={
        "project_path": "/tmp/proj",
        "video_path": "/nonexistent/test.mp4",
    })
    assert resp.status_code == 201
    return resp.get_json()["session_id"]


class TestEnhanceFlow:
    """Integration: session → enhance endpoints."""

    @pytest.mark.parametrize("endpoint,params", [
        ("/api/review/enhance/audio", {"denoise": True, "loudnorm": True}),
        ("/api/review/enhance/tts", {"voice": "zh-female", "segments": []}),
        ("/api/review/enhance/bgm", {"source": "library", "fade_in": 2.0}),
        ("/api/review/enhance/transition", {"effect": "crossfade", "duration": 0.5}),
        ("/api/review/enhance/reframe", {"platform": "tiktok"}),
    ])
    def test_enhance_endpoint_returns_job(self, client, endpoint, params):
        """Each enhance endpoint should return 202 + job_id for valid session."""
        session_id = _init_session(client)
        payload = {"session_id": session_id, **params}

        resp = client.post(endpoint, json=payload)
        assert resp.status_code == 202, f"{endpoint} returned {resp.status_code}"
        data = resp.get_json()
        assert data["success"] is True
        assert "job_id" in data
        assert data["status"] == "queued"

    def test_enhance_missing_session_id(self, client):
        """Enhance without session_id returns 400."""
        resp = client.post("/api/review/enhance/audio", json={"denoise": True})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "MISSING_PARAM"

    def test_enhance_invalid_session(self, client):
        """Enhance with non-existent session returns 404."""
        resp = client.post("/api/review/enhance/audio", json={
            "session_id": "nonexistent_session",
        })
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"] == "SESSION_NOT_FOUND"

    def test_multiple_enhancements_independent_jobs(self, client, app):
        """Multiple enhance calls produce distinct job IDs."""
        session_id = _init_session(client)

        job_ids = set()
        for ep in ("/api/review/enhance/audio", "/api/review/enhance/tts"):
            resp = client.post(ep, json={"session_id": session_id, "voice": "zh-male"})
            assert resp.status_code == 202
            job_ids.add(resp.get_json()["job_id"])

        assert len(job_ids) == 2, "Each enhancement should get a unique job_id"
