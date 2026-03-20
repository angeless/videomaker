"""Tests for interrupted job recovery endpoints (T-0804)."""
from __future__ import annotations

import json
import threading

import pytest
from flask import Flask

from modules.app_api.routes.job_routes import create_job_blueprint


def _make_app(jobs: dict):
    """Create a minimal Flask app with job_routes blueprint."""
    app = Flask(__name__)
    lock = threading.Lock()
    queue = []
    snapshots = []

    bp = create_job_blueprint(
        jobs_getter=lambda: jobs,
        load_job_from_store=lambda jid: None,
        heavy_queue_lock_getter=lambda: lock,
        heavy_job_queue_getter=lambda: queue,
        dispatch_heavy_queue_locked=lambda: None,
        persist_job_snapshot=lambda jid, reason: snapshots.append((jid, reason)),
        system_load_snapshot_getter=lambda: {},
        state_dict_getter=lambda: {},
        estimate_job_eta=lambda j: {},
    )
    app.register_blueprint(bp)
    return app, snapshots


class TestInterruptedList:
    def test_returns_interrupted_jobs(self):
        jobs = {
            "j1": {"status": "interrupted", "kind": "social_export", "log": [], "error": "crash", "progress": 50, "queued_at": "2026-01-01T00:00:00"},
            "j2": {"status": "done", "kind": "generic", "log": []},
            "j3": {"status": "interrupted", "kind": "content_publish", "log": [], "error": "", "progress": 10},
        }
        app, _ = _make_app(jobs)
        with app.test_client() as c:
            resp = c.get("/api/job/interrupted")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert len(data["jobs"]) == 2
            ids = {j["job_id"] for j in data["jobs"]}
            assert ids == {"j1", "j3"}

    def test_empty_when_no_interrupted(self):
        jobs = {"j1": {"status": "done", "kind": "generic", "log": []}}
        app, _ = _make_app(jobs)
        with app.test_client() as c:
            resp = c.get("/api/job/interrupted")
            data = resp.get_json()
            assert data["ok"] is True
            assert len(data["jobs"]) == 0


class TestRetryAll:
    def test_requeues_interrupted_jobs(self):
        jobs = {
            "j1": {"status": "interrupted", "kind": "social_export", "log": [], "error": "crash", "finished_at": "t"},
        }
        app, snapshots = _make_app(jobs)
        with app.test_client() as c:
            resp = c.post("/api/job/interrupted/retry-all", json={"job_ids": ["j1"]})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["retried"] == 1
            assert data["failed"] == 0
        assert jobs["j1"]["status"] == "queued"
        assert jobs["j1"]["error"] == ""
        assert ("j1", "job_requeued") in snapshots

    def test_skips_non_interrupted(self):
        jobs = {"j1": {"status": "done", "kind": "generic", "log": []}}
        app, _ = _make_app(jobs)
        with app.test_client() as c:
            resp = c.post("/api/job/interrupted/retry-all", json={"job_ids": ["j1"]})
            data = resp.get_json()
            assert data["retried"] == 0
            assert data["failed"] == 1


class TestIgnore:
    def test_marks_as_cancelled(self):
        jobs = {
            "j1": {"status": "interrupted", "kind": "refinement", "log": [], "error": ""},
        }
        app, snapshots = _make_app(jobs)
        with app.test_client() as c:
            resp = c.post("/api/job/interrupted/ignore", json={"job_ids": ["j1"]})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["ignored"] == 1
        assert jobs["j1"]["status"] == "cancelled"
        assert ("j1", "job_ignored") in snapshots

    def test_ignores_missing_job(self):
        app, _ = _make_app({})
        with app.test_client() as c:
            resp = c.post("/api/job/interrupted/ignore", json={"job_ids": ["nope"]})
            data = resp.get_json()
            assert data["ignored"] == 0
