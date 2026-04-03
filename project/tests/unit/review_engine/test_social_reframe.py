"""Tests for SocialReframe — R19."""

import pytest
from unittest.mock import patch, MagicMock

from modules.review_engine.social_reframe import (
    PLATFORMS,
    reframe,
)
from modules.review_engine.exceptions import RenderError


class TestSocialReframe:

    def test_all_platforms_defined(self):
        expected = {"tiktok", "instagram", "youtube", "shorts", "wechat", "xiaohongshu", "square"}
        assert set(PLATFORMS.keys()) == expected

    @patch("modules.review_engine.social_reframe._get_video_info",
           return_value={"width": 1920, "height": 1080, "duration": 30})
    @patch("modules.review_engine.social_reframe.subprocess.run")
    @patch("modules.review_engine.social_reframe.os.path.isfile", return_value=True)
    def test_crop_correct_ratio(self, mock_isfile, mock_run, mock_info):
        """Tiktok 9:16 crop from 1920x1080 source."""
        mock_run.return_value = MagicMock(returncode=0)
        reframe("/input.mp4", "/output.mp4", "tiktok")

        cmd = mock_run.call_args[0][0]
        vf_idx = cmd.index("-vf")
        crop_filter = cmd[vf_idx + 1]
        # 9:16 from 1920x1080 → crop height = 1080, crop width = 1080 * 9/16 = 607.5 → 606 (even)
        assert "crop=" in crop_filter

    @patch("modules.review_engine.social_reframe._get_video_info",
           return_value={"width": 1920, "height": 1080, "duration": 90})
    @patch("modules.review_engine.social_reframe.subprocess.run")
    @patch("modules.review_engine.social_reframe.os.path.isfile", return_value=True)
    def test_max_duration_enforced(self, mock_isfile, mock_run, mock_info):
        """Shorts (60s max) trims a 90s video."""
        mock_run.return_value = MagicMock(returncode=0)
        reframe("/input.mp4", "/output.mp4", "shorts")

        cmd = mock_run.call_args[0][0]
        assert "-t" in cmd
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "60"

    def test_unknown_platform(self):
        with pytest.raises(RenderError, match="Unknown platform"):
            reframe("/input.mp4", "/output.mp4", "myspace")
