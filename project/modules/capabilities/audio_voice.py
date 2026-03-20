"""Music and voice planning utilities."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


AUDIO_FILE_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}

MOOD_TRACK_KEYWORDS = {
    "travel_story": ["travel", "story", "vlog", "adventure", "indie", "uplift", "journey"],
    "cinematic": ["cinematic", "epic", "orchestral", "score", "trailer", "drama"],
    "clean_vlog": ["clean", "lofi", "chill", "ambient", "light", "minimal"],
}


@dataclass
class VoiceoverSegment:
    """Timeline segment for synthesized narration."""

    index: int
    start: float
    end: float
    text: str


def estimate_voiceover_segments(
    subtitles: Iterable[Dict],
    words_per_minute: int = 170,
) -> List[VoiceoverSegment]:
    """
    Create voiceover segments from subtitles.

    If subtitle timestamps are missing, duration is estimated from text length.
    """
    wpm = max(int(words_per_minute), 80)
    seconds_per_word = 60.0 / wpm
    cursor = 0.0
    out: List[VoiceoverSegment] = []

    for idx, sub in enumerate(subtitles):
        text = str(sub.get("cn_text") or sub.get("text") or "").strip()
        if not text:
            continue
        start = sub.get("start_time")
        end = sub.get("end_time")
        if start is None or end is None or float(end) <= float(start):
            word_count = max(len(text) // 2, 1)
            duration = max(word_count * seconds_per_word, 0.6)
            start = cursor
            end = cursor + duration
        start_f = max(float(start), 0.0)
        end_f = max(float(end), start_f + 0.1)
        cursor = end_f
        out.append(VoiceoverSegment(index=idx, start=round(start_f, 3), end=round(end_f, 3), text=text))

    return out


def build_music_plan(total_duration_s: float, mood: str = "travel_story") -> Dict:
    """Build a simple BGM strategy payload."""
    mood_key = str(mood or "travel_story").lower()
    style_map = {
        "travel_story": {"genre": "indie_pop", "bpm": "96-112", "energy_curve": "low-mid-high"},
        "cinematic": {"genre": "orchestral_hybrid", "bpm": "78-96", "energy_curve": "low-high"},
        "clean_vlog": {"genre": "lofi_pop", "bpm": "88-105", "energy_curve": "mid-mid"},
    }
    style = style_map.get(mood_key, style_map["travel_story"])
    return {
        "mood": mood_key,
        "duration_s": round(max(float(total_duration_s), 1.0), 2),
        "genre": style["genre"],
        "bpm_range": style["bpm"],
        "energy_curve": style["energy_curve"],
        "voice_clone_provider": "elevenlabs_compatible",
    }


def build_audio_capability_payload(script: Dict, mood: str = "travel_story") -> Dict:
    """Return combined voice + music plan payload."""
    subtitles = script.get("subtitles", [])
    clips = script.get("clips", [])
    duration = sum(max(float(c.get("duration", 0.0)), 0.0) for c in clips) or 1.0
    voice = [asdict(s) for s in estimate_voiceover_segments(subtitles)]
    return {
        "voiceover_segments": voice,
        "music_plan": build_music_plan(duration, mood=mood),
    }


def build_elevenlabs_tts_payload(text: str, model_id: str = "eleven_multilingual_v2", stability: float = 0.5, similarity_boost: float = 0.75) -> Dict:
    """Build ElevenLabs-compatible TTS payload."""
    return {
        "text": str(text or "").strip(),
        "model_id": str(model_id or "eleven_multilingual_v2").strip() or "eleven_multilingual_v2",
        "voice_settings": {
            "stability": max(min(float(stability), 1.0), 0.0),
            "similarity_boost": max(min(float(similarity_boost), 1.0), 0.0),
        },
    }


def _fetch_elevenlabs_tts_audio(
    *,
    text: str,
    voice_id: str,
    api_key: str,
    model_id: str = "eleven_multilingual_v2",
    output_format: str = "mp3_44100_128",
    timeout_seconds: float = 90.0,
) -> bytes:
    """Call ElevenLabs TTS and return audio bytes."""
    endpoint = "https://api.elevenlabs.io/v1/text-to-speech"
    voice = urllib.parse.quote(str(voice_id or "").strip(), safe="")
    fmt = urllib.parse.quote(str(output_format or "mp3_44100_128").strip(), safe="")
    url = f"{endpoint}/{voice}?output_format={fmt}"
    payload = build_elevenlabs_tts_payload(text=text, model_id=model_id)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": str(api_key or "").strip(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=max(float(timeout_seconds), 1.0)) as resp:
            audio = resp.read()
            if not audio:
                raise ValueError("ElevenLabs 返回空音频")
            return audio
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = (exc.read() or b"").decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        tail = body[-300:] if body else ""
        raise RuntimeError(f"ElevenLabs 请求失败 HTTP {exc.code}: {tail or exc.reason}") from exc


def synthesize_voiceover_segments(
    voiceover_segments: Iterable[Dict],
    output_dir: str,
    *,
    provider: str = "elevenlabs",
    voice_id: str = "",
    api_key: str = "",
    model_id: str = "eleven_multilingual_v2",
    output_format: str = "mp3_44100_128",
    timeout_seconds: float = 90.0,
    dry_run: bool = False,
) -> Dict:
    """
    Synthesize voiceover clips from timeline segments.

    In dry-run mode no network call is made; only output paths are planned.
    """
    provider_key = str(provider or "elevenlabs").strip().lower()
    if provider_key not in {"elevenlabs", "elevenlabs_compatible"}:
        raise ValueError(f"暂不支持的配音 provider: {provider_key}")
    voice_key = str(voice_id or "").strip()
    if not voice_key:
        raise ValueError("voice_id 不能为空")
    key = str(api_key or "").strip() or os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not dry_run and not key:
        raise ValueError("缺少 ELEVENLABS_API_KEY（或请求体 api_key）")

    out_root = Path(output_dir).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    items = []
    for idx, seg in enumerate(voiceover_segments, start=1):
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start", 0.0) or 0.0)
        end = float(seg.get("end", start + 1.0) or start + 1.0)
        if end <= start:
            end = start + 0.1
        fname = f"voiceover_{idx:03d}_{int(max(start, 0.0) * 1000):07d}.mp3"
        out_path = out_root / fname
        item = {
            "index": idx,
            "start": round(max(start, 0.0), 3),
            "end": round(end, 3),
            "duration_s": round(end - max(start, 0.0), 3),
            "text": text,
            "output_audio": str(out_path),
        }
        if dry_run:
            item["status"] = "planned"
            items.append(item)
            continue
        audio = _fetch_elevenlabs_tts_audio(
            text=text,
            voice_id=voice_key,
            api_key=key,
            model_id=model_id,
            output_format=output_format,
            timeout_seconds=timeout_seconds,
        )
        out_path.write_bytes(audio)
        item["status"] = "done"
        item["size"] = out_path.stat().st_size if out_path.exists() else 0
        items.append(item)

    return {
        "provider": provider_key,
        "voice_id": voice_key,
        "model_id": str(model_id or "eleven_multilingual_v2"),
        "output_dir": str(out_root),
        "dry_run": bool(dry_run),
        "total_segments": len(items),
        "generated_files": [x["output_audio"] for x in items if x.get("status") == "done"],
        "segments": items,
    }


def _probe_has_audio_stream(input_video: str, ffprobe_bin: str = "ffprobe") -> bool:
    """Check whether input video has an audio stream."""
    cmd = [
        ffprobe_bin,
        "-v",
        "quiet",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default",
        input_video,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            return False
        return "codec_type=audio" in (proc.stdout or "")
    except Exception:
        return False


def _probe_media_duration(input_media: str, ffprobe_bin: str = "ffprobe") -> Optional[float]:
    """Probe media duration in seconds; return None on failure."""
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        input_media,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            return None
        payload = json.loads(proc.stdout or "{}")
        raw = payload.get("format", {}).get("duration")
        if raw is None:
            return None
        value = float(raw)
        if value <= 0:
            return None
        return value
    except Exception:
        return None


def pick_bgm_track(
    *,
    mood: str = "travel_story",
    target_duration_s: Optional[float] = None,
    library_dirs: Optional[Iterable[str]] = None,
    ffprobe_bin: str = "ffprobe",
    max_candidates: int = 40,
) -> Dict:
    """
    Pick one BGM track from local libraries using mood keywords.

    Scoring:
    - filename keyword hit (mood-aware)
    - optional duration fit against target_duration_s
    """
    mood_key = str(mood or "travel_story").strip().lower() or "travel_story"
    keywords = set(MOOD_TRACK_KEYWORDS.get(mood_key, []))
    keywords.update(k for k in mood_key.replace("-", "_").split("_") if k)

    unique_dirs: List[Path] = []
    seen = set()
    for raw in (library_dirs or []):
        raw_text = str(raw or "").strip()
        if not raw_text:
            continue
        p = Path(raw_text).expanduser()
        try:
            resolved = p.resolve()
        except Exception:
            continue
        key = str(resolved)
        if key in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(key)
        unique_dirs.append(resolved)

    if not unique_dirs:
        return {
            "status": "empty_library",
            "mood": mood_key,
            "target_duration_s": float(target_duration_s) if target_duration_s is not None else None,
            "library_dirs": [],
            "total_tracks": 0,
            "selected_track": "",
            "candidates": [],
        }

    tracks: List[Path] = []
    for root in unique_dirs:
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in AUDIO_FILE_EXTENSIONS:
                continue
            tracks.append(file_path)

    if not tracks:
        return {
            "status": "not_found",
            "mood": mood_key,
            "target_duration_s": float(target_duration_s) if target_duration_s is not None else None,
            "library_dirs": [str(x) for x in unique_dirs],
            "total_tracks": 0,
            "selected_track": "",
            "candidates": [],
        }

    target = None
    try:
        if target_duration_s is not None:
            target = max(float(target_duration_s), 1.0)
    except Exception:
        target = None

    scored = []
    for path in tracks:
        stem = path.stem.lower()
        score = 0.0
        for kw in keywords:
            if kw and kw in stem:
                score += 2.0
        if "instrumental" in stem or "bgm" in stem:
            score += 1.0
        duration = _probe_media_duration(str(path), ffprobe_bin=ffprobe_bin)
        if target is not None and duration is not None:
            # Prefer tracks at least as long as target; otherwise prefer closer duration.
            if duration >= target:
                score += 3.0
                score += max(min((duration - target) / max(target, 1.0), 1.0), 0.0)
            else:
                score += max(duration / target, 0.0)
        elif duration is not None:
            score += min(duration / 180.0, 1.0)
        scored.append(
            {
                "path": str(path),
                "filename": path.name,
                "duration_s": round(float(duration), 3) if duration is not None else None,
                "score": round(score, 3),
            }
        )

    scored.sort(key=lambda x: (x["score"], x["duration_s"] or 0.0, x["path"]), reverse=True)
    top = scored[: max(int(max_candidates), 1)]
    selected = top[0] if top else None
    return {
        "status": "selected" if selected else "not_found",
        "mood": mood_key,
        "target_duration_s": target,
        "library_dirs": [str(x) for x in unique_dirs],
        "total_tracks": len(scored),
        "selected_track": selected.get("path", "") if selected else "",
        "selected_duration_s": selected.get("duration_s") if selected else None,
        "candidates": top,
    }


def _sanitize_audio_filename(name: str, fallback_prefix: str = "bgm_track") -> str:
    raw = str(name or "").strip()
    if raw:
        raw = Path(raw).name
    if not raw:
        raw = f"{fallback_prefix}.mp3"
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw).strip("._-")
    if not stem:
        stem = fallback_prefix
    if "." not in stem:
        stem += ".mp3"
    return stem[:128]


def _url_sha1(url: str) -> str:
    return hashlib.sha1(str(url or "").encode("utf-8")).hexdigest()


def _pick_extension_from_url_or_title(url: str, title: str = "") -> str:
    """Infer safe audio extension from URL/title, fallback .mp3."""
    allow = AUDIO_FILE_EXTENSIONS
    url_path = urllib.parse.urlparse(str(url or "")).path
    ext = Path(url_path).suffix.lower()
    if ext in allow:
        return ext
    title_ext = Path(str(title or "")).suffix.lower()
    if title_ext in allow:
        return title_ext
    return ".mp3"


def _is_cache_file_fresh(path: Path, max_age_seconds: float) -> bool:
    """Check cache freshness by mtime."""
    try:
        age = max(time.time() - float(path.stat().st_mtime), 0.0)
        return age <= max(float(max_age_seconds), 0.0)
    except Exception:
        return False


def _validate_remote_endpoint(endpoint: str) -> str:
    """Validate that an endpoint URL is a safe external HTTPS/HTTP URL (no SSRF)."""
    url = str(endpoint or "").strip()
    if not url:
        raise ValueError("endpoint URL 不能为空")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"endpoint URL 必须使用 http 或 https 协议，当前: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("endpoint URL 缺少有效主机名")
    # Block private/internal network ranges to prevent SSRF
    _blocked = (
        "localhost", "127.0.0.1", "0.0.0.0", "[::1]", "[::]",
        "metadata.google.internal", "169.254.169.254",
    )
    if host in _blocked or host.startswith("10.") or host.startswith("192.168."):
        raise ValueError(f"endpoint URL 不允许指向内网地址: {host}")
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
                if 16 <= second <= 31:
                    raise ValueError(f"endpoint URL 不允许指向内网地址: {host}")
            except ValueError:
                pass
    return url


def _http_json_post(
    *,
    endpoint: str,
    payload: Dict,
    api_key: str = "",
    timeout_seconds: float = 45.0,
) -> Dict:
    """POST JSON to endpoint and parse JSON response."""
    safe_url = _validate_remote_endpoint(endpoint)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["x-api-key"] = key
    req = urllib.request.Request(
        safe_url,
        data=body,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=max(float(timeout_seconds), 1.0)) as resp:
            raw = (resp.read() or b"").decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = (exc.read() or b"").decode("utf-8", errors="ignore")
        except Exception:
            err_body = ""
        tail = err_body[-260:] if err_body else ""
        raise RuntimeError(f"远端配乐请求失败 HTTP {exc.code}: {tail or exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"远端配乐请求失败: {exc}") from exc

    try:
        data = json.loads(raw or "{}")
    except Exception as exc:
        raise RuntimeError(f"远端配乐响应不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("远端配乐响应格式非法（非对象）")
    return data


def _http_download_binary(
    *,
    url: str,
    api_key: str = "",
    timeout_seconds: float = 90.0,
) -> bytes:
    """Download binary bytes from URL."""
    safe_url = _validate_remote_endpoint(url)
    headers = {}
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["x-api-key"] = key
    req = urllib.request.Request(safe_url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=max(float(timeout_seconds), 1.0)) as resp:
            data = resp.read()
            if not data:
                raise RuntimeError("远端配乐下载为空")
            return data
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"远端配乐下载失败 HTTP {exc.code}: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"远端配乐下载失败: {exc}") from exc


def _extract_remote_track_candidates(payload: Dict) -> List[Dict]:
    """Extract track candidates from heterogeneous provider payload."""
    tracks = payload.get("tracks")
    if isinstance(tracks, list):
        return [x for x in tracks if isinstance(x, dict)]
    cands = payload.get("candidates")
    if isinstance(cands, list):
        return [x for x in cands if isinstance(x, dict)]

    single_keys = {"path", "url", "audio_url", "download_url"}
    if any(k in payload for k in single_keys):
        return [payload]
    return []


def _validate_remote_track_schema(payload: Dict) -> None:
    """
    Validate ElevenCreative-compatible schema (strict mode).

    Minimal accepted shape:
    {
      "tracks": [{"audio_url"|"download_url"|"url"|"path": "...", ...}, ...]
    }
    """
    tracks = payload.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise RuntimeError("严格模式校验失败：响应需包含非空 tracks 数组")
    for idx, item in enumerate(tracks, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"严格模式校验失败：tracks[{idx}] 不是对象")
        audio_ref = (
            str(item.get("audio_url") or "").strip()
            or str(item.get("download_url") or "").strip()
            or str(item.get("url") or "").strip()
            or str(item.get("path") or "").strip()
        )
        if not audio_ref:
            raise RuntimeError(f"严格模式校验失败：tracks[{idx}] 缺少 audio_url/download_url/url/path")


def _pick_bgm_track_remote(
    *,
    mood: str,
    target_duration_s: Optional[float],
    endpoint: str,
    api_key: str,
    max_candidates: int,
    timeout_seconds: float,
    output_dir: str,
    download_audio: bool,
    strict_schema: bool = False,
    cache_enabled: bool = True,
    force_refresh: bool = False,
    cache_max_age_seconds: float = 0.0,
) -> Dict:
    """Select BGM from an ElevenCreative-compatible HTTP API."""
    endpoint_value = str(endpoint or "").strip() or os.getenv("ELEVENCREATIVE_BGM_ENDPOINT", "").strip()
    api_key_value = str(api_key or "").strip() or os.getenv("ELEVENCREATIVE_API_KEY", "").strip()
    if not endpoint_value:
        return {
            "status": "failed",
            "provider": "elevencreative_compatible",
            "error": "缺少 bgm_endpoint（或 ELEVENCREATIVE_BGM_ENDPOINT）",
            "selected_track": "",
            "selected_url": "",
            "candidates": [],
        }

    req_payload = {
        "mood": str(mood or "travel_story").strip().lower(),
        "target_duration_s": float(target_duration_s) if target_duration_s is not None else None,
        "max_candidates": max(int(max_candidates), 1),
    }
    data = _http_json_post(
        endpoint=endpoint_value,
        payload=req_payload,
        api_key=api_key_value,
        timeout_seconds=timeout_seconds,
    )
    if bool(strict_schema):
        _validate_remote_track_schema(data)

    candidates = _extract_remote_track_candidates(data)
    normalized = []
    for item in candidates:
        path = str(item.get("path") or "").strip()
        url = str(item.get("audio_url") or item.get("download_url") or item.get("url") or "").strip()
        title = str(item.get("title") or item.get("name") or "").strip()
        try:
            score = float(item.get("score", 0.0) or 0.0)
        except Exception:
            score = 0.0
        try:
            duration = float(item.get("duration_s")) if item.get("duration_s") is not None else None
        except Exception:
            duration = None
        normalized.append(
            {
                "path": path,
                "url": url,
                "title": title,
                "score": round(score, 3),
                "duration_s": round(duration, 3) if duration is not None else None,
                "raw": item,
            }
        )

    normalized.sort(key=lambda x: (x["score"], x["duration_s"] or 0.0, x["title"], x["path"], x["url"]), reverse=True)
    selected = normalized[0] if normalized else None
    if selected is None:
        return {
            "status": "not_found",
            "provider": "elevencreative_compatible",
            "endpoint": endpoint_value,
            "selected_track": "",
            "selected_url": "",
            "candidates": [],
        }

    selected_path = ""
    selected_url = str(selected.get("url") or "").strip()
    path_value = str(selected.get("path") or "").strip()
    cache_hit = False
    download_applied = False
    cache_expired = False
    cache_max_age_seconds = max(float(cache_max_age_seconds or 0.0), 0.0)
    if path_value and Path(path_value).expanduser().exists():
        selected_path = str(Path(path_value).expanduser().resolve())
    elif selected_url and bool(download_audio):
        out_root = Path(str(output_dir or "").strip() or "./").expanduser().resolve()
        out_root.mkdir(parents=True, exist_ok=True)
        title = str(selected.get("title") or "")
        ext = _pick_extension_from_url_or_title(selected_url, title)
        key = _url_sha1(selected_url)
        fname = _sanitize_audio_filename(f"bgm_{key}{ext}", fallback_prefix="bgm_remote")
        out_path = out_root / fname
        can_use_cache = False
        if bool(cache_enabled) and out_path.exists() and out_path.stat().st_size > 0:
            if bool(force_refresh):
                cache_expired = True
            elif cache_max_age_seconds > 0:
                can_use_cache = _is_cache_file_fresh(out_path, cache_max_age_seconds)
                cache_expired = not can_use_cache
            else:
                can_use_cache = True
        if can_use_cache:
            cache_hit = True
        else:
            data_bytes = _http_download_binary(url=selected_url, api_key=api_key_value, timeout_seconds=max(timeout_seconds, 30.0))
            out_path.write_bytes(data_bytes)
            download_applied = True
            meta_path = out_root / f"{out_path.stem}.json"
            meta = {
                "source_url": selected_url,
                "title": title,
                "provider": "elevencreative_compatible",
                "saved_at": out_path.stat().st_mtime,
                "size": out_path.stat().st_size,
            }
            try:
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        selected_path = str(out_path)

    return {
        "status": "selected" if selected_path else "selected_url",
        "provider": "elevencreative_compatible",
        "endpoint": endpoint_value,
        "selected_track": selected_path,
        "selected_url": selected_url,
        "selected_title": str(selected.get("title") or ""),
        "selected_duration_s": selected.get("duration_s"),
        "download_applied": bool(download_applied),
        "cache_hit": bool(cache_hit),
        "cache_expired": bool(cache_expired),
        "force_refresh": bool(force_refresh),
        "cache_max_age_seconds": float(cache_max_age_seconds),
        "strict_schema": bool(strict_schema),
        "cache_enabled": bool(cache_enabled),
        "total_tracks": len(normalized),
        "candidates": [
            {
                "path": x["path"],
                "url": x["url"],
                "title": x["title"],
                "score": x["score"],
                "duration_s": x["duration_s"],
            }
            for x in normalized[: max(int(max_candidates), 1)]
        ],
    }


def pick_bgm(
    *,
    provider: str = "local_library",
    mood: str = "travel_story",
    target_duration_s: Optional[float] = None,
    library_dirs: Optional[Iterable[str]] = None,
    ffprobe_bin: str = "ffprobe",
    max_candidates: int = 40,
    api_key: str = "",
    endpoint: str = "",
    timeout_seconds: float = 45.0,
    output_dir: str = "",
    download_audio: bool = True,
    strict_schema: bool = False,
    cache_enabled: bool = True,
    force_refresh: bool = False,
    cache_max_age_seconds: float = 0.0,
) -> Dict:
    """
    Unified BGM picker with pluggable providers.

    Providers:
    - local_library: select from local folders.
    - elevencreative_compatible: call remote HTTP API and optionally download audio.
    """
    provider_key = str(provider or "local_library").strip().lower()
    if provider_key in {"local", "library"}:
        provider_key = "local_library"
    if provider_key in {"elevencreative", "elevencreative_api"}:
        provider_key = "elevencreative_compatible"

    if provider_key == "local_library":
        result = pick_bgm_track(
            mood=mood,
            target_duration_s=target_duration_s,
            library_dirs=library_dirs,
            ffprobe_bin=ffprobe_bin,
            max_candidates=max_candidates,
        )
        result["provider"] = provider_key
        return result

    if provider_key == "elevencreative_compatible":
        return _pick_bgm_track_remote(
            mood=mood,
            target_duration_s=target_duration_s,
            endpoint=endpoint,
            api_key=api_key,
            max_candidates=max_candidates,
            timeout_seconds=timeout_seconds,
            output_dir=output_dir,
            download_audio=download_audio,
            strict_schema=strict_schema,
            cache_enabled=cache_enabled,
            force_refresh=force_refresh,
            cache_max_age_seconds=cache_max_age_seconds,
        )

    raise ValueError(f"不支持的 BGM provider: {provider_key}")


def _ffmpeg_supports_filter(ffmpeg_bin: str, filter_name: str) -> bool:
    """Return True if ffmpeg reports the given audio/video filter."""
    cmd = [str(ffmpeg_bin or "ffmpeg"), "-hide_banner", "-filters"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            return False
        return str(filter_name or "").strip().lower() in (proc.stdout or "").lower()
    except Exception:
        return False


def _is_remote_media_url(value: str) -> bool:
    """Return True for http/https media URLs."""
    text = str(value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://")


def build_voiceover_timeline(
    synthesized_segments: Iterable[Dict],
    output_audio: str,
    *,
    ffmpeg_bin: str = "ffmpeg",
    timeout_seconds: float = 600,
    dry_run: bool = False,
) -> Dict:
    """
    Build a single narration timeline from synthesized clips.

    The timeline respects each segment's start time using adelay + amix.
    """
    valid = []
    for item in synthesized_segments:
        if not isinstance(item, dict):
            continue
        src = str(item.get("output_audio") or "").strip()
        if not src:
            continue
        start = float(item.get("start", 0.0) or 0.0)
        if not dry_run and not Path(src).exists():
            continue
        valid.append(
            {
                "output_audio": str(Path(src).expanduser().resolve()),
                "start": max(start, 0.0),
                "text": str(item.get("text") or "").strip(),
            }
        )
    valid.sort(key=lambda x: (x["start"], x["output_audio"]))
    if not valid:
        raise ValueError("没有可用的配音片段")

    out_path = Path(output_audio).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg_bin, "-y"]
    for seg in valid:
        cmd.extend(["-i", seg["output_audio"]])

    chains = []
    mix_labels = []
    for i, seg in enumerate(valid):
        delay_ms = int(round(seg["start"] * 1000))
        label = f"[s{i}]"
        chains.append(
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}{label}"
        )
        mix_labels.append(label)
    chains.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=longest:dropout_transition=0[aout]")
    filter_complex = ";".join(chains)
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[aout]",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out_path),
        ]
    )

    result = {
        "output_audio": str(out_path),
        "segments": valid,
        "total_segments": len(valid),
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
    if proc.returncode != 0:
        raise RuntimeError(result["stderr_tail"] or "旁白轨生成失败")
    return result


def mix_voiceover_to_video(
    input_video: str,
    output_video: str,
    narration_audio: str,
    *,
    bgm_audio: str = "",
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    origin_volume: float = 0.8,
    narration_volume: float = 1.0,
    bgm_volume: float = 0.25,
    bgm_loop: bool = True,
    bgm_fade_out_s: float = 2.0,
    enable_ducking: bool = True,
    ducking_threshold: float = 0.03,
    ducking_ratio: float = 8.0,
    ducking_attack_ms: float = 15.0,
    ducking_release_ms: float = 250.0,
    audio_bitrate: str = "192k",
    timeout_seconds: float = 900,
    dry_run: bool = False,
) -> Dict:
    """Mix narration (and optional BGM) into a master video."""
    in_path = Path(str(input_video or "")).expanduser().resolve()
    out_path = Path(str(output_video or "")).expanduser().resolve()
    nar_path = Path(str(narration_audio or "")).expanduser().resolve()
    bgm_raw = str(bgm_audio or "").strip()
    bgm_is_remote = _is_remote_media_url(bgm_raw)
    bgm_path = None
    bgm_input = ""
    if bgm_raw:
        if bgm_is_remote:
            bgm_input = bgm_raw
        else:
            bgm_path = Path(bgm_raw).expanduser().resolve()
            bgm_input = str(bgm_path)

    if not in_path.exists():
        raise ValueError(f"输入视频不存在: {in_path}")
    if not nar_path.exists() and not dry_run:
        raise ValueError(f"旁白轨不存在: {nar_path}")
    if bgm_path is not None and not bgm_path.exists() and not dry_run:
        raise ValueError(f"BGM 不存在: {bgm_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    has_origin_audio = _probe_has_audio_stream(str(in_path), ffprobe_bin=ffprobe_bin)
    input_duration_s = _probe_media_duration(str(in_path), ffprobe_bin=ffprobe_bin)

    cmd = [ffmpeg_bin, "-y", "-i", str(in_path), "-i", str(nar_path)]
    bgm_present = bool(bgm_input)
    bgm_loop_requested = bool(bgm_loop)
    bgm_loop_applied = bgm_loop_requested and bgm_present and not bgm_is_remote
    bgm_loop_fallback_reason = ""
    if bgm_loop_requested and bgm_present and bgm_is_remote:
        bgm_loop_fallback_reason = "远端 BGM URL 不启用 stream_loop，已降级为单次混音"
    if bgm_present:
        if bgm_loop_applied:
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend(["-i", bgm_input])

    chains = []
    mix_labels = []
    ducking_requested = bool(enable_ducking) and bgm_present
    ducking_applied = False
    ducking_fallback_reason = ""
    if ducking_requested:
        ducking_applied = _ffmpeg_supports_filter(ffmpeg_bin=ffmpeg_bin, filter_name="sidechaincompress")
        if not ducking_applied:
            ducking_fallback_reason = "当前 ffmpeg 不支持 sidechaincompress，已降级为普通混音（无自动压低 BGM）"

    if has_origin_audio:
        chains.append(f"[0:a]volume={max(float(origin_volume), 0.0)}[a0]")
        mix_labels.append("[a0]")
    chains.append(f"[1:a]volume={max(float(narration_volume), 0.0)}[a1]")
    mix_labels.append("[a1]")
    if bgm_present:
        idx = 2
        bgm_label = "[a2]"
        bgm_src = "[a2raw]"
        chains.append(f"[{idx}:a]volume={max(float(bgm_volume), 0.0)}{bgm_src}")
        if bool(bgm_loop_applied) and input_duration_s is not None:
            trim_label = "[a2trim]"
            chains.append(f"{bgm_src}atrim=duration={float(input_duration_s):.3f}{trim_label}")
            bgm_src = trim_label
            fade_d = max(float(bgm_fade_out_s), 0.0)
            if fade_d > 0:
                fade_d = min(fade_d, float(input_duration_s))
                fade_start = max(float(input_duration_s) - fade_d, 0.0)
                fade_label = "[a2fade]"
                chains.append(f"{bgm_src}afade=t=out:st={fade_start:.3f}:d={fade_d:.3f}{fade_label}")
                bgm_src = fade_label
        if ducking_requested and ducking_applied:
            threshold = max(min(float(ducking_threshold), 1.0), 0.0001)
            ratio = max(float(ducking_ratio), 1.0)
            attack = max(float(ducking_attack_ms), 0.0)
            release = max(float(ducking_release_ms), 0.0)
            chains.append(
                f"{bgm_src}[a1]sidechaincompress=threshold={threshold}:ratio={ratio}:attack={attack}:release={release}{bgm_label}"
            )
        else:
            chains.append(f"{bgm_src}anull{bgm_label}")
        mix_labels.append(bgm_label)
    chains.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=2[aout]")
    filter_complex = ";".join(chains)

    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            str(audio_bitrate or "192k"),
            str(out_path),
        ]
    )

    result = {
        "input_video": str(in_path),
        "output_video": str(out_path),
        "narration_audio": str(nar_path),
        "bgm_audio": bgm_input,
        "bgm_is_remote": bool(bgm_is_remote),
        "input_duration_s": round(float(input_duration_s), 3) if input_duration_s is not None else None,
        "bgm_loop": bool(bgm_loop_requested),
        "bgm_loop_applied": bool(bgm_loop_applied),
        "bgm_loop_fallback_reason": bgm_loop_fallback_reason,
        "bgm_fade_out_s": float(bgm_fade_out_s),
        "has_origin_audio": bool(has_origin_audio),
        "enable_ducking": bool(enable_ducking),
        "ducking_applied": bool(ducking_applied),
        "ducking_fallback_reason": ducking_fallback_reason,
        "ducking_threshold": float(ducking_threshold),
        "ducking_ratio": float(ducking_ratio),
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
    if proc.returncode != 0:
        raise RuntimeError(result["stderr_tail"] or "音频混音失败")
    return result
