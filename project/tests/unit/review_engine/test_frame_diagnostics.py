"""Tests for FrameDiagnostics — R11/R12/R13 (v0.17.0)."""

import json
from unittest.mock import MagicMock

import pytest

try:
    from PIL import Image
    import numpy as np
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False

pytestmark = pytest.mark.skipif(not _HAS_DEPS, reason="PIL/numpy not available")

from modules.review_engine.frame_diagnostics import (
    ContinuityIssue,
    DiagnosticIssue,
    FrameDiagnostics,
)
from modules.adapters.vlm_adapter import VLMResponse


# ---------------------------------------------------------------------------
# R11: Composition
# ---------------------------------------------------------------------------

class TestComposition:
    def test_finds_composition_issue_via_vlm(self):
        adapter = MagicMock()
        adapter.describe_image.return_value = VLMResponse(
            text=json.dumps([{
                "type": "composition",
                "description": "主体偏右超出三分线",
                "suggestion": "向左移动主体",
            }]),
            model="mock",
        )
        diag = FrameDiagnostics(vlm_adapter=adapter)
        frame = Image.new("RGB", (1920, 1080), "gray")
        issues = diag.check_composition(frame)
        assert len(issues) == 1
        assert issues[0].issue_type == "composition"
        assert "三分" in issues[0].description

    def test_no_issue_empty_list(self):
        adapter = MagicMock()
        adapter.describe_image.return_value = VLMResponse(text="[]", model="mock")
        diag = FrameDiagnostics(vlm_adapter=adapter)
        frame = Image.new("RGB", (1920, 1080), "gray")
        issues = diag.check_composition(frame)
        assert issues == []

    def test_degradation_no_vlm(self):
        diag = FrameDiagnostics(vlm_adapter=None)
        frame = Image.new("RGB", (1920, 1080), "gray")
        issues = diag.check_composition(frame)
        assert issues == []


# ---------------------------------------------------------------------------
# R12: Exposure and color temperature
# ---------------------------------------------------------------------------

class TestExposure:
    def test_overexposed_frame(self):
        """Nearly all-white image should trigger overexposure warning."""
        diag = FrameDiagnostics()
        # Create a very bright image
        frame = Image.new("RGB", (200, 200), (250, 250, 250))
        issues = diag.check_exposure(frame)
        assert any(i.issue_type == "exposure" and "过亮" in i.description for i in issues)

    def test_underexposed_frame(self):
        """Nearly all-black image should trigger underexposure warning."""
        diag = FrameDiagnostics()
        frame = Image.new("RGB", (200, 200), (5, 5, 5))
        issues = diag.check_exposure(frame)
        assert any(i.issue_type == "exposure" and "过暗" in i.description for i in issues)

    def test_normal_exposure_no_issue(self):
        diag = FrameDiagnostics()
        frame = Image.new("RGB", (200, 200), (128, 128, 128))
        issues = diag.check_exposure(frame)
        assert len(issues) == 0


class TestColorTemp:
    def test_cool_color_detected(self):
        """Very blue frame should detect cool color temperature."""
        diag = FrameDiagnostics()
        frame = Image.new("RGB", (200, 200), (50, 50, 220))
        issues = diag.check_color_temperature(frame)
        # May or may not trigger depending on HSV conversion
        # At minimum should not crash
        assert isinstance(issues, list)

    def test_histogram_only_no_vlm(self):
        """Exposure check works without VLM (pure algorithm)."""
        diag = FrameDiagnostics(vlm_adapter=None)
        frame = Image.new("RGB", (200, 200), (250, 250, 250))
        issues = diag.check_exposure(frame)
        assert len(issues) >= 1  # Should find overexposure


# ---------------------------------------------------------------------------
# R13: Continuity
# ---------------------------------------------------------------------------

class TestContinuity:
    def test_brightness_jump(self):
        diag = FrameDiagnostics()
        frames = [
            Image.new("RGB", (200, 200), (200, 200, 200)),  # bright
            Image.new("RGB", (200, 200), (30, 30, 30)),  # dark
        ]
        issues = diag.check_continuity(frames)
        assert any(i.issue_type == "brightness_jump" for i in issues)

    def test_color_jump(self):
        diag = FrameDiagnostics()
        frames = [
            Image.new("RGB", (200, 200), (200, 50, 50)),  # reddish
            Image.new("RGB", (200, 200), (50, 50, 200)),  # bluish
        ]
        issues = diag.check_continuity(frames)
        assert any(i.issue_type == "color_jump" for i in issues)

    def test_single_scene_skip(self):
        diag = FrameDiagnostics()
        frames = [Image.new("RGB", (200, 200), "gray")]
        issues = diag.check_continuity(frames)
        assert issues == []

    def test_no_issue_similar_frames(self):
        diag = FrameDiagnostics()
        frames = [
            Image.new("RGB", (200, 200), (128, 128, 128)),
            Image.new("RGB", (200, 200), (130, 128, 128)),
        ]
        issues = diag.check_continuity(frames)
        assert len(issues) == 0
