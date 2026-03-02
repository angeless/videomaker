#!/usr/bin/env python3
"""Agent task plan/run routes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from typing import Any, Callable, Dict, List
import time
import uuid

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_float_param, parse_int_param, parse_str_param


def create_agent_task_run_blueprint(
    *,
    jobs_getter: Callable[[], Dict[str, Dict[str, Any]]],
    parse_request_context: Callable[[], Dict[str, str]],
    normalize_skill_budget_limit: Callable[[Any], Dict[str, int]],
    normalize_agent_skill_steps: Callable[..., List[Dict[str, Any]]],
    normalize_skill_timeout_seconds: Callable[[Any, float], float],
    apply_governance_to_skill_flow: Callable[..., Dict[str, Any]],
    apply_agent_capability_input_defaults: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    agent_capability_route_map: Callable[[], Dict[str, Dict[str, str]]],
    resolve_agent_primary_call: Callable[[str, Dict[str, str], str], Dict[str, str]],
    invoke_agent_primary_call: Callable[..., Dict[str, Any]],
    should_run_conditional_step: Callable[[Dict[str, Any], Dict[str, Dict[str, Any]]], Any],
    execute_agent_skill: Callable[..., Dict[str, Any]],
    record_governance_usage_for_skill_flow: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    extract_template_ids_from_value: Callable[[Any], List[str]],
    run_in_bg: Callable[..., None],
) -> Blueprint:
    bp = Blueprint("agent_task_run_api", __name__)

    @bp.route("/api/agent/tasks/plan", methods=["POST"])
    def api_agent_tasks_plan():
        payload = request.json or {}
        request_ctx = parse_request_context()
        mode_hint = parse_str_param(payload.get("mode", "")).lower()
        strategy = parse_str_param(payload.get("strategy", "sequential"), default="sequential").lower()
        task_id = str(uuid.uuid4())[:8]
        dry_run = bool(payload.get("dry_run", True))

        skills_raw = payload.get("skills", None)
        if mode_hint == "skill_sequence" or isinstance(skills_raw, list):
            if strategy not in {"sequential", "parallel", "conditional"}:
                return jsonify({"error": "strategy 仅支持 sequential/parallel/conditional"}), 400
            explicit_max_parallel = "max_parallel" in payload
            requested_max_parallel = parse_int_param(payload.get("max_parallel", 4), default=4, min_val=1, max_val=8)
            requested_budget = normalize_skill_budget_limit(payload.get("budget_limit", {}))
            try:
                steps = normalize_agent_skill_steps(
                    skills_raw,
                    default_retry_policy=payload.get("retry_policy", {}),
                    default_timeout_seconds=normalize_skill_timeout_seconds(payload.get("timeout_seconds", 120), default=120.0),
                )
            except Exception as exc:
                return jsonify({"error": f"skills 解析失败: {exc}"}), 400
            try:
                governance_applied = apply_governance_to_skill_flow(
                    actor_id=str(request_ctx.get("actor_id", "") or ""),
                    steps=steps,
                    requested_budget=requested_budget,
                    requested_max_parallel=requested_max_parallel,
                    explicit_max_parallel=explicit_max_parallel,
                )
            except Exception as exc:
                return jsonify({"error": f"治理校验失败: {exc}"}), 400
            max_parallel = parse_int_param(governance_applied.get("max_parallel", 1), default=1, min_val=1, max_val=8)
            budget_limit = governance_applied.get("budget_limit", {}) if isinstance(governance_applied.get("budget_limit"), dict) else {}
            governance = governance_applied.get("governance", {}) if isinstance(governance_applied.get("governance"), dict) else {}

            plan = {
                "task_id": task_id,
                "mode": "skill_sequence",
                "dry_run": dry_run,
                "skill_flow": {
                    "strategy": strategy,
                    "max_parallel": max_parallel,
                    "budget_limit": budget_limit,
                    "governance": governance,
                    "steps": steps,
                },
            }
            return jsonify({
                "ok": True,
                "task_plan": plan,
                "plan_summary": {
                    "task_id": task_id,
                    "mode": "skill_sequence",
                    "strategy": strategy,
                    "total_steps": len(steps),
                    "max_parallel": max_parallel if strategy == "parallel" else 1,
                    "budget_limit": budget_limit,
                    "governance": governance,
                    "conditional_steps": sum(1 for x in steps if isinstance(x.get("condition"), dict) and x.get("condition")),
                },
            })

        capability_id = parse_str_param(payload.get("capability_id", ""))
        input_payload = payload.get("input", {})
        if not capability_id:
            return jsonify({"error": "capability_id 不能为空（或使用 mode=skill_sequence + skills）"}), 400
        if not isinstance(input_payload, dict):
            return jsonify({"error": "input 必须是对象"}), 400
        input_payload = apply_agent_capability_input_defaults(capability_id, input_payload)

        route_map = agent_capability_route_map()
        routes = route_map.get(capability_id)
        if not isinstance(routes, dict) or not routes:
            return jsonify({"error": f"不支持的 capability_id: {capability_id}"}), 400

        primary = routes.get("plan") or routes.get("draft") or routes.get("list") or next(iter(routes.values()))
        method, endpoint = primary.split(" ", 1) if " " in primary else ("POST", primary)

        plan = {
            "task_id": task_id,
            "capability_id": capability_id,
            "mode": "single_capability",
            "primary_call": {
                "method": method,
                "endpoint": endpoint,
                "payload": input_payload,
            },
            "available_routes": routes,
            "dry_run": dry_run,
        }
        return jsonify({
            "ok": True,
            "task_plan": plan,
            "plan_summary": {
                "task_id": task_id,
                "capability_id": capability_id,
                "primary_endpoint": endpoint,
                "available_route_count": len(routes),
            },
        })

    @bp.route("/api/agent/tasks/run", methods=["POST"])
    def api_agent_tasks_run():
        payload = request.json or {}
        task_plan = payload.get("task_plan", {}) if isinstance(payload.get("task_plan"), dict) else {}
        request_ctx = parse_request_context()
        mode_hint = str(payload.get("mode", "") or task_plan.get("mode", "") or "").strip().lower()
        dry_run = bool(payload.get("dry_run", task_plan.get("dry_run", False)))
        task_id = str(task_plan.get("task_id", "") or "") if isinstance(task_plan, dict) else ""
        if not task_id:
            task_id = str(uuid.uuid4())[:8]
        job_id = str(uuid.uuid4())[:8]

        jobs = jobs_getter()
        plan_skill_flow = task_plan.get("skill_flow", {}) if isinstance(task_plan.get("skill_flow"), dict) else {}
        skills_raw = payload.get("skills", None)
        if skills_raw is None:
            skills_raw = plan_skill_flow.get("steps", None)
        if mode_hint == "skill_sequence" or isinstance(skills_raw, list):
            strategy = str(payload.get("strategy", "") or plan_skill_flow.get("strategy", "sequential") or "sequential").strip().lower()
            if strategy not in {"sequential", "parallel", "conditional"}:
                return jsonify({"error": "strategy 仅支持 sequential/parallel/conditional"}), 400
            explicit_max_parallel = ("max_parallel" in payload) or ("max_parallel" in plan_skill_flow)
            requested_max_parallel = parse_int_param(payload.get("max_parallel", plan_skill_flow.get("max_parallel", 4)), default=4, min_val=1, max_val=8)
            requested_budget = normalize_skill_budget_limit(payload.get("budget_limit", plan_skill_flow.get("budget_limit", {})))
            try:
                steps = normalize_agent_skill_steps(
                    skills_raw,
                    default_retry_policy=payload.get("retry_policy", plan_skill_flow.get("retry_policy", {})),
                    default_timeout_seconds=normalize_skill_timeout_seconds(
                        payload.get("timeout_seconds", plan_skill_flow.get("timeout_seconds", 120)),
                        default=120.0,
                    ),
                )
            except Exception as exc:
                return jsonify({"error": f"skills 解析失败: {exc}"}), 400
            try:
                governance_applied = apply_governance_to_skill_flow(
                    actor_id=str(request_ctx.get("actor_id", "") or ""),
                    steps=steps,
                    requested_budget=requested_budget,
                    requested_max_parallel=requested_max_parallel,
                    explicit_max_parallel=explicit_max_parallel,
                )
            except Exception as exc:
                return jsonify({"error": f"治理校验失败: {exc}"}), 400
            max_parallel = parse_int_param(governance_applied.get("max_parallel", 1), default=1, min_val=1, max_val=8)
            budget_limit = governance_applied.get("budget_limit", {}) if isinstance(governance_applied.get("budget_limit"), dict) else {}
            governance = governance_applied.get("governance", {}) if isinstance(governance_applied.get("governance"), dict) else {}

            if strategy == "parallel":
                has_condition = any(
                    isinstance(step.get("condition"), dict) and bool(step.get("condition"))
                    for step in steps
                )
                if has_condition:
                    return jsonify({"error": "strategy=parallel 暂不支持 step.condition，请改用 strategy=conditional"}), 400

            steps_run = deepcopy(steps)
            if dry_run:
                for step in steps_run:
                    if str(step.get("method", "")).upper() != "GET":
                        inp = step.get("input", {})
                        if isinstance(inp, dict) and "dry_run" not in inp:
                            inp["dry_run"] = True

            def _run_one_step(idx: int, step: Dict[str, Any]) -> Dict[str, Any]:
                skill_id = str(step.get("skill_id", "") or "")
                step_id = str(step.get("step_id", f"step_{idx:02d}") or f"step_{idx:02d}")
                jobs[job_id]["log"].append(f"[AgentSkillFlow] {idx}/{len(steps_run)} step_id={step_id} skill={skill_id}")
                try:
                    result = execute_agent_skill(
                        skill_id=skill_id,
                        input_payload=step.get("input", {}) if isinstance(step.get("input"), dict) else {},
                        retry_policy=step.get("retry_policy", {}) if isinstance(step.get("retry_policy"), dict) else {},
                        timeout_seconds=parse_float_param(step.get("timeout_seconds", 120.0), default=120.0, min_val=1.0, max_val=3600.0),
                        request_context=request_ctx,
                        logger=lambda msg, sid=step_id: jobs[job_id]["log"].append(f"[AgentSkillFlow:{sid}] {msg}"),
                    )
                    result["step_id"] = step_id
                    result["index"] = idx
                    result["status"] = "done"
                    result["continue_on_error"] = bool(step.get("continue_on_error", False))
                    result["condition"] = deepcopy(step.get("condition", {})) if isinstance(step.get("condition"), dict) else {}
                    return result
                except Exception as exc:
                    err = str(exc)
                    failure_item = {
                        "step_id": step_id,
                        "index": idx,
                        "skill_id": skill_id,
                        "skill_name": str(step.get("skill_name", "") or ""),
                        "capability_id": str(step.get("capability_id", "") or ""),
                        "status": "error",
                        "continue_on_error": bool(step.get("continue_on_error", False)),
                        "error": err,
                        "condition": deepcopy(step.get("condition", {})) if isinstance(step.get("condition"), dict) else {},
                    }
                    jobs[job_id]["log"].append(f"[AgentSkillFlow:{step_id}] 失败: {err}")
                    return failure_item

            def _do_run_skill_sequence():
                jobs[job_id]["progress"] = 6
                jobs[job_id]["log"].append(
                    f"[Agent] task_id={task_id} mode=skill_sequence strategy={strategy}"
                )
                started = time.monotonic()
                step_results: List[Dict[str, Any]] = []
                previous_by_step: Dict[str, Dict[str, Any]] = {}
                total = len(steps_run)
                if strategy in {"sequential", "conditional"}:
                    for idx, step in enumerate(steps_run, start=1):
                        elapsed = time.monotonic() - started
                        if budget_limit.get("max_duration_seconds", 0) > 0 and elapsed > int(budget_limit.get("max_duration_seconds", 0)):
                            raise RuntimeError(
                                f"预算超限: max_duration_seconds={budget_limit.get('max_duration_seconds')}"
                            )
                        jobs[job_id]["progress"] = min(10 + int((idx - 1) * 80 / max(total, 1)), 88)
                        step_id = str(step.get("step_id", f"step_{idx:02d}") or f"step_{idx:02d}")
                        if strategy == "conditional":
                            should_run, skip_reason = should_run_conditional_step(
                                step.get("condition", {}) if isinstance(step.get("condition"), dict) else {},
                                previous_by_step,
                            )
                            if not should_run:
                                skipped_item = {
                                    "step_id": step_id,
                                    "index": idx,
                                    "skill_id": str(step.get("skill_id", "") or ""),
                                    "skill_name": str(step.get("skill_name", "") or ""),
                                    "capability_id": str(step.get("capability_id", "") or ""),
                                    "status": "skipped",
                                    "continue_on_error": bool(step.get("continue_on_error", False)),
                                    "skip_reason": skip_reason,
                                    "condition": deepcopy(step.get("condition", {})),
                                }
                                step_results.append(skipped_item)
                                previous_by_step[step_id] = skipped_item
                                jobs[job_id]["log"].append(f"[AgentSkillFlow:{step_id}] 跳过: {skip_reason}")
                                continue
                        item = _run_one_step(idx, step)
                        step_results.append(item)
                        previous_by_step[step_id] = item
                        failed_now = sum(1 for x in step_results if x.get("status") == "error")
                        if budget_limit.get("max_failures", 0) > 0 and failed_now > int(budget_limit.get("max_failures", 0)):
                            raise RuntimeError(
                                f"预算超限: max_failures={budget_limit.get('max_failures')}"
                            )
                        if item.get("status") == "error" and not bool(item.get("continue_on_error", False)):
                            raise RuntimeError(f"step={item.get('step_id')} 执行失败: {item.get('error')}")
                else:
                    workers = min(max_parallel, max(total, 1))
                    jobs[job_id]["log"].append(f"[AgentSkillFlow] 并行执行 workers={workers}")
                    ordered: Dict[int, Dict[str, Any]] = {}
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        future_map = {
                            pool.submit(_run_one_step, idx, step): idx
                            for idx, step in enumerate(steps_run, start=1)
                        }
                        completed = 0
                        for fut in as_completed(future_map):
                            idx = future_map[fut]
                            try:
                                item = fut.result()
                            except Exception as exc:  # pragma: no cover
                                item = {
                                    "step_id": f"step_{idx:02d}",
                                    "index": idx,
                                    "skill_id": "",
                                    "status": "error",
                                    "continue_on_error": False,
                                    "error": str(exc),
                                }
                            ordered[idx] = item
                            completed += 1
                            jobs[job_id]["progress"] = min(12 + int(completed * 76 / max(total, 1)), 90)
                    step_results = [ordered[i] for i in sorted(ordered.keys())]
                    blocking = [x for x in step_results if x.get("status") == "error" and not bool(x.get("continue_on_error", False))]
                    if blocking:
                        first = blocking[0]
                        raise RuntimeError(f"parallel step={first.get('step_id')} 执行失败: {first.get('error')}")

                failed = sum(1 for x in step_results if x.get("status") == "error")
                skipped = sum(1 for x in step_results if x.get("status") == "skipped")
                success = sum(1 for x in step_results if x.get("status") == "done")
                if budget_limit.get("max_failures", 0) > 0 and failed > int(budget_limit.get("max_failures", 0)):
                    raise RuntimeError(f"预算超限: max_failures={budget_limit.get('max_failures')}")
                elapsed_total = time.monotonic() - started
                if budget_limit.get("max_duration_seconds", 0) > 0 and elapsed_total > int(budget_limit.get("max_duration_seconds", 0)):
                    raise RuntimeError(
                        f"预算超限: max_duration_seconds={budget_limit.get('max_duration_seconds')}"
                    )
                summary_payload = {
                    "task_id": task_id,
                    "mode": "skill_sequence",
                    "strategy": strategy,
                    "dry_run": dry_run,
                    "max_parallel": max_parallel if strategy == "parallel" else 1,
                    "budget_limit": budget_limit,
                    "governance": governance,
                    "total_steps": total,
                    "success_steps": success,
                    "failed_steps": failed,
                    "skipped_steps": skipped,
                    "overall_ok": failed == 0,
                    "steps": step_results,
                    "duration_seconds": round(max(elapsed_total, 0.0), 4),
                }
                governance_usage = (
                    record_governance_usage_for_skill_flow(
                        actor_id=str(request_ctx.get("actor_id", "") or ""),
                        summary=summary_payload,
                    )
                    if not dry_run
                    else {"ok": False, "reason": "dry_run"}
                )
                if isinstance(governance_usage, dict):
                    summary_payload["governance_usage"] = governance_usage
                jobs[job_id]["progress"] = 95
                return summary_payload

            run_in_bg(
                job_id,
                _do_run_skill_sequence,
                kind="agent_task",
                job_meta={
                    "actor_type": str(request_ctx.get("actor_type", "") or ""),
                    "actor_id": str(request_ctx.get("actor_id", "") or ""),
                    "trace_id": str(request_ctx.get("trace_id", "") or ""),
                    "task_mode": "skill_sequence",
                    "strategy": strategy,
                    "template_hits": extract_template_ids_from_value(payload),
                    "replay": {
                        "method": "POST",
                        "endpoint": "/api/agent/tasks/run",
                        "payload": deepcopy(payload),
                        "request_context": deepcopy(request_ctx),
                    },
                },
            )
            return jsonify({
                "ok": True,
                "job_id": job_id,
                "task_id": task_id,
                "mode": "skill_sequence",
                "strategy": strategy,
                "max_parallel": max_parallel if strategy == "parallel" else 1,
                "budget_limit": budget_limit,
                "governance": governance,
                "total_steps": len(steps_run),
                "dry_run": dry_run,
            })

        capability_id = str(payload.get("capability_id", "") or task_plan.get("capability_id", "") or "").strip()
        if not capability_id:
            return jsonify({"error": "capability_id 不能为空（或使用 mode=skill_sequence + skills）"}), 400

        route_map = agent_capability_route_map()
        routes = route_map.get(capability_id)
        if not isinstance(routes, dict) or not routes:
            return jsonify({"error": f"不支持的 capability_id: {capability_id}"}), 400

        input_payload = payload.get("input", None)
        if input_payload is None:
            input_payload = task_plan.get("primary_call", {}).get("payload", {}) if isinstance(task_plan, dict) else {}
        if not isinstance(input_payload, dict):
            return jsonify({"error": "input 必须是对象"}), 400
        input_payload = apply_agent_capability_input_defaults(capability_id, input_payload)

        action = parse_str_param(payload.get("action", "auto"), default="auto").lower()

        primary_call_raw = task_plan.get("primary_call") if isinstance(task_plan, dict) else None
        if isinstance(primary_call_raw, dict) and parse_str_param(primary_call_raw.get("endpoint", "")):
            method = parse_str_param(primary_call_raw.get("method", "POST"), default="POST").upper()
            endpoint = parse_str_param(primary_call_raw.get("endpoint", ""))
        else:
            try:
                resolved = resolve_agent_primary_call(capability_id=capability_id, routes=routes, action=action)
            except Exception as exc:
                return jsonify({"error": str(exc)}), 400
            method = resolved["method"]
            endpoint = resolved["endpoint"]

        call_payload = dict(input_payload)
        if dry_run and method != "GET" and "dry_run" not in call_payload:
            call_payload["dry_run"] = True

        def _do_run():
            jobs[job_id]["progress"] = 10
            jobs[job_id]["log"].append(f"[Agent] task_id={task_id} capability={capability_id}")
            jobs[job_id]["log"].append(f"[Agent] 调用 {method} {endpoint}")

            ret = invoke_agent_primary_call(
                method=method,
                endpoint=endpoint,
                payload=call_payload,
                request_context=request_ctx,
            )
            status_code = int(ret.get("status_code", 0) or 0)
            data = ret.get("data") if isinstance(ret.get("data"), dict) else {}
            jobs[job_id]["progress"] = 85
            if status_code >= 400 or not bool(data.get("ok", False)):
                err = str(data.get("error", "") or f"子调用失败（status={status_code}）")
                raise RuntimeError(err)
            jobs[job_id]["progress"] = 95
            return {
                "task_id": task_id,
                "capability_id": capability_id,
                "primary_call": {
                    "method": method,
                    "endpoint": endpoint,
                    "payload": call_payload,
                },
                "status_code": status_code,
                "response": data,
            }

        run_in_bg(
            job_id,
            _do_run,
            kind="agent_task",
            job_meta={
                "actor_type": str(request_ctx.get("actor_type", "") or ""),
                "actor_id": str(request_ctx.get("actor_id", "") or ""),
                "trace_id": str(request_ctx.get("trace_id", "") or ""),
                "task_mode": "single_capability",
                "capability_id": capability_id,
                "template_hits": extract_template_ids_from_value(payload),
                "replay": {
                    "method": "POST",
                    "endpoint": "/api/agent/tasks/run",
                    "payload": deepcopy(payload),
                    "request_context": deepcopy(request_ctx),
                },
            },
        )
        return jsonify({
            "ok": True,
            "job_id": job_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "primary_call": {
                "method": method,
                "endpoint": endpoint,
            },
        })

    return bp
