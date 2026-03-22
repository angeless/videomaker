"""Tests for modules.hardware.encoding_strategy — adaptive encoding."""

import pytest

from modules.hardware.detector import CPUInfo, MemoryInfo, GPUInfo, HardwareProfile
from modules.hardware.encoding_strategy import (
    EncodingParams, choose_encoder, suggest_max_concurrent, _cpu_preset,
)


def _make_profile(
    *,
    cores=8, ram=16.0, gpu_vendor="unknown",
    has_vt=False, has_nvenc=False, has_vaapi=False,
    hwaccels=None,
):
    return HardwareProfile(
        cpu=CPUInfo(physical_cores=cores, logical_cores=cores * 2,
                    architecture="arm64", model="Test CPU"),
        memory=MemoryInfo(total_gb=ram, available_gb=ram * 0.5),
        gpu=GPUInfo(vendor=gpu_vendor, model="Test GPU",
                    has_videotoolbox=has_vt, has_nvenc=has_nvenc,
                    has_vaapi=has_vaapi),
        ffmpeg_path="/usr/bin/ffmpeg",
        ffmpeg_hwaccels=hwaccels or [],
    )


class TestChooseEncoder:
    def test_videotoolbox_on_macos(self):
        profile = _make_profile(gpu_vendor="apple", has_vt=True,
                                hwaccels=["videotoolbox"])
        enc = choose_encoder(profile)
        assert enc.video_encoder == "h264_videotoolbox"
        assert enc.hwaccel == "videotoolbox"

    def test_nvenc_on_nvidia(self):
        profile = _make_profile(gpu_vendor="nvidia", has_nvenc=True,
                                hwaccels=["cuda"])
        enc = choose_encoder(profile)
        assert enc.video_encoder == "h264_nvenc"
        assert enc.hwaccel == "cuda"

    def test_vaapi_on_linux(self):
        profile = _make_profile(gpu_vendor="intel", has_vaapi=True,
                                hwaccels=["vaapi"])
        enc = choose_encoder(profile)
        assert enc.video_encoder == "h264_vaapi"
        assert enc.hwaccel == "vaapi"

    def test_cpu_fallback(self):
        profile = _make_profile()
        enc = choose_encoder(profile)
        assert enc.video_encoder == "libx264"
        assert enc.hwaccel is None

    def test_videotoolbox_priority_over_nvenc(self):
        """VideoToolbox should win if both are available."""
        profile = _make_profile(has_vt=True, has_nvenc=True,
                                hwaccels=["videotoolbox", "cuda"])
        enc = choose_encoder(profile)
        assert enc.video_encoder == "h264_videotoolbox"


class TestCPUPreset:
    def test_many_cores_slow(self):
        assert _cpu_preset(8) == "slow"
        assert _cpu_preset(16) == "slow"

    def test_medium_cores(self):
        assert _cpu_preset(4) == "medium"
        assert _cpu_preset(6) == "medium"

    def test_few_cores_fast(self):
        assert _cpu_preset(2) == "fast"
        assert _cpu_preset(1) == "fast"


class TestSuggestMaxConcurrent:
    def test_returns_int_in_range(self):
        profile = _make_profile()
        result = suggest_max_concurrent(profile)
        assert isinstance(result, int)
        assert 1 <= result <= 4

    def test_low_ram_limits_concurrency(self):
        profile = _make_profile(cores=16, ram=4.0)
        result = suggest_max_concurrent(profile)
        assert result <= 2  # 4 GB / 2.5 ≈ 1

    def test_hw_encoding_allows_more(self):
        cpu_only = _make_profile(cores=8, ram=16.0)
        hw_accel = _make_profile(cores=8, ram=16.0, has_vt=True,
                                 hwaccels=["videotoolbox"])
        assert suggest_max_concurrent(hw_accel) >= suggest_max_concurrent(cpu_only)

    def test_single_core_minimum(self):
        profile = _make_profile(cores=1, ram=2.0)
        assert suggest_max_concurrent(profile) >= 1
