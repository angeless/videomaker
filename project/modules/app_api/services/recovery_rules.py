"""Unified recovery judgment for jobs and batch tasks.

Pure functions — no side effects, no Flask dependency, no state mutation.
Used by job_routes.py and potentially by agent/frontend to determine
whether a task can be retried and what the next action should be.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ── Status sets ───────────────────────────────────────────────────────

_TERMINAL = frozenset({"done", "error", "cancelled", "interrupted", "partial"})
_RETRYABLE = frozenset({"error", "cancelled", "interrupted"})
_ACTIVE = frozenset({"running", "queued"})


def is_terminal_status(status: str) -> bool:
    """True for statuses that represent a finished (non-active) state."""
    return str(status or "").lower() in _TERMINAL


def is_retryable_status(status: str) -> bool:
    """True for statuses that allow retry."""
    return str(status or "").lower() in _RETRYABLE


# ── Single-job recovery assessment ────────────────────────────────────

def assess_recovery(
    job: Dict[str, Any],
    *,
    retry_hint_map: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, Any]:
    """Assess recovery options for a single job.

    Returns a dict with:
      current_status  — normalised status string
      can_retry       — bool
      retry_scope     — "single" | "batch" | "none"
      reason          — why retry is / isn't possible (Chinese)
      next_action     — what the caller should do next (Chinese)
      blocked_reason  — explicit block reason when can_retry=False, else None
      duplicate_risk  — whether re-execution may cause duplicates
      retry_hint      — {kind, endpoint} or None
    """
    if not isinstance(job, dict):
        return _blocked("unknown", "任务记录无效", "检查任务 ID 是否正确")

    status = str(job.get("status", "") or "").lower()
    kind = str(job.get("kind", "") or "")
    hint = _build_retry_hint(kind, job, retry_hint_map)

    # ── active states: blocked ──
    if status == "running":
        cancel_req = bool(job.get("cancel_requested", False))
        if cancel_req:
            return _blocked(
                status,
                "任务正在停止中（已收到取消请求）",
                "等待取消完成后重新发起",
            )
        return _blocked(status, "任务仍在执行中", "等待完成或先取消再重试")

    if status == "queued":
        return _blocked(status, "任务排队中，尚未执行", "等待执行或先取消再重试")

    # ── terminal success: no retry ──
    if status == "done":
        return _blocked(status, "任务已成功完成", "无需操作")

    # ── retryable terminal states ──
    if status == "error":
        return _retryable(
            status, "single",
            "任务执行失败，可重新发起",
            "通过对应能力端点重新提交",
            hint=hint,
            duplicate_risk=_has_publish_risk(kind),
        )

    if status == "cancelled":
        return _retryable(
            status, "single",
            "任务已取消，可重新发起",
            "通过对应能力端点重新提交",
            hint=hint,
            duplicate_risk=False,
        )

    if status == "interrupted":
        return _retryable(
            status, "single",
            "任务因应用重启中断，可重新发起",
            "通过对应能力端点重新提交",
            hint=hint,
            duplicate_risk=_has_publish_risk(kind),
        )

    if status == "partial":
        return _retryable(
            status, "batch",
            "批次部分成功，存在可恢复的失败项",
            "通过对应能力的 rerun 端点重试失败项",
            hint=hint,
            duplicate_risk=True,
        )

    # ── unknown status: conservative block ──
    return _blocked(status or "unknown", f"未知状态: {status}", "请检查任务详情")


# ── Batch recovery assessment ─────────────────────────────────────────

def assess_batch_recovery(
    items: List[Dict[str, Any]],
    *,
    id_field: str = "job_id",
    retry_hint_map: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, Any]:
    """Assess recovery options for a batch of items.

    Each item must have at least ``status`` and the field named by *id_field*.

    Returns:
      total, retryable, skippable, blocked counts and id lists,
      plus a human-readable summary.
    """
    total = len(items)
    retryable_ids: List[str] = []
    skipped_ids: List[str] = []
    blocked_ids: List[str] = []
    items_detail: List[Dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get(id_field, "") or "")
        status = str(item.get("status", "") or "").lower()

        if status == "done":
            skipped_ids.append(item_id)
            items_detail.append({
                id_field: item_id,
                "status": status,
                "action": "skipped",
                "reason": "已完成",
            })
        elif is_retryable_status(status) or status == "partial":
            retryable_ids.append(item_id)
            rec = assess_recovery(item, retry_hint_map=retry_hint_map)
            items_detail.append({
                id_field: item_id,
                "status": status,
                "action": "retryable",
                "reason": rec["reason"],
                "retry_hint": rec.get("retry_hint"),
            })
        elif status in _ACTIVE:
            blocked_ids.append(item_id)
            items_detail.append({
                id_field: item_id,
                "status": status,
                "action": "blocked",
                "reason": "排队中" if status == "queued" else "执行中",
            })
        else:
            blocked_ids.append(item_id)
            items_detail.append({
                id_field: item_id,
                "status": status,
                "action": "blocked",
                "reason": f"未知状态: {status}",
            })

    can_batch = len(retryable_ids) > 0
    parts = []
    if skipped_ids:
        parts.append(f"{len(skipped_ids)} 项已完成（跳过）")
    if retryable_ids:
        parts.append(f"{len(retryable_ids)} 项可重试")
    if blocked_ids:
        parts.append(f"{len(blocked_ids)} 项受阻")
    summary = "，".join(parts) if parts else "无可处理项"

    return {
        "total": total,
        "retryable": len(retryable_ids),
        "skippable": len(skipped_ids),
        "blocked": len(blocked_ids),
        "retryable_ids": retryable_ids,
        "skipped_ids": skipped_ids,
        "blocked_ids": blocked_ids,
        "can_batch_retry": can_batch,
        "reason": summary,
        "summary": summary,
        "items": items_detail,
    }


# ── Internal helpers ──────────────────────────────────────────────────

def _blocked(status: str, reason: str, next_action: str) -> Dict[str, Any]:
    return {
        "current_status": status,
        "can_retry": False,
        "retry_scope": "none",
        "reason": reason,
        "next_action": next_action,
        "blocked_reason": reason,
        "duplicate_risk": False,
        "retry_hint": None,
    }


def _retryable(
    status: str,
    scope: str,
    reason: str,
    next_action: str,
    *,
    hint: Optional[Dict[str, Any]] = None,
    duplicate_risk: bool = False,
) -> Dict[str, Any]:
    if hint is None:
        next_action = "需要手工使用原参数重新提交"
    return {
        "current_status": status,
        "can_retry": True,
        "retry_scope": scope,
        "reason": reason,
        "next_action": next_action,
        "blocked_reason": None,
        "duplicate_risk": duplicate_risk,
        "retry_hint": hint,
    }


def _build_retry_hint(
    kind: str,
    job: Dict[str, Any],
    hint_map: Optional[Dict[str, Optional[str]]],
) -> Optional[Dict[str, Any]]:
    """Build retry_hint from kind → endpoint mapping."""
    if not hint_map or not kind:
        return None
    endpoint = hint_map.get(kind)
    if endpoint is None:
        return None
    return {"kind": kind, "endpoint": endpoint}


def _has_publish_risk(kind: str) -> bool:
    """Kinds that involve external publishing have duplicate risk."""
    return kind in {"social_export", "custom_workflow"}
