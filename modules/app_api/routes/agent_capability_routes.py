#!/usr/bin/env python3
"""Agent capability discovery routes."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from flask import Blueprint, jsonify


def create_agent_capability_blueprint(
    *,
    agent_capability_route_map: Callable[[], Dict[str, Dict[str, str]]],
    list_agent_skills: Callable[[], List[Dict[str, Any]]],
    read_agent_cost_model_config: Callable[[], Dict[str, Any]],
) -> Blueprint:
    bp = Blueprint("agent_capability_api", __name__)

    @bp.route("/api/capabilities")
    def api_capabilities():
        from modules.capabilities import legacy_step_mapping, list_capabilities

        specs = [spec.__dict__ for spec in list_capabilities()]
        return jsonify({
            "ok": True,
            "capabilities": specs,
            "legacy_step_mapping": legacy_step_mapping(),
        })

    @bp.route("/api/agent/capabilities", methods=["GET"])
    def api_agent_capabilities():
        from modules.capabilities import legacy_step_mapping, list_capabilities

        specs = [spec.__dict__ for spec in list_capabilities()]
        route_map = agent_capability_route_map()
        cost_model_cfg = read_agent_cost_model_config()
        for spec in specs:
            cid = str(spec.get("capability_id", "") or "")
            spec["agent_routes"] = route_map.get(cid, {})

        return jsonify({
            "ok": True,
            "capabilities": specs,
            "legacy_step_mapping": legacy_step_mapping(),
            "agent_management_routes": {
                "templates_list": "GET /api/agent/templates",
                "templates_upsert": "POST /api/agent/templates",
                "templates_delete": "DELETE /api/agent/templates/<template_id>",
                "skills_invoke": "POST /api/agent/skills/invoke",
                "tasks_history": "GET /api/agent/tasks/history",
                "tasks_export": "POST /api/agent/tasks/<job_id>/export",
                "tasks_replay": "POST /api/agent/tasks/<job_id>/replay",
                "observability_summary": "GET /api/agent/observability",
                "observability_export": "POST /api/agent/observability/export",
                "workflows_catalog": "GET /api/workflows/catalog",
                "workflows_list": "GET /api/workflows",
                "workflows_upsert": "POST /api/workflows",
                "workflows_delete": "DELETE /api/workflows/<workflow_id>",
                "workflows_plan": "POST /api/workflows/plan",
                "workflows_run": "POST /api/workflows/run",
                "workflow_runs_history": "GET /api/workflows/runs",
                "workflow_run_rerun": "POST /api/workflows/runs/<run_id>/rerun",
            },
            "agent_skills": list_agent_skills(),
            "agent_template_schema": {
                "scope": ["system", "project", "agent"],
                "variable_types": ["string", "number", "integer", "boolean", "array", "object"],
                "fields": [
                    "template_id",
                    "name",
                    "capability_id",
                    "scope",
                    "actor_id",
                    "tags",
                    "content",
                    "base_template_id",
                    "overrides",
                    "variables",
                ],
            },
            "agent_task_modes": {
                "single_capability": {
                    "required_fields": ["capability_id", "input"],
                    "entrypoint": "POST /api/agent/tasks/run",
                },
                "skill_sequence": {
                    "required_fields": ["mode=skill_sequence", "skills[]"],
                    "supported_strategy": ["sequential", "parallel", "conditional"],
                    "entrypoint": "POST /api/agent/tasks/run",
                    "step_fields": [
                        "skill_id",
                        "input",
                        "retry_policy",
                        "timeout_seconds",
                        "continue_on_error",
                        "condition",
                    ],
                    "flow_fields": ["strategy", "max_parallel", "budget_limit"],
                    "condition_fields": ["depends_on", "status_in", "require_all", "if_overall_ok"],
                    "budget_fields": ["max_steps", "max_failures", "max_duration_seconds"],
                },
            },
            "agent_governance": {
                "policy_file": "data/agent_governance.json",
                "usage_file": "data/agent_governance_usage.json",
                "cost_model_file": "data/agent_cost_model.json",
                "resolution_order": [
                    "default_limits",
                    "actor_limits",
                    "capability_limits",
                    "actor_capability_limits",
                    "dynamic_usage_suggested_limits",
                ],
                "behavior": "tighten_only",
                "cost_model": cost_model_cfg,
                "usage_fields": [
                    "total_prompt_tokens",
                    "total_completion_tokens",
                    "total_tokens",
                    "total_estimated_cost_usd",
                    "avg_estimated_cost_usd",
                    "recent_runs",
                ],
            },
            "request_context_schema": {
                "actor_type": {"type": "string", "enum": ["human", "agent"], "default": "agent"},
                "actor_id": {"type": "string", "max_length": 128},
                "run_mode": {"type": "string", "enum": ["interactive", "headless"], "default": "headless"},
                "idempotency_key": {"type": "string", "max_length": 128},
                "trace_id": {"type": "string", "max_length": 128},
            },
        })

    return bp
