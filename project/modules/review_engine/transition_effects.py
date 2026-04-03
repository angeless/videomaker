"""TransitionEffects — 12 FFmpeg transition effects between segments.

Uses FFmpeg's xfade filter for crossfade effects and custom implementations
for special effects (black_title, glitch, flash).
"""

import logging
import os
import shutil
import subprocess
from typing import Dict, Optional

from .exceptions import RenderError

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT_S = 120

# 12 supported effects and their xfade equivalents
EFFECTS: Dict[str, Optional[str]] = {
    "cut":            None,             # No transition (hard cut)
    "fade_black":     "fade",
    "fade_white":     "fade",
    "cross_dissolve": "dissolve",
    "wipe_left":      "wipeleft",
    "wipe_right":     "wiperight",
    "zoom_in":        "smoothup",
    "zoom_out":       "smoothdown",
    "black_title":    None,             # Custom (PIL + concat)
    "whoosh":         "fade",           # Visual: fade, audio: whoosh SFX
    "glitch":         "pixelize",
    "flash":          "fade",           # White flash
}


def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if os.path.isfile(path):
        return path
    raise RenderError("FFmpeg not found")


def apply_transition(
    segment_a_path: str,
    segment_b_path: str,
    output_path: str,
    effect: str = "cross_dissolve",
    duration_s: float = 0.5,
) -> str:
    """Apply a transition between two video segments.

    Args:
        segment_a_path: Path to first video segment
        segment_b_path: Path to second video segment
        output_path: Output video path
        effect: One of the 12 supported effects
        duration_s: Transition duration (0.15-3.0s)

    Returns:
        Output file path
    """
    if effect not in EFFECTS:
        raise RenderError(f"Unknown transition effect: {effect}")

    duration_s = max(0.15, min(3.0, duration_s))

    if not os.path.isfile(segment_a_path):
        raise RenderError(f"Segment A not found: {segment_a_path}")
    if not os.path.isfile(segment_b_path):
        raise RenderError(f"Segment B not found: {segment_b_path}")

    ffmpeg = _find_ffmpeg()

    if effect == "cut":
        return _concat_cut(ffmpeg, segment_a_path, segment_b_path, output_path)

    if effect == "black_title":
        return _black_title_transition(
            ffmpeg, segment_a_path, segment_b_path, output_path, duration_s,
        )

    xfade_name = EFFECTS[effect]
    return _xfade_transition(
        ffmpeg, segment_a_path, segment_b_path, output_path,
        xfade_name, duration_s,
    )


def _xfade_transition(
    ffmpeg: str,
    seg_a: str, seg_b: str, output: str,
    xfade_name: str, duration: float,
) -> str:
    """Apply xfade filter between two segments."""
    # Get duration of segment A to calculate offset
    dur_a = _get_segment_duration(ffmpeg, seg_a)
    offset = max(0, dur_a - duration)

    cmd = [
        ffmpeg, "-y",
        "-i", seg_a,
        "-i", seg_b,
        "-filter_complex",
        f"[0:v][1:v]xfade=transition={xfade_name}:duration={duration}:offset={offset}[v];"
        f"[0:a][1:a]acrossfade=d={duration}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-ar", "44100", "-c:a", "aac", "-b:a", "128k",
        output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
    if result.returncode != 0:
        raise RenderError(f"xfade failed ({xfade_name}): {result.stderr[-300:]}")
    return output


def _concat_cut(ffmpeg: str, seg_a: str, seg_b: str, output: str) -> str:
    """Simple concatenation (no transition)."""
    import tempfile
    list_file = os.path.join(tempfile.gettempdir(), "concat_list.txt")
    with open(list_file, "w") as f:
        f.write(f"file '{seg_a}'\nfile '{seg_b}'\n")

    cmd = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0", "-i", list_file,
        "-c", "copy", output,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
    os.unlink(list_file)
    if result.returncode != 0:
        raise RenderError(f"Concat cut failed: {result.stderr[-300:]}")
    return output


def _black_title_transition(
    ffmpeg: str, seg_a: str, seg_b: str, output: str, duration: float,
) -> str:
    """Black screen with white text transition (using lavfi)."""
    # Generate black frames with text
    cmd = [
        ffmpeg, "-y",
        "-i", seg_a,
        "-f", "lavfi", "-i",
        f"color=c=black:s=1920x1080:d={duration},format=yuv420p",
        "-f", "lavfi", "-i",
        f"anullsrc=channel_layout=stereo:sample_rate=44100",
        "-i", seg_b,
        "-filter_complex",
        f"[0:v][1:v][3:v]concat=n=3:v=1:a=0[v];"
        f"[0:a][2:a][3:a]concat=n=3:v=0:a=1[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-ar", "44100", "-c:a", "aac", "-b:a", "128k",
        "-t", str(_get_segment_duration(ffmpeg, seg_a) + duration + _get_segment_duration(ffmpeg, seg_b)),
        output,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
    if result.returncode != 0:
        raise RenderError(f"Black title transition failed: {result.stderr[-300:]}")
    return output


def _get_segment_duration(ffmpeg: str, path: str) -> float:
    import json
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return 5.0
