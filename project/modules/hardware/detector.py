"""Hardware detection — CPU, memory, GPU, and FFmpeg acceleration probes.

All detection functions are best-effort: failures return safe defaults
so the rest of the application can continue with CPU-only fallback.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class CPUInfo:
    physical_cores: int
    logical_cores: int
    architecture: str  # e.g. "arm64", "x86_64"
    model: str  # human-readable brand string


@dataclass(frozen=True)
class MemoryInfo:
    total_gb: float
    available_gb: float


@dataclass(frozen=True)
class GPUInfo:
    vendor: str  # "apple", "nvidia", "amd", "intel", "unknown"
    model: str
    has_videotoolbox: bool = False
    has_nvenc: bool = False
    has_vaapi: bool = False


@dataclass(frozen=True)
class HardwareProfile:
    cpu: CPUInfo
    memory: MemoryInfo
    gpu: GPUInfo
    ffmpeg_path: str
    ffmpeg_hwaccels: List[str] = field(default_factory=list)


# ── CPU detection ─────────────────────────────────────────────────────

def detect_cpu() -> CPUInfo:
    logical = os.cpu_count() or 1
    arch = platform.machine() or "unknown"
    model = _cpu_model_string()
    physical = _physical_core_count(logical)
    return CPUInfo(
        physical_cores=physical,
        logical_cores=logical,
        architecture=arch,
        model=model,
    )


def _cpu_model_string() -> str:
    system = platform.system()
    try:
        if system == "Darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                text=True, timeout=5,
            ).strip()
            if out:
                return out
        elif system == "Linux":
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "unknown"


def _physical_core_count(logical_fallback: int) -> int:
    system = platform.system()
    try:
        if system == "Darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.physicalcpu"],
                text=True, timeout=5,
            ).strip()
            return int(out)
        elif system == "Linux":
            out = subprocess.check_output(
                ["nproc", "--all"],
                text=True, timeout=5,
            ).strip()
            return int(out)
    except Exception:
        pass
    return max(1, logical_fallback // 2)


# ── Memory detection ──────────────────────────────────────────────────

def detect_memory() -> MemoryInfo:
    system = platform.system()
    total = 0.0
    available = 0.0
    try:
        if system == "Darwin":
            total = _macos_total_memory()
            available = _macos_available_memory(total)
        elif system == "Linux":
            total, available = _linux_memory()
        else:
            total = 8.0  # safe default
            available = 4.0
    except Exception:
        logger.debug("memory detection failed", exc_info=True)
        total = total or 8.0
        available = available or 4.0
    return MemoryInfo(total_gb=round(total, 1), available_gb=round(available, 1))


def _macos_total_memory() -> float:
    out = subprocess.check_output(
        ["sysctl", "-n", "hw.memsize"], text=True, timeout=5,
    ).strip()
    return int(out) / (1024 ** 3)


def _macos_available_memory(total_gb: float) -> float:
    """Parse vm_stat for free + inactive pages."""
    try:
        out = subprocess.check_output(["vm_stat"], text=True, timeout=5)
        page_size = 16384  # Apple Silicon default
        m = re.search(r"page size of (\d+) bytes", out)
        if m:
            page_size = int(m.group(1))
        free = _vm_stat_pages(out, "Pages free")
        inactive = _vm_stat_pages(out, "Pages inactive")
        return (free + inactive) * page_size / (1024 ** 3)
    except Exception:
        return total_gb * 0.5  # estimate


def _vm_stat_pages(text: str, label: str) -> int:
    m = re.search(rf"{label}:\s+(\d+)", text)
    return int(m.group(1)) if m else 0


def _linux_memory() -> tuple:
    with open("/proc/meminfo", encoding="utf-8") as f:
        info = {}
        for line in f:
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                info[key] = int(val)
    total = info.get("MemTotal", 0) / (1024 ** 2)
    available = info.get("MemAvailable", info.get("MemFree", 0)) / (1024 ** 2)
    return total, available


# ── GPU detection ─────────────────────────────────────────────────────

def detect_gpu() -> GPUInfo:
    system = platform.system()
    try:
        if system == "Darwin":
            return _macos_gpu()
        elif system == "Linux":
            return _linux_gpu()
    except Exception:
        logger.debug("GPU detection failed", exc_info=True)
    return GPUInfo(vendor="unknown", model="unknown")


def _macos_gpu() -> GPUInfo:
    """On macOS, Apple Silicon has built-in VideoToolbox support."""
    arch = platform.machine()
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPDisplaysDataType", "-detailLevel", "mini"],
            text=True, timeout=10,
        )
        model = "unknown"
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("Chipset Model:") or stripped.startswith("Chip:"):
                model = stripped.split(":", 1)[1].strip()
                break
    except Exception:
        model = "Apple Silicon" if arch == "arm64" else "unknown"

    is_apple = arch == "arm64" or "apple" in model.lower()
    return GPUInfo(
        vendor="apple" if is_apple else "unknown",
        model=model,
        has_videotoolbox=True,  # all modern macOS have VideoToolbox
    )


def _linux_gpu() -> GPUInfo:
    vendor = "unknown"
    model = "unknown"
    has_nvenc = False
    has_vaapi = False

    # Try nvidia-smi
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=5,
        ).strip()
        if out:
            vendor = "nvidia"
            model = out.splitlines()[0].strip()
            has_nvenc = True
    except Exception:
        pass

    # Try vainfo for VAAPI
    if vendor == "unknown":
        try:
            subprocess.check_output(["vainfo"], text=True, timeout=5)
            has_vaapi = True
            vendor = "intel"  # most common VAAPI
        except Exception:
            pass

    return GPUInfo(
        vendor=vendor, model=model,
        has_nvenc=has_nvenc, has_vaapi=has_vaapi,
    )


# ── FFmpeg hardware acceleration detection ────────────────────────────

def _find_ffmpeg() -> str:
    """Locate ffmpeg binary."""
    for candidate in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("ffmpeg") or "ffmpeg"


def detect_ffmpeg_hwaccels(ffmpeg_path: Optional[str] = None) -> List[str]:
    """Return list of available FFmpeg hardware acceleration methods."""
    path = ffmpeg_path or _find_ffmpeg()
    try:
        out = subprocess.check_output(
            [path, "-hwaccels"], text=True, timeout=10,
            stderr=subprocess.DEVNULL,
        )
        accels = []
        parsing = False
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Hardware acceleration methods"):
                parsing = True
                continue
            if parsing and line:
                accels.append(line)
        return accels
    except Exception:
        logger.debug("ffmpeg -hwaccels failed", exc_info=True)
        return []


# ── Composite profile ────────────────────────────────────────────────

def get_system_profile() -> HardwareProfile:
    """Build a complete hardware profile for the current system."""
    ffmpeg = _find_ffmpeg()
    return HardwareProfile(
        cpu=detect_cpu(),
        memory=detect_memory(),
        gpu=detect_gpu(),
        ffmpeg_path=ffmpeg,
        ffmpeg_hwaccels=detect_ffmpeg_hwaccels(ffmpeg),
    )
