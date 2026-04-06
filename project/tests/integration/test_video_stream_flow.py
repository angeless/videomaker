"""Integration tests for video stream analysis pipeline (B5).

End-to-end: FrameSampler → VideoStreamAnalyzer → SceneSummarizer → API.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from modules.review_engine.contracts import SampledFrame, StreamAnalysis


# ── Helpers ──────────────────────────────────────────────────────────


def _make_frames(n=10, scenes=3):
    """Create n mock SampledFrame objects across `scenes` scenes."""
    frames = []
    for i in range(n):
        f = SampledFrame(
            frame=MagicMock(name=f"pil_frame_{i}"),
            timestamp_ms=i * 1000,
            scene_idx=i % scenes,
            source="uniform",
        )
        frames.append(f)
    return frames


def _stub_vlm():
    """VLM adapter stub that returns generic descriptions."""
    adapter = MagicMock()
    call_count = [0]

    def _describe(frame=None, strokes=None, prompt=""):
        call_count[0] += 1
        if "Summarize" in prompt:
            return {"description": "A summary of the scene with various elements"}
        return {"description": f"Frame showing object_{call_count[0]} and element_{call_count[0]}"}

    adapter.describe_region.side_effect = _describe
    adapter.get_model_info.return_value = {"available": True, "provider": "stub", "model": "v1"}
    return adapter


# ── Test 1: e2e_pipeline ─────────────────────────────────────────────


def test_e2e_pipeline():
    """Full pipeline: frames → analyze → summarize → results."""
    from modules.review_engine.video_stream_analyzer import VideoStreamAnalyzer
    from modules.review_engine.scene_summarizer import SceneSummarizer

    frames = _make_frames(9, scenes=3)
    vlm = _stub_vlm()

    # Mock FrameDiagnostics.check_continuity to return empty (no issues)
    with patch("modules.review_engine.video_stream_analyzer.FrameDiagnostics") as MockDiag:
        mock_diag = MagicMock()
        mock_diag.check_continuity.return_value = []
        MockDiag.return_value = mock_diag

        analyzer = VideoStreamAnalyzer(vlm_adapter=vlm)
        analysis = analyzer.analyze(frames)

        assert isinstance(analysis, StreamAnalysis)
        assert len(analysis.scene_descriptions) == 3  # 3 scenes

        summarizer = SceneSummarizer(vlm_adapter=vlm)
        summaries = summarizer.summarize(analysis, frames)

        assert len(summaries) == 3
        for idx in range(3):
            assert idx in summaries
            assert summaries[idx].summary != ""
            assert len(summaries[idx].key_objects) > 0


# ── Test 2: degradation (no VLM) ────────────────────────────────────


def test_degradation_no_vlm():
    """Pipeline works without VLM — pure algorithmic analysis."""
    from modules.review_engine.video_stream_analyzer import VideoStreamAnalyzer
    from modules.review_engine.scene_summarizer import SceneSummarizer

    frames = _make_frames(6, scenes=2)

    with patch("modules.review_engine.video_stream_analyzer.FrameDiagnostics") as MockDiag:
        mock_diag = MagicMock()
        mock_diag.check_continuity.return_value = []
        MockDiag.return_value = mock_diag

        analyzer = VideoStreamAnalyzer(vlm_adapter=None)
        analysis = analyzer.analyze(frames)

        assert analysis.narrative_arc != ""  # should have fallback text
        assert len(analysis.scene_descriptions) == 2

        summarizer = SceneSummarizer(vlm_adapter=None)
        summaries = summarizer.summarize(analysis, frames)
        assert len(summaries) == 2


# ── Test 3: api_chain ────────────────────────────────────────────────


def test_api_chain():
    """POST analyze-stream → GET stream-analysis (mock backend)."""
    from flask import Flask
    from modules.app_api.routes.vlm_routes import create_vlm_blueprint

    store = MagicMock()
    store.get_session.return_value = {"id": "s1"}
    vlm = _stub_vlm()

    app = Flask(__name__)
    bp = create_vlm_blueprint(
        review_store_getter=lambda: store,
        vlm_adapter_getter=lambda: vlm,
    )
    app.register_blueprint(bp)
    app.config["TESTING"] = True
    client = app.test_client()

    # Trigger
    resp = client.post("/api/review/s1/vlm/analyze-stream", json={"video_path": "/tmp/t.mp4"})
    assert resp.status_code == 202

    # Result not available yet (async) — returns 404
    resp2 = client.get("/api/review/s1/vlm/stream-analysis")
    assert resp2.status_code == 404  # not yet computed (async)


# ── Test 4: performance ──────────────────────────────────────────────


def test_performance_50_frames():
    """50 frames analyzed in under 30s with stub VLM."""
    from modules.review_engine.video_stream_analyzer import VideoStreamAnalyzer
    from modules.review_engine.scene_summarizer import SceneSummarizer

    frames = _make_frames(50, scenes=10)

    with patch("modules.review_engine.video_stream_analyzer.FrameDiagnostics") as MockDiag:
        mock_diag = MagicMock()
        mock_diag.check_continuity.return_value = []
        MockDiag.return_value = mock_diag

        start = time.time()
        analyzer = VideoStreamAnalyzer(vlm_adapter=_stub_vlm())
        analysis = analyzer.analyze(frames)
        summarizer = SceneSummarizer(vlm_adapter=_stub_vlm())
        summaries = summarizer.summarize(analysis, frames)
        elapsed = time.time() - start

        assert elapsed < 30.0, f"50-frame analysis took {elapsed:.1f}s (limit: 30s)"
        assert len(summaries) == 10


# ── Test 5: regression ───────────────────────────────────────────────


def test_regression_existing_tests():
    """Smoke check: existing review engine imports still work."""
    from modules.review_engine.contracts import SampledFrame, StreamAnalysis, SceneSummary, Clip
    from modules.review_engine.scene_summarizer import SceneSummarizer
    from modules.review_engine.video_stream_analyzer import VideoStreamAnalyzer

    # Verify classes are importable and constructable
    assert SampledFrame(frame=None, timestamp_ms=0) is not None
    assert StreamAnalysis() is not None
    assert SceneSummary() is not None
    assert VideoStreamAnalyzer() is not None
    assert SceneSummarizer() is not None
