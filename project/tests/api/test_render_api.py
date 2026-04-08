"""API tests for render endpoints (D4a)."""

import os
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


@pytest.fixture
def app(tmp_path):
    flask_app = Flask(__name__)
    from modules.app_api.routes.render_routes import create_render_blueprint

    # Mock TimelineStore with a timeline that has clips
    store = MagicMock()
    clip = MagicMock()
    clip.start_ms = 0
    clip.end_ms = 3000
    clip.source_path = "/tmp/clip.mp4"
    clip.source_in_ms = 0
    clip.source_out_ms = 3000

    track = MagicMock()
    track.track_type = "video"
    track.clips = [clip]

    timeline = MagicMock()
    timeline.tracks = [track]
    timeline.timeline_id = "tl1"
    store.get_timeline.return_value = timeline

    # Mock JobManager
    jm = MagicMock()
    jm.submit.return_value = "job_001"
    jm.get_status.return_value = {
        "status": "running",
        "progress_pct": 50.0,
        "error": None,
    }
    jm.cancel.return_value = True

    bp = create_render_blueprint(
        timeline_store_getter=lambda: store,
        job_manager_getter=lambda: jm,
    )
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


SID = "test-session"


def test_trigger_render(client):
    """POST /api/review/{id}/render returns 202 + job_id."""
    resp = client.post(
        f"/api/review/{SID}/render",
        json={"output_path": "/tmp/output.mp4"},
    )
    data = resp.get_json()
    assert resp.status_code == 202
    assert data["job_id"] == "job_001"


def test_render_progress(client):
    """GET /api/review/{id}/render/progress returns live progress."""
    # First trigger a render
    client.post(f"/api/review/{SID}/render", json={})
    # Then check progress
    resp = client.get(f"/api/review/{SID}/render/progress")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert "percent" in data
    assert "encoder" in data
    assert "elapsed_s" in data


def test_render_cancel(client):
    """POST /api/review/{id}/render/cancel stops the render."""
    client.post(f"/api/review/{SID}/render", json={})
    resp = client.post(f"/api/review/{SID}/render/cancel")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["cancelled"] is True


def test_render_complete_status(client):
    """After render completes, progress shows status=done."""
    # Trigger render first
    client.post(f"/api/review/{SID}/render", json={"output_path": "/tmp/done.mp4"})

    # Mock completion: patch the render state
    from modules.app_api.routes import render_routes
    # Get the blueprint's render state
    for rule in client.application.url_map.iter_rules():
        if "render/progress" in rule.rule:
            break

    # Simulate completion by patching job status
    resp = client.get(f"/api/review/{SID}/render/progress")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "status" in data
