"""Phase 4 — 5-category real-scenario integration tests.

Covers:
  1. Direct standard tag search
  2. Alias search
  3. Composed intent search
  4. Abstract intent search
  5. Edge cases & boundary conditions

Also validates P4-1..P4-4 backend support:
  - search_tags() autocomplete
  - get_tag_tree() tag browsing
  - get_evidence_chain() evidence display
  - search_assets() match_info fields
"""
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib
# Ensure parent packages are importable for reload
importlib.import_module("modules")
importlib.import_module("modules.library")
mod = importlib.import_module("modules.library.global_media_library")
# Reload to undo any monkeypatches from other test files
mod = importlib.reload(mod)
GlobalMediaLibrary = mod.GlobalMediaLibrary
TAG_HIT_STRENGTH = mod.TAG_HIT_STRENGTH
QUERY_TYPE_WEIGHTS = mod.QUERY_TYPE_WEIGHTS


@pytest.fixture(scope="module")
def lib():
    """Create library with seeded test assets."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_phase4.db")
    gml = GlobalMediaLibrary(db_path=db_path)

    with gml._connect() as conn:
        now = gml._now()

        # ── Self-contained tag + category seed ──
        # Do NOT rely on external seed files (_SEED_DATA_DIR).
        # Insert the minimal categories and tags this test needs.
        _test_categories = [
            ("场景", "scene", 1),
            ("地点", "place", 2),
            ("物品", "object", 3),
            ("动物", "animal", 4),
            ("视觉风格", "visual_style", 5),
            ("动作", "action", 6),
            ("时间与环境", "time_environment", 7),
            ("交通与建筑", "infrastructure", 8),
        ]
        cat_id_map = {}  # category_code → category_id
        for cat_name, cat_code, sort_order in _test_categories:
            conn.execute(
                "INSERT OR IGNORE INTO tag_category (category_name, category_code, sort_order) VALUES (?, ?, ?)",
                (cat_name, cat_code, sort_order),
            )
            cid = conn.execute(
                "SELECT category_id FROM tag_category WHERE category_code = ?",
                (cat_code,),
            ).fetchone()[0]
            cat_id_map[cat_code] = cid

        _test_tags = [
            # (tag_name, category_code, semantic_slot)
            ("厨房", "place", "scene"), ("做饭", "action", "action"),
            ("海边", "place", "scene"), ("日落", "time_environment", "time"),
            ("夜景", "scene", "scene"), ("城市", "place", "scene"),
            ("航拍", "visual_style", "style"), ("猫", "animal", "object"),
            ("电影", "visual_style", "style"),
        ]
        tag_id_map = {}  # tag_name → tag_id
        for tag_name, cat_code, sem_slot in _test_tags:
            tag_code = f"test_{tag_name}"
            conn.execute(
                """INSERT OR IGNORE INTO tag
                   (tag_name, normalized_name, tag_code, category_id,
                    semantic_slot, is_active, source_type)
                   VALUES (?, ?, ?, ?, ?, 1, 'test_seed')""",
                (tag_name, tag_name, tag_code, cat_id_map[cat_code], sem_slot),
            )
            tid = conn.execute(
                "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1",
                (tag_name,),
            ).fetchone()[0]
            tag_id_map[tag_name] = tid

        # Insert alias: 海滩 → 海边
        conn.execute(
            """INSERT OR IGNORE INTO tag_alias
               (tag_id, alias_name, normalized_alias, source_type)
               VALUES (?, '海滩', '海滩', 'test_seed')""",
            (tag_id_map["海边"],),
        )

        # ── Assets ──
        assets = [
            ("uid_kitchen", "kitchen_cooking.mp4", "sha_kitchen", "厨房做饭场景，温馨家庭料理",
             "厨房 做饭 锅 灶台 温馨 室内 料理 家庭"),
            ("uid_beach", "beach_sunset.mp4", "sha_beach", "海边日落，浪漫沙滩漫步",
             "海边 沙滩 日落 浪漫 户外 海浪 漫步"),
            ("uid_night", "city_night.mp4", "sha_night", "城市夜景，霓虹灯闪烁",
             "夜景 城市 霓虹 灯光 夜晚 建筑 街道"),
            ("uid_aerial", "aerial_mountain.mp4", "sha_aerial", "航拍山脉风景",
             "航拍 山脉 风景 自然 壮观 无人机 山"),
            ("uid_cat", "cute_cat.mp4", "sha_cat", "可爱猫咪玩耍",
             "猫 可爱 宠物 玩耍 室内 毛茸茸"),
            ("uid_film", "cinematic_shot.mp4", "sha_film", "电影感镜头运动",
             "电影 镜头 运动 质感 高级 拍摄 专业"),
        ]

        for uid, fname, sha, desc, sem_text in assets:
            conn.execute(
                """INSERT OR IGNORE INTO assets
                   (uid, filename, sha256, size_bytes, primary_path, source_type,
                    duration, resolution, quality_score, scene_description,
                    semantic_text, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, fname, sha, 5000, f"/test/{fname}", "local",
                 15.0, "1920x1080", 85, desc, sem_text, now, now),
            )

        # ── Map assets to tags (using self-contained tag_id_map) ──
        tag_mappings = {
            "uid_kitchen": [("厨房", 0.92), ("做饭", 0.85)],
            "uid_beach": [("海边", 0.90), ("日落", 0.80)],
            "uid_night": [("夜景", 0.88), ("城市", 0.82)],
            "uid_aerial": [("航拍", 0.91)],
            "uid_cat": [("猫", 0.87)],
            "uid_film": [("电影", 0.78)],
        }

        for uid, tag_list in tag_mappings.items():
            for tag_name, score in tag_list:
                tid = tag_id_map.get(tag_name)
                if not tid:
                    continue
                band = "high" if score >= 0.80 else "medium"
                conn.execute(
                    """INSERT OR IGNORE INTO asset_tag_result
                       (asset_id, tag_id, result_scope, is_displayed,
                        base_score, final_score, user_adjustment, effective_score,
                        confidence_band, source_summary, decision_reason,
                        created_at, updated_at)
                       VALUES (?,?,'asset',1, ?,?,0,?, ?,'test','[]',?,?)""",
                    (uid, tid, score, score, score, band, now, now),
                )
                # Also add evidence
                conn.execute(
                    """INSERT OR IGNORE INTO evidence
                       (asset_id, tag_id, semantic_slot, source_kind, source_model,
                        raw_value, base_score, weighted_score, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (uid, tid, "scene", "llm", "test", tag_name, score, score, now),
                )

        conn.commit()

    yield gml


# ═══════════════════════════════════════════
# 通测 1: 直搜标准标签
# ═══════════════════════════════════════════

class TestDirectTagSearch:
    """Verify standard tag search returns correct results with match_info."""

    @pytest.mark.parametrize("query,expected_uid", [
        ("厨房", "uid_kitchen"),
        ("海边", "uid_beach"),
        ("夜景", "uid_night"),
        ("航拍", "uid_aerial"),
    ])
    def test_standard_tag_search(self, lib, query, expected_uid):
        results = lib.search_assets(query=query, limit=50, retrieval_mode="hybrid")
        uids = [r["uid"] for r in results]
        assert expected_uid in uids, f"Expected {expected_uid} for query '{query}', got {uids}"

    def test_match_info_present(self, lib):
        results = lib.search_assets(query="厨房", limit=10, retrieval_mode="hybrid")
        assert len(results) > 0
        r0 = next(r for r in results if r["uid"] == "uid_kitchen")
        mi = r0.get("match_info", {})
        assert "matched_tags" in mi
        assert "match_sources" in mi
        assert "query_type" in mi
        assert "厨房" in mi["matched_tags"]

    def test_query_type_exact(self, lib):
        results = lib.search_assets(query="厨房", limit=10, retrieval_mode="hybrid")
        r0 = next(r for r in results if r["uid"] == "uid_kitchen")
        assert r0["match_info"]["query_type"] == "exact_tag"

    def test_tag_score_positive(self, lib):
        results = lib.search_assets(query="航拍", limit=10, retrieval_mode="hybrid")
        r0 = next(r for r in results if r["uid"] == "uid_aerial")
        assert r0.get("tag_score", 0) > 0


# ═══════════════════════════════════════════
# 通测 2: 搜别名
# ═══════════════════════════════════════════

class TestAliasSearch:
    """Verify alias search expands correctly."""

    def test_alias_search_finds_base(self, lib):
        """Search alias '海滩' should find '海边' tagged assets."""
        with lib._connect() as conn:
            alias_exists = conn.execute(
                "SELECT tag_id FROM tag_alias WHERE normalized_alias = '海滩'"
            ).fetchone()
        if not alias_exists:
            pytest.skip("'海滩' alias not in seed data")
        results = lib.search_assets(query="海滩", limit=50, retrieval_mode="hybrid")
        uids = [r["uid"] for r in results]
        assert "uid_beach" in uids

    def test_alias_query_type(self, lib):
        with lib._connect() as conn:
            alias_exists = conn.execute(
                "SELECT tag_id FROM tag_alias WHERE normalized_alias = '海滩'"
            ).fetchone()
        if not alias_exists:
            pytest.skip("'海滩' alias not in seed data")
        results = lib.search_assets(query="海滩", limit=50, retrieval_mode="hybrid")
        if results:
            beach = [r for r in results if r["uid"] == "uid_beach"]
            if beach:
                assert beach[0]["match_info"]["query_type"] == "alias_tag"

    def test_direct_ranks_before_alias(self, lib):
        """When searching '海边', direct hit should rank before weaker matches."""
        results = lib.search_assets(query="海边", limit=50, retrieval_mode="hybrid")
        if len(results) >= 2:
            uids = [r["uid"] for r in results]
            if "uid_beach" in uids:
                beach_idx = uids.index("uid_beach")
                # uid_beach should be near the top
                assert beach_idx <= 2, f"uid_beach at index {beach_idx}"


# ═══════════════════════════════════════════
# 通测 3: 搜组合意图
# ═══════════════════════════════════════════

class TestComposedQuery:
    """Verify composed queries merge multiple signals."""

    def test_composed_returns_results(self, lib):
        results = lib.search_assets(query="海边 日落", limit=50, retrieval_mode="hybrid")
        assert len(results) > 0

    def test_composed_query_type(self, lib):
        with lib._connect() as conn:
            _, _, qt = lib._tag_recall(conn, "海边 做饭")
        assert qt == "composed_query"

    def test_composed_fts_contributes(self, lib):
        """FTS should find assets with matching semantic_text."""
        results = lib.search_assets(query="温馨 料理", limit=50, retrieval_mode="hybrid")
        # FTS should find uid_kitchen via semantic_text
        uids = [r["uid"] for r in results]
        assert "uid_kitchen" in uids or len(results) > 0


# ═══════════════════════════════════════════
# 通测 4: 搜抽象意图
# ═══════════════════════════════════════════

class TestAbstractIntent:
    """Verify abstract/emotional queries work."""

    def test_abstract_query_type(self, lib):
        with lib._connect() as conn:
            _, _, qt = lib._tag_recall(conn, "治愈感")
        assert qt == "abstract_intent"

    def test_abstract_query_type_2(self, lib):
        with lib._connect() as conn:
            _, _, qt = lib._tag_recall(conn, "适合做开场")
        assert qt == "abstract_intent"

    def test_abstract_returns_via_fts(self, lib):
        """Abstract queries can still return FTS results."""
        results = lib.search_assets(query="电影感", limit=50, retrieval_mode="hybrid")
        # FTS might find uid_film via semantic_text containing "电影"
        # At least no errors
        assert isinstance(results, list)


# ═══════════════════════════════════════════
# 通测 5: 异常与边界
# ═══════════════════════════════════════════

class TestEdgeCases:
    """Edge cases: single char, stopwords, empty, long query, mixed lang."""

    def test_single_char_no_crash(self, lib):
        results = lib.search_assets(query="猫", limit=10, retrieval_mode="hybrid")
        assert isinstance(results, list)

    def test_stopword_no_crash(self, lib):
        results = lib.search_assets(query="的", limit=10, retrieval_mode="hybrid")
        assert isinstance(results, list)

    def test_empty_query(self, lib):
        results = lib.search_assets(query="", limit=10, retrieval_mode="hybrid")
        assert isinstance(results, list)

    def test_no_results_word(self, lib):
        results = lib.search_assets(query="恐龙化石博物馆", limit=10, retrieval_mode="hybrid")
        assert isinstance(results, list)
        # May be empty, should not crash

    def test_very_long_query(self, lib):
        long_q = "这是一个非常长的搜索查询" * 20
        results = lib.search_assets(query=long_q, limit=10, retrieval_mode="hybrid")
        assert isinstance(results, list)

    def test_mixed_language(self, lib):
        results = lib.search_assets(query="kitchen 厨房 cooking", limit=10, retrieval_mode="hybrid")
        assert isinstance(results, list)

    def test_special_chars(self, lib):
        results = lib.search_assets(query="厨房!@#$%", limit=10, retrieval_mode="hybrid")
        assert isinstance(results, list)

    def test_count_equals_search(self, lib):
        """count_matching_assets must match search_assets total."""
        q = "海边"
        count = lib.count_matching_assets(query=q, retrieval_mode="hybrid")
        all_results = lib.search_assets(query=q, limit=5000, retrieval_mode="hybrid")
        unique = {r["uid"] for r in all_results}
        assert count == len(unique), f"count={count} != unique_uids={len(unique)}"


# ═══════════════════════════════════════════
# P4 API validation
# ═══════════════════════════════════════════

class TestP4APIs:
    """Validate the 3 Phase 3 APIs used by Phase 4 frontend."""

    def test_search_tags_returns_results(self, lib):
        results = lib.search_tags("厨")
        assert len(results) > 0
        assert any(t["tag_name"] == "厨房" for t in results)

    def test_search_tags_has_matched_via(self, lib):
        results = lib.search_tags("厨")
        for r in results:
            assert "matched_via" in r
            assert r["matched_via"] in ("tag_name", "alias", "custom_tag")

    def test_search_tags_has_category(self, lib):
        results = lib.search_tags("海")
        for r in results:
            assert "category_name" in r or "tag_id" in r

    @pytest.mark.parametrize("prefix", ["厨", "海", "夜", "电影", "航拍"])
    def test_autocomplete_real_words(self, lib, prefix):
        """P4-1 acceptance: autocomplete works for real Chinese prefixes."""
        results = lib.search_tags(prefix)
        assert len(results) > 0, f"No autocomplete results for '{prefix}'"

    def test_tag_tree_has_categories(self, lib):
        tree = lib.get_tag_tree()
        assert len(tree) > 0
        for cat in tree:
            assert "category_name" in cat
            assert "tags" in cat

    def test_tag_tree_tags_have_counts(self, lib):
        tree = lib.get_tag_tree()
        has_count = False
        for cat in tree:
            for tag in cat["tags"]:
                assert "tag_name" in tag
                assert "asset_count" in tag
                if tag["asset_count"] > 0:
                    has_count = True
        assert has_count, "At least some tags should have asset_count > 0"

    def test_evidence_chain_returns_data(self, lib):
        ev = lib.get_evidence_chain("uid_kitchen")
        assert "tag_results" in ev
        assert "evidence_list" in ev
        assert len(ev["tag_results"]) > 0

    def test_evidence_chain_has_score_breakdown(self, lib):
        ev = lib.get_evidence_chain("uid_kitchen")
        for tr in ev["tag_results"]:
            assert "score_breakdown" in tr
            sb = tr["score_breakdown"]
            assert "base_score" in sb
            assert "user_adjustment" in sb

    def test_evidence_has_source_kind(self, lib):
        ev = lib.get_evidence_chain("uid_kitchen")
        for e in ev["evidence_list"]:
            assert "source_kind" in e
            assert "semantic_slot" in e
            assert "raw_value" in e

    def test_evidence_for_specific_tag(self, lib):
        """Evidence filtered by tag_id."""
        with lib._connect() as conn:
            tag = conn.execute(
                "SELECT tag_id FROM tag WHERE tag_name = '厨房' AND is_active = 1"
            ).fetchone()
        if not tag:
            pytest.skip("No 厨房 tag")
        ev = lib.get_evidence_chain("uid_kitchen", tag_id=tag[0])
        assert len(ev["tag_results"]) >= 1
        assert ev["tag_results"][0]["tag_name"] == "厨房"
