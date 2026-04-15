#!/usr/bin/env python3
"""Capability routes: audio voice."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict
import uuid

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import (
    is_safe_outbound_url,
    parse_float_param,
    parse_int_param,
    parse_str_param,
    sanitize_ffmpeg_bin,
    write_json_result,
)


def create_audio_voice_capability_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    parse_capability_input_mode: Callable[[Any, str], str],
    capability_base_dir: Callable[[str], Any],
    coerce_script_input: Callable[[Dict[str, Any], str], Dict[str, Any]],
    project_data_path: Callable[[str], Any],
    parse_str_list: Callable[[Any], list],
    default_bgm_library_dirs: Callable[..., list],
    default_bgm_output_dir: Callable[[str], Any],
    resolve_path_with_base: Callable[[str, Any], Any],
    read_project_json: Callable[[str, Any], Any],
    default_master_video_path: Callable[[], Any],
    is_remote_media_url: Callable[[str], bool],
    build_audio_voice_runner: Callable[..., Callable[[], Dict[str, Any]]],
    run_in_bg: Callable[..., None],
    task_queue_snapshot: Callable[[], Dict[str, Any]],
) -> Blueprint:
    bp = Blueprint("cap_audio_voice_api", __name__)

    @bp.route("/api/capabilities/audio_voice/plan", methods=["POST"])
    def api_audio_voice_plan():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        mood = str(payload.get("mood", "travel_story") or "travel_story")

        from modules.capabilities.audio_voice import build_audio_capability_payload

        script = coerce_script_input(payload, input_mode=input_mode)
        if input_mode == "inline" and not script:
            return jsonify({"error": "inline 模式缺少 script/clips/subtitles"}), 400
        plan = build_audio_capability_payload(script, mood=mood)
        out_path = project_data_path("audio_voice_plan.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            write_json_result(out_path, plan)
        return jsonify({"ok": True, "input_mode": input_mode, "plan": plan, "output": str(out_path) if out_path else None})

    @bp.route("/api/capabilities/audio_voice/pick_bgm", methods=["POST"])
    def api_audio_voice_pick_bgm():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        base_dir = capability_base_dir(input_mode)
        mood = str(payload.get("mood", "travel_story") or "travel_story")
        provider = str(payload.get("bgm_provider", "local_library") or "local_library")
        api_key = parse_str_param(payload.get("bgm_api_key", ""))
        endpoint = parse_str_param(payload.get("bgm_endpoint", ""))
        # SSRF guard — endpoint is user-supplied and used in outbound
        # urlopen/requests calls inside pick_bgm. Without this check the
        # server can be weaponized to probe internal services.
        if endpoint:
            safe, reason = is_safe_outbound_url(endpoint)
            if not safe:
                return jsonify({"error": f"bgm_endpoint 校验失败: {reason}"}), 400
        bgm_download = bool(payload.get("bgm_download", True))
        bgm_strict_schema = bool(payload.get("bgm_strict_schema", False))
        bgm_cache_enabled = bool(payload.get("bgm_cache_enabled", True))
        bgm_force_refresh = bool(payload.get("bgm_force_refresh", False))
        bgm_cache_max_age_days = parse_float_param(payload.get("bgm_cache_max_age_days", 0), default=0.0, min_val=0.0)
        bgm_cache_max_age_seconds = max(bgm_cache_max_age_days, 0.0) * 86400.0
        ffprobe_bin = sanitize_ffmpeg_bin(payload.get("ffprobe_bin"), default="ffprobe")
        target_duration_s = payload.get("target_duration_s", None)
        try:
            target_duration_s = float(target_duration_s) if target_duration_s is not None else None
            if target_duration_s is not None:
                target_duration_s = max(0.1, min(target_duration_s, 7200.0))  # 0.1s ~ 2h
        except Exception:
            target_duration_s = None

        custom_dir = parse_str_param(payload.get("bgm_library_dir", ""))
        custom_dirs = parse_str_list(payload.get("bgm_library_dirs", []))
        if input_mode == "project":
            library_dirs = default_bgm_library_dirs(custom_dir=custom_dir, custom_dirs=custom_dirs)
            output_dir = default_bgm_output_dir(parse_str_param(payload.get("bgm_output_dir", "")))
        else:
            library_dirs = []
            for raw in [custom_dir, *custom_dirs]:
                text = parse_str_param(raw)
                if not text:
                    continue
                resolved = resolve_path_with_base(text, base_dir=base_dir)
                if resolved.exists() and resolved.is_dir():
                    library_dirs.append(resolved)
            bgm_output_raw = parse_str_param(payload.get("bgm_output_dir", ""))
            output_dir = (
                resolve_path_with_base(bgm_output_raw, base_dir=base_dir)
                if bgm_output_raw
                else (base_dir / "data" / "audio_voice" / "bgm")
            )

        from modules.capabilities.audio_voice import pick_bgm

        try:
            pick = pick_bgm(
                provider=provider,
                mood=mood,
                target_duration_s=target_duration_s,
                library_dirs=[str(x) for x in library_dirs],
                ffprobe_bin=ffprobe_bin,
                max_candidates=parse_int_param(payload.get("max_candidates", 20), default=20, min_val=1, max_val=100),
                api_key=api_key,
                endpoint=endpoint,
                timeout_seconds=parse_float_param(payload.get("bgm_timeout_seconds", 45), default=45.0, min_val=1.0, max_val=600.0),
                output_dir=str(output_dir) if output_dir is not None else "",
                download_audio=bgm_download,
                strict_schema=bgm_strict_schema,
                cache_enabled=bgm_cache_enabled,
                force_refresh=bgm_force_refresh,
                cache_max_age_seconds=bgm_cache_max_age_seconds,
            )
        except Exception as exc:
            return jsonify({"error": f"自动配乐失败: {exc}"}), 400

        summary = {
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "mood": mood,
            "pick": pick,
        }
        out_path = project_data_path("audio_voice_bgm_last.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            write_json_result(out_path, summary)
        return jsonify({"ok": True, "input_mode": input_mode, "pick": pick, "output": str(out_path) if out_path else None})

    @bp.route("/api/capabilities/audio_voice/synthesize", methods=["POST"])
    def api_audio_voice_synthesize():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        base_dir = capability_base_dir(input_mode)
        mood = str(payload.get("mood", "travel_story") or "travel_story")
        provider = str(payload.get("provider", "elevenlabs") or "elevenlabs")
        voice_id = parse_str_param(payload.get("voice_id", ""))
        api_key = parse_str_param(payload.get("api_key", ""))
        model_id = str(payload.get("model_id", "eleven_multilingual_v2") or "eleven_multilingual_v2")
        output_format = str(payload.get("output_format", "mp3_44100_128") or "mp3_44100_128")
        dry_run = bool(payload.get("dry_run", False))
        timeout_seconds = parse_float_param(payload.get("timeout_seconds", 90), default=90.0, min_val=1.0, max_val=600.0)

        from modules.capabilities.audio_voice import build_audio_capability_payload, synthesize_voiceover_segments

        script = coerce_script_input(payload, input_mode=input_mode)
        plan = build_audio_capability_payload(script, mood=mood)
        segments = payload.get("segments", plan.get("voiceover_segments", []))
        if not isinstance(segments, list) or not segments:
            return jsonify({"error": "缺少可合成的字幕分段，请先完成脚本/字幕"}), 400

        output_dir_raw = parse_str_param(payload.get("output_dir", ""))
        output_dir = (
            (base_dir / "data" / "audio_voice" / "voiceover")
            if not output_dir_raw
            else resolve_path_with_base(output_dir_raw, base_dir=base_dir)
        )

        try:
            result = synthesize_voiceover_segments(
                segments,
                output_dir=str(output_dir),
                provider=provider,
                voice_id=voice_id,
                api_key=api_key,
                model_id=model_id,
                output_format=output_format,
                timeout_seconds=timeout_seconds,
                dry_run=dry_run,
            )
        except Exception as exc:
            return jsonify({"error": f"配音合成失败: {exc}"}), 400

        summary = {
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "provider": provider,
            "voice_id": voice_id,
            "model_id": model_id,
            "dry_run": dry_run,
            "plan": plan,
            "synthesis": result,
        }
        out_path = project_data_path("audio_voice_synthesize_last.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            write_json_result(out_path, summary)
        return jsonify({
            "ok": True,
            "input_mode": input_mode,
            "plan": plan,
            "synthesis": result,
            "output": str(out_path) if out_path else None,
        })

    @bp.route("/api/capabilities/audio_voice/build_track", methods=["POST"])
    def api_audio_voice_build_track():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        base_dir = capability_base_dir(input_mode)
        ffmpeg_bin = sanitize_ffmpeg_bin(payload.get("ffmpeg_bin"), default="ffmpeg")
        timeout_seconds = parse_float_param(payload.get("timeout_seconds", 600), default=600.0, min_val=1.0, max_val=3600.0)
        dry_run = bool(payload.get("dry_run", False))

        segments = payload.get("segments")
        if not isinstance(segments, list) or not segments:
            if input_mode == "project":
                last = read_project_json("audio_voice_synthesize_last.json", fallback={})
                synthesis = last.get("synthesis", {}) if isinstance(last, dict) else {}
                segments = synthesis.get("segments", []) if isinstance(synthesis, dict) else []
        if not isinstance(segments, list) or not segments:
            return jsonify({"error": "缺少可用的配音分段，请先执行 /api/capabilities/audio_voice/synthesize"}), 400

        output_audio_raw = parse_str_param(payload.get("output_audio", ""))
        output_audio = (
            (base_dir / "data" / "audio_voice" / "narration_timeline.m4a")
            if not output_audio_raw
            else resolve_path_with_base(output_audio_raw, base_dir=base_dir)
        )

        from modules.capabilities.audio_voice import build_voiceover_timeline

        try:
            result = build_voiceover_timeline(
                segments,
                output_audio=str(output_audio),
                ffmpeg_bin=ffmpeg_bin,
                timeout_seconds=timeout_seconds,
                dry_run=dry_run,
            )
        except Exception as exc:
            return jsonify({"error": f"旁白轨生成失败: {exc}"}), 400

        summary = {
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "timeline": result,
        }
        out_path = project_data_path("audio_voice_timeline_last.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            write_json_result(out_path, summary)
        return jsonify({"ok": True, "input_mode": input_mode, "timeline": result, "output": str(out_path) if out_path else None})

    @bp.route("/api/capabilities/audio_voice/mix_master", methods=["POST"])
    def api_audio_voice_mix_master():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        base_dir = capability_base_dir(input_mode)
        ffmpeg_bin = sanitize_ffmpeg_bin(payload.get("ffmpeg_bin"), default="ffmpeg")
        ffprobe_bin = sanitize_ffmpeg_bin(payload.get("ffprobe_bin"), default="ffprobe")
        timeout_seconds = parse_float_param(payload.get("timeout_seconds", 900), default=900.0, min_val=1.0, max_val=7200.0)
        dry_run = bool(payload.get("dry_run", False))
        replace_master = bool(payload.get("replace_master", input_mode == "project"))

        input_video_raw = parse_str_param(payload.get("input_video", ""))
        if input_video_raw:
            input_video = resolve_path_with_base(input_video_raw, base_dir=base_dir)
        else:
            if input_mode == "project":
                input_video = default_master_video_path()
                if input_video is None:
                    return jsonify({"error": "找不到可混音的输入视频"}), 404
            else:
                return jsonify({"error": "inline 模式需要 input_video"}), 400
        if not input_video.exists():
            return jsonify({"error": f"输入视频不存在: {input_video}"}), 404

        narration_audio_raw = parse_str_param(payload.get("narration_audio", ""))
        if narration_audio_raw:
            narration_audio = resolve_path_with_base(narration_audio_raw, base_dir=base_dir)
        else:
            if input_mode == "project":
                timeline_last = read_project_json("audio_voice_timeline_last.json", fallback={})
                timeline = timeline_last.get("timeline", {}) if isinstance(timeline_last, dict) else {}
                maybe_path = parse_str_param(timeline.get("output_audio", ""))
            else:
                timeline = payload.get("timeline", {}) if isinstance(payload.get("timeline"), dict) else {}
                maybe_path = parse_str_param(timeline.get("output_audio", ""))
            if maybe_path:
                narration_audio = resolve_path_with_base(maybe_path, base_dir=base_dir)
            else:
                narration_audio = base_dir / "data" / "audio_voice" / "narration_timeline.m4a"
        if not narration_audio.exists() and not dry_run:
            return jsonify({"error": f"旁白轨不存在: {narration_audio}"}), 404

        mood = str(payload.get("mood", "travel_story") or "travel_story")
        bgm_provider = str(payload.get("bgm_provider", "local_library") or "local_library")
        bgm_api_key = parse_str_param(payload.get("bgm_api_key", ""))
        bgm_endpoint = parse_str_param(payload.get("bgm_endpoint", ""))
        bgm_download = bool(payload.get("bgm_download", True))
        bgm_strict_schema = bool(payload.get("bgm_strict_schema", False))
        bgm_cache_enabled = bool(payload.get("bgm_cache_enabled", True))
        bgm_force_refresh = bool(payload.get("bgm_force_refresh", False))
        bgm_cache_max_age_days = parse_float_param(payload.get("bgm_cache_max_age_days", 0), default=0.0, min_val=0.0)
        bgm_cache_max_age_seconds = max(bgm_cache_max_age_days, 0.0) * 86400.0
        bgm_audio_raw = parse_str_param(payload.get("bgm_audio", ""))
        bgm_pick = None
        bgm_audio = ""
        if bgm_audio_raw:
            if is_remote_media_url(bgm_audio_raw):
                bgm_audio = bgm_audio_raw
            else:
                bgm_path = resolve_path_with_base(bgm_audio_raw, base_dir=base_dir)
                bgm_audio = str(bgm_path)
        elif bool(payload.get("auto_pick_bgm", False)):
            from modules.capabilities.audio_voice import pick_bgm

            plan_guess = read_project_json("audio_voice_plan.json", fallback={}) if input_mode == "project" else {}
            duration_guess = None
            if isinstance(plan_guess, dict):
                try:
                    duration_guess = float(
                        plan_guess.get("music_plan", {}).get("duration_s")
                    )
                except Exception:
                    duration_guess = None
            custom_dir = parse_str_param(payload.get("bgm_library_dir", ""))
            custom_dirs = parse_str_list(payload.get("bgm_library_dirs", []))
            if input_mode == "project":
                library_dirs = default_bgm_library_dirs(custom_dir=custom_dir, custom_dirs=custom_dirs)
                output_dir = default_bgm_output_dir(parse_str_param(payload.get("bgm_output_dir", "")))
            else:
                library_dirs = []
                for raw in [custom_dir, *custom_dirs]:
                    text = parse_str_param(raw)
                    if not text:
                        continue
                    resolved = resolve_path_with_base(text, base_dir=base_dir)
                    if resolved.exists() and resolved.is_dir():
                        library_dirs.append(resolved)
                bgm_output_raw = parse_str_param(payload.get("bgm_output_dir", ""))
                output_dir = (
                    resolve_path_with_base(bgm_output_raw, base_dir=base_dir)
                    if bgm_output_raw
                    else (base_dir / "data" / "audio_voice" / "bgm")
                )
            try:
                bgm_pick = pick_bgm(
                    provider=bgm_provider,
                    mood=mood,
                    target_duration_s=duration_guess,
                    library_dirs=[str(x) for x in library_dirs],
                    ffprobe_bin=ffprobe_bin,
                    max_candidates=parse_int_param(payload.get("bgm_max_candidates", 20), default=20, min_val=1, max_val=100),
                    api_key=bgm_api_key,
                    endpoint=bgm_endpoint,
                    timeout_seconds=parse_float_param(payload.get("bgm_timeout_seconds", 45), default=45.0, min_val=1.0, max_val=600.0),
                    output_dir=str(output_dir) if output_dir is not None else "",
                    download_audio=bgm_download,
                    strict_schema=bgm_strict_schema,
                    cache_enabled=bgm_cache_enabled,
                    force_refresh=bgm_force_refresh,
                    cache_max_age_seconds=bgm_cache_max_age_seconds,
                )
            except Exception as exc:
                return jsonify({"error": f"自动配乐失败: {exc}"}), 400
            maybe_track = parse_str_param(bgm_pick.get("selected_track", "")) if isinstance(bgm_pick, dict) else ""
            if maybe_track:
                bgm_audio = maybe_track
            elif isinstance(bgm_pick, dict):
                maybe_url = parse_str_param(bgm_pick.get("selected_url", ""))
                if maybe_url:
                    bgm_audio = maybe_url

        output_video_raw = parse_str_param(payload.get("output_video", ""))
        if replace_master:
            output_video = base_dir / "output" / "final.mp4"
        elif output_video_raw:
            output_video = resolve_path_with_base(output_video_raw, base_dir=base_dir)
        else:
            output_video = base_dir / "output" / "final_voice.mp4"

        mix_target = output_video
        used_temp = False
        if output_video.resolve() == input_video.resolve():
            used_temp = True
            mix_target = output_video.with_suffix(".mixing_tmp.mp4")

        from modules.capabilities.audio_voice import mix_voiceover_to_video

        try:
            result = mix_voiceover_to_video(
                input_video=str(input_video),
                output_video=str(mix_target),
                narration_audio=str(narration_audio),
                bgm_audio=bgm_audio,
                ffmpeg_bin=ffmpeg_bin,
                ffprobe_bin=ffprobe_bin,
                origin_volume=parse_float_param(payload.get("origin_volume", 0.8) or 0.8, default=0.8, min_val=0.0, max_val=3.0),
                narration_volume=parse_float_param(payload.get("narration_volume", 1.0) or 1.0, default=1.0, min_val=0.0, max_val=3.0),
                bgm_volume=parse_float_param(payload.get("bgm_volume", 0.25) or 0.25, default=0.25, min_val=0.0, max_val=3.0),
                bgm_loop=bool(payload.get("bgm_loop", True)),
                bgm_fade_out_s=parse_float_param(payload.get("bgm_fade_out_s", 2.0) or 0.0, default=0.0, min_val=0.0, max_val=30.0),
                enable_ducking=bool(payload.get("enable_ducking", True)),
                ducking_threshold=parse_float_param(payload.get("ducking_threshold", 0.03) or 0.03, default=0.03, min_val=0.0, max_val=1.0),
                ducking_ratio=parse_float_param(payload.get("ducking_ratio", 8.0) or 8.0, default=8.0, min_val=1.0, max_val=50.0),
                ducking_attack_ms=parse_float_param(payload.get("ducking_attack_ms", 15.0) or 15.0, default=15.0, min_val=0.0, max_val=500.0),
                ducking_release_ms=parse_float_param(payload.get("ducking_release_ms", 250.0) or 250.0, default=250.0, min_val=0.0, max_val=2000.0),
                audio_bitrate=str(payload.get("audio_bitrate", "192k") or "192k"),
                timeout_seconds=timeout_seconds,
                dry_run=dry_run,
            )
        except Exception as exc:
            return jsonify({"error": f"成片混音失败: {exc}"}), 400

        if used_temp and not dry_run and result.get("status") == "done":
            mix_target.replace(output_video)
            result["output_video"] = str(output_video.resolve())

        summary = {
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "replace_master": replace_master,
            "bgm_pick": bgm_pick,
            "mix": result,
        }
        out_path = project_data_path("audio_voice_mix_last.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            write_json_result(out_path, summary)
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "mix": result,
                "bgm_pick": bgm_pick,
                "output": str(out_path) if out_path else None,
            }
        )

    @bp.route("/api/capabilities/audio_voice/run", methods=["POST"])
    def api_audio_voice_run():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        job_id = str(uuid.uuid4())[:8]
        runner = build_audio_voice_runner(
            payload=payload,
            job_id=job_id,
            input_mode=input_mode,
            base_dir=capability_base_dir(input_mode),
        )
        run_in_bg(job_id, runner, kind="audio_voice")
        return jsonify({"ok": True, "input_mode": input_mode, "job_id": job_id, "task_queue": task_queue_snapshot()})

    return bp
