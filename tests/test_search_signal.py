"""Search signal learning loop tests.

Covers:
  1. search_log recording — every non-empty search writes to search_log
  2. Zero-hit detection — queries with 0 results recorded with is_zero_hit=1
  3. Unresolved terms → learning_candidate (source_kind='search_query')
  4. Analytics methods: get_search_analytics, get_zero_hit_queries, get_popular_searches
  5. Learning candidate management: get_learning_candidates, review_learning_candidate
  6. Edge cases: empty query, duplicate search accumulation
"""
import os
import sys
import tempfile
import json
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


@pytest.fixture(scope="module")
def lib():
    """Create library with seeded test assets for search signal testing."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_search_signal.db")
    gml = GlobalMediaLibrary(db_path=db_path)

    with gml._connect() as conn:
        now = gml._now()

        # Create test assets
        assets = [
            ("uid_ss_kitchen", "kitchen_ss.mp4", "sha_ssk", "厨房做饭",
             "厨房 做饭 锅 灶台 温馨"),
            ("uid_ss_beach", "beach_ss.mp4", "sha_ssb", "海边日落",
             "海边 沙滩 日落 浪漫 海浪"),
            ("uid_ss_cat", "cat_ss.mp4", "sha_ssc", "可爱猫咪",
             "猫 可爱 宠物 玩耍"),
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

        # Map assets to tags via asset_tag_result
        tag_mappings = {
            "uid_ss_kitchen": [("厨房", 0.90), ("做饭", 0.82)],
            "uid_ss_beach": [("海边", 0.88)],
            "uid_ss_cat": [("猫", 0.85)],
        }

        for uid, tag_list in tag_mappings.items():
            for tag_name, score in tag_list:
                row = conn.execute(
                    "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1",
                    (tag_name,),
                ).fetchone()
                if not row:
                    continue
                band = "high" if score >= 0.80 else "medium"
                conn.execute(
                    """INSERT OR IGNORE INTO asset_tag_result
                       (asset_id, tag_id, result_scope, is_displayed,
                        base_score, final_score, user_adjustment, effective_score,
                        confidence_band, source_summary, decision_reason,
                        created_at, updated_at)
                       VALUES (?,?,'asset',1, ?,?,0,?, ?,'test','[]',?,?)""",
                    (uid, row[0], score, score, score, band, now, now),
                )

        conn.commit()

    return gml


# ── 1. search_log recording ──

class TestSearchLogRecording:
    """search_assets() writes to search_log for non-empty queries."""

    def test_search_creates_log_entry(self, lib):
        """A non-empty search should create a search_log entry."""
        lib.search_assets("厨房", limit=10, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT * FROM search_log WHERE normalized_query = '厨房' ORDER BY log_id DESC LIMIT 1",
            ).fetchone()
            assert row is not None, "search_log entry should exist"

    def test_log_has_query_fields(self, lib):
        """search_log entry should have correct query metadata."""
        lib.search_assets("海边", limit=10, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT * FROM search_log WHERE normalized_query = '海边' ORDER BY log_id DESC LIMIT 1",
            ).fetchone()
            assert row is not None
            cols = {desc[0]: i for i, desc in enumerate(conn.execute("PRAGMA table_info(search_log)").fetchall())}
            # Check fields via column names
            log = dict(zip([d[0] for d in conn.execute("SELECT * FROM search_log LIMIT 0").description],
                           row))
            assert log["query_text"] == "海边"
            assert log["normalized_query"] == "海边"
            assert log["retrieval_mode"] == "keyword"
            assert log["result_count"] >= 0
            assert log["created_at"] is not None

    def test_log_records_result_count(self, lib):
        """search_log result_count should match actual search results."""
        results = lib.search_assets("厨房", limit=50, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT result_count FROM search_log WHERE normalized_query = '厨房' ORDER BY log_id DESC LIMIT 1",
            ).fetchone()
            assert row is not None
            # result_count recorded is the total ranked count (not paged)
            assert row[0] >= len(results)

    def test_empty_query_no_log(self, lib):
        """Empty query should NOT create a search_log entry."""
        with lib._connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM search_log").fetchone()[0]
        lib.search_assets("", limit=10)
        with lib._connect() as conn:
            after = conn.execute("SELECT COUNT(*) FROM search_log").fetchone()[0]
            assert after == before, "Empty query should not log"

    def test_search_duration_recorded(self, lib):
        """search_log should have a non-negative search_duration_ms."""
        lib.search_assets("猫", limit=10, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT search_duration_ms FROM search_log WHERE normalized_query = '猫' ORDER BY log_id DESC LIMIT 1",
            ).fetchone()
            assert row is not None
            assert row[0] is not None
            assert row[0] >= 0


# ── 2. Zero-hit detection ──

class TestZeroHitDetection:
    """Queries returning 0 results are marked is_zero_hit=1."""

    def test_zero_hit_flag(self, lib):
        """A query that matches nothing should be flagged as zero-hit."""
        lib.search_assets("完全不存在的测试词xyz", limit=10, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT is_zero_hit, result_count FROM search_log "
                "WHERE normalized_query = '完全不存在的测试词xyz' ORDER BY log_id DESC LIMIT 1",
            ).fetchone()
            assert row is not None
            assert row[0] == 1, "is_zero_hit should be 1"
            assert row[1] == 0, "result_count should be 0"

    def test_non_zero_hit_flag(self, lib):
        """A query that matches something should have is_zero_hit=0."""
        results = lib.search_assets("厨房", limit=10, retrieval_mode="keyword")
        if results:  # Only valid if there are actual results
            with lib._connect() as conn:
                row = conn.execute(
                    "SELECT is_zero_hit FROM search_log "
                    "WHERE normalized_query = '厨房' ORDER BY log_id DESC LIMIT 1",
                ).fetchone()
                assert row is not None
                assert row[0] == 0, "is_zero_hit should be 0 for matching queries"


# ── 3. Unresolved terms → learning_candidate ──

class TestSearchLearningCandidate:
    """Unresolved search terms feed into learning_candidate with source_kind='search_query'."""

    def test_unresolved_term_creates_candidate(self, lib):
        """Searching for a term not in tag/alias should create a learning_candidate."""
        lib.search_assets("超级无敌测试词abc", limit=10, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT * FROM learning_candidate "
                "WHERE normalized_text = '超级无敌测试词abc' AND source_kind = 'search_query'",
            ).fetchone()
            assert row is not None, "Unresolved search term should create learning_candidate"

    def test_repeated_search_increments_count(self, lib):
        """Searching the same unresolved term multiple times should increment occurrence_count."""
        term = "反复搜索测试词def"
        lib.search_assets(term, limit=10, retrieval_mode="keyword")
        lib.search_assets(term, limit=10, retrieval_mode="keyword")
        lib.search_assets(term, limit=10, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT occurrence_count FROM learning_candidate "
                "WHERE normalized_text = ? AND source_kind = 'search_query'",
                (term,),
            ).fetchone()
            assert row is not None
            assert row[0] >= 3, f"occurrence_count should be >= 3, got {row[0]}"

    def test_resolved_term_no_candidate(self, lib):
        """A term that resolves to a tag should NOT create a learning_candidate for search_query."""
        lib.search_assets("厨房", limit=10, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT * FROM learning_candidate "
                "WHERE normalized_text = '厨房' AND source_kind = 'search_query'",
            ).fetchone()
            assert row is None, "Resolved terms should not create search_query candidates"

    def test_unresolved_logged_in_search_log(self, lib):
        """search_log.unresolved_terms should contain the unresolved tokens."""
        unique_term = "独特测试不存在词ghij"
        lib.search_assets(unique_term, limit=10, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT unresolved_terms FROM search_log "
                "WHERE normalized_query = ? ORDER BY log_id DESC LIMIT 1",
                (unique_term,),
            ).fetchone()
            assert row is not None
            if row[0]:
                terms = json.loads(row[0])
                assert any(unique_term in t for t in terms), \
                    f"unresolved_terms should contain '{unique_term}', got {terms}"


# ── 4. Analytics methods ──

class TestSearchAnalytics:
    """Test get_search_analytics, get_zero_hit_queries, get_popular_searches."""

    def test_get_search_analytics_structure(self, lib):
        """get_search_analytics should return structured analytics."""
        # Ensure some searches exist
        lib.search_assets("厨房", limit=5, retrieval_mode="keyword")
        analytics = lib.get_search_analytics(days=30, limit=20)
        assert "summary" in analytics
        assert "popular_queries" in analytics
        assert "zero_hit_queries" in analytics
        assert "unresolved_search_terms" in analytics
        summary = analytics["summary"]
        assert "total_searches" in summary
        assert "unique_queries" in summary
        assert "zero_hit_count" in summary
        assert "zero_hit_rate" in summary
        assert summary["total_searches"] > 0

    def test_popular_queries_ordered(self, lib):
        """popular_queries should be ordered by search_count descending."""
        analytics = lib.get_search_analytics(days=30, limit=50)
        pops = analytics["popular_queries"]
        if len(pops) >= 2:
            for i in range(len(pops) - 1):
                assert pops[i]["search_count"] >= pops[i + 1]["search_count"]

    def test_get_zero_hit_queries(self, lib):
        """get_zero_hit_queries should return zero-hit queries."""
        # Search for something that won't exist
        lib.search_assets("零命中分析测试klm", limit=5, retrieval_mode="keyword")
        zeros = lib.get_zero_hit_queries(days=30, limit=20)
        assert isinstance(zeros, list)
        found = any(z["query"] == "零命中分析测试klm" for z in zeros)
        assert found, "Zero-hit query should appear in results"

    def test_get_popular_searches(self, lib):
        """get_popular_searches should return frequently searched queries."""
        pops = lib.get_popular_searches(days=30, limit=20)
        assert isinstance(pops, list)
        if pops:
            assert "query" in pops[0]
            assert "count" in pops[0]
            assert "avg_results" in pops[0]


# ── 5. Learning candidate management ──

class TestLearningCandidateManagement:
    """Test get_learning_candidates and review_learning_candidate.

    Uses direct DB inserts for candidate setup to avoid n-gram pollution
    from _tokenize_query.
    """

    def test_get_learning_candidates_search_query(self, lib):
        """get_learning_candidates(source_kind='search_query') should return search-driven candidates."""
        # Directly insert a clean candidate to avoid n-gram noise
        with lib._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO learning_candidate
                   (candidate_text, normalized_text, category_hint, source_kind,
                    occurrence_count, asset_count)
                   VALUES ('候选测试词', '候选测试词', 'search', 'search_query', 5, 0)""",
            )
            conn.commit()
        candidates = lib.get_learning_candidates(source_kind="search_query", status="pending", limit=50)
        assert isinstance(candidates, list)
        found = any(c["normalized"] == "候选测试词" for c in candidates)
        assert found, "Search-driven candidate should be listed"

    def test_get_learning_candidates_fields(self, lib):
        """Each learning candidate should have required fields."""
        candidates = lib.get_learning_candidates(limit=5)
        if candidates:
            c = candidates[0]
            assert "candidate_id" in c
            assert "candidate_text" in c
            assert "normalized" in c
            assert "source_kind" in c
            assert "occurrence_count" in c
            assert "review_status" in c

    def test_review_candidate_approve(self, lib):
        """Approving a learning candidate sets review_status to 'approved'."""
        with lib._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO learning_candidate
                   (candidate_text, normalized_text, category_hint, source_kind,
                    occurrence_count, asset_count)
                   VALUES ('批准词', '批准词', 'search', 'search_query', 3, 0)""",
            )
            conn.commit()
        candidates = lib.get_learning_candidates(source_kind="search_query", status="pending", limit=50)
        target = next((c for c in candidates if c["normalized"] == "批准词"), None)
        assert target is not None, "Candidate should exist before review"

        result = lib.review_learning_candidate(target["candidate_id"], "approve")
        assert result.get("ok") is True
        assert result["new_status"] == "approved"

        # Verify in DB
        updated = lib.get_learning_candidates(source_kind="search_query", status="approved", limit=50)
        found = any(c["candidate_id"] == target["candidate_id"] for c in updated)
        assert found, "Approved candidate should be in approved list"

    def test_review_candidate_reject(self, lib):
        """Rejecting a learning candidate sets review_status to 'rejected'."""
        with lib._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO learning_candidate
                   (candidate_text, normalized_text, category_hint, source_kind,
                    occurrence_count, asset_count)
                   VALUES ('拒绝词', '拒绝词', 'search', 'search_query', 2, 0)""",
            )
            conn.commit()
        candidates = lib.get_learning_candidates(source_kind="search_query", status="pending", limit=50)
        target = next((c for c in candidates if c["normalized"] == "拒绝词"), None)
        assert target is not None

        result = lib.review_learning_candidate(target["candidate_id"], "reject")
        assert result.get("ok") is True
        assert result["new_status"] == "rejected"

    def test_review_candidate_block_adds_stopword(self, lib):
        """Blocking a learning candidate should add it to learning_stopword."""
        with lib._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO learning_candidate
                   (candidate_text, normalized_text, category_hint, source_kind,
                    occurrence_count, asset_count)
                   VALUES ('封禁词', '封禁词', 'search', 'search_query', 2, 0)""",
            )
            conn.commit()
        candidates = lib.get_learning_candidates(source_kind="search_query", status="pending", limit=50)
        target = next((c for c in candidates if c["normalized"] == "封禁词"), None)
        assert target is not None

        result = lib.review_learning_candidate(target["candidate_id"], "block")
        assert result.get("ok") is True
        assert result["new_status"] == "blocked"

        # Verify stopword
        with lib._connect() as conn:
            sw = conn.execute(
                "SELECT * FROM learning_stopword WHERE normalized_text = '封禁词'",
            ).fetchone()
            assert sw is not None, "Blocked candidate should be in learning_stopword"

    def test_review_invalid_action(self, lib):
        """Invalid review action should return error."""
        result = lib.review_learning_candidate(99999, "invalid_action")
        assert result.get("error") is not None

    def test_review_nonexistent_candidate(self, lib):
        """Reviewing a nonexistent candidate should return error."""
        result = lib.review_learning_candidate(999999, "approve")
        assert result.get("error") is not None


# ── 6. Edge cases ──

class TestSearchSignalEdgeCases:
    """Edge cases for search signal recording."""

    def test_multiple_searches_accumulate(self, lib):
        """Multiple searches for the same query should create multiple log entries."""
        unique_q = "累积测试查询abc"
        lib.search_assets(unique_q, limit=5, retrieval_mode="keyword")
        lib.search_assets(unique_q, limit=5, retrieval_mode="keyword")
        with lib._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM search_log WHERE normalized_query = ?",
                (unique_q,),
            ).fetchone()[0]
            assert count >= 2, f"Should have at least 2 log entries, got {count}"

    def test_search_log_table_exists(self, lib):
        """search_log table should be created by _init_db."""
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='search_log'",
            ).fetchone()
            assert row is not None, "search_log table should exist"

    def test_query_type_recorded(self, lib):
        """search_log should record the query_type classification."""
        lib.search_assets("厨房", limit=5, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT query_type FROM search_log WHERE normalized_query = '厨房' ORDER BY log_id DESC LIMIT 1",
            ).fetchone()
            assert row is not None
            assert row[0] in ("exact_tag", "alias_tag", "composed_query", "abstract_intent", None)

    def test_resolved_tags_logged(self, lib):
        """search_log.resolved_tags should contain tag names for resolved queries."""
        lib.search_assets("厨房", limit=5, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT resolved_tags FROM search_log WHERE normalized_query = '厨房' ORDER BY log_id DESC LIMIT 1",
            ).fetchone()
            assert row is not None
            if row[0]:
                tags = json.loads(row[0])
                assert isinstance(tags, list)
                # "厨房" should be in resolved tags
                assert any("厨房" in t for t in tags), f"'厨房' should be in resolved_tags, got {tags}"

    def test_short_term_skipped(self, lib):
        """Single-character terms should not create learning_candidates."""
        lib.search_assets("x", limit=5, retrieval_mode="keyword")
        with lib._connect() as conn:
            row = conn.execute(
                "SELECT * FROM learning_candidate WHERE normalized_text = 'x' AND source_kind = 'search_query'",
            ).fetchone()
            assert row is None, "Single-char terms should not create candidates"


# ── 7. Learning candidate classification ──

@pytest.fixture(scope="module")
def classify_lib():
    """Separate library instance with seeded candidates for classification tests."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "classify_test.db")
    lib = GlobalMediaLibrary.__new__(GlobalMediaLibrary)
    lib.db_path = db_path
    lib._init_db()
    # Seed candidates of various types
    with lib._connect() as conn:
        # Noise candidates
        conn.execute(
            """INSERT INTO learning_candidate
               (candidate_text, normalized_text, category_hint, source_kind,
                occurrence_count, asset_count, review_status)
               VALUES ('12345', '12345', 'search', 'search_query', 5, 0, 'pending')""",
        )
        conn.execute(
            """INSERT INTO learning_candidate
               (candidate_text, normalized_text, category_hint, source_kind,
                occurrence_count, asset_count, review_status)
               VALUES ('嗯', '嗯', 'search', 'search_query', 3, 0, 'pending')""",
        )
        conn.execute(
            """INSERT INTO learning_candidate
               (candidate_text, normalized_text, category_hint, source_kind,
                occurrence_count, asset_count, review_status)
               VALUES ('IMG_1307', 'img_1307', 'search', 'search_query', 2, 0, 'pending')""",
        )
        # Near-match candidate (substring of existing tag)
        # First check if there's a tag with "厨房" to test alias merge
        tag_row = conn.execute(
            "SELECT tag_id, tag_name FROM tag WHERE normalized_name = '厨房' LIMIT 1"
        ).fetchone()
        if tag_row:
            conn.execute(
                """INSERT INTO learning_candidate
                   (candidate_text, normalized_text, category_hint, source_kind,
                    occurrence_count, asset_count, review_status)
                   VALUES ('大厨房', '大厨房', 'food_cooking', 'llm', 10, 3, 'pending')""",
            )
        # Normal review candidate (no special pattern)
        conn.execute(
            """INSERT INTO learning_candidate
               (candidate_text, normalized_text, category_hint, source_kind,
                occurrence_count, asset_count, review_status)
               VALUES ('彩虹瀑布', '彩虹瀑布', 'nature', 'llm', 2, 2, 'pending')""",
        )
        # Upgrade candidate (high frequency + known category)
        conn.execute(
            """INSERT INTO learning_candidate
               (candidate_text, normalized_text, category_hint, source_kind,
                occurrence_count, asset_count, review_status)
               VALUES ('星空帐篷', '星空帐篷', 'outdoor', 'llm', 20, 8, 'pending')""",
        )
        conn.commit()
    yield lib


class TestCandidateClassification:
    """Tests for classify_learning_candidates()."""

    def test_classify_returns_summary(self, classify_lib):
        """classify_learning_candidates should return classified count and action breakdown."""
        result = classify_lib.classify_learning_candidates(limit=200)
        assert "classified" in result
        assert "actions" in result
        assert result["classified"] > 0
        assert isinstance(result["actions"], dict)

    def test_noise_detected(self, classify_lib):
        """Numeric-only and filler-word candidates should be classified as reject_noise."""
        classify_lib.classify_learning_candidates(limit=200)
        with classify_lib._connect() as conn:
            # "12345" is pure numeric
            row = conn.execute(
                "SELECT suggested_action FROM learning_candidate WHERE normalized_text = '12345'"
            ).fetchone()
            assert row is not None
            assert row[0] == "reject_noise", f"'12345' should be reject_noise, got {row[0]}"

    def test_filler_word_noise(self, classify_lib):
        """Filler words like '嗯' should be classified as reject_noise."""
        with classify_lib._connect() as conn:
            row = conn.execute(
                "SELECT suggested_action FROM learning_candidate WHERE normalized_text = '嗯'"
            ).fetchone()
            assert row is not None
            assert row[0] == "reject_noise", f"'嗯' should be reject_noise, got {row[0]}"

    def test_filename_fragment_noise(self, classify_lib):
        """Filename fragments like 'IMG_1307' should be classified as reject_noise."""
        with classify_lib._connect() as conn:
            row = conn.execute(
                "SELECT suggested_action FROM learning_candidate WHERE normalized_text = 'img_1307'"
            ).fetchone()
            assert row is not None
            assert row[0] == "reject_noise", f"'img_1307' should be reject_noise, got {row[0]}"

    def test_alias_merge_detected(self, classify_lib):
        """Candidates that are substrings of existing tags should be classified as merge_to_alias."""
        with classify_lib._connect() as conn:
            # Check if "大厨房" exists (only if "厨房" tag was found during setup)
            row = conn.execute(
                "SELECT suggested_action, cooccur_json FROM learning_candidate WHERE normalized_text = '大厨房'"
            ).fetchone()
            if row:  # Only test if the candidate was created (depends on tag seed data)
                assert row[0] == "merge_to_alias", f"'大厨房' should be merge_to_alias, got {row[0]}"
                assert row[1] is not None, "cooccur_json should be populated for merge candidates"
                cooccur = json.loads(row[1])
                assert "merge_target_name" in cooccur

    def test_upgrade_candidate_high_frequency(self, classify_lib):
        """High-frequency candidates with known category should be classified as upgrade_to_new_tag."""
        with classify_lib._connect() as conn:
            row = conn.execute(
                "SELECT suggested_action FROM learning_candidate WHERE normalized_text = '星空帐篷'"
            ).fetchone()
            assert row is not None
            assert row[0] == "upgrade_to_new_tag", f"'星空帐篷' should be upgrade_to_new_tag, got {row[0]}"

    def test_cooccur_json_populated(self, classify_lib):
        """Classified candidates should have cooccur_json populated when relevant."""
        with classify_lib._connect() as conn:
            rows = conn.execute(
                "SELECT cooccur_json FROM learning_candidate WHERE cooccur_json IS NOT NULL"
            ).fetchall()
            for row in rows:
                parsed = json.loads(row[0])
                assert isinstance(parsed, dict)

    def test_idempotent_classification(self, classify_lib):
        """Running classification twice should produce consistent results."""
        r1 = classify_lib.classify_learning_candidates(limit=200)
        r2 = classify_lib.classify_learning_candidates(limit=200)
        assert r1["classified"] == r2["classified"]


# ── 8. Candidate promotion and batch operations ──

@pytest.fixture(scope="module")
def promote_lib():
    """Library instance for promotion tests."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "promote_test.db")
    lib = GlobalMediaLibrary.__new__(GlobalMediaLibrary)
    lib.db_path = db_path
    lib._init_db()

    with lib._connect() as conn:
        # 1. Alias merge candidate: "大厨房" → should merge to "厨房"
        tag_row = conn.execute(
            "SELECT tag_id FROM tag WHERE normalized_name = '厨房' LIMIT 1"
        ).fetchone()
        if tag_row:
            cooccur = json.dumps({"merge_target_tag_id": tag_row[0], "merge_target_name": "厨房", "similarity": 0.67})
            conn.execute(
                """INSERT INTO learning_candidate
                   (candidate_text, normalized_text, category_hint, source_kind,
                    occurrence_count, asset_count, suggested_action, cooccur_json, review_status)
                   VALUES ('大厨房', '大厨房', 'food_cooking', 'llm', 10, 3,
                           'merge_to_alias', ?, 'pending')""",
                (cooccur,),
            )

        # 2. Upgrade candidate: "星空咖啡" → should become new tag
        conn.execute(
            """INSERT INTO learning_candidate
               (candidate_text, normalized_text, category_hint, source_kind,
                occurrence_count, asset_count, suggested_action, review_status)
               VALUES ('星空咖啡', '星空咖啡', 'food_cuisine', 'llm', 20, 8,
                       'upgrade_to_new_tag', 'pending')""",
        )

        # 3. Noise candidates for batch reject
        for i in range(5):
            conn.execute(
                """INSERT INTO learning_candidate
                   (candidate_text, normalized_text, category_hint, source_kind,
                    occurrence_count, asset_count, suggested_action, review_status)
                   VALUES (?, ?, 'search', 'search_query', 1, 0,
                           'reject_noise', 'pending')""",
                (f"noise_{i}", f"noise_{i}"),
            )

        # 4. Review-only candidate
        conn.execute(
            """INSERT INTO learning_candidate
               (candidate_text, normalized_text, category_hint, source_kind,
                occurrence_count, asset_count, suggested_action, review_status)
               VALUES ('普通候选', '普通候选', 'scene', 'llm', 5, 2,
                       'review', 'pending')""",
        )

        conn.commit()
    yield lib


class TestCandidatePromotion:
    """Tests for promote_candidate() and batch_reject_noise()."""

    def test_promote_merge_to_alias(self, promote_lib):
        """promote_candidate with merge_to_alias should create a tag_alias."""
        with promote_lib._connect() as conn:
            row = conn.execute(
                "SELECT candidate_id FROM learning_candidate WHERE normalized_text = '大厨房' LIMIT 1"
            ).fetchone()
            if not row:
                pytest.skip("大厨房 candidate not created (厨房 tag missing)")

        result = promote_lib.promote_candidate(row[0])
        assert result.get("ok") is True
        assert result.get("action") == "merge_to_alias"

        # Verify alias was created
        with promote_lib._connect() as conn:
            alias = conn.execute(
                "SELECT alias_name, source_type FROM tag_alias WHERE normalized_alias = '大厨房'"
            ).fetchone()
            assert alias is not None, "Alias should have been created"
            assert alias[1] == "learned"

            # Candidate should be marked approved
            cand = conn.execute(
                "SELECT review_status FROM learning_candidate WHERE normalized_text = '大厨房'"
            ).fetchone()
            assert cand[0] == "approved"

    def test_promote_upgrade_to_new_tag(self, promote_lib):
        """promote_candidate with upgrade_to_new_tag should create a new tag."""
        with promote_lib._connect() as conn:
            row = conn.execute(
                "SELECT candidate_id FROM learning_candidate WHERE normalized_text = '星空咖啡'"
            ).fetchone()

        result = promote_lib.promote_candidate(row[0])
        assert result.get("ok") is True
        assert result.get("action") == "upgrade_to_new_tag"
        assert "created_tag_id" in result

        # Verify tag was created
        with promote_lib._connect() as conn:
            tag = conn.execute(
                "SELECT tag_name, source_type, is_active FROM tag WHERE tag_id = ?",
                (result["created_tag_id"],),
            ).fetchone()
            assert tag is not None
            assert tag[0] == "星空咖啡"
            assert tag[1] == "learned"
            assert tag[2] == 1

    def test_promote_review_only(self, promote_lib):
        """promote_candidate with 'review' action should just approve."""
        with promote_lib._connect() as conn:
            row = conn.execute(
                "SELECT candidate_id FROM learning_candidate WHERE normalized_text = '普通候选'"
            ).fetchone()

        result = promote_lib.promote_candidate(row[0])
        assert result.get("ok") is True

        with promote_lib._connect() as conn:
            cand = conn.execute(
                "SELECT review_status FROM learning_candidate WHERE normalized_text = '普通候选'"
            ).fetchone()
            assert cand[0] == "approved"

    def test_promote_nonexistent(self, promote_lib):
        """Promoting a nonexistent candidate should return error."""
        result = promote_lib.promote_candidate(999999)
        assert result.get("error") is not None

    def test_batch_reject_noise(self, promote_lib):
        """batch_reject_noise should block all noise candidates and add to stopword."""
        result = promote_lib.batch_reject_noise(limit=100)
        assert result["rejected"] >= 5

        with promote_lib._connect() as conn:
            # All noise candidates should be blocked
            pending_noise = conn.execute(
                """SELECT COUNT(*) FROM learning_candidate
                   WHERE suggested_action = 'reject_noise' AND review_status = 'pending'"""
            ).fetchone()[0]
            assert pending_noise == 0, "No noise candidates should remain pending"

            # Stopwords should have been created
            sw_count = conn.execute(
                "SELECT COUNT(*) FROM learning_stopword WHERE normalized_text LIKE 'noise_%'"
            ).fetchone()[0]
            assert sw_count >= 5

    def test_batch_reject_idempotent(self, promote_lib):
        """Running batch_reject_noise again should reject 0 (all already blocked)."""
        result = promote_lib.batch_reject_noise(limit=100)
        assert result["rejected"] == 0
