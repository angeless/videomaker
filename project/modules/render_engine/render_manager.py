"""RenderManager — parallel segment rendering scheduler (D3).

Splits a timeline into segments, renders them in parallel via FFmpeg
subprocesses, and concatenates the results. Uses HardwareProfile to
determine concurrency and encoding strategy.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple

from modules.hardware.detector import HardwareProfile
from modules.hardware.encoding_strategy import suggest_max_concurrent
from modules.review_engine.contracts import Clip, Segment

logger = logging.getLogger(__name__)


class RenderError(Exception):
    """Raised when rendering fails."""
    pass


class RenderManager:
    """Orchestrates parallel segment rendering.

    Architecture note (H3): This class lives in modules/render_engine/ (Business layer),
    while hardware/ is Infrastructure layer (detection + strategy).
    """

    def __init__(self, profile: HardwareProfile):
        self._profile = profile
        self._ffmpeg = profile.ffmpeg_path or "ffmpeg"

    # ── Clip → Segment adapter (H4) ─────────────────────────────

    @staticmethod
    def clip_to_segment(clip: Clip) -> Segment:
        """Convert a timeline Clip to a render Segment.

        Clip uses source_in_ms/source_out_ms for the source range.
        Segment uses start_ms/end_ms.
        """
        return Segment(
            source_path=clip.source_path,
            start_ms=clip.source_in_ms,
            end_ms=clip.source_out_ms,
        )

    # ── Main render entry ────────────────────────────────────────

    def render_timeline(
        self,
        clips: List[Clip],
        output_path: str,
        *,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """Render a full timeline to a single output file.

        Args:
            clips: List of Clip objects from the timeline.
            output_path: Destination file path for the final render.
            progress_callback: Called with (completed_count, total_count)
                after each segment finishes.

        Returns:
            Path to the rendered output file.

        Raises:
            RenderError: If rendering fails after retries.
        """
        if not clips:
            raise RenderError("No clips to render")

        segments = [self.clip_to_segment(c) for c in clips]
        max_workers = suggest_max_concurrent(self._profile)
        temp_dir = tempfile.mkdtemp(prefix="ve_render_")

        try:
            # 1. Render segments in parallel
            seg_outputs = self._render_segments_parallel(
                segments, temp_dir, max_workers, progress_callback,
            )
            # 2. Concat all segments
            self._concat_segments(seg_outputs, output_path, temp_dir)
            return output_path
        except Exception:
            # Clean output on failure
            if os.path.exists(output_path):
                os.remove(output_path)
            raise
        finally:
            # Always clean temp dir
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ── Parallel rendering ───────────────────────────────────────

    def _render_segments_parallel(
        self,
        segments: List[Segment],
        temp_dir: str,
        max_workers: int,
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> List[str]:
        """Render each segment in parallel. Returns ordered output paths."""
        total = len(segments)
        results: Dict[int, str] = {}
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for i, seg in enumerate(segments):
                out_path = os.path.join(temp_dir, f"seg_{i:04d}.mp4")
                fut = pool.submit(self._render_single_segment, seg, out_path)
                futures[fut] = i

            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    path = fut.result()
                    results[idx] = path
                except RenderError:
                    # Retry once
                    seg = segments[idx]
                    retry_path = os.path.join(temp_dir, f"seg_{idx:04d}_retry.mp4")
                    try:
                        results[idx] = self._render_single_segment(seg, retry_path)
                    except Exception as exc:
                        raise RenderError(
                            f"Segment {idx} failed after retry: {exc}"
                        ) from exc
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        return [results[i] for i in range(total)]

    def _render_single_segment(self, segment: Segment, output_path: str) -> str:
        """Render a single segment via FFmpeg."""
        if not segment.source_path:
            raise RenderError(f"Segment has no source_path")

        start_s = segment.start_ms / 1000.0
        duration_s = (segment.end_ms - segment.start_ms) / 1000.0

        cmd = [
            self._ffmpeg, "-y",
            "-ss", f"{start_s:.3f}",
            "-i", segment.source_path,
            "-t", f"{duration_s:.3f}",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-ar", "44100",  # prevent loudnorm sample rate bug
            "-preset", "fast",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if proc.returncode != 0:
                raise RenderError(
                    f"FFmpeg failed (exit {proc.returncode}): {proc.stderr[-500:]}"
                )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(f"Segment render timed out (300s)") from exc

        if not os.path.exists(output_path):
            raise RenderError(f"Output file not created: {output_path}")

        return output_path

    # ── Concat ───────────────────────────────────────────────────

    def _concat_segments(
        self,
        segment_paths: List[str],
        output_path: str,
        temp_dir: str,
    ) -> None:
        """Concatenate segment files using FFmpeg concat demuxer."""
        if len(segment_paths) == 1:
            shutil.copy2(segment_paths[0], output_path)
            return

        concat_list = os.path.join(temp_dir, "concat.txt")
        # Round-14: use escape-aware helper. Without this, a segment path
        # with a single quote would inject arbitrary concat directives.
        from modules.render_engine.concat_utils import concat_list_body
        with open(concat_list, "w") as f:
            f.write(concat_list_body(segment_paths))

        cmd = [
            self._ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RenderError(f"Concat failed: {proc.stderr[-500:]}")
