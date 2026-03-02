#!/usr/bin/env python3
"""Agent task query/export/replay routes."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Dict, List
import csv
import io

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_int_param, parse_str_param, write_json_result


def create_agent_task_query_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    jobs_getter: Callable[[], Dict[str, Dict[str, Any]]],
    find_agent_task_history_record: Callable[[str], Any],
    build_chain_view_from_history_item: Callable[[Dict[str, Any]], Dict[str, Any]],
    read_agent_task_history: Callable[[], List[Dict[str, Any]]],
    parse_agent_history_filter_tokens: Callable[[Any], List[str]],
    filter_agent_task_history: Callable[..., List[Dict[str, Any]]],
    parse_boolish: Callable[[Any, bool], bool],
    coerce_bool: Callable[[Any, bool], bool],
    build_agent_task_export_snapshot: Callable[[str, bool, bool], Any],
    project_data_path: Callable[[str], Any],
    extract_agent_replay_spec: Callable[[Any], Dict[str, Any]],
    deep_merge_dict: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    normalize_agent_replay_context: Callable[[Any], Dict[str, str]],
    invoke_agent_primary_call: Callable[..., Dict[str, Any]],
) -> Blueprint:
    bp = Blueprint("agent_task_query_api", __name__)

    @bp.route("/api/agent/tasks/<job_id>", methods=["GET"])
    def api_agent_task_status(job_id: str):
        jobs = jobs_getter()
        job = jobs.get(job_id)
        if not isinstance(job, dict) or job.get("kind") not in {"agent_task", "agent_skill"}:
            history_item = find_agent_task_history_record(job_id)
            if not isinstance(history_item, dict):
                return jsonify({"error": "agent task/skill 不存在"}), 404

            status = str(history_item.get("status", "unknown") or "unknown").strip().lower()
            chain_view = build_chain_view_from_history_item(history_item)
            return jsonify({
                "ok": True,
                "job_id": str(history_item.get("job_id", "") or job_id),
                "status": status,
                "kind": str(history_item.get("kind", "agent_task") or "agent_task"),
                "source": "history",
                "progress": 100,
                "log": [],
                "error": history_item.get("error", ""),
                "result": {"history_summary": history_item},
                "chain_view": chain_view,
                "started_at": history_item.get("started_at"),
                "finished_at": history_item.get("finished_at"),
            })
        kind = str(job.get("kind", "agent_task") or "agent_task")
        result_payload = job.get("result") if isinstance(job.get("result"), dict) else {}

        def _to_int(value: Any) -> int:
            try:
                parsed = int(value)
            except Exception:
                parsed = 0
            return max(parsed, 0)

        def _to_float(value: Any) -> float:
            try:
                parsed = float(value)
            except Exception:
                parsed = 0.0
            return max(parsed, 0.0)

        def _build_chain_view(kind_value: str, result: Dict[str, Any], fallback_status: str) -> Dict[str, Any]:
            mode = "single_capability"
            status_norm = str(fallback_status or "unknown").strip().lower()
            if status_norm == "done":
                overall_status = "done"
            elif status_norm in {"error", "cancelled"}:
                overall_status = "error"
            else:
                overall_status = "running"

            nodes: List[Dict[str, Any]] = []
            edges: List[Dict[str, Any]] = []
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_cost_usd = 0.0

            if kind_value == "agent_skill":
                mode = "skill_invoke"
                usage_tokens = result.get("usage_tokens", {}) if isinstance(result.get("usage_tokens"), dict) else {}
                estimated_cost = result.get("estimated_cost", {}) if isinstance(result.get("estimated_cost"), dict) else {}
                p = _to_int(usage_tokens.get("prompt_tokens", 0))
                c = _to_int(usage_tokens.get("completion_tokens", 0))
                cost = _to_float(estimated_cost.get("total_cost_usd", 0.0))
                total_prompt_tokens += p
                total_completion_tokens += c
                total_cost_usd += cost
                nodes.append({
                    "node_id": str(result.get("invoke_id", "") or result.get("skill_id", "skill")),
                    "node_type": "skill",
                    "status": "done" if bool(result.get("status_code", 0)) and _to_int(result.get("status_code", 0)) < 400 else overall_status,
                    "skill_id": str(result.get("skill_id", "") or ""),
                    "capability_id": str(result.get("capability_id", "") or ""),
                    "duration_seconds": round(_to_float(result.get("duration_seconds", 0.0)), 4),
                    "prompt_tokens": p,
                    "completion_tokens": c,
                    "estimated_cost_usd": round(cost, 8),
                })
            elif str(result.get("mode", "") or "").strip().lower() == "skill_sequence":
                mode = "skill_sequence"
                steps = result.get("steps", [])
                if not isinstance(steps, list):
                    steps = []
                known_step_ids = set()
                for idx, item in enumerate(steps, start=1):
                    if not isinstance(item, dict):
                        continue
                    step_id = str(item.get("step_id", "") or f"step_{idx:02d}")
                    known_step_ids.add(step_id)
                    usage_tokens = item.get("usage_tokens", {}) if isinstance(item.get("usage_tokens"), dict) else {}
                    estimated_cost = item.get("estimated_cost", {}) if isinstance(item.get("estimated_cost"), dict) else {}
                    p = _to_int(usage_tokens.get("prompt_tokens", 0))
                    c = _to_int(usage_tokens.get("completion_tokens", 0))
                    cost = _to_float(estimated_cost.get("total_cost_usd", 0.0))
                    total_prompt_tokens += p
                    total_completion_tokens += c
                    total_cost_usd += cost
                    nodes.append({
                        "node_id": step_id,
                        "node_type": "skill",
                        "index": _to_int(item.get("index", idx)),
                        "status": str(item.get("status", "unknown") or "unknown"),
                        "skill_id": str(item.get("skill_id", "") or ""),
                        "capability_id": str(item.get("capability_id", "") or ""),
                        "continue_on_error": bool(item.get("continue_on_error", False)),
                        "duration_seconds": round(_to_float(item.get("duration_seconds", 0.0)), 4),
                        "prompt_tokens": p,
                        "completion_tokens": c,
                        "estimated_cost_usd": round(cost, 8),
                        "error": str(item.get("error", "") or ""),
                        "condition": deepcopy(item.get("condition", {})) if isinstance(item.get("condition"), dict) else {},
                    })
                strategy = str(result.get("strategy", "") or "").strip().lower()
                for idx, node in enumerate(nodes):
                    node_id = str(node.get("node_id", "") or "")
                    condition = node.get("condition", {}) if isinstance(node.get("condition"), dict) else {}
                    depends_on_raw = condition.get("depends_on", [])
                    depends_on = depends_on_raw if isinstance(depends_on_raw, list) else []
                    deps_added = False
                    for dep in depends_on:
                        dep_id = str(dep or "").strip()
                        if not dep_id or dep_id not in known_step_ids:
                            continue
                        edges.append({
                            "from": dep_id,
                            "to": node_id,
                            "type": "condition_depends_on",
                        })
                        deps_added = True
                    if not deps_added and strategy in {"sequential", "conditional"} and idx > 0:
                        prev_node_id = str(nodes[idx - 1].get("node_id", "") or "")
                        if prev_node_id:
                            edges.append({
                                "from": prev_node_id,
                                "to": node_id,
                                "type": "sequence",
                            })
            else:
                mode = "single_capability"
                nodes.append({
                    "node_id": str(result.get("task_id", "") or "task"),
                    "node_type": "capability",
                    "status": "done" if bool(result.get("status_code", 0)) and _to_int(result.get("status_code", 0)) < 400 else overall_status,
                    "capability_id": str(result.get("capability_id", "") or ""),
                    "endpoint": str(
                        (result.get("primary_call", {}) if isinstance(result.get("primary_call"), dict) else {}).get("endpoint", "")
                        or ""
                    ),
                    "duration_seconds": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                })

            status_done = sum(1 for n in nodes if str(n.get("status", "")).lower() == "done")
            status_error = sum(1 for n in nodes if str(n.get("status", "")).lower() == "error")
            status_skipped = sum(1 for n in nodes if str(n.get("status", "")).lower() == "skipped")
            if nodes and status_error > 0:
                overall_status = "error"
            elif nodes and status_done == len(nodes):
                overall_status = "done"
            elif nodes and (status_done + status_skipped) == len(nodes):
                overall_status = "partial"

            return {
                "mode": mode,
                "overall_status": overall_status,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "counts": {
                    "done": status_done,
                    "error": status_error,
                    "skipped": status_skipped,
                    "other": max(len(nodes) - status_done - status_error - status_skipped, 0),
                },
                "totals": {
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": total_prompt_tokens + total_completion_tokens,
                    "estimated_cost_usd": round(total_cost_usd, 8),
                },
                "nodes": nodes,
                "edges": edges,
            }

        chain_view = _build_chain_view(
            kind_value=kind,
            result=result_payload,
            fallback_status=str(job.get("status", "unknown") or "unknown"),
        )
        return jsonify({
            "ok": True,
            "job_id": job_id,
            "status": job.get("status", "unknown"),
            "kind": kind,
            "source": "memory",
            "progress": int(job.get("progress", 0) or 0),
            "log": list(job.get("log", []))[-80:],
            "error": job.get("error"),
            "result": result_payload,
            "chain_view": chain_view,
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
        })

    @bp.route("/api/agent/tasks/history", methods=["GET"])
    def api_agent_tasks_history():
        if project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        actor_id = parse_str_param(request.args.get("actor_id", ""))
        statuses = parse_agent_history_filter_tokens(request.args.get("status", ""))
        task_modes = parse_agent_history_filter_tokens(request.args.get("task_mode", ""))
        kinds = parse_agent_history_filter_tokens(request.args.get("kind", ""))
        capability_id = parse_str_param(request.args.get("capability_id", "")).lower()
        skill_id = parse_str_param(request.args.get("skill_id", "")).lower()
        trace_id = parse_str_param(request.args.get("trace_id", ""))
        since = parse_str_param(request.args.get("since", ""))
        until = parse_str_param(request.args.get("until", ""))
        sort = parse_str_param(request.args.get("sort", "desc"), default="desc").lower()
        if sort not in {"desc", "asc"}:
            sort = "desc"

        replay_supported = None
        replay_supported_raw = request.args.get("replay_supported", None)
        if replay_supported_raw is not None and str(replay_supported_raw).strip() != "":
            replay_supported = parse_boolish(replay_supported_raw, default=False)

        limit = parse_int_param(request.args.get("limit", 100), default=100, min_val=1, max_val=1000)
        offset = parse_int_param(request.args.get("offset", 0), default=0, min_val=0)

        history = read_agent_task_history()
        filtered = filter_agent_task_history(
            history,
            actor_id=actor_id,
            statuses=statuses,
            task_modes=task_modes,
            kinds=kinds,
            capability_id=capability_id,
            skill_id=skill_id,
            trace_id=trace_id,
            replay_supported=replay_supported,
            since=since,
            until=until,
        )
        ordered = filtered if sort == "asc" else list(reversed(filtered))
        total_count = len(ordered)
        items = ordered[offset:offset + limit]
        return jsonify({
            "ok": True,
            "history_file": "data/agent_task_history.json",
            "total_count": total_count,
            "returned_count": len(items),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(items)) < total_count,
            "filters": {
                "actor_id": actor_id or None,
                "status": statuses,
                "task_mode": task_modes,
                "kind": kinds,
                "capability_id": capability_id or None,
                "skill_id": skill_id or None,
                "trace_id": trace_id or None,
                "replay_supported": replay_supported,
                "since": since or None,
                "until": until or None,
                "sort": sort,
            },
            "items": items,
        })

    @bp.route("/api/agent/tasks/<job_id>/export", methods=["POST"])
    def api_agent_task_export(job_id: str):
        if project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        payload = request.json or {}
        fmt = parse_str_param(payload.get("format", "json"), default="json").lower()
        if fmt not in {"json", "csv"}:
            return jsonify({"error": "format 仅支持 json/csv"}), 400
        include_logs = coerce_bool(payload.get("include_logs", True), default=True)
        include_result = coerce_bool(payload.get("include_result", True), default=True)

        snapshot = build_agent_task_export_snapshot(
            job_id,
            include_logs=include_logs,
            include_result=include_result,
        )
        if not isinstance(snapshot, dict):
            return jsonify({"error": "agent task/skill 不存在"}), 404

        safe_job_id = parse_str_param(job_id, default="unknown")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = project_data_path(f"agent_task_export_{safe_job_id}_{ts}.{fmt}")
        if out_path is None:
            return jsonify({"error": "项目未加载"}), 400
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "json":
            write_json_result(out_path, snapshot)
        else:
            summary = snapshot.get("summary", {}) if isinstance(snapshot.get("summary"), dict) else {}
            fieldnames = [
                "source",
                "job_id",
                "status",
                "kind",
                "task_mode",
                "strategy",
                "actor_type",
                "actor_id",
                "trace_id",
                "capability_ids",
                "skill_ids",
                "total_steps",
                "success_steps",
                "failed_steps",
                "skipped_steps",
                "retry_count",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "estimated_cost_usd",
                "duration_seconds",
                "template_hits",
                "template_hit_count",
                "replay_supported",
                "error",
                "started_at",
                "finished_at",
            ]
            row = {
                "source": str(snapshot.get("source", "") or ""),
                "job_id": str(summary.get("job_id", "") or snapshot.get("job_id", "") or ""),
                "status": str(summary.get("status", "") or snapshot.get("status", "") or ""),
                "kind": str(summary.get("kind", "") or snapshot.get("kind", "") or ""),
                "task_mode": str(summary.get("task_mode", "") or ""),
                "strategy": str(summary.get("strategy", "") or ""),
                "actor_type": str(summary.get("actor_type", "") or ""),
                "actor_id": str(summary.get("actor_id", "") or ""),
                "trace_id": str(summary.get("trace_id", "") or ""),
                "capability_ids": "|".join(str(x) for x in (summary.get("capability_ids", []) if isinstance(summary.get("capability_ids"), list) else [])),
                "skill_ids": "|".join(str(x) for x in (summary.get("skill_ids", []) if isinstance(summary.get("skill_ids"), list) else [])),
                "total_steps": int(summary.get("total_steps", 0) or 0),
                "success_steps": int(summary.get("success_steps", 0) or 0),
                "failed_steps": int(summary.get("failed_steps", 0) or 0),
                "skipped_steps": int(summary.get("skipped_steps", 0) or 0),
                "retry_count": int(summary.get("retry_count", 0) or 0),
                "prompt_tokens": int(summary.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(summary.get("completion_tokens", 0) or 0),
                "total_tokens": int(summary.get("total_tokens", 0) or 0),
                "estimated_cost_usd": float(summary.get("estimated_cost_usd", 0.0) or 0.0),
                "duration_seconds": float(summary.get("duration_seconds", 0.0) or 0.0),
                "template_hits": "|".join(str(x) for x in (summary.get("template_hits", []) if isinstance(summary.get("template_hits"), list) else [])),
                "template_hit_count": int(summary.get("template_hit_count", 0) or 0),
                "replay_supported": bool(summary.get("replay_supported", False)),
                "error": str(summary.get("error", "") or snapshot.get("error", "") or ""),
                "started_at": str(summary.get("started_at", "") or snapshot.get("started_at", "") or ""),
                "finished_at": str(summary.get("finished_at", "") or snapshot.get("finished_at", "") or ""),
            }
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(row)
            out_path.write_text(buf.getvalue(), encoding="utf-8")

        return jsonify({
            "ok": True,
            "job_id": safe_job_id,
            "source": str(snapshot.get("source", "") or ""),
            "format": fmt,
            "output": str(out_path),
            "history_file": "data/agent_task_history.json",
        })

    @bp.route("/api/agent/tasks/<job_id>/replay", methods=["POST"])
    def api_agent_task_replay(job_id: str):
        if project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        jobs = jobs_getter()
        job = jobs.get(job_id)
        source = "memory"
        replay_spec: Dict[str, Any] = {}
        if isinstance(job, dict) and job.get("kind") in {"agent_task", "agent_skill"}:
            meta = job.get("meta", {}) if isinstance(job.get("meta"), dict) else {}
            replay_spec = extract_agent_replay_spec(meta.get("replay", {}))
            if not replay_spec:
                history_item = find_agent_task_history_record(job_id)
                if isinstance(history_item, dict):
                    history_replay = extract_agent_replay_spec(history_item.get("replay", {}))
                    if history_replay:
                        source = "history"
                        replay_spec = history_replay
        else:
            source = "history"
            history_item = find_agent_task_history_record(job_id)
            if not isinstance(history_item, dict):
                return jsonify({"error": "agent task/skill 不存在"}), 404
            replay_spec = extract_agent_replay_spec(history_item.get("replay", {}))

        req = request.json or {}
        if not isinstance(req, dict):
            req = {}
        payload_overrides = req.get("payload_overrides", {})
        if payload_overrides is None:
            payload_overrides = {}
        if not isinstance(payload_overrides, dict):
            return jsonify({"error": "payload_overrides 必须是对象"}), 400
        context_overrides = req.get("context_overrides", {})
        if context_overrides is None:
            context_overrides = {}
        if not isinstance(context_overrides, dict):
            return jsonify({"error": "context_overrides 必须是对象"}), 400

        endpoint = str(replay_spec.get("endpoint", "") or "").strip()
        method = str(replay_spec.get("method", "POST") or "POST").strip().upper()
        if not endpoint:
            return jsonify({"error": "该任务缺少 replay 元数据（仅支持新任务）"}), 400
        if method not in {"POST", "GET"}:
            return jsonify({"error": f"不支持的 replay method: {method}"}), 400

        base_payload = replay_spec.get("payload", {}) if isinstance(replay_spec.get("payload"), dict) else {}
        final_payload = deep_merge_dict(base_payload, payload_overrides)
        ctx = normalize_agent_replay_context(replay_spec.get("request_context", {}))
        for key in ("actor_type", "actor_id", "run_mode", "trace_id", "idempotency_key"):
            if key in context_overrides:
                ctx[key] = str(context_overrides.get(key, "") or "").strip()[:128]
        ctx = normalize_agent_replay_context(ctx)

        new_trace_id = str(req.get("new_trace_id", "") or "").strip()[:128]
        if new_trace_id:
            ctx["trace_id"] = new_trace_id

        explicit_idem = None
        if "idempotency_key" in req:
            explicit_idem = str(req.get("idempotency_key", "") or "").strip()[:128]
        clear_idempotency = coerce_bool(req.get("clear_idempotency", True), default=True)
        if explicit_idem is not None:
            ctx["idempotency_key"] = explicit_idem
        elif clear_idempotency:
            ctx["idempotency_key"] = ""

        for key in ("actor_type", "actor_id", "run_mode", "trace_id"):
            val = str(ctx.get(key, "") or "").strip()
            if val:
                final_payload[key] = val
        idem_val = str(ctx.get("idempotency_key", "") or "").strip()
        if idem_val:
            final_payload["idempotency_key"] = idem_val
        else:
            final_payload.pop("idempotency_key", None)

        if "dry_run" in req and "dry_run" not in payload_overrides:
            final_payload["dry_run"] = coerce_bool(req.get("dry_run", False), default=False)
        final_payload["replay_of_job_id"] = job_id

        invoke_ret = invoke_agent_primary_call(
            method=method,
            endpoint=endpoint,
            payload=final_payload,
            request_context=ctx,
        )
        status_code = int(invoke_ret.get("status_code", 500) or 500)
        data = invoke_ret.get("data", {}) if isinstance(invoke_ret.get("data"), dict) else {}
        out = {
            "ok": status_code < 400 and bool(data.get("ok", False)),
            "replay_of_job_id": job_id,
            "source": source,
            "target": {
                "method": method,
                "endpoint": endpoint,
            },
            "request_context": ctx,
            "request_payload": final_payload,
            "status_code": status_code,
            "response": data,
        }
        if isinstance(data.get("job_id"), str) and str(data.get("job_id", "")).strip():
            out["new_job_id"] = str(data.get("job_id", "")).strip()
        return jsonify(out), (status_code if status_code >= 400 else 200)

    return bp
