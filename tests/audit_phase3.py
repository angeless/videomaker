"""Phase 3 audit — 7 user-perceivable verification checks.

Usage:
    python tests/audit_phase3.py

Requires seed data directory: ~/Downloads/语义数据库-chatgpt-20260306
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib

_mod_name = "modules.library.global_media_library"
if _mod_name in sys.modules:
    _mod = sys.modules[_mod_name]
    if not hasattr(_mod, "SCORING_CONFIG"):
        del sys.modules[_mod_name]

# Ensure parent packages are importable for reload
importlib.import_module("modules")
importlib.import_module("modules.library")
mod = importlib.import_module(_mod_name)
# Reload to undo any monkeypatches from other test files
mod = importlib.reload(mod)
GlobalMediaLibrary = mod.GlobalMediaLibrary
TAG_HIT_STRENGTH = mod.TAG_HIT_STRENGTH
QUERY_TYPE_WEIGHTS = mod.QUERY_TYPE_WEIGHTS

# ── Check seed data ──
_SEED_DIR = Path(os.path.expanduser("~/Downloads/语义数据库-chatgpt-20260306"))
if not _SEED_DIR.exists():
    print(f"SKIP: Seed data directory not found: {_SEED_DIR}")
    sys.exit(0)

PASS = 0
FAIL = 0
SKIP = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: {detail}")


def skip(name, reason):
    global SKIP
    SKIP += 1
    print(f"  ⏭️  {name}: {reason}")


def seed_audit_assets(gml, conn):
    """Insert test assets + tag results for audit verification."""
    now = gml._now()

    # Asset A: kitchen — will have tag "厨房" (exact match)
    conn.execute(
        """INSERT OR IGNORE INTO assets
           (uid, filename, sha256, size_bytes, primary_path, source_type,
            duration, resolution, quality_score, scene_description, mood,
            objects_json, semantic_json, semantic_text, keywords_json,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("audit_kitchen", "kitchen_video.mp4", "sha_audit_kitchen", 2000,
         "/test/kitchen_video.mp4", "local", 15.0, "1920x1080", 85,
         "厨房做饭场景", "温馨",
         '["锅","灶台"]', '{}', "厨房 做饭 锅 灶台 温馨 室内", '["厨房","做饭"]',
         now, now),
    )

    # Asset B: beach — will have tag "海边" (for alias test "海滩"→"海边")
    conn.execute(
        """INSERT OR IGNORE INTO assets
           (uid, filename, sha256, size_bytes, primary_path, source_type,
            duration, resolution, quality_score, scene_description, mood,
            objects_json, semantic_json, semantic_text, keywords_json,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("audit_beach", "beach_sunset.mp4", "sha_audit_beach", 3000,
         "/test/beach_sunset.mp4", "local", 20.0, "1920x1080", 90,
         "海边日落", "浪漫",
         '["沙滩","海浪"]', '{}', "海边 沙滩 日落 浪漫 户外", '["海边","日落"]',
         now, now),
    )

    # Asset C: sand beach — will have synonym tag "沙滩" (synonym of "海边")
    conn.execute(
        """INSERT OR IGNORE INTO assets
           (uid, filename, sha256, size_bytes, primary_path, source_type,
            duration, resolution, quality_score, scene_description, mood,
            objects_json, semantic_json, semantic_text, keywords_json,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("audit_sand", "sand_beach.mp4", "sha_audit_sand", 2500,
         "/test/sand_beach.mp4", "local", 12.0, "1920x1080", 75,
         "沙滩玩耍", "欢乐",
         '["沙子","贝壳"]', '{}', "沙滩 贝壳 玩耍 户外 海边", '["沙滩","贝壳"]',
         now, now),
    )

    # Now resolve tags and create asset_tag_result entries
    kitchen_tag = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '厨房' AND is_active = 1"
    ).fetchone()
    beach_tag = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '海边' AND is_active = 1"
    ).fetchone()
    sand_tag = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '沙滩' AND is_active = 1"
    ).fetchone()
    cooking_tag = conn.execute(
        "SELECT tag_id FROM tag WHERE tag_name = '做饭' AND is_active = 1"
    ).fetchone()

    tag_mappings = []
    if kitchen_tag:
        tag_mappings.append(("audit_kitchen", kitchen_tag[0], 0.88, "llm"))
    if cooking_tag:
        tag_mappings.append(("audit_kitchen", cooking_tag[0], 0.75, "llm"))
    if beach_tag:
        tag_mappings.append(("audit_beach", beach_tag[0], 0.92, "llm"))
        tag_mappings.append(("audit_sand", beach_tag[0], 0.60, "llm"))  # sand also has beach tag (weaker)
    if sand_tag:
        tag_mappings.append(("audit_sand", sand_tag[0], 0.85, "llm"))

    for uid, tag_id, score, source in tag_mappings:
        band = "high" if score >= 0.80 else "medium" if score >= 0.55 else "low"
        conn.execute(
            """INSERT OR IGNORE INTO asset_tag_result
               (asset_id, tag_id, result_scope, is_displayed,
                base_score, final_score, user_adjustment, effective_score,
                confidence_band, source_summary, decision_reason, created_at, updated_at)
               VALUES (?,?,'asset',1, ?,?,0,?, ?,'llm','[]',?,?)""",
            (uid, tag_id, score, score, score, band, now, now),
        )

    # Also seed some evidence for kitchen asset
    if kitchen_tag:
        conn.execute(
            """INSERT OR IGNORE INTO evidence
               (asset_id, tag_id, semantic_slot, source_kind, source_model,
                raw_value, base_score, weighted_score, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            ("audit_kitchen", kitchen_tag[0], "scene", "llm", "test_model",
             "厨房", 0.88, 0.88, now),
        )

    conn.commit()
    return {
        "kitchen_tag": kitchen_tag[0] if kitchen_tag else None,
        "beach_tag": beach_tag[0] if beach_tag else None,
        "sand_tag": sand_tag[0] if sand_tag else None,
        "cooking_tag": cooking_tag[0] if cooking_tag else None,
    }


def main():
    global PASS, FAIL, SKIP

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "audit_phase3.db")
        gml = GlobalMediaLibrary(db_path=db_path)

        with gml._connect() as conn:
            tag_ids = seed_audit_assets(gml, conn)

        if not tag_ids.get("kitchen_tag"):
            print("FATAL: Could not find '厨房' tag in seed data. Aborting.")
            sys.exit(1)

        # ═══════════════════════════════════════════
        # 验证 1: 搜规范标签 "厨房" → tag 路径命中
        # ═══════════════════════════════════════════
        print("\n验证 1: 搜规范标签 '厨房' → tag 路径命中")
        results = gml.search_assets(query="厨房", limit=50, retrieval_mode="hybrid")
        check("搜索结果非空", len(results) > 0, f"got {len(results)} results")

        if results:
            kitchen_results = [r for r in results if r.get("uid") == "audit_kitchen"]
            check("audit_kitchen 在结果中", len(kitchen_results) > 0)

            if kitchen_results:
                r0 = kitchen_results[0]
                mi = r0.get("match_info", {})
                check("match_info 存在", bool(mi))
                check("matched_tags 含 '厨房'",
                      "厨房" in mi.get("matched_tags", []),
                      f"matched_tags={mi.get('matched_tags')}")
                check("tag_score > 0",
                      r0.get("tag_score", 0) > 0,
                      f"tag_score={r0.get('tag_score')}")
                check("query_type == 'exact_tag'",
                      mi.get("query_type") == "exact_tag",
                      f"query_type={mi.get('query_type')}")
            else:
                for _ in range(4):
                    skip("...", "audit_kitchen not found in results")
        else:
            for _ in range(5):
                skip("...", "no search results")

        # ═══════════════════════════════════════════
        # 验证 2: 搜 alias "海滩" → 扩展命中 "海边"
        # ═══════════════════════════════════════════
        print("\n验证 2: 搜 alias '海滩' → 扩展命中 '海边'")
        with gml._connect() as conn:
            alias_exists = conn.execute(
                "SELECT tag_id FROM tag_alias WHERE normalized_alias = '海滩'"
            ).fetchone()

        if not alias_exists:
            skip("alias '海滩' 存在", "海滩 alias not in seed data")
            skip("tag 路径命中", "skipped")
            skip("matched_aliases 含 '海滩'", "skipped")
            skip("query_type == 'alias_tag'", "skipped")
        else:
            results2 = gml.search_assets(query="海滩", limit=50, retrieval_mode="hybrid")
            check("搜索结果非空", len(results2) > 0, f"got {len(results2)} results")

            if results2:
                beach_results = [r for r in results2 if r.get("uid") == "audit_beach"]
                check("audit_beach 在结果中 (via alias)", len(beach_results) > 0)

                if beach_results:
                    mi2 = beach_results[0].get("match_info", {})
                    check("matched_aliases 含 '海滩'",
                          "海滩" in mi2.get("matched_aliases", []),
                          f"matched_aliases={mi2.get('matched_aliases')}")
                    check("query_type == 'alias_tag'",
                          mi2.get("query_type") == "alias_tag",
                          f"query_type={mi2.get('query_type')}")
                else:
                    skip("matched_aliases", "beach not found")
                    skip("query_type", "beach not found")
            else:
                skip("beach in results", "no results")
                skip("matched_aliases", "no results")
                skip("query_type", "no results")

        # ═══════════════════════════════════════════
        # 验证 3: 三路融合真跑真合并
        # ═══════════════════════════════════════════
        print("\n验证 3: 三路融合真跑真合并")
        results3 = gml.search_assets(query="厨房", limit=50, retrieval_mode="hybrid")
        if results3:
            has_tag_nonzero = any(r.get("tag_score", 0) > 0 for r in results3)
            has_fts_nonzero = any(r.get("keyword_score", 0) > 0 for r in results3)
            # embedding may not be available in test env
            has_emb_nonzero = any(r.get("vector_score", 0) > 0 for r in results3)

            check("tag 路径有非零结果", has_tag_nonzero, "no tag_score > 0")
            check("FTS5 路径有非零结果", has_fts_nonzero, "no keyword_score > 0")
            if has_emb_nonzero:
                check("embedding 路径有非零结果", True)
            else:
                skip("embedding 路径有非零结果", "no embedding model loaded (expected in test env)")

            # Check match_sources
            r0_mi = results3[0].get("match_info", {})
            check("match_sources 含 'tag'",
                  "tag" in r0_mi.get("match_sources", []),
                  f"match_sources={r0_mi.get('match_sources')}")
        else:
            skip("三路融合", "no results")

        # ═══════════════════════════════════════════
        # 验证 4: 直接命中排在扩展命中之前
        # ═══════════════════════════════════════════
        print("\n验证 4: 直接命中排在扩展命中之前")
        # Search "海边" — audit_beach has exact tag "海边" (0.92), audit_sand has synonym
        results4 = gml.search_assets(query="海边", limit=50, retrieval_mode="hybrid")
        if results4 and tag_ids.get("beach_tag"):
            beach_uids = [r["uid"] for r in results4 if r["uid"] in ("audit_beach", "audit_sand")]
            if len(beach_uids) >= 2:
                beach_idx = beach_uids.index("audit_beach") if "audit_beach" in beach_uids else 999
                sand_idx = beach_uids.index("audit_sand") if "audit_sand" in beach_uids else 999
                check("audit_beach (exact) 排在 audit_sand (weaker) 前",
                      beach_idx < sand_idx,
                      f"beach_idx={beach_idx}, sand_idx={sand_idx}")
            elif "audit_beach" in beach_uids:
                check("audit_beach (exact) 在结果中", True)
                skip("排序对比", "audit_sand not in results (only exact hit)")
            else:
                skip("排序对比", f"beach_uids={beach_uids}")
        else:
            skip("排序对比", "no results or no beach_tag")

        # ═══════════════════════════════════════════
        # 验证 5: query_type 权重真实参与
        # ═══════════════════════════════════════════
        print("\n验证 5: query_type 权重真实参与")

        # exact_tag: "厨房"
        r5a = gml.search_assets(query="厨房", limit=10, retrieval_mode="hybrid")
        qt5a = r5a[0]["match_info"]["query_type"] if r5a and r5a[0].get("match_info") else None
        w5a = r5a[0]["match_info"].get("weights_used", {}) if r5a and r5a[0].get("match_info") else {}
        check("'厨房' → exact_tag", qt5a == "exact_tag", f"qt={qt5a}")

        # composed_query: "海边 做饭"
        r5b = gml.search_assets(query="海边 做饭", limit=10, retrieval_mode="hybrid")
        if r5b and r5b[0].get("match_info"):
            qt5b = r5b[0]["match_info"]["query_type"]
            w5b = r5b[0]["match_info"].get("weights_used", {})
            check("'海边 做饭' → composed_query", qt5b == "composed_query", f"qt={qt5b}")
        else:
            skip("'海边 做饭' → composed_query", "no results")

        # abstract_intent: "治愈感"
        r5c = gml.search_assets(query="治愈感", limit=10, retrieval_mode="hybrid")
        # May not have results, but _tag_recall still returns query_type
        with gml._connect() as conn:
            _, _, qt5c = gml._tag_recall(conn, "治愈感")
        check("'治愈感' → abstract_intent", qt5c == "abstract_intent", f"qt={qt5c}")

        # Weights differ
        if w5a and r5b and r5b[0].get("match_info"):
            w5b = r5b[0]["match_info"].get("weights_used", {})
            check("不同 query_type 使用不同权重",
                  w5a.get("tag") != w5b.get("tag"),
                  f"exact_tag.tag={w5a.get('tag')}, composed.tag={w5b.get('tag')}")
        else:
            skip("权重对比", "insufficient results")

        # ═══════════════════════════════════════════
        # 验证 6: count 与 search 一致
        # ═══════════════════════════════════════════
        print("\n验证 6: count 与 search 一致")
        q6 = "厨房"
        count6 = gml.count_matching_assets(query=q6, retrieval_mode="hybrid")
        all6 = gml.search_assets(query=q6, limit=5000, retrieval_mode="hybrid")
        unique6 = {r["uid"] for r in all6}
        check(f"count({count6}) == search_uids({len(unique6)})",
              count6 == len(unique6),
              f"count={count6}, unique_uids={len(unique6)}")

        # ═══════════════════════════════════════════
        # 验证 7: API 方法全通
        # ═══════════════════════════════════════════
        print("\n验证 7: API 方法全通")

        # get_tag_tree
        tree = gml.get_tag_tree()
        with gml._connect() as conn:
            actual_cat_count = conn.execute(
                "SELECT COUNT(*) FROM tag_category WHERE is_active=1"
            ).fetchone()[0]
        check(f"get_tag_tree() → {len(tree)} categories == {actual_cat_count}",
              len(tree) == actual_cat_count)

        # search_tags
        tags_result = gml.search_tags("厨")
        has_kitchen = any(t.get("tag_name") == "厨房" for t in tags_result)
        check("search_tags('厨') 含 '厨房'", has_kitchen,
              f"results={[t.get('tag_name') for t in tags_result[:5]]}")

        # get_evidence_chain
        ev = gml.get_evidence_chain("audit_kitchen")
        check("get_evidence_chain 有 tag_results",
              len(ev.get("tag_results", [])) > 0,
              f"tag_results={len(ev.get('tag_results', []))}")
        check("get_evidence_chain 有 evidence_list",
              len(ev.get("evidence_list", [])) > 0,
              f"evidence_list={len(ev.get('evidence_list', []))}")

        # ═══════════════════════════════════════════
        # Summary
        # ═══════════════════════════════════════════
        print(f"\n{'='*50}")
        print(f"Phase 3 Audit Results: {PASS} passed, {FAIL} failed, {SKIP} skipped")
        print(f"{'='*50}")

        if FAIL > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
