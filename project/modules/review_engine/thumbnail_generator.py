"""Thumbnail sprite sheet generator for review timeline.

Extracts frames at regular intervals from a video file and composites
them into a single sprite sheet image. Returns metadata (frame count,
dimensions, interval) for the frontend ThumbnailStrip component.

Usage:
    from modules.review_engine.thumbnail_generator import generate_thumbnails
    result = generate_thumbnails("/path/to/video.mp4", "/output/dir/")
    # result = {"sprite_url": "...", "frame_width": 160, "frame_height": 90,
    #           "columns": 10, "frame_count": 50, "interval_ms": 2000}
"""

import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from modules.review_engine.exceptions import RenderError

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT_S = 120

# Sprite sheet defaults
DEFAULT_FRAME_WIDTH = 160
DEFAULT_FRAME_HEIGHT = 90
DEFAULT_COLUMNS = 10
DEFAULT_INTERVAL_S = 2.0
MAX_FRAMES = 200


def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    homebrew = "/opt/homebrew/bin/ffmpeg"
    if os.path.isfile(homebrew):
        return homebrew
    raise RenderError("FFmpeg not found")


def _find_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if path:
        return path
    homebrew = "/opt/homebrew/bin/ffprobe"
    if os.path.isfile(homebrew):
        return homebrew
    raise RenderError("ffprobe not found")


def _get_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    ffprobe = _find_ffprobe()
    cmd = [
        ffprobe, "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except (KeyError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        raise RenderError(f"Failed to get video duration: {e}")


def generate_thumbnails(
    video_path: str,
    output_dir: str,
    interval_s: float = DEFAULT_INTERVAL_S,
    frame_width: int = DEFAULT_FRAME_WIDTH,
    frame_height: int = DEFAULT_FRAME_HEIGHT,
    columns: int = DEFAULT_COLUMNS,
) -> dict:
    """Generate a thumbnail sprite sheet from a video file.

    Args:
        video_path: Path to source video.
        output_dir: Directory to write sprite sheet and metadata.
        interval_s: Seconds between frames.
        frame_width: Width of each thumbnail frame.
        frame_height: Height of each thumbnail frame.
        columns: Number of columns in the sprite grid.

    Returns:
        dict with sprite_url, frame_width, frame_height, columns,
        frame_count, interval_ms, duration_ms.

    Raises:
        RenderError: If FFmpeg fails.
    """
    if not os.path.isfile(video_path):
        raise RenderError(f"Video not found: {video_path}")
    os.makedirs(output_dir, exist_ok=True)

    duration = _get_duration(video_path)
    frame_count = min(MAX_FRAMES, max(1, int(math.ceil(duration / interval_s))))

    # Adjust interval if we hit MAX_FRAMES
    actual_interval = duration / frame_count if frame_count == MAX_FRAMES else interval_s

    ffmpeg = _find_ffmpeg()
    sprite_path = os.path.join(output_dir, "thumbnails.jpg")

    # Use FFmpeg to extract frames and tile them into a sprite sheet
    rows = math.ceil(frame_count / columns)
    tile = f"{columns}x{rows}"

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vf", (
            f"fps=1/{actual_interval},"
            f"scale={frame_width}:{frame_height}:force_original_aspect_ratio=decrease,"
            f"pad={frame_width}:{frame_height}:(ow-iw)/2:(oh-ih)/2,"
            f"tile={tile}"
        ),
        "-frames:v", "1",
        "-q:v", "5",
        sprite_path,
    ]

    logger.info("Generating thumbnail sprite: %d frames, %s tile", frame_count, tile)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S
        )
        if result.returncode != 0:
            raise RenderError(f"FFmpeg thumbnail failed: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        raise RenderError("Thumbnail generation timed out")

    if not os.path.isfile(sprite_path):
        raise RenderError("Sprite sheet not created")

    metadata = {
        "sprite_url": sprite_path,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "columns": columns,
        "rows": rows,
        "frame_count": frame_count,
        "interval_ms": int(actual_interval * 1000),
        "duration_ms": int(duration * 1000),
    }

    # Write metadata JSON alongside sprite
    meta_path = os.path.join(output_dir, "thumbnails.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Thumbnail sprite generated: %s (%d frames)", sprite_path, frame_count)
    return metadata
