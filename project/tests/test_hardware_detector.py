"""Tests for modules.hardware.detector — hardware detection."""

import platform
from unittest.mock import patch, MagicMock
import pytest

from modules.hardware.detector import (
    CPUInfo, MemoryInfo, GPUInfo, HardwareProfile,
    detect_cpu, detect_memory, detect_gpu,
    detect_ffmpeg_hwaccels, get_system_profile,
)


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
