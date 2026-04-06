"""Integration tests for multi-track timeline (C7).

End-to-end: TimelineStore → TimelineOps → Timeline API.
"""

import os

import pytest
from flask import Flask


@pytest.fixture
def app_with_timeline(tmp_path):
    """Flask app with timeline API backed by temp DB."""
    db_path = str(tmp_path / "test_timeline.db")
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
def client(app_with_timeline):
    return app_with_timeline.test_client()


SID = "integration-session"


def test_full_timeline_crud(client):
    """Create timeline → add tracks → add clips → get nested → split → delete."""
    # Create
    r = client.post(f"/api/review/{SID}/timeline")
    assert r.status_code == 201

    # Add video track
    r = client.post(f"/api/review/{SID}/timeline/tracks", json={"track_type": "video", "label": "V1"})
    assert r.status_code == 201
    v_track = r.get_json()["track_id"]

    # Add audio track
    r = client.post(f"/api/review/{SID}/timeline/tracks", json={"track_type": "audio", "label": "BGM"})
    assert r.status_code == 201
    a_track = r.get_json()["track_id"]

    # Add clips to video track
    r = client.post(f"/api/review/{SID}/timeline/clips", json={
        "track_id": v_track, "start_ms": 0, "end_ms": 5000, "source_path": "/tmp/a.mp4",
    })
    assert r.status_code == 201
    clip_id = r.get_json()["clip_id"]

    r = client.post(f"/api/review/{SID}/timeline/clips", json={
        "track_id": a_track, "start_ms": 0, "end_ms": 10000, "label": "BGM track",
    })
    assert r.status_code == 201

    # Get full timeline — nested
    r = client.get(f"/api/review/{SID}/timeline")
    data = r.get_json()
    assert data["success"] is True
    assert len(data["tracks"]) == 2
    assert data["tracks"][0]["track_type"] == "video"
    assert len(data["tracks"][0]["clips"]) == 1

    # Split video clip at 2500ms
    r = client.post(f"/api/review/{SID}/timeline/clips/{clip_id}/split", json={"at_ms": 2500})
    assert r.status_code == 200
    left = r.get_json()["left_clip_id"]
    right = r.get_json()["right_clip_id"]
    assert left != right

    # Verify split result
    r = client.get(f"/api/review/{SID}/timeline")
    data = r.get_json()
    video_clips = data["tracks"][0]["clips"]
    assert len(video_clips) == 2

    # Delete audio track
    r = client.delete(f"/api/review/{SID}/timeline/tracks/{a_track}")
    assert r.status_code == 200

    # Verify only video track remains
    r = client.get(f"/api/review/{SID}/timeline")
    assert len(r.get_json()["tracks"]) == 1


def test_track_type_limits(client):
    """Cannot exceed track type limits (4 video max)."""
    client.post(f"/api/review/{SID}/timeline")
    for i in range(4):
        r = client.post(f"/api/review/{SID}/timeline/tracks", json={"track_type": "video", "label": f"V{i+1}"})
        assert r.status_code == 201

    # 5th video track should fail
    r = client.post(f"/api/review/{SID}/timeline/tracks", json={"track_type": "video", "label": "V5"})
    assert r.status_code == 400
    assert "limit" in r.get_json()["error"].lower()


def test_locked_track_operations(client):
    """Locked track prevents clip addition and track deletion."""
    client.post(f"/api/review/{SID}/timeline")
    r = client.post(f"/api/review/{SID}/timeline/tracks", json={"track_type": "video", "label": "V1"})
    track_id = r.get_json()["track_id"]

    # Lock track
    client.patch(f"/api/review/{SID}/timeline/tracks/{track_id}", json={"locked": True})

    # Cannot add clip
    r = client.post(f"/api/review/{SID}/timeline/clips", json={
        "track_id": track_id, "start_ms": 0, "end_ms": 1000,
    })
    assert r.status_code == 403

    # Cannot delete
    r = client.delete(f"/api/review/{SID}/timeline/tracks/{track_id}")
    assert r.status_code == 403
