"""v0.7 Phase B — Duplicate resolution + member decision tests.

Tests:
  - resolve/ignore duplicate groups
  - set primary uid
  - set member keep/remove decisions
  - status filtering
  - list_unavailable_assets
"""
import os
import sys
import shutil
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import importlib
importlib.import_module("modules")
importlib.import_module("modules.library")
mod = importlib.import_module("modules.library.global_media_library")
mod = importlib.reload(mod)
GlobalMediaLibrary = mod.GlobalMediaLibrary


@pytest.fixture()
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def lib_with_groups(tmpdir):
    """Library with 2 assets + 1 duplicate group having 2 members."""
    db_path = os.path.join(tmpdir, "test_b.db")
    gml = GlobalMediaLibrary(db_path=db_path)

    with gml._connect() as conn:
        now = gml._now()
        for uid, fname, sha in [
            ("uid_x", "x.mp4", "sha_xxx"),
            ("uid_y", "y.mp4", "sha_yyy"),
        ]:
            conn.execute(
                """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
                   duration, resolution, quality_score, scene_description, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, fname, sha, f"/media/{fname}", "local", 10.0, "1920x1080", 80, "scene", now, now),
            )

        conn.execute(
            """INSERT INTO duplicate_group (group_type, primary_uid, member_count, total_size_bytes, status)
               VALUES ('exact_sha', 'uid_x', 2, 30000, 'pending')""",
        )
        group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO duplicate_group_member (group_id, uid, fingerprint_distance, file_size) VALUES (?,?,?,?)",
            (group_id, "uid_x", 0, 10000),
        )
        conn.execute(
            "INSERT INTO duplicate_group_member (group_id, uid, fingerprint_distance, file_size) VALUES (?,?,?,?)",
            (group_id, "uid_y", 0, 20000),
        )

    return gml, group_id


class TestDuplicateResolution:
    def test_resolve_sets_status(self, lib_with_groups):
        gml, gid = lib_with_groups
        result = gml.resolve_duplicate_group(gid)
        assert result.get("ok") is True
        assert result["status"] == "resolved"
        # verify in DB
        groups = gml.list_duplicate_groups(status="resolved")
        assert any(g["group_id"] == gid for g in groups)

    def test_resolve_sets_resolved_at(self, lib_with_groups):
        gml, gid = lib_with_groups
        gml.resolve_duplicate_group(gid)
        with gml._connect() as conn:
            row = conn.execute("SELECT resolved_at FROM duplicate_group WHERE group_id=?", (gid,)).fetchone()
            assert row["resolved_at"] is not None

    def test_resolve_nonexistent_returns_error(self, lib_with_groups):
        gml, _ = lib_with_groups
        result = gml.resolve_duplicate_group(99999)
        assert "error" in result

    def test_ignore_sets_status(self, lib_with_groups):
        gml, gid = lib_with_groups
        result = gml.ignore_duplicate_group(gid)
        assert result.get("ok") is True
        assert result["status"] == "ignored"

    def test_resolved_excluded_from_pending(self, lib_with_groups):
        gml, gid = lib_with_groups
        gml.resolve_duplicate_group(gid)
        pending = gml.list_duplicate_groups(status="pending")
        assert not any(g["group_id"] == gid for g in pending)

    def test_set_primary_updates_uid(self, lib_with_groups):
        gml, gid = lib_with_groups
        result = gml.set_duplicate_primary(gid, "uid_y")
        assert result.get("ok") is True
        assert result["primary_uid"] == "uid_y"
        # verify
        groups = gml.list_duplicate_groups()
        g = [x for x in groups if x["group_id"] == gid][0]
        assert g["primary_uid"] == "uid_y"

    def test_set_primary_invalid_uid(self, lib_with_groups):
        gml, gid = lib_with_groups
        result = gml.set_duplicate_primary(gid, "uid_nonexistent")
        assert "error" in result

    def test_set_member_decision_keep(self, lib_with_groups):
        gml, gid = lib_with_groups
        # Get member id
        groups = gml.list_duplicate_groups()
        g = [x for x in groups if x["group_id"] == gid][0]
        member_id = g["members"][0]["id"]
        result = gml.set_member_decision(gid, member_id, "keep")
        assert result.get("ok") is True
        assert result["decision"] == "keep"

    def test_set_member_decision_remove(self, lib_with_groups):
        gml, gid = lib_with_groups
        groups = gml.list_duplicate_groups()
        g = [x for x in groups if x["group_id"] == gid][0]
        member_id = g["members"][1]["id"]
        result = gml.set_member_decision(gid, member_id, "remove")
        assert result.get("ok") is True
        assert result["decision"] == "remove"

    def test_set_member_decision_invalid(self, lib_with_groups):
        gml, gid = lib_with_groups
        groups = gml.list_duplicate_groups()
        g = [x for x in groups if x["group_id"] == gid][0]
        member_id = g["members"][0]["id"]
        result = gml.set_member_decision(gid, member_id, "destroy")
        assert "error" in result

    def test_decision_persists_after_refresh(self, lib_with_groups):
        """硬约束 2 验证：操作后刷新数据一致。"""
        gml, gid = lib_with_groups
        groups = gml.list_duplicate_groups()
        g = [x for x in groups if x["group_id"] == gid][0]
        mid = g["members"][0]["id"]
        gml.set_member_decision(gid, mid, "keep")
        # Re-query
        groups2 = gml.list_duplicate_groups()
        g2 = [x for x in groups2 if x["group_id"] == gid][0]
        m2 = [m for m in g2["members"] if m["id"] == mid][0]
        assert m2["keep_decision"] == "keep"
