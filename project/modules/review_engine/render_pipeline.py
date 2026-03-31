"""Rough cut render pipeline — FFmpeg concat from EDITS list.

Renders a list of Segment objects into a single video file using
FFmpeg's concat demuxer. Handles HEVC transcoding, loudnorm, and
audio sync.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Callable, Dict, List, Optional

from modules.review_engine.contracts import Segment
from modules.review_engine.exceptions import RenderError

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT_S = 300
MAX_RETRIES = 3


def _find_ffmpeg() -> str:
    """Find FFmpeg binary."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    homebrew = "/opt/homebrew/bin/ffmpeg"
    if os.path.isfile(homebrew):
        return homebrew
    raise RenderError("FFmpeg not found")


def _run_ffmpeg(
    cmd: List[str],
    timeout: int = FFMPEG_TIMEOUT_S,
    retries: int = MAX_RETRIES,
) -> subprocess.CompletedProcess:
    """Run an FFmpeg command with timeout and retry logic.

    Captures stderr for diagnostics. Retries on timeout.

    Raises:
        RenderError: After all retries exhausted.
    """
    last_error = None
    for attempt in range(retries):
        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=timeout,
            )
            if result.returncode == 0:
                return result

            stderr = (result.stderr or b"").decode("utf-8", errors="replace")[:1000]
            last_error = f"FFmpeg exit code {result.returncode}: {stderr}"
            logger.warning("FFmpeg attempt %d/%d failed: %s", attempt + 1, retries, last_error)

        except subprocess.TimeoutExpired:
            last_error = f"FFmpeg timed out after {timeout}s"
            logger.warning("FFmpeg attempt %d/%d: %s", attempt + 1, retries, last_error)

    raise RenderError(f"FFmpeg failed after {retries} attempts: {last_error}")


def _transcode_segment(
    source_path: str,
    start_ms: int,
    end_ms: int,
    output_path: str,
    ffmpeg_bin: str,
) -> str:
    """Trim and transcode a segment to H.264+AAC.

    Handles HEVC iPhone MOV files by transcoding to H.264.
    """
    start_s = start_ms / 1000.0
    duration_s = (end_ms - start_ms) / 1000.0

    cmd = [
        ffmpeg_bin, "-y",
        "-ss", f"{start_s:.3f}",
        "-i", source_path,
        "-t", f"{duration_s:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        output_path,
    ]

    _run_ffmpeg(cmd)
    return output_path


def render_rough_cut(
    edits: List[Segment],
    output_path: str,
    apply_loudnorm: bool = True,
    on_progress: Optional[Callable] = None,
) -> Dict:
    """Render a rough cut from an EDITS list.

    Steps:
    1. Transcode each segment to H.264+AAC temp file
    2. Create concat list
    3. Concatenate with FFmpeg concat demuxer
    4. Optional: apply loudnorm (with -ar 44100 to prevent bug)

    Args:
        edits: List of Segment objects to concatenate.
        output_path: Output video file path.
        apply_loudnorm: Apply loudness normalization.
        on_progress: Callback (step, total_steps, message).

    Returns:
        Dict with: video_path, duration_s, file_size_bytes, processing_time_s.

    Raises:
        RenderError: If rendering fails.
    """
    if not edits:
        raise RenderError("Empty EDITS list — nothing to render")

    # Filter out removed segments
    active_edits = [e for e in edits if e.segment_type != "removed"]
    if not active_edits:
        raise RenderError("All segments removed — nothing to render")

    ffmpeg_bin = _find_ffmpeg()
    tmp_dir = tempfile.mkdtemp(prefix="roughcut_render_")
    start_time = time.time()
    total_steps = len(active_edits) + 2  # segments + concat + (loudnorm)

    try:
        # Step 1: Transcode segments
        segment_paths = []
        for i, seg in enumerate(active_edits):
            if on_progress:
                on_progress(i + 1, total_steps, f"Transcoding segment {i + 1}/{len(active_edits)}")

            seg_path = os.path.join(tmp_dir, f"seg_{i:04d}.mp4")
            _transcode_segment(seg.source_path, seg.start_ms, seg.end_ms, seg_path, ffmpeg_bin)
            segment_paths.append(seg_path)

        # Step 2: Create concat list
        concat_list = os.path.join(tmp_dir, "concat.txt")
        with open(concat_list, "w") as f:
            for path in segment_paths:
                f.write(f"file '{path}'\n")

        # Step 3: Concatenate
        if on_progress:
            on_progress(len(active_edits) + 1, total_steps, "Concatenating segments")

        concat_output = os.path.join(tmp_dir, "concat.mp4")
        concat_cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            concat_output,
        ]
        _run_ffmpeg(concat_cmd)

        # Step 4: Loudnorm (optional)
        if apply_loudnorm:
            if on_progress:
                on_progress(len(active_edits) + 2, total_steps, "Normalizing audio")

            norm_cmd = [
                ffmpeg_bin, "-y",
                "-i", concat_output,
                "-c:v", "copy",
                "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
                "-ar", "44100",  # MUST: prevent loudnorm sample rate bug
                "-c:a", "aac", "-b:a", "128k",
                output_path,
            ]
            _run_ffmpeg(norm_cmd)
        else:
            shutil.move(concat_output, output_path)

        # Get output info
        duration_s = _get_duration(output_path, ffmpeg_bin)
        file_size = os.path.getsize(output_path)
        processing_time = time.time() - start_time

        logger.info(
            "Rough cut rendered: %.1fs, %.1fMB, took %.1fs",
            duration_s, file_size / 1024 / 1024, processing_time,
        )

        return {
            "video_path": output_path,
            "duration_s": round(duration_s, 2),
            "file_size_bytes": file_size,
            "processing_time_s": round(processing_time, 2),
        }

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _get_duration(video_path: str, ffmpeg_bin: str) -> float:
    """Get video duration."""
    ffprobe = ffmpeg_bin.replace("ffmpeg", "ffprobe")
    cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", video_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = __import__("json").loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        logger.warning("Failed to get duration for %s: %s", video_path, e)
        return 0.0
