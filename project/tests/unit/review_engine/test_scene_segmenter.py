"""Unit tests for scene_segmenter module."""

from unittest.mock import MagicMock, patch

import pytest
from modules.review_engine.contracts import SceneInfo
from modules.review_engine.exceptions import ReviewEngineError
from modules.review_engine.scene_segmenter import (
    detect_scene_changes,
    segment_scenes,
)


class TestDetectSceneChanges:
    """Test scene change timestamp detection."""

    @patch("modules.review_engine.scene_segmenter._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("modules.review_engine.scene_segmenter.subprocess.run")
    def test_scene_segmenter_parses_timestamps(self, mock_run, mock_ff):
        mock_run.return_value = MagicMock(
            returncode=0,
            stderr=(
                "[Parsed_showinfo] n:0 pts:0 pts_time:0.000000\n"
                "[Parsed_showinfo] n:45 pts:1800 pts_time:2.500000\n"
                "[Parsed_showinfo] n:120 pts:4800 pts_time:6.700000\n"
            ),
        )
        timestamps = detect_scene_changes("/fake/video.mp4", threshold=0.3)
        assert 0.0 in timestamps
        assert 2.5 in timestamps
        assert 6.7 in timestamps

    @patch("modules.review_engine.scene_segmenter._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("modules.review_engine.scene_segmenter.subprocess.run")
    def test_scene_segmenter_always_starts_at_zero(self, mock_run, mock_ff):
        mock_run.return_value = MagicMock(
            returncode=0,
            stderr="[Parsed_showinfo] pts_time:3.000000\n",
        )
        timestamps = detect_scene_changes("/fake/video.mp4")
        assert timestamps[0] == 0.0

    @patch("modules.review_engine.scene_segmenter._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("modules.review_engine.scene_segmenter.subprocess.run")
    def test_scene_segmenter_no_scenes_still_has_zero(self, mock_run, mock_ff):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        timestamps = detect_scene_changes("/fake/video.mp4")
        assert timestamps == [0.0]


class TestSegmentScenes:
    """Test full scene segmentation pipeline."""

    @patch("modules.review_engine.scene_segmenter._extract_thumbnail")
    @patch("modules.review_engine.scene_segmenter.detect_scene_changes")
    @patch("modules.review_engine.scene_segmenter._get_video_info")
    @patch("modules.review_engine.scene_segmenter._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("modules.review_engine.scene_segmenter.os.path.isfile", return_value=True)
    def test_scene_segmenter_builds_scene_list(
        self, mock_isfile, mock_ff, mock_info, mock_detect, mock_thumb,
    ):
        mock_info.return_value = {"duration": 10.0, "fps": 30.0}
        mock_detect.return_value = [0.0, 3.0, 7.0]

        scenes = segment_scenes("/fake/video.mp4")

        # 3 scenes: 0→3, 3→7, 7→10 (endpoint added at total_duration)
        assert len(scenes) == 3
        assert scenes[0].start_ms == 0
        assert scenes[0].end_ms == 3000
        assert scenes[1].start_ms == 3000
        assert scenes[1].end_ms == 7000
        assert scenes[2].start_ms == 7000
        assert scenes[2].end_ms == 10000

    @patch("modules.review_engine.scene_segmenter.detect_scene_changes")
    @patch("modules.review_engine.scene_segmenter._get_video_info")
    @patch("modules.review_engine.scene_segmenter._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("modules.review_engine.scene_segmenter.os.path.isfile", return_value=True)
    def test_scene_segmenter_filters_short_scenes(
        self, mock_isfile, mock_ff, mock_info, mock_detect,
    ):
        mock_info.return_value = {"duration": 5.0, "fps": 30.0}
        # 0→0.2 is too short (0.2s < 0.5s min), 0.2→5.0 is kept
        mock_detect.return_value = [0.0, 0.2]

        scenes = segment_scenes("/fake/video.mp4", min_scene_duration_s=0.5)

        assert len(scenes) == 1
        assert scenes[0].start_ms == 200

    def test_scene_segmenter_file_not_found_raises(self):
        with pytest.raises(ReviewEngineError, match="not found"):
            segment_scenes("/nonexistent/video.mp4")

    @patch("modules.review_engine.scene_segmenter._get_video_info")
    @patch("modules.review_engine.scene_segmenter._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("modules.review_engine.scene_segmenter.os.path.isfile", return_value=True)
    def test_scene_segmenter_zero_duration_raises(self, mock_isfile, mock_ff, mock_info):
        mock_info.return_value = {"duration": 0, "fps": 30.0}
        with pytest.raises(ReviewEngineError, match="Invalid video duration"):
            segment_scenes("/fake/video.mp4")
