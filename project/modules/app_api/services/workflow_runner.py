"""Workflow management functions extracted from server.py (L1-4)."""

import json
import uuid
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

# ── Module-level constants ──────────────────────────────────────────
_AGENT_TASK_HISTORY_MAX = 600
_CUSTOM_WORKFLOW_STEP_LIMIT = 60
_CUSTOM_WORKFLOW_HISTORY_MAX = 500

# ── Module-level state (defaults; overwritten by init()) ────────────
_custom_workflow_lock = threading.Lock()
_custom_workflow_store_mem: Dict[str, Dict[str, Any]] = {}
_custom_workflow_runs_mem: List[Dict[str, Any]] = []
_project_dir = None  # Injected via init()


def _get_project_dir():
    """Always read _project_dir from server module to stay in sync with tests."""
    try:
        from modules.app_api import server
        return server._project_dir
    except Exception:
        return _project_dir


def init(*, project_dir=None, custom_workflow_lock=None, custom_workflow_store_mem=None, custom_workflow_runs_mem=None):
    global _project_dir, _custom_workflow_lock, _custom_workflow_store_mem, _custom_workflow_runs_mem
    if project_dir is not None:
        _project_dir = project_dir
    if custom_workflow_lock is not None:
        _custom_workflow_lock = custom_workflow_lock
    if custom_workflow_store_mem is not None:
        _custom_workflow_store_mem = custom_workflow_store_mem
    if custom_workflow_runs_mem is not None:
        _custom_workflow_runs_mem = custom_workflow_runs_mem


def _read_agent_task_history() -> List[Dict[str, Any]]:
    from modules.app_api.server import _read_project_json
    raw = _read_project_json("agent_task_history.json", fallback=[])
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    if len(out) > _AGENT_TASK_HISTORY_MAX:
        out = out[-_AGENT_TASK_HISTORY_MAX:]
    return out


def _save_agent_task_history(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from modules.app_api.server import _project_data_path
    out: List[Dict[str, Any]] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                out.append(item)
    if len(out) > _AGENT_TASK_HISTORY_MAX:
        out = out[-_AGENT_TASK_HISTORY_MAX:]
    p = _project_data_path("agent_task_history.json")
    if p is not None:
        from modules.app_api.param_utils import atomic_write_json
        atomic_write_json(p, out)
    return out


def _find_agent_task_history_record(job_id: str) -> Optional[Dict[str, Any]]:
    jid = str(job_id or "").strip()
    if not jid:
        return None
    history = _read_agent_task_history()
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("job_id", "") or "").strip() == jid:
            return deepcopy(item)
    return None


def _custom_workflow_store_path() -> Optional[Path]:
    from modules.app_api.server import _project_data_path
    return _project_data_path("custom_workflows.json")


def _custom_workflow_runs_path() -> Optional[Path]:
    from modules.app_api.server import _project_data_path
    return _project_data_path("custom_workflow_runs.json")


def _normalize_custom_workflow_id(value: Any, fallback: str = "") -> str:
    from modules.app_api.server import _normalize_agent_template_id
    raw = str(value or "").strip() or str(fallback or "").strip()
    if not raw:
        return ""
    normalized = _normalize_agent_template_id(raw)
    if normalized:
        return normalized
    return f"workflow_{uuid.uuid4().hex[:8]}"


def _parse_custom_workflow_tags(raw: Any) -> List[str]:
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


def _normalize_custom_workflow_step(step_raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    from modules.app_api.server import _normalize_agent_template_id, _coerce_bool
    if not isinstance(step_raw, dict):
        raise ValueError(f"steps[{idx}] 必须是对象")
    node_type = str(step_raw.get("node_type", "action") or "action").strip().lower()
    if node_type not in {"action", "condition"}:
        raise ValueError(f"steps[{idx}].node_type 仅支持 action/condition")
    capability_id = str(step_raw.get("capability_id", "") or "").strip().lower()
    if node_type == "action" and not capability_id:
        raise ValueError(f"steps[{idx}].capability_id 不能为空")
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
        raise ValueError(f"steps[{idx}].input 必须是对象")
    input_mode_raw = str(step_raw.get("input_mode", "auto") or "auto").strip().lower()
    if input_mode_raw not in {"auto", "project", "inline"}:
        raise ValueError(f"steps[{idx}].input_mode 仅支持 auto/project/inline")
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


def _normalize_custom_workflow_payload(
    payload: Dict[str, Any],
    *,
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from modules.app_api.server import _normalize_agent_template_id
    raw = payload if isinstance(payload, dict) else {}
    base = existing if isinstance(existing, dict) else {}

    name = str(raw.get("name", base.get("name", "")) or "").strip()
    workflow_id = _normalize_custom_workflow_id(raw.get("workflow_id", base.get("workflow_id", "")), fallback=name)
    if not workflow_id:
        workflow_id = f"workflow_{uuid.uuid4().hex[:8]}"
    if not name:
        name = str(base.get("name", "") or workflow_id).strip() or workflow_id
    description = str(raw.get("description", base.get("description", "")) or "").strip()

    input_mode = str(raw.get("input_mode", base.get("input_mode", "auto")) or "auto").strip().lower()
    if input_mode not in {"auto", "project", "inline"}:
        input_mode = "auto"

    tags = _parse_custom_workflow_tags(raw.get("tags", base.get("tags", [])))
    steps_raw = raw.get("steps", base.get("steps", []))
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("steps 不能为空")
    if len(steps_raw) > _CUSTOM_WORKFLOW_STEP_LIMIT:
        raise ValueError(f"steps 最多支持 {_CUSTOM_WORKFLOW_STEP_LIMIT} 个")

    steps: List[Dict[str, Any]] = []
    seen_step_ids = set()
    for idx, step_raw in enumerate(steps_raw, start=1):
        step = _normalize_custom_workflow_step(step_raw, idx)
        sid = step["step_id"]
        if sid in seen_step_ids:
            raise ValueError(f"steps.step_id 重复: {sid}")
        seen_step_ids.add(sid)
        steps.append(step)

    start_step_id = _normalize_agent_template_id(raw.get("start_step_id", base.get("start_step_id", "")))
    if start_step_id and start_step_id not in seen_step_ids:
        raise ValueError(f"start_step_id 不存在于 steps: {start_step_id}")

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


def _read_custom_workflow_store() -> Dict[str, Dict[str, Any]]:
    if _get_project_dir() is None:
        return deepcopy(_custom_workflow_store_mem)

    p = _custom_workflow_store_path()
    raw: Any = {}
    if p is not None and p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    if raw is None:
        raw = {}

    candidates: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        workflows_raw = raw.get("workflows")
        if isinstance(workflows_raw, list):
            candidates.extend([x for x in workflows_raw if isinstance(x, dict)])
        else:
            for key, value in raw.items():
                if not isinstance(value, dict):
                    continue
                item = deepcopy(value)
                item.setdefault("workflow_id", str(key))
                candidates.append(item)
    elif isinstance(raw, list):
        candidates.extend([x for x in raw if isinstance(x, dict)])

    out: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        try:
            normalized = _normalize_custom_workflow_payload(item)
        except Exception:
            continue
        out[normalized["workflow_id"]] = normalized
    return out


def _save_custom_workflow_store(store: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(store, dict):
        for key, value in store.items():
            if not isinstance(value, dict):
                continue
            candidate = deepcopy(value)
            if not str(candidate.get("workflow_id", "") or "").strip():
                candidate["workflow_id"] = str(key or "")
            try:
                normalized = _normalize_custom_workflow_payload(candidate, existing=value)
            except Exception:
                continue
            out[normalized["workflow_id"]] = normalized

    _custom_workflow_store_mem.clear()
    _custom_workflow_store_mem.update(deepcopy(out))

    p = _custom_workflow_store_path()
    if p is not None:
        data = {"version": 1, "updated_at": datetime.now().isoformat(timespec="seconds"), "workflows": list(out.values())}
        from modules.app_api.param_utils import atomic_write_json
        atomic_write_json(p, data)
    return out


def _read_custom_workflow_runs() -> List[Dict[str, Any]]:
    if _get_project_dir() is None:
        return deepcopy(_custom_workflow_runs_mem)
    p = _custom_workflow_runs_path()
    if p is None or not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    if len(out) > _CUSTOM_WORKFLOW_HISTORY_MAX:
        out = out[-_CUSTOM_WORKFLOW_HISTORY_MAX:]
    return out


def _save_custom_workflow_runs(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                out.append(item)
    if len(out) > _CUSTOM_WORKFLOW_HISTORY_MAX:
        out = out[-_CUSTOM_WORKFLOW_HISTORY_MAX:]

    _custom_workflow_runs_mem.clear()
    _custom_workflow_runs_mem.extend(deepcopy(out))

    p = _custom_workflow_runs_path()
    if p is not None:
        from modules.app_api.param_utils import atomic_write_json
        atomic_write_json(p, out)
    return out


def _append_custom_workflow_run(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    with _custom_workflow_lock:
        history = _read_custom_workflow_runs()
        history.append(record if isinstance(record, dict) else {})
        return _save_custom_workflow_runs(history)


def _find_custom_workflow_run(run_id: str) -> Optional[Dict[str, Any]]:
    rid = str(run_id or "").strip()
    if not rid:
        return None
    runs = _read_custom_workflow_runs()
    for item in reversed(runs):
        if not isinstance(item, dict):
            continue
        if str(item.get("run_id", "") or "").strip() == rid:
            return deepcopy(item)
    return None


def _build_custom_workflow_catalog() -> List[Dict[str, Any]]:
    from modules.app_api.server import _agent_capability_route_map, _resolve_agent_primary_call, _capability_supports_input_mode
    route_map = _agent_capability_route_map()
    catalog: List[Dict[str, Any]] = []
    for capability_id in sorted(route_map.keys()):
        routes = route_map.get(capability_id, {})
        if not isinstance(routes, dict) or not routes:
            continue
        actions: List[Dict[str, str]] = []
        for action, route in routes.items():
            route_text = str(route or "").strip()
            if not route_text:
                continue
            method, endpoint = route_text.split(" ", 1) if " " in route_text else ("POST", route_text)
            actions.append(
                {
                    "action": str(action or "").strip().lower(),
                    "method": str(method or "POST").strip().upper(),
                    "endpoint": str(endpoint or "").strip(),
                }
            )
        if not actions:
            continue
        try:
            primary = _resolve_agent_primary_call(capability_id=capability_id, routes=routes, action="auto")
        except Exception:
            primary = {"method": actions[0]["method"], "endpoint": actions[0]["endpoint"]}
        catalog.append(
            {
                "capability_id": capability_id,
                "actions": actions,
                "default_action": "auto",
                "primary_call": primary,
                "supports_input_mode": _capability_supports_input_mode(capability_id),
            }
        )
    return catalog


def _extract_agent_replay_spec(replay_raw: Any) -> Dict[str, Any]:
    from modules.app_api.server import _normalize_agent_replay_context
    raw = replay_raw if isinstance(replay_raw, dict) else {}
    endpoint = str(raw.get("endpoint", "") or "").strip()
    if not endpoint:
        return {}
    method = str(raw.get("method", "POST") or "POST").strip().upper()
    if method not in {"GET", "POST"}:
        method = "POST"
    payload = deepcopy(raw.get("payload", {})) if isinstance(raw.get("payload"), dict) else {}
    request_context = _normalize_agent_replay_context(raw.get("request_context", {}))
    return {
        "method": method,
        "endpoint": endpoint,
        "payload": payload,
        "request_context": request_context,
    }


def _extract_template_ids_from_value(value: Any, max_count: int = 64) -> List[str]:
    from modules.app_api.server import _normalize_agent_template_id
    found: List[str] = []
    seen = set()

    def _push(text: str):
        tid = _normalize_agent_template_id(str(text or "").strip())
        if not tid or tid in seen:
            return
        seen.add(tid)
        found.append(tid)

    def _walk(node: Any):
        if len(found) >= max_count:
            return
        if isinstance(node, dict):
            for key, val in node.items():
                key_text = str(key or "").strip().lower()
                if key_text in {"template_id", "base_template_id"}:
                    if isinstance(val, str):
                        _push(val)
                    elif isinstance(val, list):
                        for x in val:
                            if isinstance(x, str):
                                _push(x)
                elif key_text in {"template_ids", "templates"} and isinstance(val, list):
                    for x in val:
                        if isinstance(x, str):
                            _push(x)
                        elif isinstance(x, dict):
                            inner_tid = x.get("template_id")
                            if isinstance(inner_tid, str):
                                _push(inner_tid)
                _walk(val)
                if len(found) >= max_count:
                    return
        elif isinstance(node, list):
            for item in node:
                _walk(item)
                if len(found) >= max_count:
                    return

    _walk(value)
    return found


# ── Workflow execution functions (appended in final extraction batch) ──

def _normalize_agent_skill_condition(condition_raw):
    from modules.app_api.server import _normalize_agent_template_id, _coerce_bool
    raw = condition_raw if isinstance(condition_raw, dict) else {}
    if not raw:
        return {}
    depends_on_raw = raw.get("depends_on", [])
    depends_on = []
    if isinstance(depends_on_raw, list):
        for item in depends_on_raw:
            sid = _normalize_agent_template_id(str(item or "").strip())
            if sid:
                depends_on.append(sid)
    status_in_raw = raw.get("status_in", ["done"])
    status_in = []
    if isinstance(status_in_raw, list):
        for item in status_in_raw:
            st = str(item or "").strip().lower()
            if st in {"done", "error", "skipped"}:
                status_in.append(st)
    if not status_in:
        status_in = ["done"]
    return {
        "depends_on": list(dict.fromkeys(depends_on)),
        "status_in": sorted(set(status_in)),
        "require_all": _coerce_bool(raw.get("require_all", True), default=True),
        "if_overall_ok": _coerce_bool(raw.get("if_overall_ok", False), default=False),
    }


def _capability_supports_input_mode(capability_id):
    cid = str(capability_id or "").strip().lower()
    return cid in {
        "topic_library",
        "topic_copy",
        "text_rough_cut",
        "short_clip",
        "refinement",
        "publish_prep",
        "subtitle_calibration",
        "image_semantic",
        "article_expand",
        "content_publish",
        "social_export",
        "audio_voice",
    }


def _normalize_agent_input_mode_value(raw_value):
    from modules.app_api.services.capability_helpers import _parse_capability_input_mode
    text = str(raw_value or "").strip().lower()
    if text == "auto":
        return "project" if _get_project_dir() is not None else "inline"
    return _parse_capability_input_mode(text or "project", default="project")


def _apply_agent_capability_input_defaults(
    capability_id,
    input_payload,
    *,
    default_input=None,
):
    out = deepcopy(default_input) if isinstance(default_input, dict) else {}
    out.update(input_payload if isinstance(input_payload, dict) else {})

    if not _capability_supports_input_mode(capability_id):
        return out
    if "input_mode" in out:
        out["input_mode"] = _normalize_agent_input_mode_value(out.get("input_mode"))
    else:
        out["input_mode"] = "project" if _get_project_dir() is not None else "inline"
    return out


def _normalize_agent_skill_steps(
    steps_raw,
    *,
    default_retry_policy=None,
    default_timeout_seconds=120.0,
):
    from modules.app_api.server import _normalize_agent_template_id, _coerce_bool, _AGENT_SKILL_REGISTRY
    from modules.app_api.services.agent_governance_service import _normalize_skill_retry_policy, _normalize_skill_timeout_seconds
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("skills \u4e0d\u80fd\u4e3a\u7a7a\uff0c\u4e14\u5fc5\u987b\u662f\u6570\u7ec4")
    out = []
    for idx, item in enumerate(steps_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"skills[{idx}] \u5fc5\u987b\u662f\u5bf9\u8c61")
        skill_id = str(item.get("skill_id", "") or "").strip()
        if not skill_id:
            raise ValueError(f"skills[{idx}].skill_id \u4e0d\u80fd\u4e3a\u7a7a")
        skill_spec = _AGENT_SKILL_REGISTRY.get(skill_id)
        if not isinstance(skill_spec, dict):
            raise ValueError(f"\u4e0d\u652f\u6301\u7684 skill_id: {skill_id}")

        input_payload = item.get("input", {})
        if input_payload is None:
            input_payload = {}
        if not isinstance(input_payload, dict):
            raise ValueError(f"skills[{idx}].input \u5fc5\u987b\u662f\u5bf9\u8c61")
        capability_id = str(skill_spec.get("capability_id", "") or "")
        input_payload = _apply_agent_capability_input_defaults(
            capability_id,
            input_payload,
            default_input=skill_spec.get("default_input", {}),
        )

        retry_base = default_retry_policy if isinstance(default_retry_policy, dict) else {}
        retry_policy = _normalize_skill_retry_policy(
            item.get("retry_policy", retry_base),
        )
        timeout_seconds = _normalize_skill_timeout_seconds(
            item.get("timeout_seconds", default_timeout_seconds),
            default=default_timeout_seconds,
        )
        continue_on_error = _coerce_bool(item.get("continue_on_error", False), default=False)
        step_id_raw = str(item.get("step_id", "") or "").strip()
        step_id = _normalize_agent_template_id(step_id_raw) or f"step_{idx:02d}"
        condition = _normalize_agent_skill_condition(item.get("condition", item.get("when", {})))

        out.append({
            "index": idx,
            "step_id": step_id,
            "skill_id": skill_id,
            "skill_name": str(skill_spec.get("name", "") or ""),
            "capability_id": capability_id,
            "method": str(skill_spec.get("method", "POST") or "POST").strip().upper(),
            "endpoint": str(skill_spec.get("endpoint", "") or "").strip(),
            "input": deepcopy(input_payload),
            "retry_policy": retry_policy,
            "timeout_seconds": timeout_seconds,
            "continue_on_error": continue_on_error,
            "condition": condition,
        })
    return out


def _resolve_agent_primary_call(
    *,
    capability_id,
    routes,
    action="auto",
):
    action_norm = str(action or "auto").strip().lower()
    picked = ""
    if action_norm and action_norm != "auto":
        picked = str(routes.get(action_norm, "") or "").strip()
        if not picked:
            raise ValueError(f"capability={capability_id} \u4e0d\u652f\u6301 action={action_norm}")
    else:
        picked = (
            str(routes.get("run", "") or "").strip()
            or str(routes.get("plan", "") or "").strip()
            or str(routes.get("draft", "") or "").strip()
            or str(routes.get("list", "") or "").strip()
            or str(next(iter(routes.values()), "") or "").strip()
        )
    if not picked:
        raise ValueError(f"capability={capability_id} \u7f3a\u5c11\u53ef\u6267\u884c\u8def\u7531")
    method, endpoint = picked.split(" ", 1) if " " in picked else ("POST", picked)
    return {"method": str(method or "POST").strip().upper(), "endpoint": str(endpoint or "").strip()}


def _invoke_agent_primary_call(
    *,
    method,
    endpoint,
    payload,
    request_context,
):
    from modules.app_api.server import app
    method_upper = str(method or "POST").strip().upper()
    req_payload = dict(payload) if isinstance(payload, dict) else {}

    with app.test_client() as client:
        if method_upper == "GET":
            query = {}
            for k, v in req_payload.items():
                if v is None:
                    continue
                if isinstance(v, dict):
                    query[str(k)] = json.dumps(v, ensure_ascii=False)
                elif isinstance(v, (list, tuple, set)):
                    query[str(k)] = ",".join(str(x) for x in v)
                else:
                    query[str(k)] = str(v)
            for k in ("actor_type", "actor_id", "run_mode", "idempotency_key", "trace_id"):
                val = str(request_context.get(k, "") or "").strip()
                if val:
                    query[k] = val
            resp = client.open(endpoint, method=method_upper, query_string=query)
        else:
            for k in ("actor_type", "actor_id", "run_mode", "idempotency_key", "trace_id"):
                val = str(request_context.get(k, "") or "").strip()
                if val and k not in req_payload:
                    req_payload[k] = val
            resp = client.open(endpoint, method=method_upper, json=req_payload)

    data = resp.get_json(silent=True)
    if not isinstance(data, dict):
        data = {
            "ok": False,
            "error": f"\u76ee\u6807\u63a5\u53e3\u8fd4\u56de\u975e JSON: {endpoint}",
            "status_code": int(resp.status_code),
        }
    return {"status_code": int(resp.status_code), "data": data}


import re as _re
_WORKFLOW_TEMPLATE_PATTERN = _re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _workflow_get_path_value(path_expr, context):
    path = str(path_expr or "").strip()
    if not path:
        return None
    cur = context
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


def _resolve_workflow_templates(
    value,
    *,
    context,
    warnings,
):
    if isinstance(value, dict):
        return {
            k: _resolve_workflow_templates(v, context=context, warnings=warnings)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_workflow_templates(item, context=context, warnings=warnings)
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
        resolved = _workflow_get_path_value(key, context)
        if resolved is None:
            warnings.append(f"workflow \u6a21\u677f\u53d8\u91cf\u672a\u547d\u4e2d: {key}")
            return value
        return resolved

    out = text
    for match in matches:
        key = str(match.group(1) or "").strip()
        resolved = _workflow_get_path_value(key, context)
        if resolved is None:
            warnings.append(f"workflow \u6a21\u677f\u53d8\u91cf\u672a\u547d\u4e2d: {key}")
            continue
        if isinstance(resolved, (dict, list)):
            repl = json.dumps(resolved, ensure_ascii=False)
        else:
            repl = str(resolved)
        out = out.replace(match.group(0), repl)
    return out


def _workflow_truthy(value):
    from modules.app_api.server import _coerce_bool as _server_coerce_bool
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


def _workflow_pick_next_step_id(
    *,
    step,
    current_step_id,
    default_next_map,
    status,
):
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


def _workflow_pick_target_with_source(
    *candidates,
):
    for target_raw, source in candidates:
        target = str(target_raw or "").strip()
        if target:
            return target, str(source or "").strip() or "unknown"
    return "", "none"


def _workflow_graph_has_cycle(adjacency):
    state = {}
    # 0=unvisited, 1=visiting, 2=done

    def _dfs(node):
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


def _build_custom_workflow_graph(
    *,
    steps,
    requested_start_step_id,
):
    from modules.app_api.server import _normalize_agent_template_id, _coerce_bool
    rows = steps if isinstance(steps, list) else []
    ordered_step_ids = []
    step_map = {}
    default_next_map = {}
    nodes = []
    transitions = []
    edge_seen = set()
    edges = []

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
        from_step,
        to_step,
        *,
        when,
        source,
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
            true_to, true_source = _workflow_pick_target_with_source(
                (next_on_success, "next_on_success"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            false_to, false_source = _workflow_pick_target_with_source(
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
            success_to, success_source = _workflow_pick_target_with_source(
                (next_on_success, "next_on_success"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            error_to, error_source = _workflow_pick_target_with_source(
                (next_on_error, "next_on_error"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            skip_to, skip_source = _workflow_pick_target_with_source(
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

    adjacency = {}
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

    has_cycle = _workflow_graph_has_cycle(adjacency)
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


def _build_failed_only_workflow_subset(
    *,
    workflow,
    base_run,
):
    from modules.app_api.server import _normalize_agent_template_id
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

    step_order = {}
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
    graph = _build_custom_workflow_graph(
        steps=steps,
        requested_start_step_id=requested_start,
    )

    reverse_adj = {}
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

    subset_steps = []
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
        sub_graph = _build_custom_workflow_graph(steps=subset_steps, requested_start_step_id="")
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


def _resolve_custom_workflow_from_payload(payload):
    from modules.app_api.server import _normalize_agent_template_id
    raw = payload if isinstance(payload, dict) else {}
    workflow_raw = raw.get("workflow")
    if isinstance(workflow_raw, dict):
        return _normalize_custom_workflow_payload(workflow_raw)

    workflow_id = _normalize_agent_template_id(raw.get("workflow_id", ""))
    if workflow_id and not str(raw.get("workflow", "")).strip():
        store = _read_custom_workflow_store()
        item = store.get(workflow_id)
        if isinstance(item, dict):
            return deepcopy(item)
        raise ValueError(f"workflow \u4e0d\u5b58\u5728: {workflow_id}")

    if isinstance(raw.get("steps"), list):
        return _normalize_custom_workflow_payload(raw)

    raise ValueError("\u7f3a\u5c11 workflow/workflow_id\uff08\u6216 inline steps\uff09")


def _build_custom_workflow_plan(
    *,
    workflow,
    payload,
    dry_run,
):
    from modules.app_api.server import _normalize_agent_template_id, _coerce_bool, _deep_merge_dict
    from modules.app_api.services.agent_governance_service import _agent_capability_route_map
    route_map = _agent_capability_route_map()
    steps_raw = workflow.get("steps", []) if isinstance(workflow, dict) else []
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("workflow.steps \u4e0d\u80fd\u4e3a\u7a7a")

    step_inputs_raw = payload.get("step_inputs", {})
    step_inputs = step_inputs_raw if isinstance(step_inputs_raw, dict) else {}
    workflow_input_raw = payload.get("input", {})
    workflow_input = workflow_input_raw if isinstance(workflow_input_raw, dict) else {}
    workflow_default_mode = str(workflow.get("input_mode", "auto") or "auto").strip().lower()
    if workflow_default_mode not in {"auto", "project", "inline"}:
        workflow_default_mode = "auto"

    planned_steps = []
    for idx, step in enumerate(steps_raw, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{idx}] \u5fc5\u987b\u662f\u5bf9\u8c61")
        node_type = str(step.get("node_type", "action") or "action").strip().lower()
        if node_type not in {"action", "condition"}:
            raise ValueError(f"steps[{idx}].node_type \u4ec5\u652f\u6301 action/condition")
        capability_id = str(step.get("capability_id", "") or "").strip().lower()
        action = str(step.get("action", "auto") or "auto").strip().lower()
        if not action:
            action = "auto"

        step_id = _normalize_agent_template_id(step.get("step_id", "")) or f"step_{idx:02d}"
        input_template = step.get("input", {})
        if input_template is None:
            input_template = {}
        if not isinstance(input_template, dict):
            raise ValueError(f"steps[{idx}].input \u5fc5\u987b\u662f\u5bf9\u8c61")
        input_template = deepcopy(input_template)

        step_override = step_inputs.get(step_id, {})
        if isinstance(step_override, dict) and step_override:
            input_template = _deep_merge_dict(input_template, step_override)

        candidate_mode = str(step.get("input_mode", workflow_default_mode) or workflow_default_mode).strip().lower()
        if candidate_mode not in {"auto", "project", "inline"}:
            candidate_mode = workflow_default_mode

        resolved_method = "POST"
        resolved_endpoint = ""
        if node_type == "action":
            if not capability_id:
                raise ValueError(f"steps[{idx}].capability_id \u4e0d\u80fd\u4e3a\u7a7a")
            routes = route_map.get(capability_id)
            if not isinstance(routes, dict) or not routes:
                raise ValueError(f"steps[{idx}] \u4e0d\u652f\u6301 capability_id={capability_id}")
            resolved = _resolve_agent_primary_call(capability_id=capability_id, routes=routes, action=action)
            resolved_method = str(resolved.get("method", "POST") or "POST").strip().upper()
            resolved_endpoint = str(resolved.get("endpoint", "") or "").strip()

            if _capability_supports_input_mode(capability_id):
                if "input_mode" not in input_template:
                    input_template["input_mode"] = candidate_mode
                input_template = _apply_agent_capability_input_defaults(capability_id, input_template)

            if dry_run and resolved_method != "GET" and "dry_run" not in input_template:
                input_template["dry_run"] = True
        else:
            if capability_id:
                # condition node allows capability_id to be empty; if provided, kept as annotation only
                capability_id = str(capability_id).strip().lower()

        planned_steps.append(
            {
                "index": idx,
                "step_id": step_id,
                "node_type": node_type,
                "name": str(step.get("name", "") or "").strip(),
                "description": str(step.get("description", "") or "").strip(),
                "capability_id": capability_id,
                "action": action,
                "method": resolved_method,
                "endpoint": resolved_endpoint,
                "input_template": input_template,
                "condition": deepcopy(step.get("condition", "")),
                "run_if": deepcopy(step.get("run_if", "")),
                "continue_on_error": _coerce_bool(step.get("continue_on_error", False), default=False),
                "enabled": _coerce_bool(step.get("enabled", True), default=True),
                "save_as": _normalize_agent_template_id(step.get("save_as", "")),
                "next_step_id": _normalize_agent_template_id(step.get("next_step_id", "")),
                "next_on_success": _normalize_agent_template_id(step.get("next_on_success", "")),
                "next_on_error": _normalize_agent_template_id(step.get("next_on_error", "")),
                "next_on_skip": _normalize_agent_template_id(step.get("next_on_skip", "")),
            }
        )

    step_ids = {str(item.get("step_id", "") or "") for item in planned_steps}
    for item in planned_steps:
        sid = str(item.get("step_id", "") or "")
        for route_key in ("next_step_id", "next_on_success", "next_on_error", "next_on_skip"):
            target = str(item.get(route_key, "") or "").strip()
            if target and target not in step_ids:
                raise ValueError(f"step={sid} \u7684 {route_key} \u6307\u5411\u4e0d\u5b58\u5728\u7684 step_id: {target}")

    start_step_id = _normalize_agent_template_id(payload.get("start_step_id", workflow.get("start_step_id", "")))
    graph = _build_custom_workflow_graph(
        steps=planned_steps,
        requested_start_step_id=start_step_id,
    )

    return {
        "workflow_id": str(workflow.get("workflow_id", "") or ""),
        "name": str(workflow.get("name", "") or ""),
        "description": str(workflow.get("description", "") or ""),
        "input_mode": workflow_default_mode,
        "input": deepcopy(workflow_input),
        "start_step_id": start_step_id,
        "graph": graph,
        "dry_run": bool(dry_run),
        "steps": planned_steps,
        "total_steps": len(planned_steps),
    }


def _execute_custom_workflow_plan(
    *,
    plan,
    request_context,
    job_id,
):
    import time as _time
    from modules.app_api.server import _normalize_agent_template_id, _coerce_bool, _jobs, _extract_artifacts_from_payload, JobCancelledError
    started_at_iso = datetime.now().isoformat(timespec="seconds")
    started = _time.monotonic()
    steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
    total = len(steps)

    step_map = {}
    ordered_step_ids = []
    default_next_map = {}
    for idx, step in enumerate(steps):
        sid = str(step.get("step_id", "") or "").strip()
        if not sid:
            continue
        step_map[sid] = step
        ordered_step_ids.append(sid)
        default_next_map[sid] = (
            str(steps[idx + 1].get("step_id", "") or "").strip()
            if idx + 1 < len(steps)
            else ""
        )

    history_steps = []
    warnings = []
    artifact_rows = []
    artifact_seen = set()
    execution_path = []
    reached_set = set()

    state = "done"
    success_count = 0
    failed_count = 0
    skipped_count = 0

    template_context = {
        "workflow": {"input": deepcopy(plan.get("input", {})) if isinstance(plan.get("input"), dict) else {}},
        "input": deepcopy(plan.get("input", {})) if isinstance(plan.get("input"), dict) else {},
        "steps": {},
        "vars": {},
        "last": {},
        "request_context": deepcopy(request_context),
    }

    start_step_id = _normalize_agent_template_id(plan.get("start_step_id", ""))
    if not start_step_id:
        start_step_id = ordered_step_ids[0] if ordered_step_ids else ""
    if start_step_id and start_step_id not in step_map:
        warnings.append(f"start_step_id \u4e0d\u5b58\u5728\uff0c\u5df2\u56de\u9000\u9996\u8282\u70b9: {start_step_id}")
        start_step_id = ordered_step_ids[0] if ordered_step_ids else ""

    max_hops = max(total * 4, 20)
    hops = 0
    current_step_id = start_step_id
    while current_step_id:
        hops += 1
        if hops > max_hops:
            warnings.append(f"workflow \u8def\u5f84\u8d85\u8fc7\u6700\u5927\u8df3\u6570 {max_hops}\uff0c\u5df2\u63d0\u524d\u505c\u6b62\uff08\u53ef\u80fd\u5b58\u5728\u73af\u8def\uff09")
            break
        if current_step_id in reached_set:
            warnings.append(f"\u68c0\u6d4b\u5230\u73af\u8def\u6216\u91cd\u590d\u8282\u70b9: {current_step_id}\uff0c\u5df2\u505c\u6b62")
            break
        step = step_map.get(current_step_id)
        if not isinstance(step, dict):
            warnings.append(f"\u8282\u70b9\u4e0d\u5b58\u5728: {current_step_id}\uff0c\u6267\u884c\u63d0\u524d\u7ec8\u6b62")
            break
        reached_set.add(current_step_id)
        execution_path.append(current_step_id)

        idx = int(step.get("index", len(history_steps) + 1) or (len(history_steps) + 1))
        step_id = str(step.get("step_id", current_step_id) or current_step_id)
        node_type = str(step.get("node_type", "action") or "action").strip().lower()
        continue_on_error = _coerce_bool(step.get("continue_on_error", False), default=False)

        if _jobs.get(job_id, {}).get("cancel_requested"):
            raise JobCancelledError("\u4efb\u52a1\u5df2\u53d6\u6d88")

        progress = min(10 + int((len(execution_path) - 1) * 80 / max(total, 1)), 89)
        _jobs[job_id]["progress"] = progress
        _jobs[job_id]["log"].append(
            f"[Workflow] step_id={step_id} type={node_type} {step.get('method')} {step.get('endpoint')}"
        )

        base_item = {
            "index": idx,
            "step_id": step_id,
            "node_type": node_type,
            "capability_id": str(step.get("capability_id", "") or ""),
            "action": str(step.get("action", "auto") or "auto"),
            "method": str(step.get("method", "POST") or "POST"),
            "endpoint": str(step.get("endpoint", "") or ""),
            "continue_on_error": continue_on_error,
            "enabled": _coerce_bool(step.get("enabled", True), default=True),
            "next_step_id": str(step.get("next_step_id", "") or ""),
            "next_on_success": str(step.get("next_on_success", "") or ""),
            "next_on_error": str(step.get("next_on_error", "") or ""),
            "next_on_skip": str(step.get("next_on_skip", "") or ""),
        }

        next_step_id = ""
        request_payload = {}
        status_code = 0
        response_data = {}
        step_status = "done"
        step_error = ""
        step_duration = 0.0

        if not _coerce_bool(step.get("enabled", True), default=True):
            step_status = "skipped"
            step_error = "\u6b65\u9aa4 disabled=true"
            skipped_count += 1
            next_step_id = _workflow_pick_next_step_id(
                step=step,
                current_step_id=step_id,
                default_next_map=default_next_map,
                status="skipped",
            )
            response_data = {"ok": True, "skipped": True, "reason": step_error}
        elif node_type == "condition":
            cond_raw = step.get("condition", True)
            resolved_cond = _resolve_workflow_templates(
                deepcopy(cond_raw),
                context=template_context,
                warnings=warnings,
            )
            passed = _workflow_truthy(resolved_cond)
            step_status = "done"
            status_code = 200
            response_data = {"ok": True, "passed": passed, "condition": resolved_cond}
            step_duration = 0.0001
            success_count += 1
            if passed:
                next_step_id = (
                    str(step.get("next_on_success", "") or "").strip()
                    or str(step.get("next_step_id", "") or "").strip()
                    or default_next_map.get(step_id, "")
                )
            else:
                next_step_id = (
                    str(step.get("next_on_error", "") or "").strip()
                    or str(step.get("next_on_skip", "") or "").strip()
                    or str(step.get("next_step_id", "") or "").strip()
                    or default_next_map.get(step_id, "")
                )
        else:
            run_if_raw = step.get("run_if", "")
            run_if_enabled = not (
                run_if_raw is None
                or (isinstance(run_if_raw, str) and not str(run_if_raw).strip())
            )
            if run_if_enabled:
                run_if_resolved = _resolve_workflow_templates(
                    deepcopy(run_if_raw),
                    context=template_context,
                    warnings=warnings,
                )
                if not _workflow_truthy(run_if_resolved):
                    step_status = "skipped"
                    step_error = "run_if \u6761\u4ef6\u4e0d\u6ee1\u8db3"
                    skipped_count += 1
                    response_data = {"ok": True, "skipped": True, "run_if": run_if_resolved}
                    next_step_id = _workflow_pick_next_step_id(
                        step=step,
                        current_step_id=step_id,
                        default_next_map=default_next_map,
                        status="skipped",
                    )
                else:
                    request_payload = {}
                    input_template = step.get("input_template", {})
                    resolved_input = _resolve_workflow_templates(
                        input_template if isinstance(input_template, dict) else {},
                        context=template_context,
                        warnings=warnings,
                    )
                    if isinstance(resolved_input, dict):
                        request_payload = resolved_input
                    step_begin = _time.monotonic()
                    ret = _invoke_agent_primary_call(
                        method=str(step.get("method", "POST") or "POST"),
                        endpoint=str(step.get("endpoint", "") or ""),
                        payload=request_payload,
                        request_context=request_context,
                    )
                    step_duration = round(max(_time.monotonic() - step_begin, 0.0), 4)
                    status_code = int(ret.get("status_code", 0) or 0)
                    response_data = ret.get("data") if isinstance(ret.get("data"), dict) else {}
                    ok = status_code < 400 and bool(response_data.get("ok", False))
                    if ok:
                        step_status = "done"
                        success_count += 1
                        next_step_id = _workflow_pick_next_step_id(
                            step=step,
                            current_step_id=step_id,
                            default_next_map=default_next_map,
                            status="done",
                        )
                    else:
                        step_status = "error"
                        step_error = str(response_data.get("error", "") or f"step \u8c03\u7528\u5931\u8d25\uff08status={status_code}\uff09")
                        failed_count += 1
                        _jobs[job_id]["log"].append(f"[Workflow:{step_id}] \u5931\u8d25: {step_error}")
                        if continue_on_error:
                            next_step_id = _workflow_pick_next_step_id(
                                step=step,
                                current_step_id=step_id,
                                default_next_map=default_next_map,
                                status="error",
                            )
                        else:
                            next_step_id = (
                                str(step.get("next_on_error", "") or "").strip()
                                or str(step.get("next_step_id", "") or "").strip()
                            )
            else:
                request_payload = {}
                input_template = step.get("input_template", {})
                resolved_input = _resolve_workflow_templates(
                    input_template if isinstance(input_template, dict) else {},
                    context=template_context,
                    warnings=warnings,
                )
                if isinstance(resolved_input, dict):
                    request_payload = resolved_input
                step_begin = _time.monotonic()
                ret = _invoke_agent_primary_call(
                    method=str(step.get("method", "POST") or "POST"),
                    endpoint=str(step.get("endpoint", "") or ""),
                    payload=request_payload,
                    request_context=request_context,
                )
                step_duration = round(max(_time.monotonic() - step_begin, 0.0), 4)
                status_code = int(ret.get("status_code", 0) or 0)
                response_data = ret.get("data") if isinstance(ret.get("data"), dict) else {}
                ok = status_code < 400 and bool(response_data.get("ok", False))
                if ok:
                    step_status = "done"
                    success_count += 1
                    next_step_id = _workflow_pick_next_step_id(
                        step=step,
                        current_step_id=step_id,
                        default_next_map=default_next_map,
                        status="done",
                    )
                else:
                    step_status = "error"
                    step_error = str(response_data.get("error", "") or f"step \u8c03\u7528\u5931\u8d25\uff08status={status_code}\uff09")
                    failed_count += 1
                    _jobs[job_id]["log"].append(f"[Workflow:{step_id}] \u5931\u8d25: {step_error}")
                    if continue_on_error:
                        next_step_id = _workflow_pick_next_step_id(
                            step=step,
                            current_step_id=step_id,
                            default_next_map=default_next_map,
                            status="error",
                        )
                    else:
                        next_step_id = (
                            str(step.get("next_on_error", "") or "").strip()
                            or str(step.get("next_step_id", "") or "").strip()
                        )

        step_item = dict(base_item)
        step_item["status"] = step_status
        step_item["status_code"] = status_code
        step_item["duration_seconds"] = step_duration
        step_item["request_payload"] = deepcopy(request_payload)
        step_item["response"] = deepcopy(response_data)
        step_item["next_selected"] = str(next_step_id or "")
        if step_error:
            step_item["error"] = step_error
        history_steps.append(step_item)

        context_entry = {
            "status": step_status,
            "response": deepcopy(response_data),
            "status_code": status_code,
            "error": step_error,
            "request_payload": deepcopy(request_payload),
            "next_selected": str(next_step_id or ""),
        }
        template_context["steps"][step_id] = context_entry
        template_context["last"] = context_entry
        save_as = _normalize_agent_template_id(step.get("save_as", ""))
        if save_as:
            template_context.setdefault("vars", {})[save_as] = deepcopy(response_data)

        if isinstance(response_data, dict):
            for artifact in _extract_artifacts_from_payload(response_data):
                marker = (artifact.get("type", ""), artifact.get("value", ""))
                if marker in artifact_seen:
                    continue
                artifact_seen.add(marker)
                artifact_rows.append(artifact)

        if next_step_id:
            if next_step_id not in step_map:
                warnings.append(f"step={step_id} \u8df3\u8f6c\u5230\u4e0d\u5b58\u5728\u8282\u70b9: {next_step_id}\uff0c\u6267\u884c\u7ec8\u6b62")
                break
            current_step_id = next_step_id
            continue
        current_step_id = ""

    for sid in ordered_step_ids:
        if sid in reached_set:
            continue
        step = step_map.get(sid, {})
        item = {
            "index": int(step.get("index", len(history_steps) + 1) or (len(history_steps) + 1)),
            "step_id": sid,
            "node_type": str(step.get("node_type", "action") or "action"),
            "capability_id": str(step.get("capability_id", "") or ""),
            "action": str(step.get("action", "auto") or "auto"),
            "method": str(step.get("method", "POST") or "POST"),
            "endpoint": str(step.get("endpoint", "") or ""),
            "status": "unreached",
            "error": "\u672a\u8fdb\u5165\u6267\u884c\u8def\u5f84",
            "continue_on_error": _coerce_bool(step.get("continue_on_error", False), default=False),
            "enabled": _coerce_bool(step.get("enabled", True), default=True),
            "next_step_id": str(step.get("next_step_id", "") or ""),
            "next_on_success": str(step.get("next_on_success", "") or ""),
            "next_on_error": str(step.get("next_on_error", "") or ""),
            "next_on_skip": str(step.get("next_on_skip", "") or ""),
            "status_code": 0,
            "duration_seconds": 0.0,
            "request_payload": {},
            "response": {},
            "next_selected": "",
        }
        history_steps.append(item)
        skipped_count += 1

    finished_at_iso = datetime.now().isoformat(timespec="seconds")
    duration_seconds = round(max(_time.monotonic() - started, 0.0), 4)
    if failed_count == 0:
        state = "done"
    elif success_count > 0:
        state = "partial"
    else:
        state = "failed"

    return {
        "run_id": str(uuid.uuid4())[:8],
        "workflow_id": str(plan.get("workflow_id", "") or ""),
        "workflow_name": str(plan.get("name", "") or ""),
        "status": state,
        "dry_run": bool(plan.get("dry_run", False)),
        "started_at": started_at_iso,
        "finished_at": finished_at_iso,
        "duration_seconds": duration_seconds,
        "summary": {
            "total_steps": total,
            "traversed_steps": len(execution_path),
            "unreached_steps": max(total - len(execution_path), 0),
            "success_steps": success_count,
            "failed_steps": failed_count,
            "skipped_steps": skipped_count,
            "overall_ok": failed_count == 0,
        },
        "execution_path": execution_path,
        "steps": history_steps,
        "warnings": list(dict.fromkeys(str(x) for x in warnings if str(x).strip())),
        "artifacts": artifact_rows,
    }


def _start_custom_workflow_run(
    *,
    workflow,
    payload,
    request_context,
    source,
):
    from modules.app_api.server import _coerce_bool, _jobs, _run_in_bg
    dry_run = _coerce_bool(payload.get("dry_run", False), default=False)
    plan = _build_custom_workflow_plan(workflow=workflow, payload=payload, dry_run=dry_run)
    rerun_context_raw = payload.get("rerun_context", {})
    rerun_context = deepcopy(rerun_context_raw) if isinstance(rerun_context_raw, dict) else {}
    if rerun_context:
        rerun_context.setdefault("mode", "custom")
        rerun_context.setdefault("source", source)

    job_id = str(uuid.uuid4())[:8]
    run_id = str(uuid.uuid4())[:8]
    source_text = str(source or "manual").strip() or "manual"

    def _do_run():
        _jobs[job_id]["progress"] = 5
        _jobs[job_id]["log"].append(
            f"[Workflow] run_id={run_id} workflow={plan.get('workflow_id')} source={source_text}"
        )
        result = _execute_custom_workflow_plan(
            plan=plan,
            request_context=request_context,
            job_id=job_id,
        )
        result["run_id"] = run_id
        record = {
            "run_id": run_id,
            "workflow_id": str(plan.get("workflow_id", "") or ""),
            "workflow_name": str(plan.get("name", "") or ""),
            "status": str(result.get("status", "done") or "done"),
            "dry_run": bool(plan.get("dry_run", False)),
            "started_at": str(result.get("started_at", "") or ""),
            "finished_at": str(result.get("finished_at", "") or ""),
            "duration_seconds": float(result.get("duration_seconds", 0.0) or 0.0),
            "summary": deepcopy(result.get("summary", {})) if isinstance(result.get("summary"), dict) else {},
            "execution_path": deepcopy(result.get("execution_path", [])) if isinstance(result.get("execution_path"), list) else [],
            "steps": deepcopy(result.get("steps", [])) if isinstance(result.get("steps"), list) else [],
            "warnings": deepcopy(result.get("warnings", [])) if isinstance(result.get("warnings"), list) else [],
            "artifacts": deepcopy(result.get("artifacts", [])) if isinstance(result.get("artifacts"), list) else [],
            "request_context": deepcopy(request_context),
            "source": source_text,
            "workflow": deepcopy(workflow),
            "plan": deepcopy(plan),
        }
        if rerun_context:
            record["rerun_context"] = deepcopy(rerun_context)
        _append_custom_workflow_run(record)
        _jobs[job_id]["progress"] = 95
        return {"ok": True, "run": record}

    _run_in_bg(
        job_id,
        _do_run,
        kind="custom_workflow",
        job_meta={
            "workflow_id": str(plan.get("workflow_id", "") or ""),
            "source": source_text,
            "dry_run": bool(plan.get("dry_run", False)),
            "request_context": deepcopy(request_context),
            "replay": {
                "method": "POST",
                "endpoint": "/api/workflows/run",
                "payload": deepcopy(payload),
                "request_context": deepcopy(request_context),
            },
        },
    )
    return {
        "ok": True,
        "job_id": job_id,
        "run_id": run_id,
        "workflow_id": str(plan.get("workflow_id", "") or ""),
        "workflow_name": str(plan.get("name", "") or ""),
        "dry_run": bool(plan.get("dry_run", False)),
        "total_steps": int(plan.get("total_steps", 0) or 0),
        "status_endpoint": f"/api/job/{job_id}",
        "rerun_context": deepcopy(rerun_context) if rerun_context else {},
    }


def _normalize_agent_replay_context(raw):
    src = raw if isinstance(raw, dict) else {}
    actor_type = str(src.get("actor_type", "agent") or "agent").strip().lower()
    if actor_type not in {"human", "agent"}:
        actor_type = "agent"
    actor_id = str(src.get("actor_id", "") or "").strip()[:128]
    run_mode = str(src.get("run_mode", "headless") or "headless").strip().lower()
    if run_mode not in {"interactive", "headless"}:
        run_mode = "headless" if actor_type == "agent" else "interactive"
    idempotency_key = str(src.get("idempotency_key", "") or "").strip()[:128]
    trace_id = str(src.get("trace_id", "") or "").strip()[:128]
    return {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "run_mode": run_mode,
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
    }


def _execute_agent_skill(
    *,
    skill_id,
    input_payload,
    retry_policy,
    timeout_seconds,
    request_context,
    logger=None,
):
    import time as _time
    from modules.app_api.server import _AGENT_SKILL_REGISTRY
    from modules.app_api.services.agent_governance_service import (
        _normalize_skill_timeout_seconds,
        _extract_usage_tokens_from_response,
        _extract_pricing_hint_from_response,
        _estimate_step_cost_metrics,
    )
    skill_spec = _AGENT_SKILL_REGISTRY.get(skill_id)
    if not isinstance(skill_spec, dict):
        raise ValueError(f"\u4e0d\u652f\u6301\u7684 skill_id: {skill_id}")
    method = str(skill_spec.get("method", "POST") or "POST").strip().upper()
    endpoint = str(skill_spec.get("endpoint", "") or "").strip()
    if not endpoint:
        raise RuntimeError(f"skill \u914d\u7f6e\u7f3a\u5c11 endpoint: {skill_id}")
    capability_id = str(skill_spec.get("capability_id", "") or "")
    effective_input = _apply_agent_capability_input_defaults(
        capability_id,
        input_payload if isinstance(input_payload, dict) else {},
        default_input=skill_spec.get("default_input", {}),
    )

    max_attempts = int(retry_policy.get("max_retries", 0) or 0) + 1
    retry_http_codes = set(retry_policy.get("retry_on_http", []))
    backoff_s = float(int(retry_policy.get("backoff_ms", 0) or 0)) / 1000.0
    timeout_s = _normalize_skill_timeout_seconds(timeout_seconds, default=120.0)
    begin = _time.monotonic()
    final_status = 0
    final_data = {}
    attempts = 0

    # Use server module's reference to allow test patching
    from modules.app_api import server as _srv
    _invoke_fn = getattr(_srv, '_invoke_agent_primary_call', _invoke_agent_primary_call)

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        if callable(logger):
            logger(f"\u5c1d\u8bd5 {attempt}/{max_attempts} -> {method} {endpoint}")
        ret = _invoke_fn(
            method=method,
            endpoint=endpoint,
            payload=effective_input,
            request_context=request_context,
        )
        final_status = int(ret.get("status_code", 0) or 0)
        final_data = ret.get("data") if isinstance(ret.get("data"), dict) else {}
        if final_status < 400 and bool(final_data.get("ok", False)):
            duration_seconds = round(max(_time.monotonic() - begin, 0.0), 4)
            usage_tokens = _extract_usage_tokens_from_response(final_data)
            pricing_hint = _extract_pricing_hint_from_response(final_data)
            estimated_cost = _estimate_step_cost_metrics(
                prompt_tokens=int(usage_tokens.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage_tokens.get("completion_tokens", 0) or 0),
                duration_seconds=duration_seconds,
                provider=str(pricing_hint.get("provider", "") or ""),
                model=str(pricing_hint.get("model", "") or ""),
            )
            return {
                "skill_id": skill_id,
                "skill_name": str(skill_spec.get("name", "") or ""),
                "capability_id": str(skill_spec.get("capability_id", "") or ""),
                "primary_call": {
                    "method": method,
                    "endpoint": endpoint,
                    "payload": deepcopy(effective_input),
                },
                "attempts": attempts,
                "status_code": final_status,
                "response": final_data,
                "duration_seconds": duration_seconds,
                "usage_tokens": usage_tokens,
                "pricing_hint": pricing_hint,
                "estimated_cost": estimated_cost,
            }

        elapsed = _time.monotonic() - begin
        if elapsed >= timeout_s:
            raise RuntimeError(f"skill \u8c03\u7528\u8d85\u65f6\uff08{timeout_s:.1f}s\uff09")
        can_retry = attempt < max_attempts and final_status in retry_http_codes
        if not can_retry:
            break
        if backoff_s > 0:
            if callable(logger):
                logger(f"\u91cd\u8bd5\u7b49\u5f85 {backoff_s:.2f}s")
            _time.sleep(backoff_s)

    err = str(final_data.get("error", "") or f"skill \u8c03\u7528\u5931\u8d25\uff08status={final_status}\uff09")
    raise RuntimeError(err)


def _should_run_conditional_step(
    condition,
    previous_results,
):
    from modules.app_api.server import _normalize_agent_template_id, _coerce_bool
    cond = condition if isinstance(condition, dict) else {}
    if_overall_ok = _coerce_bool(cond.get("if_overall_ok", False), default=False)
    if if_overall_ok:
        for item in previous_results.values():
            if str(item.get("status", "")).lower() == "error":
                return False, "if_overall_ok \u672a\u6ee1\u8db3\uff08\u524d\u5e8f\u5b58\u5728 error\uff09"

    depends_on = cond.get("depends_on", [])
    if not isinstance(depends_on, list) or not depends_on:
        return True, ""
    status_in_raw = cond.get("status_in", ["done"])
    status_in = {str(x).lower().strip() for x in status_in_raw} if isinstance(status_in_raw, list) else {"done"}
    if not status_in:
        status_in = {"done"}
    require_all = _coerce_bool(cond.get("require_all", True), default=True)

    matched = []
    missing = []
    for dep in depends_on:
        dep_id = _normalize_agent_template_id(str(dep or "").strip())
        if not dep_id:
            continue
        dep_item = previous_results.get(dep_id)
        if not isinstance(dep_item, dict):
            missing.append(dep_id)
            matched.append(False)
            continue
        dep_status = str(dep_item.get("status", "")).strip().lower()
        matched.append(dep_status in status_in)
    if missing:
        return False, f"\u4f9d\u8d56\u672a\u5b8c\u6210: {','.join(missing)}"

    passed = all(matched) if require_all else any(matched)
    if passed:
        return True, ""
    return False, "\u4f9d\u8d56\u72b6\u6001\u4e0d\u6ee1\u8db3 condition"
