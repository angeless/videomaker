"""Tests for Enhance API — R22."""

import pytest
from unittest.mock import MagicMock

from modules.app_api.routes.enhance_routes import create_enhance_blueprint
from flask import Flask


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True

    mock_store = MagicMock()
    mock_store.get_session.return_value = {"video_path": "/tmp/v.mp4"}

    jobs = {}

    bp = create_enhance_blueprint(
        review_store_getter=lambda: mock_store,
        jobs_getter=lambda: jobs,
    )
    app.register_blueprint(bp)
    return app


class TestEnhanceAPI:

    @pytest.mark.parametrize("endpoint", [
        "/api/review/enhance/audio",
        "/api/review/enhance/tts",
        "/api/review/enhance/bgm",
        "/api/review/enhance/transition",
        "/api/review/enhance/reframe",
    ])
    def test_enhance_returns_202(self, app, endpoint):
        with app.test_client() as c:
            resp = c.post(endpoint, json={"session_id": "s1"})
            assert resp.status_code == 202
            data = resp.get_json()
            assert data["success"] is True
            assert "job_id" in data

    def test_missing_session_id(self, app):
        with app.test_client() as c:
            resp = c.post("/api/review/enhance/audio", json={})
            assert resp.status_code == 400
