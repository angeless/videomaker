"""Tests for GET /api/timeline endpoint."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock


def _make_app(tmp_path, script=None, materials=None, ws=None):
    """Create a minimal Flask app with the timeline blueprint."""
    from flask import Flask
    from modules.app_api.routes.timeline_routes import create_timeline_blueprint

    project_dir = tmp_path / "project"
    data_dir = project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if script is not None:
        (data_dir / "script_matched.json").write_text(json.dumps(script), encoding="utf-8")
    if materials is not None:
        (data_dir / "materials.json").write_text(json.dumps(materials), encoding="utf-8")

    app = Flask(__name__)
    app.register_blueprint(
        create_timeline_blueprint(
            project_dir_getter=lambda: project_dir,
            workflow_state_getter=lambda: ws,
        )
    )
    return app


def test_timeline_no_project():
    from flask import Flask
    from modules.app_api.routes.timeline_routes import create_timeline_blueprint

    app = Flask(__name__)
    app.register_blueprint(
        create_timeline_blueprint(
            project_dir_getter=lambda: None,
            workflow_state_getter=lambda: None,
        )
    )
    with app.test_client() as client:
        resp = client.get("/api/timeline")
        assert resp.status_code == 400


def test_timeline_no_script(tmp_path):
    app = _make_app(tmp_path, script=None)
    with app.test_client() as client:
        resp = client.get("/api/timeline")
        data = resp.get_json()
        assert data["ok"] is True
        assert data["timeline"] is None


def test_timeline_with_clips(tmp_path):
    script = {
        "clips": [
            {"clip_index": 1, "video_id": "abc", "source_start": 0, "source_end": 5, "duration": 5, "has_face": False},
            {"clip_index": 2, "video_id": "def", "source_start": 2, "source_end": 8, "duration": 6, "has_face": True},
        ],
        "subtitles": [
            {"clip_index": 1, "start_time": 0, "end_time": 5, "cn_text": "Hello"},
        ],
    }
    materials = {
        "abc": {"filename": "clip_a.mp4"},
        "def": {"filename": "clip_b.mp4"},
    }
    app = _make_app(tmp_path, script=script, materials=materials)
    with app.test_client() as client:
        resp = client.get("/api/timeline")
        data = resp.get_json()
        assert data["ok"] is True
        tl = data["timeline"]
        assert tl is not None
        assert len(tl["clips"]) == 2
        assert tl["clips"][0]["timeline_start"] == 0
        assert tl["clips"][0]["timeline_end"] == 5
        assert tl["clips"][0]["filename"] == "clip_a.mp4"
        assert tl["clips"][1]["timeline_start"] > 0
        assert tl["clips"][1]["has_face"] is True
        assert len(tl["subtitles"]) == 1
        assert tl["total_duration"] > 0


def test_timeline_transition_overlap(tmp_path):
    """Transition duration should reduce gap between clips."""
    script = {
        "clips": [
            {"clip_index": 1, "duration": 10},
            {"clip_index": 2, "duration": 10},
            {"clip_index": 3, "duration": 10},
        ],
        "subtitles": [],
    }
    ws = MagicMock()
    ws.config = {"transition_duration": 2.0, "fps": 30}
    ws.data = {"current_step": 3}
    ws.get_step = lambda n: {}

    app = _make_app(tmp_path, script=script, ws=ws)
    with app.test_client() as client:
        resp = client.get("/api/timeline")
        tl = resp.get_json()["timeline"]
        # Clip 1: 0-10, clip 2 starts at 10-2=8, clip 3 starts at 8+10-2=16
        assert tl["clips"][0]["timeline_start"] == 0
        assert tl["clips"][0]["timeline_end"] == 10
        assert tl["clips"][1]["timeline_start"] == 8
        assert tl["clips"][1]["timeline_end"] == 18
        assert tl["clips"][2]["timeline_start"] == 16
        assert tl["clips"][2]["timeline_end"] == 26
        # Total = last clip end (no transition overlap for last clip)
        assert tl["total_duration"] == 26


def test_timeline_clip_status_rendered(tmp_path):
    """Step 7 completed should yield 'rendered' status."""
    script = {"clips": [{"clip_index": 1, "duration": 5}], "subtitles": []}
    ws = MagicMock()
    ws.config = {}
    ws.data = {"current_step": 7}
    ws.get_step = lambda n: {"status": "completed"} if n == 7 else {}

    app = _make_app(tmp_path, script=script, ws=ws)
    with app.test_client() as client:
        resp = client.get("/api/timeline")
        tl = resp.get_json()["timeline"]
        assert tl["clips"][0]["processing_status"] == "rendered"


def test_timeline_clip_status_matched(tmp_path):
    """Step 4+ without step 7 completed should yield 'matched'."""
    script = {"clips": [{"clip_index": 1, "duration": 5}], "subtitles": []}
    ws = MagicMock()
    ws.config = {}
    ws.data = {"current_step": 5}
    ws.get_step = lambda n: {}

    app = _make_app(tmp_path, script=script, ws=ws)
    with app.test_client() as client:
        resp = client.get("/api/timeline")
        tl = resp.get_json()["timeline"]
        assert tl["clips"][0]["processing_status"] == "matched"


def test_timeline_clip_status_pending(tmp_path):
    """Step 3 should yield 'pending' status."""
    script = {"clips": [{"clip_index": 1, "duration": 5}], "subtitles": []}
    ws = MagicMock()
    ws.config = {}
    ws.data = {"current_step": 3}
    ws.get_step = lambda n: {}

    app = _make_app(tmp_path, script=script, ws=ws)
    with app.test_client() as client:
        resp = client.get("/api/timeline")
        tl = resp.get_json()["timeline"]
        assert tl["clips"][0]["processing_status"] == "pending"
