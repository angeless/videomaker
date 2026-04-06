"""Unit tests for VideoStreamAnalyzer (B2)."""

from unittest.mock import MagicMock, patch

import pytest

from modules.review_engine.contracts import SampledFrame, StreamAnalysis
from modules.review_engine.video_stream_analyzer import VideoStreamAnalyzer


def _make_frame(scene_idx=0, ts_ms=0):
    """Create a mock SampledFrame with a fake PIL Image."""
    img = MagicMock()
    img.convert.return_value = img
    return SampledFrame(frame=img, timestamp_ms=ts_ms, scene_idx=scene_idx)


# ── T1: delegates to check_continuity ────────────────────────────

def test_delegates_to_check_continuity():
    """B2 must delegate brightness/color checks to FrameDiagnostics."""
    analyzer = VideoStreamAnalyzer(vlm_adapter=None)
    frames = [_make_frame(0, 0), _make_frame(1, 5000)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]) as mock_cc:
        result = analyzer.analyze(frames)
        mock_cc.assert_called_once()


# ── T2: transition quality (VLM available) ───────────────────────

def test_transition_quality_with_vlm():
    """With VLM, transition quality issues should be detected."""
    vlm = MagicMock()
    vlm.describe_region.return_value = {"description": "1 - poor transition"}
    analyzer = VideoStreamAnalyzer(vlm_adapter=vlm)
    frames = [_make_frame(0, 0), _make_frame(1, 5000)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]):
        result = analyzer.analyze(frames)
    # Score 1 → should create a transition_quality issue
    assert any(i.issue_type == "transition_quality" for i in result.issues)


# ── T3: narrative with VLM ───────────────────────────────────────

def test_narrative_with_vlm():
    """With VLM, narrative arc should contain scene descriptions."""
    vlm = MagicMock()
    vlm.describe_region.return_value = {"description": "sunset beach scene"}
    analyzer = VideoStreamAnalyzer(vlm_adapter=vlm)
    frames = [_make_frame(0, 0)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]):
        result = analyzer.analyze(frames)
    assert "叙事弧线" in result.narrative_arc


# ── T4: narrative without VLM ────────────────────────────────────

def test_narrative_without_vlm():
    """Without VLM, narrative should indicate unavailability."""
    analyzer = VideoStreamAnalyzer(vlm_adapter=None)
    frames = [_make_frame(0, 0)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]):
        result = analyzer.analyze(frames)
    assert "VLM 不可用" in result.narrative_arc


# ── T5: timeout / error handling ─────────────────────────────────

def test_vlm_error_handled_gracefully():
    """VLM errors should not crash the analyzer."""
    vlm = MagicMock()
    vlm.describe_region.side_effect = TimeoutError("VLM timeout")
    analyzer = VideoStreamAnalyzer(vlm_adapter=vlm)
    frames = [_make_frame(0, 0), _make_frame(1, 5000)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]):
        result = analyzer.analyze(frames)
    assert isinstance(result, StreamAnalysis)
    # Should not crash, narrative should mention failure
    assert "失败" in result.narrative_arc or "VLM" in result.narrative_arc
