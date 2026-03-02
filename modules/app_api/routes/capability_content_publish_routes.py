#!/usr/bin/env python3
"""Capability routes: content_publish."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict
import json
import uuid

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_int_param


def create_content_publish_capability_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    parse_capability_input_mode: Callable[[Any, str], str],
    parse_platforms: Callable[[Any], list],
    resolve_content_publish_content: Callable[[Dict[str, Any], str], Dict[str, Any]],
    resolve_content_publish_connectors: Callable[[Dict[str, Any]], Dict[str, Any]],
    read_content_publish_sessions: Callable[[], Dict[str, Dict[str, Any]]],
    save_content_publish_sessions: Callable[[Dict[str, Dict[str, Any]]], None],
    read_content_publish_history: Callable[[], list],
    save_content_publish_history: Callable[[list], None],
    read_project_json: Callable[[str, Any], Any],
    project_data_path: Callable[[str], Any],
) -> Blueprint:
    bp = Blueprint("cap_content_publish_api", __name__)

    @bp.route("/api/capabilities/content_publish/platforms", methods=["GET"])
    def api_content_publish_platforms():
        from modules.capabilities.content_publish import list_publish_platforms

        return jsonify({"ok": True, **list_publish_platforms()})

    @bp.route("/api/capabilities/content_publish/session/bootstrap", methods=["POST"])
    def api_content_publish_session_bootstrap():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if project_dir_getter() is None and input_mode == "project":
            return jsonify({"error": "项目未加载"}), 400

        from modules.capabilities.content_publish import bootstrap_publish_session

        session = bootstrap_publish_session(
            actor_id=str(payload.get("actor_id", "") or "").strip(),
            session_id=str(payload.get("session_id", "") or "").strip(),
            authenticated=bool(payload.get("authenticated", False)),
            expires_in_minutes=parse_int_param(payload.get("expires_in_minutes", 120), default=120, min_val=1, max_val=43200),
        )
        sessions = read_content_publish_sessions() if project_dir_getter() is not None else {}
        sessions[str(session.get("session_id"))] = session
        if project_dir_getter() is not None:
            save_content_publish_sessions(sessions)
        return jsonify({"ok": True, "session": session})

    @bp.route("/api/capabilities/content_publish/plan", methods=["POST"])
    def api_content_publish_plan():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        from modules.capabilities.content_publish import build_publish_plan

        platforms = parse_platforms(payload.get("platforms", payload.get("platform_ids", [])))
        content_payload = resolve_content_publish_content(payload, input_mode=input_mode)
        connectors = resolve_content_publish_connectors(payload)
        sessions = read_content_publish_sessions() if project_dir_getter() is not None else {}
        session_id = str(payload.get("session_id", "") or "").strip()
        session = sessions.get(session_id, {}) if session_id else {}
        plan = build_publish_plan(
            content=content_payload,
            platform_ids=platforms,
            platform_content_type=str(payload.get("platform_content_type", "video_post") or "video_post"),
            dry_run=bool(payload.get("dry_run", True)),
            session=session,
            humanization=payload.get("humanization", {}) if isinstance(payload.get("humanization"), dict) else {},
            connectors=connectors,
        )
        plan_record = {
            "plan_id": str(uuid.uuid4())[:10],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "input_mode": input_mode,
            "connector_count": len(connectors),
            **plan,
        }
        if project_dir_getter() is not None:
            out = project_data_path("content_publish_plan_last.json")
            if out is not None:
                out.write_text(json.dumps(plan_record, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "plan": plan_record})

    @bp.route("/api/capabilities/content_publish/run", methods=["POST"])
    def api_content_publish_run():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        from modules.capabilities.content_publish import run_publish_plan

        plan = payload.get("plan", {}) if isinstance(payload.get("plan"), dict) else {}
        if not plan:
            plan = read_project_json("content_publish_plan_last.json", fallback={}) if project_dir_getter() is not None else {}
        if not isinstance(plan, dict) or not plan:
            return jsonify({"error": "缺少 plan，请先调用 /api/capabilities/content_publish/plan"}), 400

        sessions = read_content_publish_sessions() if project_dir_getter() is not None else {}
        session_id = str(payload.get("session_id", "") or "").strip()
        if not session_id:
            session_id = str(plan.get("session", {}).get("session_id", "") if isinstance(plan.get("session"), dict) else "")
        session = sessions.get(session_id, {}) if session_id else {}
        connectors = resolve_content_publish_connectors(payload)
        output_root = str(payload.get("output_root", "") or "").strip()
        if not output_root and project_dir_getter() is not None:
            output_root = str((project_dir_getter() / "output" / "content_publish").resolve())

        result = run_publish_plan(
            plan=plan,
            session=session,
            dry_run=bool(payload.get("dry_run", plan.get("dry_run", False))),
            rerun_failed_only=bool(payload.get("rerun_failed_only", False)),
            random_seed=payload.get("random_seed", 7),
            connectors=connectors,
            output_root=output_root,
        )

        run_record = {
            "run_id": str(uuid.uuid4())[:10],
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "input_mode": input_mode,
            "plan_id": str(plan.get("plan_id", "") or ""),
            "plan": plan,
            "connector_count": len(connectors),
            "output_root": output_root,
            "result": result,
        }
        history = read_content_publish_history() if project_dir_getter() is not None else []
        history.append(run_record)
        history = history[-300:]
        if project_dir_getter() is not None:
            save_content_publish_history(history)
            out = project_data_path("content_publish_run_last.json")
            if out is not None:
                out.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")
        waiting_auth = str(result.get("status", "")).lower() == "waiting_auth"
        return jsonify(
            {
                "ok": True,
                "run": run_record,
                "state": result.get("status"),
                "auth_required": waiting_auth,
                "auth_hint": "会话过期，请扫码续登后重试" if waiting_auth else "",
            }
        )

    @bp.route("/api/capabilities/content_publish/rerun", methods=["POST"])
    def api_content_publish_rerun():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        run_id = str(payload.get("run_id", "") or "").strip()
        if not run_id:
            return jsonify({"error": "run_id 不能为空"}), 400

        history = read_content_publish_history() if project_dir_getter() is not None else []
        base = next((x for x in reversed(history) if str(x.get("run_id", "") or "") == run_id), None)
        if not isinstance(base, dict):
            return jsonify({"error": f"未找到 run_id={run_id}"}), 404

        from modules.capabilities.content_publish import run_publish_plan

        plan = base.get("plan", {}) if isinstance(base.get("plan"), dict) else {}
        if not plan:
            return jsonify({"error": f"run_id={run_id} 缺少可复跑 plan"}), 400

        sessions = read_content_publish_sessions() if project_dir_getter() is not None else {}
        session_id = str(payload.get("session_id", "") or "").strip()
        if not session_id:
            session_id = str(plan.get("session", {}).get("session_id", "") if isinstance(plan.get("session"), dict) else "")
        session = sessions.get(session_id, {}) if session_id else {}
        connectors = resolve_content_publish_connectors(payload)
        output_root = str(payload.get("output_root", "") or "").strip()
        if not output_root and project_dir_getter() is not None:
            output_root = str((project_dir_getter() / "output" / "content_publish").resolve())

        result = run_publish_plan(
            plan=plan,
            session=session,
            dry_run=bool(payload.get("dry_run", False)),
            rerun_failed_only=bool(payload.get("rerun_failed_only", True)),
            random_seed=payload.get("random_seed", 7),
            connectors=connectors,
            output_root=output_root,
        )
        run_record = {
            "run_id": str(uuid.uuid4())[:10],
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "input_mode": input_mode,
            "plan_id": str(plan.get("plan_id", "") or ""),
            "plan": plan,
            "connector_count": len(connectors),
            "output_root": output_root,
            "result": result,
            "rerun_from": run_id,
        }
        history.append(run_record)
        history = history[-300:]
        if project_dir_getter() is not None:
            save_content_publish_history(history)
            out = project_data_path("content_publish_run_last.json")
            if out is not None:
                out.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")

        waiting_auth = str(result.get("status", "")).lower() == "waiting_auth"
        return jsonify(
            {
                "ok": True,
                "run": run_record,
                "state": result.get("status"),
                "auth_required": waiting_auth,
                "auth_hint": "会话过期，请扫码续登后重试" if waiting_auth else "",
                "rerun_from": run_id,
            }
        )

    return bp

