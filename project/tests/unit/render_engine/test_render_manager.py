"""Unit tests for RenderManager (D3)."""

import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

from modules.review_engine.contracts import Clip, Segment
from modules.render_engine.render_manager import RenderManager, RenderError


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def profile():
    """Minimal HardwareProfile mock."""
    p = MagicMock()
    p.ffmpeg_path = "ffmpeg"
    p.cpu.logical_count = 4
    p.memory.total_gb = 16.0
    p.gpu.name = "none"
    return p


@pytest.fixture
def manager(profile):
    return RenderManager(profile)


def _clip(source_path="/tmp/clip.mp4", in_ms=0, out_ms=3000):
    return Clip(
        clip_id="c1",
        track_id="t1",
        start_ms=0,
        end_ms=out_ms - in_ms,
        source_path=source_path,
        source_in_ms=in_ms,
        source_out_ms=out_ms,
    )


# ── Test 1: clip_to_segment ─────────────────────────────────────────


def test_clip_to_segment():
    """Clip → Segment adapter maps source_in/out to start/end."""
    clip = Clip(
        clip_id="c1", track_id="t1",
        start_ms=5000, end_ms=10000,
        source_path="/tmp/source.mp4",
        source_in_ms=1000, source_out_ms=6000,
    )
    seg = RenderManager.clip_to_segment(clip)

    assert isinstance(seg, Segment)
    assert seg.source_path == "/tmp/source.mp4"
    assert seg.start_ms == 1000  # source_in_ms
    assert seg.end_ms == 6000    # source_out_ms


# ── Test 2: parallel_render ──────────────────────────────────────────


@patch("modules.render_engine.render_manager.suggest_max_concurrent", return_value=2)
@patch("modules.render_engine.render_manager.subprocess.run")
def test_parallel_render(mock_run, mock_concurrent, manager, tmp_path):
    """Multiple clips are rendered in parallel and concatenated."""
    output = str(tmp_path / "output.mp4")

    # Mock FFmpeg success: create output files
    def _ffmpeg_side_effect(cmd, **kwargs):
        # Find the output path (last arg or after -i flag)
        out = cmd[-1]
        if out.endswith(".mp4"):
            open(out, "w").close()  # create empty file
        elif out.endswith(".txt"):
            pass
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    mock_run.side_effect = _ffmpeg_side_effect

    clips = [_clip(in_ms=0, out_ms=3000), _clip(in_ms=3000, out_ms=6000)]
    result = manager.render_timeline(clips, output)

    assert result == output
    # FFmpeg called: 2 segments + 1 concat = 3 calls
    assert mock_run.call_count == 3


# ── Test 3: progress_callback ────────────────────────────────────────


@patch("modules.render_engine.render_manager.suggest_max_concurrent", return_value=1)
@patch("modules.render_engine.render_manager.subprocess.run")
def test_progress_callback(mock_run, mock_concurrent, manager, tmp_path):
    """Progress callback is called after each segment completes."""
    output = str(tmp_path / "output.mp4")

    def _ffmpeg_ok(cmd, **kwargs):
        out = cmd[-1]
        if out.endswith(".mp4"):
            open(out, "w").close()
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        return m

    mock_run.side_effect = _ffmpeg_ok
    progress = MagicMock()

    clips = [_clip(in_ms=0, out_ms=2000), _clip(in_ms=2000, out_ms=4000)]
    manager.render_timeline(clips, output, progress_callback=progress)

    assert progress.call_count == 2
    # Should have been called with (1, 2) and (2, 2)
    progress.assert_any_call(1, 2)
    progress.assert_any_call(2, 2)


# ── Test 4: segment_failure ──────────────────────────────────────────


@patch("modules.render_engine.render_manager.suggest_max_concurrent", return_value=1)
@patch("modules.render_engine.render_manager.subprocess.run")
def test_segment_failure_with_retry(mock_run, mock_concurrent, manager, tmp_path):
    """Segment failure retries once, then raises on second failure."""
    output = str(tmp_path / "output.mp4")

    fail_result = MagicMock()
    fail_result.returncode = 1
    fail_result.stderr = "encode error"
    mock_run.return_value = fail_result

    clips = [_clip()]
    with pytest.raises(RenderError, match="failed after retry"):
        manager.render_timeline(clips, output)


# ── Test 5: concat ───────────────────────────────────────────────────


@patch("modules.render_engine.render_manager.suggest_max_concurrent", return_value=1)
@patch("modules.render_engine.render_manager.subprocess.run")
def test_concat_single_segment(mock_run, mock_concurrent, manager, tmp_path):
    """Single segment skips concat (just copies)."""
    output = str(tmp_path / "output.mp4")

    def _ffmpeg_ok(cmd, **kwargs):
        out = cmd[-1]
        if out.endswith(".mp4"):
            open(out, "w").close()
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        return m

    mock_run.side_effect = _ffmpeg_ok

    clips = [_clip()]
    manager.render_timeline(clips, output)

    # Only 1 FFmpeg call (render), no concat call
    assert mock_run.call_count == 1


# ── Test 6: cleanup ──────────────────────────────────────────────────


@patch("modules.render_engine.render_manager.suggest_max_concurrent", return_value=1)
@patch("modules.render_engine.render_manager.subprocess.run")
def test_temp_dir_cleanup(mock_run, mock_concurrent, manager, tmp_path):
    """Temp directory is cleaned up even on failure."""
    output = str(tmp_path / "output.mp4")

    fail_result = MagicMock()
    fail_result.returncode = 1
    fail_result.stderr = "error"
    mock_run.return_value = fail_result

    clips = [_clip()]
    with pytest.raises(RenderError):
        manager.render_timeline(clips, output)

    # Output should not exist
    assert not os.path.exists(output)
    # Temp dirs matching ve_render_* should be cleaned
    # (We can't check specific paths, but the test shouldn't leave debris)
