#!/usr/bin/env python3
"""Agent observability routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import csv
import io
import json

from flask import Blueprint, jsonify, request


def create_agent_observability_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    parse_agent_history_filter_tokens: Callable[[Any], List[str]],
    parse_boolish: Callable[[Any, bool], bool],
    read_agent_task_history: Callable[[], List[Dict[str, Any]]],
    filter_agent_task_history: Callable[..., List[Dict[str, Any]]],
    build_agent_observability_summary: Callable[[List[Dict[str, Any]], int], Dict[str, Any]],
    project_data_path: Callable[[str], Any],
) -> Blueprint:
    bp = Blueprint("agent_observability_api", __name__)

    @bp.route("/api/agent/observability", methods=["GET"])
    def api_agent_observability():
        if project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        actor_id = str(request.args.get("actor_id", "") or "").strip()
        statuses = parse_agent_history_filter_tokens(request.args.get("status", ""))
        task_modes = parse_agent_history_filter_tokens(request.args.get("task_mode", ""))
        kinds = parse_agent_history_filter_tokens(request.args.get("kind", ""))
        capability_id = str(request.args.get("capability_id", "") or "").strip().lower()
        skill_id = str(request.args.get("skill_id", "") or "").strip().lower()
        trace_id = str(request.args.get("trace_id", "") or "").strip()
        since = str(request.args.get("since", "") or "").strip()
        until = str(request.args.get("until", "") or "").strip()
        replay_supported: Optional[bool] = None
        replay_supported_raw = request.args.get("replay_supported", None)
        if replay_supported_raw is not None and str(replay_supported_raw).strip() != "":
            replay_supported = parse_boolish(replay_supported_raw, default=False)
        include_items = parse_boolish(request.args.get("include_items", "false"), default=False)
        try:
            limit = int(request.args.get("limit", 200) or 200)
        except Exception:
            limit = 200
        limit = max(1, min(limit, 2000))
        try:
            top_n = int(request.args.get("top_n", 5) or 5)
        except Exception:
            top_n = 5
        top_n = max(1, min(top_n, 20))

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
        picked = filtered[-limit:] if filtered else []
        summary = build_agent_observability_summary(picked, top_n=top_n)
        return jsonify({
            "ok": True,
            "actor_id": actor_id,
            "window_limit": limit,
            "top_n": top_n,
            "history_count": len(filtered),
            "window_count": len(picked),
            "summary": summary,
            "history_file": "data/agent_task_history.json",
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
            },
            "items": list(reversed(picked)) if include_items else [],
        })

    @bp.route("/api/agent/observability/export", methods=["POST"])
    def api_agent_observability_export():
        if project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        payload = request.json or {}
        actor_id = str(payload.get("actor_id", "") or "").strip()
        statuses = parse_agent_history_filter_tokens(payload.get("status", ""))
        task_modes = parse_agent_history_filter_tokens(payload.get("task_mode", ""))
        kinds = parse_agent_history_filter_tokens(payload.get("kind", ""))
        capability_id = str(payload.get("capability_id", "") or "").strip().lower()
        skill_id = str(payload.get("skill_id", "") or "").strip().lower()
        trace_id = str(payload.get("trace_id", "") or "").strip()
        since = str(payload.get("since", "") or "").strip()
        until = str(payload.get("until", "") or "").strip()
        replay_supported: Optional[bool] = None
        replay_supported_raw = payload.get("replay_supported", None)
        if replay_supported_raw is not None and str(replay_supported_raw).strip() != "":
            replay_supported = parse_boolish(replay_supported_raw, default=False)
        fmt = str(payload.get("format", "json") or "json").strip().lower()
        if fmt not in {"json", "csv"}:
            return jsonify({"error": "format 仅支持 json/csv"}), 400
        try:
            limit = int(payload.get("limit", 500) or 500)
        except Exception:
            limit = 500
        limit = max(1, min(limit, 5000))
        try:
            top_n = int(payload.get("top_n", 5) or 5)
        except Exception:
            top_n = 5
        top_n = max(1, min(top_n, 20))

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
        picked = filtered[-limit:] if filtered else []
        summary = build_agent_observability_summary(picked, top_n=top_n)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "json" if fmt == "json" else "csv"
        out_path = project_data_path(f"agent_observability_{ts}.{ext}")
        if out_path is None:
            return jsonify({"error": "项目未加载"}), 400
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "json":
            body = {
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "actor_id": actor_id,
                "window_limit": limit,
                "window_count": len(picked),
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
                },
                "summary": summary,
                "items": list(reversed(picked)),
            }
            out_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            fieldnames = [
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
                "error",
                "started_at",
                "finished_at",
            ]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=fieldnames)
            writer.writeheader()
            for item in reversed(picked):
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                for key in ("capability_ids", "skill_ids", "template_hits"):
                    val = row.get(key)
                    row[key] = "|".join(str(x) for x in val) if isinstance(val, list) else ""
                writer.writerow({k: row.get(k, "") for k in fieldnames})
            out_path.write_text(buf.getvalue(), encoding="utf-8")

        return jsonify({
            "ok": True,
            "format": fmt,
            "output": str(out_path),
            "history_file": "data/agent_task_history.json",
            "window_count": len(picked),
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
            },
            "summary": summary,
        })

    return bp
