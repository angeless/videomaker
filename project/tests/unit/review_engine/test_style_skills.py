"""Tests for StyleSkill — R20."""

import pytest

from modules.review_engine.style_skills import (
    StyleConfig,
    auto_extract_style,
    list_styles,
    load_style,
    save_style,
)

try:
    import yaml as _yaml
except ImportError:
    _yaml = None

_skip_no_yaml = pytest.mark.skipif(_yaml is None, reason="pyyaml not installed")


class TestStyleSkills:

    @_skip_no_yaml
    def test_save_load_roundtrip(self, tmp_path):
        """Save a style and load it back."""
        style = StyleConfig(
            name="vlog_warm",
            color_grade="warm",
            font="PingFang SC",
            transition="fade_black",
            audio_preset="voice",
            pacing="fast",
            bgm_volume_db=-15.0,
        )
        path = save_style(style, str(tmp_path))
        loaded = load_style(path)

        assert loaded.name == "vlog_warm"
        assert loaded.color_grade == "warm"
        assert loaded.pacing == "fast"
        assert loaded.bgm_volume_db == -15.0

    def test_auto_extract(self):
        """Auto-extract style from project data."""
        data = {
            "project_name": "canada_trip",
            "render_settings": {"color_grade": "cinematic", "pacing": "slow"},
            "audio_settings": {"preset": "music", "bgm_volume_db": -10.0},
            "subtitle_settings": {"font": "Noto Sans"},
        }
        style = auto_extract_style(data)
        assert style.name == "canada_trip"
        assert style.color_grade == "cinematic"
        assert style.audio_preset == "music"
        assert style.font == "Noto Sans"

    @_skip_no_yaml
    def test_list_styles(self, tmp_path):
        """List all styles in a directory."""
        save_style(StyleConfig(name="a"), str(tmp_path))
        save_style(StyleConfig(name="b"), str(tmp_path))
        styles = list_styles(str(tmp_path))
        assert len(styles) == 2
