#!/usr/bin/env python3
"""Job runtime service for async execution and heavy queue scheduling."""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from collections import deque
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ManagedJobLog(list):
    def __init__(self, values: Optional[List[Any]] = None, on_change: Optional[Callable[[], None]] = None):
        super().__init__([str(item) for item in (values or [])])
        self._on_change = on_change

    def _notify(self):
        if callable(self._on_change):
            try:
                self._on_change()
            except Exception:
                logger.exception("job runtime callback error")

    def append(self, item):
        super().append(str(item))
        self._notify()

    def extend(self, items):
        super().extend([str(item) for item in items])
        self._notify()

    def insert(self, index, item):
        super().insert(index, str(item))
        self._notify()

    def pop(self, index: int = -1):
        out = super().pop(index)
        self._notify()
        return out

    def clear(self):
        super().clear()
        self._notify()

    def remove(self, value):
        super().remove(value)
        self._notify()

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            value = [str(item) for item in value]
        else:
            value = str(value)
        super().__setitem__(key, value)
        self._notify()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._notify()


class ManagedJob(dict):
    def __init__(self, job_id: str, payload: Dict[str, Any], on_change: Optional[Callable[[], None]] = None):
        super().__init__()
        self._job_id = str(job_id or "")
        self._on_change = on_change
        self._suspend = True
        for key, value in (payload or {}).items():
            dict.__setitem__(self, key, self._wrap(key, value))
        self._suspend = False

    def _wrap(self, key: str, value: Any):
        if key == "log":
            if isinstance(value, ManagedJobLog):
                value._on_change = self._notify
                return value
            if isinstance(value, list):
                return ManagedJobLog(value, on_change=self._notify)
            return ManagedJobLog([], on_change=self._notify)
        return value

    def _notify(self):
        if self._suspend:
            return
        if callable(self._on_change):
            try:
                self._on_change()
            except Exception:
                logger.exception("job runtime callback error")

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, self._wrap(str(key), value))
        self._notify()

    def update(self, *args, **kwargs):
        data = dict(*args, **kwargs)
        for key, value in data.items():
            dict.__setitem__(self, key, self._wrap(str(key), value))
        self._notify()

    def pop(self, key, default=None):
        out = dict.pop(self, key, default)
        self._notify()
        return out

    def clear(self):
        dict.clear(self)
        self._notify()


class JobRuntime:
    """In-process async job runtime with heavy-job queue control."""

    def __init__(
        self,
        *,
        heavy_job_kinds: Iterable[str],
        max_running: int,
        cancel_token: str,
        job_cancelled_error_cls: type[BaseException],
        persist_snapshot: Callable[[str, str], None],
        after_job_finished: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.heavy_queue_lock = threading.Lock()
        self.heavy_job_queue: Deque[str] = deque()
        self._heavy_job_kinds = {str(item or "") for item in heavy_job_kinds}
        self._max_running = max(1, int(max_running or 1))
        self._cancel_token = str(cancel_token or "")
        self._job_cancelled_error_cls = job_cancelled_error_cls
        self._persist_snapshot = persist_snapshot
        self._after_job_finished = after_job_finished

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _persist(self, job_id: str, event_type: str = ""):
        try:
            self._persist_snapshot(str(job_id or ""), str(event_type or ""))
        except Exception:
            logger.exception("job runtime callback error")

    def make_managed_job(self, job_id: str, payload: Dict[str, Any]) -> ManagedJob:
        base = dict(payload or {})
        if not isinstance(base.get("meta"), dict):
            base["meta"] = {}
        if not isinstance(base.get("log"), list):
            base["log"] = []
        if "created_at" not in base:
            base["created_at"] = str(base.get("queued_at", "") or self._now_iso())
        base["job_id"] = str(job_id or "").strip()
        return ManagedJob(
            str(job_id or ""),
            base,
            on_change=lambda jid=str(job_id or ""): self._persist(jid),
        )

    def _normalize_restored_job(self, row: Dict[str, Any], *, context: str) -> Dict[str, Any]:
        payload = dict(row or {})
        status = str(payload.get("status", "") or "").strip().lower()
        if status in {"queued", "running"}:
            logs = payload.get("log", []) if isinstance(payload.get("log"), list) else []
            if context == "startup":
                logs.append("[系统] 任务在上次退出时中断，请重新发起该任务。")
                payload["error"] = payload.get("error") or "任务因应用重启中断"
            else:
                logs.append("[系统] 任务在恢复时已中断，请重新发起。")
                payload["error"] = payload.get("error") or "任务因应用重启中断"
            payload["log"] = logs[-500:]
            payload["status"] = "interrupted"
            payload["finished_at"] = str(payload.get("finished_at", "") or self._now_iso())
        return payload

    def restore_jobs(self, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        recovered: Dict[str, Dict[str, Any]] = {}
        for item in rows or []:
            jid = str((item or {}).get("job_id", "") or "").strip()
            if not jid:
                continue
            recovered[jid] = self.make_managed_job(jid, self._normalize_restored_job(item, context="startup"))
        self.jobs.clear()
        self.jobs.update(recovered)
        with self.heavy_queue_lock:
            self.heavy_job_queue.clear()
        for jid in list(recovered.keys()):
            self._persist(jid)
        return recovered

    def adopt_job(self, job_id: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        jid = str(job_id or "").strip()
        if not jid or not isinstance(row, dict):
            return None
        job = self.make_managed_job(jid, self._normalize_restored_job(row, context="load"))
        self.jobs[jid] = job
        self._persist(jid)
        return job

    def is_heavy_kind(self, kind: Any) -> bool:
        return str(kind or "") in self._heavy_job_kinds

    def _count_running_heavy_jobs_locked(self) -> int:
        return sum(
            1
            for job in self.jobs.values()
            if isinstance(job, dict) and job.get("status") == "running" and self.is_heavy_kind(job.get("kind"))
        )

    def _queued_heavy_jobs_locked(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        pos = 1
        for jid in list(self.heavy_job_queue):
            job = self.jobs.get(jid, {})
            if not isinstance(job, dict):
                continue
            if job.get("status") != "queued":
                continue
            rows.append(
                {
                    "job_id": jid,
                    "kind": job.get("kind"),
                    "queued_at": job.get("queued_at"),
                    "queue_position": pos,
                }
            )
            pos += 1
        return rows

    def running_heavy_jobs(self) -> List[Dict[str, Any]]:
        return [
            {"job_id": jid, "kind": job.get("kind"), "started_at": job.get("started_at")}
            for jid, job in self.jobs.items()
            if isinstance(job, dict) and job.get("status") == "running" and self.is_heavy_kind(job.get("kind"))
        ]

    def task_queue_snapshot(self) -> Dict[str, Any]:
        with self.heavy_queue_lock:
            queued = self._queued_heavy_jobs_locked()
            running = self.running_heavy_jobs()
            return {
                "max_running": self._max_running,
                "running_count": len(running),
                "queued_count": len(queued),
                "running": running,
                "queued": queued,
            }

    def _start_job_worker_thread(
        self,
        job_id: str,
        fn: Callable,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ):
        job = self.jobs.get(job_id)
        if not isinstance(job, dict):
            return
        kind = str(job.get("kind", "generic") or "generic")
        job["status"] = "running"
        job["started_at"] = self._now_iso()
        job["queue_position"] = 0
        job.pop("_fn", None)
        job.pop("_args", None)
        job.pop("_kwargs", None)
        self._persist(job_id, "job_started")

        class Tee:
            def __init__(self, real):
                self._real = real

            def write(self, s):
                self._real.write(s)
                if s.strip():
                    current = self_runtime.jobs.get(job_id)
                    if isinstance(current, dict):
                        current["log"].append(s.rstrip())

            def flush(self):
                self._real.flush()

        self_runtime = self

        def _worker():
            old_stdout = sys.stdout
            sys.stdout = Tee(old_stdout)
            final_status = "done"
            final_error = ""
            final_result = None
            has_result = False
            final_progress = None
            try:
                ret = fn(*args, **kwargs)
                final_result = ret
                has_result = True
                final_progress = 100
            except Exception as exc:
                err_text = str(exc)
                cancelled = isinstance(exc, self._job_cancelled_error_cls) or (
                    bool(self._cancel_token) and self._cancel_token in err_text
                )
                current = self_runtime.jobs.get(job_id)
                if not isinstance(current, dict):
                    current = {}
                if cancelled:
                    final_status = "cancelled"
                    final_error = "任务已取消"
                    if isinstance(exc, self._job_cancelled_error_cls):
                        final_result = getattr(exc, "result", None)
                        has_result = True
                    if isinstance(current.get("log"), list):
                        current["log"].append("[系统] 任务已取消")
                else:
                    final_status = "error"
                    final_error = err_text
                    if isinstance(current.get("log"), list):
                        current["log"].append(traceback.format_exc())
            finally:
                sys.stdout = old_stdout
                current = self_runtime.jobs.get(job_id)
                if isinstance(current, dict):
                    if has_result:
                        current["result"] = final_result
                    if isinstance(final_progress, int):
                        current["progress"] = max(0, min(100, int(final_progress)))
                    if final_status == "done":
                        current["error"] = None
                    elif final_error:
                        current["error"] = final_error
                    current["finished_at"] = self_runtime._now_iso()
                    if callable(self_runtime._after_job_finished):
                        try:
                            self_runtime._after_job_finished(job_id, current)
                        except Exception:
                            pass
                    current["status"] = final_status
                self_runtime._persist(job_id, "job_finished")
                if self_runtime.is_heavy_kind(kind):
                    with self_runtime.heavy_queue_lock:
                        self_runtime.dispatch_heavy_queue_locked()

        threading.Thread(target=_worker, daemon=True).start()

    def dispatch_heavy_queue_locked(self):
        while self._count_running_heavy_jobs_locked() < self._max_running and self.heavy_job_queue:
            jid = self.heavy_job_queue.popleft()
            job = self.jobs.get(jid)
            if not isinstance(job, dict):
                continue
            if job.get("status") != "queued":
                continue
            if bool(job.get("cancel_requested")):
                job["status"] = "cancelled"
                job["error"] = "任务已取消"
                job["finished_at"] = self._now_iso()
                self._persist(jid, "job_cancelled")
                continue
            if not callable(job.get("_fn")):
                job["status"] = "interrupted"
                job["error"] = "任务缺少可执行上下文，请重新发起"
                job["finished_at"] = self._now_iso()
                job["log"].append("[系统] 队列任务在恢复时缺少执行上下文，已中断。")
                self._persist(jid, "job_interrupted")
                continue
            self._start_job_worker_thread(
                jid,
                job["_fn"],
                tuple(job.get("_args", ()) or ()),
                dict(job.get("_kwargs", {}) or {}),
            )

        queued_rows = self._queued_heavy_jobs_locked()
        for row in queued_rows:
            jid = row.get("job_id")
            if isinstance(jid, str) and jid in self.jobs:
                self.jobs[jid]["queue_position"] = int(row.get("queue_position", 0) or 0)

    def run_in_bg(
        self,
        job_id: str,
        fn: Callable,
        *args,
        kind: str = "generic",
        job_meta: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        status = "queued" if self.is_heavy_kind(kind) else "running"
        now_iso = self._now_iso()
        self.jobs[job_id] = self.make_managed_job(
            job_id,
            {
                "status": status,
                "log": [],
                "progress": 0,
                "kind": kind,
                "meta": deepcopy(job_meta) if isinstance(job_meta, dict) else {},
                "queued_at": now_iso,
                "created_at": now_iso,
                "started_at": None,
                "result": None,
                "cancel_requested": False,
                "queue_position": 0,
                "_fn": fn,
                "_args": tuple(args),
                "_kwargs": dict(kwargs),
            },
        )
        self._persist(job_id, "job_created")
        if self.is_heavy_kind(kind):
            with self.heavy_queue_lock:
                self.heavy_job_queue.append(job_id)
                self.dispatch_heavy_queue_locked()
        else:
            self._start_job_worker_thread(job_id, fn, tuple(args), dict(kwargs))
        return job_id
