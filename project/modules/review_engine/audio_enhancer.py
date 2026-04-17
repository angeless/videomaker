"""AudioEnhancer — FFmpeg filter chain for audio enhancement.

Applies denoise (afftdn) → equalizer → compressor → loudnorm
as configurable stages via FFmpeg subprocess.
"""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from modules.render_engine.concat_utils import safe_ffmpeg_arg
from .exceptions import RenderError

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT_S = 120
MAX_RETRIES = 3


@dataclass
class AudioConfig:
    """Configuration for audio enhancement stages."""
    denoise: bool = True
    equalizer: bool = True
    compressor: bool = True
    loudnorm: bool = True
    target_lufs: float = -16.0
    eq_preset: str = "voice"  # "voice" | "music" | "flat"


# EQ presets: FFmpeg equalizer filter params
_EQ_PRESETS = {
    "voice": "equalizer=f=300:t=h:w=200:g=3,equalizer=f=3000:t=h:w=1000:g=2",
    "music": "equalizer=f=60:t=h:w=50:g=2,equalizer=f=10000:t=h:w=2000:g=1",
    "flat": "",
}


def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    brew_path = "/opt/homebrew/bin/ffmpeg"
    if os.path.isfile(brew_path):
        return brew_path
    raise RenderError("FFmpeg not found")


def enhance_audio(
    audio_path: str,
    output_path: str,
    config: Optional[AudioConfig] = None,
) -> str:
    """Apply audio enhancement filter chain.

    Returns the output file path.
    """
    if not os.path.isfile(audio_path):
        raise RenderError(f"Input audio not found: {audio_path}")

    config = config or AudioConfig()
    ffmpeg = _find_ffmpeg()

    # Build filter chain
    filters: List[str] = []

    if config.denoise:
        filters.append("afftdn=nf=-25")

    if config.equalizer:
        preset = _EQ_PRESETS.get(config.eq_preset, "")
        if preset:
            filters.append(preset)

    if config.compressor:
        filters.append("acompressor=threshold=-20dB:ratio=4:attack=5:release=50")

    if config.loudnorm:
        filters.append(
            f"loudnorm=I={config.target_lufs}:LRA=11:TP=-1.5"
        )

    if not filters:
        # No processing needed, just copy
        shutil.copy2(audio_path, output_path)
        return output_path

    af = ",".join(filters)

    # Round-15.5: safe_ffmpeg_arg prevents leading-dash filename argv
    # injection (e.g. user file "-filter_complex;..." being parsed as
    # an option). Absolute paths pass through unchanged; relative ones
    # get a "./" prefix.
    cmd = [
        ffmpeg, "-y",
        "-i", safe_ffmpeg_arg(audio_path),
        "-af", af,
        "-ar", "44100",  # MUST: prevent loudnorm sample rate bug
        "-c:a", "aac", "-b:a", "128k",
        safe_ffmpeg_arg(output_path),
    ]

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S,
            )
            if result.returncode == 0:
                return output_path
            last_error = result.stderr[-500:] if result.stderr else "unknown error"
            logger.warning(
                "FFmpeg attempt %d/%d failed (rc=%d): %s",
                attempt + 1, MAX_RETRIES, result.returncode, last_error,
            )
        except subprocess.TimeoutExpired:
            last_error = f"timeout after {FFMPEG_TIMEOUT_S}s"
            logger.warning(
                "FFmpeg attempt %d/%d timed out after %ds",
                attempt + 1, MAX_RETRIES, FFMPEG_TIMEOUT_S,
            )
        except OSError as e:
            raise RenderError(f"FFmpeg not found or not executable: {e}") from e

    raise RenderError(
        f"Audio enhancement failed after {MAX_RETRIES} retries: {last_error}"
    )
