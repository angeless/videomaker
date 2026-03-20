#!/usr/bin/env python3
"""Capability routes: content_publish."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional
import uuid

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_int_param, parse_str_param, write_json_result


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
    idempotency_lookup: Optional[Callable] = None,
    idempotency_put_success: Optional[Callable] = None,
    idempotency_make_cache_key: Optional[Callable] = None,
) -> Blueprint:
    bp = Blueprint("cap_content_publish_api", __name__)

    @bp.route("/api/capabilities/content_publish/platforms", methods=["GET"])
    def api_content_publish_platforms():
        from modules.capabilities.content_publish import list_publish_platforms

        connectors = resolve_content_publish_connectors({})
        return jsonify({"ok": True, **list_publish_platforms(connectors=connectors)})

    @bp.route("/api/capabilities/content_publish/session/bootstrap", methods=["POST"])
    def api_content_publish_session_bootstrap():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if project_dir_getter() is None and input_mode == "project":
            return jsonify({"error": "项目未加载"}), 400

        from modules.capabilities.content_publish import bootstrap_publish_session

        session = bootstrap_publish_session(
            actor_id=parse_str_param(payload.get("actor_id", "")),
            session_id=parse_str_param(payload.get("session_id", "")),
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
        session_id = parse_str_param(payload.get("session_id", ""))
        session = sessions.get(session_id, {}) if session_id else {}
        plan = build_publish_plan(
            content=content_payload,
            platform_ids=platforms,
            platform_content_type=parse_str_param(payload.get("platform_content_type", "video_post"), default="video_post"),
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
            write_json_result(project_data_path("content_publish_plan_last.json"), plan_record)
        return jsonify({"ok": True, "plan": plan_record})

    @bp.route("/api/capabilities/content_publish/run", methods=["POST"])
    def api_content_publish_run():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        from modules.capabilities.content_publish import run_publish_plan, _build_publish_idempotency_digest

        plan = payload.get("plan", {}) if isinstance(payload.get("plan"), dict) else {}
        if not plan:
            plan = read_project_json("content_publish_plan_last.json", fallback={}) if project_dir_getter() is not None else {}
        if not isinstance(plan, dict) or not plan:
            return jsonify({"error": "缺少 plan，请先调用 /api/capabilities/content_publish/plan"}), 400

        sessions = read_content_publish_sessions() if project_dir_getter() is not None else {}
        session_id = parse_str_param(payload.get("session_id", ""))
        if not session_id:
            session_id = str(plan.get("session", {}).get("session_id", "") if isinstance(plan.get("session"), dict) else "")
        session = sessions.get(session_id, {}) if session_id else {}
        connectors = resolve_content_publish_connectors(payload)
        run_dry = bool(payload.get("dry_run", plan.get("dry_run", False)))
        output_root = parse_str_param(payload.get("output_root", ""))
        if not output_root and project_dir_getter() is not None:
            output_root = str((project_dir_getter() / "output" / "content_publish").resolve())

        # ── idempotency guard ──
        cache_key = None
        if idempotency_lookup is not None and idempotency_make_cache_key is not None:
            digest = _build_publish_idempotency_digest(plan, connectors, run_dry)
            cache_key = idempotency_make_cache_key(
                "/capabilities/content_publish/run",
                {"actor_id": "", "idempotency_key": digest},
            )
            hit, source = idempotency_lookup(cache_key)
            if hit is not None:
                return jsonify({**hit.get("body", {}), "idempotency_replay": True, "idempotency_source": source})

        result = run_publish_plan(
            plan=plan,
            session=session,
            dry_run=run_dry,
            rerun_failed_only=bool(payload.get("rerun_failed_only", False)),
            random_seed=payload.get("random_seed", 7),
            connectors=connectors,
            output_root=output_root,
        )

        run_record = {
            "run_id": str(uuid.uuid4())[:10],
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "input_mode": input_mode,
            "plan_id": parse_str_param(plan.get("plan_id", "")),
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
            write_json_result(project_data_path("content_publish_run_last.json"), run_record)

        from modules.app_api.services.audit_log import audit as _audit
        summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
        _audit("publish_run", "content_publish", run_record["run_id"],
               actor=f"local:{request.remote_addr}",
               detail={
                   "dry_run": bool(run_dry),
                   "connector_count": len(connectors),
                   "posted": summary.get("posted", 0),
                   "failed": summary.get("failed", 0),
                   "blocked": summary.get("blocked", 0),
               })

        # ── publish_blocked 审计 ──
        if summary.get("blocked", 0) > 0:
            blocked_platforms = [
                s.get("platform_id", "") for s in (result.get("steps") or [])
                if isinstance(s, dict) and s.get("run_state") == "blocked"
            ]
            _audit("publish_blocked", "content_publish", run_record["run_id"],
                   actor=f"local:{request.remote_addr}", status="blocked",
                   detail={"platforms": blocked_platforms[:10]})

        # ── publish_error 审计（逐条，detail 只保留摘要）──
        if summary.get("failed", 0) > 0:
            for step in (result.get("steps") or []):
                if not isinstance(step, dict) or step.get("run_state") != "failed":
                    continue
                ed = step.get("error_detail", {}) if isinstance(step.get("error_detail"), dict) else {}
                _audit("publish_error", "content_publish", run_record["run_id"],
                       actor=f"local:{request.remote_addr}", status="error",
                       detail={
                           "platform": step.get("platform_id", ""),
                           "error_class": ed.get("error_class", "unknown"),
                           "error": str(step.get("error", ""))[:200],
                           "dry_run": bool(run_dry),
                       })

        # ── idempotency: 只缓存明确成功的结果 ──
        response_body = {
            "ok": True,
            "run": run_record,
            "state": result.get("status"),
            "auth_required": str(result.get("status", "")).lower() == "waiting_auth",
            "auth_hint": "会话过期，请扫码续登后重试" if str(result.get("status", "")).lower() == "waiting_auth" else "",
        }
        if (
            cache_key is not None
            and idempotency_put_success is not None
            and result.get("status") in ("posted", "planned")
            and summary.get("failed", 0) == 0
            and summary.get("blocked", 0) == 0
        ):
            idempotency_put_success(cache_key, status=200, body=response_body)

        return jsonify(response_body)

    @bp.route("/api/capabilities/content_publish/rerun", methods=["POST"])
    def api_content_publish_rerun():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        run_id = parse_str_param(payload.get("run_id", ""))
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
        session_id = parse_str_param(payload.get("session_id", ""))
        if not session_id:
            session_id = str(plan.get("session", {}).get("session_id", "") if isinstance(plan.get("session"), dict) else "")
        session = sessions.get(session_id, {}) if session_id else {}
        connectors = resolve_content_publish_connectors(payload)
        output_root = parse_str_param(payload.get("output_root", ""))
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
            "plan_id": parse_str_param(plan.get("plan_id", "")),
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
            write_json_result(project_data_path("content_publish_run_last.json"), run_record)
        from modules.app_api.services.audit_log import audit as _audit
        _audit("publish_rerun", "content_publish", run_record["run_id"], actor=f"local:{request.remote_addr}", detail={"source_run_id": run_id, "connector_count": len(connectors)})

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

    @bp.route("/api/capabilities/content_publish/history", methods=["GET"])
    def api_content_publish_history():
        if project_dir_getter() is None:
            return jsonify({"ok": True, "runs": []})
        history = read_content_publish_history()
        pf = parse_str_param(request.args.get("platform"), default="")
        sf = parse_str_param(request.args.get("status"), default="")
        lim = parse_int_param(request.args.get("limit"), default=50, min_val=1, max_val=300)
        if pf:
            history = [r for r in history if pf in str(r.get("platforms", r.get("platform_ids", [])))]
        if sf:
            history = [r for r in history if r.get("result", {}).get("status") == sf or r.get("status") == sf]
        history = list(reversed(history))[:lim]
        return jsonify({"ok": True, "runs": history, "total": len(history)})

    return bp

