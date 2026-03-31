"""R1: Seed keyword library verification + cold-start ingestion test.

Validates:
  1. JSONL file exists with >= 2100 lines
  2. Every line is valid JSON with 5 required fields
  3. All 12 top_categories are present
  4. Cold-start: empty tag table → seed loads >= 2100 tags (not 33 minimal)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED_PATH = ROOT / "data" / "seeds" / "semantic_keyword_library_flat.jsonl"

REQUIRED_FIELDS = {"keyword", "top_category", "subcategory", "kind", "aliases"}
EXPECTED_CATEGORIES = {
    "交通与建筑", "人物", "动作", "动物", "地点", "场景",
    "抽象语义", "文本与媒体", "时间与环境", "植物", "物品", "视觉风格",
}


class TestSeedFileIntegrity:
    """Verify the JSONL seed file itself."""

    def test_file_exists(self):
        assert SEED_PATH.exists(), f"Seed file not found: {SEED_PATH}"

    def test_line_count_at_least_2100(self):
        with open(SEED_PATH, encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())
        assert count >= 2100, f"Expected >= 2100 lines, got {count}"

    def test_every_line_valid_json_with_required_fields(self):
        errors = []
        with open(SEED_PATH, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {i}: invalid JSON: {e}")
                    continue
                missing = REQUIRED_FIELDS - set(obj.keys())
                if missing:
                    errors.append(f"Line {i}: missing {missing}")
        assert not errors, f"{len(errors)} errors:\n" + "\n".join(errors[:10])

    def test_all_12_categories_present(self):
        cats = set()
        with open(SEED_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                cats.add(obj.get("top_category", ""))
        assert cats == EXPECTED_CATEGORIES, (
            f"Missing: {EXPECTED_CATEGORIES - cats}, Extra: {cats - EXPECTED_CATEGORIES}"
        )


class TestColdStartSeedIngestion:
    """Verify that a fresh database seeds from the JSONL, not the 33-tag fallback."""

    def test_cold_start_loads_full_seed(self):
        """Create a fresh GlobalMediaLibrary with empty DB → tag count >= 2100."""
        from modules.library.global_media_library import GlobalMediaLibrary

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cold_start.db"
            lib = GlobalMediaLibrary(str(db_path))

            with lib._connect() as conn:
                tag_count = conn.execute("SELECT count(*) FROM tag").fetchone()[0]

            assert tag_count >= 2100, (
                f"Cold start loaded only {tag_count} tags "
                f"(expected >= 2100, fallback minimal set is ~33)"
            )

    def test_cold_start_has_all_12_categories(self):
        """Fresh DB should have all 12 seed categories in tag_category table."""
        from modules.library.global_media_library import GlobalMediaLibrary

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cold_cats.db"
            lib = GlobalMediaLibrary(str(db_path))

            with lib._connect() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT category_name FROM tag_category"
                ).fetchall()
                db_cats = {r[0] for r in rows}

            # The DB categories may have extra system categories beyond seed 12
            missing = EXPECTED_CATEGORIES - db_cats
            assert not missing, f"Missing categories after cold start: {missing}"

    def test_aliases_loaded(self):
        """Seed data aliases should be loaded into tag_alias table."""
        from modules.library.global_media_library import GlobalMediaLibrary

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_aliases.db"
            lib = GlobalMediaLibrary(str(db_path))

            with lib._connect() as conn:
                alias_count = conn.execute(
                    "SELECT count(*) FROM tag_alias WHERE source_type = 'seed'"
                ).fetchone()[0]

            # Seed data should produce a substantial number of aliases
            assert alias_count >= 100, (
                f"Only {alias_count} seed aliases loaded (expected >= 100)"
            )
