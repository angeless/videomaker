"""Shared E2E / flow-test fixtures.

Only used by test_e2e_*.py files.  Uses ``e2e_`` prefix to avoid
shadowing per-file ``tmpdir`` / ``client`` fixtures in existing tests.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib

importlib.import_module("modules")
importlib.import_module("modules.library")
_mod = importlib.import_module("modules.library.global_media_library")
_mod = importlib.reload(_mod)
GlobalMediaLibrary = _mod.GlobalMediaLibrary

from flask import Flask
from modules.app_api.routes.library_routes import create_library_blueprint


# ── helpers ──


def _make_app(gml):
    """Build a Flask test-app wired to *gml* with synchronous job runner."""
    jobs = {}

    def _run_in_bg(job_id, fn, *args, kind="generic", job_meta=None, **kwargs):
        jobs[job_id] = {"status": "running", "progress": 0, "log": []}
        try:
            fn()
            jobs[job_id]["status"] = "done"
        except Exception as exc:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(exc)
        return job_id

    app = Flask(__name__)
    app.config["TESTING"] = True
    bp = create_library_blueprint(
        library_getter=lambda: gml,
        jobs_getter=lambda: jobs,
        run_in_bg=_run_in_bg,
        running_heavy_jobs_getter=lambda: [],
        system_load_snapshot_getter=lambda: {},
        task_queue_snapshot_getter=lambda: {},
        cancel_token_getter=lambda: "CANCEL",
        job_cancelled_error_getter=lambda: Exception,
    )
    app.register_blueprint(bp)
    return app


# ── fixtures (e2e_ prefix) ──


@pytest.fixture()
def e2e_tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def e2e_library(e2e_tmpdir):
    """Empty GlobalMediaLibrary instance."""
    db_path = os.path.join(e2e_tmpdir, "e2e_test.db")
    return GlobalMediaLibrary(db_path=db_path)


@pytest.fixture()
def e2e_seeded_library(e2e_tmpdir):
    """GlobalMediaLibrary pre-loaded with 3 test assets (2 video + 1 image)."""
    db_path = os.path.join(e2e_tmpdir, "e2e_test.db")
    gml = GlobalMediaLibrary(db_path=db_path)
    now = gml._now()
    with gml._connect() as conn:
        for uid, fname, sha in [
            ("uid_a", "clip_a.mp4", "sha_aaa"),
            ("uid_b", "clip_b.mp4", "sha_bbb"),
            ("uid_c", "photo_c.jpg", "sha_ccc"),
        ]:
            conn.execute(
                """INSERT INTO assets
                   (uid, filename, sha256, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    size_bytes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid, fname, sha, f"/test/{fname}", "local",
                    10.0, "1920x1080", 80, f"scene for {fname}",
                    50000, now, now,
                ),
            )
            conn.execute(
                """INSERT INTO asset_locations
                   (uid, path, source_type, is_available, last_seen_at)
                   VALUES (?,?,?,?,?)""",
                (uid, f"/test/{fname}", "local", 1, now),
            )
    return gml


@pytest.fixture()
def e2e_app(e2e_seeded_library):
    """Flask app wired to *e2e_seeded_library*."""
    return _make_app(e2e_seeded_library)


@pytest.fixture()
def e2e_client(e2e_app):
    return e2e_app.test_client()
