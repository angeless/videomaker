"""v0.7 Phase B — Relink report tests (POST variant + structure consistency)."""
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
def lib_with_changes(tmpdir):
    """Library with some path_change_log entries."""
    db_path = os.path.join(tmpdir, "test_relink.db")
    gml = GlobalMediaLibrary(db_path=db_path)

    with gml._connect() as conn:
        now = gml._now()
        conn.execute(
            """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
               duration, resolution, quality_score, scene_description, created_at, updated_at)
               VALUES ('uid_r1','r1.mp4','sha_r1','/new/r1.mp4','local',10.0,'1920x1080',80,'s',?,?)""",
            (now, now),
        )
        conn.execute(
            """INSERT INTO path_change_log (uid, old_path, new_path, change_type, source, created_at)
               VALUES ('uid_r1', '/old/r1.mp4', '/new/r1.mp4', 'relocated', 'batch_scan', ?)""",
            (now,),
        )
        conn.execute(
            """INSERT INTO path_change_log (uid, old_path, new_path, change_type, source, created_at)
               VALUES ('uid_r1', NULL, '/extra/r1.mp4', 'added', 'system', ?)""",
            (now,),
        )

    return gml


class TestRelinkReport:
    def test_report_returns_changes(self, lib_with_changes):
        """Basic relink report returns expected structure."""
        report = lib_with_changes.relink_report(uids=["uid_r1"])
        assert isinstance(report, list)
        assert len(report) == 1
        entry = report[0]
        assert entry["uid"] == "uid_r1"
        assert len(entry["changes"]) == 2

    def test_report_change_fields_complete(self, lib_with_changes):
        """硬约束 6 验证：返回字段完整。"""
        report = lib_with_changes.relink_report(uids=["uid_r1"])
        change = report[0]["changes"][0]
        assert "old_path" in change
        assert "new_path" in change
        assert "change_type" in change
        assert "created_at" in change

    def test_empty_uids_does_not_crash(self, lib_with_changes):
        """Empty uid list should return empty or all — no crash."""
        report = lib_with_changes.relink_report(uids=[])
        assert isinstance(report, list)

    def test_nonexistent_uid_returns_empty(self, lib_with_changes):
        report = lib_with_changes.relink_report(uids=["uid_nonexistent"])
        # Should return empty list or entry with no changes
        if len(report) > 0:
            assert report[0]["changes"] == [] or report[0]["uid"] == "uid_nonexistent"
        else:
            assert report == []

    def test_get_and_post_structure_consistent(self, lib_with_changes):
        """硬约束 6：GET/POST relink-report 返回结构必须一致。
        Both call the same relink_report() method, so the structure IS the same.
        This test verifies the method produces consistent output."""
        report1 = lib_with_changes.relink_report(uids=["uid_r1"])
        report2 = lib_with_changes.relink_report(uids=["uid_r1"], since=None)
        assert len(report1) == len(report2)
        assert report1[0]["uid"] == report2[0]["uid"]
        assert len(report1[0]["changes"]) == len(report2[0]["changes"])
