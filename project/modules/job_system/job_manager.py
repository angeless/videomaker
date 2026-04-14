"""Async job management infrastructure (X0).

Provides a thread-safe JobManager for submitting, tracking, and cancelling
asynchronous tasks. Used by B4a (video stream analysis) and D4a (render
progress) for 202 + job_id async patterns.
"""

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Valid job status values
_VALID_STATUSES = ("pending", "running", "done", "failed", "cancelled")


class _JobRecord:
    """Internal record for a single job."""

    __slots__ = (
        "job_id", "job_type", "status", "progress_pct",
        "result", "error", "cancel_flag", "created_at", "finished_at",
        "_lock", "future",
    )

    def __init__(self, job_id: str, job_type: str):
        self.job_id = job_id
        self.job_type = job_type
        self.status = "pending"
        self.progress_pct = 0.0
        self.result = None  # type: Any
        self.error = None  # type: Optional[str]
        self.cancel_flag = False
        self.created_at = time.time()
        self.finished_at = None  # type: Optional[float]
        self._lock = threading.Lock()
        self.future = None  # type: Optional[Any]

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "job_id": self.job_id,
                "job_type": self.job_type,
                "status": self.status,
                "progress_pct": self.progress_pct,
                "result": self.result,
                "error": self.error,
            }


class JobManager:
    """Async task manager with submit / progress / cancel semantics.

    Args:
        max_workers: Maximum concurrent jobs (default 4).
    """

    def __init__(self, max_workers: int = 4):
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: Dict[str, _JobRecord] = {}
        self._lock = threading.Lock()  # protects _jobs dict

    # ── Public API ───────────────────────────────────────────────

    def submit(self, job_type: str, fn: Callable, *args: Any) -> str:
        """Submit an async task, returns job_id (UUID hex)."""
        job_id = uuid.uuid4().hex[:16]
        record = _JobRecord(job_id, job_type)

        with self._lock:
            self._jobs[job_id] = record

        future = self._pool.submit(self._run_job, record, fn, args)
        record.future = future
        logger.info("Job submitted: %s (type=%s)", job_id, job_type)
        return job_id

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """Return status dict for a job. Returns status='not_found' if unknown."""
        with self._lock:
            record = self._jobs.get(job_id)

        if record is None:
            return {
                "job_id": job_id,
                "job_type": "",
                "status": "not_found",
                "progress_pct": 0.0,
                "result": None,
                "error": None,
            }
        return record.to_dict()

    def update_progress(self, job_id: str, pct: float) -> None:
        """Update progress percentage for a running job (0-100)."""
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            return
        with record._lock:
            record.progress_pct = max(0.0, min(100.0, pct))

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Cancels pending futures and sets flag for running jobs."""
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            return False
        with record._lock:
            if record.status in ("done", "failed", "cancelled"):
                return False
            record.cancel_flag = True
            # Attempt to cancel the Future if still pending (not yet started).
            # If cancel() succeeds, _run_job never executes, so we must mark the
            # record terminal here; otherwise status would be stuck at "pending".
            if record.future is not None and record.future.cancel():
                record.status = "cancelled"
                record.finished_at = time.time()
        logger.info("Cancel requested: %s", job_id)
        return True

    def is_cancelled(self, job_id: str) -> bool:
        """Check if cancel has been requested for this job."""
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            return False
        with record._lock:
            return record.cancel_flag

    def cleanup_expired(self, max_age_s: int = 3600) -> int:
        """Remove completed jobs older than max_age_s. Returns count removed."""
        now = time.time()
        to_remove = []

        with self._lock:
            for jid, rec in self._jobs.items():
                with rec._lock:
                    if rec.status in ("done", "failed", "cancelled"):
                        if rec.finished_at is not None and (now - rec.finished_at) >= max_age_s:
                            to_remove.append(jid)

            for jid in to_remove:
                del self._jobs[jid]

        if to_remove:
            logger.info("Cleaned up %d expired jobs", len(to_remove))
        return len(to_remove)

    def shutdown(self) -> None:
        """Gracefully shut down the thread pool."""
        self._pool.shutdown(wait=False)

    # ── Internal ─────────────────────────────────────────────────

    def _run_job(self, record: _JobRecord, fn: Callable, args: tuple) -> None:
        """Execute a job function, updating record status."""
        # Attach job_id to thread for progress updates from within the task
        threading.current_thread()._job_id = record.job_id  # type: ignore[attr-defined]

        with record._lock:
            record.status = "running"

        try:
            result = fn(*args)
            with record._lock:
                if record.cancel_flag:
                    record.status = "cancelled"
                    record.result = result
                else:
                    record.status = "done"
                    record.result = result
                record.progress_pct = 100.0
                record.finished_at = time.time()
        except Exception as exc:
            with record._lock:
                record.status = "failed"
                record.error = str(exc)
                record.finished_at = time.time()
            logger.error("Job %s failed: %s", record.job_id, exc)
