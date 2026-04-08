"""Tests for modules.hardware.detector — hardware detection."""

import platform
from unittest.mock import patch, MagicMock
import pytest

from modules.hardware.detector import (
    CPUInfo, MemoryInfo, GPUInfo, HardwareProfile,
    detect_cpu, detect_memory, detect_gpu,
    detect_ffmpeg_hwaccels, detect_decoders, has_hevc_hardware_decode,
    get_system_profile,
)
from modules.hardware.encoding_strategy import choose_decoder, DecodingParams


class TestDetectCPU:
    def test_returns_cpuinfo(self):
        info = detect_cpu()
        assert isinstance(info, CPUInfo)
        assert info.physical_cores >= 1
        assert info.logical_cores >= 1
        assert info.architecture  # non-empty
        assert info.model  # non-empty

    def test_logical_gte_physical(self):
        info = detect_cpu()
        assert info.logical_cores >= info.physical_cores


class TestDetectMemory:
    def test_returns_memoryinfo(self):
        info = detect_memory()
        assert isinstance(info, MemoryInfo)
        assert info.total_gb > 0
        assert info.available_gb > 0

    def test_available_lte_total(self):
        info = detect_memory()
        assert info.available_gb <= info.total_gb + 1  # small margin


class TestDetectGPU:
    def test_returns_gpuinfo(self):
        info = detect_gpu()
        assert isinstance(info, GPUInfo)
        assert info.vendor  # non-empty

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_macos_has_videotoolbox(self):
        info = detect_gpu()
        assert info.has_videotoolbox is True


class TestDetectFFmpegHwaccels:
    def test_returns_list(self):
        accels = detect_ffmpeg_hwaccels()
        assert isinstance(accels, list)

    def test_fallback_on_missing_ffmpeg(self):
        accels = detect_ffmpeg_hwaccels("/nonexistent/ffmpeg")
        assert accels == []

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_macos_includes_videotoolbox(self):
        accels = detect_ffmpeg_hwaccels()
        assert "videotoolbox" in accels


class TestGetSystemProfile:
    def test_returns_hardware_profile(self):
        profile = get_system_profile()
        assert isinstance(profile, HardwareProfile)
        assert isinstance(profile.cpu, CPUInfo)
        assert isinstance(profile.memory, MemoryInfo)
        assert isinstance(profile.gpu, GPUInfo)
        assert profile.ffmpeg_path  # non-empty
        assert isinstance(profile.ffmpeg_hwaccels, list)
        assert isinstance(profile.ffmpeg_decoders, list)
        assert isinstance(profile.has_hevc_hw_decode, bool)


# ── D1: Decoder detection tests ──────────────────────────────────


class TestDetectDecoders:
    def test_decoders_detected(self):
        decoders = detect_decoders()
        assert isinstance(decoders, list)
        # FFmpeg may return empty list when ffmpeg is missing or stripped (e.g. CI runners).
        # We only assert the function returns a list — content depends on environment.

    def test_hevc_hw_detection(self):
        # Test with known hardware decoder list
        assert has_hevc_hardware_decode(["h264", "hevc_videotoolbox", "aac"]) is True
        assert has_hevc_hardware_decode(["h264", "hevc", "aac"]) is False

    def test_fallback_empty(self):
        """Simulated failure returns empty list."""
        with patch("modules.hardware.detector.subprocess.check_output", side_effect=OSError):
            result = detect_decoders("/nonexistent/ffmpeg")
        assert result == []

    def test_backward_compat(self):
        """Old code using HardwareProfile without new fields should still work."""
        profile = get_system_profile()
        # Old fields still present
        assert hasattr(profile, "cpu")
        assert hasattr(profile, "ffmpeg_hwaccels")
        # New fields also present
        assert hasattr(profile, "ffmpeg_decoders")
        assert hasattr(profile, "has_hevc_hw_decode")


class TestChooseDecoder:
    def _profile(self, decoders, hwaccels):
        return HardwareProfile(
            cpu=CPUInfo(8, 8, "arm64", "Apple M1"),
            memory=MemoryInfo(16.0, 8.0),
            gpu=GPUInfo("apple", "M1", has_videotoolbox=True),
            ffmpeg_path="/opt/homebrew/bin/ffmpeg",
            ffmpeg_hwaccels=hwaccels,
            ffmpeg_decoders=decoders,
            has_hevc_hw_decode=has_hevc_hardware_decode(decoders),
        )

    def test_hevc_videotoolbox(self):
        p = self._profile(["hevc_videotoolbox", "h264"], ["videotoolbox"])
        d = choose_decoder(p, "hevc")
        assert d.hwaccel == "videotoolbox"
        assert d.decoder == "hevc_videotoolbox"

    def test_cpu_fallback(self):
        p = self._profile(["h264", "hevc"], [])
        d = choose_decoder(p, "hevc")
        assert d.hwaccel is None
        assert d.decoder is None
        assert "CPU" in d.label
