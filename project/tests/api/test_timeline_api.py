"""API tests for multi-track timeline endpoints (C4).

Tests 7: create / get / add_track / update_track / add_clip / split / locked_reject
"""

import json
import os
import tempfile

import pytest

from flask import Flask


@pytest.fixture
def app(tmp_path):
    """Create a Flask app with timeline blueprint wired to a temp DB."""
    # Set DB path to temp dir
    db_path = str(tmp_path / "timeline_test.db")
    os.environ["VIDEOEDITOR_TIMELINE_DB"] = db_path

    from modules.app_api.routes.timeline_routes import create_timeline_blueprint

    flask_app = Flask(__name__)
    bp = create_timeline_blueprint(
        project_dir_getter=lambda: tmp_path,
        workflow_state_getter=lambda: None,
    )
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True
    yield flask_app

    os.environ.pop("VIDEOEDITOR_TIMELINE_DB", None)


@pytest.fixture
def client(app):
    return app.test_client()


SID = "test-session-001"


def test_create_timeline(client):
    """POST /api/review/{id}/timeline creates a new timeline (idempotent)."""
    resp = client.post(f"/api/review/{SID}/timeline")
    data = resp.get_json()
    assert resp.status_code == 201
    assert data["success"] is True
    assert "timeline_id" in data

    # Duplicate creation is idempotent (returns 200, not 409)
    # After adding a track, creation returns existing timeline
    client.post(f"/api/review/{SID}/timeline/tracks", json={"track_type": "video"})
    resp2 = client.post(f"/api/review/{SID}/timeline")
    assert resp2.status_code == 200
    assert resp2.get_json()["timeline_id"] is not None


def test_get_timeline(client):
    """GET /api/review/{id}/timeline returns nested tracks+clips."""
    # Create timeline + add track + add clip
    client.post(f"/api/review/{SID}/timeline")
    track_resp = client.post(
        f"/api/review/{SID}/timeline/tracks",
        json={"track_type": "video", "label": "V1"},
    )
    track_id = track_resp.get_json()["track_id"]
    client.post(
        f"/api/review/{SID}/timeline/clips",
        json={"track_id": track_id, "start_ms": 0, "end_ms": 5000},
    )

    resp = client.get(f"/api/review/{SID}/timeline")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert len(data["tracks"]) == 1
    assert data["tracks"][0]["track_type"] == "video"
    assert len(data["tracks"][0]["clips"]) == 1
    assert data["duration_ms"] == 5000


def test_add_track(client):
    """POST /api/review/{id}/timeline/tracks adds a track."""
    client.post(f"/api/review/{SID}/timeline")
    resp = client.post(
        f"/api/review/{SID}/timeline/tracks",
        json={"track_type": "audio", "label": "BGM"},
    )
    data = resp.get_json()
    assert resp.status_code == 201
    assert "track_id" in data


def test_update_track(client):
    """PATCH /api/review/{id}/timeline/tracks/{id} updates properties."""
    client.post(f"/api/review/{SID}/timeline")
    track_resp = client.post(
        f"/api/review/{SID}/timeline/tracks",
        json={"track_type": "audio", "label": "BGM"},
    )
    track_id = track_resp.get_json()["track_id"]

    resp = client.patch(
        f"/api/review/{SID}/timeline/tracks/{track_id}",
        json={"muted": True, "volume": 0.5},
    )
    assert resp.status_code == 200
    assert resp.get_json()["updated"] is True


def test_add_clip(client):
    """POST /api/review/{id}/timeline/clips adds a clip."""
    client.post(f"/api/review/{SID}/timeline")
    track_resp = client.post(
        f"/api/review/{SID}/timeline/tracks",
        json={"track_type": "video", "label": "V1"},
    )
    track_id = track_resp.get_json()["track_id"]

    resp = client.post(
        f"/api/review/{SID}/timeline/clips",
        json={
            "track_id": track_id,
            "start_ms": 0,
            "end_ms": 3000,
            "source_path": "/tmp/clip.mp4",
        },
    )
    data = resp.get_json()
    assert resp.status_code == 201
    assert "clip_id" in data


def test_split_clip(client):
    """POST /api/review/{id}/timeline/clips/{id}/split returns two clip IDs."""
    client.post(f"/api/review/{SID}/timeline")
    track_resp = client.post(
        f"/api/review/{SID}/timeline/tracks",
        json={"track_type": "video", "label": "V1"},
    )
    track_id = track_resp.get_json()["track_id"]
    clip_resp = client.post(
        f"/api/review/{SID}/timeline/clips",
        json={"track_id": track_id, "start_ms": 0, "end_ms": 6000},
    )
    clip_id = clip_resp.get_json()["clip_id"]

    resp = client.post(
        f"/api/review/{SID}/timeline/clips/{clip_id}/split",
        json={"at_ms": 3000},
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert "left_clip_id" in data
    assert "right_clip_id" in data
    assert data["left_clip_id"] != data["right_clip_id"]


def test_locked_track_reject(client):
    """Operations on locked tracks return 403."""
    client.post(f"/api/review/{SID}/timeline")
    track_resp = client.post(
        f"/api/review/{SID}/timeline/tracks",
        json={"track_type": "video", "label": "V1"},
    )
    track_id = track_resp.get_json()["track_id"]

    # Lock the track
    client.patch(
        f"/api/review/{SID}/timeline/tracks/{track_id}",
        json={"locked": True},
    )

    # Attempt to delete locked track → 403
    resp = client.delete(f"/api/review/{SID}/timeline/tracks/{track_id}")
    assert resp.status_code == 403
    assert "locked" in resp.get_json()["error"].lower()

    # Attempt to add clip to locked track → 403
    resp2 = client.post(
        f"/api/review/{SID}/timeline/clips",
        json={"track_id": track_id, "start_ms": 0, "end_ms": 1000},
    )
    assert resp2.status_code == 403
