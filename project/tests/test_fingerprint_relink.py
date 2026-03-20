"""v0.7 — Fingerprint / Path relocation / Duplicate detection tests.

Covers 4 closed-loop capabilities:
  1. Fingerprint computation + storage (sha256, content_fingerprint, thumbnail_hash)
  2. Path health check + batch relocate (scan_asset_availability, batch_relocate, known_media_roots)
  3. Duplicate detection + grouping (detect_duplicates, duplicate_group)
  4. Path change audit log (path_change_log, relink_report)

Also validates:
  - Schema migration correctness (new tables, columns, indexes)
  - Decoupling: fingerprint ops do NOT touch semantic tables
  - Backward compatibility: existing tests unaffected
"""
import os
import sys
import shutil
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

from modules.step1_material_analysis.indexer.fingerprint import VideoHasher


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture()
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def lib(tmpdir):
    """Create a library with some seeded test assets."""
    db_path = os.path.join(tmpdir, "test_fp.db")
    gml = GlobalMediaLibrary(db_path=db_path)

    with gml._connect() as conn:
        now = gml._now()

        # Insert 4 test assets with varying fingerprint states
        # Use valid hex strings for content_fingerprint (needed for hamming distance computation)
        assets = [
            ("uid_a", "video_a.mp4", "sha_aaa111", "abcdef0123456789", "abcdef0123456789", "ab01cd02", 1, 10000),
            ("uid_b", "video_b.mp4", "sha_bbb222", "abcdef0123456780", "abcdef0123456780", "ab01cd03", 1, 20000),  # cfp distance=2 from uid_a → near_identical
            ("uid_c", "video_c.mp4", "sha_ccc333", "1111111111111111", "1111111111111111", "11111111", 1, 15000),  # very different cfp
            ("uid_d", "image_d.jpg", "sha_ddd444", "2222222222222222", None, None, 0, 5000),  # no fingerprint
        ]

        for uid, fname, sha, phash, cfp, thumb, fp_ver, size in assets:
            conn.execute(
                """INSERT OR IGNORE INTO assets
                   (uid, filename, sha256, phash, content_fingerprint, thumbnail_hash,
                    fingerprint_version, size_bytes, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, fname, sha, phash, cfp, thumb,
                 fp_ver, size, f"/media/{fname}", "local",
                 15.0, "1920x1080", 85, "test scene", now, now),
            )

        # Add location entries
        for uid, fname, *_ in assets:
            conn.execute(
                """INSERT OR IGNORE INTO asset_locations
                   (uid, path, source_type, is_available, last_seen_at)
                   VALUES (?, ?, 'local', 1, ?)""",
                (uid, f"/media/{fname}", now),
            )

    return gml


# ──────────────────────────────────────────────────────────
# Schema migration tests
# ──────────────────────────────────────────────────────────

class TestSchemaMigration:
    """Verify new tables, columns, and indexes are created correctly."""

    def test_new_tables_exist(self, lib):
        import sqlite3
        conn = sqlite3.connect(str(lib.db_path))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()

        for t in ["known_media_roots", "duplicate_group", "duplicate_group_member", "path_change_log"]:
            assert t in tables, f"Missing table: {t}"

    def test_new_asset_columns_exist(self, lib):
        import sqlite3
        conn = sqlite3.connect(str(lib.db_path))
        conn.row_factory = sqlite3.Row
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(assets)").fetchall()}
        conn.close()

        for c in ["content_fingerprint", "thumbnail_hash", "fingerprint_version"]:
            assert c in cols, f"Missing column: {c}"

    def test_new_indexes_exist(self, lib):
        import sqlite3
        conn = sqlite3.connect(str(lib.db_path))
        indexes = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()]
        conn.close()

        expected = [
            "idx_locations_path", "idx_locations_available",
            "idx_dup_member_uid", "idx_dup_member_group",
            "idx_path_change_uid", "idx_path_change_time",
            "idx_assets_content_fp", "idx_assets_phash",
        ]
        for idx in expected:
            assert idx in indexes, f"Missing index: {idx}"

    def test_existing_assets_table_compatible(self, lib):
        """New ALTER TABLE columns don't break existing data."""
        with lib._connect() as conn:
            rows = conn.execute("SELECT uid, sha256, phash FROM assets").fetchall()
            assert len(rows) == 4
            for row in rows:
                assert row["uid"] is not None
                assert row["sha256"] is not None


# ──────────────────────────────────────────────────────────
# Fingerprint computation tests
# ──────────────────────────────────────────────────────────

class TestFingerprintComputation:
    """Test SHA256 determinism, SimHash aggregation, and fingerprint methods."""

    def test_sha256_deterministic(self, tmpdir):
        """Same file content → same sha256 twice."""
        f = Path(tmpdir) / "test.bin"
        f.write_bytes(b"hello world" * 100)
        h1 = GlobalMediaLibrary._compute_sha256(f)
        h2 = GlobalMediaLibrary._compute_sha256(f)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex length

    def test_simhash_aggregate_identical(self):
        """Identical hashes aggregate to the same hash."""
        h = "abcdef0123456789"
        result = VideoHasher.simhash_aggregate([h, h, h, h, h])
        assert result == h

    def test_simhash_aggregate_majority_vote(self):
        """Majority vote: if >50% have a bit set, result has it set."""
        h_all_f = "ffff"
        h_all_0 = "0000"
        # 3 f's vs 2 0's → should be all f's
        result = VideoHasher.simhash_aggregate([h_all_f, h_all_f, h_all_f, h_all_0, h_all_0])
        assert result == h_all_f

    def test_simhash_aggregate_empty(self):
        """Empty hash list → empty string."""
        assert VideoHasher.simhash_aggregate([]) == ""

    def test_content_fingerprint_stored(self, lib):
        """Assets seeded with content_fingerprint are queryable."""
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT content_fingerprint FROM assets WHERE uid='uid_a'"
            ).fetchone()
            assert row["content_fingerprint"] == "abcdef0123456789"

    def test_thumbnail_hash_stored(self, lib):
        """Assets seeded with thumbnail_hash are queryable."""
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT thumbnail_hash FROM assets WHERE uid='uid_a'"
            ).fetchone()
            assert row["thumbnail_hash"] == "ab01cd02"

    def test_fingerprint_version_set(self, lib):
        """Assets with fingerprints have version > 0."""
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT fingerprint_version FROM assets WHERE uid='uid_a'"
            ).fetchone()
            assert row["fingerprint_version"] >= 1

    def test_phash_distance_calculation(self):
        """Hamming distance computation works correctly."""
        assert GlobalMediaLibrary._phash_distance("ffff", "ffff") == 0
        assert GlobalMediaLibrary._phash_distance("ffff", "0000") == 16
        assert GlobalMediaLibrary._phash_distance("ffff", "fffe") == 1
        assert GlobalMediaLibrary._phash_distance(None, "ffff") is None
        assert GlobalMediaLibrary._phash_distance("ff", "ffff") is None


# ──────────────────────────────────────────────────────────
# Path relocation tests
# ──────────────────────────────────────────────────────────

class TestPathRelocation:
    """Test known_media_roots CRUD, availability scanning, and batch relocation."""

    def test_known_roots_crud(self, lib, tmpdir):
        """Register, list, and remove known media roots."""
        root_path = os.path.join(tmpdir, "media_root")
        os.makedirs(root_path, exist_ok=True)

        # Add
        result = lib.add_known_root(root_path, label="Test Media")
        assert "root_path" in result
        assert result["label"] == "Test Media"

        # List
        roots = lib.list_known_roots()
        assert len(roots) >= 1
        root_id = roots[0]["root_id"]

        # Remove (soft delete)
        removed = lib.remove_known_root(root_id)
        assert removed is True

        # Should not appear in active list
        active_roots = lib.list_known_roots(active_only=True)
        assert all(r["root_id"] != root_id for r in active_roots)

        # Should appear in full list
        all_roots = lib.list_known_roots(active_only=False)
        assert any(r["root_id"] == root_id for r in all_roots)

    def test_scan_availability_marks_missing(self, lib):
        """Files that don't exist are marked is_available=0."""
        # All test paths (/media/*) don't actually exist
        result = lib.scan_asset_availability()
        assert result["checked"] == 4
        assert result["unavailable"] == 4
        assert result["changed"] == 4  # All were available, now unavailable

        # Second scan: nothing should change (already marked)
        result2 = lib.scan_asset_availability()
        assert result2["changed"] == 0

    def test_scan_availability_marks_present(self, lib, tmpdir):
        """Files that exist are marked is_available=1."""
        # Create a real file and add a location for it
        real_file = Path(tmpdir) / "real_video.mp4"
        real_file.write_bytes(b"\x00" * 100)

        with lib._connect() as conn:
            conn.execute(
                """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
                   VALUES ('uid_a', ?, 'local', 0, ?)""",
                (str(real_file), lib._now()),
            )

        result = lib.scan_asset_availability()
        assert result["available"] >= 1

    def test_batch_relocate_finds_moved_file(self, tmpdir):
        """Batch relocate finds files that were moved to a new location."""
        # Use a fresh library to avoid state contamination
        db_path = os.path.join(tmpdir, "reloc_test.db")
        lib = GlobalMediaLibrary(db_path=db_path)

        content = b"test video content for relocation"
        import hashlib
        sha = hashlib.sha256(content).hexdigest()

        now = lib._now()
        with lib._connect() as conn:
            conn.execute(
                """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
                   duration, resolution, quality_score, scene_description, created_at, updated_at)
                   VALUES ('uid_reloc', 'video_reloc.mp4', ?, '/old/video_reloc.mp4', 'local',
                   15.0, '1920x1080', 85, 'test', ?, ?)""",
                (sha, now, now),
            )
            conn.execute(
                """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
                   VALUES ('uid_reloc', '/old/video_reloc.mp4', 'local', 0, ?)""",
                (now,),
            )

        new_root = Path(tmpdir) / "new_location"
        new_root.mkdir()
        target_file = new_root / "video_reloc.mp4"
        target_file.write_bytes(content)

        result = lib.batch_relocate(root_paths=[str(new_root)])
        assert result["attempted"] >= 1
        assert result["relocated"] >= 1
        assert len(result["details"]) >= 1

    def test_relocated_path_updates_primary(self, tmpdir):
        """After relocation, primary_path is updated."""
        db_path = os.path.join(tmpdir, "reloc_primary.db")
        lib = GlobalMediaLibrary(db_path=db_path)

        content = b"unique relocatable content"
        import hashlib
        sha = hashlib.sha256(content).hexdigest()

        now = lib._now()
        with lib._connect() as conn:
            conn.execute(
                """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
                   duration, resolution, quality_score, scene_description, created_at, updated_at)
                   VALUES ('uid_prim', 'video_prim.mp4', ?, '/old/video_prim.mp4', 'local',
                   15.0, '1920x1080', 85, 'test', ?, ?)""",
                (sha, now, now),
            )
            conn.execute(
                """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
                   VALUES ('uid_prim', '/old/video_prim.mp4', 'local', 0, ?)""",
                (now,),
            )

        new_root = Path(tmpdir) / "reloc_prim_dir"
        new_root.mkdir()
        (new_root / "video_prim.mp4").write_bytes(content)

        lib.batch_relocate(root_paths=[str(new_root)])

        with lib._connect() as conn:
            row = conn.execute("SELECT primary_path FROM assets WHERE uid='uid_prim'").fetchone()
            assert str(new_root) in (row["primary_path"] or "")


# ──────────────────────────────────────────────────────────
# Duplicate detection tests
# ──────────────────────────────────────────────────────────

class TestDuplicateDetection:
    """Test duplicate detection and grouping."""

    def test_near_identical_grouped(self, lib):
        """Assets with same content_fingerprint are grouped."""
        # uid_a and uid_b have cfp = "cfp_a1" (same)
        result = lib.detect_duplicates(threshold=6)
        assert result["groups_found"] >= 1

    def test_duplicate_group_has_members(self, lib):
        """Duplicate groups contain correct members."""
        lib.detect_duplicates(threshold=6)
        groups = lib.list_duplicate_groups(status="pending")

        # Find group containing uid_a
        found = False
        for g in groups:
            member_uids = [m["uid"] for m in g["members"]]
            if "uid_a" in member_uids and "uid_b" in member_uids:
                found = True
                assert g["member_count"] >= 2
                break
        assert found, "Expected group containing uid_a and uid_b not found"

    def test_no_false_positive_different_content(self, lib):
        """Assets with very different fingerprints are NOT grouped together."""
        lib.detect_duplicates(threshold=6)
        groups = lib.list_duplicate_groups(status="pending")

        # uid_c has cfp_c_different — should NOT be grouped with uid_a/uid_b
        # (assuming cfp_a1 and cfp_c_different are truly different)
        for g in groups:
            member_uids = [m["uid"] for m in g["members"]]
            if "uid_a" in member_uids or "uid_b" in member_uids:
                assert "uid_c" not in member_uids, "uid_c should not be in same group as uid_a/uid_b"

    def test_duplicate_group_total_size(self, lib):
        """Total size in duplicate group is sum of member sizes."""
        lib.detect_duplicates(threshold=6)
        groups = lib.list_duplicate_groups(status="pending")

        for g in groups:
            member_sizes = sum(m.get("file_size") or 0 for m in g["members"])
            assert g["total_size_bytes"] == member_sizes

    def test_detect_clears_previous_pending(self, lib):
        """Re-running detect clears old pending groups."""
        r1 = lib.detect_duplicates(threshold=6)
        r2 = lib.detect_duplicates(threshold=6)
        # Should not accumulate groups
        assert r2["groups_found"] == r1["groups_found"]


# ──────────────────────────────────────────────────────────
# Path change audit log tests
# ──────────────────────────────────────────────────────────

class TestPathChangeLog:
    """Test path change logging and relink report."""

    def test_path_change_logged_on_scan(self, lib):
        """scan_asset_availability logs changes."""
        # Reset: mark all available
        with lib._connect() as conn:
            conn.execute("UPDATE asset_locations SET is_available=1")
            conn.execute("DELETE FROM path_change_log")

        # Scan — paths don't exist, so they go unavailable
        lib.scan_asset_availability()

        with lib._connect() as conn:
            logs = conn.execute("SELECT * FROM path_change_log").fetchall()
            assert len(logs) >= 1
            types = [l["change_type"] for l in logs]
            assert "unavailable" in types

    def test_path_change_logged_on_relocate(self, tmpdir):
        """batch_relocate logs path changes."""
        db_path = os.path.join(tmpdir, "reloc_log.db")
        lib = GlobalMediaLibrary(db_path=db_path)

        content = b"log test relocatable"
        import hashlib
        sha = hashlib.sha256(content).hexdigest()

        now = lib._now()
        with lib._connect() as conn:
            conn.execute(
                """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
                   duration, resolution, quality_score, scene_description, created_at, updated_at)
                   VALUES ('uid_log', 'video_log.mp4', ?, '/old/video_log.mp4', 'local',
                   15.0, '1920x1080', 85, 'test', ?, ?)""",
                (sha, now, now),
            )
            conn.execute(
                """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
                   VALUES ('uid_log', '/old/video_log.mp4', 'local', 0, ?)""",
                (now,),
            )

        new_root = Path(tmpdir) / "relink_log_test"
        new_root.mkdir()
        (new_root / "video_log.mp4").write_bytes(content)

        lib.batch_relocate(root_paths=[str(new_root)])

        with lib._connect() as conn:
            logs = conn.execute(
                "SELECT * FROM path_change_log WHERE uid='uid_log' AND change_type='relocated'"
            ).fetchall()
            assert len(logs) >= 1

    def test_relink_report_returns_changes(self, lib):
        """relink_report returns path change history."""
        # Trigger some changes
        with lib._connect() as conn:
            conn.execute("UPDATE asset_locations SET is_available=1")
            conn.execute("DELETE FROM path_change_log")

        lib.scan_asset_availability()

        report = lib.relink_report(uids=["uid_a"])
        assert len(report) >= 1
        assert report[0]["uid"] == "uid_a"
        assert len(report[0]["changes"]) >= 1

    def test_relink_report_empty_for_stable(self, lib):
        """Assets with no changes return empty report."""
        with lib._connect() as conn:
            conn.execute("DELETE FROM path_change_log")

        report = lib.relink_report(uids=["uid_nonexistent"])
        assert report == []


# ──────────────────────────────────────────────────────────
# Backfill and fingerprint health tests
# ──────────────────────────────────────────────────────────

class TestBackfillAndHealth:
    """Test fingerprint backfill and health stats."""

    def test_backfill_skips_missing_files(self, lib):
        """Backfill skips assets whose primary_path doesn't exist."""
        # uid_d has no fingerprint but path doesn't exist
        result = lib.backfill_fingerprints()
        # Should process uid_d (no fingerprint) but skip it (file not found)
        assert result["skipped"] >= 1

    def test_fingerprint_health_structure(self, lib):
        """get_fingerprint_health returns correct structure."""
        health = lib.get_fingerprint_health()
        expected_keys = [
            "total_assets", "with_content_fingerprint", "with_thumbnail_hash",
            "with_phash", "fingerprint_coverage_pct", "current_version_count",
            "fingerprint_version", "needs_backfill", "duplicate_groups",
            "pending_duplicate_groups", "known_roots_active", "total_path_changes",
        ]
        for key in expected_keys:
            assert key in health, f"Missing key: {key}"

    def test_fingerprint_coverage_pct_consistent(self, lib):
        """Coverage percentage matches actual counts."""
        health = lib.get_fingerprint_health()
        total = health["total_assets"]
        if total > 0:
            expected_pct = round(health["with_content_fingerprint"] / total * 100, 1)
            assert health["fingerprint_coverage_pct"] == expected_pct


# ──────────────────────────────────────────────────────────
# Decoupling tests
# ──────────────────────────────────────────────────────────

class TestDecoupling:
    """Verify fingerprint operations don't touch semantic tables."""

    def test_fingerprint_does_not_touch_semantic_tables(self, lib):
        """Fingerprint/path/dedup operations don't write to semantic tables."""
        with lib._connect() as conn:
            # Snapshot semantic tables before
            tag_count_before = conn.execute("SELECT COUNT(*) FROM asset_tag_result").fetchone()[0]
            evidence_count_before = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

        # Run all fingerprint/path/dedup operations
        lib.scan_asset_availability()
        lib.detect_duplicates()
        lib.backfill_fingerprints()
        lib.relink_report()

        with lib._connect() as conn:
            # Snapshot after
            tag_count_after = conn.execute("SELECT COUNT(*) FROM asset_tag_result").fetchone()[0]
            evidence_count_after = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

        assert tag_count_before == tag_count_after, "Fingerprint ops modified asset_tag_result!"
        assert evidence_count_before == evidence_count_after, "Fingerprint ops modified evidence!"


# ──────────────────────────────────────────────────────────
# Constraint enforcement tests
# ──────────────────────────────────────────────────────────

class TestConstraintEnforcement:
    """
    Verify the 4 execution constraints:
    C1: detect_duplicates uses coarse→fine (thumbnail pre-filter → distance calc)
    C2: batch_relocate updates primary_path + path_change_log on sha256 match
    C3: content_fingerprint similar hit does NOT auto-relink primary_path
    C4: API returns all 5 required observable data points
    """

    def test_c1_detect_duplicates_uses_coarse_fine(self, lib):
        """
        C1: detect_duplicates must use thumbnail_hash as coarse pre-filter
        before content_fingerprint distance calculation.
        Verify by ensuring assets with very different thumbnails are NOT grouped
        even if they accidentally have close content_fingerprints.
        """
        with lib._connect() as conn:
            now = lib._now()
            # Insert two assets with SAME content_fingerprint but very different thumbnails
            conn.execute(
                """INSERT OR REPLACE INTO assets
                   (uid, filename, sha256, phash, content_fingerprint, thumbnail_hash,
                    fingerprint_version, size_bytes, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    created_at, updated_at)
                   VALUES ('uid_cf_same1', 'same1.mp4', 'sha_cf1', 'aaaa', 'aabbccdd11223344', '0000000000000000',
                    1, 10000, '/test/same1.mp4', 'local', 10, '1920x1080', 80, 'test', ?, ?)""",
                (now, now),
            )
            conn.execute(
                """INSERT OR REPLACE INTO assets
                   (uid, filename, sha256, phash, content_fingerprint, thumbnail_hash,
                    fingerprint_version, size_bytes, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    created_at, updated_at)
                   VALUES ('uid_cf_same2', 'same2.mp4', 'sha_cf2', 'bbbb', 'aabbccdd11223345', 'ffffffffffffffff',
                    1, 10000, '/test/same2.mp4', 'local', 10, '1920x1080', 80, 'test', ?, ?)""",
                (now, now),
            )

        # threshold=6 → coarse cutoff = 12
        # thumbnail distance = 64 (all bits differ) >> 12, so coarse filter should skip
        result = lib.detect_duplicates(threshold=6)
        groups = lib.list_duplicate_groups(status="pending")

        for g in groups:
            member_uids = {m["uid"] for m in g["members"]}
            if "uid_cf_same1" in member_uids:
                assert "uid_cf_same2" not in member_uids, \
                    "C1 violated: coarse thumbnail filter should have excluded this pair"

    def test_c2_batch_relocate_updates_primary_path_and_log(self, tmpdir):
        """
        C2: Successful sha256-based relocation MUST:
        (a) update assets.primary_path
        (b) write to path_change_log
        Incomplete without both.
        """
        db_path = os.path.join(tmpdir, "c2_test.db")
        lib = GlobalMediaLibrary(db_path=db_path)

        import hashlib
        content = b"c2 test content"
        sha = hashlib.sha256(content).hexdigest()
        now = lib._now()

        with lib._connect() as conn:
            conn.execute(
                """INSERT INTO assets (uid, filename, sha256, primary_path, source_type,
                   duration, resolution, quality_score, scene_description, created_at, updated_at)
                   VALUES ('uid_c2', 'c2.mp4', ?, '/old/c2.mp4', 'local',
                   15.0, '1920x1080', 85, 'test', ?, ?)""",
                (sha, now, now),
            )
            conn.execute(
                """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
                   VALUES ('uid_c2', '/old/c2.mp4', 'local', 0, ?)""",
                (now,),
            )

        new_root = Path(tmpdir) / "c2_root"
        new_root.mkdir()
        (new_root / "c2.mp4").write_bytes(content)

        lib.batch_relocate(root_paths=[str(new_root)])

        with lib._connect() as conn:
            # (a) primary_path must be updated
            row = conn.execute("SELECT primary_path FROM assets WHERE uid='uid_c2'").fetchone()
            assert row["primary_path"] is not None
            assert str(new_root) in row["primary_path"], \
                f"C2 violated: primary_path not updated. Got: {row['primary_path']}"

            # (b) path_change_log must have entry
            logs = conn.execute(
                "SELECT * FROM path_change_log WHERE uid='uid_c2' AND change_type='relocated'"
            ).fetchall()
            assert len(logs) >= 1, "C2 violated: no path_change_log entry for relocation"
            assert logs[0]["new_path"] is not None
            assert logs[0]["old_path"] == "/old/c2.mp4"

    def test_c3_fingerprint_similarity_does_not_auto_relink(self, tmpdir):
        """
        C3: content_fingerprint similarity must NOT auto-update primary_path.
        Only sha256 exact match may auto-relink.
        batch_relocate must only use sha256 for matching.
        """
        db_path = os.path.join(tmpdir, "c3_test.db")
        lib = GlobalMediaLibrary(db_path=db_path)
        now = lib._now()

        with lib._connect() as conn:
            # Asset with unavailable path, has a content_fingerprint
            conn.execute(
                """INSERT INTO assets (uid, filename, sha256, content_fingerprint, primary_path,
                   source_type, duration, resolution, quality_score, scene_description,
                   created_at, updated_at)
                   VALUES ('uid_c3', 'c3.mp4', 'sha_c3_unique', 'aabbccdd11223344', '/missing/c3.mp4',
                   'local', 15.0, '1920x1080', 85, 'test', ?, ?)""",
                (now, now),
            )
            conn.execute(
                """INSERT INTO asset_locations (uid, path, source_type, is_available, last_seen_at)
                   VALUES ('uid_c3', '/missing/c3.mp4', 'local', 0, ?)""",
                (now,),
            )

        # Create a file in a search root that has DIFFERENT sha256 but would have
        # similar content_fingerprint if someone tried to use it
        new_root = Path(tmpdir) / "c3_root"
        new_root.mkdir()
        different_file = new_root / "c3.mp4"
        different_file.write_bytes(b"different content that would not sha256-match")

        old_primary = "/missing/c3.mp4"
        lib.batch_relocate(root_paths=[str(new_root)])

        with lib._connect() as conn:
            row = conn.execute("SELECT primary_path FROM assets WHERE uid='uid_c3'").fetchone()
            # primary_path must NOT have been changed because sha256 doesn't match
            assert row["primary_path"] == old_primary, \
                f"C3 violated: primary_path was changed without sha256 match! Got: {row['primary_path']}"

    def test_c4_api_observable_fingerprint_coverage(self, lib):
        """C4: get_fingerprint_health returns fingerprint coverage percentage."""
        health = lib.get_fingerprint_health()
        assert "fingerprint_coverage_pct" in health
        assert "with_content_fingerprint" in health
        assert "total_assets" in health
        assert isinstance(health["fingerprint_coverage_pct"], (int, float))

    def test_c4_api_observable_unavailable_paths(self, lib):
        """C4: scan_asset_availability returns unavailable path count."""
        result = lib.scan_asset_availability()
        assert "unavailable" in result
        assert isinstance(result["unavailable"], int)

    def test_c4_api_observable_relocated_count(self, tmpdir):
        """C4: batch_relocate returns relocated count."""
        db_path = os.path.join(tmpdir, "c4_reloc.db")
        lib = GlobalMediaLibrary(db_path=db_path)
        result = lib.batch_relocate()
        assert "relocated" in result
        assert isinstance(result["relocated"], int)

    def test_c4_api_observable_duplicate_groups(self, lib):
        """C4: detect_duplicates returns groups_found count."""
        result = lib.detect_duplicates()
        assert "groups_found" in result
        assert isinstance(result["groups_found"], int)
        # list_duplicate_groups also returns data
        groups = lib.list_duplicate_groups()
        assert isinstance(groups, list)

    def test_c4_api_observable_relink_report_by_uid(self, lib):
        """C4: relink_report returns path change history for specified uid."""
        # Generate some changes first
        with lib._connect() as conn:
            conn.execute("UPDATE asset_locations SET is_available=1")
            conn.execute("DELETE FROM path_change_log")
        lib.scan_asset_availability()

        report = lib.relink_report(uids=["uid_a"])
        assert isinstance(report, list)
        # Should have entries since scan marked paths unavailable
        if report:
            entry = report[0]
            assert "uid" in entry
            assert "changes" in entry
            assert isinstance(entry["changes"], list)
            if entry["changes"]:
                change = entry["changes"][0]
                assert "change_type" in change
                assert "created_at" in change
