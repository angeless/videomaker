"""API tests for review_routes (R26-R28)."""

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
    """Create a session and return its ID."""
    resp = client.post("/api/review/init", json={
        "project_path": "/tmp/proj",
        "video_path": "/tmp/video.mp4",
        "video_type": "speech",
        "speech_ratio": 0.75,
    })
    return resp.get_json()["session_id"]


# ── R26: init + state + comments ──

class TestReviewInit:
    def test_review_api_init_creates_session(self, client):
        resp = client.post("/api/review/init", json={
            "project_path": "/p", "video_path": "/v.mp4", "video_type": "scenic",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert "session_id" in data

    def test_review_api_init_missing_fields(self, client):
        resp = client.post("/api/review/init", json={"project_path": "/p"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"] == "MISSING_FIELDS"
        assert data["code"] == 400
        assert "trace_id" in data


class TestReviewState:
    def test_review_api_get_state(self, client, session_id):
        resp = client.get(f"/api/review/{session_id}/state")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["session"]["video_type"] == "speech"

    def test_review_api_state_not_found(self, client):
        resp = client.get("/api/review/nonexistent/state")
        assert resp.status_code == 404


class TestReviewComments:
    def test_review_api_add_and_list_comments(self, client, session_id):
        resp = client.post(f"/api/review/{session_id}/comments", json={
            "time_start_ms": 1500,
            "comment_type": "text",
            "text": "Too slow here",
        })
        assert resp.status_code == 201
        assert "comment_id" in resp.get_json()

        resp2 = client.get(f"/api/review/{session_id}/comments")
        comments = resp2.get_json()["comments"]
        assert len(comments) == 1
        assert comments[0]["text"] == "Too slow here"

    def test_review_api_patch_comment(self, client, session_id):
        resp = client.post(f"/api/review/{session_id}/comments", json={
            "time_start_ms": 0, "comment_type": "text", "text": "Original",
        })
        cid = resp.get_json()["comment_id"]

        resp2 = client.patch(f"/api/review/comments/{cid}", json={
            "text": "Updated", "status": "resolved",
        })
        assert resp2.status_code == 200

    def test_review_api_delete_comment(self, client, session_id):
        resp = client.post(f"/api/review/{session_id}/comments", json={
            "time_start_ms": 0, "comment_type": "text", "text": "Remove me",
        })
        cid = resp.get_json()["comment_id"]

        resp2 = client.delete(f"/api/review/comments/{cid}")
        assert resp2.status_code == 200
        assert resp2.get_json()["deleted"] is True


# ── R27: versions + diff + rollback ──

class TestReviewVersions:
    def test_review_api_list_versions(self, client, session_id, app):
        # Create version via store directly
        with app.app_context():
            store = app.extensions.get("review_store")
        # Use the API indirectly: versions are created by the store
        resp = client.get(f"/api/review/{session_id}/versions")
        assert resp.status_code == 200
        assert "versions" in resp.get_json()

    def test_review_api_diff_versions(self, client, session_id, app):
        # We need versions in the store; create them via the store fixture
        resp = client.get(f"/api/review/{session_id}/diff/1/2")
        # Both versions don't exist → error
        assert resp.status_code == 404

    def test_review_api_rollback_nonexistent(self, client, session_id):
        resp = client.post(f"/api/review/{session_id}/rollback/99")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "ROLLBACK_FAILED"

    def test_review_api_get_version_not_found(self, client, session_id):
        resp = client.get(f"/api/review/{session_id}/versions/99")
        assert resp.status_code == 404


# ── R28: thumbnails + waveform stubs ──

class TestReviewStubs:
    def test_review_api_thumbnails_stub(self, client, session_id):
        resp = client.post(f"/api/review/{session_id}/thumbnails")
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "done"
        assert "job_id" in data

    def test_review_api_waveform_stub(self, client, session_id):
        resp = client.post(f"/api/review/{session_id}/waveform")
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "done"
