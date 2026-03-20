#!/usr/bin/env python3
"""Job status/cancel routes extracted from server.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_str_param


def create_job_blueprint(
    *,
    jobs_getter: Callable[[], Dict[str, Dict[str, Any]]],
    load_job_from_store: Callable[[str], Dict[str, Any] | None],
    heavy_queue_lock_getter: Callable[[], Any],
    heavy_job_queue_getter: Callable[[], Any],
    dispatch_heavy_queue_locked: Callable[[], None],
    persist_job_snapshot: Callable[[str, str], None],
    system_load_snapshot_getter: Callable[[], Dict[str, Any]],
    state_dict_getter: Callable[[], Dict[str, Any]],
    estimate_job_eta: Callable[[Dict[str, Any]], Dict[str, Any]],
    retry_hint_map: Dict[str, str | None] | None = None,
) -> Blueprint:
    bp = Blueprint("job_api", __name__)

    def _jobs() -> Dict[str, Dict[str, Any]]:
        src = jobs_getter()
        return src if isinstance(src, dict) else {}

    @bp.route("/api/job/<job_id>", methods=["GET"])
    def api_job(job_id: str):
        jobs = _jobs()
        job = jobs.get(job_id)
        if job is None:
            job = load_job_from_store(job_id)
        if job is None:
            return jsonify({"error": "job 不存在"}), 404
        queue_position = 0
        if job.get("status") == "queued":
            with heavy_queue_lock_getter():
                pos = 1
                for jid in list(heavy_job_queue_getter()):
                    if jid == job_id:
                        queue_position = pos
                        break
                    pos += 1
            job["queue_position"] = queue_position
        status_text = parse_str_param(job.get("status", "")).lower()
        if status_text in {"done", "error", "cancelled", "interrupted"}:
            persist_job_snapshot(job_id, "")
        eta = estimate_job_eta(job) if isinstance(job, dict) else {}
        if not isinstance(eta, dict):
            eta = {}
        from modules.app_api.services.recovery_rules import assess_recovery
        recovery = assess_recovery(job, retry_hint_map=retry_hint_map)
        return jsonify(
            {
                "status": job["status"],
                "kind": job.get("kind", "generic"),
                "log": job["log"][-50:],
                "progress": job.get("progress", 0),
                "queued_at": job.get("queued_at"),
                "queue_position": int(job.get("queue_position", queue_position) or 0),
                "cancel_requested": bool(job.get("cancel_requested", False)),
                "error": job.get("error"),
                "result": job.get("result"),
                "started_at": job.get("started_at"),
                "finished_at": job.get("finished_at"),
                "eta": eta,
                "system": system_load_snapshot_getter(),
                "state": state_dict_getter(),
                "recovery": recovery,
            }
        )

    @bp.route("/api/job/<job_id>/cancel", methods=["POST"])
    def api_job_cancel(job_id: str):
        jobs = _jobs()
        job = jobs.get(job_id)
        if job is None:
            job = load_job_from_store(job_id)
        if job is None:
            return jsonify({"error": "job 不存在"}), 404
        status = str(job.get("status", "") or "")
        if status == "queued":
            removed = False
            with heavy_queue_lock_getter():
                queue_obj = heavy_job_queue_getter()
                new_queue = []
                for jid in list(queue_obj):
                    if jid == job_id:
                        removed = True
                        continue
                    new_queue.append(jid)
                queue_obj.clear()
                for jid in new_queue:
                    queue_obj.append(jid)
                dispatch_heavy_queue_locked()
            if removed:
                job["status"] = "cancelled"
                job["cancel_requested"] = True
                job["cancel_requested_at"] = datetime.now().isoformat(timespec="seconds")
                job["finished_at"] = datetime.now().isoformat(timespec="seconds")
                job["error"] = "任务已取消"
                job["log"].append("[系统] 排队中的任务已取消")
                job.pop("_fn", None)
                job.pop("_args", None)
                job.pop("_kwargs", None)
                persist_job_snapshot(job_id, "job_cancelled")
                from modules.app_api.services.audit_log import audit as _audit
                _audit("cancel", "job", job_id, actor=f"local:{request.remote_addr}", detail={"previous_status": "queued"})
                return jsonify({"ok": True, "status": job.get("status"), "cancel_requested": True})
        if status != "running":
            return jsonify({"error": "任务不在运行中，无法取消", "status": job.get("status")}), 409
        job["cancel_requested"] = True
        job["cancel_requested_at"] = datetime.now().isoformat(timespec="seconds")
        job["log"].append("[系统] 收到取消请求，正在安全停止…")
        persist_job_snapshot(job_id, "job_cancel_requested")
        from modules.app_api.services.audit_log import audit as _audit
        _audit("cancel", "job", job_id, actor=f"local:{request.remote_addr}", detail={"previous_status": status})
        return jsonify({"ok": True, "status": job.get("status"), "cancel_requested": True})

    # ── Single-job recovery (advice only) ──

    @bp.route("/api/job/<job_id>/retry", methods=["POST"])
    def api_job_retry(job_id: str):
        from modules.app_api.services.recovery_rules import assess_recovery
        jobs = _jobs()
        job = jobs.get(job_id)
        if job is None:
            job = load_job_from_store(job_id)
        if job is None:
            return jsonify({"error": "job 不存在"}), 404
        recovery = assess_recovery(job, retry_hint_map=retry_hint_map)
        actor = f"local:{request.remote_addr}"
        if not recovery["can_retry"]:
            from modules.app_api.services.audit_log import audit as _audit
            _audit("retry_blocked", "job", job_id, actor=actor, status="blocked", detail={"current_status": recovery["current_status"], "reason": recovery["reason"]})
            return jsonify({
                "error": "任务不可重试",
                "action": "advice_only",
                "retry_submitted": False,
                "recovery": recovery,
            }), 409
        from modules.app_api.services.audit_log import audit as _audit
        _audit("retry", "job", job_id, actor=actor, detail={"source_status": recovery["current_status"], "kind": job.get("kind", "")})
        return jsonify({
            "ok": True,
            "action": "advice_only",
            "retry_submitted": False,
            "source_job_id": job_id,
            "recovery": recovery,
        })

    # ── Batch recovery (advice only) ──

    @bp.route("/api/jobs/batch-retry", methods=["POST"])
    def api_jobs_batch_retry():
        from modules.app_api.services.recovery_rules import assess_batch_recovery
        payload = request.json or {}
        job_ids = payload.get("job_ids", [])
        if not isinstance(job_ids, list) or not job_ids:
            return jsonify({"error": "job_ids 不能为空"}), 400
        job_ids = [str(jid) for jid in job_ids[:200]]
        jobs = _jobs()
        items = []
        for jid in job_ids:
            job = jobs.get(jid)
            if job is None:
                job = load_job_from_store(jid)
            if job is None:
                items.append({"job_id": jid, "status": "not_found"})
                continue
            items.append({
                "job_id": jid,
                "status": str(job.get("status", "") or ""),
                "kind": str(job.get("kind", "") or ""),
            })
        result = assess_batch_recovery(items, id_field="job_id", retry_hint_map=retry_hint_map)
        actor = f"local:{request.remote_addr}"
        from modules.app_api.services.audit_log import audit as _audit
        _audit("batch_retry", "job", None, actor=actor, detail={
            "total": result["total"],
            "retryable": result["retryable"],
            "skippable": result["skippable"],
            "blocked": result["blocked"],
        })
        return jsonify({
            "ok": True,
            "action": "advice_only",
            "retry_submitted": False,
            "summary": {
                "total": result["total"],
                "retryable": result["retryable"],
                "skipped": result["skippable"],
                "blocked": result["blocked"],
            },
            "reason": result["reason"],
            "items": result["items"],
        })

    # ── Interrupted jobs listing + batch ignore ──

    @bp.route("/api/job/interrupted", methods=["GET"])
    def api_job_interrupted():
        """List all jobs with status 'interrupted'."""
        jobs = _jobs()
        interrupted = []
        for jid, job in jobs.items():
            if str(job.get("status", "")).lower() == "interrupted":
                interrupted.append({
                    "job_id": jid,
                    "kind": job.get("kind", "generic"),
                    "created_at": job.get("queued_at", job.get("created_at", "")),
                    "error": job.get("error", ""),
                    "progress": job.get("progress", 0),
                })
        # Also check persisted store
        try:
            store_jobs = load_job_from_store("__list__")
        except Exception:
            store_jobs = None
        if store_jobs is None:
            # Fallback: scan store for interrupted jobs not already in memory
            pass
        return jsonify({"ok": True, "jobs": interrupted})

    @bp.route("/api/job/interrupted/retry-all", methods=["POST"])
    def api_job_interrupted_retry_all():
        """Batch retry all interrupted jobs (re-queue them)."""
        payload = request.json or {}
        job_ids = payload.get("job_ids", [])
        if not isinstance(job_ids, list):
            job_ids = []
        jobs = _jobs()
        retried = 0
        failed = 0
        for jid in job_ids:
            jid = str(jid)
            job = jobs.get(jid)
            if job is None:
                job = load_job_from_store(jid)
            if job is None or str(job.get("status", "")).lower() != "interrupted":
                failed += 1
                continue
            # Mark as queued for re-dispatch
            job["status"] = "queued"
            job["error"] = ""
            job["finished_at"] = ""
            job["log"].append("[系统] 中断任务已重新入队")
            persist_job_snapshot(jid, "job_requeued")
            retried += 1
        from modules.app_api.services.audit_log import audit as _audit
        _audit("batch_retry_interrupted", "job", None, actor=f"local:{request.remote_addr}",
               detail={"retried": retried, "failed": failed, "total": len(job_ids)})
        return jsonify({"ok": True, "retried": retried, "failed": failed})

    @bp.route("/api/job/interrupted/ignore", methods=["POST"])
    def api_job_interrupted_ignore():
        """Batch ignore interrupted jobs (mark as cancelled)."""
        payload = request.json or {}
        job_ids = payload.get("job_ids", [])
        if not isinstance(job_ids, list):
            job_ids = []
        jobs = _jobs()
        ignored = 0
        for jid in job_ids:
            jid = str(jid)
            job = jobs.get(jid)
            if job is None:
                job = load_job_from_store(jid)
            if job is None:
                continue
            if str(job.get("status", "")).lower() == "interrupted":
                job["status"] = "cancelled"
                job["error"] = "用户已忽略中断任务"
                job["log"].append("[系统] 中断任务已被用户忽略")
                persist_job_snapshot(jid, "job_ignored")
                ignored += 1
        return jsonify({"ok": True, "ignored": ignored})

    return bp
