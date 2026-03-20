"""v0.7 Phase B — Location health + unavailable assets tests."""
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
def lib_with_locations(tmpdir):
    """Library with assets having mixed availability."""
    db_path = os.path.join(tmpdir, "test_loc.db")
    gml = GlobalMediaLibrary(db_path=db_path)

    with gml._connect() as conn:
        now = gml._now()
        for uid, fname, sha in [
            ("uid_ok", "ok.mp4", "sha_ok"),
            ("uid_miss", "miss.mp4", "sha_miss"),
            ("uid_miss2", "miss2.mp4", "sha_miss2"),
        ]:
            conn.execute(
                """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
                   duration, resolution, quality_score, scene_description, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, fname, sha, f"/media/{fname}", "local", 10.0, "1920x1080", 80, "scene", now, now),
            )

        # uid_ok is available
        conn.execute(
            """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
               VALUES ('uid_ok', '/media/ok.mp4', 'local', 1, ?)""", (now,),
        )
        # uid_miss is unavailable
        conn.execute(
            """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
               VALUES ('uid_miss', '/old/miss.mp4', 'local', 0, ?)""", (now,),
        )
        # uid_miss2 is also unavailable
        conn.execute(
            """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
               VALUES ('uid_miss2', '/old/miss2.mp4', 'local', 0, ?)""", (now,),
        )

    return gml


class TestUnavailableAssets:
    def test_list_returns_unavailable_only(self, lib_with_locations):
        result = lib_with_locations.list_unavailable_assets()
        uids = [r["uid"] for r in result]
        assert "uid_miss" in uids
        assert "uid_miss2" in uids
        assert "uid_ok" not in uids

    def test_list_includes_filename(self, lib_with_locations):
        """Verify JOIN with assets table works correctly."""
        result = lib_with_locations.list_unavailable_assets()
        for r in result:
            assert "filename" in r
            assert r["filename"] is not None

    def test_list_includes_primary_path(self, lib_with_locations):
        result = lib_with_locations.list_unavailable_assets()
        for r in result:
            assert "primary_path" in r

    def test_empty_when_all_available(self, tmpdir):
        db_path = os.path.join(tmpdir, "test_all_avail.db")
        gml = GlobalMediaLibrary(db_path=db_path)
        with gml._connect() as conn:
            now = gml._now()
            conn.execute(
                """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
                   duration, resolution, quality_score, scene_description, created_at, updated_at)
                   VALUES ('u1','f.mp4','s1','/f.mp4','local',10.0,'1920x1080',80,'s',?,?)""",
                (now, now),
            )
            conn.execute(
                "INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at) VALUES ('u1','/f.mp4','local',1,?)",
                (now,),
            )
        assert gml.list_unavailable_assets() == []
