#!/usr/bin/env python3
"""Custom workflow API routes extracted from server.py."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_int_param, parse_str_param


def create_workflow_blueprint(
    *,
    parse_request_context: Callable[[], Dict[str, str]],
    build_custom_workflow_catalog: Callable[[], list],
    normalize_agent_template_id: Callable[[Any], str],
    parse_boolish: Callable[[Any, bool], bool],
    coerce_bool: Callable[[Any, bool], bool],
    custom_workflow_lock_getter: Callable[[], Any],
    read_custom_workflow_store: Callable[[], Dict[str, Dict[str, Any]]],
    save_custom_workflow_store: Callable[[Dict[str, Dict[str, Any]]], Dict[str, Dict[str, Any]]],
    normalize_custom_workflow_payload: Callable[..., Dict[str, Any]],
    resolve_custom_workflow_from_payload: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_custom_workflow_plan: Callable[..., Dict[str, Any]],
    start_custom_workflow_run: Callable[..., Dict[str, Any]],
    read_custom_workflow_runs: Callable[[], list],
    find_custom_workflow_run: Callable[[str], Dict[str, Any] | None],
    build_failed_only_workflow_subset: Callable[..., Dict[str, Any]],
    project_dir_getter: Callable[[], Any],
) -> Blueprint:
    bp = Blueprint("workflow_api", __name__)

    @bp.route("/api/workflows/catalog", methods=["GET"])
    def api_workflows_catalog():
        ctx = parse_request_context()
        catalog = build_custom_workflow_catalog()
        return jsonify({"ok": True, "catalog": catalog, "count": len(catalog), "request_context": ctx})

    @bp.route("/api/workflows", methods=["GET"])
    def api_workflows_list():
        ctx = parse_request_context()
        workflow_id = normalize_agent_template_id(request.args.get("workflow_id", ""))
        include_steps = parse_boolish(request.args.get("include_steps", "true"), default=True)
        with custom_workflow_lock_getter():
            store = read_custom_workflow_store()
        items = list(store.values())
        items.sort(key=lambda x: str(x.get("updated_at", "") or ""), reverse=True)
        if workflow_id:
            items = [x for x in items if str(x.get("workflow_id", "") or "") == workflow_id]
        if not include_steps:
            for item in items:
                item.pop("steps", None)
        return jsonify(
            {
                "ok": True,
                "workflows": items,
                "count": len(items),
                "persisted": project_dir_getter() is not None,
                "request_context": ctx,
            }
        )

    @bp.route("/api/workflows", methods=["POST"])
    def api_workflows_upsert():
        payload = request.json or {}
        ctx = parse_request_context()
        try:
            workflow_id = normalize_agent_template_id(payload.get("workflow_id", ""))
            with custom_workflow_lock_getter():
                store = read_custom_workflow_store()
                existing = store.get(workflow_id) if workflow_id else None
                workflow = normalize_custom_workflow_payload(payload, existing=existing)
                old_id = workflow_id if workflow_id and workflow_id in store else ""
                store[workflow["workflow_id"]] = workflow
                if old_id and old_id != workflow["workflow_id"]:
                    store.pop(old_id, None)
                saved = save_custom_workflow_store(store)
        except Exception as exc:
            return jsonify({"error": f"workflow 保存失败: {exc}"}), 400
        return jsonify(
            {
                "ok": True,
                "workflow": workflow,
                "count": len(saved),
                "persisted": project_dir_getter() is not None,
                "request_context": ctx,
            }
        )

    @bp.route("/api/workflows/plan", methods=["POST"])
    def api_workflows_plan():
        payload = request.json or {}
        ctx = parse_request_context()
        dry_run = coerce_bool(payload.get("dry_run", True), default=True)
        try:
            workflow = resolve_custom_workflow_from_payload(payload)
            plan = build_custom_workflow_plan(workflow=workflow, payload=payload, dry_run=dry_run)
        except Exception as exc:
            return jsonify({"error": f"workflow 规划失败: {exc}"}), 400
        return jsonify(
            {
                "ok": True,
                "workflow": {
                    "workflow_id": plan.get("workflow_id"),
                    "name": plan.get("name"),
                    "description": plan.get("description"),
                },
                "plan": plan,
                "plan_summary": {
                    "workflow_id": plan.get("workflow_id"),
                    "total_steps": plan.get("total_steps", 0),
                    "dry_run": dry_run,
                    "start_step_id": (plan.get("graph", {}) or {}).get("start_step_id", ""),
                    "edge_count": (plan.get("graph", {}) or {}).get("edge_count", 0),
                    "has_cycle": bool((plan.get("graph", {}) or {}).get("has_cycle", False)),
                    "enabled_steps": sum(
                        1
                        for step in (plan.get("steps", []) if isinstance(plan.get("steps"), list) else [])
                        if coerce_bool(step.get("enabled", True), default=True)
                    ),
                },
                "request_context": ctx,
            }
        )

    @bp.route("/api/workflows/run", methods=["POST"])
    def api_workflows_run():
        payload = request.json or {}
        ctx = parse_request_context()
        try:
            workflow = resolve_custom_workflow_from_payload(payload)
            ret = start_custom_workflow_run(
                workflow=workflow,
                payload=payload,
                request_context=ctx,
                source="api/workflows/run",
            )
        except Exception as exc:
            return jsonify({"error": f"workflow 执行失败: {exc}"}), 400
        ret["request_context"] = ctx
        return jsonify(ret)

    @bp.route("/api/workflows/runs", methods=["GET"])
    def api_workflows_runs():
        ctx = parse_request_context()
        workflow_id = normalize_agent_template_id(request.args.get("workflow_id", ""))
        include_steps = parse_boolish(request.args.get("include_steps", "false"), default=False)
        limit = parse_int_param(request.args.get("limit", "50"), default=50, min_val=1, max_val=200)
        offset = parse_int_param(request.args.get("offset", "0"), default=0, min_val=0)

        with custom_workflow_lock_getter():
            runs = read_custom_workflow_runs()
        if workflow_id:
            runs = [x for x in runs if str(x.get("workflow_id", "") or "") == workflow_id]
        ordered = list(reversed(runs))
        page = ordered[offset : offset + limit]
        has_more = (offset + limit) < len(ordered)
        if not include_steps:
            for item in page:
                item.pop("steps", None)
                item.pop("workflow", None)
                item.pop("plan", None)
        return jsonify(
            {
                "ok": True,
                "items": page,
                "total_count": len(ordered),
                "offset": offset,
                "limit": limit,
                "has_more": has_more,
                "request_context": ctx,
            }
        )

    @bp.route("/api/workflows/runs/<run_id>", methods=["GET"])
    def api_workflows_run_detail(run_id: str):
        ctx = parse_request_context()
        record = find_custom_workflow_run(run_id)
        if not isinstance(record, dict):
            return jsonify({"error": f"run 不存在: {run_id}"}), 404
        return jsonify({"ok": True, "run": record, "request_context": ctx})

    @bp.route("/api/workflows/runs/<run_id>/rerun", methods=["POST"])
    def api_workflows_run_rerun(run_id: str):
        payload = request.json or {}
        ctx = parse_request_context()
        base = find_custom_workflow_run(run_id)
        if not isinstance(base, dict):
            return jsonify({"error": f"run 不存在: {run_id}"}), 404

        workflow_raw = base.get("workflow", {})
        if not isinstance(workflow_raw, dict):
            workflow_raw = {}
        if not workflow_raw:
            workflow_id = normalize_agent_template_id(base.get("workflow_id", ""))
            with custom_workflow_lock_getter():
                workflow_raw = read_custom_workflow_store().get(workflow_id, {})
        if not isinstance(workflow_raw, dict) or not workflow_raw:
            return jsonify({"error": "历史 run 缺少可复用 workflow 定义"}), 400

        rerun_failed_only = coerce_bool(payload.get("rerun_failed_only", False), default=False)
        failed_step_ids = [
            normalize_agent_template_id(step.get("step_id", ""))
            for step in (base.get("steps", []) if isinstance(base.get("steps"), list) else [])
            if parse_str_param(step.get("status", "")).lower() == "error"
        ]
        failed_step_ids = [sid for sid in failed_step_ids if sid]
        try:
            workflow = normalize_custom_workflow_payload(workflow_raw, existing=workflow_raw)
        except Exception as exc:
            return jsonify({"error": f"workflow 解析失败: {exc}"}), 400

        if rerun_failed_only:
            try:
                workflow = build_failed_only_workflow_subset(workflow=workflow, base_run=base)
            except Exception as exc:
                return jsonify({"error": str(exc)}), 400

        run_payload = deepcopy(payload)
        run_payload["workflow"] = workflow
        included_step_ids = [
            normalize_agent_template_id(step.get("step_id", ""))
            for step in (workflow.get("steps", []) if isinstance(workflow.get("steps"), list) else [])
        ]
        included_step_ids = [sid for sid in included_step_ids if sid]
        run_payload["rerun_context"] = {
            "mode": "failed_with_dependencies" if rerun_failed_only else "full",
            "source_run_id": run_id,
            "failed_step_ids": failed_step_ids,
            "included_step_ids": included_step_ids,
            "start_step_id": normalize_agent_template_id(workflow.get("start_step_id", "")),
        }
        if "input" not in run_payload:
            plan_raw = base.get("plan", {})
            if isinstance(plan_raw, dict) and isinstance(plan_raw.get("input"), dict):
                run_payload["input"] = deepcopy(plan_raw.get("input", {}))
        try:
            ret = start_custom_workflow_run(
                workflow=workflow,
                payload=run_payload,
                request_context=ctx,
                source=f"api/workflows/runs/{run_id}/rerun",
            )
        except Exception as exc:
            return jsonify({"error": f"workflow 重跑失败: {exc}"}), 400
        ret["source_run_id"] = run_id
        ret["rerun_context"] = deepcopy(run_payload.get("rerun_context", {}))
        ret["request_context"] = ctx
        return jsonify(ret)

    @bp.route("/api/workflows/<workflow_id>", methods=["DELETE"])
    def api_workflows_delete(workflow_id: str):
        ctx = parse_request_context()
        workflow_key = normalize_agent_template_id(workflow_id)
        if not workflow_key:
            return jsonify({"error": "workflow_id 无效"}), 400
        with custom_workflow_lock_getter():
            store = read_custom_workflow_store()
            deleted = store.pop(workflow_key, None)
            if deleted is None:
                return jsonify({"error": f"workflow 不存在: {workflow_key}"}), 404
            save_custom_workflow_store(store)
        return jsonify({"ok": True, "deleted": deleted, "request_context": ctx})

    return bp

