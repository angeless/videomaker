"""Integration tests for GPU render pipeline (D6).

End-to-end: HardwareProfile → EncodingParams → RenderManager → output.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from modules.review_engine.contracts import Clip


# ── Helpers ──────────────────────────────────────────────────────────


def _mock_profile(*, has_videotoolbox=False, has_nvenc=False):
    """Create a mock HardwareProfile."""
    p = MagicMock()
    p.ffmpeg_path = "ffmpeg"
    p.cpu.logical_cores = 4
    p.cpu.physical_cores = 2
    p.memory.total_gb = 16.0
    p.memory.available_gb = 8.0
    p.gpu.vendor = "apple" if has_videotoolbox else "none"
    p.gpu.model = "Apple M1" if has_videotoolbox else "none"
    p.gpu.has_videotoolbox = has_videotoolbox
    p.gpu.has_nvenc = has_nvenc
    p.gpu.has_vaapi = False
    p.ffmpeg_hwaccels = ["videotoolbox"] if has_videotoolbox else []
    p.ffmpeg_decoders = []
    p.has_hevc_hw_decode = False
    return p


def _test_clips(n=4):
    return [
        Clip(
            clip_id=f"c{i}", track_id="t1",
            start_ms=i * 3000, end_ms=(i + 1) * 3000,
            source_path="/tmp/test.mp4",
            source_in_ms=i * 3000, source_out_ms=(i + 1) * 3000,
        ) for i in range(n)
    ]


# ── Test 1: full_pipeline ────────────────────────────────────────────


@patch("modules.render_engine.render_manager.subprocess.run")
@patch("modules.render_engine.render_manager.suggest_max_concurrent", return_value=2)
def test_full_pipeline(mock_concurrent, mock_run, tmp_path):
    """Full pipeline: profile → manager → parallel render → concat → output."""
    from modules.render_engine.render_manager import RenderManager

    output = str(tmp_path / "output.mp4")

    def _ffmpeg_ok(cmd, **kw):
        out = cmd[-1]
        if out.endswith(".mp4"):
            open(out, "w").close()
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        return m

    mock_run.side_effect = _ffmpeg_ok

    profile = _mock_profile(has_videotoolbox=True)
    manager = RenderManager(profile)
    clips = _test_clips(4)

    progress_log = []
    result = manager.render_timeline(clips, output, progress_callback=lambda d, t: progress_log.append((d, t)))

    assert result == output
    assert len(progress_log) == 4  # 4 segments
    assert mock_run.call_count == 5  # 4 renders + 1 concat


# ── Test 2: cpu_fallback ─────────────────────────────────────────────


def test_cpu_fallback():
    """No GPU → RenderManager uses libx264 (CPU-only profile)."""
    from modules.render_engine.render_manager import RenderManager
    from modules.hardware.encoding_strategy import choose_encoder

    profile = _mock_profile(has_videotoolbox=False, has_nvenc=False)
    enc = choose_encoder(profile)
    assert enc.video_encoder == "libx264"

    manager = RenderManager(profile)
    seg = RenderManager.clip_to_segment(_test_clips(1)[0])
    assert seg.source_path == "/tmp/test.mp4"


# ── Test 3: hw_accel ─────────────────────────────────────────────────


def test_hw_accel_detection():
    """With VideoToolbox → encoder should prefer hardware acceleration."""
    from modules.hardware.encoding_strategy import choose_encoder

    profile = _mock_profile(has_videotoolbox=True)
    enc = choose_encoder(profile)
    assert "videotoolbox" in enc.video_encoder or "videotoolbox" in (enc.hwaccel or "")


# ── Test 4: parallel_concat ──────────────────────────────────────────


@patch("modules.render_engine.render_manager.subprocess.run")
@patch("modules.render_engine.render_manager.suggest_max_concurrent", return_value=2)
def test_parallel_concat(mock_concurrent, mock_run, tmp_path):
    """4 segments rendered in parallel, then concatenated."""
    from modules.render_engine.render_manager import RenderManager

    output = str(tmp_path / "final.mp4")

    def _ffmpeg_ok(cmd, **kw):
        out = cmd[-1]
        if out.endswith(".mp4"):
            open(out, "w").close()
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        return m

    mock_run.side_effect = _ffmpeg_ok

    manager = RenderManager(_mock_profile())
    result = manager.render_timeline(_test_clips(4), output)

    # 4 render calls + 1 concat
    assert mock_run.call_count == 5
    # Verify concat was called with -f concat
    concat_call = mock_run.call_args_list[-1]
    assert "-f" in concat_call[0][0]
    assert "concat" in concat_call[0][0]


# ── Test 5: regression ───────────────────────────────────────────────


def test_regression_hardware_imports():
    """Existing hardware module imports still work."""
    from modules.hardware.detector import HardwareProfile, detect_cpu, detect_memory, detect_gpu
    from modules.hardware.encoding_strategy import choose_encoder, suggest_max_concurrent
    from modules.render_engine.render_manager import RenderManager, RenderError

    assert HardwareProfile is not None
    assert RenderManager is not None
    assert RenderError is not None
