"""Video type detector using Voice Activity Detection.

Classifies videos as speech/scenic/mixed based on the ratio of
voiced segments to total duration. Uses FFmpeg silencedetect for
fast, dependency-free detection.
"""

import json
import shutil
import subprocess
import re
from typing import Dict, Optional

from modules.render_engine.concat_utils import safe_ffmpeg_arg
from modules.review_engine.contracts import DetectionResult, VideoType
from modules.review_engine.exceptions import VideoDetectionError


# Thresholds for classification
SPEECH_THRESHOLD = 0.6   # speech_ratio > 0.6 → speech
SCENIC_THRESHOLD = 0.15  # speech_ratio < 0.15 → scenic

# FFmpeg defaults
FFMPEG_TIMEOUT_S = 60
SILENCE_THRESHOLD_DB = -30  # dB below which is "silence"
MIN_SILENCE_DURATION_S = 0.5  # minimum silence duration to detect


def _find_ffmpeg() -> str:
    """Find FFmpeg binary path."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    # macOS Homebrew fallback
    homebrew_path = "/opt/homebrew/bin/ffmpeg"
    import os
    if os.path.isfile(homebrew_path):
        return homebrew_path
    raise VideoDetectionError("FFmpeg not found. Install FFmpeg to use video detection.")


def _get_audio_duration(video_path: str, ffmpeg_bin: str) -> Optional[float]:
    """Get audio stream duration using ffprobe.

    Returns None if no audio stream exists.
    """
    ffprobe_bin = ffmpeg_bin.replace("ffmpeg", "ffprobe")
    cmd = [
        ffprobe_bin,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",
        safe_ffmpeg_arg(video_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise VideoDetectionError(f"ffprobe timed out after {FFMPEG_TIMEOUT_S}s: {video_path}")
    except FileNotFoundError:
        raise VideoDetectionError(f"ffprobe not found at {ffprobe_bin}")

    if result.returncode != 0:
        return None

    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    streams = probe.get("streams", [])
    if not streams:
        return None

    duration_str = streams[0].get("duration")
    if duration_str:
        return float(duration_str)

    # Fallback: get container duration
    return None


def _get_video_duration(video_path: str, ffmpeg_bin: str) -> float:
    """Get total video duration using ffprobe."""
    ffprobe_bin = ffmpeg_bin.replace("ffmpeg", "ffprobe")
    cmd = [
        ffprobe_bin,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        safe_ffmpeg_arg(video_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise VideoDetectionError(f"ffprobe timed out: {video_path}")
    except FileNotFoundError:
        raise VideoDetectionError(f"ffprobe not found")

    if result.returncode != 0:
        stderr = result.stderr[:500] if result.stderr else ""
        raise VideoDetectionError(f"ffprobe failed for {video_path}: {stderr}")

    try:
        probe = json.loads(result.stdout)
        return float(probe["format"]["duration"])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise VideoDetectionError(f"Cannot parse duration from {video_path}: {e}")


def _detect_silence_segments(
    video_path: str,
    ffmpeg_bin: str,
    noise_db: int = SILENCE_THRESHOLD_DB,
    min_duration: float = MIN_SILENCE_DURATION_S,
) -> list:
    """Run FFmpeg silencedetect, return list of (start, end, duration) tuples."""
    # Round-15.5: clamp noise_db/min_duration to numeric ranges so the
    # f-string interpolation into the -af filter cannot smuggle filter
    # graph fragments, and safe_ffmpeg_arg prevents leading-dash argv
    # injection on video_path.
    noise_db_i = int(noise_db)
    min_duration_f = max(0.01, float(min_duration))
    cmd = [
        ffmpeg_bin,
        "-i", safe_ffmpeg_arg(video_path),
        "-af", f"silencedetect=noise={noise_db_i}dB:d={min_duration_f:.3f}",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise VideoDetectionError(f"FFmpeg silencedetect timed out: {video_path}")

    # Parse silence segments from stderr
    stderr = result.stderr or ""
    silence_starts = re.findall(r"silence_start: ([\d.]+)", stderr)
    silence_ends = re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", stderr)

    segments = []
    for i, start in enumerate(silence_starts):
        start_f = float(start)
        if i < len(silence_ends):
            end_f = float(silence_ends[i][0])
            dur_f = float(silence_ends[i][1])
        else:
            # Last silence extends to end of file
            end_f = None
            dur_f = None
        segments.append((start_f, end_f, dur_f))

    return segments


def detect_video_type(
    video_path: str,
    config: Optional[Dict] = None,
) -> DetectionResult:
    """Detect video type (speech/scenic/mixed) using VAD.

    Uses FFmpeg silencedetect to estimate speech ratio without running
    full transcription. Fast (~1-2s for most videos).

    Args:
        video_path: Path to the video file.
        config: Optional overrides for thresholds/params.

    Returns:
        DetectionResult with video_type, speech_ratio, duration, etc.

    Raises:
        VideoDetectionError: If the file doesn't exist or analysis fails.
    """
    import os
    if not os.path.isfile(video_path):
        raise VideoDetectionError(f"Video file not found: {video_path}")

    cfg = config or {}
    speech_thresh = cfg.get("speech_threshold", SPEECH_THRESHOLD)
    scenic_thresh = cfg.get("scenic_threshold", SCENIC_THRESHOLD)

    ffmpeg_bin = _find_ffmpeg()

    # Get total duration
    total_duration = _get_video_duration(video_path, ffmpeg_bin)
    if total_duration <= 0:
        raise VideoDetectionError(f"Invalid video duration: {total_duration}s")

    # Check if audio exists
    audio_duration = _get_audio_duration(video_path, ffmpeg_bin)
    if audio_duration is None:
        # No audio stream → scenic
        return DetectionResult(
            video_type=VideoType.SCENIC,
            speech_ratio=0.0,
            duration_s=round(total_duration, 2),
            has_audio=False,
            method="ffmpeg_silencedetect",
        )

    # Run silence detection
    silence_segments = _detect_silence_segments(video_path, ffmpeg_bin)

    # Calculate total silence duration
    total_silence = 0.0
    for start, end, dur in silence_segments:
        if dur is not None:
            total_silence += dur
        elif end is not None:
            total_silence += (end - start)

    # Speech ratio = 1 - (silence / total)
    speech_ratio = max(0.0, min(1.0, 1.0 - (total_silence / total_duration)))

    # Classify
    if speech_ratio > speech_thresh:
        video_type = VideoType.SPEECH
    elif speech_ratio < scenic_thresh:
        video_type = VideoType.SCENIC
    else:
        video_type = VideoType.MIXED

    return DetectionResult(
        video_type=video_type,
        speech_ratio=round(speech_ratio, 3),
        duration_s=round(total_duration, 2),
        has_audio=True,
        method="ffmpeg_silencedetect",
    )
