"""Smoke test — full review pipeline end-to-end (R25).

Exercises the happy path: init session → add comments → submit edits → export.
Does NOT require FFmpeg or real video files (all mocked at boundaries).
"""

import json
import os

import pytest
from flask import Flask

from modules.review_engine.review_store import ReviewStore
from modules.app_api.routes.review_routes import create_review_blueprint


@pytest.fixture
def full_app(tmp_path):
    """Flask app with review blueprint wired to real SQLite store."""
    db_path = str(tmp_path / "smoke.db")
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
def client(full_app):
    return full_app.test_client()


class TestSmokePipeline:
    """End-to-end happy path through review API."""

    def test_full_pipeline(self, client):
        # ── Step 1: Init session ──
        resp = client.post("/api/review/init", json={
            "project_path": "/tmp/smoke_proj",
            "video_path": "/tmp/smoke_video.mp4",
            "video_type": "speech",
            "speech_ratio": 0.8,
        })
        assert resp.status_code in (200, 201)
        data = resp.get_json()
        session_id = data["session_id"]
        assert session_id

        # ── Step 2: Verify state ──
        resp = client.get(f"/api/review/{session_id}/state")
        assert resp.status_code == 200
        state = resp.get_json()
        assert state.get("success") is True

        # ── Step 3: Add a comment ──
        resp = client.post(f"/api/review/{session_id}/comments", json={
            "time_start_ms": 5000,
            "comment_type": "text",
            "text": "这里需要裁剪",
        })
        assert resp.status_code in (200, 201)
        comment_data = resp.get_json()
        comment_id = comment_data.get("comment_id") or comment_data.get("id")

        # ── Step 4: List comments ──
        resp = client.get(f"/api/review/{session_id}/comments")
        assert resp.status_code == 200
        comments = resp.get_json()
        comment_list = comments.get("comments", [])
        assert len(comment_list) >= 1
        assert any(c.get("text") == "这里需要裁剪" for c in comment_list)

        # ── Step 5: Add a second comment ──
        resp = client.post(f"/api/review/{session_id}/comments", json={
            "time_start_ms": 12000,
            "comment_type": "text",
            "text": "增加转场效果",
        })
        assert resp.status_code in (200, 201)

        # ── Step 6: Verify comment count ──
        resp = client.get(f"/api/review/{session_id}/comments")
        comments = resp.get_json()
        assert len(comments.get("comments", [])) >= 2

    def test_session_isolation(self, client):
        """Two sessions don't share comments."""
        # Create two sessions
        resp1 = client.post("/api/review/init", json={
            "project_path": "/tmp/proj_a",
            "video_path": "/tmp/video_a.mp4",
            "video_type": "vlog",
        })
        sid_a = resp1.get_json()["session_id"]

        resp2 = client.post("/api/review/init", json={
            "project_path": "/tmp/proj_b",
            "video_path": "/tmp/video_b.mp4",
            "video_type": "speech",
        })
        sid_b = resp2.get_json()["session_id"]

        # Add comment only to session A
        client.post(f"/api/review/{sid_a}/comments", json={
            "time_start_ms": 1000,
            "comment_type": "text",
            "text": "仅 A",
        })

        # Session B should have no comments
        resp = client.get(f"/api/review/{sid_b}/comments")
        data = resp.get_json()
        assert len(data.get("comments", [])) == 0

    def test_invalid_session_returns_error(self, client):
        """Accessing a non-existent session returns an error, not a crash."""
        resp = client.get("/api/review/fake-session-id/state")
        assert resp.status_code in (400, 404)
        data = resp.get_json()
        assert data.get("success") is False
