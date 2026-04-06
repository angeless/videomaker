"""Unit tests for render_pipeline hardware acceleration (D2)."""

from unittest.mock import patch, MagicMock

import pytest

from modules.review_engine.render_pipeline import (
    _build_video_encode_args,
    _build_decode_args,
)
from modules.hardware.detector import (
    CPUInfo, MemoryInfo, GPUInfo, HardwareProfile,
)


def _profile(has_vt=True, decoders=None, hwaccels=None):
    return HardwareProfile(
        cpu=CPUInfo(8, 8, "arm64", "Apple M1"),
        memory=MemoryInfo(16.0, 8.0),
        gpu=GPUInfo("apple", "M1", has_videotoolbox=has_vt),
        ffmpeg_path="/opt/homebrew/bin/ffmpeg",
        ffmpeg_hwaccels=hwaccels or (["videotoolbox"] if has_vt else []),
        ffmpeg_decoders=decoders or [],
        has_hevc_hw_decode=bool(decoders and "hevc_videotoolbox" in decoders),
    )


def test_pipeline_cmd_has_hwaccel():
    """With VideoToolbox available, encoder should be h264_videotoolbox."""
    profile = _profile(has_vt=True)
    args = _build_video_encode_args(profile)
    assert "h264_videotoolbox" in args
    assert "-crf" not in args  # hw encoder uses bitrate, not CRF
    assert "-b:v" in args


def test_hevc_input_decode():
    """HEVC input with hw decoder available should add -hwaccel."""
    profile = _profile(decoders=["hevc_videotoolbox", "h264"], hwaccels=["videotoolbox"])
    with patch("modules.review_engine.render_pipeline._probe_video_codec", return_value="hevc"):
        args = _build_decode_args("/fake/hevc.mov", profile)
    assert "-hwaccel" in args
    assert "videotoolbox" in args


def test_crf_to_bitrate():
    """Hardware encoder should use -b:v instead of -crf."""
    profile = _profile(has_vt=True)
    args = _build_video_encode_args(profile)
    assert "-b:v" in args
    assert "-crf" not in args


def test_cpu_fallback():
    """Without GPU, should fall back to libx264 + CRF."""
    profile = _profile(has_vt=False, hwaccels=[])
    args = _build_video_encode_args(profile)
    assert "libx264" in args
    assert "-crf" in args


def test_encoder_label():
    """None profile should give CPU fallback."""
    args = _build_video_encode_args(None)
    assert "libx264" in args
