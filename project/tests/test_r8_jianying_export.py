"""Tests for R8 Jianying draft export."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.exporters.jianying.draft_builder import JianyingExportBuilder


@pytest.fixture
def sample_tracks():
    return {
        "video": [
            {"uid": "v1", "start_ms": 0, "end_ms": 3000, "label": "opening", "path": "/fake/v1.mp4"},
            {"uid": "v2", "start_ms": 2700, "end_ms": 7700, "label": "middle", "path": "/fake/v2.mp4"},
        ],
        "subtitle": [
            {"text": "Hello", "start_ms": 0, "end_ms": 2000},
            {"text": "World", "start_ms": 3000, "end_ms": 5000},
        ],
        "audio": [
            {"label": "BGM", "start_ms": 0, "end_ms": 7700, "volume": 0.4},
        ],
    }


class TestJianyingExportBuilder:
    def test_build_creates_draft_files(self, tmp_path, sample_tracks):
        builder = JianyingExportBuilder("test_draft", sample_tracks)
        result = builder.build(str(tmp_path))

        assert "draft_path" in result
        draft_dir = Path(result["draft_path"])
        assert draft_dir.exists()
        assert (draft_dir / "draft_content.json").exists()
        assert (draft_dir / "draft_meta_info.json").exists()

    def test_draft_content_is_valid_json(self, tmp_path, sample_tracks):
        builder = JianyingExportBuilder("test_draft", sample_tracks)
        result = builder.build(str(tmp_path))

        content = json.loads((Path(result["draft_path"]) / "draft_content.json").read_text())
        assert "tracks" in content
        assert "materials" in content
        assert "duration" in content

    def test_draft_has_correct_track_count(self, tmp_path, sample_tracks):
        builder = JianyingExportBuilder("test_draft", sample_tracks)
        result = builder.build(str(tmp_path))

        content = json.loads((Path(result["draft_path"]) / "draft_content.json").read_text())
        assert len(content["tracks"]) == 3  # video + text + audio

    def test_video_segments_order_correct(self, tmp_path, sample_tracks):
        builder = JianyingExportBuilder("test_draft", sample_tracks)
        result = builder.build(str(tmp_path))

        content = json.loads((Path(result["draft_path"]) / "draft_content.json").read_text())
        video_track = [t for t in content["tracks"] if t["type"] == "video"][0]
        assert len(video_track["segments"]) == 2
        # First segment starts at 0
        assert video_track["segments"][0]["target_timerange"]["start"] == 0

    def test_meta_file_has_name(self, tmp_path, sample_tracks):
        builder = JianyingExportBuilder("my_project", sample_tracks)
        result = builder.build(str(tmp_path))

        meta = json.loads((Path(result["draft_path"]) / "draft_meta_info.json").read_text())
        assert meta["draft_name"] == "my_project"

    def test_empty_tracks(self, tmp_path):
        builder = JianyingExportBuilder("empty", {"video": [], "subtitle": [], "audio": []})
        result = builder.build(str(tmp_path))
        content = json.loads((Path(result["draft_path"]) / "draft_content.json").read_text())
        assert content["tracks"] == []
        assert result["duration_ms"] == 0

    def test_custom_resolution(self, tmp_path, sample_tracks):
        builder = JianyingExportBuilder("hd", sample_tracks, width=1920, height=1080)
        result = builder.build(str(tmp_path))
        content = json.loads((Path(result["draft_path"]) / "draft_content.json").read_text())
        assert content["canvas_config"]["width"] == 1920
        assert content["canvas_config"]["height"] == 1080
