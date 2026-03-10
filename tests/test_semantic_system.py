"""Tests for v0.6 semantic tag system — Phase 1 schema + seed data."""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force-reload the real module in case a previous test replaced it with a fake
import importlib
_mod_name = "modules.library.global_media_library"
if _mod_name in sys.modules:
    _mod = sys.modules[_mod_name]
    if not hasattr(_mod, "SCORING_CONFIG"):
        # A fake module was injected — remove and reimport the real one
        del sys.modules[_mod_name]
        importlib.import_module(_mod_name)

# ---------------------------------------------------------------------------
# Skip entire module if seed data directory doesn't exist
# ---------------------------------------------------------------------------
_SEED_DIR = Path(os.path.expanduser("~/Downloads/语义数据库-chatgpt-20260306"))
pytestmark = pytest.mark.skipif(
    not _SEED_DIR.exists(),
    reason="Seed data directory not available",
)


@pytest.fixture(scope="module")
def lib():
    """Create a GlobalMediaLibrary with a temporary DB that seeds automatically."""
    # Re-import to ensure we have the real module
    mod = importlib.import_module("modules.library.global_media_library")
    GlobalMediaLibrary = mod.GlobalMediaLibrary

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_semantic.db")
        gml = GlobalMediaLibrary(db_path=db_path)
        yield gml


@pytest.fixture(scope="module")
def conn(lib):
    """Direct SQLite connection to the library's DB for assertions."""
    c = sqlite3.connect(lib.db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ── Test 1: Schema completeness ──

EXPECTED_TABLES = [
    "tag_category", "tag", "tag_alias", "tag_relation",
    "composite_rule", "evidence", "asset_tag_result",
    "custom_tag", "feedback_event", "learning_candidate",
    "learning_stopword",
]

def test_all_11_tables_exist(conn):
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for t in EXPECTED_TABLES:
        assert t in tables, f"Missing table: {t}"


EXPECTED_INDEXES = [
    "idx_tag_category", "idx_tag_parent", "idx_tag_slot",
    "idx_alias_name", "idx_evidence_asset", "idx_evidence_tag",
    "idx_result_asset_score", "idx_result_tag",
    "idx_feedback_asset", "idx_feedback_tag",
]

def test_key_indexes_exist(conn):
    indexes = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for idx in EXPECTED_INDEXES:
        assert idx in indexes, f"Missing index: {idx}"


# ── Test 2: Seed import idempotency ──

def test_seed_idempotent(lib, conn):
    """Calling _seed_tag_library_if_empty a second time should not add rows."""
    count_before = conn.execute("SELECT count(*) FROM tag").fetchone()[0]
    # Call seed again — should be a no-op because tag table is not empty
    c2 = sqlite3.connect(lib.db_path)
    c2.row_factory = sqlite3.Row
    lib._seed_tag_library_if_empty(c2)
    c2.close()
    count_after = conn.execute("SELECT count(*) FROM tag").fetchone()[0]
    assert count_after == count_before


# ── Test 3: Tag count and semantic_slot distribution ──

def test_tag_count_minimum(conn):
    count = conn.execute("SELECT count(*) FROM tag").fetchone()[0]
    assert count >= 2124, f"Expected >= 2124 tags, got {count}"


def test_all_16_semantic_slots_have_tags(conn):
    EXPECTED_SLOTS = {
        "object", "place", "scene", "action", "person", "event", "mood",
        "style", "weather", "season", "nature", "food", "animal",
        "indoor_outdoor", "time_of_day", "shot_type",
    }
    rows = conn.execute(
        "SELECT semantic_slot, count(*) as cnt FROM tag GROUP BY semantic_slot"
    ).fetchall()
    slot_counts = {r["semantic_slot"]: r["cnt"] for r in rows}
    for slot in EXPECTED_SLOTS:
        assert slot in slot_counts, f"No tags with semantic_slot='{slot}'"
        assert slot_counts[slot] > 0, f"semantic_slot='{slot}' has 0 tags"


# ── Test 4: Alias import ──

def test_alias_count(conn):
    count = conn.execute("SELECT count(*) FROM tag_alias").fetchone()[0]
    assert count >= 200, f"Expected >= 200 aliases, got {count}"


def test_alias_normalized(conn):
    """All normalized_alias values should be lowercase stripped."""
    bad = conn.execute(
        "SELECT alias_id, normalized_alias FROM tag_alias WHERE normalized_alias != lower(trim(normalized_alias))"
    ).fetchall()
    assert len(bad) == 0, f"{len(bad)} aliases not properly normalized"


# ── Test 5: Parent/child hierarchy ──

def test_parent_child_relations_exist(conn):
    parent_count = conn.execute(
        "SELECT count(*) FROM tag_relation WHERE relation_type = 'parent'"
    ).fetchone()[0]
    child_count = conn.execute(
        "SELECT count(*) FROM tag_relation WHERE relation_type = 'child'"
    ).fetchone()[0]
    assert parent_count >= 100, f"Expected >= 100 parent relations, got {parent_count}"
    assert child_count >= 100, f"Expected >= 100 child relations, got {child_count}"


def test_subcategory_tags_exist(conn):
    """Subcategory tags should have level_no=1."""
    count = conn.execute(
        "SELECT count(*) FROM tag WHERE level_no = 1"
    ).fetchone()[0]
    assert count >= 50, f"Expected >= 50 subcategory tags (level_no=1), got {count}"


def test_keyword_tags_have_parent(conn):
    """Most keyword tags should have parent_tag_id set (level_no=2)."""
    count = conn.execute(
        "SELECT count(*) FROM tag WHERE level_no = 2 AND parent_tag_id IS NOT NULL"
    ).fetchone()[0]
    assert count >= 1000, f"Expected >= 1000 keyword tags with parent, got {count}"


# ── Test 6: Stopword count ──

def test_stopword_count(conn):
    count = conn.execute("SELECT count(*) FROM learning_stopword").fetchone()[0]
    assert count >= 80, f"Expected >= 80 stopwords, got {count}"


def test_stopword_categories(conn):
    cats = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT block_reason FROM learning_stopword"
        ).fetchall()
    }
    expected = {"ocr_noise", "spoken_filler", "device_name", "timestamp", "logo", "ad", "functional"}
    assert expected.issubset(cats), f"Missing stopword categories: {expected - cats}"


# ── Test 7: Config constants validity ──

def test_scoring_config_values():
    mod = importlib.import_module("modules.library.global_media_library")
    SCORING_CONFIG = mod.SCORING_CONFIG
    weights = SCORING_CONFIG["source_weight"]
    for k, v in weights.items():
        assert 0.0 <= v <= 2.0, f"source_weight[{k}]={v} out of range [0, 2.0]"
    assert 0.0 <= SCORING_CONFIG["display_threshold"] <= 1.0
    assert 0.0 <= SCORING_CONFIG["write_threshold"] <= 1.0
    assert SCORING_CONFIG["write_threshold"] <= SCORING_CONFIG["display_threshold"]
    for band, val in SCORING_CONFIG["confidence_bands"].items():
        assert 0.0 <= val <= 1.0, f"confidence_band[{band}]={val} out of range"


def test_search_weights_sum():
    mod = importlib.import_module("modules.library.global_media_library")
    SEARCH_WEIGHTS = mod.SEARCH_WEIGHTS
    core_sum = (
        SEARCH_WEIGHTS["tag_match"]
        + SEARCH_WEIGHTS["fts_match"]
        + SEARCH_WEIGHTS["embedding_match"]
    )
    assert abs(core_sum - 1.0) < 0.01, f"Core search weights sum to {core_sum}, expected 1.0"


def test_semantic_slots_constant():
    mod = importlib.import_module("modules.library.global_media_library")
    SEMANTIC_SLOTS = mod.SEMANTIC_SLOTS
    assert len(SEMANTIC_SLOTS) == 16
    assert "object" in SEMANTIC_SLOTS
    assert "shot_type" in SEMANTIC_SLOTS


# ── Test 8: Event slot includes 婚礼 ──

def test_event_has_wedding(conn):
    row = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '婚礼' AND semantic_slot = 'event'"
    ).fetchone()
    assert row is not None, "婚礼 should exist in event slot"


# ── Test 9: Composite rules ──

def test_composite_rules_imported(conn):
    count = conn.execute("SELECT count(*) FROM composite_rule").fetchone()[0]
    assert count >= 7, f"Expected >= 7 composite rules, got {count}"


def test_negative_rule_for_wedding(conn):
    """婚礼 negative rule should now exist since 婚礼 is in the tag table."""
    row = conn.execute(
        """SELECT cr.rule_name FROM composite_rule cr
           JOIN tag t ON cr.target_tag_id = t.tag_id
           WHERE t.tag_name = '婚礼' AND cr.rule_type = 'negative'"""
    ).fetchone()
    assert row is not None, "Negative rule for 婚礼 should exist"


# ── Test 10: Tag category count ──

def test_tag_category_count(conn):
    count = conn.execute("SELECT count(*) FROM tag_category").fetchone()[0]
    assert count == 22, f"Expected 22 tag categories, got {count}"


# ═══════════════════════════════════════════════════════════
# Phase 2 tests: Evidence persistence + tag resolution
# ═══════════════════════════════════════════════════════════

def test_resolve_tag_id_exact(lib, conn):
    """_resolve_tag_id finds a tag by exact name."""
    tag_id = lib._resolve_tag_id("客厅", conn)
    assert tag_id is not None
    row = conn.execute("SELECT tag_name FROM tag WHERE tag_id = ?", (tag_id,)).fetchone()
    assert row[0] == "客厅"


def test_resolve_tag_id_alias(lib, conn):
    """_resolve_tag_id finds a tag via its alias."""
    # 客厅 has alias 起居室
    tag_id_direct = lib._resolve_tag_id("客厅", conn)
    tag_id_alias = lib._resolve_tag_id("起居室", conn)
    assert tag_id_alias is not None
    assert tag_id_alias == tag_id_direct


def test_resolve_tag_id_stopword(lib, conn):
    """_resolve_tag_id returns _STOPWORD_SENTINEL for stopwords."""
    tag_id = lib._resolve_tag_id("加载中", conn)
    assert tag_id == lib._STOPWORD_SENTINEL


def test_resolve_tag_id_unknown(lib, conn):
    """_resolve_tag_id returns None for unknown terms."""
    tag_id = lib._resolve_tag_id("不可能存在的词汇xyz123", conn)
    assert tag_id is None


def test_resolve_tag_id_cache(lib, conn):
    """_resolve_tag_id uses cache correctly."""
    cache = {}
    lib._resolve_tag_id("客厅", conn, _cache=cache)
    assert "客厅" in cache
    assert cache["客厅"] is not None
    lib._resolve_tag_id("加载中", conn, _cache=cache)
    assert "加载中" in cache
    assert cache["加载中"] == lib._STOPWORD_SENTINEL


def test_persist_evidence_and_tags_basic(lib, conn):
    """_persist_evidence_and_tags writes evidence and tag_result rows."""
    # Create a fake asset (all NOT NULL columns required)
    conn.execute(
        "INSERT OR IGNORE INTO assets (uid, sha256, filename, source_type, created_at, updated_at) VALUES ('test_uid_001', 'sha_001', 'test.mp4', 'local', datetime('now'), datetime('now'))"
    )
    conn.commit()

    # Build a minimal semantic_json
    semantic_json = {
        "structured_tags": {
            "tags": {
                "objects": {"zh": ["沙发", "电视"], "en": ["sofa", "tv"], "confidence": 0.80},
                "scene": {"zh": ["客厅"], "en": ["living room"], "confidence": 0.75},
                "mood": {"zh": ["温馨"], "en": ["cozy"], "confidence": 0.65},
            }
        },
        "setting": "indoor",
        "_meta": {"model_version": "test_model"},
    }

    count = lib._persist_evidence_and_tags("test_uid_001", semantic_json, conn)
    conn.commit()

    assert count > 0, "Should have written at least 1 tag result"

    # Check evidence was written
    ev_count = conn.execute(
        "SELECT count(*) FROM evidence WHERE asset_id = 'test_uid_001'"
    ).fetchone()[0]
    assert ev_count > 0, f"Expected evidence rows, got {ev_count}"

    # Check asset_tag_result was written
    result_count = conn.execute(
        "SELECT count(*) FROM asset_tag_result WHERE asset_id = 'test_uid_001'"
    ).fetchone()[0]
    assert result_count > 0, f"Expected tag result rows, got {result_count}"

    # Check score isolation: final_score > 0, user_adjustment = 0
    row = conn.execute(
        "SELECT final_score, user_adjustment, effective_score FROM asset_tag_result WHERE asset_id = 'test_uid_001' LIMIT 1"
    ).fetchone()
    assert row[0] > 0, "final_score should be > 0"
    assert row[1] == 0.0, "user_adjustment should be 0.0"
    assert row[2] > 0, "effective_score should be > 0"
    assert abs(row[2] - (row[0] + row[1])) < 0.001, "effective_score = final_score + user_adjustment"


def test_persist_evidence_scores_clamped(lib, conn):
    """Scores in asset_tag_result are clamped to [0, 1]."""
    rows = conn.execute(
        """SELECT final_score, effective_score FROM asset_tag_result
           WHERE asset_id = 'test_uid_001'"""
    ).fetchall()
    for r in rows:
        assert 0.0 <= r[0] <= 1.0, f"final_score {r[0]} out of [0,1]"
        assert 0.0 <= r[1] <= 1.0, f"effective_score {r[1]} out of [0,1]"


def test_persist_evidence_decision_reason(lib, conn):
    """Each tag result has a decision_reason JSON."""
    rows = conn.execute(
        "SELECT decision_reason FROM asset_tag_result WHERE asset_id = 'test_uid_001'"
    ).fetchall()
    for r in rows:
        reason = json.loads(r[0])
        assert isinstance(reason, list)
        assert len(reason) > 0
        assert "source" in reason[0]
        assert "term" in reason[0]


def test_persist_evidence_unresolved_goes_to_learning(lib, conn):
    """Unknown terms from structured_tags go to learning_candidate."""
    conn.execute(
        "INSERT OR IGNORE INTO assets (uid, sha256, filename, source_type, created_at, updated_at) VALUES ('test_uid_002', 'sha_002', 'test2.mp4', 'local', datetime('now'), datetime('now'))"
    )
    conn.commit()

    semantic_json = {
        "structured_tags": {
            "tags": {
                "objects": {"zh": ["完全虚构的物品名称abc"], "en": ["fictitious"], "confidence": 0.70},
            }
        },
        "_meta": {"model_version": "test"},
    }
    lib._persist_evidence_and_tags("test_uid_002", semantic_json, conn)
    conn.commit()

    row = conn.execute(
        "SELECT candidate_text FROM learning_candidate WHERE normalized_text = '完全虚构的物品名称abc'"
    ).fetchone()
    assert row is not None, "Unknown term should go to learning_candidate"


def test_persist_evidence_empty_input(lib, conn):
    """_persist_evidence_and_tags handles empty input gracefully."""
    assert lib._persist_evidence_and_tags("fake_uid", {}, conn) == 0
    assert lib._persist_evidence_and_tags("fake_uid", None, conn) == 0
    assert lib._persist_evidence_and_tags("fake_uid", {"structured_tags": None}, conn) == 0
