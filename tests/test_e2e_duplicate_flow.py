"""E2E flow test — Duplicate Detection & Resolution lifecycle.

Exercises: detect duplicates → list groups → set primary → resolve / ignore.
Uses content_fingerprint similarity (Phase 2 detection) since sha256 has UNIQUE constraint.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conftest import GlobalMediaLibrary, _make_app


@pytest.fixture()
def dup_tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def dup_lib(dup_tmpdir):
    """Library with 2 assets having identical content_fingerprint (near-duplicates)."""
    db_path = os.path.join(dup_tmpdir, "dup_e2e.db")
    gml = GlobalMediaLibrary(db_path=db_path)
    now = gml._now()
    # Use a hex fingerprint string (content_fingerprint is a hex-encoded hash)
    SHARED_FP = "a" * 64  # 64-char hex → hamming distance = 0 → exact content match
    with gml._connect() as conn:
        for uid, fname, sha in [
            ("uid_d1", "dup_one.mp4", "sha_dup_one"),
            ("uid_d2", "dup_two.mp4", "sha_dup_two"),
        ]:
            conn.execute(
                """INSERT INTO assets
                   (uid, filename, sha256, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    size_bytes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid, fname, sha, f"/test/{fname}", "local",
                    15.0, "1920x1080", 75, "dup scene",
                    100000, now, now,
                ),
            )
            # Set content_fingerprint via UPDATE (column added by migration)
            try:
                conn.execute(
                    "UPDATE assets SET content_fingerprint = ? WHERE uid = ?",
                    (SHARED_FP, uid),
                )
            except Exception:
                pass
            conn.execute(
                """INSERT INTO asset_locations
                   (uid, path, source_type, is_available, last_seen_at)
                   VALUES (?,?,?,?,?)""",
                (uid, f"/test/{fname}", "local", 1, now),
            )
    return gml


@pytest.fixture()
def dup_client(dup_lib):
    app = _make_app(dup_lib)
    return app.test_client()


class TestE2EDuplicateFlow:
    """Full duplicate detection lifecycle via API."""

    def test_detect_and_list(self, dup_client):
        """POST detect → GET duplicates → at least 1 pending group."""
        # Detect
        resp = dup_client.post(
            "/api/library/duplicates/detect",
            json={"threshold": 6},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") or data.get("job_id")

        # List
        resp2 = dup_client.get("/api/library/duplicates")
        assert resp2.status_code == 200
        groups = resp2.get_json().get("groups", [])
        assert len(groups) >= 1

    def test_set_primary_and_resolve(self, dup_client):
        """Set primary → resolve → group status = resolved."""
        # Detect first
        dup_client.post(
            "/api/library/duplicates/detect",
            json={"threshold": 6},
            content_type="application/json",
        )
        groups = dup_client.get("/api/library/duplicates").get_json()["groups"]
        assert len(groups) >= 1
        gid = groups[0]["group_id"]

        # Set primary
        resp = dup_client.post(
            f"/api/library/duplicates/{gid}/primary",
            json={"uid": "uid_d1"},
            content_type="application/json",
        )
        assert resp.status_code == 200

        # Resolve
        resp2 = dup_client.post(f"/api/library/duplicates/{gid}/resolve")
        assert resp2.status_code == 200

        # Verify resolved
        groups_after = dup_client.get("/api/library/duplicates?status=resolved").get_json()["groups"]
        resolved_ids = [g["group_id"] for g in groups_after]
        assert gid in resolved_ids

    def test_ignore_group(self, dup_client):
        """Ignore a group → it no longer appears in pending list."""
        dup_client.post(
            "/api/library/duplicates/detect",
            json={"threshold": 6},
            content_type="application/json",
        )
        groups = dup_client.get("/api/library/duplicates").get_json()["groups"]
        assert len(groups) >= 1
        gid = groups[0]["group_id"]

        # Ignore
        resp = dup_client.post(f"/api/library/duplicates/{gid}/ignore")
        assert resp.status_code == 200

        # Verify: no pending groups left
        groups_after = dup_client.get("/api/library/duplicates?status=pending").get_json()["groups"]
        pending_ids = [g["group_id"] for g in groups_after]
        assert gid not in pending_ids
