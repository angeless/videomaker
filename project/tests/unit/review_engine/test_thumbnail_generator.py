"""Unit tests for thumbnail_generator module."""

import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from modules.review_engine.thumbnail_generator import (
    generate_thumbnails,
    _get_duration,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_COLUMNS,
)
from modules.review_engine.exceptions import RenderError


class TestGetDuration:
    """Test _get_duration helper."""

    @patch("modules.review_engine.thumbnail_generator.subprocess.run")
    @patch("modules.review_engine.thumbnail_generator._find_ffprobe", return_value="/usr/bin/ffprobe")
    def test_returns_duration(self, mock_probe, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"format": {"duration": "12.5"}}),
            returncode=0,
        )
        assert _get_duration("/tmp/video.mp4") == 12.5

    @patch("modules.review_engine.thumbnail_generator.subprocess.run")
    @patch("modules.review_engine.thumbnail_generator._find_ffprobe", return_value="/usr/bin/ffprobe")
    def test_raises_on_bad_json(self, mock_probe, mock_run):
        mock_run.return_value = MagicMock(stdout="not json", returncode=0)
        with pytest.raises(RenderError, match="Failed to get video duration"):
            _get_duration("/tmp/video.mp4")

    @patch("modules.review_engine.thumbnail_generator.subprocess.run")
    @patch("modules.review_engine.thumbnail_generator._find_ffprobe", return_value="/usr/bin/ffprobe")
    def test_raises_on_timeout(self, mock_probe, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)
        with pytest.raises(RenderError, match="Failed to get video duration"):
            _get_duration("/tmp/video.mp4")


class TestGenerateThumbnails:
    """Test generate_thumbnails function."""

    def test_raises_on_missing_video(self, tmp_path):
        with pytest.raises(RenderError, match="Video not found"):
            generate_thumbnails("/nonexistent/video.mp4", str(tmp_path))

    @patch("modules.review_engine.thumbnail_generator._get_duration", return_value=20.0)
    @patch("modules.review_engine.thumbnail_generator.subprocess.run")
    @patch("modules.review_engine.thumbnail_generator._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    def test_generates_sprite_and_metadata(self, mock_ffmpeg, mock_run, mock_dur, tmp_path):
        # Create a fake video file
        video = tmp_path / "video.mp4"
        video.write_text("fake")
        output_dir = str(tmp_path / "out")

        # Mock FFmpeg success + create the sprite file
        def side_effect(*args, **kwargs):
            sprite_path = os.path.join(output_dir, "thumbnails.jpg")
            os.makedirs(output_dir, exist_ok=True)
            with open(sprite_path, "wb") as f:
                f.write(b"\xff\xd8\xff")  # JPEG magic bytes
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = side_effect

        result = generate_thumbnails(str(video), output_dir)

        assert result["frame_width"] == DEFAULT_FRAME_WIDTH
        assert result["frame_height"] == DEFAULT_FRAME_HEIGHT
        assert result["columns"] == DEFAULT_COLUMNS
        assert result["frame_count"] == 10  # 20s / 2s interval
        assert result["interval_ms"] == 2000
        assert result["duration_ms"] == 20000
        assert os.path.isfile(os.path.join(output_dir, "thumbnails.json"))

    @patch("modules.review_engine.thumbnail_generator._get_duration", return_value=10.0)
    @patch("modules.review_engine.thumbnail_generator.subprocess.run")
    @patch("modules.review_engine.thumbnail_generator._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    def test_raises_on_ffmpeg_failure(self, mock_ffmpeg, mock_run, mock_dur, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_text("fake")
        mock_run.return_value = MagicMock(returncode=1, stderr="error details here")

        with pytest.raises(RenderError, match="FFmpeg thumbnail failed"):
            generate_thumbnails(str(video), str(tmp_path / "out"))
