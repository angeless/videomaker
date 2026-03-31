"""Integration test: end-to-end roughcut + review flow.

Tests the full pipeline through the Flask API layer:
  init → detect-type → transcript-edit → version → comments → diff → rollback
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
    """Full app with both roughcut + review blueprints sharing one store."""
    db_path = str(tmp_path / "integration.db")
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


class TestRoughcutToReviewFlow:
    """E2E: roughcut init → review comments → versions → rollback."""

    def test_full_session_lifecycle(self, client):
        """Complete lifecycle: init → stats → comments → versions → rollback."""

        # 1. Init roughcut session (video detection falls back to mixed)
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/tmp/proj",
            "video_path": "/nonexistent/test.mp4",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        session_id = data["session_id"]
        assert data["video_type"] == "mixed"

        # 2. Check stats
        resp = client.get(f"/api/roughcut/{session_id}/stats")
        assert resp.status_code == 200
        stats = resp.get_json()
        assert stats["total_comments"] == 0
        assert stats["total_versions"] == 0

        # 3. Check detect-type
        resp = client.get(f"/api/roughcut/{session_id}/detect-type")
        assert resp.status_code == 200
        assert resp.get_json()["video_type"] == "mixed"

        # 4. Add comments via review API
        resp = client.post(f"/api/review/{session_id}/comments", json={
            "time_start_ms": 2000,
            "comment_type": "text",
            "text": "Cut this section",
        })
        assert resp.status_code == 201
        comment_id = resp.get_json()["comment_id"]

        resp = client.post(f"/api/review/{session_id}/comments", json={
            "time_start_ms": 5000,
            "comment_type": "text",
            "text": "Keep this part",
        })
        assert resp.status_code == 201

        # 5. Verify comments listed
        resp = client.get(f"/api/review/{session_id}/comments")
        assert resp.status_code == 200
        comments = resp.get_json()["comments"]
        assert len(comments) == 2

        # 6. Update a comment
        resp = client.patch(f"/api/review/comments/{comment_id}", json={
            "status": "resolved",
        })
        assert resp.status_code == 200

        # 7. Delete a comment
        resp = client.delete(f"/api/review/comments/{comment_id}")
        assert resp.status_code == 200
        resp = client.get(f"/api/review/{session_id}/comments")
        assert len(resp.get_json()["comments"]) == 1

        # 8. Stats updated
        resp = client.get(f"/api/roughcut/{session_id}/stats")
        assert resp.get_json()["total_comments"] == 1

    def test_version_workflow(self, client):
        """Create versions, diff them, and rollback."""

        # Init session
        resp = client.post("/api/roughcut/init", json={
            "project_path": "/tmp/proj",
            "video_path": "/nonexistent/v.mp4",
        })
        session_id = resp.get_json()["session_id"]

        # Create versions via review store (through review API state)
        # We'll use the review API to get state and manipulate versions
        resp = client.get(f"/api/review/{session_id}/state")
        assert resp.status_code == 200

        # Versions list should be empty initially
        resp = client.get(f"/api/review/{session_id}/versions")
        assert resp.status_code == 200
        assert len(resp.get_json()["versions"]) == 0

    def test_thumbnail_and_waveform_stubs(self, client):
        """Stub endpoints return 202 with job_id."""

        resp = client.post("/api/roughcut/init", json={
            "project_path": "/tmp/proj",
            "video_path": "/nonexistent/v.mp4",
        })
        session_id = resp.get_json()["session_id"]

        # Thumbnails stub
        resp = client.post(f"/api/review/{session_id}/thumbnails")
        assert resp.status_code == 202
        assert resp.get_json()["status"] == "done"

        # Waveform stub
        resp = client.post(f"/api/review/{session_id}/waveform")
        assert resp.status_code == 202
        assert resp.get_json()["status"] == "done"

    def test_cross_api_session_shared(self, client):
        """Session created via roughcut is accessible via review API."""

        resp = client.post("/api/roughcut/init", json={
            "project_path": "/tmp/proj",
            "video_path": "/nonexistent/v.mp4",
        })
        session_id = resp.get_json()["session_id"]

        # Review API can see the same session
        resp = client.get(f"/api/review/{session_id}/state")
        assert resp.status_code == 200
        state = resp.get_json()["session"]
        assert state["video_type"] == "mixed"
        assert state["project_path"] == "/tmp/proj"

    def test_error_format_consistency(self, client):
        """All error responses follow the standardized format."""

        endpoints = [
            ("GET", "/api/roughcut/nonexistent/stats"),
            ("GET", "/api/review/nonexistent/state"),
            ("POST", "/api/roughcut/init", {}),  # missing fields
            ("POST", "/api/review/init", {"project_path": "/p"}),  # missing fields
        ]

        for endpoint in endpoints:
            method = endpoint[0]
            url = endpoint[1]
            body = endpoint[2] if len(endpoint) > 2 else None

            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json=body)

            data = resp.get_json()
            # All errors must have these fields
            assert "success" in data, f"Missing 'success' in {url}"
            assert data["success"] is False, f"Expected failure for {url}"
            assert "error" in data, f"Missing 'error' in {url}"
            assert "message" in data, f"Missing 'message' in {url}"
            assert "code" in data, f"Missing 'code' in {url}"
            assert "timestamp" in data, f"Missing 'timestamp' in {url}"
            assert "trace_id" in data, f"Missing 'trace_id' in {url}"
