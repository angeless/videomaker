"""Adaptive encoding strategy based on hardware profile.

Selects the best FFmpeg encoder and concurrency settings for the detected
hardware, with CPU-only fallback as the universal safety net.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from .detector import HardwareProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EncodingParams:
    """FFmpeg encoding parameters chosen for the current hardware."""
    video_encoder: str       # e.g. "h264_videotoolbox", "h264_nvenc", "libx264"
    hwaccel: Optional[str]   # e.g. "videotoolbox", None for CPU
    extra_args: List[str]    # additional ffmpeg flags
    label: str               # human-readable description


def choose_encoder(profile: HardwareProfile) -> EncodingParams:
    """Pick the best available encoder based on hardware profile.

    Priority:
    1. VideoToolbox (macOS) — near-zero CPU cost on Apple Silicon
    2. NVENC (NVIDIA GPU) — high throughput, low CPU
    3. libx264 CPU — universal fallback, quality tuned by core count
    """
    gpu = profile.gpu
    hwaccels = profile.ffmpeg_hwaccels

    # macOS VideoToolbox
    if gpu.has_videotoolbox and "videotoolbox" in hwaccels:
        return EncodingParams(
            video_encoder="h264_videotoolbox",
            hwaccel="videotoolbox",
            extra_args=["-allow_sw", "1"],  # fallback to sw if hw busy
            label="Apple VideoToolbox (hardware)",
        )

    # NVIDIA NVENC
    if gpu.has_nvenc and "cuda" in hwaccels:
        return EncodingParams(
            video_encoder="h264_nvenc",
            hwaccel="cuda",
            extra_args=["-preset", "p4", "-tune", "hq"],
            label="NVIDIA NVENC (hardware)",
        )

    # VAAPI (Linux Intel/AMD)
    if gpu.has_vaapi and "vaapi" in hwaccels:
        return EncodingParams(
            video_encoder="h264_vaapi",
            hwaccel="vaapi",
            extra_args=["-vaapi_device", "/dev/dri/renderD128"],
            label="VAAPI (hardware)",
        )

    # CPU fallback — tune preset based on core count
    preset = _cpu_preset(profile.cpu.physical_cores)
    return EncodingParams(
        video_encoder="libx264",
        hwaccel=None,
        extra_args=["-preset", preset],
        label=f"libx264 CPU (preset={preset})",
    )


def _cpu_preset(physical_cores: int) -> str:
    """Choose x264 preset: more cores → slower preset (better quality)."""
    if physical_cores >= 8:
        return "slow"
    elif physical_cores >= 4:
        return "medium"
    else:
        return "fast"


def suggest_max_concurrent(profile: HardwareProfile) -> int:
    """Suggest max concurrent render jobs based on system resources.

    Heuristic: each render job needs ~2 GB RAM and benefits from ≥2 cores.
    Hardware-accelerated encoding is lighter on CPU, so we allow more.
    """
    ram_limit = max(1, int(profile.memory.total_gb / 2.5))
    core_limit = max(1, profile.cpu.physical_cores // 2)

    encoder = choose_encoder(profile)
    is_hw = encoder.hwaccel is not None

    # Hardware encoding uses minimal CPU → allow more parallelism
    if is_hw:
        base = min(ram_limit, core_limit * 2)
    else:
        base = min(ram_limit, core_limit)

    return max(1, min(base, 4))  # clamp 1-4
