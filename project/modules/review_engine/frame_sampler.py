"""FrameSampler — keyframe extraction strategies (B1).

Provides scene_boundary, uniform, and hybrid sampling from video files.
Uses FFmpeg for single-frame extraction.
"""

import logging
import os
import subprocess
import tempfile
from typing import List, Optional

from modules.review_engine.contracts import SampledFrame

logger = logging.getLogger(__name__)

# Default sampling parameters
DEFAULT_INTERVAL_MS = 5000  # 5 seconds for uniform sampling
HYBRID_INTRA_INTERVAL_MS = 10000  # 10 seconds for intra-scene hybrid
DEFAULT_MAX_FRAMES = 50

# FFmpeg binary path (prefer Homebrew on macOS)
_FFMPEG = "/opt/homebrew/bin/ffmpeg"
if not os.path.exists(_FFMPEG):
    _FFMPEG = "ffmpeg"


def _extract_frame_pil(video_path: str, timestamp_ms: int):
    """Extract a single frame at timestamp_ms as PIL.Image.

    This is the unified frame extraction function (audit M7).
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("PIL not available, returning None for frame at %dms", timestamp_ms)
        return None

    ts_s = timestamp_ms / 1000.0
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = [
            _FFMPEG, "-ss", f"{ts_s:.3f}", "-i", video_path,
            "-vframes", "1", "-q:v", "2", "-y", tmp_path,
        ]
        subprocess.run(
            cmd, capture_output=True, timeout=10,
            check=False,
        )
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            img = Image.open(tmp_path)
            img.load()  # Force read before file is deleted
            return img
        return None
    except Exception as exc:
        logger.warning("Frame extraction failed at %dms: %s", timestamp_ms, exc)
        return None
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _get_video_duration_ms(video_path: str) -> int:
    """Get video duration in milliseconds using ffprobe."""
    try:
        ffprobe = _FFMPEG.replace("ffmpeg", "ffprobe")
        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0", video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return int(float(result.stdout.strip()) * 1000)
    except Exception as exc:
        logger.warning("Could not get duration for %s: %s", video_path, exc)
    return 0


class FrameSampler:
    """Extract keyframes from video using configurable strategies."""

    def __init__(self, max_frames: int = DEFAULT_MAX_FRAMES):
        self.max_frames = max_frames

    def sample(
        self,
        video_path: str,
        strategy: str = "hybrid",
        scene_boundaries: Optional[List[int]] = None,
        interval_ms: int = DEFAULT_INTERVAL_MS,
    ) -> List[SampledFrame]:
        """Sample frames from a video.

        Args:
            video_path: Path to video file.
            strategy: "scene_boundary" | "uniform" | "hybrid".
            scene_boundaries: List of boundary timestamps (ms) for scene-based sampling.
            interval_ms: Sampling interval for uniform mode.

        Returns:
            List of SampledFrame (may be fewer than max_frames).
        """
        if not os.path.exists(video_path):
            logger.warning("Video not found: %s", video_path)
            return []

        duration_ms = _get_video_duration_ms(video_path)
        if duration_ms <= 0:
            logger.warning("Could not determine video duration: %s", video_path)
            return []

        if strategy == "scene_boundary":
            timestamps = self._scene_boundary_timestamps(scene_boundaries or [], duration_ms)
        elif strategy == "uniform":
            timestamps = self._uniform_timestamps(duration_ms, interval_ms)
        elif strategy == "hybrid":
            timestamps = self._hybrid_timestamps(scene_boundaries or [], duration_ms)
        else:
            logger.warning("Unknown strategy '%s', falling back to uniform", strategy)
            timestamps = self._uniform_timestamps(duration_ms, interval_ms)

        # Cap at max_frames (subsample uniformly if needed)
        if len(timestamps) > self.max_frames:
            step = len(timestamps) / self.max_frames
            timestamps = [timestamps[int(i * step)] for i in range(self.max_frames)]

        # Extract frames
        frames = []
        _cache = {}  # timestamp → PIL.Image cache
        for ts_ms, scene_idx, source in timestamps:
            if ts_ms in _cache:
                img = _cache[ts_ms]
            else:
                img = _extract_frame_pil(video_path, ts_ms)
                _cache[ts_ms] = img
            if img is not None:
                frames.append(SampledFrame(
                    frame=img,
                    timestamp_ms=ts_ms,
                    scene_idx=scene_idx,
                    source=source,
                ))

        logger.info("Sampled %d frames from %s (strategy=%s)", len(frames), video_path, strategy)
        return frames

    # ── Timestamp generation ─────────────────────────────────────

    def _scene_boundary_timestamps(self, boundaries, duration_ms):
        """Scene boundary sampling: first frame of each scene."""
        if not boundaries:
            return [(0, 0, "scene_boundary")]
        result = []
        for i, ts in enumerate(sorted(boundaries)):
            if 0 <= ts < duration_ms:
                result.append((ts, i, "scene_boundary"))
        if not result:
            result.append((0, 0, "scene_boundary"))
        return result

    def _uniform_timestamps(self, duration_ms, interval_ms):
        """Uniform sampling at fixed intervals."""
        if interval_ms <= 0:
            interval_ms = 1000  # default 1 s to prevent infinite loop
        result = []
        ts = 0
        idx = 0
        while ts < duration_ms:
            result.append((ts, idx, "uniform"))
            ts += interval_ms
            idx += 1
        return result

    def _hybrid_timestamps(self, boundaries, duration_ms):
        """Hybrid: scene boundaries + intra-scene sampling every 10s."""
        result = []
        if not boundaries:
            boundaries = [0]

        sorted_boundaries = sorted(set(boundaries))
        for i, start in enumerate(sorted_boundaries):
            end = sorted_boundaries[i + 1] if i + 1 < len(sorted_boundaries) else duration_ms
            # Scene boundary frame
            if 0 <= start < duration_ms:
                result.append((start, i, "scene_boundary"))
            # Intra-scene uniform sampling
            ts = start + HYBRID_INTRA_INTERVAL_MS
            while ts < end and ts < duration_ms:
                result.append((ts, i, "hybrid"))
                ts += HYBRID_INTRA_INTERVAL_MS

        # Deduplicate by timestamp
        seen = set()
        deduped = []
        for item in result:
            if item[0] not in seen:
                seen.add(item[0])
                deduped.append(item)
        return deduped
