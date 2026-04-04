"""Tests for scene_selector — R14."""

import json
from unittest.mock import patch, MagicMock

import pytest

from modules.review_engine.exceptions import VideoDetectionError
from modules.review_engine.scene_selector import (
    detect_scenes,
    _build_scenes,
    _detect_scene_timestamps,
    _get_duration,
)


class TestBuildScenes:
    """Unit tests for _build_scenes (no FFmpeg needed)."""

    def test_splits_scenes(self):
        """Multiple scene change timestamps produce correct scenes."""
        timestamps = [5.0, 12.5]
        duration = 20.0
        scenes = _build_scenes(timestamps, duration)

        assert len(scenes) == 3
        assert scenes[0]["start_s"] == 0.0
        assert scenes[0]["end_s"] == 5.0
        assert scenes[0]["duration_s"] == 5.0
        assert scenes[1]["start_s"] == 5.0
        assert scenes[1]["end_s"] == 12.5
        assert scenes[2]["start_s"] == 12.5
        assert scenes[2]["end_s"] == 20.0

    def test_single_scene_video(self):
        """No scene changes → entire video is one scene."""
        scenes = _build_scenes([], 30.0)

        assert len(scenes) == 1
        assert scenes[0]["scene_id"] == 0
        assert scenes[0]["start_s"] == 0.0
        assert scenes[0]["end_s"] == 30.0
        assert scenes[0]["duration_s"] == 30.0

    def test_tiny_fragments_skipped(self):
        """Fragments shorter than 0.1s are filtered out."""
        timestamps = [10.0, 10.05]  # 0.05s gap
        scenes = _build_scenes(timestamps, 20.0)
        # The 0.05s fragment is skipped
        durations = [s["duration_s"] for s in scenes]
        assert all(d >= 0.1 for d in durations)

    def test_scene_ids_sequential(self):
        """Scene IDs are sequential starting from 0."""
        scenes = _build_scenes([3.0, 7.0, 15.0], 20.0)
        ids = [s["scene_id"] for s in scenes]
        assert ids == [0, 1, 2, 3]

    def test_thumbnail_path_default_none(self):
        """All scenes have thumbnail_path=None by default."""
        scenes = _build_scenes([5.0], 10.0)
        for s in scenes:
            assert s["thumbnail_path"] is None


class TestDetectScenes:
    """Integration-style tests with mocked FFmpeg."""

    def test_file_not_found_raises(self):
        with pytest.raises(VideoDetectionError, match="not found"):
            detect_scenes("/nonexistent/video.mp4")

    @patch("modules.review_engine.scene_selector._detect_scene_timestamps")
    @patch("modules.review_engine.scene_selector._get_duration")
    def test_detect_returns_scenes(self, mock_dur, mock_ts, tmp_path):
        """detect_scenes returns correct structure."""
        # Create a dummy file
        video = tmp_path / "test.mp4"
        video.write_bytes(b"fake")

        mock_dur.return_value = 20.0
        mock_ts.return_value = [5.0, 12.0]

        result = detect_scenes(str(video), extract_thumbnails=False)

        assert result["total_scenes"] == 3
        assert len(result["scenes"]) == 3
        assert result["scenes"][0]["start_s"] == 0.0
        assert result["scenes"][2]["end_s"] == 20.0

    @patch("modules.review_engine.scene_selector._get_duration")
    def test_zero_duration_raises(self, mock_dur, tmp_path):
        video = tmp_path / "empty.mp4"
        video.write_bytes(b"fake")
        mock_dur.return_value = 0.0

        with pytest.raises(VideoDetectionError, match="duration"):
            detect_scenes(str(video))
