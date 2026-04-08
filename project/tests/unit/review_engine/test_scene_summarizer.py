"""Unit tests for SceneSummarizer (B3)."""

from unittest.mock import MagicMock

import pytest

from modules.review_engine.contracts import (
    SampledFrame,
    SceneSummary,
    StreamAnalysis,
)
from modules.review_engine.scene_summarizer import SceneSummarizer


# ── Helpers ──────────────────────────────────────────────────────────


def _frame(ts_ms: int, scene_idx: int = 0) -> SampledFrame:
    """Create a test frame with a dummy PIL image."""
    return SampledFrame(
        frame=MagicMock(name=f"frame_{ts_ms}"),
        timestamp_ms=ts_ms,
        scene_idx=scene_idx,
        source="uniform",
    )


def _vlm_mock(descriptions: dict):
    """Create a VLM adapter mock that returns descriptions keyed by prompt substring."""
    adapter = MagicMock()

    def _describe(frame=None, strokes=None, prompt=""):
        for key, val in descriptions.items():
            if key in prompt:
                return {"description": val}
        return {"description": "default description"}

    adapter.describe_region.side_effect = _describe
    return adapter


# ── Test 1: merge_descriptions ───────────────────────────────────────


def test_merge_descriptions():
    """Multi-frame descriptions for the same scene are merged and de-duplicated."""
    frames = [_frame(0, scene_idx=0), _frame(5000, scene_idx=0)]
    analysis = StreamAnalysis(
        scene_descriptions={0: "A person walking on the beach near the ocean"},
    )

    # VLM adds a second description for the second frame
    vlm = _vlm_mock({"Describe this": "A surfer riding waves near the shoreline"})
    summarizer = SceneSummarizer(vlm_adapter=vlm)
    result = summarizer.summarize(analysis, frames)

    assert 0 in result
    scene = result[0]
    # Objects from both descriptions are merged (de-duped)
    assert "person" in scene.key_objects
    assert "beach" in scene.key_objects
    assert "ocean" in scene.key_objects
    assert "surfer" in scene.key_objects
    # No duplicates
    assert len(scene.key_objects) == len(set(scene.key_objects))


# ── Test 2: representative_frame ─────────────────────────────────────


def test_representative_frame():
    """Frame with the most objects is selected as representative."""
    frames = [
        _frame(0, scene_idx=0),     # first frame: simple description
        _frame(3000, scene_idx=0),   # second frame: richer description
    ]
    analysis = StreamAnalysis(
        scene_descriptions={0: "A cat"},  # simple — few objects
    )
    # VLM returns a richer description for the second frame
    vlm = _vlm_mock({"Describe this": "A fluffy orange cat sleeping on a velvet sofa near a window"})
    summarizer = SceneSummarizer(vlm_adapter=vlm)
    result = summarizer.summarize(analysis, frames)

    scene = result[0]
    # Second frame has more objects → should be representative
    assert scene.representative_frame_ms == 3000


# ── Test 3: vlm_summary ─────────────────────────────────────────────


def test_vlm_summary():
    """With VLM and multiple descriptions, a condensed summary is generated."""
    frames = [_frame(0, scene_idx=0), _frame(2000, scene_idx=0)]
    analysis = StreamAnalysis(
        scene_descriptions={0: "A runner crossing the finish line"},
    )

    vlm = _vlm_mock({
        "Describe this": "Crowd cheering in the stadium",
        "Summarize": "A runner wins the race as the crowd celebrates",
    })
    summarizer = SceneSummarizer(vlm_adapter=vlm)
    result = summarizer.summarize(analysis, frames)

    scene = result[0]
    assert "runner wins" in scene.summary.lower() or "race" in scene.summary.lower()


# ── Test 4: degradation (no VLM) ────────────────────────────────────


def test_degradation_no_vlm():
    """Without VLM, first frame description is used as-is for summary."""
    frames = [_frame(0, scene_idx=0), _frame(5000, scene_idx=0)]
    analysis = StreamAnalysis(
        scene_descriptions={0: "A mountain landscape with snow"},
    )

    summarizer = SceneSummarizer(vlm_adapter=None)
    result = summarizer.summarize(analysis, frames)

    scene = result[0]
    assert scene.summary == "A mountain landscape with snow"
    assert "mountain" in scene.key_objects
    assert scene.duration_ms == 5000
    assert scene.representative_frame_ms == 0  # only 1 description → first frame


# ── Edge case: empty frames ──────────────────────────────────────────


def test_empty_frames():
    """Empty frame list returns empty result."""
    analysis = StreamAnalysis()
    summarizer = SceneSummarizer()
    result = summarizer.summarize(analysis, [])
    assert result == {}
