"""Tests for R7 three-track timeline API (GET/PUT /api/timeline/tracks)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.app_api.routes.timeline_routes import create_timeline_blueprint
from flask import Flask


@pytest.fixture
def app_with_tracks(tmp_path):
    """Flask test app with a project containing script + config."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    data_dir = project_dir / "data"
    data_dir.mkdir()

    script = {
        "clips": [
            {"clip_index": 1, "video_id": "v1", "source_start": 0, "source_end": 3, "duration": 3, "scene_description": "opening"},
            {"clip_index": 2, "video_id": "v2", "source_start": 0, "source_end": 5, "duration": 5, "scene_description": "middle"},
            {"clip_index": 3, "video_id": "v3", "source_start": 0, "source_end": 2, "duration": 2, "scene_description": "closing"},
        ],
        "subtitles": [
            {"cn_text": "你好", "start_time": 0, "end_time": 2},
            {"cn_text": "世界", "start_time": 3, "end_time": 5},
        ],
    }
    (data_dir / "script_matched.json").write_text(json.dumps(script), encoding="utf-8")

    ws = MagicMock()
    ws.config = {"transition_duration": 0.3, "bgm_path": "/fake/bgm.mp3", "bgm_volume": 0.4}
    ws.data = {"current_step": 6}

    app = Flask(__name__)
    app.config["TESTING"] = True
    bp = create_timeline_blueprint(
        project_dir_getter=lambda: project_dir,
        workflow_state_getter=lambda: ws,
    )
    app.register_blueprint(bp)
    return app, project_dir


class TestTimelineTracksGet:
    def test_returns_three_tracks(self, app_with_tracks):
        app, _ = app_with_tracks
        with app.test_client() as c:
            resp = c.get("/api/timeline/tracks")
            data = resp.get_json()
            assert data["ok"] is True
            tracks = data["tracks"]
            assert "video" in tracks
            assert "subtitle" in tracks
            assert "audio" in tracks

    def test_video_track_has_correct_count(self, app_with_tracks):
        app, _ = app_with_tracks
        with app.test_client() as c:
            data = c.get("/api/timeline/tracks").get_json()
            assert len(data["tracks"]["video"]) == 3

    def test_video_track_has_labels(self, app_with_tracks):
        app, _ = app_with_tracks
        with app.test_client() as c:
            data = c.get("/api/timeline/tracks").get_json()
            labels = [v["label"] for v in data["tracks"]["video"]]
            assert "opening" in labels

    def test_subtitle_track_has_text(self, app_with_tracks):
        app, _ = app_with_tracks
        with app.test_client() as c:
            data = c.get("/api/timeline/tracks").get_json()
            texts = [s["text"] for s in data["tracks"]["subtitle"]]
            assert "你好" in texts

    def test_audio_track_has_bgm(self, app_with_tracks):
        app, _ = app_with_tracks
        with app.test_client() as c:
            data = c.get("/api/timeline/tracks").get_json()
            labels = [a["label"] for a in data["tracks"]["audio"]]
            assert "BGM" in labels

    def test_video_clips_have_ms_fields(self, app_with_tracks):
        app, _ = app_with_tracks
        with app.test_client() as c:
            data = c.get("/api/timeline/tracks").get_json()
            clip = data["tracks"]["video"][0]
            assert "start_ms" in clip
            assert "end_ms" in clip
            assert "uid" in clip
            assert clip["end_ms"] > clip["start_ms"]


class TestTimelineTracksPut:
    def test_save_and_reload(self, app_with_tracks):
        app, project_dir = app_with_tracks
        with app.test_client() as c:
            # Get current
            data = c.get("/api/timeline/tracks").get_json()
            tracks = data["tracks"]

            # Modify subtitle
            tracks["subtitle"][0]["text"] = "modified"
            tracks["subtitle"][0]["start_ms"] = 500
            tracks["subtitle"][0]["end_ms"] = 1500

            # Save
            resp = c.put("/api/timeline/tracks",
                         data=json.dumps({"tracks": tracks}),
                         content_type="application/json")
            assert resp.get_json()["ok"] is True

            # Verify persisted
            script = json.loads((project_dir / "data" / "script_matched.json").read_text())
            assert script["subtitles"][0]["cn_text"] == "modified"
            assert script["subtitles"][0]["start_time"] == 0.5

    def test_save_invalid_tracks_returns_error(self, app_with_tracks):
        app, _ = app_with_tracks
        with app.test_client() as c:
            resp = c.put("/api/timeline/tracks",
                         data=json.dumps({"tracks": "not_an_object"}),
                         content_type="application/json")
            assert resp.status_code == 400

    def test_no_project_returns_error(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        bp = create_timeline_blueprint(
            project_dir_getter=lambda: None,
            workflow_state_getter=lambda: None,
        )
        app.register_blueprint(bp)
        with app.test_client() as c:
            resp = c.get("/api/timeline/tracks")
            assert resp.status_code == 400
