#!/usr/bin/env python3
"""Capability routes: social export."""

from __future__ import annotations

from typing import Any, Callable, Dict
import uuid

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_float_param, parse_int_param, write_json_result


def create_social_export_capability_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    request_json_any_method: Callable[[], Dict[str, Any]],
    parse_capability_input_mode: Callable[[Any, str], str],
    coerce_social_export_overrides: Callable[[Dict[str, Any], str], Dict[str, Dict[str, Any]]],
    normalize_export_template_payload: Callable[[Dict[str, Any]], Dict[str, Any]],
    save_social_export_templates: Callable[[Dict[str, Dict[str, Any]]], Dict[str, Dict[str, Any]]],
    normalize_export_template_id: Callable[[str], str],
    get_social_export_history: Callable[[], list],
    capability_base_dir: Callable[[str], Any],
    resolve_path_with_base: Callable[[str, Any], Any],
    default_master_video_path: Callable[[], Any],
    parse_platforms: Callable[[Any], list],
    project_data_path: Callable[[str], Any],
    build_social_export_runner: Callable[..., Callable[[], Dict[str, Any]]],
    run_in_bg: Callable[..., None],
    task_queue_snapshot: Callable[[], Dict[str, Any]],
) -> Blueprint:
    bp = Blueprint("cap_social_export_api", __name__)

    @bp.route("/api/capabilities/social_export/profiles", methods=["GET"])
    def api_social_export_profiles():
        from modules.capabilities.social_export import list_export_profiles

        payload = request_json_any_method()
        input_mode = parse_capability_input_mode(
            request.args.get("input_mode", payload.get("input_mode", "project")),
            default="project",
        )
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)
        profiles = list_export_profiles(profile_overrides=templates)
        custom_ids = set(templates.keys())
        for item in profiles:
            pid = str(item.get("platform_id", "") or "")
            item["is_custom"] = pid in custom_ids
        return jsonify({"ok": True, "input_mode": input_mode, "profiles": profiles})

    @bp.route("/api/capabilities/social_export/specs", methods=["GET"])
    def api_social_export_specs():
        from modules.capabilities.social_export import list_export_specs

        payload = request_json_any_method()
        input_mode = parse_capability_input_mode(
            request.args.get("input_mode", payload.get("input_mode", "project")),
            default="project",
        )
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)
        specs = list_export_specs(profile_overrides=templates)
        return jsonify({"ok": True, "input_mode": input_mode, "specs": specs})

    @bp.route("/api/capabilities/social_export/templates", methods=["GET"])
    def api_social_export_templates_list():
        payload = request_json_any_method()
        input_mode = parse_capability_input_mode(
            request.args.get("input_mode", payload.get("input_mode", "project")),
            default="project",
        )
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)
        items = list(templates.values())
        return jsonify({"ok": True, "input_mode": input_mode, "templates": items})

    @bp.route("/api/capabilities/social_export/templates", methods=["POST"])
    def api_social_export_templates_upsert():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        try:
            tmpl = normalize_export_template_payload(payload)
        except Exception as exc:
            return jsonify({"error": f"模板保存失败: {exc}"}), 400
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)
        templates[tmpl["platform_id"]] = tmpl
        saved = save_social_export_templates(templates) if input_mode == "project" else templates
        return jsonify({"ok": True, "input_mode": input_mode, "template": tmpl, "templates": list(saved.values())})

    @bp.route("/api/capabilities/social_export/templates/<template_id>", methods=["DELETE"])
    def api_social_export_templates_delete(template_id: str):
        payload = request.json or {}
        input_mode = parse_capability_input_mode(
            request.args.get("input_mode", payload.get("input_mode", "project")),
            default="project",
        )
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        pid = normalize_export_template_id(template_id)
        if not pid:
            return jsonify({"error": "template_id 无效"}), 400
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)
        if pid not in templates:
            return jsonify({"error": f"模板不存在: {pid}"}), 404
        templates.pop(pid, None)
        saved = save_social_export_templates(templates) if input_mode == "project" else templates
        return jsonify({"ok": True, "input_mode": input_mode, "deleted": pid, "templates": list(saved.values())})

    @bp.route("/api/capabilities/social_export/history", methods=["GET"])
    def api_social_export_history():
        payload = request_json_any_method()
        input_mode = parse_capability_input_mode(
            request.args.get("input_mode", payload.get("input_mode", "project")),
            default="project",
        )
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        limit = parse_int_param(request.args.get("limit", payload.get("limit", "30")), default=30, min_val=1, max_val=200)

        history_raw = payload.get("history", [])
        if input_mode == "project":
            history = get_social_export_history()
        else:
            history = [x for x in history_raw if isinstance(x, dict)] if isinstance(history_raw, list) else []
        items = list(reversed(history[-limit:])) if history else []
        return jsonify({"ok": True, "input_mode": input_mode, "history": items})

    @bp.route("/api/capabilities/social_export/validate_source", methods=["POST"])
    def api_social_export_validate_source():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        base_dir = capability_base_dir(input_mode)
        from modules.capabilities.social_export import validate_source_for_export

        input_video_raw = str(payload.get("input_video", "") or "").strip()
        if input_video_raw:
            input_video = resolve_path_with_base(input_video_raw, base_dir=base_dir)
        else:
            if input_mode == "project":
                input_video = default_master_video_path()
                if input_video is None:
                    return jsonify({"error": "找不到可校验的母版视频"}), 404
            else:
                return jsonify({"error": "inline 模式需要 input_video"}), 400
        if not input_video.exists():
            return jsonify({"error": f"输入视频不存在: {input_video}"}), 404

        platforms = parse_platforms(payload.get("platforms"))
        if not platforms:
            platforms = ["douyin", "xiaohongshu", "tiktok"]
        strict_duration_limit = bool(payload.get("strict_duration_limit", True))
        ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)
        try:
            report = validate_source_for_export(
                input_video=str(input_video),
                platform_ids=platforms,
                strict_duration_limit=strict_duration_limit,
                ffprobe_bin=ffprobe_bin,
                profile_overrides=templates,
            )
        except Exception as exc:
            return jsonify({"error": f"源视频校验失败: {exc}"}), 400

        out_path = project_data_path("social_export_validation_last.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            write_json_result(out_path, report)
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "report": report,
                "output": str(out_path) if out_path else None,
            }
        )

    @bp.route("/api/capabilities/social_export/plan", methods=["POST"])
    def api_social_export_plan():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        base_dir = capability_base_dir(input_mode)
        from modules.capabilities.social_export import build_export_plan

        input_video_raw = str(payload.get("input_video", "") or "").strip()
        if input_video_raw:
            input_video = resolve_path_with_base(input_video_raw, base_dir=base_dir)
        else:
            if input_mode == "project":
                input_video = default_master_video_path()
                if input_video is None:
                    return jsonify({"error": "找不到可导出的母版视频"}), 404
            else:
                return jsonify({"error": "inline 模式需要 input_video"}), 400
        if not input_video.exists():
            return jsonify({"error": f"输入视频不存在: {input_video}"}), 404

        quality = str(payload.get("quality", "high") or "high").strip().lower()
        if quality not in {"low", "medium", "high", "lossless"}:
            quality = "high"
        strict_duration_limit = bool(payload.get("strict_duration_limit", True))
        ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
        platforms = parse_platforms(payload.get("platforms"))
        if not platforms:
            platforms = ["douyin", "xiaohongshu", "tiktok"]
        output_dir_raw = str(payload.get("output_dir", "") or "").strip()
        output_dir = (
            (base_dir / "output" / "social_exports")
            if not output_dir_raw
            else resolve_path_with_base(output_dir_raw, base_dir=base_dir)
        )
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)

        try:
            plan = build_export_plan(
                input_video=str(input_video),
                output_dir=str(output_dir),
                platform_ids=platforms,
                quality=quality,
                ffmpeg_bin=str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg"),
                ffprobe_bin=ffprobe_bin,
                strict_duration_limit=strict_duration_limit,
                profile_overrides=templates,
            )
        except Exception as exc:
            return jsonify({"error": f"导出计划生成失败: {exc}"}), 400

        plan_path = project_data_path("social_export_plan.json") if input_mode == "project" else None
        if plan_path is not None and bool(payload.get("store_result", True)):
            write_json_result(plan_path, plan)
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "plan": plan,
                "output": str(plan_path) if plan_path else None,
            }
        )

    @bp.route("/api/capabilities/social_export/run", methods=["POST"])
    def api_social_export_run():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        base_dir = capability_base_dir(input_mode)
        timeout_seconds = parse_float_param(payload.get("timeout_seconds", 3600), default=3600.0, min_val=10.0, max_val=7200.0)
        ffmpeg_bin = str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg")
        ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
        strict_duration_limit = bool(payload.get("strict_duration_limit", True))
        quality = str(payload.get("quality", "high") or "high").strip().lower()
        if quality not in {"low", "medium", "high", "lossless"}:
            quality = "high"
        platforms = parse_platforms(payload.get("platforms"))
        output_dir_raw = str(payload.get("output_dir", "") or "").strip()
        input_video_raw = str(payload.get("input_video", "") or "").strip()
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)

        job_id = str(uuid.uuid4())[:8]
        runner = build_social_export_runner(
            input_video_raw=input_video_raw,
            output_dir_raw=output_dir_raw,
            platforms=platforms,
            quality=quality,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
            strict_duration_limit=strict_duration_limit,
            timeout_seconds=timeout_seconds,
            job_id=job_id,
            profile_overrides=templates,
            input_mode=input_mode,
            base_dir=base_dir,
            persist_history=(input_mode == "project"),
        )
        run_in_bg(job_id, runner, kind="social_export")
        return jsonify({"ok": True, "input_mode": input_mode, "job_id": job_id, "task_queue": task_queue_snapshot()})

    @bp.route("/api/capabilities/social_export/rerun", methods=["POST"])
    def api_social_export_rerun():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        batch_id = str(payload.get("batch_id", "") or "").strip()
        record = payload.get("batch") if isinstance(payload.get("batch"), dict) else None
        if record is None and batch_id:
            history = get_social_export_history() if input_mode == "project" else []
            record = next((x for x in reversed(history) if str(x.get("batch_id", "")) == batch_id), None)
        if record is None:
            if input_mode == "inline":
                return jsonify({"error": "inline rerun 需要 batch（或切换 project 模式并提供 batch_id）"}), 400
            if not batch_id:
                return jsonify({"error": "batch_id 不能为空"}), 400
            return jsonify({"error": f"未找到批次: {batch_id}"}), 404

        base_dir = capability_base_dir(input_mode)
        input_video_raw = str(payload.get("input_video", record.get("input_video", "")) or "")
        output_dir_raw = str(payload.get("output_dir", record.get("output_dir", "")) or "")
        quality = str(payload.get("quality", record.get("quality", "high")) or "high").strip().lower()
        if quality not in {"low", "medium", "high", "lossless"}:
            quality = "high"
        strict_duration_limit = bool(payload.get("strict_duration_limit", record.get("strict_duration_limit", True)))
        ffmpeg_bin = str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg")
        ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
        timeout_seconds = parse_float_param(payload.get("timeout_seconds", 3600), default=3600.0, min_val=10.0, max_val=7200.0)
        platforms = parse_platforms(payload.get("platforms", record.get("platforms", [])))
        templates = coerce_social_export_overrides(payload, input_mode=input_mode)

        job_id = str(uuid.uuid4())[:8]
        runner = build_social_export_runner(
            input_video_raw=input_video_raw,
            output_dir_raw=output_dir_raw,
            platforms=platforms,
            quality=quality,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
            strict_duration_limit=strict_duration_limit,
            timeout_seconds=timeout_seconds,
            job_id=job_id,
            profile_overrides=templates,
            input_mode=input_mode,
            base_dir=base_dir,
            persist_history=(input_mode == "project"),
        )
        run_in_bg(job_id, runner, kind="social_export")
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "job_id": job_id,
                "rerun_from": batch_id or record.get("batch_id", ""),
                "task_queue": task_queue_snapshot(),
            }
        )

    return bp
