#!/usr/bin/env python3
"""Agent skill invoke routes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List
import uuid

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_str_param


def create_agent_skill_blueprint(
    *,
    jobs_getter: Callable[[], Dict[str, Dict[str, Any]]],
    parse_request_context: Callable[[], Dict[str, Any]],
    agent_skill_registry_getter: Callable[[], Dict[str, Dict[str, Any]]],
    list_agent_skills: Callable[[], List[Dict[str, Any]]],
    apply_agent_capability_input_defaults: Callable[[str, Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    normalize_skill_retry_policy: Callable[[Dict[str, Any]], Dict[str, Any]],
    normalize_skill_timeout_seconds: Callable[[Any, float], float],
    execute_agent_skill: Callable[..., Dict[str, Any]],
    run_in_bg: Callable[..., None],
    extract_template_ids_from_value: Callable[[Any], List[str]],
) -> Blueprint:
    bp = Blueprint("agent_skill_api", __name__)

    @bp.route("/api/agent/skills/invoke", methods=["POST"])
    def api_agent_skills_invoke():
        # Round-15.6: dict-type guard. A JSON array body would crash on
        # payload.get(); a JSON null becomes {} via the legacy `or {}`,
        # but other shapes (string/number) still passed through. Treat
        # any non-dict body as empty.
        payload = request.json
        if not isinstance(payload, dict):
            payload = {}
        request_ctx = parse_request_context()
        skill_id = parse_str_param(payload.get("skill_id", ""))
        if not skill_id:
            return jsonify({"error": "skill_id 不能为空"}), 400

        skill_spec = agent_skill_registry_getter().get(skill_id)
        if not isinstance(skill_spec, dict):
            return jsonify({
                "error": f"不支持的 skill_id: {skill_id}",
                "available_skills": [x.get("skill_id") for x in list_agent_skills()],
            }), 400

        input_payload = payload.get("input", {})
        if input_payload is None:
            input_payload = {}
        if not isinstance(input_payload, dict):
            return jsonify({"error": "input 必须是对象"}), 400
        input_payload = apply_agent_capability_input_defaults(
            str(skill_spec.get("capability_id", "") or ""),
            input_payload,
            skill_spec.get("default_input", {}),
        )

        retry_policy = normalize_skill_retry_policy(payload.get("retry_policy", {}))
        timeout_seconds = normalize_skill_timeout_seconds(payload.get("timeout_seconds", 120), default=120.0)

        method = parse_str_param(skill_spec.get("method", "POST"), default="POST").upper()
        endpoint = parse_str_param(skill_spec.get("endpoint", ""))
        if not endpoint:
            return jsonify({"error": f"skill 配置缺少 endpoint: {skill_id}"}), 500

        job_id = str(uuid.uuid4())[:8]
        invoke_id = str(uuid.uuid4())[:8]
        jobs = jobs_getter()

        def _do_invoke():
            # Round-15.6: defensive setdefault — if run_in_bg's contract
            # changes such that the worker fires before the jobs[job_id]
            # slot is initialized, a raw assignment to jobs[job_id]["progress"]
            # would 500 the worker (no slot yet) and corrupt the job log.
            # setdefault guarantees a sane starting record either way.
            slot = jobs.setdefault(
                job_id,
                {"status": "running", "progress": 0, "log": [], "kind": "agent_skill"},
            )
            slot.setdefault("log", []).append(
                f"[AgentSkill] invoke_id={invoke_id} skill_id={skill_id}"
            )
            slot["log"].append(f"[AgentSkill] 调用 {method} {endpoint}")
            slot["progress"] = 8
            ret = execute_agent_skill(
                skill_id=skill_id,
                input_payload=input_payload,
                retry_policy=retry_policy,
                timeout_seconds=timeout_seconds,
                request_context=request_ctx,
                logger=lambda msg: slot["log"].append(f"[AgentSkill] {msg}"),
            )
            slot["progress"] = 95
            ret["invoke_id"] = invoke_id
            return ret

        run_in_bg(
            job_id,
            _do_invoke,
            kind="agent_skill",
            job_meta={
                "actor_type": str(request_ctx.get("actor_type", "") or ""),
                "actor_id": str(request_ctx.get("actor_id", "") or ""),
                "trace_id": str(request_ctx.get("trace_id", "") or ""),
                "task_mode": "skill_invoke",
                "skill_id": skill_id,
                "capability_id": str(skill_spec.get("capability_id", "") or ""),
                "template_hits": extract_template_ids_from_value(payload),
                "replay": {
                    "method": "POST",
                    "endpoint": "/api/agent/skills/invoke",
                    "payload": deepcopy(payload),
                    "request_context": deepcopy(request_ctx),
                },
            },
        )
        return jsonify({
            "ok": True,
            "job_id": job_id,
            "invoke_id": invoke_id,
            "skill_id": skill_id,
            "skill_name": str(skill_spec.get("name", "") or ""),
            "capability_id": str(skill_spec.get("capability_id", "") or ""),
            "primary_call": {
                "method": method,
                "endpoint": endpoint,
            },
            "retry_policy": retry_policy,
            "timeout_seconds": timeout_seconds,
            "status_endpoint": f"/api/agent/tasks/{job_id}",
        })

    return bp
