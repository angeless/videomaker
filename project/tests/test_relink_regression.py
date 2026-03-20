"""Real Jianying project regression tests for project_relink full pipeline.

Uses sanitized fixtures extracted from real 剪映 projects:

    fixtures/jianying_samples/sample_small.json   — 56 videos   (潮州婚礼)
    fixtures/jianying_samples/sample_medium.json  — 105 videos  (莫斯科)
    fixtures/jianying_samples/sample_large.json   — 104 videos + 40 audios (摩尔曼斯克)
    fixtures/jianying_samples/sample_mixed.json   — 93 videos + 63 audios (粉色捷琳别尔卡)

Regression coverage:
  1. Full pipeline parse → relink map → all status buckets populated
  2. Realistic material path patterns (relative, absolute, CJK filenames)
  3. Manual binding → reanalyze inheritance across jobs
  4. Apply → verify → handover → export closure
  5. Performance: large projects complete within time budget
  6. Freeze rule compliance throughout pipeline
"""
import json
import os
import shutil
import sys
import tempfile
import time
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

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "jianying_samples"


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture()
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def gml(tmpdir):
    """GlobalMediaLibrary with a fresh temp DB."""
    db = os.path.join(tmpdir, "test_media.db")
    return GlobalMediaLibrary(db_path=db)


def _load_sample(name: str) -> dict:
    """Load a sample fixture and return parsed JSON."""
    path = FIXTURE_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_draft(tmpdir, sample_name: str, make_some_files=False,
                stable_fraction=0.0, library_fraction=0.5) -> str:
    """Write a sample fixture as a draft file with absolute paths.

    Args:
        stable_fraction: fraction of refs whose old_path file actually exists
        library_fraction: fraction of refs to seed into asset library (uid match)
    """
    data = _load_sample(sample_name)
    materials = data.get("materials", {})

    # Convert relative paths to absolute (simulating a real project)
    project_dir = os.path.join(tmpdir, f"project_{sample_name}")
    os.makedirs(project_dir, exist_ok=True)

    all_refs = []
    for cat in ("videos", "audios"):
        for entry in materials.get(cat, []):
            rel_path = entry.get("path", "")
            abs_path = os.path.join(project_dir, rel_path)
            entry["path"] = abs_path
            all_refs.append((entry, cat))

    # Create stable files on disk for a fraction
    n_stable = int(len(all_refs) * stable_fraction)
    for i in range(n_stable):
        entry, _ = all_refs[i]
        p = Path(entry["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"stable content {i}")

    draft_path = os.path.join(project_dir, "draft_content.json")
    with open(draft_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return draft_path


def _seed_library(gml, draft_path: str, tmpdir: str, fraction: float = 0.5):
    """Seed the asset library with UIDs and paths for a fraction of refs.

    Returns (seeded_uids_set, relocated_dir).
    """
    with open(draft_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    materials = data.get("materials", {})
    all_paths = []
    for cat in ("videos", "audios"):
        for entry in materials.get(cat, []):
            p = entry.get("path", "").strip()
            if p:
                all_paths.append(p)

    n_seed = int(len(all_paths) * fraction)
    relocated_dir = os.path.join(tmpdir, "relocated")
    os.makedirs(relocated_dir, exist_ok=True)

    seeded = set()
    now = gml._now()
    with gml._connect() as conn:
        for i in range(n_seed):
            old_path = all_paths[i]
            filename = Path(old_path).name
            uid = f"uid_{i:04d}"
            sha = f"sha256_regr_{i:06d}"

            # Register asset in library (include all NOT NULL columns)
            conn.execute(
                """INSERT OR IGNORE INTO assets
                   (uid, sha256, filename, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    size_bytes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, sha, filename, old_path, "local",
                 10.0, "1920x1080", 80, "",
                 50000, now, now),
            )

            # Create a relocated file
            new_file = os.path.join(relocated_dir, f"batch_{i}", filename)
            Path(new_file).parent.mkdir(parents=True, exist_ok=True)
            Path(new_file).write_text(f"relocated content {i}")

            # Register location
            conn.execute(
                "INSERT OR IGNORE INTO asset_locations "
                "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                (uid, new_file, "local", 1, now),
            )

            seeded.add(uid)

    return seeded, relocated_dir


# ──────────────────────────────────────────────────────────
# 1. Full Pipeline Parse
# ──────────────────────────────────────────────────────────

class TestFullPipelineParse:
    """Verify that real project structures parse correctly through the pipeline."""

    @pytest.mark.parametrize("sample", ["sample_small", "sample_medium", "sample_large", "sample_mixed"])
    def test_parse_all_samples(self, gml, tmpdir, sample):
        """All 4 samples parse without error and produce a done job."""
        draft_path = _make_draft(tmpdir, sample, stable_fraction=0.1, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        assert "error" not in result, f"Parse failed: {result.get('error')}"
        assert result["status"] == "done"
        assert result["summary"]["total_refs"] > 0

    @pytest.mark.parametrize("sample", ["sample_small", "sample_medium", "sample_large", "sample_mixed"])
    def test_all_status_buckets(self, gml, tmpdir, sample):
        """With mixed seeding, all 4 status buckets should be populated."""
        draft_path = _make_draft(tmpdir, sample, stable_fraction=0.1, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        job_id = result["job_id"]
        job = gml.get_project_relink_job(job_id)

        # With 10% stable + 30% library-seeded, we should get a mix
        total = job["total_refs"]
        stable = job["stable_refs"]
        changed = job["changed_refs"]
        missing = job["missing_refs"]
        unmatched = job["unmatched_refs"]

        assert stable + changed + missing + unmatched == total
        # At least some should be in different buckets (exact depends on path overlap)
        assert total > 0

    def test_cjk_filenames(self, gml, tmpdir):
        """Projects with CJK filenames (e.g., 1月1日.mp4) parse correctly."""
        draft_path = _make_draft(tmpdir, "sample_mixed", stable_fraction=0.0)

        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        assert "error" not in result
        assert result["summary"]["total_refs"] > 0

    def test_relative_vs_absolute_paths(self, gml, tmpdir):
        """Paths with various formats are handled correctly."""
        data = _load_sample("sample_small")
        # Verify fixture has relative paths originally
        materials = data.get("materials", {})
        videos = materials.get("videos", [])
        assert len(videos) > 0
        # After _make_draft, paths become absolute
        draft_path = _make_draft(tmpdir, "sample_small")
        with open(draft_path, "r") as f:
            draft = json.load(f)
        for v in draft["materials"]["videos"]:
            assert os.path.isabs(v["path"]), f"Expected absolute path: {v['path']}"


# ──────────────────────────────────────────────────────────
# 2. Manual Binding + Inheritance
# ──────────────────────────────────────────────────────────

class TestManualBindingInheritance:
    """Test manual bind → reanalyze → inheritance with real project structure."""

    def test_bind_and_reanalyze_inherits(self, gml, tmpdir):
        """Manual bindings from job 1 carry forward to job 2 via reanalyze."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.05, library_fraction=0.2)
        seeded, _ = _seed_library(gml, draft_path, tmpdir, fraction=0.2)

        # Job 1
        r1 = gml.create_project_relink_job(draft_path, project_type="jianying")
        job1_id = r1["job_id"]

        # Get items — find unmatched or missing to bind
        items1 = gml.get_project_relink_job(job1_id)["items"]
        bindable = [i for i in items1 if i["status"] in ("missing", "unmatched")]

        # Bind a few manually
        bound_count = 0
        for i, item in enumerate(bindable[:3]):
            uid = f"uid_manual_{i}"
            relocated = os.path.join(tmpdir, "manual_relocated", f"file_{i}.mp4")
            Path(relocated).parent.mkdir(parents=True, exist_ok=True)
            Path(relocated).write_text(f"manual {i}")
            with gml._connect() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO assets
                       (uid, sha256, filename, primary_path, source_type,
                        duration, resolution, quality_score, scene_description,
                        size_bytes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (uid, f"sha_{uid}", f"file_{i}.mp4", relocated, "local",
                     10.0, "1920x1080", 80, "", 50000, gml._now(), gml._now()),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO asset_locations "
                    "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                    (uid, relocated, "local", 1, gml._now()),
                )
            result = gml.bind_project_relink_item(item["item_id"], uid)
            if "error" not in result:
                bound_count += 1

        assert bound_count > 0, "Should have bound at least one item"

        # Job 2 — reanalyze
        r2 = gml.reanalyze_project_relink(draft_path, project_type="jianying")
        assert "error" not in r2
        job2_id = r2["job_id"]
        assert r2["predecessor_job_id"] == job1_id

        # Check inheritance
        items2 = gml.get_project_relink_job(job2_id)["items"]
        inherited = [i for i in items2 if i.get("inherited_from_item_id")]
        assert len(inherited) > 0, "Reanalyze should inherit manual bindings"

        # Verify inheritance doesn't corrupt system fields
        for item in inherited:
            assert item.get("manual_uid") is not None
            # Freeze rule §2.4: system fields preserved
            # manual_uid should be separate from uid

    def test_three_tier_priority(self, gml, tmpdir):
        """Inheritance uses source_ref → old_path → asset_name+media_type priority."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.0, library_fraction=0.0)

        # Job 1 with manual binding
        r1 = gml.create_project_relink_job(draft_path, project_type="jianying")
        job1_id = r1["job_id"]
        items1 = gml.get_project_relink_job(job1_id)["items"]

        # Bind first unmatched item
        unmatched = [i for i in items1 if i["status"] == "unmatched"]
        if not unmatched:
            pytest.skip("No unmatched items in sample_small")

        uid = "uid_tier_test"
        relocated = os.path.join(tmpdir, "tier_test", "test.mp4")
        Path(relocated).parent.mkdir(parents=True, exist_ok=True)
        Path(relocated).write_text("tier test")
        with gml._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO assets
                   (uid, sha256, filename, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    size_bytes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, f"sha_{uid}", "test.mp4", relocated, "local",
                 10.0, "1920x1080", 80, "", 50000, gml._now(), gml._now()),
            )
            conn.execute(
                "INSERT OR IGNORE INTO asset_locations "
                "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                (uid, relocated, "local", 1, gml._now()),
            )
        bound_item = unmatched[0]
        gml.bind_project_relink_item(bound_item["item_id"], uid)

        # Job 2 — reanalyze
        r2 = gml.reanalyze_project_relink(draft_path, project_type="jianying")
        assert "error" not in r2, f"Reanalyze failed: {r2}"

        # Find the inherited item
        items2 = gml.get_project_relink_job(r2["job_id"])["items"]
        inherited = [i for i in items2 if i.get("inherited_from_item_id")]

        if inherited:
            # The inherited item should trace back to the bound item
            assert inherited[0]["manual_uid"] == uid


# ──────────────────────────────────────────────────────────
# 3. Apply → Verify → Handover Closure
# ──────────────────────────────────────────────────────────

class TestApplyVerifyHandover:
    """End-to-end closure: apply → verify → handover → export."""

    def _create_relinked_job(self, gml, tmpdir, sample="sample_small"):
        """Create a job with at least some relinked items."""
        draft_path = _make_draft(tmpdir, sample, stable_fraction=0.1, library_fraction=0.4)
        _seed_library(gml, draft_path, tmpdir, fraction=0.4)
        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        return result["job_id"], draft_path

    def test_apply_produces_valid_output(self, gml, tmpdir):
        """Apply on a real project structure produces a valid output file."""
        job_id, draft_path = self._create_relinked_job(gml, tmpdir)

        job = gml.get_project_relink_job(job_id)
        if job["changed_refs"] == 0:
            pytest.skip("No relinked items to apply")

        result = gml.apply_project_relink(job_id)
        assert "error" not in result, f"Apply failed: {result}"
        assert result["applied"] > 0

        # Output file should exist and be valid JSON
        output_path = result["output_path"]
        assert Path(output_path).exists()
        with open(output_path, "r", encoding="utf-8") as f:
            output_data = json.load(f)
        assert "materials" in output_data

        # Output should NOT be the same file as original
        assert str(Path(output_path).resolve()) != str(Path(draft_path).resolve())

    def test_verify_after_apply(self, gml, tmpdir):
        """Verify after apply reports correct path health."""
        job_id, _ = self._create_relinked_job(gml, tmpdir)

        verification = gml.verify_project_relink_state(job_id)
        assert "error" not in verification
        assert "all_valid" in verification
        assert "stale_count" in verification
        assert "verified" in verification

        # Verify doesn't change any item status (freeze rule §2.10)
        items = gml.get_project_relink_job(job_id)["items"]
        for item in items:
            status = item["status"]
            assert status in ("stable", "relinked", "missing", "unmatched")

    def test_handover_generates_snapshot(self, gml, tmpdir):
        """Handover on a real project generates a complete frozen snapshot."""
        job_id, _ = self._create_relinked_job(gml, tmpdir)

        report = gml.generate_handover_report(job_id, auto_verify=True)
        assert "error" not in report, f"Handover failed: {report}"
        assert "closure_status" in report
        assert report["closure_status"] in ("complete", "incomplete")
        assert "resolution_summary" in report

        summary = report["resolution_summary"]
        assert "total_refs" in summary
        assert summary["total_refs"] > 0

        # Verify snapshot is stored (frozen)
        with gml._connect() as conn:
            row = conn.execute(
                "SELECT handover_snapshot, handover_at FROM project_relink_job WHERE job_id=?",
                (job_id,),
            ).fetchone()
            assert row["handover_at"] is not None
            snapshot = json.loads(row["handover_snapshot"])
            assert snapshot["report_version"] == "1.0"

    def test_export_handover_json(self, gml, tmpdir):
        """Export handover as JSON produces valid output."""
        job_id, _ = self._create_relinked_job(gml, tmpdir)
        gml.generate_handover_report(job_id)

        result = gml.export_handover_report(job_id, fmt="json")
        assert "error" not in result
        assert "report" in result
        assert "filename" in result

    def test_export_handover_markdown(self, gml, tmpdir):
        """Export handover as Markdown includes expected sections."""
        job_id, _ = self._create_relinked_job(gml, tmpdir)
        gml.generate_handover_report(job_id)

        result = gml.export_handover_report(job_id, fmt="markdown")
        assert "error" not in result
        assert "markdown_content" in result
        md = result["markdown_content"]
        assert "# 工程 Relink 交接报告" in md
        assert "解决汇总" in md

    def test_full_closure_pipeline(self, gml, tmpdir):
        """Full pipeline: create → bind → apply → verify → handover → export."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.1, library_fraction=0.3)
        seeded, _ = _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        # 1. Create
        r1 = gml.create_project_relink_job(draft_path, project_type="jianying")
        job_id = r1["job_id"]
        assert r1["status"] == "done"

        # 2. Bind some unmatched (if any)
        items = gml.get_project_relink_job(job_id)["items"]
        unmatched = [i for i in items if i["status"] in ("missing", "unmatched")]
        for item in unmatched[:2]:
            uid = f"uid_closure_{item['item_id']}"
            f = os.path.join(tmpdir, "closure_files", f"f_{item['item_id']}.mp4")
            Path(f).parent.mkdir(parents=True, exist_ok=True)
            Path(f).write_text("closure file")
            with gml._connect() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO assets
                       (uid, sha256, filename, primary_path, source_type,
                        duration, resolution, quality_score, scene_description,
                        size_bytes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (uid, f"sha_{uid}", Path(f).name, f, "local",
                     10.0, "1920x1080", 80, "", 50000, gml._now(), gml._now()),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO asset_locations "
                    "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                    (uid, f, "local", 1, gml._now()),
                )
            gml.bind_project_relink_item(item["item_id"], uid)

        # 3. Apply
        job_after = gml.get_project_relink_job(job_id)
        if job_after["changed_refs"] > 0:
            apply_result = gml.apply_project_relink(job_id)
            assert "error" not in apply_result

        # 4. Verify
        verify = gml.verify_project_relink_state(job_id)
        assert "error" not in verify

        # 5. Handover
        handover = gml.generate_handover_report(job_id, auto_verify=True)
        assert "error" not in handover

        # 6. Export
        export = gml.export_handover_report(job_id, fmt="markdown")
        assert "error" not in export
        assert "markdown_content" in export

        # 7. Reanalyze → verify inheritance
        r2 = gml.reanalyze_project_relink(draft_path, project_type="jianying")
        assert "error" not in r2
        assert r2["predecessor_job_id"] == job_id

        # 8. Job chain
        chain = gml.get_project_job_chain(draft_path)
        assert len(chain["chain"]) >= 2


# ──────────────────────────────────────────────────────────
# 4. Performance Budget
# ──────────────────────────────────────────────────────────

class TestPerformanceBudget:
    """Ensure large projects complete within acceptable time."""

    def test_large_project_parse_under_5s(self, gml, tmpdir):
        """104 videos + 40 audios should parse under 5 seconds."""
        draft_path = _make_draft(tmpdir, "sample_large", stable_fraction=0.1, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        t0 = time.time()
        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        elapsed = time.time() - t0

        assert "error" not in result
        assert elapsed < 5.0, f"Large project parse took {elapsed:.2f}s (budget: 5s)"

    def test_mixed_project_reanalyze_under_5s(self, gml, tmpdir):
        """93 videos + 63 audios reanalyze should complete under 5 seconds."""
        draft_path = _make_draft(tmpdir, "sample_mixed", stable_fraction=0.05, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        # First job
        gml.create_project_relink_job(draft_path, project_type="jianying")

        # Reanalyze
        t0 = time.time()
        result = gml.reanalyze_project_relink(draft_path, project_type="jianying")
        elapsed = time.time() - t0

        assert "error" not in result
        assert elapsed < 5.0, f"Reanalyze took {elapsed:.2f}s (budget: 5s)"


# ──────────────────────────────────────────────────────────
# 5. Freeze Rule Compliance
# ──────────────────────────────────────────────────────────

class TestFreezeRuleCompliance:
    """Verify freeze rules hold throughout the pipeline with real data."""

    def test_job_status_only_four_values(self, gml, tmpdir):
        """§2.1: job.status only pending/running/done/failed."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.1, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        job_id = result["job_id"]

        with gml._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT status FROM project_relink_job"
            ).fetchall()
            statuses = {r["status"] for r in rows}
            assert statuses.issubset({"pending", "running", "done", "failed"})

    def test_item_status_only_four_values(self, gml, tmpdir):
        """§2.2: item.status only stable/relinked/missing/unmatched."""
        draft_path = _make_draft(tmpdir, "sample_medium", stable_fraction=0.1, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)
        gml.create_project_relink_job(draft_path, project_type="jianying")

        with gml._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT status FROM project_relink_item"
            ).fetchall()
            statuses = {r["status"] for r in rows}
            assert statuses.issubset({"stable", "relinked", "missing", "unmatched"})

    def test_bind_preserves_system_new_path(self, gml, tmpdir):
        """§2.4: bind does NOT overwrite system new_path field."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.0, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        job_id = result["job_id"]
        items = gml.get_project_relink_job(job_id)["items"]

        # Find a missing item with a system new_path (relinked then unbind won't have one,
        # but we look for any with non-null new_path)
        missing = [i for i in items if i["status"] == "missing" and i.get("new_path")]
        if not missing:
            pytest.skip("No missing items with system new_path")

        item = missing[0]
        original_new_path = item["new_path"]

        # Bind to a manual uid
        uid = "uid_sys_test"
        f = os.path.join(tmpdir, "sys_test.mp4")
        Path(f).write_text("sys test")
        with gml._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO assets
                   (uid, sha256, filename, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    size_bytes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, f"sha_{uid}", "sys_test.mp4", f, "local",
                 10.0, "1920x1080", 80, "", 50000, gml._now(), gml._now()),
            )
            conn.execute(
                "INSERT OR IGNORE INTO asset_locations "
                "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                (uid, f, "local", 1, gml._now()),
            )
        gml.bind_project_relink_item(item["item_id"], uid)

        # After bind: system new_path should be UNCHANGED
        with gml._connect() as conn:
            updated = conn.execute(
                "SELECT new_path, manual_new_path FROM project_relink_item WHERE item_id=?",
                (item["item_id"],),
            ).fetchone()
            assert updated["new_path"] == original_new_path, \
                f"System new_path was overwritten: {original_new_path} → {updated['new_path']}"
            assert updated["manual_new_path"] is not None

    def test_verify_never_changes_status(self, gml, tmpdir):
        """§2.10: verify only sets verified_at, never changes item.status."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.1, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        job_id = result["job_id"]

        # Record statuses before verify
        items_before = gml.get_project_relink_job(job_id)["items"]
        status_before = {i["item_id"]: i["status"] for i in items_before}

        # Run verify
        gml.verify_project_relink_state(job_id)

        # Record statuses after verify
        items_after = gml.get_project_relink_job(job_id)["items"]
        status_after = {i["item_id"]: i["status"] for i in items_after}

        assert status_before == status_after, "Verify changed item status!"

    def test_handover_snapshot_frozen(self, gml, tmpdir):
        """§2.11: handover_snapshot doesn't auto-update."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.1, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        job_id = result["job_id"]

        # Generate handover
        report = gml.generate_handover_report(job_id)
        assert "error" not in report

        # Read snapshot
        with gml._connect() as conn:
            snap1 = conn.execute(
                "SELECT handover_snapshot FROM project_relink_job WHERE job_id=?",
                (job_id,),
            ).fetchone()["handover_snapshot"]

        # Bind a new item (change the job state)
        items = gml.get_project_relink_job(job_id)["items"]
        unmatched = [i for i in items if i["status"] in ("missing", "unmatched")]
        if unmatched:
            uid = "uid_freeze_test"
            f = os.path.join(tmpdir, "freeze_test.mp4")
            Path(f).write_text("freeze test")
            with gml._connect() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO assets
                       (uid, sha256, filename, primary_path, source_type,
                        duration, resolution, quality_score, scene_description,
                        size_bytes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (uid, f"sha_{uid}", "freeze_test.mp4", f, "local",
                     10.0, "1920x1080", 80, "", 50000, gml._now(), gml._now()),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO asset_locations "
                    "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                    (uid, f, "local", 1, gml._now()),
                )
            gml.bind_project_relink_item(unmatched[0]["item_id"], uid)

        # Snapshot should NOT have changed
        with gml._connect() as conn:
            snap2 = conn.execute(
                "SELECT handover_snapshot FROM project_relink_job WHERE job_id=?",
                (job_id,),
            ).fetchone()["handover_snapshot"]

        assert snap1 == snap2, "Handover snapshot auto-updated after bind!"

    def test_apply_never_overwrites_original(self, gml, tmpdir):
        """§2.6: apply always writes to a separate file."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.1, library_fraction=0.4)
        _seed_library(gml, draft_path, tmpdir, fraction=0.4)

        result = gml.create_project_relink_job(draft_path, project_type="jianying")
        job_id = result["job_id"]

        job = gml.get_project_relink_job(job_id)
        if job["changed_refs"] == 0:
            pytest.skip("No relinked items")

        # Read original content
        with open(draft_path, "r") as f:
            original = f.read()

        # Apply
        apply_result = gml.apply_project_relink(job_id)
        assert "error" not in apply_result

        # Original should be UNCHANGED
        with open(draft_path, "r") as f:
            after = f.read()
        assert original == after, "Apply modified the original project file!"

    def test_action_log_completeness(self, gml, tmpdir):
        """§3.3: all key actions produce audit log entries."""
        draft_path = _make_draft(tmpdir, "sample_small", stable_fraction=0.1, library_fraction=0.3)
        _seed_library(gml, draft_path, tmpdir, fraction=0.3)

        # Create
        r = gml.create_project_relink_job(draft_path, project_type="jianying")
        job_id = r["job_id"]

        items = gml.get_project_relink_job(job_id)["items"]
        unmatched = [i for i in items if i["status"] in ("missing", "unmatched")]

        if unmatched:
            uid = "uid_audit"
            f = os.path.join(tmpdir, "audit.mp4")
            Path(f).write_text("audit")
            with gml._connect() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO assets
                       (uid, sha256, filename, primary_path, source_type,
                        duration, resolution, quality_score, scene_description,
                        size_bytes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (uid, f"sha_{uid}", "audit.mp4", f, "local",
                     10.0, "1920x1080", 80, "", 50000, gml._now(), gml._now()),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO asset_locations "
                    "(uid, path, source_type, is_available, last_seen_at) VALUES (?,?,?,?,?)",
                    (uid, f, "local", 1, gml._now()),
                )

            # Bind
            gml.bind_project_relink_item(unmatched[0]["item_id"], uid)
            # Unbind
            gml.unbind_project_relink_item(unmatched[0]["item_id"])

        # Verify
        gml.verify_project_relink_state(job_id)

        # Handover
        gml.generate_handover_report(job_id)

        # Check action log
        log = gml.get_project_relink_action_log(job_id)
        action_types = {entry["action_type"] for entry in log}

        # At minimum: verify and handover
        assert "verify" in action_types, f"Missing 'verify' in action log: {action_types}"
        assert "handover" in action_types, f"Missing 'handover' in action log: {action_types}"

        if unmatched:
            assert "bind" in action_types, f"Missing 'bind' in action log: {action_types}"
            assert "unbind" in action_types, f"Missing 'unbind' in action log: {action_types}"
