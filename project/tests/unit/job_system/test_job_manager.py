"""Unit tests for JobManager (X0 — async job infrastructure)."""

import time
import threading
from unittest.mock import MagicMock

import pytest

from modules.job_system.job_manager import JobManager


@pytest.fixture
def jm():
    """Fresh JobManager for each test."""
    mgr = JobManager(max_workers=2)
    yield mgr
    mgr.shutdown()


# ── T1: submit returns UUID job_id ──────────────────────────────

def test_submit_returns_id(jm):
    """submit() returns a non-empty string job_id."""
    job_id = jm.submit("test", lambda: "ok")
    assert isinstance(job_id, str)
    assert len(job_id) > 0


# ── T2: status lifecycle (pending → running → done) ────────────

def test_status_lifecycle(jm):
    """Job transitions through pending → running → done."""
    barrier = threading.Event()

    def slow_fn():
        barrier.wait(timeout=5)
        return 42

    job_id = jm.submit("test", slow_fn)
    # Should be pending or running immediately
    status = jm.get_status(job_id)
    assert status["status"] in ("pending", "running")

    barrier.set()
    # Wait for completion
    for _ in range(50):
        status = jm.get_status(job_id)
        if status["status"] == "done":
            break
        time.sleep(0.05)

    assert status["status"] == "done"
    assert status["result"] == 42
    assert status["error"] is None


# ── T3: progress update ────────────────────────────────────────

def test_progress_update(jm):
    """update_progress sets progress_pct on a running job."""
    barrier = threading.Event()

    def fn_with_progress():
        jm.update_progress(threading.current_thread()._job_id, 50.0)
        barrier.wait(timeout=5)
        return "done"

    job_id = jm.submit("test", fn_with_progress)
    # Give the task time to start and update progress
    time.sleep(0.3)

    status = jm.get_status(job_id)
    assert status["progress_pct"] == 50.0

    barrier.set()


# ── T4: cancel sets flag, task sees it ─────────────────────────

def test_cancel(jm):
    """cancel() sets a cancel flag; task can query it."""
    started = threading.Event()
    cancelled_seen = threading.Event()

    def cancellable_fn():
        started.set()
        # Poll cancel flag
        for _ in range(100):
            if jm.is_cancelled(threading.current_thread()._job_id):
                cancelled_seen.set()
                return "cancelled_by_task"
            time.sleep(0.05)
        return "not_cancelled"

    job_id = jm.submit("test", cancellable_fn)
    started.wait(timeout=2)

    result = jm.cancel(job_id)
    assert result is True

    cancelled_seen.wait(timeout=3)
    # Wait for job to finish
    for _ in range(50):
        status = jm.get_status(job_id)
        if status["status"] in ("done", "cancelled"):
            break
        time.sleep(0.05)

    assert status["status"] == "cancelled"


# ── T5: cleanup_expired removes old completed jobs ─────────────

def test_cleanup_expired(jm):
    """cleanup_expired removes jobs older than max_age_s."""
    job_id = jm.submit("test", lambda: "fast")
    # Wait for completion
    for _ in range(50):
        if jm.get_status(job_id)["status"] == "done":
            break
        time.sleep(0.05)

    # Not expired yet (max_age_s=3600 by default)
    removed = jm.cleanup_expired(max_age_s=3600)
    assert removed == 0

    # Force expire with 0 seconds
    removed = jm.cleanup_expired(max_age_s=0)
    assert removed == 1

    # Job should be gone
    status = jm.get_status(job_id)
    assert status["status"] == "not_found"
