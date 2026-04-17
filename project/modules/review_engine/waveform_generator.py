"""Waveform data generator for review timeline.

Extracts audio from a video file, downsamples to a peaks array
suitable for rendering as a waveform visualization in the frontend
WaveformTrack component.

Usage:
    from modules.review_engine.waveform_generator import generate_waveform
    result = generate_waveform("/path/to/video.mp4", "/output/dir/")
    # result = {"peaks": [0.1, 0.5, ...], "sample_rate": 44100,
    #           "samples_per_peak": 4410, "duration_ms": 60000, "peak_count": 600}
"""

import json
import logging
import math
import os
import shutil
import struct
import subprocess
import tempfile
from typing import List, Optional

from modules.review_engine.exceptions import RenderError

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT_S = 120

# Waveform defaults
DEFAULT_PEAKS_PER_SECOND = 10
MAX_PEAKS = 3000
AUDIO_SAMPLE_RATE = 44100


def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    homebrew = "/opt/homebrew/bin/ffmpeg"
    if os.path.isfile(homebrew):
        return homebrew
    raise RenderError("FFmpeg not found")


def generate_waveform(
    video_path: str,
    output_dir: str,
    peaks_per_second: int = DEFAULT_PEAKS_PER_SECOND,
) -> dict:
    """Generate waveform peak data from a video's audio track.

    Extracts audio as raw PCM s16le mono, then computes peak amplitudes
    at the requested resolution.

    Args:
        video_path: Path to source video.
        output_dir: Directory to write waveform JSON.
        peaks_per_second: Number of peak samples per second of audio.

    Returns:
        dict with peaks (float[0..1]), sample_rate, samples_per_peak,
        duration_ms, peak_count.

    Raises:
        RenderError: If FFmpeg fails or no audio track found.
    """
    if not os.path.isfile(video_path):
        raise RenderError(f"Video not found: {video_path}")
    os.makedirs(output_dir, exist_ok=True)

    ffmpeg = _find_ffmpeg()
    # Round-15: per-call PCM tempfile. Previously the fixed name
    # "audio_raw.pcm" caused two concurrent renders targeting the same
    # output_dir to corrupt each other's extraction. Use mkstemp so the
    # two workers get isolated files and can clean up independently.
    import tempfile as _tf
    fd_pcm, pcm_path = _tf.mkstemp(dir=output_dir, prefix="audio_raw_", suffix=".pcm")
    os.close(fd_pcm)  # ffmpeg will reopen for writing

    # Extract raw PCM (signed 16-bit little-endian, mono, 44100 Hz)
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-ac", "1",
        "-f", "s16le",
        pcm_path,
    ]

    logger.info("Extracting audio for waveform: %s", video_path)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S
        )
        if result.returncode != 0:
            # No audio track is not fatal — return flat waveform
            if "does not contain any stream" in result.stderr:
                logger.warning("No audio track found, returning flat waveform")
                return _flat_waveform(output_dir)
            raise RenderError(f"FFmpeg audio extraction failed: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        raise RenderError("Audio extraction timed out")

    if not os.path.isfile(pcm_path) or os.path.getsize(pcm_path) == 0:
        logger.warning("Empty PCM output, returning flat waveform")
        return _flat_waveform(output_dir)

    # Read PCM and compute peaks
    peaks = _compute_peaks(pcm_path, peaks_per_second)

    # Clean up raw PCM
    try:
        os.remove(pcm_path)
    except OSError:
        pass

    total_samples = len(peaks)
    duration_ms = int((total_samples / peaks_per_second) * 1000) if peaks_per_second else 0

    metadata = {
        "peaks": peaks,
        "sample_rate": AUDIO_SAMPLE_RATE,
        "samples_per_peak": AUDIO_SAMPLE_RATE // peaks_per_second,
        "duration_ms": duration_ms,
        "peak_count": total_samples,
    }

    # Round-15: atomic write via shared helper.
    from modules.app_api.param_utils import atomic_write_json
    meta_path = os.path.join(output_dir, "waveform.json")
    atomic_write_json(meta_path, metadata, indent=None)

    logger.info("Waveform generated: %d peaks over %dms", total_samples, duration_ms)
    return metadata


def _compute_peaks(pcm_path: str, peaks_per_second: int) -> List[float]:
    """Compute peak amplitudes from raw PCM s16le mono data."""
    samples_per_peak = AUDIO_SAMPLE_RATE // peaks_per_second
    peaks = []
    max_val = 32768.0  # s16 range

    with open(pcm_path, "rb") as f:
        while True:
            # Read one peak-window worth of samples
            chunk = f.read(samples_per_peak * 2)  # 2 bytes per s16 sample
            if not chunk:
                break

            # Unpack s16le samples
            n_samples = len(chunk) // 2
            if n_samples == 0:
                break

            samples = struct.unpack(f"<{n_samples}h", chunk[:n_samples * 2])

            # Peak = max absolute value normalized to [0, 1]
            peak = max(abs(s) for s in samples) / max_val
            peaks.append(round(min(1.0, peak), 4))

            if len(peaks) >= MAX_PEAKS:
                break

    return peaks


def _flat_waveform(output_dir: str) -> dict:
    """Return a flat (silent) waveform when no audio is available."""
    metadata = {
        "peaks": [],
        "sample_rate": AUDIO_SAMPLE_RATE,
        "samples_per_peak": AUDIO_SAMPLE_RATE // DEFAULT_PEAKS_PER_SECOND,
        "duration_ms": 0,
        "peak_count": 0,
    }
    from modules.app_api.param_utils import atomic_write_json
    meta_path = os.path.join(output_dir, "waveform.json")
    atomic_write_json(meta_path, metadata, indent=None)
    return metadata
