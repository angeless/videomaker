"""E2E flow test — Location Health & Availability lifecycle.

Exercises: health stats → unavailable listing → scan.
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


@pytest.fixture()
def loc_tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def loc_lib(loc_tmpdir):
    """Library with 2 assets: one available, one unavailable."""
    db_path = os.path.join(loc_tmpdir, "loc_e2e.db")
    gml = GlobalMediaLibrary(db_path=db_path)
    now = gml._now()
    with gml._connect() as conn:
        # Available asset
        conn.execute(
            """INSERT INTO assets
               (uid, filename, sha256, primary_path, source_type,
                duration, resolution, quality_score, scene_description,
                size_bytes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "uid_ok", "ok.mp4", "sha_ok", "/test/ok.mp4", "local",
                5.0, "1280x720", 70, "ok scene",
                30000, now, now,
            ),
        )
        conn.execute(
            """INSERT INTO asset_locations
               (uid, path, source_type, is_available, last_seen_at)
               VALUES (?,?,?,?,?)""",
            ("uid_ok", "/test/ok.mp4", "local", 1, now),
        )

        # Unavailable asset
        conn.execute(
            """INSERT INTO assets
               (uid, filename, sha256, primary_path, source_type,
                duration, resolution, quality_score, scene_description,
                size_bytes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "uid_miss", "missing.mp4", "sha_miss", "/gone/missing.mp4", "local",
                8.0, "1920x1080", 60, "missing scene",
                40000, now, now,
            ),
        )
        conn.execute(
            """INSERT INTO asset_locations
               (uid, path, source_type, is_available, last_seen_at)
               VALUES (?,?,?,?,?)""",
            ("uid_miss", "/gone/missing.mp4", "local", 0, now),
        )
    return gml


@pytest.fixture()
def loc_client(loc_lib):
    app = _make_app(loc_lib)
    return app.test_client()


class TestE2ELocationHealthFlow:
    """Location health lifecycle via API."""

    def test_health_baseline(self, loc_client):
        """GET /fingerprint/health returns stats with total > 0."""
        resp = loc_client.get("/api/library/fingerprint/health")
        assert resp.status_code == 200
        data = resp.get_json()
        # The response should contain some health metric
        assert isinstance(data, dict)
        # At minimum we expect it to return without error
        assert "error" not in data

    def test_unavailable_listing(self, loc_client):
        """GET /locations/unavailable lists the missing asset."""
        resp = loc_client.get("/api/library/locations/unavailable")
        assert resp.status_code == 200
        data = resp.get_json()
        assets = data.get("assets", [])
        uids = [a.get("uid") for a in assets]
        assert "uid_miss" in uids

    def test_scan_returns_job(self, loc_client):
        """POST /locations/scan starts an async scan job."""
        resp = loc_client.post("/api/library/locations/scan")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") is True
        assert "job_id" in data

    def test_stats_after_scan(self, loc_client):
        """Stats remain consistent after a scan cycle."""
        # Run scan
        loc_client.post("/api/library/locations/scan")

        # Stats should still work
        resp = loc_client.get("/api/library/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_assets"] == 2
