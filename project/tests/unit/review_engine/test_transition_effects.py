"""Tests for TransitionEffects — R17."""

import pytest
from unittest.mock import patch, MagicMock

from modules.review_engine.transition_effects import (
    EFFECTS,
    apply_transition,
)
from modules.review_engine.exceptions import RenderError


class TestTransitionEffects:

    def test_all_12_effects_defined(self):
        """All 12 effect names exist in the EFFECTS dict."""
        expected = {
            "cut", "fade_black", "fade_white", "cross_dissolve",
            "wipe_left", "wipe_right", "zoom_in", "zoom_out",
            "black_title", "whoosh", "glitch", "flash",
        }
        assert set(EFFECTS.keys()) == expected

    @patch("modules.review_engine.transition_effects._get_segment_duration", return_value=5.0)
    @patch("modules.review_engine.transition_effects.subprocess.run")
    @patch("modules.review_engine.transition_effects.os.path.isfile", return_value=True)
    def test_fade_black(self, mock_isfile, mock_run, mock_dur):
        mock_run.return_value = MagicMock(returncode=0)
        result = apply_transition("/a.mp4", "/b.mp4", "/out.mp4", "fade_black", 0.5)
        assert result == "/out.mp4"
        cmd = mock_run.call_args[0][0]
        assert "xfade" in " ".join(cmd)

    @patch("modules.review_engine.transition_effects._get_segment_duration", return_value=5.0)
    @patch("modules.review_engine.transition_effects.subprocess.run")
    @patch("modules.review_engine.transition_effects.os.path.isfile", return_value=True)
    def test_cross_dissolve(self, mock_isfile, mock_run, mock_dur):
        mock_run.return_value = MagicMock(returncode=0)
        result = apply_transition("/a.mp4", "/b.mp4", "/out.mp4", "cross_dissolve")
        assert result == "/out.mp4"

    def test_unknown_effect(self):
        with pytest.raises(RenderError, match="Unknown transition"):
            apply_transition("/a.mp4", "/b.mp4", "/out.mp4", "rainbow_sparkle")

    def test_missing_segment(self):
        with pytest.raises(RenderError, match="not found"):
            apply_transition("/nonexistent.mp4", "/b.mp4", "/out.mp4")
