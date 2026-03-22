"""Tests for R7 timeline editing API endpoints."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from modules.app_api.routes.timeline_routes import create_timeline_blueprint


@pytest.fixture
def project_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    script = {
        "clips": [
            {"clip_index": 1, "video_id": "v1", "source_start": 0, "source_end": 5, "duration": 5,
             "scene_description": "intro", "has_face": False},
            {"clip_index": 2, "video_id": "v2", "source_start": 2, "source_end": 8, "duration": 6,
             "scene_description": "middle", "has_face": True},
            {"clip_index": 3, "video_id": "v3", "source_start": 0, "source_end": 4, "duration": 4,
             "scene_description": "outro", "has_face": False},
        ],
        "subtitles": [],
    }
    (data_dir / "script_matched.json").write_text(json.dumps(script), encoding="utf-8")
    return tmp_path


@pytest.fixture
def app(project_dir):
    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True

    ws = MagicMock()
    ws.data = {"current_step": 6}
    ws.config = {}
    ws.get_step = MagicMock(return_value={})

    bp = create_timeline_blueprint(
        project_dir_getter=lambda: project_dir,
        workflow_state_getter=lambda: ws,
    )
    app.register_blueprint(bp)
    return app


class TestTimelineReorder:
    def test_reorder_clips(self, app, project_dir):
        with app.test_client() as c:
            # Reorder: 3, 1, 2
            resp = c.post("/api/timeline/reorder",
                          json={"order": [3, 1, 2]},
                          content_type="application/json")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["reordered_count"] == 3

        # Verify persisted
        script = json.loads((project_dir / "data" / "script_matched.json").read_text())
        clips = script["clips"]
        assert clips[0]["video_id"] == "v3"
        assert clips[0]["clip_index"] == 1
        assert clips[1]["video_id"] == "v1"
        assert clips[2]["video_id"] == "v2"

    def test_reorder_invalid_index(self, app):
        with app.test_client() as c:
            resp = c.post("/api/timeline/reorder",
                          json={"order": [1, 2, 99]},
                          content_type="application/json")
            assert resp.status_code == 400
            assert "not found" in resp.get_json()["error"]

    def test_reorder_empty_order(self, app):
        with app.test_client() as c:
            resp = c.post("/api/timeline/reorder",
                          json={"order": []},
                          content_type="application/json")
            assert resp.status_code == 400


class TestTimelineTrim:
    def test_trim_clip(self, app, project_dir):
        with app.test_client() as c:
            resp = c.post("/api/timeline/trim",
                          json={"clip_index": 2, "source_start": 3.0, "source_end": 7.5},
                          content_type="application/json")
            assert resp.status_code == 200
            assert resp.get_json()["ok"] is True

        script = json.loads((project_dir / "data" / "script_matched.json").read_text())
        clip2 = next(c for c in script["clips"] if c["clip_index"] == 2)
        assert clip2["source_start"] == 3.0
        assert clip2["source_end"] == 7.5
        assert clip2["duration"] == 4.5

    def test_trim_invalid_range(self, app):
        with app.test_client() as c:
            resp = c.post("/api/timeline/trim",
                          json={"clip_index": 1, "source_start": 5.0, "source_end": 3.0},
                          content_type="application/json")
            assert resp.status_code == 400

    def test_trim_missing_clip(self, app):
        with app.test_client() as c:
            resp = c.post("/api/timeline/trim",
                          json={"clip_index": 99, "source_start": 0, "source_end": 5},
                          content_type="application/json")
            assert resp.status_code == 404


class TestTimelineGet:
    def test_get_timeline(self, app):
        with app.test_client() as c:
            resp = c.get("/api/timeline")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert len(data["timeline"]["clips"]) == 3
