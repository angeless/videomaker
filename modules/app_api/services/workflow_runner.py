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
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
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
    if _project_dir is None:
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
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "updated_at": datetime.now().isoformat(timespec="seconds"), "workflows": list(out.values())}
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _read_custom_workflow_runs() -> List[Dict[str, Any]]:
    if _project_dir is None:
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
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
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
