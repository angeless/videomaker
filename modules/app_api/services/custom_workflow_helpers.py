"""Custom workflow normalization and graph helpers.

Extracted from server.py (Roadmap L1) — pure functions only, no IO.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import json
import re
import uuid

from modules.app_api.services.agent_governance import (
    _normalize_agent_template_id,
    _coerce_bool,
    normalize_agent_skill_condition as normalize_agent_skill_condition,
)


_CUSTOM_WORKFLOW_STEP_LIMIT = 60

_WORKFLOW_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


# ---------------------------------------------------------------------------
# Block 1: Normalization
# ---------------------------------------------------------------------------


def normalize_custom_workflow_id(value: Any, fallback: str = "") -> str:
    raw = str(value or "").strip() or str(fallback or "").strip()
    if not raw:
        return ""
    normalized = _normalize_agent_template_id(raw)
    if normalized:
        return normalized
    return f"workflow_{uuid.uuid4().hex[:8]}"


def parse_custom_workflow_tags(raw: Any) -> List[str]:
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        items = text.replace("\uff0c", ",").split(",")
    out: List[str] = []
    seen = set()
    for item in items:
        tag = str(item or "").strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag[:64])
    return out[:20]


def normalize_custom_workflow_step(step_raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    if not isinstance(step_raw, dict):
        raise ValueError(f"steps[{idx}] \u5fc5\u987b\u662f\u5bf9\u8c61")
    node_type = str(step_raw.get("node_type", "action") or "action").strip().lower()
    if node_type not in {"action", "condition"}:
        raise ValueError(f"steps[{idx}].node_type \u4ec5\u652f\u6301 action/condition")
    capability_id = str(step_raw.get("capability_id", "") or "").strip().lower()
    if node_type == "action" and not capability_id:
        raise ValueError(f"steps[{idx}].capability_id \u4e0d\u80fd\u4e3a\u7a7a")
    step_id = _normalize_agent_template_id(step_raw.get("step_id", ""))
    if not step_id:
        step_id = f"step_{idx:02d}"
    action = str(step_raw.get("action", "auto") or "auto").strip().lower()
    if not action:
        action = "auto"
    input_payload = step_raw.get("input", {})
    if input_payload is None:
        input_payload = {}
    if not isinstance(input_payload, dict):
        raise ValueError(f"steps[{idx}].input \u5fc5\u987b\u662f\u5bf9\u8c61")
    input_mode_raw = str(step_raw.get("input_mode", "auto") or "auto").strip().lower()
    if input_mode_raw not in {"auto", "project", "inline"}:
        raise ValueError(f"steps[{idx}].input_mode \u4ec5\u652f\u6301 auto/project/inline")
    save_as = _normalize_agent_template_id(step_raw.get("save_as", ""))
    next_step_id = _normalize_agent_template_id(step_raw.get("next_step_id", ""))
    next_on_success = _normalize_agent_template_id(step_raw.get("next_on_success", ""))
    next_on_error = _normalize_agent_template_id(step_raw.get("next_on_error", ""))
    next_on_skip = _normalize_agent_template_id(step_raw.get("next_on_skip", ""))
    return {
        "index": idx,
        "step_id": step_id,
        "node_type": node_type,
        "name": str(step_raw.get("name", "") or "").strip(),
        "description": str(step_raw.get("description", "") or "").strip(),
        "capability_id": capability_id,
        "action": action,
        "input": deepcopy(input_payload),
        "input_mode": input_mode_raw,
        "continue_on_error": _coerce_bool(step_raw.get("continue_on_error", False), default=False),
        "enabled": _coerce_bool(step_raw.get("enabled", True), default=True),
        "save_as": save_as,
        "next_step_id": next_step_id,
        "next_on_success": next_on_success,
        "next_on_error": next_on_error,
        "next_on_skip": next_on_skip,
        "run_if": deepcopy(step_raw.get("run_if", "")),
        "condition": deepcopy(step_raw.get("condition", "")),
    }


def normalize_custom_workflow_payload(
    payload: Dict[str, Any],
    *,
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    base = existing if isinstance(existing, dict) else {}

    name = str(raw.get("name", base.get("name", "")) or "").strip()
    workflow_id = normalize_custom_workflow_id(raw.get("workflow_id", base.get("workflow_id", "")), fallback=name)
    if not workflow_id:
        workflow_id = f"workflow_{uuid.uuid4().hex[:8]}"
    if not name:
        name = str(base.get("name", "") or workflow_id).strip() or workflow_id
    description = str(raw.get("description", base.get("description", "")) or "").strip()

    input_mode = str(raw.get("input_mode", base.get("input_mode", "auto")) or "auto").strip().lower()
    if input_mode not in {"auto", "project", "inline"}:
        input_mode = "auto"

    tags = parse_custom_workflow_tags(raw.get("tags", base.get("tags", [])))
    steps_raw = raw.get("steps", base.get("steps", []))
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("steps \u4e0d\u80fd\u4e3a\u7a7a")
    if len(steps_raw) > _CUSTOM_WORKFLOW_STEP_LIMIT:
        raise ValueError(f"steps \u6700\u591a\u652f\u6301 {_CUSTOM_WORKFLOW_STEP_LIMIT} \u4e2a")

    steps: List[Dict[str, Any]] = []
    seen_step_ids = set()
    for idx, step_raw in enumerate(steps_raw, start=1):
        step = normalize_custom_workflow_step(step_raw, idx)
        sid = step["step_id"]
        if sid in seen_step_ids:
            raise ValueError(f"steps.step_id \u91cd\u590d: {sid}")
        seen_step_ids.add(sid)
        steps.append(step)

    start_step_id = _normalize_agent_template_id(raw.get("start_step_id", base.get("start_step_id", "")))
    if start_step_id and start_step_id not in seen_step_ids:
        raise ValueError(f"start_step_id \u4e0d\u5b58\u5728\u4e8e steps: {start_step_id}")

    now_iso = datetime.now().isoformat(timespec="seconds")
    created_at = str(base.get("created_at", raw.get("created_at", now_iso)) or now_iso)
    return {
        "workflow_id": workflow_id,
        "name": name[:128],
        "description": description[:500],
        "input_mode": input_mode,
        "start_step_id": start_step_id,
        "tags": tags,
        "steps": steps,
        "created_at": created_at,
        "updated_at": now_iso,
    }


# ---------------------------------------------------------------------------
# Block 2: Graph / template / execution helpers
# ---------------------------------------------------------------------------


def workflow_get_path_value(path_expr: str, context: Dict[str, Any]) -> Any:
    path = str(path_expr or "").strip()
    if not path:
        return None
    cur: Any = context
    for token in path.split("."):
        key = str(token or "").strip()
        if not key:
            return None
        if isinstance(cur, dict):
            if key not in cur:
                return None
            cur = cur.get(key)
            continue
        if isinstance(cur, list):
            try:
                idx = int(key)
            except Exception:
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        return None
    return deepcopy(cur)


def resolve_workflow_templates(
    value: Any,
    *,
    context: Dict[str, Any],
    warnings: List[str],
) -> Any:
    if isinstance(value, dict):
        return {
            k: resolve_workflow_templates(v, context=context, warnings=warnings)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            resolve_workflow_templates(item, context=context, warnings=warnings)
            for item in value
        ]
    if not isinstance(value, str):
        return value

    text = value
    matches = list(_WORKFLOW_TEMPLATE_PATTERN.finditer(text))
    if not matches:
        return value

    if len(matches) == 1 and matches[0].span() == (0, len(text)):
        key = str(matches[0].group(1) or "").strip()
        resolved = workflow_get_path_value(key, context)
        if resolved is None:
            warnings.append(f"workflow \u6a21\u677f\u53d8\u91cf\u672a\u547d\u4e2d: {key}")
            return value
        return resolved

    out = text
    for match in matches:
        key = str(match.group(1) or "").strip()
        resolved = workflow_get_path_value(key, context)
        if resolved is None:
            warnings.append(f"workflow \u6a21\u677f\u53d8\u91cf\u672a\u547d\u4e2d: {key}")
            continue
        if isinstance(resolved, (dict, list)):
            repl = json.dumps(resolved, ensure_ascii=False)
        else:
            repl = str(resolved)
        out = out.replace(match.group(0), repl)
    return out


def workflow_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "0", "false", "no", "off", "null", "none"}:
            return False
        if text in {"1", "true", "yes", "on"}:
            return True
        return True
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return bool(value)


def workflow_pick_next_step_id(
    *,
    step: Dict[str, Any],
    current_step_id: str,
    default_next_map: Dict[str, str],
    status: str,
) -> str:
    st = str(status or "").strip().lower()
    next_explicit = str(step.get("next_step_id", "") or "").strip()
    next_success = str(step.get("next_on_success", "") or "").strip()
    next_error = str(step.get("next_on_error", "") or "").strip()
    next_skip = str(step.get("next_on_skip", "") or "").strip()

    if st == "error":
        return next_error or next_explicit or default_next_map.get(current_step_id, "")
    if st == "skipped":
        return next_skip or next_explicit or default_next_map.get(current_step_id, "")
    return next_success or next_explicit or default_next_map.get(current_step_id, "")


def workflow_pick_target_with_source(
    *candidates: Tuple[Any, str],
) -> Tuple[str, str]:
    for target_raw, source in candidates:
        target = str(target_raw or "").strip()
        if target:
            return target, str(source or "").strip() or "unknown"
    return "", "none"


def workflow_graph_has_cycle(adjacency: Dict[str, List[str]]) -> bool:
    state: Dict[str, int] = {}
    # 0=unvisited, 1=visiting, 2=done

    def _dfs(node: str) -> bool:
        st = state.get(node, 0)
        if st == 1:
            return True
        if st == 2:
            return False
        state[node] = 1
        for nxt in adjacency.get(node, []):
            if _dfs(nxt):
                return True
        state[node] = 2
        return False

    for node in adjacency.keys():
        if state.get(node, 0) == 0 and _dfs(node):
            return True
    return False


def build_custom_workflow_graph(
    *,
    steps: List[Dict[str, Any]],
    requested_start_step_id: str,
) -> Dict[str, Any]:
    rows = steps if isinstance(steps, list) else []
    ordered_step_ids: List[str] = []
    step_map: Dict[str, Dict[str, Any]] = {}
    default_next_map: Dict[str, str] = {}
    nodes: List[Dict[str, Any]] = []
    transitions: List[Dict[str, Any]] = []
    edge_seen = set()
    edges: List[Dict[str, str]] = []

    for idx, step in enumerate(rows):
        sid = str(step.get("step_id", "") or "").strip()
        if not sid:
            continue
        ordered_step_ids.append(sid)
        step_map[sid] = step
        default_next_map[sid] = (
            str(rows[idx + 1].get("step_id", "") or "").strip()
            if idx + 1 < len(rows)
            else ""
        )
        nodes.append(
            {
                "index": int(step.get("index", idx + 1) or (idx + 1)),
                "step_id": sid,
                "node_type": str(step.get("node_type", "action") or "action"),
                "capability_id": str(step.get("capability_id", "") or ""),
                "action": str(step.get("action", "auto") or "auto"),
                "enabled": _coerce_bool(step.get("enabled", True), default=True),
            }
        )

    def _append_transition_edge(
        from_step: str,
        to_step: str,
        *,
        when: str,
        source: str,
    ):
        tgt = str(to_step or "").strip()
        if not tgt:
            return
        transition_key = (str(from_step or "").strip(), str(when or "").strip(), tgt, str(source or "").strip())
        if transition_key in edge_seen:
            return
        edge_seen.add(transition_key)
        edges.append(
            {
                "from": str(from_step or "").strip(),
                "to": tgt,
                "when": str(when or "").strip(),
                "source": str(source or "").strip(),
            }
        )

    for sid in ordered_step_ids:
        step = step_map.get(sid, {})
        node_type = str(step.get("node_type", "action") or "action").strip().lower()
        next_step_id = str(step.get("next_step_id", "") or "").strip()
        next_on_success = str(step.get("next_on_success", "") or "").strip()
        next_on_error = str(step.get("next_on_error", "") or "").strip()
        next_on_skip = str(step.get("next_on_skip", "") or "").strip()
        default_next = default_next_map.get(sid, "")

        if node_type == "condition":
            true_to, true_source = workflow_pick_target_with_source(
                (next_on_success, "next_on_success"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            false_to, false_source = workflow_pick_target_with_source(
                (next_on_error, "next_on_error"),
                (next_on_skip, "next_on_skip"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            branches = [
                {"when": "condition_true", "to": true_to, "source": true_source},
                {"when": "condition_false", "to": false_to, "source": false_source},
            ]
        else:
            success_to, success_source = workflow_pick_target_with_source(
                (next_on_success, "next_on_success"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            error_to, error_source = workflow_pick_target_with_source(
                (next_on_error, "next_on_error"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            skip_to, skip_source = workflow_pick_target_with_source(
                (next_on_skip, "next_on_skip"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            branches = [
                {"when": "success", "to": success_to, "source": success_source},
                {"when": "error", "to": error_to, "source": error_source},
                {"when": "skip", "to": skip_to, "source": skip_source},
            ]

        for branch in branches:
            _append_transition_edge(
                sid,
                branch.get("to", ""),
                when=str(branch.get("when", "") or ""),
                source=str(branch.get("source", "") or ""),
            )
        transitions.append(
            {
                "step_id": sid,
                "node_type": node_type,
                "branches": branches,
            }
        )

    requested_start = _normalize_agent_template_id(requested_start_step_id)
    resolved_start = requested_start if requested_start in step_map else (ordered_step_ids[0] if ordered_step_ids else "")

    adjacency: Dict[str, List[str]] = {}
    for sid in ordered_step_ids:
        adjacency.setdefault(sid, [])
    for edge in edges:
        frm = str(edge.get("from", "") or "").strip()
        to = str(edge.get("to", "") or "").strip()
        if not frm or not to:
            continue
        if frm not in adjacency:
            adjacency[frm] = []
        if to not in adjacency[frm]:
            adjacency[frm].append(to)

    reachable = set()
    if resolved_start:
        stack = [resolved_start]
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            for nxt in adjacency.get(cur, []):
                if nxt not in reachable:
                    stack.append(nxt)

    has_cycle = workflow_graph_has_cycle(adjacency)
    unreached = [sid for sid in ordered_step_ids if sid not in reachable]

    return {
        "requested_start_step_id": requested_start,
        "start_step_id": resolved_start,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "transitions": transitions,
        "has_cycle": bool(has_cycle),
        "unreached_nodes": unreached,
    }


def build_failed_only_workflow_subset(
    *,
    workflow: Dict[str, Any],
    base_run: Dict[str, Any],
) -> Dict[str, Any]:
    steps = workflow.get("steps", []) if isinstance(workflow.get("steps"), list) else []
    if not steps:
        raise ValueError("workflow.steps \u4e0d\u80fd\u4e3a\u7a7a")

    failed_step_ids = [
        _normalize_agent_template_id(step.get("step_id", ""))
        for step in (base_run.get("steps", []) if isinstance(base_run.get("steps"), list) else [])
        if str(step.get("status", "") or "").strip().lower() == "error"
    ]
    failed_set = {sid for sid in failed_step_ids if sid}
    if not failed_set:
        raise ValueError("\u5386\u53f2 run \u6ca1\u6709\u5931\u8d25\u6b65\u9aa4\uff0c\u65e0\u6cd5 rerun_failed_only")

    step_order: Dict[str, int] = {}
    step_id_set = set()
    for idx, step in enumerate(steps):
        sid = _normalize_agent_template_id(step.get("step_id", ""))
        if not sid:
            continue
        step_order[sid] = idx
        step_id_set.add(sid)

    failed_set = {sid for sid in failed_set if sid in step_id_set}
    if not failed_set:
        raise ValueError("\u65e0\u6cd5\u5339\u914d\u5931\u8d25\u6b65\u9aa4\u5230\u5f53\u524d workflow \u5b9a\u4e49")

    requested_start = _normalize_agent_template_id(workflow.get("start_step_id", ""))
    graph = build_custom_workflow_graph(
        steps=steps,
        requested_start_step_id=requested_start,
    )

    reverse_adj: Dict[str, set] = {}
    for edge in (graph.get("edges", []) if isinstance(graph.get("edges"), list) else []):
        if not isinstance(edge, dict):
            continue
        frm = _normalize_agent_template_id(edge.get("from", ""))
        to = _normalize_agent_template_id(edge.get("to", ""))
        if not frm or not to:
            continue
        reverse_adj.setdefault(to, set()).add(frm)

    required_set = set(failed_set)
    stack = list(failed_set)
    while stack:
        cur = stack.pop()
        for parent in reverse_adj.get(cur, set()):
            if parent in required_set:
                continue
            required_set.add(parent)
            stack.append(parent)

    subset_steps: List[Dict[str, Any]] = []
    included_set = set()
    for step in steps:
        sid = _normalize_agent_template_id(step.get("step_id", ""))
        if not sid or sid not in required_set:
            continue
        subset_steps.append(deepcopy(step))
        included_set.add(sid)
    if not subset_steps:
        raise ValueError("\u65e0\u6cd5\u5339\u914d\u5931\u8d25\u6b65\u9aa4\u5230\u5f53\u524d workflow \u5b9a\u4e49")

    for step in subset_steps:
        for route_key in ("next_step_id", "next_on_success", "next_on_error", "next_on_skip"):
            target = _normalize_agent_template_id(step.get(route_key, ""))
            if target and target not in included_set:
                step[route_key] = ""

    start_step_id = requested_start if requested_start in included_set else ""
    if not start_step_id:
        sub_graph = build_custom_workflow_graph(steps=subset_steps, requested_start_step_id="")
        in_degree = {
            _normalize_agent_template_id(step.get("step_id", "")): 0
            for step in subset_steps
            if _normalize_agent_template_id(step.get("step_id", ""))
        }
        for edge in (sub_graph.get("edges", []) if isinstance(sub_graph.get("edges"), list) else []):
            if not isinstance(edge, dict):
                continue
            to = _normalize_agent_template_id(edge.get("to", ""))
            frm = _normalize_agent_template_id(edge.get("from", ""))
            if to in in_degree and frm in in_degree:
                in_degree[to] = int(in_degree.get(to, 0) or 0) + 1
        roots = [sid for sid, deg in in_degree.items() if deg == 0]
        if roots:
            roots.sort(key=lambda sid: int(step_order.get(sid, 10**9)))
            start_step_id = roots[0]
        else:
            start_step_id = _normalize_agent_template_id(subset_steps[0].get("step_id", ""))

    out = deepcopy(workflow)
    out["steps"] = subset_steps
    out["start_step_id"] = start_step_id
    return out
