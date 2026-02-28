"""Generate and launch external NLE handoff files (FCPXML / EDL)."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List
from xml.etree.ElementTree import Element, ElementTree, SubElement
import json
import shutil
import subprocess
import sys


DEFAULT_NLE_APPS: Dict[str, str] = {
    "finalcut": "Final Cut Pro",
    "premiere": "Adobe Premiere Pro",
    "davinci": "DaVinci Resolve",
    "jianying": "剪映专业版",
}

EDITOR_FILE_PRIORITY: Dict[str, List[str]] = {
    "finalcut": [".fcpxml", ".edl", ".json"],
    "premiere": [".edl", ".fcpxml", ".json"],
    "davinci": [".fcpxml", ".edl", ".json"],
    "jianying": [".json", ".fcpxml", ".edl"],
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}


@dataclass
class TimelineClip:
    """Normalized clip for NLE exchange."""

    index: int
    video_id: str
    file_path: str
    source_start: float
    source_end: float
    timeline_start: float
    timeline_end: float
    scene_description: str


def build_timeline_clips(script: Dict, materials: Dict) -> List[TimelineClip]:
    """Build timeline clips with resolved media paths."""
    timeline: List[TimelineClip] = []
    cursor = 0.0
    for idx, clip in enumerate(script.get("clips", []), start=1):
        video_id = str(clip.get("video_id") or "")
        if not video_id:
            continue
        media_path = _resolve_material_path(video_id, materials)
        if not media_path:
            continue
        source_start = _to_float(clip.get("source_start", 0), 0.0)
        source_end_raw = clip.get("source_end")
        if source_end_raw is None:
            source_end = source_start + _to_float(clip.get("duration", 5), 5.0)
        else:
            source_end = _to_float(source_end_raw, source_start + 5.0)
        if source_end <= source_start:
            source_end = source_start + 0.1

        duration = source_end - source_start
        timeline_start = cursor
        timeline_end = cursor + duration
        cursor = timeline_end

        timeline.append(
            TimelineClip(
                index=idx,
                video_id=video_id,
                file_path=media_path,
                source_start=round(source_start, 3),
                source_end=round(source_end, 3),
                timeline_start=round(timeline_start, 3),
                timeline_end=round(timeline_end, 3),
                scene_description=str(clip.get("scene_description", "") or ""),
            )
        )
    return timeline


def create_nle_handoff(
    script: Dict,
    materials: Dict,
    output_dir: str,
    editor: str = "finalcut",
    title: str = "VideoEditer",
    fps: int = 30,
) -> Dict:
    """
    Create NLE handoff package for a target editor.

    Supported editor values:
    - finalcut  -> FCPXML + manifest
    - premiere  -> EDL + manifest
    - davinci   -> FCPXML + EDL + manifest
    - jianying  -> manifest only (keeps compatibility)
    """
    editor_key = str(editor or "finalcut").strip().lower()
    if editor_key not in {"finalcut", "premiere", "davinci", "jianying"}:
        editor_key = "finalcut"

    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = build_timeline_clips(script, materials)
    if not clips:
        raise ValueError("No clips available for NLE handoff")

    files: List[str] = []
    if editor_key in {"finalcut", "davinci"}:
        fcpxml_path = out_dir / f"{_safe_name(title)}.fcpxml"
        generate_fcpxml(clips, str(fcpxml_path), title=title, fps=fps)
        files.append(str(fcpxml_path))
    if editor_key in {"premiere", "davinci"}:
        edl_path = out_dir / f"{_safe_name(title)}.edl"
        generate_edl(clips, str(edl_path), title=title, fps=fps)
        files.append(str(edl_path))

    manifest_path = out_dir / "timeline_manifest.json"
    manifest = {
        "title": title,
        "editor": editor_key,
        "fps": int(fps),
        "clip_count": len(clips),
        "clips": [asdict(c) for c in clips],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    files.append(str(manifest_path))

    return {
        "editor": editor_key,
        "title": title,
        "fps": int(fps),
        "output_dir": str(out_dir),
        "clip_count": len(clips),
        "files": files,
    }


def select_launch_target(files: List[str], editor: str) -> str:
    """Select preferred handoff file for launching an external editor."""
    editor_key = str(editor or "").strip().lower()
    priority = EDITOR_FILE_PRIORITY.get(editor_key, [".fcpxml", ".edl", ".json"])
    candidates = [str(Path(p).resolve()) for p in files if str(p or "").strip()]
    if not candidates:
        return ""
    for suffix in priority:
        for path in candidates:
            if path.lower().endswith(suffix):
                return path
    return candidates[0]


def build_nle_launch_command(
    editor: str,
    target_file: str,
    app_name: str = "",
    platform_key: str = "",
) -> Dict:
    """Build platform-specific launch command."""
    editor_key = str(editor or "").strip().lower()
    platform_id = str(platform_key or sys.platform).strip().lower()
    selected_app = str(app_name or DEFAULT_NLE_APPS.get(editor_key, "")).strip()
    target = str(Path(target_file).resolve())

    if platform_id.startswith("darwin"):
        cmd = ["open"]
        if selected_app:
            cmd.extend(["-a", selected_app])
        cmd.append(target)
        return {"platform": "darwin", "app_name": selected_app, "command": cmd}
    if platform_id.startswith("linux"):
        return {"platform": "linux", "app_name": "", "command": ["xdg-open", target]}
    if platform_id.startswith("win"):
        return {"platform": "windows", "app_name": "", "command": ["cmd", "/c", "start", "", target]}
    raise ValueError(f"Unsupported platform for launch: {platform_id}")


def launch_nle_handoff(
    handoff: Dict,
    app_name: str = "",
    timeout_seconds: float = 20,
    dry_run: bool = False,
    platform_key: str = "",
) -> Dict:
    """Launch generated handoff file in external editor."""
    editor_key = str(handoff.get("editor", "") or "").strip().lower()
    files = handoff.get("files", [])
    if not isinstance(files, list):
        files = []
    target = select_launch_target(files, editor=editor_key)
    if not target:
        raise ValueError("No handoff target file found")
    if not Path(target).exists():
        raise ValueError(f"Handoff target does not exist: {target}")

    launch = build_nle_launch_command(
        editor=editor_key,
        target_file=target,
        app_name=app_name,
        platform_key=platform_key,
    )
    cmd = list(launch.get("command", []))
    if not cmd:
        raise ValueError("Failed to build launch command")

    result = {
        "editor": editor_key,
        "target_file": target,
        "platform": launch.get("platform"),
        "app_name": launch.get("app_name"),
        "command": cmd,
    }
    if dry_run:
        result["status"] = "planned"
        return result

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(float(timeout_seconds), 1.0),
    )
    result.update(
        {
            "status": "done" if proc.returncode == 0 else "failed",
            "returncode": int(proc.returncode),
            "stderr_tail": (proc.stderr or "")[-400:],
            "stdout_tail": (proc.stdout or "")[-200:],
        }
    )
    return result


def find_latest_video_candidate(search_dirs: List[str]) -> str:
    """Find latest modified video from search directories."""
    files: List[Path] = []
    for raw in search_dirs:
        p = Path(str(raw or "")).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            continue
        for item in p.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            files.append(item)
    if not files:
        return ""
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(files[0].resolve())


def collect_nle_master_video(
    source_video: str,
    output_dir: str,
    output_name: str = "final.mp4",
    copy_mode: str = "copy",
) -> Dict:
    """Import external NLE master into project output directory."""
    src = Path(str(source_video or "")).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise ValueError(f"源视频不存在: {src}")
    if src.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"不支持的源视频格式: {src.suffix}")

    out_root = Path(str(output_dir or "")).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    safe_name = Path(output_name or "final.mp4").name
    if not safe_name:
        safe_name = "final.mp4"
    dst = (out_root / safe_name).resolve()
    if dst == src:
        return {
            "status": "skipped",
            "mode": "same_path",
            "source_video": str(src),
            "output_video": str(dst),
            "size": src.stat().st_size,
        }

    mode = str(copy_mode or "copy").strip().lower()
    if mode == "move":
        shutil.move(str(src), str(dst))
    else:
        mode = "copy"
        shutil.copy2(str(src), str(dst))
    return {
        "status": "done",
        "mode": mode,
        "source_video": str(src),
        "output_video": str(dst),
        "size": dst.stat().st_size if dst.exists() else 0,
    }


def generate_edl(clips: List[TimelineClip], output_path: str, title: str = "VIDEOEDITOR", fps: int = 30) -> None:
    """Generate CMX3600 EDL file."""
    lines = [
        f"TITLE: {_safe_edl_title(title)}",
        "FCM: NON-DROP FRAME",
        "",
    ]
    for i, clip in enumerate(clips, start=1):
        event = f"{i:03d}"
        reel = _reel_from_path(clip.file_path)
        src_in = _sec_to_timecode(clip.source_start, fps)
        src_out = _sec_to_timecode(clip.source_end, fps)
        rec_in = _sec_to_timecode(clip.timeline_start, fps)
        rec_out = _sec_to_timecode(clip.timeline_end, fps)
        lines.append(f"{event}  {reel:<8} V     C        {src_in} {src_out} {rec_in} {rec_out}")
        lines.append(f"* FROM CLIP NAME: {Path(clip.file_path).name}")
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_fcpxml(clips: List[TimelineClip], output_path: str, title: str = "VideoEditer", fps: int = 30) -> None:
    """Generate a minimal FCPXML timeline."""
    root = Element("fcpxml", {"version": "1.10"})
    resources = SubElement(root, "resources")
    format_id = "r_format_1"
    SubElement(
        resources,
        "format",
        {
            "id": format_id,
            "name": f"FFVideoFormat{_safe_resolution_label(clips)}",
            "frameDuration": f"1/{int(fps)}s",
            "width": "1080",
            "height": "1920",
        },
    )

    asset_ids = {}
    for idx, clip in enumerate(clips, start=1):
        p = str(Path(clip.file_path).resolve())
        if p in asset_ids:
            continue
        aid = f"r_asset_{idx}"
        asset_ids[p] = aid
        SubElement(
            resources,
            "asset",
            {
                "id": aid,
                "name": Path(p).name,
                "src": Path(p).resolve().as_uri(),
                "start": "0s",
                "duration": _seconds_to_fcpx_time(clip.source_end, fps),
                "hasVideo": "1",
                "hasAudio": "1",
                "format": format_id,
            },
        )

    library = SubElement(root, "library")
    event = SubElement(library, "event", {"name": "VideoEditer"})
    project = SubElement(event, "project", {"name": title})
    sequence = SubElement(
        project,
        "sequence",
        {
            "format": format_id,
            "duration": _seconds_to_fcpx_time(clips[-1].timeline_end, fps),
            "tcStart": "0s",
            "tcFormat": "NDF",
        },
    )
    spine = SubElement(sequence, "spine")
    for clip in clips:
        SubElement(
            spine,
            "asset-clip",
            {
                "name": Path(clip.file_path).name,
                "ref": asset_ids[str(Path(clip.file_path).resolve())],
                "offset": _seconds_to_fcpx_time(clip.timeline_start, fps),
                "start": _seconds_to_fcpx_time(clip.source_start, fps),
                "duration": _seconds_to_fcpx_time(clip.source_end - clip.source_start, fps),
            },
        )
    ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)


def _resolve_material_path(video_id: str, materials: Dict) -> str:
    if Path(video_id).exists():
        return str(Path(video_id).resolve())
    item = materials.get(video_id, {}) if isinstance(materials, dict) else {}
    path = str(item.get("path") or "").strip()
    if path and Path(path).exists():
        return str(Path(path).resolve())
    nested = item.get("analysis", {}).get("metadata", {}).get("path") if isinstance(item, dict) else ""
    if nested and Path(nested).exists():
        return str(Path(nested).resolve())
    return ""


def _reel_from_path(path: str) -> str:
    stem = Path(path).stem.upper()
    cleaned = "".join(ch for ch in stem if ch.isalnum())
    return (cleaned or "AX")[:8]


def _sec_to_timecode(seconds: float, fps: int) -> str:
    total_frames = max(int(round(float(seconds) * int(fps))), 0)
    ff = total_frames % fps
    total_seconds = total_frames // fps
    ss = total_seconds % 60
    total_minutes = total_seconds // 60
    mm = total_minutes % 60
    hh = total_minutes // 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def _seconds_to_fcpx_time(seconds: float, fps: int) -> str:
    frames = max(int(round(float(seconds) * int(fps))), 0)
    return f"{frames}/{int(fps)}s"


def _safe_name(text: str) -> str:
    out = []
    for ch in str(text or "").strip():
        if ch.isalnum() or ch in {"_", "-", "."}:
            out.append(ch)
        elif ch in {" ", "/"}:
            out.append("_")
    cleaned = "".join(out).strip("._")
    return cleaned[:80] or "VideoEditer"


def _safe_edl_title(text: str) -> str:
    return _safe_name(text).upper()[:72]


def _safe_resolution_label(clips: List[TimelineClip]) -> str:
    return "1080p30"


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)
