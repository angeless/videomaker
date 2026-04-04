"""Scene detection via FFmpeg — R14 of dev-plan-v0.14.0.

Splits a video into scenes using FFmpeg's scene change detection filter,
then extracts a thumbnail from the middle frame of each scene.
"""

import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

from modules.review_engine.exceptions import VideoDetectionError

logger = logging.getLogger(__name__)

# FFmpeg scene detection threshold (0.0–1.0); lower = more sensitive
DEFAULT_SCENE_THRESHOLD = 0.3


def detect_scenes(
    video_path: str,
    output_dir: Optional[str] = None,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
    extract_thumbnails: bool = True,
) -> Dict[str, Any]:
    """Detect scene changes in a video file.

    Args:
        video_path: Path to the input video.
        output_dir: Directory for thumbnail output. Created if needed.
        threshold: Scene change sensitivity (0.0–1.0).
        extract_thumbnails: Whether to extract mid-frame thumbnails.

    Returns:
        {scenes: [{scene_id, start_s, end_s, duration_s, thumbnail_path}], total_scenes}
    """
    if not os.path.isfile(video_path):
        raise VideoDetectionError(f"Video file not found: {video_path}")

    # Get video duration first
    duration = _get_duration(video_path)
    if duration <= 0:
        raise VideoDetectionError(f"Cannot determine video duration: {video_path}")

    # Detect scene change timestamps
    timestamps = _detect_scene_timestamps(video_path, threshold)

    # Build scene list from timestamps
    scenes = _build_scenes(timestamps, duration)

    # Extract thumbnails
    if extract_thumbnails and output_dir:
        os.makedirs(output_dir, exist_ok=True)
        for scene in scenes:
            mid_s = (scene["start_s"] + scene["end_s"]) / 2
            thumb_path = os.path.join(output_dir, f"scene_{scene['scene_id']:03d}.jpg")
            try:
                _extract_frame(video_path, mid_s, thumb_path)
                scene["thumbnail_path"] = thumb_path
            except VideoDetectionError:
                scene["thumbnail_path"] = None
                logger.warning("Failed to extract thumbnail for scene %d", scene["scene_id"])

    return {"scenes": scenes, "total_scenes": len(scenes)}


def _get_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise VideoDetectionError(f"ffprobe failed: {result.stderr[:200]}")
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except (subprocess.TimeoutExpired, KeyError, ValueError, json.JSONDecodeError) as e:
        raise VideoDetectionError(f"Cannot get duration: {e}") from e
    except FileNotFoundError:
        raise VideoDetectionError("ffprobe not found — is FFmpeg installed?")


def _detect_scene_timestamps(video_path: str, threshold: float) -> List[float]:
    """Run FFmpeg scene detection filter, return list of scene change timestamps."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise VideoDetectionError("Scene detection timed out")
    except FileNotFoundError:
        raise VideoDetectionError("ffmpeg not found — is FFmpeg installed?")

    # Parse showinfo output for pts_time values
    timestamps = []
    for line in result.stderr.split("\n"):
        if "showinfo" in line and "pts_time:" in line:
            try:
                pts_part = line.split("pts_time:")[1]
                pts_time = float(pts_part.strip().split()[0])
                timestamps.append(pts_time)
            except (IndexError, ValueError):
                continue

    timestamps.sort()
    return timestamps


def _build_scenes(
    timestamps: List[float], duration: float,
) -> List[Dict[str, Any]]:
    """Build scene list from detected timestamps."""
    boundaries = [0.0] + timestamps + [duration]
    scenes = []

    for i in range(len(boundaries) - 1):
        start = round(boundaries[i], 3)
        end = round(boundaries[i + 1], 3)
        dur = round(end - start, 3)
        if dur < 0.1:
            continue  # skip tiny fragments
        scenes.append({
            "scene_id": len(scenes),
            "start_s": start,
            "end_s": end,
            "duration_s": dur,
            "thumbnail_path": None,
        })

    # If no scenes detected, treat entire video as one scene
    if not scenes:
        scenes.append({
            "scene_id": 0,
            "start_s": 0.0,
            "end_s": round(duration, 3),
            "duration_s": round(duration, 3),
            "thumbnail_path": None,
        })

    return scenes


def _extract_frame(video_path: str, timestamp_s: float, output_path: str):
    """Extract a single frame at the given timestamp."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp_s),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "3",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise VideoDetectionError(f"Frame extraction failed: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        raise VideoDetectionError("Frame extraction timed out")
    except FileNotFoundError:
        raise VideoDetectionError("ffmpeg not found")
