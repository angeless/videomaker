"""Tests for P0-2 queue recovery UX: recovery_rules + job retry endpoints."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Unit tests: recovery_rules (no Flask) ──────────────────────────────

from modules.app_api.services.recovery_rules import (
    assess_recovery,
    assess_batch_recovery,
    is_terminal_status,
    is_retryable_status,
)

_HINT_MAP = {
    "social_export": "/api/capabilities/social_export/rerun",
    "library_ingest_local": "/api/library/ingest/local",
}


class TestRecoveryRulesUnit:

    def test_is_terminal_status(self):
        for s in ("done", "error", "cancelled", "interrupted", "partial"):
            assert is_terminal_status(s), f"{s} should be terminal"
        for s in ("running", "queued", ""):
            assert not is_terminal_status(s), f"{s} should not be terminal"

    def test_is_retryable_status(self):
        for s in ("error", "cancelled", "interrupted"):
            assert is_retryable_status(s), f"{s} should be retryable"
        for s in ("done", "running", "queued", "partial"):
            assert not is_retryable_status(s), f"{s} should not be retryable"

    def test_assess_done_not_retryable(self):
        r = assess_recovery({"status": "done"})
        assert r["can_retry"] is False
        assert r["retry_scope"] == "none"
        assert r["current_status"] == "done"
        assert r["blocked_reason"] is not None

    def test_assess_running_not_retryable(self):
        r = assess_recovery({"status": "running"})
        assert r["can_retry"] is False
        assert r["retry_scope"] == "none"
        assert "执行中" in r["reason"]

    def test_assess_running_cancel_requested(self):
        r = assess_recovery({"status": "running", "cancel_requested": True})
        assert r["can_retry"] is False
        assert "停止中" in r["reason"]

    def test_assess_queued_not_retryable(self):
        r = assess_recovery({"status": "queued"})
        assert r["can_retry"] is False
        assert "排队" in r["reason"]

    def test_assess_error_retryable(self):
        r = assess_recovery({"status": "error", "kind": "social_export"}, retry_hint_map=_HINT_MAP)
        assert r["can_retry"] is True
        assert r["retry_scope"] == "single"
        assert r["retry_hint"] is not None
        assert r["retry_hint"]["endpoint"] == "/api/capabilities/social_export/rerun"

    def test_assess_cancelled_retryable(self):
        r = assess_recovery({"status": "cancelled"})
        assert r["can_retry"] is True
        assert r["retry_scope"] == "single"
        assert r["duplicate_risk"] is False

    def test_assess_interrupted_retryable(self):
        r = assess_recovery({"status": "interrupted", "kind": "library_ingest_local"}, retry_hint_map=_HINT_MAP)
        assert r["can_retry"] is True
        assert r["retry_scope"] == "single"
        assert r["retry_hint"]["endpoint"] == "/api/library/ingest/local"

    def test_assess_partial_batch(self):
        r = assess_recovery({"status": "partial"})
        assert r["can_retry"] is True
        assert r["retry_scope"] == "batch"
        assert r["duplicate_risk"] is True

    def test_assess_no_hint_when_kind_unknown(self):
        r = assess_recovery({"status": "error", "kind": "unknown_kind"}, retry_hint_map=_HINT_MAP)
        assert r["can_retry"] is True
        assert r["retry_hint"] is None
        assert "手工" in r["next_action"]

    def test_assess_invalid_job(self):
        r = assess_recovery(None)
        assert r["can_retry"] is False
        assert r["current_status"] == "unknown"

    def test_assess_unknown_status(self):
        r = assess_recovery({"status": "weird"})
        assert r["can_retry"] is False
        assert "未知" in r["reason"]


class TestBatchRecoveryUnit:

    def test_batch_recovery_mixed(self):
        items = [
            {"job_id": "a1", "status": "done"},
            {"job_id": "a2", "status": "error", "kind": "social_export"},
            {"job_id": "a3", "status": "running"},
            {"job_id": "a4", "status": "cancelled"},
            {"job_id": "a5", "status": "queued"},
        ]
        r = assess_batch_recovery(items, retry_hint_map=_HINT_MAP)
        assert r["total"] == 5
        assert r["retryable"] == 2
        assert r["skippable"] == 1
        assert r["blocked"] == 2
        assert r["can_batch_retry"] is True
        assert "a1" in r["skipped_ids"]
        assert "a2" in r["retryable_ids"]
        assert "a4" in r["retryable_ids"]
        assert "a3" in r["blocked_ids"]
        assert "a5" in r["blocked_ids"]

    def test_batch_all_done(self):
        items = [{"job_id": "x", "status": "done"}, {"job_id": "y", "status": "done"}]
        r = assess_batch_recovery(items)
        assert r["can_batch_retry"] is False
        assert r["retryable"] == 0
        assert r["skippable"] == 2

    def test_batch_all_retryable(self):
        items = [{"job_id": "x", "status": "error"}, {"job_id": "y", "status": "interrupted"}]
        r = assess_batch_recovery(items)
        assert r["can_batch_retry"] is True
        assert r["retryable"] == 2

    def test_batch_items_detail(self):
        items = [
            {"job_id": "a1", "status": "done"},
            {"job_id": "a2", "status": "error"},
        ]
        r = assess_batch_recovery(items)
        assert len(r["items"]) == 2
        assert r["items"][0]["action"] == "skipped"
        assert r["items"][1]["action"] == "retryable"

    def test_batch_empty(self):
        r = assess_batch_recovery([])
        assert r["total"] == 0
        assert r["can_batch_retry"] is False

    def test_batch_partial_item(self):
        items = [{"job_id": "p1", "status": "partial"}]
        r = assess_batch_recovery(items)
        assert r["retryable"] == 1
        assert r["can_batch_retry"] is True


# ── API integration tests ──────────────────────────────────────────────

fake_library_mod = types.ModuleType("modules.library.global_media_library")


class _FakeGML:
    def __init__(self, *args, **kwargs):
        self.db_path = ROOT / ".tmp_fake_library_recovery.db"

    def stats(self):
        return {}

    def search_assets(self, query="", limit=120, offset=0, retrieval_mode="hybrid", media_type="all"):
        return []

    def count_matching_assets(self, query="", retrieval_mode="hybrid", media_type="all"):
        return 0

    def get_assets(self, uids):
        return []

    def discover_videos(self, root):
        return []

    def discover_images(self, root):
        return []

    def ingest_local_path(self, source_path, max_videos=600, progress_callback=None, should_cancel=None):
        return {"cancelled": False, "scanned": 0, "indexed": 0, "dedup_hits": 0, "failed": 0, "total_candidates": 0, "assets": [], "truncated": False}


fake_library_mod.GlobalMediaLibrary = _FakeGML
sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

from modules.app_api import server  # noqa: E402


class _FakeSecretStore:
    def __init__(self):
        self.available = False
        self.backend = "fake"
        self.values = {}

    def info(self):
        return type("_I", (), {"backend": self.backend, "available": self.available, "reason": "test"})()

    def public_status(self):
        return {"backend": self.backend, "available": False, "reason": "test"}

    def get(self, name):
        return ""

    def set(self, name, value):
        return False

    def delete(self, name):
        return True


def _make_test_job(status, kind="social_export", **extra):
    """Create a minimal job dict for testing."""
    job = {
        "status": status,
        "kind": kind,
        "log": [],
        "progress": 100 if status == "done" else 0,
        "error": "test error" if status == "error" else None,
        "queued_at": "2026-03-10T12:00:00",
        "started_at": "2026-03-10T12:00:01",
        "finished_at": "2026-03-10T12:00:10" if status in ("done", "error", "cancelled", "interrupted") else None,
    }
    job.update(extra)
    return job


class TestJobEndpointRecovery:
    """Test that GET /api/job/<id> now includes recovery field."""

    def _setup(self, tmp_path, jobs_dict):
        old_lib = server._library
        old_ss = server._secret_store
        lib = _FakeGML()
        lib.db_path = tmp_path / "fake.db"
        server._library = lib
        server._secret_store = _FakeSecretStore()

        # Inject test jobs into server._jobs
        for jid, job in jobs_dict.items():
            server._jobs[jid] = job

        client = server.app.test_client()
        return client, old_lib, old_ss

    def _teardown(self, old_lib, old_ss, job_ids):
        server._library = old_lib
        server._secret_store = old_ss
        for jid in job_ids:
            server._jobs.pop(jid, None)

    def test_job_endpoint_includes_recovery(self, tmp_path):
        jobs = {"test_rec_1": _make_test_job("error")}
        client, old_lib, old_ss = self._setup(tmp_path, jobs)
        try:
            resp = client.get("/api/job/test_rec_1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "recovery" in data
            rec = data["recovery"]
            assert rec["can_retry"] is True
            assert rec["current_status"] == "error"
            assert rec["retry_scope"] == "single"
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()))

    def test_job_recovery_done(self, tmp_path):
        jobs = {"test_rec_done": _make_test_job("done")}
        client, old_lib, old_ss = self._setup(tmp_path, jobs)
        try:
            resp = client.get("/api/job/test_rec_done")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["recovery"]["can_retry"] is False
            assert data["recovery"]["blocked_reason"] is not None
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()))


class TestRetryEndpoint:
    """Test POST /api/job/<id>/retry."""

    def _setup(self, tmp_path, jobs_dict):
        old_lib = server._library
        old_ss = server._secret_store
        lib = _FakeGML()
        lib.db_path = tmp_path / "fake.db"
        server._library = lib
        server._secret_store = _FakeSecretStore()
        for jid, job in jobs_dict.items():
            server._jobs[jid] = job
        from modules.app_api.services import audit_log
        audit_log.close()
        audit_log.init_audit_log(tmp_path / "audit_test.db")
        client = server.app.test_client()
        return client, old_lib, old_ss, audit_log

    def _teardown(self, old_lib, old_ss, job_ids, audit_log):
        server._library = old_lib
        server._secret_store = old_ss
        for jid in job_ids:
            server._jobs.pop(jid, None)
        audit_log.close()

    def test_retry_failed_job(self, tmp_path):
        jobs = {"tr_fail": _make_test_job("error", kind="social_export")}
        client, old_lib, old_ss, al = self._setup(tmp_path, jobs)
        try:
            resp = client.post("/api/job/tr_fail/retry")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["action"] == "advice_only"
            assert data["retry_submitted"] is False
            assert data["recovery"]["can_retry"] is True
            assert data["source_job_id"] == "tr_fail"
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()), al)

    def test_retry_done_job_blocked(self, tmp_path):
        jobs = {"tr_done": _make_test_job("done")}
        client, old_lib, old_ss, al = self._setup(tmp_path, jobs)
        try:
            resp = client.post("/api/job/tr_done/retry")
            assert resp.status_code == 409
            data = resp.get_json()
            assert data["action"] == "advice_only"
            assert data["retry_submitted"] is False
            assert data["recovery"]["can_retry"] is False
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()), al)

    def test_retry_running_job_blocked(self, tmp_path):
        jobs = {"tr_run": _make_test_job("running")}
        client, old_lib, old_ss, al = self._setup(tmp_path, jobs)
        try:
            resp = client.post("/api/job/tr_run/retry")
            assert resp.status_code == 409
            data = resp.get_json()
            assert data["recovery"]["can_retry"] is False
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()), al)

    def test_retry_nonexistent_404(self, tmp_path):
        client, old_lib, old_ss, al = self._setup(tmp_path, {})
        try:
            resp = client.post("/api/job/no_such_job/retry")
            assert resp.status_code == 404
        finally:
            self._teardown(old_lib, old_ss, [], al)

    def test_retry_writes_audit(self, tmp_path):
        jobs = {"tr_audit": _make_test_job("error", kind="social_export")}
        client, old_lib, old_ss, al = self._setup(tmp_path, jobs)
        try:
            resp = client.post("/api/job/tr_audit/retry")
            assert resp.status_code == 200
            entries = al.query(operation="retry")
            assert len(entries) >= 1
            assert entries[0]["resource_id"] == "tr_audit"
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()), al)

    def test_retry_blocked_writes_audit(self, tmp_path):
        jobs = {"tr_blk": _make_test_job("done")}
        client, old_lib, old_ss, al = self._setup(tmp_path, jobs)
        try:
            resp = client.post("/api/job/tr_blk/retry")
            assert resp.status_code == 409
            entries = al.query(operation="retry_blocked")
            assert len(entries) >= 1
            assert entries[0]["resource_id"] == "tr_blk"
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()), al)


class TestBatchRetryEndpoint:
    """Test POST /api/jobs/batch-retry."""

    def _setup(self, tmp_path, jobs_dict):
        old_lib = server._library
        old_ss = server._secret_store
        lib = _FakeGML()
        lib.db_path = tmp_path / "fake.db"
        server._library = lib
        server._secret_store = _FakeSecretStore()
        for jid, job in jobs_dict.items():
            server._jobs[jid] = job
        from modules.app_api.services import audit_log
        audit_log.close()
        audit_log.init_audit_log(tmp_path / "audit_batch.db")
        client = server.app.test_client()
        return client, old_lib, old_ss, audit_log

    def _teardown(self, old_lib, old_ss, job_ids, audit_log):
        server._library = old_lib
        server._secret_store = old_ss
        for jid in job_ids:
            server._jobs.pop(jid, None)
        audit_log.close()

    def test_batch_retry_mixed(self, tmp_path):
        jobs = {
            "b1": _make_test_job("done"),
            "b2": _make_test_job("error"),
            "b3": _make_test_job("running"),
        }
        client, old_lib, old_ss, al = self._setup(tmp_path, jobs)
        try:
            resp = client.post("/api/jobs/batch-retry", json={"job_ids": ["b1", "b2", "b3"]})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["action"] == "advice_only"
            assert data["retry_submitted"] is False
            s = data["summary"]
            assert s["total"] == 3
            assert s["retryable"] == 1
            assert s["skipped"] == 1
            assert s["blocked"] == 1
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()), al)

    def test_batch_retry_empty(self, tmp_path):
        client, old_lib, old_ss, al = self._setup(tmp_path, {})
        try:
            resp = client.post("/api/jobs/batch-retry", json={"job_ids": []})
            assert resp.status_code == 400
        finally:
            self._teardown(old_lib, old_ss, [], al)

    def test_batch_retry_writes_audit(self, tmp_path):
        jobs = {
            "ba1": _make_test_job("error"),
            "ba2": _make_test_job("done"),
        }
        client, old_lib, old_ss, al = self._setup(tmp_path, jobs)
        try:
            resp = client.post("/api/jobs/batch-retry", json={"job_ids": ["ba1", "ba2"]})
            assert resp.status_code == 200
            entries = al.query(operation="batch_retry")
            assert len(entries) >= 1
            detail = entries[0].get("detail", {})
            assert detail["total"] == 2
            assert detail["retryable"] == 1
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()), al)

    def test_batch_retry_nonexistent_job(self, tmp_path):
        jobs = {"be1": _make_test_job("done")}
        client, old_lib, old_ss, al = self._setup(tmp_path, jobs)
        try:
            resp = client.post("/api/jobs/batch-retry", json={"job_ids": ["be1", "no_such"]})
            assert resp.status_code == 200
            data = resp.get_json()
            # nonexistent → blocked (not_found is unknown status)
            assert data["summary"]["total"] == 2
        finally:
            self._teardown(old_lib, old_ss, list(jobs.keys()), al)
