#!/usr/bin/env python3
"""Phase 2 strict audit: real ingest → SQL evidence verification."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib
_mod_name = "modules.library.global_media_library"
if _mod_name in sys.modules:
    _mod = sys.modules[_mod_name]
    if not hasattr(_mod, "SCORING_CONFIG"):
        del sys.modules[_mod_name]
mod = importlib.import_module(_mod_name)
GlobalMediaLibrary = mod.GlobalMediaLibrary

# ── Config ──
VIDEO_SRC = Path(os.path.expanduser("~/Downloads/0a5bc5f0-c37b-c285-9039-c628dc0b7449_rendition.mp4"))
IMAGE_SRC = Path(os.path.expanduser("~/Downloads/IMG_1728.jpg"))

def prt(label, val=""):
    print(f"  {label}: {val}")

def sql(conn, query, params=()):
    return conn.execute(query, params).fetchall()

def sql1(conn, query, params=()):
    r = conn.execute(query, params).fetchone()
    return r[0] if r else None

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def run_audit():
    tmpdir = tempfile.mkdtemp(prefix="audit_phase2_")
    db_path = os.path.join(tmpdir, "audit.db")

    # Copy files to temp dir to isolate
    video_dir = os.path.join(tmpdir, "videos")
    image_dir = os.path.join(tmpdir, "images")
    os.makedirs(video_dir)
    os.makedirs(image_dir)
    video_file = os.path.join(video_dir, "test_video.mp4")
    image_file = os.path.join(image_dir, "test_image.jpg")
    shutil.copy2(str(VIDEO_SRC), video_file)
    shutil.copy2(str(IMAGE_SRC), image_file)

    print("Phase 2 Strict Audit — Real Ingest Verification")
    print(f"DB: {db_path}")
    print(f"Video: {video_file} ({os.path.getsize(video_file)/1e6:.1f} MB)")
    print(f"Image: {image_file} ({os.path.getsize(image_file)/1e6:.1f} MB)")
    print(f"LLM tagging enabled: {GlobalMediaLibrary._llm_tagging_enabled()}")

    lib = GlobalMediaLibrary(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # ── Ingest A: new video ──
    section("INGEST A: New Video")
    t0 = time.time()
    try:
        result_a = lib.ingest_local_path(video_dir, max_videos=1)
        print(f"  Ingest result: {json.dumps({k: v for k, v in result_a.items() if k != 'assets'}, indent=2)}")
        if result_a.get("assets"):
            asset_a = result_a["assets"][0]
            uid_a = asset_a.get("uid", "")
            print(f"  UID: {uid_a}")
        else:
            uid_a = sql1(conn, "SELECT uid FROM assets LIMIT 1") or ""
            print(f"  UID (from DB): {uid_a}")
    except Exception as e:
        print(f"  ERROR: {e}")
        uid_a = sql1(conn, "SELECT uid FROM assets LIMIT 1") or ""
    prt("Time", f"{time.time()-t0:.1f}s")

    # ── Ingest B: new image ──
    section("INGEST B: New Image")
    t0 = time.time()
    try:
        result_b = lib.ingest_local_images(image_dir, max_images=1)
        print(f"  Ingest result: {json.dumps({k: v for k, v in result_b.items() if k != 'assets'}, indent=2)}")
        if result_b.get("assets"):
            asset_b = result_b["assets"][0]
            uid_b = asset_b.get("uid", "")
            print(f"  UID: {uid_b}")
        else:
            uid_b = sql1(conn, "SELECT uid FROM assets WHERE uid != ? LIMIT 1", (uid_a,)) or ""
            print(f"  UID (from DB): {uid_b}")
    except Exception as e:
        print(f"  ERROR: {e}")
        uid_b = sql1(conn, "SELECT uid FROM assets WHERE uid != ? LIMIT 1", (uid_a,)) or ""
    prt("Time", f"{time.time()-t0:.1f}s")

    # Snapshot counts before re-ingest
    ev_a_before = sql1(conn, "SELECT count(*) FROM evidence WHERE asset_id=?", (uid_a,))
    tr_a_before = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE asset_id=?", (uid_a,))
    ev_b_before = sql1(conn, "SELECT count(*) FROM evidence WHERE asset_id=?", (uid_b,))
    tr_b_before = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE asset_id=?", (uid_b,))

    # ── Ingest C: re-ingest same video (existing path) ──
    section("INGEST C: Re-ingest Same Video (existing path)")
    t0 = time.time()
    try:
        result_c = lib.ingest_local_path(video_dir, max_videos=1)
        print(f"  Ingest result: {json.dumps({k: v for k, v in result_c.items() if k != 'assets'}, indent=2)}")
    except Exception as e:
        print(f"  ERROR: {e}")
    prt("Time", f"{time.time()-t0:.1f}s")

    # ── Ingest D: re-ingest same image (existing path) ──
    section("INGEST D: Re-ingest Same Image (existing path)")
    t0 = time.time()
    try:
        result_d = lib.ingest_local_images(image_dir, max_images=1)
        print(f"  Ingest result: {json.dumps({k: v for k, v in result_d.items() if k != 'assets'}, indent=2)}")
    except Exception as e:
        print(f"  ERROR: {e}")
    prt("Time", f"{time.time()-t0:.1f}s")

    # Snapshot counts after re-ingest
    ev_a_after = sql1(conn, "SELECT count(*) FROM evidence WHERE asset_id=?", (uid_a,))
    tr_a_after = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE asset_id=?", (uid_a,))
    ev_b_after = sql1(conn, "SELECT count(*) FROM evidence WHERE asset_id=?", (uid_b,))
    tr_b_after = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE asset_id=?", (uid_b,))

    # ═══════════════════════════════════════════════════════════════
    # VERIFICATION
    # ═══════════════════════════════════════════════════════════════

    section("I. 双写是否真实发生")
    for label, uid in [("A (video)", uid_a), ("B (image)", uid_b)]:
        print(f"\n  --- Asset {label}: {uid} ---")
        ev_count = sql1(conn, "SELECT count(*) FROM evidence WHERE asset_id=?", (uid,))
        prt("evidence count", ev_count)
        ev_by_kind = sql(conn, "SELECT source_kind, count(*) cnt FROM evidence WHERE asset_id=? GROUP BY source_kind", (uid,))
        for r in ev_by_kind:
            prt(f"  evidence[{r[0]}]", r[1])

        tr_count = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE asset_id=?", (uid,))
        prt("asset_tag_result count", tr_count)
        slot_dist = sql(conn,
            "SELECT t.semantic_slot, count(*) cnt FROM asset_tag_result r JOIN tag t ON r.tag_id=t.tag_id WHERE r.asset_id=? GROUP BY t.semantic_slot ORDER BY cnt DESC",
            (uid,))
        for r in slot_dist:
            prt(f"  slot[{r[0]}]", r[1])

        # semantic_json._meta
        sj_raw = sql1(conn, "SELECT semantic_json FROM assets WHERE uid=?", (uid,))
        if sj_raw:
            try:
                sj = json.loads(sj_raw)
                meta = sj.get("_meta", {})
                prt("_meta keys", list(meta.keys()))
                prt("_meta content", json.dumps(meta, ensure_ascii=False, indent=4))
            except:
                prt("semantic_json", "PARSE ERROR")
        else:
            prt("semantic_json", "NULL/EMPTY")

    section("II. 幂等性/重复写入风险 (existing path)")
    print(f"\n  --- Video A ---")
    prt("evidence before re-ingest", ev_a_before)
    prt("evidence after re-ingest", ev_a_after)
    prt("asset_tag_result before", tr_a_before)
    prt("asset_tag_result after", tr_a_after)
    prt("evidence delta", ev_a_after - (ev_a_before or 0))
    prt("tag_result delta", tr_a_after - (tr_a_before or 0))
    # Check unique index effectiveness
    tr_total = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE asset_id=?", (uid_a,))
    tr_distinct = sql1(conn,
        "SELECT count(DISTINCT tag_id || ':' || coalesce(segment_id,'') || ':' || result_scope) FROM asset_tag_result WHERE asset_id=?",
        (uid_a,))
    prt("total rows vs distinct(tag_id,segment_id,scope)", f"{tr_total} vs {tr_distinct}")

    print(f"\n  --- Image B ---")
    prt("evidence before re-ingest", ev_b_before)
    prt("evidence after re-ingest", ev_b_after)
    prt("asset_tag_result before", tr_b_before)
    prt("asset_tag_result after", tr_b_after)
    prt("evidence delta", ev_b_after - (ev_b_before or 0))
    prt("tag_result delta", tr_b_after - (tr_b_before or 0))

    section("III. 分数隔离")
    sample_rows = sql(conn,
        "SELECT r.asset_id, t.tag_name, r.final_score, r.user_adjustment, r.effective_score "
        "FROM asset_tag_result r JOIN tag t ON r.tag_id=t.tag_id LIMIT 5")
    for r in sample_rows:
        computed = max(0.0, min(1.0, r[2] + r[3]))
        ok = abs(computed - r[4]) < 0.001
        prt(f"tag={r[1]}", f"final={r[2]:.3f} adj={r[3]:.3f} eff={r[4]:.3f} clamp_ok={ok}")

    section("IV. 规则轻修正")

    # Check hierarchy bonus
    print("\n  --- Hierarchy (child→parent bonus) ---")
    hier_rows = sql(conn,
        "SELECT r.asset_id, t.tag_name, r.hierarchy_bonus FROM asset_tag_result r "
        "JOIN tag t ON r.tag_id=t.tag_id WHERE r.hierarchy_bonus > 0 LIMIT 3")
    if hier_rows:
        for r in hier_rows:
            prt(f"tag={r[1]}", f"hierarchy_bonus={r[2]:.3f}")
    else:
        prt("RESULT", "NO hierarchy bonus found in any asset_tag_result")

    # Check conflict penalty
    print("\n  --- Conflict penalty ---")
    conf_rows = sql(conn,
        "SELECT r.asset_id, t.tag_name, r.conflict_penalty FROM asset_tag_result r "
        "JOIN tag t ON r.tag_id=t.tag_id WHERE r.conflict_penalty > 0 LIMIT 3")
    if conf_rows:
        for r in conf_rows:
            prt(f"tag={r[1]}", f"conflict_penalty={r[2]:.3f}")
    else:
        prt("RESULT", "NO conflict penalty found (may be correct if no conflicting tags detected)")

    # Check cooccurrence bonus
    print("\n  --- Cooccurrence bonus ---")
    cooc_rows = sql(conn,
        "SELECT r.asset_id, t.tag_name, r.cooccurrence_bonus FROM asset_tag_result r "
        "JOIN tag t ON r.tag_id=t.tag_id WHERE r.cooccurrence_bonus > 0 LIMIT 3")
    if cooc_rows:
        for r in cooc_rows:
            prt(f"tag={r[1]}", f"cooccurrence_bonus={r[2]:.3f}")
    else:
        prt("RESULT", "NO cooccurrence bonus found")

    # Check negative penalty
    print("\n  --- Negative penalty ---")
    neg_rows = sql(conn,
        "SELECT r.asset_id, t.tag_name, r.negative_penalty FROM asset_tag_result r "
        "JOIN tag t ON r.tag_id=t.tag_id WHERE r.negative_penalty > 0 LIMIT 3")
    if neg_rows:
        for r in neg_rows:
            prt(f"tag={r[1]}", f"negative_penalty={r[2]:.3f}")
    else:
        prt("RESULT", "NO negative penalty found")

    # Show decision_reason samples
    print("\n  --- decision_reason samples ---")
    dr_rows = sql(conn,
        "SELECT t.tag_name, r.decision_reason FROM asset_tag_result r "
        "JOIN tag t ON r.tag_id=t.tag_id WHERE r.decision_reason IS NOT NULL LIMIT 3")
    for r in dr_rows:
        prt(f"tag={r[0]}", r[1])

    # Show composite rules for reference
    print("\n  --- Available composite rules ---")
    rules = sql(conn, "SELECT rule_name, rule_type, expr_json FROM composite_rule LIMIT 10")
    for r in rules:
        prt(f"{r[0]} ({r[1]})", r[2][:80] if r[2] else "")

    section("V. learning_candidate")

    # Inject a semantic_json with a fictitious term to test unresolved path
    print("\n  --- Injecting fictitious term via _persist_evidence_and_tags ---")
    # First create a fake asset
    conn.execute(
        "INSERT OR IGNORE INTO assets (uid, sha256, filename, source_type, created_at, updated_at) "
        "VALUES ('audit_fake_001', 'sha_audit_001', 'fake.mp4', 'local', datetime('now'), datetime('now'))")
    conn.commit()
    fake_sj = {
        "structured_tags": {
            "tags": {
                "objects": {
                    "zh": ["审计虚构物品xyz999", "桌子"],
                    "en": ["audit_fictitious", "table"],
                    "confidence": 0.75
                },
            }
        },
        "_meta": {"model_version": "audit_test"},
    }
    count = lib._persist_evidence_and_tags("audit_fake_001", fake_sj, conn)
    conn.commit()
    prt("Tags written from fake_sj", count)

    # Check learning_candidate
    lc_rows = sql(conn, "SELECT candidate_text, normalized_text, category_hint, source_kind, occurrence_count FROM learning_candidate")
    prt("learning_candidate total", len(lc_rows))
    for r in lc_rows:
        prt(f"  candidate", f"text='{r[0]}' norm='{r[1]}' cat={r[2]} src={r[3]} occ={r[4]}")

    # Check stopword blocking
    print("\n  --- Stopword blocking ---")
    # Inject a known stopword
    conn.execute(
        "INSERT OR IGNORE INTO assets (uid, sha256, filename, source_type, created_at, updated_at) "
        "VALUES ('audit_fake_002', 'sha_audit_002', 'fake2.mp4', 'local', datetime('now'), datetime('now'))")
    conn.commit()
    stopword_sj = {
        "structured_tags": {
            "tags": {
                "objects": {
                    "zh": ["加载中", "请稍候", "桌子"],
                    "en": ["loading", "wait", "table"],
                    "confidence": 0.80
                },
            }
        },
        "_meta": {"model_version": "audit_test"},
    }
    count2 = lib._persist_evidence_and_tags("audit_fake_002", stopword_sj, conn)
    conn.commit()
    prt("Tags written (with stopwords)", count2)

    # Verify stopwords NOT in learning_candidate
    for sw in ["加载中", "请稍候"]:
        r = sql1(conn, "SELECT count(*) FROM learning_candidate WHERE normalized_text=?", (sw,))
        prt(f"  '{sw}' in learning_candidate", f"{r} (should be 0)")

    # Verify stopwords NOT in asset_tag_result
    for sw in ["加载中", "请稍候"]:
        r = sql1(conn, "SELECT count(*) FROM asset_tag_result r JOIN tag t ON r.tag_id=t.tag_id WHERE t.tag_name=? AND r.asset_id='audit_fake_002'", (sw,))
        prt(f"  '{sw}' in asset_tag_result", f"{r} (should be 0)")

    section("VI. Evidence 膨胀控制")
    for label, uid in [("A (video)", uid_a), ("B (image)", uid_b)]:
        ev_count = sql1(conn, "SELECT count(*) FROM evidence WHERE asset_id=?", (uid,))
        prt(f"{label} evidence count", f"{ev_count} (limit: 100)")
        # Check per-source_kind distribution
        dup_check = sql(conn,
            "SELECT asset_id, segment_id, tag_id, source_kind, count(*) cnt "
            "FROM evidence WHERE asset_id=? GROUP BY asset_id, segment_id, tag_id, source_kind HAVING cnt > 1",
            (uid,))
        prt(f"{label} duplicate (asset,seg,tag,kind)", f"{len(dup_check)} groups with >1 row")

    section("VII. 字段非空率")
    total = sql1(conn, "SELECT count(*) FROM asset_tag_result") or 1
    ss_nonnull = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE source_summary IS NOT NULL AND source_summary != ''")
    cb_nonnull = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE confidence_band IS NOT NULL AND confidence_band != ''")
    dr_nonnull = sql1(conn, "SELECT count(*) FROM asset_tag_result WHERE decision_reason IS NOT NULL AND decision_reason != ''")
    prt(f"total asset_tag_result rows", total)
    prt(f"source_summary non-null", f"{ss_nonnull}/{total} ({100*ss_nonnull/total:.0f}%)")
    prt(f"confidence_band non-null", f"{cb_nonnull}/{total} ({100*cb_nonnull/total:.0f}%)")
    prt(f"decision_reason non-null", f"{dr_nonnull}/{total} ({100*dr_nonnull/total:.0f}%)")

    # evidence.evidence_json
    ev_total = sql1(conn, "SELECT count(*) FROM evidence") or 1
    ej_nonnull = sql1(conn, "SELECT count(*) FROM evidence WHERE evidence_json IS NOT NULL AND evidence_json != ''")
    prt(f"evidence.evidence_json non-null", f"{ej_nonnull}/{ev_total} ({100*ej_nonnull/ev_total:.0f}%)")

    # Show all tag_name -> semantic_slot for real assets
    section("APPENDIX: All tag results for real assets")
    for label, uid in [("A (video)", uid_a), ("B (image)", uid_b)]:
        print(f"\n  --- {label}: {uid} ---")
        rows = sql(conn,
            "SELECT t.tag_name, t.semantic_slot, r.final_score, r.effective_score, r.source_summary, r.confidence_band "
            "FROM asset_tag_result r JOIN tag t ON r.tag_id=t.tag_id WHERE r.asset_id=? ORDER BY r.effective_score DESC",
            (uid,))
        for r in rows:
            prt(f"  {r[0]} [{r[1]}]", f"score={r[2]:.3f} eff={r[3]:.3f} src={r[4]} band={r[5]}")

    conn.close()
    print(f"\n\nAudit DB preserved at: {db_path}")
    print("Done.")


if __name__ == "__main__":
    run_audit()
