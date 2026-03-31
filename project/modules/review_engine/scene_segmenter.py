"""Scene segmentation using FFmpeg scene detection.

Splits a video into individual scenes based on visual content changes.
Uses FFmpeg's `select` filter with scene detection threshold.
"""

import json
import logging
import os
import re
import shutil
import subprocess
from typing import Dict, List, Optional

from modules.review_engine.contracts import SceneInfo
from modules.review_engine.exceptions import ReviewEngineError

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT_S = 120
DEFAULT_SCENE_THRESHOLD = 0.3  # 0.0-1.0, lower = more sensitive


def _find_ffmpeg() -> str:
    """Find FFmpeg binary."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    homebrew = "/opt/homebrew/bin/ffmpeg"
    if os.path.isfile(homebrew):
        return homebrew
    raise ReviewEngineError("FFmpeg not found")


def _get_video_info(video_path: str, ffmpeg_bin: str) -> Dict:
    """Get video duration and fps using ffprobe."""
    ffprobe = ffmpeg_bin.replace("ffmpeg", "ffprobe")
    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", "-select_streams", "v:0",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise ReviewEngineError(f"ffprobe timed out: {video_path}")

    if result.returncode != 0:
        raise ReviewEngineError(f"ffprobe failed: {video_path}")

    probe = json.loads(result.stdout)
    duration = float(probe.get("format", {}).get("duration", 0))

    # Get fps
    streams = probe.get("streams", [])
    fps = 30.0
    if streams:
        r_frame_rate = streams[0].get("r_frame_rate", "30/1")
        parts = r_frame_rate.split("/")
        if len(parts) == 2 and int(parts[1]) > 0:
            fps = int(parts[0]) / int(parts[1])

    return {"duration": duration, "fps": fps}


def detect_scene_changes(
    video_path: str,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
) -> List[float]:
    """Detect scene change timestamps using FFmpeg.

    Args:
        video_path: Path to video file.
        threshold: Scene detection sensitivity (0.0-1.0).

    Returns:
        List of scene change timestamps in seconds.
    """
    ffmpeg_bin = _find_ffmpeg()

    cmd = [
        ffmpeg_bin, "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise ReviewEngineError(f"Scene detection timed out: {video_path}")

    # Parse timestamps from showinfo output
    stderr = result.stderr or ""
    timestamps = [0.0]  # Always start at 0

    for match in re.finditer(r"pts_time:([\d.]+)", stderr):
        ts = float(match.group(1))
        timestamps.append(ts)

    return sorted(set(timestamps))


def segment_scenes(
    video_path: str,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
    min_scene_duration_s: float = 0.5,
    thumbnail_dir: Optional[str] = None,
) -> List[SceneInfo]:
    """Segment video into scenes.

    Args:
        video_path: Path to video file.
        threshold: Scene detection sensitivity.
        min_scene_duration_s: Minimum scene duration (filter short flashes).
        thumbnail_dir: If provided, extract thumbnail for each scene.

    Returns:
        List of SceneInfo objects.

    Raises:
        ReviewEngineError: If video file not found or FFmpeg fails.
    """
    if not os.path.isfile(video_path):
        raise ReviewEngineError(f"Video file not found: {video_path}")

    ffmpeg_bin = _find_ffmpeg()
    info = _get_video_info(video_path, ffmpeg_bin)
    total_duration = info["duration"]

    if total_duration <= 0:
        raise ReviewEngineError(f"Invalid video duration: {total_duration}")

    # Detect scene changes
    change_points = detect_scene_changes(video_path, threshold)

    # Add end point
    if not change_points or change_points[-1] < total_duration - 0.1:
        change_points.append(total_duration)

    # Build scene list
    scenes = []
    scene_idx = 0

    for i in range(len(change_points) - 1):
        start = change_points[i]
        end = change_points[i + 1]
        duration = end - start

        # Filter too-short scenes
        if duration < min_scene_duration_s:
            continue

        scene = SceneInfo(
            scene_idx=scene_idx,
            start_ms=int(start * 1000),
            end_ms=int(end * 1000),
            duration_ms=int(duration * 1000),
        )

        # Extract thumbnail if requested
        if thumbnail_dir:
            os.makedirs(thumbnail_dir, exist_ok=True)
            thumb_path = os.path.join(thumbnail_dir, f"scene_{scene_idx:04d}.jpg")
            mid_time = start + duration / 2
            if _extract_thumbnail(video_path, mid_time, thumb_path, ffmpeg_bin):
                scene.thumbnail_path = thumb_path

        scenes.append(scene)
        scene_idx += 1

    logger.info("Segmented into %d scenes (threshold=%.2f)", len(scenes), threshold)
    return scenes


def _extract_thumbnail(
    video_path: str, timestamp: float, output_path: str, ffmpeg_bin: str,
) -> bool:
    """Extract a single frame as thumbnail."""
    cmd = [
        ffmpeg_bin, "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-vf", "scale=320:-1",
        output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        logger.warning("Thumbnail extraction failed at %.2fs: %s", timestamp, e)
        return False
