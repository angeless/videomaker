#!/usr/bin/env python3
"""Agent template routes extracted from server.py."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict

from flask import Blueprint, jsonify, request


def create_agent_template_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    parse_request_context: Callable[[], Dict[str, str]],
    parse_boolish: Callable[[Any, bool], bool],
    list_agent_templates: Callable[..., list],
    normalize_agent_template_payload: Callable[..., Dict[str, Any]],
    read_agent_template_store: Callable[[], Dict[str, Any]],
    validate_agent_template_base_reference: Callable[..., str | None],
    save_agent_template_store: Callable[[Dict[str, Any]], Dict[str, Any]],
    normalize_agent_template_id: Callable[[str], str],
) -> Blueprint:
    bp = Blueprint("agent_template_api", __name__)

    @bp.route("/api/agent/templates", methods=["GET"])
    def api_agent_templates_list():
        if project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        ctx = parse_request_context()
        capability_id = str(request.args.get("capability_id", "") or "").strip()
        scope = str(request.args.get("scope", "") or "").strip().lower()
        actor_id = str(request.args.get("actor_id", "") or "").strip() or ctx.get("actor_id", "")
        include_system = parse_boolish(request.args.get("include_system", "true"), default=True)
        resolve = parse_boolish(request.args.get("resolve", "true"), default=True)
        templates = list_agent_templates(
            capability_id=capability_id,
            scope=scope,
            actor_id=actor_id,
            include_system=include_system,
            resolve=resolve,
        )
        return jsonify(
            {
                "ok": True,
                "templates": templates,
                "count": len(templates),
                "filters": {
                    "capability_id": capability_id,
                    "scope": scope or None,
                    "actor_id": actor_id or None,
                    "include_system": include_system,
                    "resolve": resolve,
                },
            }
        )

    @bp.route("/api/agent/templates", methods=["POST"])
    def api_agent_templates_upsert():
        if project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        payload = request.json or {}
        ctx = parse_request_context()
        default_scope = str(payload.get("scope", "") or "").strip().lower()
        if not default_scope:
            default_scope = "agent" if ctx.get("actor_type") == "agent" else "project"
        try:
            tmpl = normalize_agent_template_payload(
                payload,
                scope_default=default_scope,
                actor_id_default=ctx.get("actor_id", ""),
            )
        except Exception as exc:
            return jsonify({"error": f"模板保存失败: {exc}"}), 400

        scope = str(tmpl.get("scope", "")).lower()
        if scope == "system":
            return jsonify({"error": "system scope 模板是只读内置模板，不能写入"}), 400

        store = read_agent_template_store()
        candidate_store = deepcopy(store)
        if scope == "project":
            bucket = candidate_store.setdefault("project", {})
            if not isinstance(bucket, dict):
                bucket = {}
                candidate_store["project"] = bucket
            bucket[tmpl["template_id"]] = tmpl
        else:
            actor_id = str(tmpl.get("actor_id", "") or "").strip()
            if not actor_id:
                return jsonify({"error": "agent scope 需要 actor_id"}), 400
            agent_store = candidate_store.setdefault("agent", {})
            if not isinstance(agent_store, dict):
                agent_store = {}
                candidate_store["agent"] = agent_store
            actor_bucket = agent_store.setdefault(actor_id, {})
            if not isinstance(actor_bucket, dict):
                actor_bucket = {}
                agent_store[actor_id] = actor_bucket
            actor_bucket[tmpl["template_id"]] = tmpl

        base_error = validate_agent_template_base_reference(tmpl, store=candidate_store)
        if base_error:
            return jsonify({"error": f"模板保存失败: {base_error}"}), 400

        _ = save_agent_template_store(candidate_store)
        templates = list_agent_templates(
            capability_id=str(tmpl.get("capability_id", "") or ""),
            scope=scope,
            actor_id=str(tmpl.get("actor_id", "") or ""),
            include_system=(scope == "system"),
            resolve=True,
        )
        return jsonify({"ok": True, "template": tmpl, "templates": templates})

    @bp.route("/api/agent/templates/<template_id>", methods=["DELETE"])
    def api_agent_templates_delete(template_id: str):
        if project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        ctx = parse_request_context()
        payload = request.get_json(silent=True) if request.method == "DELETE" else {}
        if not isinstance(payload, dict):
            payload = {}

        tid = normalize_agent_template_id(template_id)
        if not tid:
            return jsonify({"error": "template_id 无效"}), 400
        scope = str(request.args.get("scope", payload.get("scope", "")) or "").strip().lower()
        if scope not in {"project", "agent", "system"}:
            return jsonify({"error": "scope 不能为空，且仅支持 project/agent/system"}), 400
        if scope == "system":
            return jsonify({"error": "system scope 模板是只读内置模板，不能删除"}), 400

        store = read_agent_template_store()
        if scope == "project":
            bucket = store.get("project", {})
            if not isinstance(bucket, dict) or tid not in bucket:
                return jsonify({"error": f"模板不存在: {tid}"}), 404
            deleted = bucket.pop(tid, None)
            store["project"] = bucket
        else:
            actor_id = str(request.args.get("actor_id", payload.get("actor_id", "")) or "").strip()
            if not actor_id:
                actor_id = str(ctx.get("actor_id", "") or "").strip()
            if not actor_id:
                return jsonify({"error": "agent scope 删除需要 actor_id"}), 400
            agent_store = store.get("agent", {})
            actor_bucket = agent_store.get(actor_id, {}) if isinstance(agent_store, dict) else {}
            if not isinstance(actor_bucket, dict) or tid not in actor_bucket:
                return jsonify({"error": f"模板不存在: {tid}"}), 404
            deleted = actor_bucket.pop(tid, None)
            if isinstance(agent_store, dict):
                if actor_bucket:
                    agent_store[actor_id] = actor_bucket
                else:
                    agent_store.pop(actor_id, None)
                store["agent"] = agent_store

        save_agent_template_store(store)
        return jsonify({"ok": True, "deleted": deleted})

    return bp

