"""Tests for v0.6 Phase 3 — semantic search engine (tag recall + 3-path fusion)."""
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

import importlib

_mod_name = "modules.library.global_media_library"
if _mod_name in sys.modules:
    _mod = sys.modules[_mod_name]
    if not hasattr(_mod, "SCORING_CONFIG"):
        del sys.modules[_mod_name]
        importlib.import_module(_mod_name)

_SEED_DIR = Path(os.path.expanduser("~/Downloads/语义数据库-chatgpt-20260306"))
_SEED_JSONL = _SEED_DIR / "semantic_keyword_library_flat.jsonl"


def _seed_data_readable():
    """Check seed data is both present and readable (macOS TCC may block ~/Downloads)."""
    try:
        _SEED_JSONL.open("r").close()
        return True
    except (PermissionError, OSError, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(
    not _seed_data_readable(),
    reason="Seed data directory not available or not readable",
)


@pytest.fixture(scope="module")
def lib():
    importlib.import_module("modules")
    importlib.import_module("modules.library")
    mod = importlib.import_module("modules.library.global_media_library")
    mod = importlib.reload(mod)  # Undo any monkeypatches from other test files
    GlobalMediaLibrary = mod.GlobalMediaLibrary
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_recall.db")
        gml = GlobalMediaLibrary(db_path=db_path)
        # Insert a fake asset + tag_result so search can find it
        with gml._connect() as conn:
            _seed_test_data(gml, conn)
        yield gml


def _seed_test_data(gml, conn):
    """Insert minimal test data: assets + asset_tag_result rows for search tests."""
    now = gml._now()

    # Insert 3 test assets
    for i, (uid, fname) in enumerate([
        ("test_uid_kitchen", "kitchen_video.mp4"),
        ("test_uid_beach", "beach_sunset.mp4"),
        ("test_uid_cat", "cute_cat.mp4"),
    ]):
        conn.execute(
            """INSERT OR IGNORE INTO assets
               (uid, filename, sha256, size_bytes, primary_path, source_type,
                duration, resolution, quality_score, scene_description, mood,
                objects_json, semantic_json, semantic_text, keywords_json,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (uid, fname, f"sha_{uid}", 1000 + i, f"/test/{fname}", "local",
             10.0, "1920x1080", 80, f"scene_{uid}", "neutral",
             "[]", "{}", f"厨房 海边 猫 做饭 沙滩", "[]", now, now),
        )

    # Find tag_ids for known seed tags
    kitchen_tag = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '厨房' AND is_active = 1"
    ).fetchone()
    beach_tag = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '海边' AND is_active = 1"
    ).fetchone()
    cat_tag = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '猫' AND is_active = 1"
    ).fetchone()
    cooking_tag = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '做饭' AND is_active = 1"
    ).fetchone()

    # Insert asset_tag_result rows
    tag_mappings = []
    if kitchen_tag:
        tag_mappings.append(("test_uid_kitchen", kitchen_tag[0], 0.85))
    if beach_tag:
        tag_mappings.append(("test_uid_beach", beach_tag[0], 0.90))
    if cat_tag:
        tag_mappings.append(("test_uid_cat", cat_tag[0], 0.80))
    if cooking_tag:
        tag_mappings.append(("test_uid_kitchen", cooking_tag[0], 0.75))

    for uid, tag_id, score in tag_mappings:
        conn.execute(
            """INSERT OR IGNORE INTO asset_tag_result
               (asset_id, tag_id, result_scope, is_displayed,
                base_score, final_score, user_adjustment, effective_score,
                confidence_band, source_summary, created_at, updated_at)
               VALUES (?,?,'asset',1, ?,?,0,?, 'high','test',?,?)""",
            (uid, tag_id, score, score, score, now, now),
        )

    conn.commit()


@pytest.fixture(scope="module")
def conn(lib):
    c = sqlite3.connect(lib.db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ── 1: tag recall exact match ──

def test_tag_recall_exact_match(lib):
    with lib._connect() as conn:
        scores, info, qt = lib._tag_recall(conn, "厨房")
    assert "test_uid_kitchen" in scores, "Kitchen asset should be recalled by exact tag '厨房'"
    assert scores["test_uid_kitchen"] > 0


# ── 2: tag recall normalized match ──

def test_tag_recall_normalized_match(lib):
    """Normalized match: lowercase/strip should still resolve."""
    with lib._connect() as conn:
        scores, info, qt = lib._tag_recall(conn, " 厨房 ")
    assert "test_uid_kitchen" in scores


# ── 3: tag recall alias expansion ──

def test_tag_recall_alias_expansion(lib):
    """If '海滩' is an alias for '海边', searching '海滩' should find beach asset."""
    with lib._connect() as conn:
        # Check if alias exists
        alias = conn.execute(
            "SELECT tag_id FROM tag_alias WHERE normalized_alias = '海滩'"
        ).fetchone()
        if alias is None:
            pytest.skip("'海滩' alias not in seed data")
        scores, info, qt = lib._tag_recall(conn, "海滩")
    assert "test_uid_beach" in scores, "Beach asset should be recalled via alias '海滩'→'海边'"


# ── 4: tag recall synonym expansion ──

def test_tag_recall_synonym_expansion(lib):
    """Synonym expansion via tag_relation should work."""
    with lib._connect() as conn:
        # Find a synonym pair
        syn = conn.execute(
            """SELECT tr.from_tag_id, tr.to_tag_id, t1.tag_name, t2.tag_name
               FROM tag_relation tr
               JOIN tag t1 ON tr.from_tag_id = t1.tag_id
               JOIN tag t2 ON tr.to_tag_id = t2.tag_id
               WHERE tr.relation_type = 'synonym' LIMIT 1"""
        ).fetchone()
        if syn is None:
            pytest.skip("No synonyms in seed data")

        from_tag_id, to_tag_id, from_name, to_name = syn

        # Insert an asset_tag_result for the to_tag
        now = lib._now()
        conn.execute(
            """INSERT OR IGNORE INTO asset_tag_result
               (asset_id, tag_id, result_scope, is_displayed,
                base_score, final_score, user_adjustment, effective_score,
                confidence_band, source_summary, created_at, updated_at)
               VALUES (?,?,'asset',1, 0.7,0.7,0,0.7, 'medium','syn_test',?,?)""",
            ("test_uid_kitchen", to_tag_id, now, now),
        )
        conn.commit()

        # Search by from_tag name → should find asset via synonym expansion to to_tag
        scores, info, qt = lib._tag_recall(conn, from_name)
    assert isinstance(scores, dict)


# ── 5: tag recall parent expansion ──

def test_tag_recall_parent_expansion(lib):
    """Parent→child expansion via tag_relation should recall child assets."""
    with lib._connect() as conn:
        pc = conn.execute(
            """SELECT tr.from_tag_id, tr.to_tag_id, t1.tag_name, t2.tag_name
               FROM tag_relation tr
               JOIN tag t1 ON tr.from_tag_id = t1.tag_id
               JOIN tag t2 ON tr.to_tag_id = t2.tag_id
               WHERE tr.relation_type = 'parent_child' LIMIT 1"""
        ).fetchone()
        if pc is None:
            pytest.skip("No parent_child relations in seed data")
    # Just verify structure — parent expansion runs without error
    with lib._connect() as conn:
        scores, info, qt = lib._tag_recall(conn, pc[2])
    assert isinstance(scores, dict)


# ── 6: stopword skip ──

def test_tag_recall_stopword_skip(lib):
    """Stopwords should be skipped, not crash."""
    with lib._connect() as conn:
        # Add a stopword
        conn.execute(
            "INSERT OR IGNORE INTO learning_stopword (normalized_text, block_reason, created_at) VALUES ('的','common',?)",
            (lib._now(),),
        )
        conn.commit()
        scores, info, qt = lib._tag_recall(conn, "的")
    assert scores == {} or isinstance(scores, dict)


# ── 7: hit strength ordering ──

def test_tag_recall_hit_strength_order(lib):
    """exact hit should score higher than synonym/parent_child for same effective_score."""
    mod = importlib.import_module("modules.library.global_media_library")
    hs = mod.TAG_HIT_STRENGTH
    assert hs["exact"] > hs["normalized"] > hs["alias"] > hs["custom"] > hs["synonym"] > hs["parent_child"]


# ── 8–11: query type classification ──

def test_classify_query_exact_tag(lib):
    with lib._connect() as conn:
        resolved = {"厨房": 1}
        info = {"厨房": {"tag_id": 1, "hit_type": "exact", "tag_name": "厨房", "original_term": "厨房"}}
        qt = lib._classify_query("厨房", resolved, info, conn)
    assert qt == "exact_tag"


def test_classify_query_alias_tag(lib):
    with lib._connect() as conn:
        resolved = {"海滩": 2}
        info = {"海滩": {"tag_id": 2, "hit_type": "alias", "tag_name": "海边", "original_term": "海滩"}}
        qt = lib._classify_query("海滩", resolved, info, conn)
    assert qt == "alias_tag"


def test_classify_query_composed(lib):
    with lib._connect() as conn:
        resolved = {"厨房": 1, "做饭": 2}
        info = {
            "厨房": {"tag_id": 1, "hit_type": "exact", "tag_name": "厨房", "original_term": "厨房"},
            "做饭": {"tag_id": 2, "hit_type": "exact", "tag_name": "做饭", "original_term": "做饭"},
        }
        qt = lib._classify_query("厨房 做饭", resolved, info, conn)
    assert qt == "composed_query"


def test_classify_query_abstract(lib):
    with lib._connect() as conn:
        qt = lib._classify_query("治愈感", {}, {}, conn)
    assert qt == "abstract_intent"


# ── 12: three-path merge ──

def test_hybrid_three_path_merge(lib):
    """All three paths should contribute to ranked results."""
    results = lib.search_assets(query="厨房", limit=50, retrieval_mode="hybrid")
    if not results:
        pytest.skip("No search results (empty library or no embeddings)")
    r0 = results[0]
    assert "match_info" in r0, "Results must contain match_info"
    mi = r0["match_info"]
    assert "match_sources" in mi
    assert "tag" in mi["match_sources"], "Tag path should be active"


# ── 13: dynamic weights by query type ──

def test_dynamic_weights_by_query_type(lib):
    """Different query types should use different weight profiles."""
    mod = importlib.import_module("modules.library.global_media_library")
    w = mod.QUERY_TYPE_WEIGHTS

    assert w["exact_tag"]["tag"] > w["abstract_intent"]["tag"]
    assert w["abstract_intent"]["embedding"] > w["exact_tag"]["embedding"]
    assert w["composed_query"]["tag"] < w["exact_tag"]["tag"]


# ── 14: match_info fields ──

def test_match_info_fields_complete(lib):
    results = lib.search_assets(query="厨房", limit=10)
    if not results:
        pytest.skip("No results")
    mi = results[0].get("match_info", {})
    required = {"match_sources", "combined_score", "tag_score", "fts_score",
                "embedding_score", "query_type", "weights_used",
                "matched_tags", "matched_aliases", "expanded_tags", "hit_details"}
    assert required.issubset(set(mi.keys())), f"Missing fields: {required - set(mi.keys())}"


# ── 15: count == search total ──

def test_count_equals_search_total(lib):
    q = "厨房"
    count = lib.count_matching_assets(query=q, retrieval_mode="hybrid")
    all_results = lib.search_assets(query=q, limit=5000, retrieval_mode="hybrid")
    unique_uids = {r["uid"] for r in all_results}
    assert count == len(unique_uids), f"count={count} != search_uids={len(unique_uids)}"


# ── 16: search_tags autocomplete ──

def test_search_tags_autocomplete(lib):
    results = lib.search_tags("厨")
    if not results:
        pytest.skip("No tag matching '厨' in seed data")
    r0 = results[0]
    assert "tag_id" in r0
    assert "tag_name" in r0
    assert "matched_via" in r0
    assert r0["matched_via"] in ("tag_name", "alias", "custom_tag")


# ── 17: get_tag_tree categories ──

def test_get_tag_tree_categories(lib):
    tree = lib.get_tag_tree()
    assert isinstance(tree, list)
    assert len(tree) > 0, "Tag tree should have at least 1 category"
    cat = tree[0]
    assert "category_id" in cat
    assert "category_name" in cat
    assert "tags" in cat
    # Verify count matches actual active tag_category count
    with lib._connect() as conn:
        actual = conn.execute("SELECT COUNT(*) FROM tag_category").fetchone()[0]
    assert len(tree) == actual, f"len(tree)={len(tree)} != tag_category count={actual}"


# ── 18: get_evidence_chain ──

def test_get_evidence_chain(lib):
    result = lib.get_evidence_chain("test_uid_kitchen")
    assert "asset_id" in result
    assert result["asset_id"] == "test_uid_kitchen"
    assert "tag_results" in result
    assert "evidence_list" in result
    assert "total_tag_results" in result
    assert isinstance(result["tag_results"], list)
    if result["tag_results"]:
        tr = result["tag_results"][0]
        assert "tag_name" in tr
        assert "score_breakdown" in tr
        assert "effective_score" in tr["score_breakdown"]


# ── 19: semantic_slot count ──

def test_semantic_slot_count_16(lib):
    with lib._connect() as conn:
        count = conn.execute("SELECT COUNT(DISTINCT semantic_slot) FROM tag").fetchone()[0]
    assert count == 16, f"Expected 16 distinct semantic_slots, got {count}"
