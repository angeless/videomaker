"""Unit tests for FrameSampler (B1)."""

import os
from unittest.mock import patch, MagicMock

import pytest

from modules.review_engine.frame_sampler import FrameSampler


@pytest.fixture
def sampler():
    return FrameSampler(max_frames=50)


def _mock_duration(ms):
    """Mock _get_video_duration_ms to return a fixed value."""
    return patch(
        "modules.review_engine.frame_sampler._get_video_duration_ms",
        return_value=ms,
    )


def _mock_extract():
    """Mock _extract_frame_pil to return a fake image."""
    fake_img = MagicMock()
    fake_img.__bool__ = lambda self: True
    return patch(
        "modules.review_engine.frame_sampler._extract_frame_pil",
        return_value=fake_img,
    )


def _mock_exists():
    return patch("modules.review_engine.frame_sampler.os.path.exists", return_value=True)


# ── T1: scene_boundary strategy ─────────────────────────────────

def test_scene_boundary(sampler):
    with _mock_exists(), _mock_duration(30000), _mock_extract():
        frames = sampler.sample("/fake/video.mp4", strategy="scene_boundary",
                                scene_boundaries=[0, 5000, 15000, 25000])
    assert len(frames) == 4
    assert all(f.source == "scene_boundary" for f in frames)
    assert frames[0].timestamp_ms == 0
    assert frames[-1].timestamp_ms == 25000


# ── T2: uniform strategy ────────────────────────────────────────

def test_uniform(sampler):
    with _mock_exists(), _mock_duration(25000), _mock_extract():
        frames = sampler.sample("/fake/video.mp4", strategy="uniform", interval_ms=5000)
    # 0, 5000, 10000, 15000, 20000 = 5 frames
    assert len(frames) == 5
    assert all(f.source == "uniform" for f in frames)


# ── T3: hybrid strategy ─────────────────────────────────────────

def test_hybrid(sampler):
    with _mock_exists(), _mock_duration(60000), _mock_extract():
        frames = sampler.sample("/fake/video.mp4", strategy="hybrid",
                                scene_boundaries=[0, 30000])
    # Scene 0: boundary at 0, hybrid at 10000, 20000
    # Scene 1: boundary at 30000, hybrid at 40000, 50000
    assert len(frames) >= 4  # At least boundaries + some intra


# ── T4: max_frames cap ──────────────────────────────────────────

def test_max_cap():
    small = FrameSampler(max_frames=3)
    with _mock_exists(), _mock_duration(100000), _mock_extract():
        frames = small.sample("/fake/video.mp4", strategy="uniform", interval_ms=5000)
    assert len(frames) <= 3


# ── T5: empty/missing video ─────────────────────────────────────

def test_empty_video(sampler):
    # Non-existent file
    frames = sampler.sample("/nonexistent/video.mp4")
    assert frames == []
