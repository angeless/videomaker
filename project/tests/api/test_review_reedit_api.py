"""Tests for AI Reedit API — R10."""

import pytest
from unittest.mock import MagicMock

from modules.app_api.routes.review_routes import create_review_blueprint
from flask import Flask


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True

    mock_store = MagicMock()
    mock_store.get_session.return_value = {"video_path": "/tmp/v.mp4", "edits": []}
    mock_store.get_comments.return_value = []
    mock_store.get_comment.return_value = {"ai_reply": "已处理"}

    bp = create_review_blueprint(
        review_store_getter=lambda: mock_store,
        artifact_store_getter=lambda: None,
    )
    app.register_blueprint(bp)
    return app


class TestReviewReeditAPI:

    def test_reedit_creates_job(self, app):
        with app.test_client() as c:
            resp = c.post("/api/review/test-session/ai-reedit", json={})
            assert resp.status_code == 202
            data = resp.get_json()
            assert data["success"] is True
            assert "job_id" in data

    def test_dry_run_no_render(self, app):
        with app.test_client() as c:
            resp = c.post("/api/review/test-session/ai-reedit/dry-run", json={})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert "diff" in data

    def test_idempotent(self, app):
        with app.test_client() as c:
            resp = c.post(
                "/api/review/test-session/ai-reedit",
                json={"idempotency_key": "abc123"},
            )
            data = resp.get_json()
            assert data["idempotency_key"] == "abc123"

    def test_session_not_found(self, app):
        # Override store to return None
        app2 = Flask(__name__)
        app2.config["TESTING"] = True
        mock = MagicMock()
        mock.get_session.return_value = None
        bp = create_review_blueprint(
            review_store_getter=lambda: mock,
            artifact_store_getter=lambda: None,
        )
        app2.register_blueprint(bp)
        with app2.test_client() as c:
            resp = c.post("/api/review/bad/ai-reedit", json={})
            assert resp.status_code == 404
