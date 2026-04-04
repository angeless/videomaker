"""Integration test: AI reedit flow through Flask API.

Tests the full pipeline:
  init → add comments → dry-run diff → ai-reedit → ai-reply → export
"""

import json
import os

import pytest
from flask import Flask

from modules.review_engine.review_store import ReviewStore
from modules.review_engine.artifact_store import ArtifactStore
from modules.app_api.routes.review_routes import create_review_blueprint
from modules.app_api.routes.roughcut_routes import create_roughcut_blueprint


@pytest.fixture
def app(tmp_path):
    """Full app with roughcut + review blueprints sharing one store."""
    db_path = str(tmp_path / "reedit_integration.db")
    project_dir = str(tmp_path / "project")
    os.makedirs(project_dir, exist_ok=True)

    store = ReviewStore(db_path)
    artifact_store = ArtifactStore(project_dir, store)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True

    flask_app.register_blueprint(
        create_roughcut_blueprint(review_store_getter=lambda: store)
    )
    flask_app.register_blueprint(
        create_review_blueprint(
            review_store_getter=lambda: store,
            artifact_store_getter=lambda: artifact_store,
        )
    )
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _init_session(client):
    """Helper: create a session and return session_id."""
    resp = client.post("/api/roughcut/init", json={
        "project_path": "/tmp/proj",
        "video_path": "/nonexistent/test.mp4",
    })
    assert resp.status_code == 201
    data = resp.get_json()
    return data["session_id"]


def _add_comment(client, session_id, text, time_ms=5000):
    """Helper: add a comment to session."""
    resp = client.post(f"/api/review/{session_id}/comments", json={
        "text": text,
        "time_start_ms": time_ms,
        "comment_type": "text",
        "author": "test_user",
    })
    assert resp.status_code in (200, 201)
    return resp.get_json()


class TestAiReeditFlow:
    """Integration: comment → dry-run → ai-reedit → reply → export."""

    def test_dry_run_returns_diff(self, client):
        """Dry run should return diff without creating a new version."""
        session_id = _init_session(client)
        _add_comment(client, session_id, "删掉这一段")

        resp = client.post(f"/api/review/{session_id}/ai-reedit/dry-run", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "diff" in data
        assert "summary" in data

    def test_dry_run_no_comments(self, client):
        """Dry run with no comments should return empty diff."""
        session_id = _init_session(client)

        resp = client.post(f"/api/review/{session_id}/ai-reedit/dry-run", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["diff"] == []

    def test_ai_reedit_returns_job(self, client):
        """AI reedit should return 202 with job_id."""
        session_id = _init_session(client)
        _add_comment(client, session_id, "这段太长了，缩短一下")

        resp = client.post(f"/api/review/{session_id}/ai-reedit", json={
            "idempotency_key": "test-key-001",
        })
        assert resp.status_code == 202
        data = resp.get_json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["idempotency_key"] == "test-key-001"

    def test_ai_reply_for_comment(self, client):
        """After adding a comment, ai-reply endpoint should return."""
        session_id = _init_session(client)
        comment_data = _add_comment(client, session_id, "加个转场")

        comment_id = comment_data.get("comment_id") or comment_data.get("id")
        if not comment_id:
            pytest.skip("Comment ID not returned by API")

        resp = client.get(f"/api/review/{session_id}/comments/{comment_id}/ai-reply")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "ai_reply" in data

    def test_export_after_comments(self, client):
        """Export comments in JSON/CSV/EDL after adding some."""
        session_id = _init_session(client)
        _add_comment(client, session_id, "调色太暗了", time_ms=2000)
        _add_comment(client, session_id, "BGM太吵", time_ms=8000)

        for fmt in ("json", "csv", "edl"):
            resp = client.get(
                f"/api/review/{session_id}/comments/export?format={fmt}"
            )
            assert resp.status_code == 200, f"Export {fmt} failed"
            data = resp.get_json()
            assert data["success"] is True
            assert data["format"] == fmt
            assert data["count"] == 2
            assert len(data["data"]) > 0

    def test_reedit_missing_session(self, client):
        """AI reedit on non-existent session returns 404."""
        resp = client.post("/api/review/nonexistent/ai-reedit", json={})
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"] == "SESSION_NOT_FOUND"
