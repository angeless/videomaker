#!/usr/bin/env python3
"""Step6 rough cut builder."""

from pathlib import Path
from typing import Callable, Dict, Optional
import subprocess
import tempfile
import shutil


def build_rough_cut(
    script: Dict,
    materials: Dict,
    rough_path: Path,
    ffmpeg: str,
    render_config: Dict,
    resolve_video_path: Callable[[str], Optional[str]],
    check_cancel: Optional[Callable[[], None]] = None,
    emit_progress: Optional[Callable[[float, str], None]] = None,
) -> Dict:
    """
    Build a 15s rough-cut preview from matched script clips.

    Returns:
        {"used_seconds": float, "segment_count": int}
    """
    rough_path = Path(rough_path)
    rough_path.parent.mkdir(parents=True, exist_ok=True)

    def _check_cancel():
        if callable(check_cancel):
            check_cancel()

    def _emit(progress: float, message: str):
        if callable(emit_progress):
            emit_progress(progress, message)

    rc = render_config or {}
    crf = rc.get("crf_rough", 28)
    preset = rc.get("preset_rough", "ultrafast")
    fps = rc.get("fps", 30)
    w, h = rc.get("width", 1080), rc.get("height", 1920)

    tmp = Path(tempfile.mkdtemp(prefix="rough_"))
    segs = []
    budget = 15.0
    used = 0.0

    try:
        for clip in script.get("clips", []):
            _check_cancel()
            if used >= budget:
                break

            vid_id = clip.get("video_id")
            if not vid_id:
                continue

            vid_path = resolve_video_path(str(vid_id))
            if not vid_path:
                continue

            ss = clip.get("source_start", 0)
            se = clip.get("source_end", ss + clip.get("duration", 5))
            allot = min(se - ss, budget - used)
            seg_out = tmp / f"seg_{len(segs):03d}.mp4"

            vf = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}"
            )
            cmd = [
                ffmpeg,
                "-y",
                "-ss",
                str(ss),
                "-i",
                vid_path,
                "-t",
                str(allot),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-preset",
                preset,
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-pix_fmt",
                "yuv420p",
                str(seg_out),
            ]
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode == 0:
                segs.append(str(seg_out))
                used += allot
                _emit(20 + min(used / max(budget, 1.0), 1.0) * 10, f"粗剪时长 {used:.1f}/{budget:.1f}s")

        if not segs:
            raise RuntimeError("没有可用片段生成粗剪")

        concat_list = tmp / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p}'" for p in segs), encoding="utf-8")
        cmd2 = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(rough_path)]
        _check_cancel()
        subprocess.run(cmd2, capture_output=True, check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return {
        "used_seconds": used,
        "segment_count": len(segs),
    }

