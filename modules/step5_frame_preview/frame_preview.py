#!/usr/bin/env python3
"""Step5 frame preview generator."""

from pathlib import Path
from typing import Callable, Dict, Optional
import re
import subprocess


def generate_frame_previews(
    script: Dict,
    materials: Dict,
    frames_dir: Path,
    ffmpeg: str,
    resolve_video_path: Callable[[str], Optional[str]],
    check_cancel: Optional[Callable[[], None]] = None,
    emit_progress: Optional[Callable[[float, str], None]] = None,
) -> Dict:
    """
    Extract midpoint preview frame for each script clip.

    Returns:
        {"extracted": int}
    """
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    def _check_cancel():
        if callable(check_cancel):
            check_cancel()

    def _emit(progress: float, message: str):
        if callable(emit_progress):
            emit_progress(progress, message)

    extracted = 0
    total = max(len(script.get("clips", [])), 1)

    for clip in script.get("clips", []):
        _check_cancel()
        idx = clip.get("clip_index", extracted)
        vid_id = clip.get("video_id")
        if not vid_id:
            continue

        vid_path = resolve_video_path(str(vid_id))
        if not vid_path:
            print(f"  片段 {idx}: 找不到 {vid_id}，跳过")
            continue

        ss = clip.get("source_start", 0)
        se = clip.get("source_end", ss + clip.get("duration", 5))
        mid = (ss + se) / 2.0

        desc = re.sub(r"[^\w\u4e00-\u9fff]", "_", clip.get("scene_description", "clip"))[:20]
        out_jpg = frames_dir / f"{idx:02d}_{desc}.jpg"
        cmd = [ffmpeg, "-y", "-ss", str(mid), "-i", vid_path, "-vframes", "1", "-q:v", "2", str(out_jpg)]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            extracted += 1
            print(f"  ✓ 片段 {idx}: {out_jpg.name}")
            _emit(5 + (extracted / total) * 10, f"帧预览 {extracted}/{total}")
        else:
            print(f"  ✗ 片段 {idx}: 提取失败")

    return {"extracted": extracted}

