"""v0.7 Phase C-1 + C-2 + D-1 + D-2 + D-3 + D-4 — Project Relink API tests.

C-1 tests (6):
  POST /api/library/project-relink
  GET  /api/library/project-relink/<job_id>
  GET  /api/library/project-relink/<job_id>/export
  POST /api/library/project-relink/<job_id>/apply
  Invalid project path → error
  Relink does not touch semantic tables

C-2 tests (5):
  GET  /api/library/project-relink/list
  GET  /api/library/project-relink/compare
  POST /api/library/project-relink/validate
  POST apply → 409 idempotent guard
  POST apply with force=True → 200

D-1 tests (7):
  POST retry → success / not-failed guard
  GET  preview-apply
  GET  export-missing?format=json / csv
  GET  suggest-candidates
  GET  missing-stats

D-2 tests (4):
  POST bind → success / invalid uid
  POST unbind → success
  POST refresh-items → success

D-3 tests (5):
  POST batch-bind → success
  GET  item/<id>/history
  POST item/<id>/undo-bind
  GET  <job_id>/outputs
  GET  <job_id>/workbench

D-4 tests (5):
  POST reanalyze → successor job with inherited bindings
  GET  job-chain → ordered chain
  POST verify → path validation
  POST handover → generates report
  GET  export-handover → json/markdown
"""
import json
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
mod = importlib.import_module("modules.library.global_media_library")
mod = importlib.reload(mod)
GlobalMediaLibrary = mod.GlobalMediaLibrary

from flask import Flask
from modules.app_api.routes.library_routes import create_library_blueprint


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture()
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _write_draft(path, videos=None, audios=None):
    draft = {
        "materials": {
            "videos": videos or [],
            "audios": audios or [],
        },
        "tracks": [],
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(draft, f)
    return path


@pytest.fixture()
def app_and_lib(tmpdir):
    """Create a minimal Flask app with the library blueprint."""
    db_path = os.path.join(tmpdir, "api_test.db")
    gml = GlobalMediaLibrary(db_path=db_path)

    # Seed a test asset
    with gml._connect() as conn:
        now = gml._now()
        conn.execute(
            """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
               duration, resolution, quality_score, scene_description,
               size_bytes, created_at, updated_at)
               VALUES ('uid_x','clip_x.mp4','sha_xxx','/old/clip_x.mp4','local',
                       10.0,'1920x1080',80,'scene_x',50000,?,?)""",
            (now, now),
        )
        conn.execute(
            "INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
            ("uid_x", "/old/clip_x.mp4", "local", 0, now),
        )

    # Minimal stubs for blueprint dependencies
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

    return app, gml


@pytest.fixture()
def client(app_and_lib):
    app, _ = app_and_lib
    return app.test_client()


# ──────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────

class TestProjectRelinkAPI:
    def test_create_project_relink(self, app_and_lib, tmpdir):
        """POST /api/library/project-relink → 200 + job_id."""
        app, _ = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "api_draft.json")
        _write_draft(
            draft_path,
            videos=[{"id": "v1", "path": "/old/clip_x.mp4"}],
        )

        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["job_id"] > 0
        assert "summary" in data
        assert len(data["items"]) == 1

    def test_get_project_relink(self, app_and_lib, tmpdir):
        """GET /api/library/project-relink/{id} → 200 + items."""
        app, _ = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "api_get.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/old/clip_x.mp4"}])

        create_resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        job_id = create_resp.get_json()["job_id"]

        resp = client.get(f"/api/library/project-relink/{job_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "job" in data
        assert len(data["job"]["items"]) == 1

    def test_export_project_relink(self, app_and_lib, tmpdir):
        """GET /api/library/project-relink/{id}/export → relink_map."""
        app, _ = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "api_exp.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/old/clip_x.mp4"}])

        create_resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        job_id = create_resp.get_json()["job_id"]

        resp = client.get(f"/api/library/project-relink/{job_id}/export")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "relink_map" in data
        assert "summary" in data["relink_map"]
        assert "items" in data["relink_map"]

    def test_invalid_project_path(self, client):
        """POST with nonexistent path → error."""
        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": "/nonexistent/path/draft.json"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_missing_project_path(self, client):
        """POST without project_path → 400."""
        resp = client.post(
            "/api/library/project-relink",
            json={},
        )
        assert resp.status_code == 400

    def test_relink_does_not_touch_semantic_tables(self, app_and_lib, tmpdir):
        """Verify relink API does NOT write to asset_tag_result/evidence."""
        app, gml = app_and_lib
        client = app.test_client()

        with gml._connect() as conn:
            before_tags = conn.execute("SELECT count(*) FROM asset_tag_result").fetchone()[0]
            before_evidence = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]

        draft_path = os.path.join(tmpdir, "api_sem.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/old/clip_x.mp4"}])
        client.post("/api/library/project-relink", json={"project_path": draft_path})

        with gml._connect() as conn:
            after_tags = conn.execute("SELECT count(*) FROM asset_tag_result").fetchone()[0]
            after_evidence = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]

        assert before_tags == after_tags
        assert before_evidence == after_evidence


# ──────────────────────────────────────────────────────────
# Phase C-2 API Tests
# ──────────────────────────────────────────────────────────

class TestProjectRelinkAPIv2:
    """C-2: list, compare, validate, idempotent apply, force apply."""

    # ── helpers ──

    def _create_job(self, client, tmpdir, suffix="a"):
        draft_path = os.path.join(tmpdir, f"c2_draft_{suffix}.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/old/clip_x.mp4"}])
        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        assert resp.status_code == 200
        return resp.get_json()["job_id"], draft_path

    def _create_relinked_job(self, client, gml, tmpdir, suffix="r"):
        """Create a job with one genuinely relinked item (asset at new path)."""
        new_file = os.path.join(tmpdir, f"relocated_{suffix}", "clip_x.mp4")
        Path(new_file).parent.mkdir(parents=True, exist_ok=True)
        Path(new_file).write_text("content")
        with gml._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO asset_locations "
                "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                ("uid_x", new_file, "local", 1, gml._now()),
            )
        # Draft references the OLD (non-existent) path → will be relinked to new_file
        draft_path = os.path.join(tmpdir, f"c2_draft_rl_{suffix}.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/old/clip_x.mp4"}])
        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        assert resp.status_code == 200
        return resp.get_json()["job_id"], draft_path

    # ── list ──

    def test_api_list_jobs(self, app_and_lib, tmpdir):
        """GET /project-relink/list → jobs list."""
        app, _ = app_and_lib
        client = app.test_client()

        jid1, _ = self._create_job(client, tmpdir, "l1")
        jid2, _ = self._create_job(client, tmpdir, "l2")

        resp = client.get("/api/library/project-relink/list")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "jobs" in data
        ids = [j["job_id"] for j in data["jobs"]]
        assert jid1 in ids
        assert jid2 in ids
        # Descending order — most recent first
        assert ids.index(jid2) < ids.index(jid1)

    # ── compare ──

    def test_api_compare_jobs(self, app_and_lib, tmpdir):
        """GET /project-relink/compare → delta result."""
        app, gml = app_and_lib
        client = app.test_client()

        jid1, _ = self._create_job(client, tmpdir, "c1")
        jid2, _ = self._create_job(client, tmpdir, "c2")

        resp = client.get(
            f"/api/library/project-relink/compare?job_id_a={jid1}&job_id_b={jid2}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data
        assert "job_id_a" in data
        assert "job_id_b" in data
        # Both jobs reference same asset → no newly_relinked/newly_missing
        assert isinstance(data["summary"]["total_changes"], int)

    def test_api_compare_missing_params(self, client):
        """GET /project-relink/compare without params → 400."""
        resp = client.get("/api/library/project-relink/compare")
        assert resp.status_code == 400

    # ── validate ──

    def test_api_validate(self, app_and_lib, tmpdir):
        """POST /project-relink/validate → valid result."""
        app, _ = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "val_draft.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/some/clip.mp4"}])

        resp = client.post(
            "/api/library/project-relink/validate",
            json={"project_path": draft_path, "project_type": "jianying"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True
        assert isinstance(data["errors"], list)
        assert isinstance(data["warnings"], list)
        assert "version_info" in data

    def test_api_validate_missing_path(self, client):
        """POST /project-relink/validate without path → 400."""
        resp = client.post(
            "/api/library/project-relink/validate",
            json={},
        )
        assert resp.status_code == 400

    # ── idempotent apply ──

    def test_api_apply_idempotent(self, app_and_lib, tmpdir):
        """Second apply without force → 409."""
        app, gml = app_and_lib
        client = app.test_client()

        jid, draft_path = self._create_relinked_job(client, gml, tmpdir, "idem")

        # First apply
        resp1 = client.post(
            f"/api/library/project-relink/{jid}/apply",
            json={},
        )
        assert resp1.status_code == 200
        assert resp1.get_json()["result"]["applied"] >= 1

        # Second apply → 409
        resp2 = client.post(
            f"/api/library/project-relink/{jid}/apply",
            json={},
        )
        assert resp2.status_code == 409
        data = resp2.get_json()
        assert data.get("already_applied") is True

    # ── force apply ──

    def test_api_apply_force(self, app_and_lib, tmpdir):
        """Apply with force=True after first apply → 200."""
        app, gml = app_and_lib
        client = app.test_client()

        jid, draft_path = self._create_relinked_job(client, gml, tmpdir, "force")

        # First apply
        resp1 = client.post(
            f"/api/library/project-relink/{jid}/apply",
            json={},
        )
        assert resp1.status_code == 200

        # Force apply → 200
        resp2 = client.post(
            f"/api/library/project-relink/{jid}/apply",
            json={"force": True},
        )
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert data["ok"] is True


# ──────────────────────────────────────────────────────────
# Phase D-1 API Tests
# ──────────────────────────────────────────────────────────

class TestProjectRelinkAPID1:
    """D-1: retry, preview-apply, export-missing."""

    # ── retry ──

    def test_retry_api_success(self, app_and_lib, tmpdir):
        """POST retry on a failed job → 200 + new job."""
        app, gml = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "d1_retry.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/old/clip_x.mp4"}])

        # Create a failed job manually
        with gml._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO project_relink_job (project_path, project_type, status, error_message) "
                "VALUES (?, 'jianying', 'failed', 'test failure')",
                (draft_path,),
            )
            failed_id = cursor.lastrowid

        resp = client.post(f"/api/library/project-relink/{failed_id}/retry")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["job_id"] != failed_id
        assert data["retry_of"] == failed_id

    def test_retry_api_not_failed(self, app_and_lib, tmpdir):
        """POST retry on a done job → 400."""
        app, gml = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "d1_retry_nf.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/old/clip_x.mp4"}])
        create_resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        job_id = create_resp.get_json()["job_id"]

        resp = client.post(f"/api/library/project-relink/{job_id}/retry")
        assert resp.status_code == 400

    # ── preview-apply ──

    def test_preview_apply_api(self, app_and_lib, tmpdir):
        """GET preview-apply → will_apply, will_skip, warnings."""
        app, gml = app_and_lib
        client = app.test_client()

        # Create a relinked job
        new_file = os.path.join(tmpdir, "relocated_pa", "clip_x.mp4")
        Path(new_file).parent.mkdir(parents=True, exist_ok=True)
        Path(new_file).write_text("content pa")
        with gml._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO asset_locations "
                "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                ("uid_x", new_file, "local", 1, gml._now()),
            )
        draft_path = os.path.join(tmpdir, "d1_pa.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/old/clip_x.mp4"}])
        create_resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        job_id = create_resp.get_json()["job_id"]

        resp = client.get(f"/api/library/project-relink/{job_id}/preview-apply")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "will_apply" in data
        assert "will_skip" in data
        assert "output_path_preview" in data
        assert "warnings" in data

    # ── export-missing ──

    def test_export_missing_json_api(self, app_and_lib, tmpdir):
        """GET export-missing?format=json → items + summary."""
        app, gml = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "d1_em.json")
        _write_draft(draft_path, videos=[
            {"id": "v1", "path": "/old/clip_x.mp4"},
            {"id": "v2", "path": "/totally/unknown_file.mp4"},
        ])
        create_resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        job_id = create_resp.get_json()["job_id"]

        resp = client.get(f"/api/library/project-relink/{job_id}/export-missing?format=json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        assert "summary" in data
        # Every item must have reason (hard rule #4)
        for item in data["items"]:
            assert "reason" in item

    def test_export_missing_csv_api(self, app_and_lib, tmpdir):
        """GET export-missing?format=csv → text/csv response."""
        app, gml = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "d1_em_csv.json")
        _write_draft(draft_path, videos=[{"id": "v1", "path": "/totally/unknown_csv.mp4"}])
        create_resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        job_id = create_resp.get_json()["job_id"]

        resp = client.get(f"/api/library/project-relink/{job_id}/export-missing?format=csv")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/csv")
        csv_text = resp.data.decode("utf-8")
        lines = csv_text.strip().split("\n")
        assert len(lines) >= 2  # header + data

    # ── suggest-candidates ──

    def test_suggest_candidates_api(self, app_and_lib, tmpdir):
        """GET suggest-candidates → suggestions list with candidates."""
        app, gml = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "d1_sc.json")
        _write_draft(draft_path, videos=[
            {"id": "v1", "path": "/old/clip_x.mp4"},  # missing (uid_x exists)
            {"id": "v2", "path": "/totally/unknown_sc.mp4"},  # unmatched
        ])
        create_resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        job_id = create_resp.get_json()["job_id"]

        resp = client.get(f"/api/library/project-relink/{job_id}/suggest-candidates?max=3")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "suggestions" in data
        assert "total_items" in data
        # Each suggestion has required fields
        for s in data["suggestions"]:
            assert "item_id" in s
            assert "candidates" in s
            assert isinstance(s["candidates"], list)

    # ── missing-stats ──

    def test_missing_stats_api(self, app_and_lib, tmpdir):
        """GET missing-stats → aggregated stats."""
        app, gml = app_and_lib
        client = app.test_client()

        draft_path = os.path.join(tmpdir, "d1_ms.json")
        _write_draft(draft_path, videos=[
            {"id": "v1", "path": "/old/clip_x.mp4"},
        ])
        # Create two jobs
        client.post("/api/library/project-relink", json={"project_path": draft_path})
        client.post("/api/library/project-relink", json={"project_path": draft_path})

        resp = client.get(f"/api/library/project-relink/missing-stats?project_path={draft_path}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_jobs"] == 2
        assert "unique_missing_assets" in data
        assert "persistent_missing" in data
        assert "trend" in data


# ──────────────────────────────────────────────────────────
# Phase D-2 API Tests
# ──────────────────────────────────────────────────────────

class TestProjectRelinkAPID2:
    """D-2: bind, unbind, refresh-items."""

    def _create_missing_job(self, client, tmpdir):
        """Create a job with a missing item, then GET to obtain items with item_id."""
        draft_path = os.path.join(tmpdir, "d2_draft.json")
        _write_draft(draft_path, videos=[
            {"id": "v1", "path": "/old/clip_x.mp4"},        # missing
            {"id": "v2", "path": "/x/unknown_d2.mp4"},      # unmatched
        ])
        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        assert resp.status_code == 200
        job_id = resp.get_json()["job_id"]
        # GET the job to obtain items with item_id (create response lacks item_id)
        get_resp = client.get(f"/api/library/project-relink/{job_id}")
        assert get_resp.status_code == 200
        items = get_resp.get_json()["job"]["items"]
        return job_id, items

    def test_bind_api_success(self, app_and_lib, tmpdir):
        """POST bind → 200 + manual_uid set + effective fields."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)
        missing = [i for i in items if i["status"] == "missing"]
        assert len(missing) >= 1
        item_id = missing[0]["item_id"]

        resp = client.post(
            f"/api/library/project-relink/item/{item_id}/bind",
            json={"uid": "uid_x", "decision_source": "candidate"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["item"]["manual_uid"] == "uid_x"
        assert data["item"]["manual_decision_source"] == "candidate"
        assert "effective_uid" in data["item"]
        assert "binding_mode" in data["item"]
        assert data["item"]["binding_mode"] == "manual"

    def test_bind_invalid_uid(self, app_and_lib, tmpdir):
        """POST bind with nonexistent uid → 400."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)
        missing = [i for i in items if i["status"] == "missing"]
        item_id = missing[0]["item_id"]

        resp = client.post(
            f"/api/library/project-relink/item/{item_id}/bind",
            json={"uid": "uid_nonexistent"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_unbind_api(self, app_and_lib, tmpdir):
        """POST unbind → 200 + manual fields cleared."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)
        missing = [i for i in items if i["status"] == "missing"]
        item_id = missing[0]["item_id"]

        # First bind
        client.post(
            f"/api/library/project-relink/item/{item_id}/bind",
            json={"uid": "uid_x"},
        )

        # Then unbind
        resp = client.post(f"/api/library/project-relink/item/{item_id}/unbind")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["item"]["manual_uid"] is None
        assert data["item"]["binding_mode"] == "system"

    def test_refresh_api(self, app_and_lib, tmpdir):
        """POST refresh-items → 200 + refreshed summary."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)

        resp = client.post(f"/api/library/project-relink/{job_id}/refresh-items")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "result" in data
        assert "refreshed" in data["result"]
        assert "changed" in data["result"]
        assert "unchanged" in data["result"]


# ──────────────────────────────────────────────────────────
# D-3: batch-bind, history, undo-bind, outputs, workbench
# ──────────────────────────────────────────────────────────

class TestProjectRelinkAPID3:
    """D-3: batch-bind, history, undo-bind, outputs, workbench."""

    def _create_missing_job(self, client, tmpdir):
        """Create a job with a missing + unmatched item."""
        draft_path = os.path.join(tmpdir, "d3_draft.json")
        _write_draft(draft_path, videos=[
            {"id": "v1", "path": "/old/clip_x.mp4"},
            {"id": "v2", "path": "/x/unknown_d3.mp4"},
        ])
        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        assert resp.status_code == 200
        job_id = resp.get_json()["job_id"]
        get_resp = client.get(f"/api/library/project-relink/{job_id}")
        assert get_resp.status_code == 200
        items = get_resp.get_json()["job"]["items"]
        return job_id, items

    def test_batch_bind_api(self, app_and_lib, tmpdir):
        """POST batch-bind → 200 + success/failed counts."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)
        missing = [i for i in items if i["status"] == "missing"]
        assert len(missing) >= 1

        bindings = [{"item_id": missing[0]["item_id"], "uid": "uid_x"}]
        resp = client.post(
            "/api/library/project-relink/batch-bind",
            json={"bindings": bindings, "decision_source": "candidate"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["success_count"] >= 1

    def test_item_history_api(self, app_and_lib, tmpdir):
        """GET item history → 200 + action entries."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)
        missing = [i for i in items if i["status"] == "missing"]
        item_id = missing[0]["item_id"]

        # Bind first to create history
        client.post(
            f"/api/library/project-relink/item/{item_id}/bind",
            json={"uid": "uid_x"},
        )

        resp = client.get(f"/api/library/project-relink/item/{item_id}/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "history" in data
        assert len(data["history"]) >= 1

    def test_undo_bind_api(self, app_and_lib, tmpdir):
        """POST undo-bind → 200 + manual_uid cleared."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)
        missing = [i for i in items if i["status"] == "missing"]
        item_id = missing[0]["item_id"]

        # Bind first
        client.post(
            f"/api/library/project-relink/item/{item_id}/bind",
            json={"uid": "uid_x"},
        )

        # Undo
        resp = client.post(f"/api/library/project-relink/item/{item_id}/undo-bind")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["item"]["manual_uid"] is None

    def test_outputs_api(self, app_and_lib, tmpdir):
        """GET outputs → 200 + output list (may be empty if no apply yet)."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)

        resp = client.get(f"/api/library/project-relink/{job_id}/outputs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "outputs" in data
        assert isinstance(data["outputs"], list)

    def test_workbench_api(self, app_and_lib, tmpdir):
        """GET workbench → 200 + grouped items."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, items = self._create_missing_job(client, tmpdir)

        resp = client.get(f"/api/library/project-relink/{job_id}/workbench")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "groups" in data
        groups = data["groups"]
        for key in ("stable", "relinked_system", "relinked_manual", "missing", "unmatched"):
            assert key in groups, f"Missing workbench group: {key}"


# ──────────────────────────────────────────────────────────
# D-4: reanalyze, job-chain, verify, handover, export-handover
# ──────────────────────────────────────────────────────────

class TestProjectRelinkAPID4:
    """D-4: long-term sync + handover closure API tests."""

    def _create_done_job_with_manual(self, client, gml, tmpdir, suffix=""):
        """Create a done job that has a manual binding."""
        draft_path = os.path.join(tmpdir, f"d4_draft{suffix}.json")
        new_file = os.path.join(tmpdir, f"relocated{suffix}", "clip_x.mp4")
        Path(new_file).parent.mkdir(parents=True, exist_ok=True)
        Path(new_file).write_text(f"content d4{suffix}")
        with gml._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO asset_locations "
                "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                ("uid_x", new_file, "local", 1, gml._now()),
            )
        _write_draft(draft_path, videos=[
            {"id": "v1", "path": "/old/clip_x.mp4"},
            {"id": "v2", "path": "/x/unknown_d4.mp4"},
        ])
        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": draft_path},
        )
        assert resp.status_code == 200
        job_id = resp.get_json()["job_id"]

        # Get items to find one we can bind
        get_resp = client.get(f"/api/library/project-relink/{job_id}")
        items = get_resp.get_json()["job"]["items"]
        unmatched = [i for i in items if i["status"] == "unmatched"]
        if unmatched:
            # Register a uid for the unmatched item
            with gml._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO asset_locations "
                    "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                    ("uid_manual", new_file, "local", 1, gml._now()),
                )
            client.post(
                f"/api/library/project-relink/item/{unmatched[0]['item_id']}/bind",
                json={"uid": "uid_manual", "decision_source": "browse"},
            )

        return job_id, draft_path

    def test_reanalyze_api(self, app_and_lib, tmpdir):
        """POST reanalyze → 200 + predecessor_job_id + inherited count."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, draft_path = self._create_done_job_with_manual(client, gml, tmpdir)

        resp = client.post(
            "/api/library/project-relink/reanalyze",
            json={"project_path": draft_path},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["predecessor_job_id"] == job_id
        assert "inherited_bindings" in data
        assert data["job_id"] != job_id

    def test_job_chain_api(self, app_and_lib, tmpdir):
        """GET job-chain → 200 + chain array."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, draft_path = self._create_done_job_with_manual(client, gml, tmpdir, suffix="_chain")

        # Reanalyze to create a chain
        client.post(
            "/api/library/project-relink/reanalyze",
            json={"project_path": draft_path},
        )

        resp = client.get(f"/api/library/project-relink/job-chain?project_path={draft_path}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "chain" in data
        assert len(data["chain"]) >= 2

    def test_verify_api(self, app_and_lib, tmpdir):
        """POST verify → 200 + all_valid + stale_count."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, draft_path = self._create_done_job_with_manual(client, gml, tmpdir, suffix="_verify")

        resp = client.post(f"/api/library/project-relink/{job_id}/verify")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "all_valid" in data
        assert "stale_count" in data
        assert "verified" in data

    def test_handover_api(self, app_and_lib, tmpdir):
        """POST handover → 200 + report with closure_status."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, draft_path = self._create_done_job_with_manual(client, gml, tmpdir, suffix="_ho")

        resp = client.post(
            f"/api/library/project-relink/{job_id}/handover",
            json={"auto_verify": True},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "report" in data
        report = data["report"]
        assert "closure_status" in report
        assert "resolution_summary" in report

    def test_export_handover_api(self, app_and_lib, tmpdir):
        """GET export-handover → 200 + content."""
        app, gml = app_and_lib
        client = app.test_client()

        job_id, draft_path = self._create_done_job_with_manual(client, gml, tmpdir, suffix="_exp")

        # Generate handover first
        client.post(
            f"/api/library/project-relink/{job_id}/handover",
            json={"auto_verify": True},
        )

        # Export JSON
        resp_json = client.get(f"/api/library/project-relink/{job_id}/export-handover?format=json")
        assert resp_json.status_code == 200
        data_json = resp_json.get_json()
        assert "report" in data_json
        assert "filename" in data_json

        # Export Markdown — returns text/markdown, not JSON
        resp_md = client.get(f"/api/library/project-relink/{job_id}/export-handover?format=markdown")
        assert resp_md.status_code == 200
        assert resp_md.content_type.startswith("text/markdown")
        md_text = resp_md.data.decode("utf-8")
        assert "# 工程 Relink 交接报告" in md_text
