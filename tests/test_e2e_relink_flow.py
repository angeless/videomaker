"""E2E flow test — Project Relink lifecycle.

Exercises the full relink user journey:
  analyze project → inspect items → manual bind → preview apply → apply → export → history
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conftest import GlobalMediaLibrary, _make_app


def _write_draft(path, videos=None, audios=None):
    """Create a minimal Jianying draft_content.json."""
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
def relink_tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def relink_setup(relink_tmpdir):
    """Library + draft project with one matching and one missing asset."""
    db_path = os.path.join(relink_tmpdir, "relink_e2e.db")
    gml = GlobalMediaLibrary(db_path=db_path)
    now = gml._now()

    # Seed library with known asset (new path)
    new_path = os.path.join(relink_tmpdir, "media", "clip_x.mp4")
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    with open(new_path, "wb") as f:
        f.write(b"\x00" * 1024)

    with gml._connect() as conn:
        conn.execute(
            """INSERT INTO assets
               (uid, filename, sha256, primary_path, source_type,
                duration, resolution, quality_score, scene_description,
                size_bytes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "uid_x", "clip_x.mp4", "sha_xxx", new_path, "local",
                10.0, "1920x1080", 80, "scene_x",
                50000, now, now,
            ),
        )
        conn.execute(
            """INSERT INTO asset_locations
               (uid, path, source_type, is_available, last_seen_at)
               VALUES (?,?,?,?,?)""",
            ("uid_x", new_path, "local", 1, now),
        )

    # Create draft referencing old path (will be detected as changed)
    project_dir = os.path.join(relink_tmpdir, "project")
    draft_path = os.path.join(project_dir, "draft_content.json")
    _write_draft(
        draft_path,
        videos=[
            {"id": "v1", "path": "/old/clip_x.mp4"},
            {"id": "v2", "path": "/missing/gone.mp4"},
        ],
    )

    app = _make_app(gml)
    # project_path should be the draft file, matching existing test patterns
    return app, gml, draft_path


@pytest.fixture()
def relink_client(relink_setup):
    app, _, _ = relink_setup
    return app.test_client()


class TestE2ERelinkFlow:
    """Full project relink lifecycle via API."""

    def test_full_relink_lifecycle(self, relink_setup):
        """analyze → items → bind → preview → apply → export."""
        app, gml, project_dir = relink_setup
        client = app.test_client()

        # 1. Analyze
        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": project_dir, "project_type": "jianying"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") or data.get("job_id")
        job_id = data["job_id"]

        # 2. Fetch job — check items (response wraps in {"job": ...})
        resp2 = client.get(f"/api/library/project-relink/{job_id}")
        assert resp2.status_code == 200
        job = resp2.get_json()["job"]
        items = job.get("items", [])
        assert len(items) >= 1

        # Find a missing/unmatched item to bind
        bindable = [i for i in items if i["status"] in ("missing", "unmatched")]
        if bindable:
            item_id = bindable[0]["item_id"]

            # 3. Manual bind
            resp3 = client.post(
                f"/api/library/project-relink/item/{item_id}/bind",
                json={"uid": "uid_x"},
                content_type="application/json",
            )
            assert resp3.status_code == 200

        # 4. Preview apply
        resp4 = client.get(f"/api/library/project-relink/{job_id}/preview-apply")
        assert resp4.status_code == 200
        preview = resp4.get_json()
        assert "diff_items" in preview or "diff" in preview or "preview" in preview

        # 5. Apply
        resp5 = client.post(
            f"/api/library/project-relink/{job_id}/apply",
            json={"force": True},
            content_type="application/json",
        )
        assert resp5.status_code == 200

        # 6. Export
        resp6 = client.get(f"/api/library/project-relink/{job_id}/export")
        assert resp6.status_code == 200

    def test_relink_appears_in_history(self, relink_setup):
        """After analysis, the job appears in the history list."""
        app, _, project_dir = relink_setup
        client = app.test_client()

        # Analyze
        resp = client.post(
            "/api/library/project-relink",
            json={"project_path": project_dir, "project_type": "jianying"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        job_id = resp.get_json()["job_id"]

        # List
        resp2 = client.get("/api/library/project-relink/list")
        assert resp2.status_code == 200
        jobs = resp2.get_json().get("jobs", [])
        job_ids = [j["job_id"] for j in jobs]
        assert job_id in job_ids
