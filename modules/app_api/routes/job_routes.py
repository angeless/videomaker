#!/usr/bin/env python3
"""Job status/cancel routes extracted from server.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict

from flask import Blueprint, jsonify


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
        status_text = str(job.get("status", "") or "").strip().lower()
        if status_text in {"done", "error", "cancelled", "interrupted"}:
            persist_job_snapshot(job_id, "")
        eta = estimate_job_eta(job) if isinstance(job, dict) else {}
        if not isinstance(eta, dict):
            eta = {}
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
                return jsonify({"ok": True, "status": job.get("status"), "cancel_requested": True})
        if status != "running":
            return jsonify({"error": "任务不在运行中，无法取消", "status": job.get("status")}), 409
        job["cancel_requested"] = True
        job["cancel_requested_at"] = datetime.now().isoformat(timespec="seconds")
        job["log"].append("[系统] 收到取消请求，正在安全停止…")
        persist_job_snapshot(job_id, "job_cancel_requested")
        return jsonify({"ok": True, "status": job.get("status"), "cancel_requested": True})

    return bp
