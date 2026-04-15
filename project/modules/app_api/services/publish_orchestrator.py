"""Publish orchestration functions extracted from server.py (L1-5)."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

# ── Module-level state (defaults; overwritten by init()) ────────────
_project_dir = None
_secret_store = None  # SecretStore instance, injected via init()
_jobs: Dict[str, dict] = {}  # job_id → {status, log, progress}


def init(*, project_dir=None, secret_store=None, jobs=None):
    global _project_dir, _secret_store, _jobs
    if project_dir is not None:
        _project_dir = project_dir
    if secret_store is not None:
        _secret_store = secret_store
    if jobs is not None:
        _jobs = jobs


# ── Group A — Runners ────────────────────────────────────────────────

def _build_social_export_runner(
    *,
    input_video_raw: str,
    output_dir_raw: str,
    platforms: List[str],
    quality: str,
    ffmpeg_bin: str,
    ffprobe_bin: str,
    strict_duration_limit: bool,
    timeout_seconds: float,
    job_id: str,
    profile_overrides: Optional[Dict] = None,
    input_mode: str = "project",
    base_dir: Optional[Path] = None,
    persist_history: bool = True,
):
    from modules.capabilities.social_export import build_export_plan, run_export_plan
    from modules.app_api.server import (
        _resolve_path_with_base,
        _default_master_video_path,
        _append_social_export_history,
        logger,
    )

    def _do_export():
        anchor = base_dir if base_dir is not None else (_project_dir if _project_dir is not None else Path.cwd())
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + job_id
        started_at = datetime.now().isoformat(timespec="seconds")
        if input_video_raw:
            in_path = _resolve_path_with_base(input_video_raw, base_dir=anchor, enforce_contain=(input_mode == "project"))
        else:
            if input_mode == "project":
                in_path = _default_master_video_path()
                if in_path is None:
                    raise RuntimeError("找不到可导出的母版视频")
            else:
                raise RuntimeError("inline 模式需要提供 input_video")
        if not in_path.exists():
            raise RuntimeError(f"输入视频不存在: {in_path}")

        final_platforms = platforms if platforms else ["douyin", "xiaohongshu", "tiktok"]
        out_dir = (
            (anchor / "output" / "social_exports")
            if not output_dir_raw
            else _resolve_path_with_base(output_dir_raw, base_dir=anchor, enforce_contain=(input_mode == "project"))
        )

        plan = build_export_plan(
            input_video=str(in_path),
            output_dir=str(out_dir),
            platform_ids=final_platforms,
            quality=quality,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
            strict_duration_limit=bool(strict_duration_limit),
            profile_overrides=profile_overrides,
        )
        logger.info("[社媒导出] 总任务 %d，输出目录: %s", len(plan.get("jobs", [])), out_dir)
        for i, job in enumerate(plan.get("jobs", []), start=1):
            logger.info("[社媒导出] %d/%d %s -> %s", i, len(plan["jobs"]), job.get("platform_id"), job.get("output_video"))
        try:
            result = run_export_plan(plan, timeout_seconds=timeout_seconds)
        except Exception as exc:
            failed_record = {
                "batch_id": batch_id,
                "job_id": job_id,
                "status": "failed",
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "input_video": str(in_path),
                "output_dir": str(out_dir),
                "platforms": [j.get("platform_id") for j in plan.get("jobs", [])],
                "quality": quality,
                "strict_duration_limit": bool(strict_duration_limit),
                "total": len(plan.get("jobs", [])),
                "success": 0,
                "failed": len(plan.get("jobs", [])),
                "error": str(exc),
                "output_files": [],
            }
            if persist_history and input_mode == "project":
                _append_social_export_history(failed_record)
            raise

        done_files = [
            r.get("output_video")
            for r in result.get("results", [])
            if r.get("status") == "done" and r.get("output_video")
        ]
        record = {
            "batch_id": batch_id,
            "job_id": job_id,
            "status": "done" if int(result.get("failed", 0)) == 0 else "partial",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "input_video": str(in_path),
            "output_dir": str(out_dir),
            "platforms": [j.get("platform_id") for j in plan.get("jobs", [])],
            "quality": quality,
            "strict_duration_limit": bool(strict_duration_limit),
            "total": int(result.get("total", 0)),
            "success": int(result.get("success", 0)),
            "failed": int(result.get("failed", 0)),
            "output_files": done_files,
        }
        if persist_history and input_mode == "project":
            _append_social_export_history(record)
        logger.info("[社媒导出] 完成，成功 %d，失败 %d", result.get("success", 0), result.get("failed", 0))
        return {"plan": plan, "result": result, "batch": record}

    return _do_export


def _build_audio_voice_runner(
    *,
    payload: Dict,
    job_id: str,
    input_mode: str = "project",
    base_dir: Optional[Path] = None,
):
    from modules.capabilities.audio_voice import (
        build_audio_capability_payload,
        build_voiceover_timeline,
        mix_voiceover_to_video,
        pick_bgm,
        synthesize_voiceover_segments,
    )
    from modules.app_api.server import (
        _capability_base_dir,
        _coerce_script_input,
        _resolve_path_with_base,
        _default_master_video_path,
        _parse_str_list,
        _default_bgm_library_dirs,
        _default_bgm_output_dir,
        _is_remote_media_url,
        _project_data_path,
        logger,
    )

    def _set_progress(p: int, msg: str = ""):
        if job_id in _jobs:
            _jobs[job_id]["progress"] = max(0, min(99, int(p)))
            if msg:
                _jobs[job_id]["log"].append(msg)
                _jobs[job_id]["log"] = _jobs[job_id]["log"][-220:]

    def _do_audio_voice():
        if input_mode == "project" and _project_dir is None:
            raise RuntimeError("项目未加载")
        anchor = base_dir if base_dir is not None else _capability_base_dir(input_mode)

        mood = str(payload.get("mood", "travel_story") or "travel_story")
        provider = str(payload.get("provider", "elevenlabs") or "elevenlabs")
        voice_id = str(payload.get("voice_id", "") or "").strip()
        api_key = str(payload.get("api_key", "") or "").strip()
        model_id = str(payload.get("model_id", "eleven_multilingual_v2") or "eleven_multilingual_v2")
        output_format = str(payload.get("output_format", "mp3_44100_128") or "mp3_44100_128")
        dry_run = bool(payload.get("dry_run", False))

        _set_progress(5, "[配音] 读取脚本与字幕")
        script = _coerce_script_input(payload, input_mode=input_mode)
        plan = build_audio_capability_payload(script, mood=mood)
        segments = payload.get("segments", plan.get("voiceover_segments", []))
        if not isinstance(segments, list) or not segments:
            raise RuntimeError("缺少可合成的字幕分段，请先完成脚本/字幕")
        clip_duration_s = plan.get("music_plan", {}).get("duration_s")
        if clip_duration_s in {None, 0, 0.0}:
            clip_duration_s = payload.get("target_duration_s")

        output_dir_raw = str(payload.get("output_dir", "") or "").strip()
        output_dir = (
            (anchor / "data" / "audio_voice" / "voiceover")
            if not output_dir_raw
            else _resolve_path_with_base(output_dir_raw, base_dir=anchor, enforce_contain=(input_mode == "project"))
        )

        _set_progress(20, "[配音] 开始 ElevenLabs 合成")
        synthesis = synthesize_voiceover_segments(
            segments,
            output_dir=str(output_dir),
            provider=provider,
            voice_id=voice_id,
            api_key=api_key,
            model_id=model_id,
            output_format=output_format,
            timeout_seconds=float(payload.get("tts_timeout_seconds", 90) or 90),
            dry_run=dry_run,
        )

        output_audio_raw = str(payload.get("output_audio", "") or "").strip()
        output_audio = (
            (anchor / "data" / "audio_voice" / "narration_timeline.m4a")
            if not output_audio_raw
            else _resolve_path_with_base(output_audio_raw, base_dir=anchor, enforce_contain=(input_mode == "project"))
        )

        _set_progress(55, "[配音] 生成旁白时间线轨")
        timeline = build_voiceover_timeline(
            synthesis.get("segments", []),
            output_audio=str(output_audio),
            ffmpeg_bin=str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg"),
            timeout_seconds=float(payload.get("track_timeout_seconds", 600) or 600),
            dry_run=dry_run,
        )

        input_video_raw = str(payload.get("input_video", "") or "").strip()
        if input_video_raw:
            input_video = _resolve_path_with_base(input_video_raw, base_dir=anchor, enforce_contain=(input_mode == "project"))
        else:
            if input_mode == "project":
                input_video = _default_master_video_path()
                if input_video is None:
                    raise RuntimeError("找不到可混音的输入视频")
            else:
                raise RuntimeError("inline 模式需要提供 input_video")
        if not input_video.exists():
            raise RuntimeError(f"输入视频不存在: {input_video}")

        bgm_audio_raw = str(payload.get("bgm_audio", "") or "").strip()
        bgm_audio = ""
        bgm_pick = None
        if bgm_audio_raw:
            if _is_remote_media_url(bgm_audio_raw):
                bgm_audio = bgm_audio_raw
            else:
                bgm_path = _resolve_path_with_base(bgm_audio_raw, base_dir=anchor, enforce_contain=(input_mode == "project"))
                bgm_audio = str(bgm_path)
        elif bool(payload.get("auto_pick_bgm", True)):
            _set_progress(68, "[配乐] 自动匹配 BGM")
            library_dir = str(payload.get("bgm_library_dir", "") or "").strip()
            library_dirs = _parse_str_list(payload.get("bgm_library_dirs", []))
            if input_mode == "project":
                resolved_dirs = _default_bgm_library_dirs(custom_dir=library_dir, custom_dirs=library_dirs)
            else:
                resolved_dirs = []
                for item in [library_dir, *library_dirs]:
                    raw = str(item or "").strip()
                    if not raw:
                        continue
                    # BGM library dirs are legitimately OPERATOR-configured
                    # to live outside the project (e.g. ~/Music/BGM_Library).
                    # This is one of the few sites where containment is off.
                    resolved = _resolve_path_with_base(raw, base_dir=anchor, enforce_contain=False)
                    if resolved.exists() and resolved.is_dir():
                        resolved_dirs.append(resolved)
            bgm_provider = str(payload.get("bgm_provider", "local_library") or "local_library")
            if input_mode == "project":
                bgm_output_dir = _default_bgm_output_dir(str(payload.get("bgm_output_dir", "") or "").strip())
            else:
                bgm_output_raw = str(payload.get("bgm_output_dir", "") or "").strip()
                bgm_output_dir = (
                    (anchor / "data" / "audio_voice" / "bgm")
                    if not bgm_output_raw
                    else _resolve_path_with_base(bgm_output_raw, base_dir=anchor, enforce_contain=(input_mode == "project"))
                )
            bgm_force_refresh = bool(payload.get("bgm_force_refresh", False))
            bgm_cache_max_age_days = float(payload.get("bgm_cache_max_age_days", 0) or 0)
            bgm_cache_max_age_seconds = max(bgm_cache_max_age_days, 0.0) * 86400.0
            try:
                bgm_pick = pick_bgm(
                    provider=bgm_provider,
                    mood=mood,
                    target_duration_s=float(clip_duration_s or 0.0) or None,
                    library_dirs=[str(x) for x in resolved_dirs],
                    ffprobe_bin=str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe"),
                    max_candidates=int(payload.get("bgm_max_candidates", 20) or 20),
                    api_key=str(payload.get("bgm_api_key", "") or "").strip(),
                    endpoint=str(payload.get("bgm_endpoint", "") or "").strip(),
                    timeout_seconds=float(payload.get("bgm_timeout_seconds", 45) or 45),
                    output_dir=str(bgm_output_dir) if bgm_output_dir is not None else "",
                    download_audio=bool(payload.get("bgm_download", True)),
                    strict_schema=bool(payload.get("bgm_strict_schema", False)),
                    cache_enabled=bool(payload.get("bgm_cache_enabled", True)),
                    force_refresh=bgm_force_refresh,
                    cache_max_age_seconds=bgm_cache_max_age_seconds,
                )
                maybe_track = str(bgm_pick.get("selected_track", "") or "").strip() if isinstance(bgm_pick, dict) else ""
                if maybe_track:
                    bgm_audio = maybe_track
                    _set_progress(71, f"[配乐] 已选择 BGM: {Path(maybe_track).name}")
                elif isinstance(bgm_pick, dict) and str(bgm_pick.get("selected_url", "")).strip():
                    bgm_audio = str(bgm_pick.get("selected_url", "")).strip()
                    _set_progress(71, "[配乐] 使用远端 BGM URL 参与混音")
                else:
                    _set_progress(71, "[配乐] 未找到可用 BGM，将仅混入旁白")
            except Exception as exc:
                bgm_pick = {"status": "failed", "error": str(exc), "provider": bgm_provider}
                _set_progress(71, f"[配乐] 自动匹配失败，改为仅混入旁白: {exc}")

        replace_master = bool(payload.get("replace_master", input_mode == "project"))
        output_video_raw = str(payload.get("output_video", "") or "").strip()
        if replace_master:
            output_video = anchor / "output" / "final.mp4"
        elif output_video_raw:
            output_video = _resolve_path_with_base(output_video_raw, base_dir=anchor, enforce_contain=(input_mode == "project"))
        else:
            output_video = anchor / "output" / "final_voice.mp4"

        mix_target = output_video
        used_temp = False
        if output_video.resolve() == input_video.resolve():
            used_temp = True
            mix_target = output_video.with_suffix(".audio_pipeline_tmp.mp4")

        _set_progress(75, "[配音] 混音到成片")
        mix = mix_voiceover_to_video(
            input_video=str(input_video),
            output_video=str(mix_target),
            narration_audio=str(output_audio),
            bgm_audio=bgm_audio,
            ffmpeg_bin=str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg"),
            ffprobe_bin=str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe"),
            origin_volume=float(payload.get("origin_volume", 0.8) or 0.8),
            narration_volume=float(payload.get("narration_volume", 1.0) or 1.0),
            bgm_volume=float(payload.get("bgm_volume", 0.25) or 0.25),
            bgm_loop=bool(payload.get("bgm_loop", True)),
            bgm_fade_out_s=float(payload.get("bgm_fade_out_s", 2.0) or 0.0),
            enable_ducking=bool(payload.get("enable_ducking", True)),
            ducking_threshold=float(payload.get("ducking_threshold", 0.03) or 0.03),
            ducking_ratio=float(payload.get("ducking_ratio", 8.0) or 8.0),
            ducking_attack_ms=float(payload.get("ducking_attack_ms", 15.0) or 15.0),
            ducking_release_ms=float(payload.get("ducking_release_ms", 250.0) or 250.0),
            audio_bitrate=str(payload.get("audio_bitrate", "192k") or "192k"),
            timeout_seconds=float(payload.get("mix_timeout_seconds", 900) or 900),
            dry_run=dry_run,
        )

        if used_temp and not dry_run and mix.get("status") == "done":
            mix_target.replace(output_video)
            mix["output_video"] = str(output_video.resolve())

        _set_progress(95, "[配音] 写入结果摘要")
        summary = {
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "input_mode": input_mode,
            "dry_run": dry_run,
            "plan": plan,
            "bgm_pick": bgm_pick,
            "synthesis": synthesis,
            "timeline": timeline,
            "mix": mix,
        }
        out_path = _project_data_path("audio_voice_pipeline_last.json") if input_mode == "project" else None
        if out_path is not None:
            from modules.app_api.param_utils import atomic_write_json
            atomic_write_json(out_path, summary)
        return summary

    return _do_audio_voice


# ── Group B — Content Publish ────────────────────────────────────────

def _read_content_publish_sessions() -> Dict[str, Dict[str, Any]]:
    from modules.app_api.server import _read_project_json
    raw = _read_project_json("content_publish_sessions.json", fallback={})
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        sid = str(key or "").strip()
        if sid and isinstance(value, dict):
            out[sid] = value
    return out


def _save_content_publish_sessions(sessions: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    from modules.app_api.server import _project_data_path
    p = _project_data_path("content_publish_sessions.json")
    if p is None:
        return sessions
    payload = sessions if isinstance(sessions, dict) else {}
    from modules.app_api.param_utils import atomic_write_json
    atomic_write_json(p, payload)
    return payload


def _read_content_publish_history() -> List[Dict[str, Any]]:
    from modules.app_api.server import _read_project_json
    raw = _read_project_json("content_publish_history.json", fallback=[])
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _save_content_publish_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from modules.app_api.server import _project_data_path
    p = _project_data_path("content_publish_history.json")
    if p is None:
        return history
    items = [x for x in history if isinstance(x, dict)]
    from modules.app_api.param_utils import atomic_write_json
    atomic_write_json(p, items)
    return items


def _resolve_content_publish_content(
    payload: Dict[str, Any],
    *,
    input_mode: str,
) -> Dict[str, Any]:
    from modules.app_api.server import _read_project_json
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    out = dict(content)
    if input_mode == "project":
        if not out.get("title") or not out.get("description"):
            publish_prep = _read_project_json("publish_prep_last.json", fallback={})
            result = publish_prep.get("platform_results", []) if isinstance(publish_prep, dict) else []
            first = result[0] if isinstance(result, list) and result else {}
            generated = first.get("content", {}) if isinstance(first, dict) else {}
            if not out.get("title"):
                out["title"] = str(generated.get("title") or "").strip()
            if not out.get("description"):
                out["description"] = str(generated.get("body") or "").strip()
            if not out.get("keywords") and isinstance(generated.get("keywords"), list):
                out["keywords"] = generated.get("keywords")
        if not out.get("article_markdown") or not out.get("article_html"):
            article = _read_project_json("article_expand_last.json", fallback={})
            if isinstance(article, dict):
                if not out.get("article_markdown"):
                    out["article_markdown"] = str(article.get("markdown") or "").strip()
                if not out.get("article_html"):
                    md = str(article.get("markdown") or "").strip()
                    title = str(article.get("title_candidates", ["Untitled"])[0] if isinstance(article.get("title_candidates"), list) and article.get("title_candidates") else "Untitled")
                    if md:
                        out["article_html"] = f"<article><h1>{title}</h1><pre>{md}</pre></article>"
    return out


def _resolve_content_publish_connectors(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    from modules.app_api.server import _normalize_publish_connectors, _load_publish_settings
    connectors = payload.get("connectors", {})
    if isinstance(connectors, dict) and connectors:
        result = _normalize_publish_connectors(connectors)
    else:
        saved = _load_publish_settings()
        result = saved.get("connectors", {}) if isinstance(saved.get("connectors"), dict) else {}
    # Auto-inject YouTube OAuth token from secure_store
    result = _inject_youtube_oauth_token(result)
    return result


def _inject_youtube_oauth_token(connectors: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """If YouTube connector has no access_token, inject from secure_store OAuth."""
    yt = connectors.get("youtube", {})
    if isinstance(yt, dict) and yt.get("access_token"):
        return connectors  # Already has a token, don't override
    try:
        raw = _secret_store.get("youtube_oauth")
        if not raw:
            return connectors
        import json as _json
        token_data = _json.loads(raw)
        access_token = token_data.get("access_token", "")
        if not access_token:
            return connectors
        # Auto-refresh if expired
        expires_at = float(token_data.get("expires_at", 0))
        if expires_at and (time.time() > expires_at - 300):
            refreshed = _refresh_youtube_token(token_data)
            if refreshed:
                token_data = refreshed
                access_token = token_data.get("access_token", "")
        yt_connector = dict(yt) if isinstance(yt, dict) else {}
        yt_connector.update({
            "kind": "youtube_api",
            "access_token": access_token,
        })
        connectors = dict(connectors)
        connectors["youtube"] = yt_connector
    except Exception as _inject_exc:
        # Don't silently eat OAuth refresh failures — surface them on the
        # connector record so the downstream runner reports "OAuth refresh
        # failed" instead of a cryptic 401 from YouTube. Round-12 P0 finding.
        try:
            _inject_logger = __import__("logging").getLogger(__name__)
            _inject_logger.warning("[yt_oauth] inject failed: %s", _inject_exc)
        except Exception:
            pass
        if isinstance(connectors, dict):
            connectors = dict(connectors)
            yt = connectors.get("youtube")
            if isinstance(yt, dict):
                yt = dict(yt)
                yt["refresh_error"] = str(_inject_exc)
                connectors["youtube"] = yt
    return connectors


# 4MB cap on OAuth token-endpoint response; a healthy response is <2KB,
# anything larger means the endpoint is compromised or hijacked — better
# to OOM-fail the token refresh than OOM the whole app.
_OAUTH_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def _refresh_youtube_token(token_data: dict) -> Optional[dict]:
    """Refresh YouTube OAuth token using refresh_token."""
    refresh_token = token_data.get("refresh_token", "")
    if not refresh_token:
        return None
    import os
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    try:
        import urllib.request
        import urllib.parse
        import json as _json
        post_data = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            # Cap response size. Previously an unlimited resp.read() on a
            # compromised/hijacked token endpoint could OOM the process.
            raw = resp.read(_OAUTH_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _OAUTH_MAX_RESPONSE_BYTES:
                raise ValueError(
                    f"OAuth token endpoint response exceeds {_OAUTH_MAX_RESPONSE_BYTES} bytes"
                )
            new_token = _json.loads(raw.decode("utf-8"))
        new_access = new_token.get("access_token", "")
        if not new_access:
            return None
        token_data["access_token"] = new_access
        token_data["expires_at"] = time.time() + int(new_token.get("expires_in", 3600))
        # Persist refreshed token
        _secret_store.set("youtube_oauth", _json.dumps(token_data, ensure_ascii=False))
        return token_data
    except Exception as _refresh_exc:
        # Surface the failure reason to callers/logs — previously this
        # bare return None hid 401s, expired refresh tokens, network
        # errors, and JSON parse errors identically.
        try:
            __import__("logging").getLogger(__name__).warning(
                "[yt_oauth] token refresh failed: %s", _refresh_exc
            )
        except Exception:
            pass
        return None
