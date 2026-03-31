"""Unit tests for video_detector module."""

import os
import pytest
from unittest.mock import patch, MagicMock

from modules.review_engine.video_detector import (
    detect_video_type,
    _detect_silence_segments,
    _get_video_duration,
)
from modules.review_engine.contracts import VideoType
from modules.review_engine.exceptions import VideoDetectionError


class TestDetectVideoTypeSpeech:
    """Test speech-heavy video detection."""

    @patch("modules.review_engine.video_detector._find_ffmpeg")
    @patch("modules.review_engine.video_detector._get_video_duration")
    @patch("modules.review_engine.video_detector._get_audio_duration")
    @patch("modules.review_engine.video_detector._detect_silence_segments")
    def test_video_detector_speech_heavy_returns_speech(
        self, mock_silence, mock_audio_dur, mock_video_dur, mock_ffmpeg, tmp_path
    ):
        """Speech-heavy video (little silence) → video_type=speech."""
        # Create a dummy file
        video_file = tmp_path / "speech.mp4"
        video_file.touch()

        mock_ffmpeg.return_value = "/usr/bin/ffmpeg"
        mock_video_dur.return_value = 120.0
        mock_audio_dur.return_value = 120.0
        # Only 10s of silence in 120s video → speech_ratio ≈ 0.917
        mock_silence.return_value = [
            (5.0, 8.0, 3.0),
            (50.0, 55.0, 5.0),
            (100.0, 102.0, 2.0),
        ]

        result = detect_video_type(str(video_file))

        assert result.video_type == VideoType.SPEECH
        assert result.speech_ratio > 0.6
        assert result.has_audio is True
        assert result.duration_s == 120.0

    @patch("modules.review_engine.video_detector._find_ffmpeg")
    @patch("modules.review_engine.video_detector._get_video_duration")
    @patch("modules.review_engine.video_detector._get_audio_duration")
    @patch("modules.review_engine.video_detector._detect_silence_segments")
    def test_video_detector_scenic_returns_scenic(
        self, mock_silence, mock_audio_dur, mock_video_dur, mock_ffmpeg, tmp_path
    ):
        """Scenic video (mostly silence) → video_type=scenic."""
        video_file = tmp_path / "scenic.mp4"
        video_file.touch()

        mock_ffmpeg.return_value = "/usr/bin/ffmpeg"
        mock_video_dur.return_value = 60.0
        mock_audio_dur.return_value = 60.0
        # 55s of silence in 60s → speech_ratio ≈ 0.083
        mock_silence.return_value = [
            (0.0, 55.0, 55.0),
        ]

        result = detect_video_type(str(video_file))

        assert result.video_type == VideoType.SCENIC
        assert result.speech_ratio < 0.15
        assert result.has_audio is True

    @patch("modules.review_engine.video_detector._find_ffmpeg")
    @patch("modules.review_engine.video_detector._get_video_duration")
    @patch("modules.review_engine.video_detector._get_audio_duration")
    @patch("modules.review_engine.video_detector._detect_silence_segments")
    def test_video_detector_mixed_returns_mixed(
        self, mock_silence, mock_audio_dur, mock_video_dur, mock_ffmpeg, tmp_path
    ):
        """Mixed video (moderate silence) → video_type=mixed."""
        video_file = tmp_path / "mixed.mp4"
        video_file.touch()

        mock_ffmpeg.return_value = "/usr/bin/ffmpeg"
        mock_video_dur.return_value = 100.0
        mock_audio_dur.return_value = 100.0
        # 60s of silence in 100s → speech_ratio = 0.4
        mock_silence.return_value = [
            (0.0, 20.0, 20.0),
            (40.0, 70.0, 30.0),
            (85.0, 95.0, 10.0),
        ]

        result = detect_video_type(str(video_file))

        assert result.video_type == VideoType.MIXED
        assert 0.15 <= result.speech_ratio <= 0.6

    @patch("modules.review_engine.video_detector._find_ffmpeg")
    @patch("modules.review_engine.video_detector._get_video_duration")
    @patch("modules.review_engine.video_detector._get_audio_duration")
    def test_video_detector_no_audio_returns_scenic(
        self, mock_audio_dur, mock_video_dur, mock_ffmpeg, tmp_path
    ):
        """Video with no audio track → scenic, has_audio=False."""
        video_file = tmp_path / "no_audio.mp4"
        video_file.touch()

        mock_ffmpeg.return_value = "/usr/bin/ffmpeg"
        mock_video_dur.return_value = 30.0
        mock_audio_dur.return_value = None  # No audio stream

        result = detect_video_type(str(video_file))

        assert result.video_type == VideoType.SCENIC
        assert result.speech_ratio == 0.0
        assert result.has_audio is False


class TestDetectVideoTypeErrors:
    """Test error handling."""

    def test_video_detector_invalid_path_raises_error(self):
        """Non-existent path → VideoDetectionError."""
        with pytest.raises(VideoDetectionError, match="not found"):
            detect_video_type("/nonexistent/path/video.mp4")


class TestSilenceDetectParsing:
    """Test FFmpeg silence detect output parsing."""

    @patch("subprocess.run")
    def test_silence_parsing_extracts_segments(self, mock_run):
        """Parse FFmpeg silencedetect stderr output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stderr=(
                "[silencedetect @ 0x...] silence_start: 5.2\n"
                "[silencedetect @ 0x...] silence_end: 8.5 | silence_duration: 3.3\n"
                "[silencedetect @ 0x...] silence_start: 20.0\n"
                "[silencedetect @ 0x...] silence_end: 25.1 | silence_duration: 5.1\n"
            ),
        )

        segments = _detect_silence_segments("test.mp4", "/usr/bin/ffmpeg")

        assert len(segments) == 2
        assert segments[0] == (5.2, 8.5, 3.3)
        assert segments[1] == (20.0, 25.1, 5.1)
