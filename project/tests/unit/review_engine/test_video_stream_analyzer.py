"""Unit tests for VideoStreamAnalyzer (B2)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from modules.review_engine.contracts import SampledFrame, StreamAnalysis
from modules.review_engine.video_stream_analyzer import VideoStreamAnalyzer


def _make_frame(scene_idx=0, ts_ms=0):
    """Create a mock SampledFrame with a fake PIL Image."""
    img = MagicMock()
    img.convert.return_value = img
    return SampledFrame(frame=img, timestamp_ms=ts_ms, scene_idx=scene_idx)


def _adapter_mock(text_value=None, side_effect=None):
    """Build a VLM adapter mock matching the real protocol:
    describe_image(image, prompt) -> object with a .text attribute.

    This reflects OpenAIVisionAdapter / ClaudeVisionAdapter / StubVLMAdapter,
    which all return VLMResponse(text=...). Previous tests mocked the
    non-existent describe_region kwarg protocol — they silently no-op'd in
    production because real adapters don't have that method.
    """
    vlm = MagicMock()
    # Spec the method so hasattr(vlm, "describe_image") is True AND other
    # random attribute access doesn't silently succeed.
    if side_effect is not None:
        vlm.describe_image.side_effect = side_effect
    else:
        vlm.describe_image.return_value = SimpleNamespace(text=text_value or "")
    # Remove the auto-created describe_region so the shim's hasattr check
    # for describe_image wins (MagicMock would otherwise auto-create both).
    del vlm.describe_region
    return vlm


# ── T1: delegates to check_continuity ────────────────────────────

def test_delegates_to_check_continuity():
    """B2 must delegate brightness/color checks to FrameDiagnostics."""
    analyzer = VideoStreamAnalyzer(vlm_adapter=None)
    frames = [_make_frame(0, 0), _make_frame(1, 5000)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]) as mock_cc:
        result = analyzer.analyze(frames)
        mock_cc.assert_called_once()


# ── T2: transition quality (VLM available, modern protocol) ──────

def test_transition_quality_with_vlm():
    """With VLM, transition quality issues should be detected (describe_image protocol)."""
    vlm = _adapter_mock(text_value="1 - poor transition")
    analyzer = VideoStreamAnalyzer(vlm_adapter=vlm)
    frames = [_make_frame(0, 0), _make_frame(1, 5000)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]):
        result = analyzer.analyze(frames)
    # Score 1 → should create a transition_quality issue
    assert any(i.issue_type == "transition_quality" for i in result.issues)


# ── T3: narrative with VLM (modern protocol) ─────────────────────

def test_narrative_with_vlm():
    """With VLM, narrative arc should contain scene descriptions."""
    vlm = _adapter_mock(text_value="sunset beach scene")
    analyzer = VideoStreamAnalyzer(vlm_adapter=vlm)
    frames = [_make_frame(0, 0)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]):
        result = analyzer.analyze(frames)
    assert "叙事弧线" in result.narrative_arc
    assert "sunset beach scene" in result.narrative_arc


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
    vlm = _adapter_mock(side_effect=TimeoutError("VLM timeout"))
    analyzer = VideoStreamAnalyzer(vlm_adapter=vlm)
    frames = [_make_frame(0, 0), _make_frame(1, 5000)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]):
        result = analyzer.analyze(frames)
    assert isinstance(result, StreamAnalysis)
    # Every VLM call fails → no scene descriptions → narrative_arc falls to
    # the fallback message; none of the failures should crash the pipeline.
    assert "无法提取叙事弧线" in result.narrative_arc or "失败" in result.narrative_arc


# ── T6: legacy describe_region protocol still supported ──────────

def test_legacy_describe_region_protocol_supported():
    """Adapters that only expose describe_region (like VLMAnalyzer wrapper)
    must still work — the shim falls back when describe_image is absent."""
    vlm = MagicMock()
    # Remove describe_image so hasattr returns False and the shim falls through
    del vlm.describe_image
    vlm.describe_region.return_value = {"description": "2 - borderline"}
    analyzer = VideoStreamAnalyzer(vlm_adapter=vlm)
    frames = [_make_frame(0, 0), _make_frame(1, 5000)]

    with patch.object(analyzer._diag, "check_continuity", return_value=[]):
        result = analyzer.analyze(frames)
    # Score 2 → still warning severity
    assert any(i.issue_type == "transition_quality" for i in result.issues)
