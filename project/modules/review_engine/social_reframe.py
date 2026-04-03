"""SocialReframe — crop video to different social media aspect ratios.

Supports 7 platform presets with intelligent center crop.
"""

import logging
import os
import shutil
import subprocess
from typing import Dict, Optional

from .exceptions import RenderError

logger = logging.getLogger(__name__)

# Platform aspect ratios: (width, height, max_duration_s)
PLATFORMS: Dict[str, Dict] = {
    "tiktok":      {"ratio": (9, 16),  "max_duration": None},
    "instagram":   {"ratio": (9, 16),  "max_duration": 90},
    "youtube":     {"ratio": (16, 9),  "max_duration": None},
    "shorts":      {"ratio": (9, 16),  "max_duration": 60},
    "wechat":      {"ratio": (9, 16),  "max_duration": 60},
    "xiaohongshu": {"ratio": (3, 4),   "max_duration": None},
    "square":      {"ratio": (1, 1),   "max_duration": None},
}


def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if os.path.isfile(path):
        return path
    raise RenderError("FFmpeg not found")


def _get_video_info(ffmpeg: str, path: str) -> Dict:
    """Get video width, height, duration."""
    import json
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            {},
        )
        return {
            "width": int(video_stream.get("width", 1920)),
            "height": int(video_stream.get("height", 1080)),
            "duration": float(data.get("format", {}).get("duration", 0)),
        }
    except Exception:
        return {"width": 1920, "height": 1080, "duration": 0}


def reframe(
    video_path: str,
    output_path: str,
    platform: str = "tiktok",
) -> str:
    """Crop video to the target platform's aspect ratio.

    Uses center crop when no face detection is available.

    Returns:
        Output file path
    """
    if platform not in PLATFORMS:
        raise RenderError(f"Unknown platform: {platform}. Supported: {list(PLATFORMS.keys())}")

    if not os.path.isfile(video_path):
        raise RenderError(f"Video not found: {video_path}")

    ffmpeg = _find_ffmpeg()
    info = _get_video_info(ffmpeg, video_path)
    src_w, src_h = info["width"], info["height"]
    duration = info["duration"]

    plat = PLATFORMS[platform]
    target_w_ratio, target_h_ratio = plat["ratio"]
    max_dur = plat["max_duration"]

    # Calculate crop dimensions (center crop)
    target_aspect = target_w_ratio / target_h_ratio
    src_aspect = src_w / src_h

    if src_aspect > target_aspect:
        # Source is wider, crop horizontally
        crop_h = src_h
        crop_w = int(src_h * target_aspect)
    else:
        # Source is taller, crop vertically
        crop_w = src_w
        crop_h = int(src_w / target_aspect)

    # Ensure even dimensions
    crop_w = crop_w - (crop_w % 2)
    crop_h = crop_h - (crop_h % 2)

    x_offset = (src_w - crop_w) // 2
    y_offset = (src_h - crop_h) // 2

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vf", f"crop={crop_w}:{crop_h}:{x_offset}:{y_offset}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
    ]

    if max_dur and duration > max_dur:
        cmd.extend(["-t", str(max_dur)])

    cmd.append(output_path)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RenderError(f"Reframe failed: {result.stderr[-300:]}")

    return output_path
