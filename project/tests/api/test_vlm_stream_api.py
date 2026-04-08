"""API tests for video stream analysis endpoints (B4a)."""

import pytest
from unittest.mock import MagicMock, patch

from flask import Flask


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    from modules.app_api.routes.vlm_routes import create_vlm_blueprint

    store = MagicMock()
    store.get_session.return_value = {"id": "s1", "video_path": "/tmp/v.mp4"}
    adapter = MagicMock()
    adapter.get_model_info.return_value = {"available": True, "provider": "stub", "model": "v1"}

    bp = create_vlm_blueprint(
        review_store_getter=lambda: store,
        vlm_adapter_getter=lambda: adapter,
    )
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


SID = "test-session"


def test_api_trigger_stream_analysis(client):
    """POST /api/review/{id}/vlm/analyze-stream returns 202 + job_id."""
    resp = client.post(
        f"/api/review/{SID}/vlm/analyze-stream",
        json={"video_path": "/tmp/test.mp4"},
    )
    data = resp.get_json()
    assert resp.status_code == 202
    assert "job_id" in data


def test_api_stream_analysis_not_found(client):
    """GET stream-analysis returns 404 if no analysis has been run."""
    resp = client.get(f"/api/review/{SID}/vlm/stream-analysis")
    assert resp.status_code == 404


def test_api_scene_summaries_not_found(client):
    """GET scene-summaries returns 404 if no analysis has been run."""
    resp = client.get(f"/api/review/{SID}/vlm/scene-summaries")
    assert resp.status_code == 404
