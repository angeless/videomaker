"""Unit tests for waveform_generator module."""

import json
import os
import struct
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from modules.review_engine.waveform_generator import (
    generate_waveform,
    _compute_peaks,
    _flat_waveform,
    AUDIO_SAMPLE_RATE,
    DEFAULT_PEAKS_PER_SECOND,
)
from modules.review_engine.exceptions import RenderError


class TestComputePeaks:
    """Test _compute_peaks from raw PCM data."""

    def test_basic_peaks(self, tmp_path):
        """Generate known PCM data and verify peak computation."""
        pcm_path = str(tmp_path / "test.pcm")
        samples_per_peak = AUDIO_SAMPLE_RATE // DEFAULT_PEAKS_PER_SECOND  # 4410

        # Write two peaks worth of samples
        with open(pcm_path, "wb") as f:
            # Peak 1: all zeros → peak = 0
            for _ in range(samples_per_peak):
                f.write(struct.pack("<h", 0))
            # Peak 2: alternating ±16384 → peak = 0.5
            for i in range(samples_per_peak):
                val = 16384 if i % 2 == 0 else -16384
                f.write(struct.pack("<h", val))

        peaks = _compute_peaks(pcm_path, DEFAULT_PEAKS_PER_SECOND)
        assert len(peaks) == 2
        assert peaks[0] == 0.0
        assert peaks[1] == 0.5

    def test_empty_file(self, tmp_path):
        pcm_path = str(tmp_path / "empty.pcm")
        with open(pcm_path, "wb") as f:
            pass
        peaks = _compute_peaks(pcm_path, DEFAULT_PEAKS_PER_SECOND)
        assert peaks == []


class TestFlatWaveform:
    """Test _flat_waveform fallback."""

    def test_returns_empty_peaks(self, tmp_path):
        result = _flat_waveform(str(tmp_path))
        assert result["peaks"] == []
        assert result["peak_count"] == 0
        assert os.path.isfile(str(tmp_path / "waveform.json"))


class TestGenerateWaveform:
    """Test generate_waveform function."""

    def test_raises_on_missing_video(self, tmp_path):
        with pytest.raises(RenderError, match="Video not found"):
            generate_waveform("/nonexistent/video.mp4", str(tmp_path))

    @patch("modules.review_engine.waveform_generator.subprocess.run")
    @patch("modules.review_engine.waveform_generator._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    def test_flat_waveform_on_no_audio(self, mock_ffmpeg, mock_run, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_text("fake")
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="does not contain any stream"
        )

        result = generate_waveform(str(video), str(tmp_path / "out"))
        assert result["peaks"] == []
        assert result["peak_count"] == 0

    @patch("modules.review_engine.waveform_generator.subprocess.run")
    @patch("modules.review_engine.waveform_generator._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    def test_generates_waveform(self, mock_ffmpeg, mock_run, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_text("fake")
        output_dir = str(tmp_path / "out")

        # Mock FFmpeg to create a PCM file with known data
        samples_per_peak = AUDIO_SAMPLE_RATE // DEFAULT_PEAKS_PER_SECOND

        def side_effect(*args, **kwargs):
            os.makedirs(output_dir, exist_ok=True)
            pcm_path = os.path.join(output_dir, "audio_raw.pcm")
            with open(pcm_path, "wb") as f:
                # Write 3 peaks of known amplitudes
                for peak_val in [0, 16384, 32767]:
                    for _ in range(samples_per_peak):
                        f.write(struct.pack("<h", peak_val))
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = side_effect

        result = generate_waveform(str(video), output_dir)

        assert len(result["peaks"]) == 3
        assert result["peaks"][0] == 0.0
        assert result["peaks"][1] == 0.5
        assert result["peaks"][2] == 1.0  # 32767/32768 rounds to 1.0
        assert result["sample_rate"] == AUDIO_SAMPLE_RATE
        assert os.path.isfile(os.path.join(output_dir, "waveform.json"))
        # PCM should be cleaned up
        assert not os.path.isfile(os.path.join(output_dir, "audio_raw.pcm"))

    @patch("modules.review_engine.waveform_generator.subprocess.run")
    @patch("modules.review_engine.waveform_generator._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    def test_raises_on_ffmpeg_error(self, mock_ffmpeg, mock_run, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_text("fake")
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="some other error"
        )
        with pytest.raises(RenderError, match="FFmpeg audio extraction failed"):
            generate_waveform(str(video), str(tmp_path / "out"))
