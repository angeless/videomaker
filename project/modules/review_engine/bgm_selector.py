"""BGMSelector — beat analysis and segment sync using librosa.

Analyzes BGM beat positions and micro-adjusts segment cut points
to align with beats for smoother transitions.
"""

import json
import logging
import os
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple

from modules.render_engine.concat_utils import safe_ffmpeg_arg
from .contracts import Segment
from .exceptions import RenderError

logger = logging.getLogger(__name__)

try:
    import librosa
    import numpy as np
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False


def analyze_beats(bgm_path: str) -> List[float]:
    """Extract beat timestamps from audio file.

    Returns list of beat times in seconds.
    Falls back to empty list if librosa is unavailable.
    """
    if not os.path.isfile(bgm_path):
        raise RenderError(f"BGM file not found: {bgm_path}")

    if not HAS_LIBROSA:
        logger.warning("librosa not available, skipping beat analysis")
        return []

    try:
        y, sr = librosa.load(bgm_path, sr=22050, mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        return [round(float(t), 3) for t in beat_times]
    except Exception as e:
        logger.warning("librosa beat analysis failed: %s — returning empty beats", e)
        return []


def beat_sync_edits(
    edits: List[Segment],
    beats: List[float],
    max_shift_ms: int = 200,
) -> List[Segment]:
    """Micro-adjust segment cut points to align with beats.

    Shifts each segment boundary by at most ±max_shift_ms to the nearest beat.
    """
    if not beats:
        return edits

    beat_ms = [int(b * 1000) for b in beats]

    from copy import deepcopy
    adjusted = deepcopy(edits)

    for seg in adjusted:
        # Find nearest beat to segment end
        nearest = min(beat_ms, key=lambda b: abs(b - seg.end_ms))
        shift = nearest - seg.end_ms
        if abs(shift) <= max_shift_ms:
            seg.end_ms = nearest

    return adjusted


def mix_bgm(
    video_path: str,
    bgm_path: str,
    output_path: str,
    bgm_volume_db: float = -12.0,
    fade_in_s: float = 2.0,
    fade_out_s: float = 3.0,
) -> str:
    """Mix BGM into video with volume control and fade in/out.

    Returns output path.
    """
    if not os.path.isfile(video_path):
        raise RenderError(f"Video not found: {video_path}")
    if not os.path.isfile(bgm_path):
        raise RenderError(f"BGM not found: {bgm_path}")

    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not os.path.isfile(ffmpeg):
        raise RenderError("FFmpeg not found")

    # Get video duration for fade out timing
    duration = _get_duration(video_path, ffmpeg)

    fade_out_start = max(0, duration - fade_out_s)

    # BGM filter: volume + fade in + fade out
    bgm_filter = (
        f"[1:a]volume={bgm_volume_db}dB,"
        f"afade=t=in:st=0:d={fade_in_s},"
        f"afade=t=out:st={fade_out_start}:d={fade_out_s}[bgm];"
        f"[0:a][bgm]amix=inputs=2:normalize=0[out]"
    )

    # Round-15.5: safe_ffmpeg_arg shields against leading-dash argv injection.
    cmd = [
        ffmpeg, "-y",
        "-i", safe_ffmpeg_arg(video_path),
        "-i", safe_ffmpeg_arg(bgm_path),
        "-filter_complex", bgm_filter,
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy",
        "-ar", "44100",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        safe_ffmpeg_arg(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RenderError(f"BGM mix failed: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        raise RenderError("BGM mix timed out")

    return output_path


def _get_duration(path: str, ffmpeg: str) -> float:
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", safe_ffmpeg_arg(path)],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError, KeyError, ValueError, OSError) as e:
        logger.warning("Cannot probe duration for %s: %s", path, e)
        return 60.0  # fallback
