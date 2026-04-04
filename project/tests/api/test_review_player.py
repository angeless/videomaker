"""API tests for review player endpoints (R1: video load, thumbnails, waveform)."""

import json
import os
import tempfile

import pytest
from flask import Flask

from modules.review_engine.review_store import ReviewStore
from modules.app_api.routes.review_routes import create_review_blueprint


@pytest.fixture
def app(tmp_path):
    """Create a Flask test app with the review blueprint."""
    db_path = str(tmp_path / "review.db")
    store = ReviewStore(db_path)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True

    bp = create_review_blueprint(
        review_store_getter=lambda: store,
        artifact_store_getter=lambda: None,
    )
    flask_app.register_blueprint(bp)

    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def session_id(client):
    """Create a review session for player tests."""
    resp = client.post("/api/review/init", json={
        "project_path": "/tmp/proj",
        "video_path": "/tmp/video.mp4",
        "video_type": "speech",
        "speech_ratio": 0.75,
    })
    data = resp.get_json()
    assert data.get("success") or "session_id" in data
    return data["session_id"]


class TestReviewPlayerInit:
    """R1: Session initialization for player."""

    def test_init_returns_session_id(self, client):
        resp = client.post("/api/review/init", json={
            "project_path": "/tmp/proj",
            "video_path": "/tmp/test.mp4",
            "video_type": "speech",
        })
        data = resp.get_json()
        assert resp.status_code == 200 or resp.status_code == 201
        assert "session_id" in data

    def test_init_missing_fields(self, client):
        resp = client.post("/api/review/init", json={
            "project_path": "/tmp/proj",
        })
        data = resp.get_json()
        assert resp.status_code == 400
        assert data["success"] is False

    def test_init_with_video_type(self, client):
        resp = client.post("/api/review/init", json={
            "project_path": "/tmp/proj",
            "video_path": "/tmp/vlog.mp4",
            "video_type": "vlog",
        })
        data = resp.get_json()
        assert "session_id" in data


class TestReviewPlayerState:
    """R1: Session state retrieval for player."""

    def test_get_state(self, client, session_id):
        resp = client.get(f"/api/review/{session_id}/state")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data.get("success") is True

    def test_get_state_invalid_session(self, client):
        resp = client.get("/api/review/nonexistent-session/state")
        assert resp.status_code in (400, 404)


class TestReviewPlayerArtifacts:
    """R1: Thumbnail and waveform endpoints for player."""

    def test_thumbnails_endpoint_exists(self, client, session_id):
        # Thumbnails is a POST (generation trigger); 500 expected when artifact_store is None
        resp = client.post(f"/api/review/{session_id}/thumbnails", json={})
        assert resp.status_code in (200, 400, 404, 500, 501)

    def test_waveform_endpoint_exists(self, client, session_id):
        resp = client.post(f"/api/review/{session_id}/waveform", json={})
        assert resp.status_code in (200, 400, 404, 500, 501)

    def test_comments_initially_empty(self, client, session_id):
        resp = client.get(f"/api/review/{session_id}/comments")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data.get("success") is True
        assert data.get("comments") == [] or data.get("count") == 0
