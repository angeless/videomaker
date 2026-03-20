"""Platform-specific export presets and ffmpeg export jobs."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import json
import math
import subprocess


@dataclass(frozen=True)
class ExportProfile:
    """Target platform export spec."""

    platform_id: str
    name: str
    width: int
    height: int
    fps: int
    video_bitrate: str
    audio_bitrate: str
    max_duration_s: int


EXPORT_PROFILES: Dict[str, ExportProfile] = {
    # 用户指定的基础模板
    "tiktok": ExportProfile("tiktok", "TikTok短视频 9:16", 1080, 1920, 30, "10M", "192k", 600),
    "wechat_short": ExportProfile("wechat_short", "微信短视频 9:16", 1080, 1920, 30, "10M", "192k", 180),
    "douyin": ExportProfile("douyin", "抖音短视频 9:16", 1080, 1920, 30, "12M", "192k", 180),
    "xiaohongshu": ExportProfile("xiaohongshu", "小红书短视频 9:16", 1080, 1920, 30, "10M", "192k", 300),
    "wechat_mp": ExportProfile("wechat_mp", "微信公众号视频 16:9", 1920, 1080, 30, "10M", "192k", 1800),
    "bilibili": ExportProfile("bilibili", "B站视频 16:9", 1920, 1080, 30, "16M", "256k", 14400),
    "youtube": ExportProfile("youtube", "YouTube视频 16:9", 1920, 1080, 30, "16M", "192k", 43200),
    # 兼容扩展模板
    "ixigua": ExportProfile("ixigua", "西瓜视频 16:9", 1920, 1080, 30, "12M", "192k", 43200),
    "wechat_channels": ExportProfile("wechat_channels", "微信号（视频号）9:16", 1080, 1920, 30, "10M", "192k", 180),
    "instagram": ExportProfile("instagram", "Instagram Reels 9:16", 1080, 1920, 30, "10M", "192k", 90),
    "twitter": ExportProfile("twitter", "Twitter/X 视频 16:9", 1920, 1080, 30, "8M", "192k", 140),
    "threads": ExportProfile("threads", "Threads 视频 9:16", 1080, 1920, 30, "8M", "192k", 300),
    "facebook": ExportProfile("facebook", "Facebook 视频 16:9", 1920, 1080, 30, "10M", "192k", 14400),
    "blog": ExportProfile("blog", "Blog 视频 16:9", 1920, 1080, 30, "10M", "192k", 43200),
    "youtube_shorts": ExportProfile("youtube_shorts", "YouTube Shorts 9:16", 1080, 1920, 30, "12M", "192k", 180),
    "instagram_reels": ExportProfile("instagram_reels", "Instagram Reels 9:16", 1080, 1920, 30, "10M", "192k", 90),
}


PLATFORM_ALIASES: Dict[str, str] = {
    # 中文名称
    "tiktok短视频": "tiktok",
    "微信短视频": "wechat_short",
    "微信号": "wechat_channels",
    "视频号": "wechat_channels",
    "抖音短视频": "douyin",
    "西瓜视频": "ixigua",
    "西瓜": "ixigua",
    "小红书短视频": "xiaohongshu",
    "微信公众号": "wechat_mp",
    "公众号视频": "wechat_mp",
    "b站视频": "bilibili",
    "哔哩哔哩视频": "bilibili",
    "youtube视频": "youtube",
    "threads视频": "threads",
    "instagram视频": "instagram",
    "twitter视频": "twitter",
    "facebook视频": "facebook",
    "博客视频": "blog",
    # 常见英文别名
    "wechat": "wechat_short",
    "wechat_video": "wechat_short",
    "wechat_channels": "wechat_channels",
    "wechat_channel": "wechat_channels",
    "wechat_official_account": "wechat_mp",
    "official_account": "wechat_mp",
    "bilibili_video": "bilibili",
    "yt": "youtube",
    "youtube_video": "youtube",
    "xigua": "ixigua",
    "ixigua_video": "ixigua",
    "insta": "instagram",
    "ig": "instagram",
    "x": "twitter",
    "twitter_x": "twitter",
    "thread": "threads",
    "fb": "facebook",
    "facebook_video": "facebook",
}

PLATFORM_NOTES: Dict[str, str] = {
    "tiktok": "竖屏 9:16，偏短内容分发。",
    "wechat_short": "微信视频号短视频，建议短时长竖屏。",
    "wechat_channels": "微信号（视频号）发布，建议竖屏短时长。",
    "douyin": "抖音竖屏分发，建议节奏快、封面清晰。",
    "ixigua": "西瓜视频偏横屏中长内容，建议信息密度高。",
    "xiaohongshu": "小红书竖屏内容，封面与前 3 秒抓人。",
    "wechat_mp": "公众号长视频，常见 16:9 横屏。",
    "bilibili": "B站投稿常见 1080p 横屏，高码率更稳。",
    "youtube": "YouTube 长视频与教程类常见 16:9。",
    "instagram": "Instagram Reels 竖屏，建议强节奏与短句字幕。",
    "twitter": "Twitter/X 视频建议控制时长，首句信息要强。",
    "threads": "Threads 更偏短帖互动，标题需直接。",
    "facebook": "Facebook 支持长短视频，封面与标题同样重要。",
    "blog": "博客平台可挂载视频，建议同时提供图文摘要。",
    "youtube_shorts": "YouTube Shorts 竖屏短内容。",
    "instagram_reels": "Instagram Reels 竖屏短视频。",
}

EXPORT_CODEC_SPEC = {
    "container": "mp4",
    "video_codec": "h264",
    "audio_codec": "aac",
    "pixel_format": "yuv420p",
}


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _coerce_export_profile(platform_id: str, raw) -> ExportProfile:
    """Coerce dict-like payload into ExportProfile."""
    if isinstance(raw, ExportProfile):
        if platform_id and raw.platform_id != platform_id:
            return ExportProfile(
                platform_id=platform_id,
                name=raw.name,
                width=raw.width,
                height=raw.height,
                fps=raw.fps,
                video_bitrate=raw.video_bitrate,
                audio_bitrate=raw.audio_bitrate,
                max_duration_s=raw.max_duration_s,
            )
        return raw
    if not isinstance(raw, dict):
        raise ValueError("profile payload must be dict or ExportProfile")
    pid = str(platform_id or raw.get("platform_id") or "").strip().lower()
    if not pid:
        raise ValueError("profile_id is required")
    name = str(raw.get("name") or pid).strip() or pid
    width = max(_to_int(raw.get("width", 1080), 1080), 16)
    height = max(_to_int(raw.get("height", 1920), 1920), 16)
    fps = max(_to_int(raw.get("fps", 30), 30), 1)
    video_bitrate = str(raw.get("video_bitrate") or "10M").strip() or "10M"
    audio_bitrate = str(raw.get("audio_bitrate") or "192k").strip() or "192k"
    max_duration_s = max(_to_int(raw.get("max_duration_s", 180), 180), 1)
    return ExportProfile(
        platform_id=pid,
        name=name,
        width=width,
        height=height,
        fps=fps,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        max_duration_s=max_duration_s,
    )


def resolve_export_profiles(profile_overrides: Optional[Dict] = None) -> Dict[str, ExportProfile]:
    """Merge built-in profiles with optional override/custom profiles."""
    profiles: Dict[str, ExportProfile] = dict(EXPORT_PROFILES)
    if not isinstance(profile_overrides, dict):
        return profiles
    for key, value in profile_overrides.items():
        pid = str(key or "").strip().lower()
        if not pid and isinstance(value, dict):
            pid = str(value.get("platform_id") or "").strip().lower()
        if not pid:
            continue
        try:
            profiles[pid] = _coerce_export_profile(pid, value)
        except Exception:
            continue
    return profiles


def list_export_profiles(profile_overrides: Optional[Dict] = None) -> List[Dict]:
    """List built-in and optional custom profiles."""
    profiles = resolve_export_profiles(profile_overrides)
    return [asdict(profile) for profile in profiles.values()]


def _safe_ratio(width: Optional[int], height: Optional[int]) -> Optional[float]:
    if width is None or height is None:
        return None
    if int(width) <= 0 or int(height) <= 0:
        return None
    return float(width) / float(height)


def _ratio_label(width: Optional[int], height: Optional[int]) -> str:
    if width is None or height is None:
        return ""
    w = int(width)
    h = int(height)
    if w <= 0 or h <= 0:
        return ""
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


def _parse_fps(value) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if "/" in text:
            left, right = text.split("/", 1)
            den = float(right)
            if den == 0:
                return None
            fps = float(left) / den
        else:
            fps = float(text)
        if fps <= 0:
            return None
        return fps
    except Exception:
        return None


def _platform_aliases_for(platform_id: str) -> List[str]:
    out = []
    for alias, target in PLATFORM_ALIASES.items():
        if target == platform_id:
            out.append(alias)
    return sorted(out)


def list_export_specs(profile_overrides: Optional[Dict] = None) -> List[Dict]:
    """List export specs with technical codec/container details."""
    profiles = resolve_export_profiles(profile_overrides)
    custom_ids = set(profile_overrides.keys()) if isinstance(profile_overrides, dict) else set()
    out: List[Dict] = []
    for profile in profiles.values():
        ratio = _safe_ratio(profile.width, profile.height)
        out.append(
            {
                **asdict(profile),
                **EXPORT_CODEC_SPEC,
                "aspect_ratio": round(ratio, 6) if ratio is not None else None,
                "aspect_ratio_label": _ratio_label(profile.width, profile.height),
                "aliases": _platform_aliases_for(profile.platform_id),
                "is_custom": profile.platform_id in custom_ids,
                "note": PLATFORM_NOTES.get(profile.platform_id, ""),
            }
        )
    return out


def probe_video_meta(input_video: str, ffprobe_bin: str = "ffprobe") -> Optional[Dict]:
    """Probe source video meta. Returns None on failure."""
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,r_frame_rate,avg_frame_rate",
        "-of",
        "json",
        input_video,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            return None
        payload = json.loads(proc.stdout or "{}")
        streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
        video_stream = next((s for s in streams if str(s.get("codec_type", "")).lower() == "video"), None)
        audio_streams = [s for s in streams if str(s.get("codec_type", "")).lower() == "audio"]
        if not isinstance(video_stream, dict):
            return None

        width = _to_int(video_stream.get("width"), 0)
        height = _to_int(video_stream.get("height"), 0)
        width = width if width > 0 else None
        height = height if height > 0 else None

        fps = _parse_fps(video_stream.get("avg_frame_rate"))
        if fps is None:
            fps = _parse_fps(video_stream.get("r_frame_rate"))

        duration = None
        format_payload = payload.get("format")
        if isinstance(format_payload, dict):
            raw_duration = format_payload.get("duration")
            try:
                parsed_duration = float(raw_duration)
                if parsed_duration > 0:
                    duration = parsed_duration
            except Exception:
                duration = None

        ratio = _safe_ratio(width, height)
        return {
            "path": str(input_video),
            "duration_s": round(float(duration), 3) if duration is not None else None,
            "width": width,
            "height": height,
            "fps": round(float(fps), 3) if fps is not None else None,
            "aspect_ratio": round(float(ratio), 6) if ratio is not None else None,
            "aspect_ratio_label": _ratio_label(width, height),
            "has_audio_stream": len(audio_streams) > 0,
            "audio_streams": len(audio_streams),
        }
    except Exception:
        return None


def build_ffmpeg_export_cmd(
    input_video: str,
    output_video: str,
    platform_id: str,
    quality: str = "high",
    ffmpeg_bin: str = "ffmpeg",
    clip_duration_s: Optional[float] = None,
    profile_map: Optional[Dict[str, ExportProfile]] = None,
) -> List[str]:
    """
    Build an ffmpeg command for platform export.

    The caller executes this command in orchestration code.
    """
    profiles = profile_map if isinstance(profile_map, dict) else EXPORT_PROFILES
    profile = profiles.get(platform_id)
    if not profile:
        raise ValueError(f"Unsupported platform profile: {platform_id}")

    crf_by_quality = {
        "premium": 16,
        "high": 18,
        "medium": 22,
        "draft": 28,
    }
    crf = crf_by_quality.get(str(quality or "high").lower(), 18)
    vf = (
        f"scale={profile.width}:{profile.height}:force_original_aspect_ratio=decrease,"
        f"pad={profile.width}:{profile.height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={profile.fps}"
    )

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        input_video,
    ]
    if clip_duration_s is not None:
        cmd.extend(["-t", str(max(float(clip_duration_s), 0.1))])
    cmd.extend([
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-preset",
        "slow",
        "-b:v",
        profile.video_bitrate,
        "-c:a",
        "aac",
        "-b:a",
        profile.audio_bitrate,
        "-movflags",
        "+faststart",
        "-pix_fmt",
        "yuv420p",
        output_video,
    ])
    return cmd


def probe_video_duration(input_video: str, ffprobe_bin: str = "ffprobe") -> Optional[float]:
    """Probe source video duration in seconds. Returns None on failure."""
    meta = probe_video_meta(input_video, ffprobe_bin=ffprobe_bin)
    if not isinstance(meta, dict):
        return None
    duration = meta.get("duration_s")
    try:
        value = float(duration)
        if value > 0:
            return value
    except Exception:
        return None
    return None


def parse_platform_ids(platforms: Iterable[str], profile_map: Optional[Dict[str, ExportProfile]] = None) -> List[str]:
    """Normalize platform ids and keep declaration order."""
    profiles = profile_map if isinstance(profile_map, dict) else EXPORT_PROFILES
    out: List[str] = []
    for item in platforms:
        pid = str(item or "").strip().lower()
        if not pid:
            continue
        pid = PLATFORM_ALIASES.get(pid, pid)
        if pid not in profiles:
            continue
        if pid not in out:
            out.append(pid)
    return out


def build_export_plan(
    input_video: str,
    output_dir: str,
    platform_ids: Iterable[str],
    quality: str = "high",
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    strict_duration_limit: bool = True,
    profile_overrides: Optional[Dict] = None,
) -> Dict:
    """Build a serializable export plan with one job per platform."""
    profiles = resolve_export_profiles(profile_overrides)
    platforms = parse_platform_ids(platform_ids, profile_map=profiles)
    if not platforms:
        raise ValueError("No valid platform ids provided")

    in_path = Path(input_video).resolve()
    out_root = Path(output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    source_duration_s = probe_video_duration(str(in_path), ffprobe_bin=ffprobe_bin)

    jobs = []
    for pid in platforms:
        profile = profiles[pid]
        suffix = f"{profile.width}x{profile.height}_{profile.fps}fps"
        out_path = out_root / f"{pid}_{suffix}.mp4"
        effective_duration_s = source_duration_s
        trim_applied = False
        if strict_duration_limit and source_duration_s is not None and source_duration_s > float(profile.max_duration_s):
            effective_duration_s = float(profile.max_duration_s)
            trim_applied = True
        cmd = build_ffmpeg_export_cmd(
            input_video=str(in_path),
            output_video=str(out_path),
            platform_id=pid,
            quality=quality,
            ffmpeg_bin=ffmpeg_bin,
            clip_duration_s=effective_duration_s if trim_applied else None,
            profile_map=profiles,
        )
        jobs.append(
            {
                "platform_id": pid,
                "profile": asdict(profile),
                "input_video": str(in_path),
                "output_video": str(out_path),
                "quality": str(quality or "high").lower(),
                "source_duration_s": round(float(source_duration_s), 3) if source_duration_s is not None else None,
                "effective_duration_s": round(float(effective_duration_s), 3) if effective_duration_s is not None else None,
                "trim_applied": trim_applied,
                "command": cmd,
            }
        )

    return {
        "input_video": str(in_path),
        "output_dir": str(out_root),
        "quality": str(quality or "high").lower(),
        "strict_duration_limit": bool(strict_duration_limit),
        "source_duration_s": round(float(source_duration_s), 3) if source_duration_s is not None else None,
        "jobs": jobs,
    }


def run_export_plan(plan: Dict, timeout_seconds: float = 3600) -> Dict:
    """Execute export jobs sequentially and return status summary."""
    jobs = list(plan.get("jobs", []))
    if not jobs:
        raise ValueError("Empty export plan")

    results = []
    success = 0
    failed = 0
    for idx, job in enumerate(jobs, start=1):
        cmd = list(job.get("command", []))
        if not cmd:
            results.append({"index": idx, "status": "failed", "error": "Missing command", **job})
            failed += 1
            continue
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(float(timeout_seconds), 1.0),
            )
            ok = proc.returncode == 0
            result = {
                "index": idx,
                "status": "done" if ok else "failed",
                "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "")[-400:],
                "stdout_tail": (proc.stdout or "")[-200:],
                **job,
            }
            results.append(result)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as exc:
            results.append({"index": idx, "status": "failed", "error": str(exc), **job})
            failed += 1

    return {
        "total": len(jobs),
        "success": success,
        "failed": failed,
        "results": results,
    }


def validate_source_for_export(
    input_video: str,
    platform_ids: Iterable[str],
    strict_duration_limit: bool = True,
    ffprobe_bin: str = "ffprobe",
    profile_overrides: Optional[Dict] = None,
) -> Dict:
    """Validate source meta against platform export specs."""
    profiles = resolve_export_profiles(profile_overrides)
    platforms = parse_platform_ids(platform_ids, profile_map=profiles)
    if not platforms:
        raise ValueError("No valid platform ids provided")

    in_path = Path(input_video).resolve()
    source_meta = probe_video_meta(str(in_path), ffprobe_bin=ffprobe_bin) or {}
    src_duration = source_meta.get("duration_s")
    src_width = source_meta.get("width")
    src_height = source_meta.get("height")
    src_ratio = source_meta.get("aspect_ratio")
    src_fps = source_meta.get("fps")
    source_meta_known = bool(source_meta)

    checks = []
    transform_count = 0
    strict_trim_count = 0
    for pid in platforms:
        profile = profiles[pid]
        target_ratio = _safe_ratio(profile.width, profile.height)

        duration_exceeded = (
            src_duration is not None and float(src_duration) > float(profile.max_duration_s)
        )
        trim_required = bool(strict_duration_limit and duration_exceeded)
        if trim_required:
            strict_trim_count += 1

        upscale_required = (
            src_width is not None
            and src_height is not None
            and (int(src_width) < int(profile.width) or int(src_height) < int(profile.height))
        )
        aspect_transform_required = (
            src_ratio is not None
            and target_ratio is not None
            and abs(float(src_ratio) - float(target_ratio)) > 0.01
        )
        fps_convert_required = (
            src_fps is not None and abs(float(src_fps) - float(profile.fps)) > 0.1
        )

        operations = []
        warnings = []
        if trim_required:
            operations.append("trim_to_max_duration")
        if aspect_transform_required:
            operations.append("scale_pad_to_target_aspect")
        if upscale_required:
            operations.append("upscale_to_target_resolution")
            warnings.append("源分辨率低于目标分辨率，导出将发生上采样。")
        if fps_convert_required:
            operations.append("fps_convert")
        operations.append("transcode_h264_aac")

        if duration_exceeded and not strict_duration_limit:
            warnings.append("源时长超过平台上限，当前未启用严格时长截断。")
        if not source_meta_known:
            warnings.append("未能探测到源视频元数据，将在导出时再校验。")
        if (
            aspect_transform_required
            or upscale_required
            or fps_convert_required
            or (duration_exceeded and strict_duration_limit)
        ):
            transform_count += 1

        compliant_without_transform = (
            source_meta_known
            and (not duration_exceeded)
            and (not aspect_transform_required)
            and (not upscale_required)
            and (not fps_convert_required)
        )

        checks.append(
            {
                "platform_id": pid,
                "profile": asdict(profile),
                "target_aspect_ratio": round(float(target_ratio), 6) if target_ratio is not None else None,
                "target_aspect_ratio_label": _ratio_label(profile.width, profile.height),
                "source_duration_s": src_duration,
                "source_resolution": (
                    f"{int(src_width)}x{int(src_height)}"
                    if src_width is not None and src_height is not None
                    else None
                ),
                "source_fps": src_fps,
                "duration_exceeded": duration_exceeded,
                "trim_required": trim_required,
                "strict_duration_limit": bool(strict_duration_limit),
                "upscale_required": upscale_required,
                "aspect_transform_required": aspect_transform_required,
                "fps_convert_required": fps_convert_required,
                "estimated_output_duration_s": (
                    round(min(float(src_duration), float(profile.max_duration_s)), 3)
                    if src_duration is not None and strict_duration_limit
                    else src_duration
                ),
                "compliant_without_transform": compliant_without_transform,
                "operations": operations,
                "warnings": warnings,
            }
        )

    return {
        "input_video": str(in_path),
        "source_meta": source_meta if source_meta_known else None,
        "strict_duration_limit": bool(strict_duration_limit),
        "platform_ids": platforms,
        "checks": checks,
        "summary": {
            "total_platforms": len(checks),
            "source_meta_known": source_meta_known,
            "transform_required_platforms": transform_count,
            "strict_trim_required_platforms": strict_trim_count,
        },
    }
