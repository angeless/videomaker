"""ETA/history/observability functions extracted from server.py."""

import json
import time
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

# ── Module-level state (injected via init()) ──
_project_dir = None

def _get_project_dir():
    """Always read _project_dir from server module to stay in sync with tests."""
    try:
        from modules.app_api import server
        return server._project_dir
    except Exception:
        return _project_dir
_eta_history_lock = threading.Lock()
_eta_history_cache: Dict[str, Any] = {
    "updated_at": 0.0,
    "avg_by_kind": {},
    "fallback_avg": 0.0,
}
_ensure_job_store = None  # callable
_jobs = None  # dict ref
_agent_history_lock = threading.Lock()


def init(
    *,
    project_dir=None,
    eta_history_lock=None,
    eta_history_cache=None,
    ensure_job_store=None,
    jobs=None,
    agent_history_lock=None,
):
    global _project_dir, _eta_history_lock, _eta_history_cache, _ensure_job_store, _jobs, _agent_history_lock
    if project_dir is not None:
        _project_dir = project_dir
    if eta_history_lock is not None:
        _eta_history_lock = eta_history_lock
    if eta_history_cache is not None:
        _eta_history_cache = eta_history_cache
    if ensure_job_store is not None:
        _ensure_job_store = ensure_job_store
    if jobs is not None:
        _jobs = jobs
    if agent_history_lock is not None:
        _agent_history_lock = agent_history_lock


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _duration_from_iso_range(started_at: Any, finished_at: Any) -> float:
    begin = _parse_iso_datetime(started_at)
    end = _parse_iso_datetime(finished_at)
    if begin is None or end is None:
        return 0.0
    return max((end - begin).total_seconds(), 0.0)


def _trimmed_avg(values: List[float]) -> float:
    nums = sorted(float(x) for x in values if float(x) > 0.0)
    if not nums:
        return 0.0
    if len(nums) >= 10:
        trim = max(1, int(len(nums) * 0.1))
        nums = nums[trim:-trim] or nums
    return max(sum(nums) / max(len(nums), 1), 0.0)


def _refresh_eta_history_cache(*, limit: int = 800, ttl_seconds: float = 30.0) -> Dict[str, Any]:
    now_ts = time.time()
    with _eta_history_lock:
        updated_at = float(_eta_history_cache.get("updated_at", 0.0) or 0.0)
        if now_ts - updated_at <= max(float(ttl_seconds), 1.0):
            return deepcopy(_eta_history_cache)

    try:
        rows = _ensure_job_store().list_jobs(limit=limit)
    except Exception:
        rows = []
    if not isinstance(rows, list):
        rows = []

    durations_by_kind: Dict[str, List[float]] = {}
    all_durations: List[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "") or "").strip().lower() != "done":
            continue
        d = _duration_from_iso_range(row.get("started_at"), row.get("finished_at"))
        if d < 2.0:
            continue
        kind = str(row.get("kind", "") or "").strip()
        all_durations.append(d)
        bucket = durations_by_kind.setdefault(kind, [])
        if len(bucket) < 200:
            bucket.append(d)

    avg_by_kind = {kind: _trimmed_avg(vals) for kind, vals in durations_by_kind.items()}
    payload = {
        "updated_at": now_ts,
        "avg_by_kind": avg_by_kind,
        "fallback_avg": _trimmed_avg(all_durations),
    }
    with _eta_history_lock:
        _eta_history_cache.update(payload)
        return deepcopy(_eta_history_cache)


def _historical_avg_duration_for_kind(kind: Any, *, ttl_seconds: float = 30.0) -> float:
    snapshot = _refresh_eta_history_cache(ttl_seconds=ttl_seconds)
    avg_by_kind = snapshot.get("avg_by_kind", {})
    if not isinstance(avg_by_kind, dict):
        avg_by_kind = {}
    kind_text = str(kind or "").strip()
    if kind_text:
        exact = avg_by_kind.get(kind_text)
        if isinstance(exact, (int, float)) and float(exact) > 0:
            return float(exact)
    fallback_avg = snapshot.get("fallback_avg", 0.0)
    try:
        return max(float(fallback_avg), 0.0)
    except Exception:
        return 0.0


def _estimate_job_eta(job: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict):
        return {"available": False, "remaining_seconds": None, "source": "none", "confidence": 0.0}

    status = str(job.get("status", "") or "").strip().lower()
    kind = str(job.get("kind", "") or "").strip()
    avg_history = _historical_avg_duration_for_kind(kind)

    if status in {"done", "error", "cancelled", "interrupted"}:
        return {
            "available": False,
            "remaining_seconds": 0,
            "source": "finished",
            "confidence": 1.0,
            "historical_avg_seconds": int(round(avg_history)) if avg_history > 0 else None,
        }

    if status == "queued":
        try:
            queue_position = int(job.get("queue_position", 0) or 0)
        except Exception:
            queue_position = 0
        if avg_history <= 0:
            return {
                "available": False,
                "remaining_seconds": None,
                "source": "queue_unknown",
                "confidence": 0.0,
                "historical_avg_seconds": None,
                "queue_position": queue_position,
            }
        wait_seconds = avg_history * max(queue_position - 1, 0)
        return {
            "available": True,
            "remaining_seconds": int(max(round(wait_seconds), 0)),
            "source": "history_queue",
            "confidence": 0.55,
            "historical_avg_seconds": int(round(avg_history)),
            "queue_position": queue_position,
        }

    if status != "running":
        return {"available": False, "remaining_seconds": None, "source": "unknown", "confidence": 0.0}

    started = _parse_iso_datetime(job.get("started_at"))
    elapsed = 0.0
    if started is not None:
        elapsed = max((datetime.now() - started).total_seconds(), 0.0)

    try:
        progress = int(job.get("progress", 0) or 0)
    except Exception:
        progress = 0
    progress = max(0, min(progress, 100))

    by_progress: Optional[float] = None
    if elapsed > 0 and progress >= 2 and progress < 100:
        by_progress = elapsed * max(100 - progress, 0) / max(progress, 1)

    by_history: Optional[float] = None
    if avg_history > 0:
        by_history = max(avg_history - elapsed, 0.0)

    remaining = None
    source = "none"
    confidence = 0.0

    if by_progress is not None and by_history is not None:
        # Blend historical signal and live progress; progress gets more weight once >20%.
        progress_weight = 0.7 if progress >= 20 else 0.5
        history_weight = 1.0 - progress_weight
        remaining = (by_progress * progress_weight) + (by_history * history_weight)
        source = "blended"
        confidence = 0.78 if progress >= 20 else 0.62
    elif by_progress is not None:
        remaining = by_progress
        source = "progress"
        confidence = 0.58 if progress >= 20 else 0.42
    elif by_history is not None:
        remaining = by_history
        source = "history"
        confidence = 0.5

    if remaining is None:
        return {
            "available": False,
            "remaining_seconds": None,
            "source": source,
            "confidence": confidence,
            "elapsed_seconds": int(round(elapsed)),
            "historical_avg_seconds": int(round(avg_history)) if avg_history > 0 else None,
        }

    remaining = max(min(float(remaining), 72 * 3600), 0.0)
    return {
        "available": True,
        "remaining_seconds": int(round(remaining)),
        "source": source,
        "confidence": round(confidence, 3),
        "elapsed_seconds": int(round(elapsed)),
        "historical_avg_seconds": int(round(avg_history)) if avg_history > 0 else None,
        "progress": progress,
    }


def _build_agent_task_history_record(job_id: str, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _get_project_dir() is None or not isinstance(job, dict):
        return None
    kind = str(job.get("kind", "") or "")
    if kind not in {"agent_task", "agent_skill"}:
        return None
    meta = job.get("meta", {}) if isinstance(job.get("meta"), dict) else {}
    result = job.get("result", {}) if isinstance(job.get("result"), dict) else {}
    status = str(job.get("status", "unknown") or "unknown").strip().lower()
    started_at = str(job.get("started_at", "") or "")
    finished_at = str(job.get("finished_at", "") or "")
    error_text = str(job.get("error", "") or "")

    def _safe_int(v: Any) -> int:
        try:
            parsed = int(v)
        except Exception:
            parsed = 0
        return max(parsed, 0)

    def _safe_float(v: Any) -> float:
        try:
            parsed = float(v)
        except Exception:
            parsed = 0.0
        return max(parsed, 0.0)

    task_mode = "single_capability"
    strategy = ""
    capability_ids: List[str] = []
    skill_ids: List[str] = []
    total_steps = 1
    success_steps = 0
    failed_steps = 0
    skipped_steps = 0
    retry_count = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_cost = 0.0
    failed_nodes: List[Dict[str, str]] = []
    step_summaries: List[Dict[str, Any]] = []

    if kind == "agent_skill":
        task_mode = "skill_invoke"
        sid = str(result.get("skill_id", "") or "").strip()
        cid = str(result.get("capability_id", "") or "").strip()
        if sid:
            skill_ids.append(sid)
        if cid:
            capability_ids.append(cid)
        attempts = _safe_int(result.get("attempts", 1))
        retry_count = max(attempts - 1, 0)
        usage_tokens = result.get("usage_tokens", {}) if isinstance(result.get("usage_tokens"), dict) else {}
        prompt_tokens += _safe_int(usage_tokens.get("prompt_tokens", 0))
        completion_tokens += _safe_int(usage_tokens.get("completion_tokens", 0))
        estimated = result.get("estimated_cost", {}) if isinstance(result.get("estimated_cost"), dict) else {}
        total_cost += _safe_float(estimated.get("total_cost_usd", 0.0))
        step_summaries.append({
            "step_id": str(result.get("invoke_id", "") or "invoke"),
            "index": 1,
            "skill_id": sid,
            "capability_id": cid,
            "status": status if status in {"done", "error", "cancelled"} else "unknown",
            "error": error_text or str(result.get("error", "") or ""),
            "continue_on_error": False,
            "duration_seconds": round(_safe_float(result.get("duration_seconds", 0.0)), 4),
            "prompt_tokens": _safe_int(usage_tokens.get("prompt_tokens", 0)),
            "completion_tokens": _safe_int(usage_tokens.get("completion_tokens", 0)),
            "estimated_cost_usd": round(_safe_float(estimated.get("total_cost_usd", 0.0)), 8),
            "condition": {},
        })
        if status == "done":
            success_steps = 1
        elif status == "cancelled":
            skipped_steps = 1
        else:
            failed_steps = 1
            failed_nodes.append({
                "skill_id": sid,
                "capability_id": cid,
                "error": error_text or str(result.get("error", "") or ""),
            })
    elif str(result.get("mode", "") or "").strip().lower() == "skill_sequence":
        task_mode = "skill_sequence"
        strategy = str(result.get("strategy", "") or "").strip().lower()
        total_steps = _safe_int(result.get("total_steps", 0))
        success_steps = _safe_int(result.get("success_steps", 0))
        failed_steps = _safe_int(result.get("failed_steps", 0))
        skipped_steps = _safe_int(result.get("skipped_steps", 0))
        steps = result.get("steps", []) if isinstance(result.get("steps"), list) else []
        if total_steps <= 0:
            total_steps = len(steps)
        for item in steps:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("skill_id", "") or "").strip()
            cid = str(item.get("capability_id", "") or "").strip()
            step_status = str(item.get("status", "") or "").strip().lower() or "unknown"
            if sid and sid not in skill_ids:
                skill_ids.append(sid)
            if cid and cid not in capability_ids:
                capability_ids.append(cid)
            retry_count += max(_safe_int(item.get("attempts", 1)) - 1, 0)
            usage_tokens = item.get("usage_tokens", {}) if isinstance(item.get("usage_tokens"), dict) else {}
            prompt_tokens += _safe_int(usage_tokens.get("prompt_tokens", 0))
            completion_tokens += _safe_int(usage_tokens.get("completion_tokens", 0))
            estimated = item.get("estimated_cost", {}) if isinstance(item.get("estimated_cost"), dict) else {}
            total_cost += _safe_float(estimated.get("total_cost_usd", 0.0))
            step_summaries.append({
                "step_id": str(item.get("step_id", "") or ""),
                "index": _safe_int(item.get("index", len(step_summaries) + 1)),
                "skill_id": sid,
                "capability_id": cid,
                "status": step_status,
                "error": str(item.get("error", "") or ""),
                "continue_on_error": bool(item.get("continue_on_error", False)),
                "duration_seconds": round(_safe_float(item.get("duration_seconds", 0.0)), 4),
                "prompt_tokens": _safe_int(usage_tokens.get("prompt_tokens", 0)),
                "completion_tokens": _safe_int(usage_tokens.get("completion_tokens", 0)),
                "estimated_cost_usd": round(_safe_float(estimated.get("total_cost_usd", 0.0)), 8),
                "condition": deepcopy(item.get("condition", {})) if isinstance(item.get("condition"), dict) else {},
            })
            if step_status == "error":
                failed_nodes.append({
                    "skill_id": sid,
                    "capability_id": cid,
                    "error": str(item.get("error", "") or ""),
                })
    else:
        task_mode = "single_capability"
        cid = str(result.get("capability_id", "") or "").strip()
        if cid:
            capability_ids.append(cid)
        step_summaries.append({
            "step_id": str(result.get("task_id", "") or "task"),
            "index": 1,
            "skill_id": "",
            "capability_id": cid,
            "status": status if status in {"done", "error", "cancelled"} else "unknown",
            "error": error_text or str(result.get("error", "") or ""),
            "continue_on_error": False,
            "duration_seconds": round(_safe_float(result.get("duration_seconds", 0.0)), 4),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost_usd": 0.0,
            "condition": {},
        })
        total_steps = 1
        if status == "done":
            success_steps = 1
        elif status == "cancelled":
            skipped_steps = 1
        else:
            failed_steps = 1
            failed_nodes.append({
                "skill_id": "",
                "capability_id": cid,
                "error": error_text or str(result.get("error", "") or ""),
            })

    from modules.app_api.services.workflow_runner import _extract_template_ids_from_value, _extract_agent_replay_spec
    template_hits = _extract_template_ids_from_value({
        "meta": meta,
        "result": result,
    })
    replay_spec = _extract_agent_replay_spec(meta.get("replay", {}))
    duration_seconds = _safe_float(result.get("duration_seconds", 0.0))
    if duration_seconds <= 0.0:
        duration_seconds = _duration_from_iso_range(started_at, finished_at)

    return {
        "job_id": str(job_id or ""),
        "kind": kind,
        "status": status,
        "task_mode": task_mode,
        "strategy": strategy,
        "actor_type": str(meta.get("actor_type", "") or ""),
        "actor_id": str(meta.get("actor_id", "") or ""),
        "trace_id": str(meta.get("trace_id", "") or ""),
        "capability_ids": capability_ids,
        "skill_ids": skill_ids,
        "total_steps": max(total_steps, 0),
        "success_steps": max(success_steps, 0),
        "failed_steps": max(failed_steps, 0),
        "skipped_steps": max(skipped_steps, 0),
        "retry_count": max(retry_count, 0),
        "prompt_tokens": max(prompt_tokens, 0),
        "completion_tokens": max(completion_tokens, 0),
        "total_tokens": max(prompt_tokens + completion_tokens, 0),
        "estimated_cost_usd": round(max(total_cost, 0.0), 8),
        "duration_seconds": round(max(duration_seconds, 0.0), 4),
        "template_hits": template_hits,
        "template_hit_count": len(template_hits),
        "replay_supported": bool(replay_spec),
        "replay": replay_spec,
        "failed_nodes": failed_nodes,
        "step_summaries": step_summaries,
        "error": error_text,
        "started_at": started_at,
        "finished_at": finished_at,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
    }


def _record_agent_task_history_from_job(job_id: str):
    if _get_project_dir() is None:
        return
    job = _jobs.get(job_id)
    if not isinstance(job, dict):
        return
    record = _build_agent_task_history_record(job_id, job)
    if not isinstance(record, dict):
        return
    from modules.app_api.services.workflow_runner import _read_agent_task_history, _save_agent_task_history
    with _agent_history_lock:
        history = _read_agent_task_history()
        history.append(record)
        _save_agent_task_history(history)


def _parse_agent_history_filter_tokens(raw: Any) -> List[str]:
    text = str(raw or "").replace("\uff0c", ",")
    out: List[str] = []
    seen = set()
    for token in text.split(","):
        item = str(token or "").strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _agent_history_anchor_time(item: Dict[str, Any]) -> Optional[datetime]:
    if not isinstance(item, dict):
        return None
    for key in ("finished_at", "started_at", "recorded_at"):
        dt = _parse_iso_datetime(item.get(key))
        if dt is not None:
            return dt
    return None


def _filter_agent_task_history(
    history: List[Dict[str, Any]],
    *,
    actor_id: str = "",
    statuses: Optional[List[str]] = None,
    task_modes: Optional[List[str]] = None,
    kinds: Optional[List[str]] = None,
    capability_id: str = "",
    skill_id: str = "",
    trace_id: str = "",
    replay_supported: Optional[bool] = None,
    since: Any = None,
    until: Any = None,
) -> List[Dict[str, Any]]:
    items = [x for x in history if isinstance(x, dict)]
    status_set = {str(x or "").strip().lower() for x in (statuses or []) if str(x or "").strip()}
    mode_set = {str(x or "").strip().lower() for x in (task_modes or []) if str(x or "").strip()}
    kind_set = {str(x or "").strip().lower() for x in (kinds or []) if str(x or "").strip()}
    actor_text = str(actor_id or "").strip()
    capability_text = str(capability_id or "").strip().lower()
    skill_text = str(skill_id or "").strip().lower()
    trace_text = str(trace_id or "").strip()
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)

    out: List[Dict[str, Any]] = []
    for item in items:
        if actor_text and str(item.get("actor_id", "") or "").strip() != actor_text:
            continue
        if status_set:
            status_val = str(item.get("status", "") or "").strip().lower()
            if status_val not in status_set:
                continue
        if mode_set:
            mode_val = str(item.get("task_mode", "") or "").strip().lower()
            if mode_val not in mode_set:
                continue
        if kind_set:
            kind_val = str(item.get("kind", "") or "").strip().lower()
            if kind_val not in kind_set:
                continue
        if capability_text:
            capability_ids = item.get("capability_ids", [])
            capability_values = capability_ids if isinstance(capability_ids, list) else []
            capability_ok = any(str(x or "").strip().lower() == capability_text for x in capability_values)
            if not capability_ok:
                continue
        if skill_text:
            skill_ids = item.get("skill_ids", [])
            skill_values = skill_ids if isinstance(skill_ids, list) else []
            skill_ok = any(str(x or "").strip().lower() == skill_text for x in skill_values)
            if not skill_ok:
                continue
        if trace_text and str(item.get("trace_id", "") or "").strip() != trace_text:
            continue
        if replay_supported is not None and bool(item.get("replay_supported", False)) != bool(replay_supported):
            continue

        item_time = _agent_history_anchor_time(item)
        if since_dt is not None and (item_time is None or item_time < since_dt):
            continue
        if until_dt is not None and (item_time is None or item_time > until_dt):
            continue
        out.append(item)
    return out


def _build_agent_task_export_snapshot(
    job_id: str,
    *,
    include_logs: bool = True,
    include_result: bool = True,
) -> Optional[Dict[str, Any]]:
    jid = str(job_id or "").strip()
    if not jid:
        return None

    live_job = _jobs.get(jid)
    if isinstance(live_job, dict) and live_job.get("kind") in {"agent_task", "agent_skill"}:
        summary = _build_agent_task_history_record(jid, live_job)
        payload: Dict[str, Any] = {
            "job_id": jid,
            "source": "memory",
            "summary": summary if isinstance(summary, dict) else {},
            "status": str(live_job.get("status", "unknown") or "unknown"),
            "kind": str(live_job.get("kind", "") or ""),
            "started_at": live_job.get("started_at"),
            "finished_at": live_job.get("finished_at"),
            "error": live_job.get("error"),
            "meta": deepcopy(live_job.get("meta", {})) if isinstance(live_job.get("meta"), dict) else {},
        }
        if include_logs:
            payload["log"] = list(live_job.get("log", []))
        if include_result:
            payload["result"] = deepcopy(live_job.get("result", {})) if isinstance(live_job.get("result"), dict) else {}
        return payload

    from modules.app_api.services.workflow_runner import _find_agent_task_history_record
    history_item = _find_agent_task_history_record(jid)
    if not isinstance(history_item, dict):
        return None
    return {
        "job_id": jid,
        "source": "history",
        "summary": history_item,
        "status": str(history_item.get("status", "unknown") or "unknown"),
        "kind": str(history_item.get("kind", "") or ""),
        "started_at": history_item.get("started_at"),
        "finished_at": history_item.get("finished_at"),
        "error": history_item.get("error", ""),
    }


def _build_chain_view_from_history_item(history_item: Dict[str, Any]) -> Dict[str, Any]:
    item = history_item if isinstance(history_item, dict) else {}
    mode = str(item.get("task_mode", "") or "single_capability").strip().lower() or "single_capability"
    strategy = str(item.get("strategy", "") or "").strip().lower()
    status = str(item.get("status", "") or "unknown").strip().lower()
    if status == "done":
        overall_status = "done"
    elif status == "error":
        overall_status = "error"
    elif status == "cancelled":
        overall_status = "cancelled"
    else:
        overall_status = "unknown"

    step_summaries = item.get("step_summaries", [])
    steps = step_summaries if isinstance(step_summaries, list) else []
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    known_step_ids = set()

    if mode == "skill_sequence" and steps:
        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("step_id", "") or f"step_{idx:02d}")
            known_step_ids.add(step_id)
            nodes.append({
                "node_id": step_id,
                "node_type": "skill",
                "index": max(int(step.get("index", idx) or idx), 1),
                "status": str(step.get("status", "unknown") or "unknown").strip().lower() or "unknown",
                "skill_id": str(step.get("skill_id", "") or ""),
                "capability_id": str(step.get("capability_id", "") or ""),
                "continue_on_error": bool(step.get("continue_on_error", False)),
                "duration_seconds": round(max(float(step.get("duration_seconds", 0.0) or 0.0), 0.0), 4),
                "prompt_tokens": max(int(step.get("prompt_tokens", 0) or 0), 0),
                "completion_tokens": max(int(step.get("completion_tokens", 0) or 0), 0),
                "estimated_cost_usd": round(max(float(step.get("estimated_cost_usd", 0.0) or 0.0), 0.0), 8),
                "error": str(step.get("error", "") or ""),
                "condition": deepcopy(step.get("condition", {})) if isinstance(step.get("condition"), dict) else {},
            })

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
                edges.append({"from": dep_id, "to": node_id, "type": "condition_depends_on"})
                deps_added = True
            if not deps_added and strategy in {"sequential", "conditional"} and idx > 0:
                prev_node_id = str(nodes[idx - 1].get("node_id", "") or "")
                if prev_node_id:
                    edges.append({"from": prev_node_id, "to": node_id, "type": "sequence"})
    elif mode == "skill_sequence":
        total_steps = max(int(item.get("total_steps", 0) or 0), 0)
        success_steps = max(int(item.get("success_steps", 0) or 0), 0)
        failed_steps = max(int(item.get("failed_steps", 0) or 0), 0)
        skipped_steps = max(int(item.get("skipped_steps", 0) or 0), 0)
        if total_steps <= 0:
            total_steps = max(success_steps + failed_steps + skipped_steps, 1)
        statuses = (["done"] * success_steps) + (["error"] * failed_steps) + (["skipped"] * skipped_steps)
        if len(statuses) < total_steps:
            statuses.extend(["unknown"] * (total_steps - len(statuses)))
        capability_first = str((item.get("capability_ids", [""])[0] if isinstance(item.get("capability_ids"), list) and item.get("capability_ids") else "") or "")
        skill_first = str((item.get("skill_ids", [""])[0] if isinstance(item.get("skill_ids"), list) and item.get("skill_ids") else "") or "")
        for idx in range(total_steps):
            nodes.append({
                "node_id": f"step_{idx + 1:02d}",
                "node_type": "skill",
                "index": idx + 1,
                "status": statuses[idx],
                "skill_id": skill_first,
                "capability_id": capability_first,
                "continue_on_error": False,
                "duration_seconds": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "error": "",
                "condition": {},
            })
        if total_steps > 1 and strategy in {"", "sequential", "conditional"}:
            for idx in range(1, total_steps):
                edges.append({"from": f"step_{idx:02d}", "to": f"step_{idx + 1:02d}", "type": "sequence"})
    elif mode == "skill_invoke":
        nodes.append({
            "node_id": str(item.get("job_id", "") or "invoke"),
            "node_type": "skill",
            "status": status,
            "skill_id": str((item.get("skill_ids", [""])[0] if isinstance(item.get("skill_ids"), list) and item.get("skill_ids") else "") or ""),
            "capability_id": str((item.get("capability_ids", [""])[0] if isinstance(item.get("capability_ids"), list) and item.get("capability_ids") else "") or ""),
            "duration_seconds": round(max(float(item.get("duration_seconds", 0.0) or 0.0), 0.0), 4),
            "prompt_tokens": max(int(item.get("prompt_tokens", 0) or 0), 0),
            "completion_tokens": max(int(item.get("completion_tokens", 0) or 0), 0),
            "estimated_cost_usd": round(max(float(item.get("estimated_cost_usd", 0.0) or 0.0), 0.0), 8),
            "error": str(item.get("error", "") or ""),
        })
    else:
        nodes.append({
            "node_id": str(item.get("job_id", "") or "task"),
            "node_type": "capability",
            "status": status,
            "skill_id": "",
            "capability_id": str((item.get("capability_ids", [""])[0] if isinstance(item.get("capability_ids"), list) and item.get("capability_ids") else "") or ""),
            "duration_seconds": round(max(float(item.get("duration_seconds", 0.0) or 0.0), 0.0), 4),
            "prompt_tokens": max(int(item.get("prompt_tokens", 0) or 0), 0),
            "completion_tokens": max(int(item.get("completion_tokens", 0) or 0), 0),
            "estimated_cost_usd": round(max(float(item.get("estimated_cost_usd", 0.0) or 0.0), 0.0), 8),
            "error": str(item.get("error", "") or ""),
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

    total_prompt = sum(max(int(n.get("prompt_tokens", 0) or 0), 0) for n in nodes)
    total_completion = sum(max(int(n.get("completion_tokens", 0) or 0), 0) for n in nodes)
    total_cost = sum(max(float(n.get("estimated_cost_usd", 0.0) or 0.0), 0.0) for n in nodes)

    item_prompt = max(int(item.get("prompt_tokens", 0) or 0), 0)
    item_completion = max(int(item.get("completion_tokens", 0) or 0), 0)
    item_cost = max(float(item.get("estimated_cost_usd", 0.0) or 0.0), 0.0)
    if total_prompt <= 0 and item_prompt > 0:
        total_prompt = item_prompt
    if total_completion <= 0 and item_completion > 0:
        total_completion = item_completion
    if total_cost <= 0.0 and item_cost > 0.0:
        total_cost = item_cost

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
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "estimated_cost_usd": round(total_cost, 8),
        },
        "nodes": nodes,
        "edges": edges,
    }


def _build_agent_observability_summary(history: List[Dict[str, Any]], *, top_n: int = 5) -> Dict[str, Any]:
    items = [x for x in history if isinstance(x, dict)]
    total = len(items)
    if total <= 0:
        return {
            "total_tasks": 0,
            "status_counts": {"done": 0, "error": 0, "cancelled": 0, "other": 0},
            "rates": {
                "success_rate": 0.0,
                "error_rate": 0.0,
                "cancel_rate": 0.0,
                "retry_rate": 0.0,
                "template_hit_rate": 0.0,
            },
            "averages": {
                "duration_seconds": 0.0,
                "retry_count": 0.0,
                "total_tokens": 0.0,
                "estimated_cost_usd": 0.0,
            },
            "mode_counts": {},
            "top_templates": [],
            "failed_top": [],
        }

    status_counts = {"done": 0, "error": 0, "cancelled": 0, "other": 0}
    mode_counts: Dict[str, int] = {}
    retry_tasks = 0
    template_hit_tasks = 0
    total_retry = 0
    total_duration = 0.0
    total_tokens = 0
    total_cost = 0.0
    template_counter: Dict[str, int] = {}
    failed_counter: Dict[str, Dict[str, Any]] = {}

    for item in items:
        status = str(item.get("status", "") or "").strip().lower()
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts["other"] += 1

        mode = str(item.get("task_mode", "") or "unknown").strip().lower() or "unknown"
        mode_counts[mode] = int(mode_counts.get(mode, 0)) + 1

        retry_count = max(int(item.get("retry_count", 0) or 0), 0)
        if retry_count > 0:
            retry_tasks += 1
        total_retry += retry_count

        total_duration += max(float(item.get("duration_seconds", 0.0) or 0.0), 0.0)
        total_tokens += max(int(item.get("total_tokens", 0) or 0), 0)
        total_cost += max(float(item.get("estimated_cost_usd", 0.0) or 0.0), 0.0)

        template_hits = item.get("template_hits", [])
        if isinstance(template_hits, list) and template_hits:
            template_hit_tasks += 1
            for tid in template_hits:
                k = str(tid or "").strip()
                if not k:
                    continue
                template_counter[k] = int(template_counter.get(k, 0)) + 1

        failed_nodes = item.get("failed_nodes", [])
        if isinstance(failed_nodes, list):
            for node in failed_nodes:
                if not isinstance(node, dict):
                    continue
                sid = str(node.get("skill_id", "") or "").strip()
                cid = str(node.get("capability_id", "") or "").strip()
                err = str(node.get("error", "") or "").strip()
                label = sid or cid or "unknown"
                if err:
                    label = f"{label}|{err[:80]}"
                bucket = failed_counter.get(label)
                if not isinstance(bucket, dict):
                    bucket = {
                        "skill_id": sid,
                        "capability_id": cid,
                        "error": err[:120],
                        "count": 0,
                    }
                    failed_counter[label] = bucket
                bucket["count"] = int(bucket.get("count", 0)) + 1

    top_templates = [
        {"template_id": k, "count": v}
        for k, v in sorted(template_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:max(int(top_n), 1)]
    ]
    failed_top = sorted(
        failed_counter.values(),
        key=lambda x: (-int(x.get("count", 0) or 0), str(x.get("skill_id", "") or ""), str(x.get("capability_id", "") or "")),
    )[:max(int(top_n), 1)]

    return {
        "total_tasks": total,
        "status_counts": status_counts,
        "rates": {
            "success_rate": round(float(status_counts["done"]) / float(total), 4),
            "error_rate": round(float(status_counts["error"]) / float(total), 4),
            "cancel_rate": round(float(status_counts["cancelled"]) / float(total), 4),
            "retry_rate": round(float(retry_tasks) / float(total), 4),
            "template_hit_rate": round(float(template_hit_tasks) / float(total), 4),
        },
        "averages": {
            "duration_seconds": round(float(total_duration) / float(total), 4),
            "retry_count": round(float(total_retry) / float(total), 4),
            "total_tokens": round(float(total_tokens) / float(total), 2),
            "estimated_cost_usd": round(float(total_cost) / float(total), 8),
        },
        "totals": {
            "duration_seconds": round(total_duration, 4),
            "retry_count": int(total_retry),
            "total_tokens": int(total_tokens),
            "estimated_cost_usd": round(total_cost, 8),
        },
        "mode_counts": mode_counts,
        "top_templates": top_templates,
        "failed_top": failed_top,
    }


def _read_script_json() -> Dict:
    from modules.app_api.server import _project_data_path
    if _get_project_dir() is None:
        return {}
    for name in ("script_matched.json", "script_draft.json"):
        p = _project_data_path(name)
        if p is not None and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}
