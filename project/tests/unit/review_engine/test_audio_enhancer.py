"""Tests for AudioEnhancer — R14."""

import pytest
from unittest.mock import patch, MagicMock

from modules.review_engine.audio_enhancer import (
    AudioConfig,
    enhance_audio,
)
from modules.review_engine.exceptions import RenderError


class TestAudioEnhancer:

    def test_full_chain_builds_correct_filters(self):
        """Full config builds denoise + eq + compressor + loudnorm chain."""
        config = AudioConfig(
            denoise=True, equalizer=True, compressor=True, loudnorm=True,
        )
        # We test the filter chain by mocking subprocess
        with patch("modules.review_engine.audio_enhancer.subprocess.run") as mock_run, \
             patch("modules.review_engine.audio_enhancer.os.path.isfile", return_value=True):
            mock_run.return_value = MagicMock(returncode=0)
            enhance_audio("/tmp/in.wav", "/tmp/out.aac", config)

            cmd = mock_run.call_args[0][0]
            af_idx = cmd.index("-af")
            af_value = cmd[af_idx + 1]
            assert "afftdn" in af_value
            assert "equalizer" in af_value
            assert "acompressor" in af_value
            assert "loudnorm" in af_value

    def test_partial_config(self):
        """Only enabled stages appear in filter chain."""
        config = AudioConfig(denoise=False, equalizer=False, compressor=False, loudnorm=True)
        with patch("modules.review_engine.audio_enhancer.subprocess.run") as mock_run, \
             patch("modules.review_engine.audio_enhancer.os.path.isfile", return_value=True):
            mock_run.return_value = MagicMock(returncode=0)
            enhance_audio("/tmp/in.wav", "/tmp/out.aac", config)

            cmd = mock_run.call_args[0][0]
            af_value = cmd[cmd.index("-af") + 1]
            assert "afftdn" not in af_value
            assert "loudnorm" in af_value

    def test_loudnorm_sample_rate(self):
        """Must always include -ar 44100."""
        config = AudioConfig()
        with patch("modules.review_engine.audio_enhancer.subprocess.run") as mock_run, \
             patch("modules.review_engine.audio_enhancer.os.path.isfile", return_value=True):
            mock_run.return_value = MagicMock(returncode=0)
            enhance_audio("/tmp/in.wav", "/tmp/out.aac", config)

            cmd = mock_run.call_args[0][0]
            assert "-ar" in cmd
            ar_idx = cmd.index("-ar")
            assert cmd[ar_idx + 1] == "44100"

    def test_missing_input(self):
        with pytest.raises(RenderError, match="not found"):
            enhance_audio("/nonexistent/file.wav", "/tmp/out.aac")
