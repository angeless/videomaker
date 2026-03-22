"""Database schema initialization mixin for GlobalMediaLibrary.

Extracted from global_media_library.py — contains _init_db (full schema
DDL), seed data loading, column migrations, and library stats.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.library._constants import *  # noqa: F403
from modules.library._constants import (  # noqa: F401
    _KIND_TO_SLOT, _TOPCATEGORY_TO_CODE, _SEED_DATA_DIR,
)

logger = logging.getLogger(__name__)


class SchemaMixin:
    """Methods related to database schema creation and migration."""

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    uid TEXT PRIMARY KEY,
                    sha256 TEXT UNIQUE NOT NULL,
                    phash TEXT,
                    filename TEXT NOT NULL,
                    primary_path TEXT,
                    source_type TEXT NOT NULL,
                    duration REAL,
                    size_bytes INTEGER,
                    resolution TEXT,
                    width INTEGER,
                    height INTEGER,
                    fps REAL,
                    codec TEXT,
                    quality_score REAL,
                    scene_description TEXT,
                    mood TEXT,
                    objects_json TEXT,
                    analysis_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS asset_locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    is_available INTEGER NOT NULL DEFAULT 1,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(uid) REFERENCES assets(uid) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_assets_updated ON assets(updated_at);
                CREATE INDEX IF NOT EXISTS idx_assets_filename ON assets(filename);
                CREATE INDEX IF NOT EXISTS idx_assets_scene ON assets(scene_description);
                CREATE INDEX IF NOT EXISTS idx_assets_resolution ON assets(resolution);
                CREATE INDEX IF NOT EXISTS idx_locations_uid ON asset_locations(uid);

                CREATE TABLE IF NOT EXISTS asset_embeddings (
                    uid TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding_version TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(uid) REFERENCES assets(uid) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_asset_embeddings_model ON asset_embeddings(model);
                CREATE INDEX IF NOT EXISTS idx_asset_embeddings_updated ON asset_embeddings(updated_at);
                """
            )

            # FTS5 full-text search index
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts
                    USING fts5(uid UNINDEXED, semantic_text,
                               content='assets', content_rowid='rowid',
                               tokenize='unicode61')
                    """
                )
            except Exception:
                pass  # FTS5 may not be available in all SQLite builds

            # ── v0.6 semantic engine tables (11 tables) ──
            conn.executescript(
                """
                -- 1. Tag categories (16+ categories)
                CREATE TABLE IF NOT EXISTS tag_category (
                    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_name TEXT NOT NULL,
                    category_code TEXT NOT NULL UNIQUE,
                    sort_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 2. Tags (2124+ seed entries)
                CREATE TABLE IF NOT EXISTS tag (
                    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    tag_code TEXT NOT NULL UNIQUE,
                    category_id INTEGER NOT NULL REFERENCES tag_category(category_id),
                    parent_tag_id INTEGER REFERENCES tag(tag_id),
                    level_no INTEGER DEFAULT 1,
                    semantic_slot TEXT NOT NULL DEFAULT 'object',
                    search_boost REAL DEFAULT 1.0,
                    description TEXT,
                    trigger_objects TEXT,
                    trigger_scenes TEXT,
                    trigger_texts TEXT,
                    negative_terms TEXT,
                    score_threshold REAL DEFAULT 0.6,
                    is_active INTEGER DEFAULT 1,
                    source_type TEXT DEFAULT 'system',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_tag_category ON tag(category_id);
                CREATE INDEX IF NOT EXISTS idx_tag_parent ON tag(parent_tag_id);
                CREATE INDEX IF NOT EXISTS idx_tag_slot ON tag(semantic_slot);

                -- 3. Tag aliases
                CREATE TABLE IF NOT EXISTS tag_alias (
                    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_id INTEGER NOT NULL REFERENCES tag(tag_id),
                    alias_name TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    alias_type TEXT DEFAULT 'alias',
                    language_code TEXT DEFAULT 'zh-CN',
                    confidence REAL DEFAULT 1.0,
                    source_type TEXT DEFAULT 'seed',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_alias_name ON tag_alias(normalized_alias);

                -- 4. Tag relations (synonym/conflict/parent/child/related/cooccurs)
                CREATE TABLE IF NOT EXISTS tag_relation (
                    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_tag_id INTEGER NOT NULL REFERENCES tag(tag_id),
                    to_tag_id INTEGER NOT NULL REFERENCES tag(tag_id),
                    relation_type TEXT NOT NULL,
                    relation_weight REAL DEFAULT 0.1,
                    participates_in_search INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 5. Composite rules (cooccurrence/negative)
                CREATE TABLE IF NOT EXISTS composite_rule (
                    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT NOT NULL,
                    target_tag_id INTEGER NOT NULL REFERENCES tag(tag_id),
                    rule_type TEXT DEFAULT 'cooccurrence',
                    min_match_count INTEGER DEFAULT 2,
                    score_bonus REAL DEFAULT 0.1,
                    penalty_value REAL DEFAULT 0.0,
                    priority_no INTEGER DEFAULT 100,
                    is_active INTEGER DEFAULT 1,
                    expr_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 6. Evidence (product-explainability, not raw detection log)
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    segment_id INTEGER,
                    tag_id INTEGER REFERENCES tag(tag_id),
                    semantic_slot TEXT,
                    source_kind TEXT NOT NULL,
                    source_model TEXT,
                    raw_value TEXT,
                    raw_text TEXT,
                    base_score REAL NOT NULL,
                    weighted_score REAL NOT NULL,
                    evidence_json TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_asset ON evidence(asset_id);
                CREATE INDEX IF NOT EXISTS idx_evidence_tag ON evidence(tag_id);

                -- 7. Asset tag results (fused scores)
                CREATE TABLE IF NOT EXISTS asset_tag_result (
                    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    segment_id TEXT NOT NULL DEFAULT '',
                    tag_id INTEGER NOT NULL REFERENCES tag(tag_id),
                    result_scope TEXT DEFAULT 'asset',
                    base_score REAL DEFAULT 0.0,
                    source_bonus REAL DEFAULT 0.0,
                    cooccurrence_bonus REAL DEFAULT 0.0,
                    hierarchy_bonus REAL DEFAULT 0.0,
                    conflict_penalty REAL DEFAULT 0.0,
                    negative_penalty REAL DEFAULT 0.0,
                    final_score REAL NOT NULL,
                    user_adjustment REAL DEFAULT 0.0,
                    effective_score REAL NOT NULL,
                    rank_no INTEGER DEFAULT 0,
                    is_displayed INTEGER DEFAULT 0,
                    source_summary TEXT,
                    confidence_band TEXT DEFAULT 'medium',
                    user_confirm_state TEXT DEFAULT 'none',
                    decision_reason TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_result_asset_score ON asset_tag_result(asset_id, effective_score);
                CREATE INDEX IF NOT EXISTS idx_result_tag ON asset_tag_result(tag_id, effective_score);

                -- 8. Custom tags (user-defined, with full semantic definition)
                CREATE TABLE IF NOT EXISTS custom_tag (
                    custom_tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    custom_tag_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    parent_system_tag_id INTEGER REFERENCES tag(tag_id),
                    category_id INTEGER REFERENCES tag_category(category_id),
                    semantic_slot TEXT,
                    aliases TEXT,
                    related_objects TEXT,
                    trigger_texts TEXT,
                    negative_terms TEXT,
                    composite_logic TEXT,
                    threshold_value REAL DEFAULT 0.72,
                    status TEXT DEFAULT 'gray',
                    match_count INTEGER DEFAULT 0,
                    last_used_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- 9. Feedback events (immutable log)
                CREATE TABLE IF NOT EXISTS feedback_event (
                    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    asset_id INTEGER NOT NULL,
                    segment_id INTEGER,
                    tag_id INTEGER REFERENCES tag(tag_id),
                    custom_tag_id INTEGER REFERENCES custom_tag(custom_tag_id),
                    feedback_type TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_asset ON feedback_event(asset_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_tag ON feedback_event(tag_id);

                -- 10. Learning candidate pool
                CREATE TABLE IF NOT EXISTS learning_candidate (
                    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    category_hint TEXT,
                    source_kind TEXT NOT NULL,
                    occurrence_count INTEGER DEFAULT 1,
                    asset_count INTEGER DEFAULT 1,
                    confirmed_count INTEGER DEFAULT 0,
                    cooccur_json TEXT,
                    suggested_action TEXT DEFAULT 'review',
                    review_status TEXT DEFAULT 'pending',
                    blocked_reason TEXT,
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 11. Learning stopwords / blacklist
                CREATE TABLE IF NOT EXISTS learning_stopword (
                    stopword_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_text TEXT NOT NULL UNIQUE,
                    block_reason TEXT,
                    blocked_by TEXT DEFAULT 'system',
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 12. Search log (search signal learning loop)
                CREATE TABLE IF NOT EXISTS search_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_text TEXT NOT NULL,
                    normalized_query TEXT NOT NULL,
                    query_type TEXT,
                    retrieval_mode TEXT DEFAULT 'hybrid',
                    result_count INTEGER DEFAULT 0,
                    tag_hit_count INTEGER DEFAULT 0,
                    fts_hit_count INTEGER DEFAULT 0,
                    vector_hit_count INTEGER DEFAULT 0,
                    resolved_tags TEXT,
                    unresolved_terms TEXT,
                    weights_used TEXT,
                    is_zero_hit INTEGER DEFAULT 0,
                    search_duration_ms INTEGER,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_search_log_query ON search_log(normalized_query);
                CREATE INDEX IF NOT EXISTS idx_search_log_zero ON search_log(is_zero_hit);
                CREATE INDEX IF NOT EXISTS idx_search_log_time ON search_log(created_at);
                """
            )

            # ── v0.7 fingerprint / path relocation / dedup tables (4 tables) ──
            conn.executescript(
                """
                -- 1. Known media root directories (user-registered storage roots)
                CREATE TABLE IF NOT EXISTS known_media_roots (
                    root_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    root_path TEXT NOT NULL UNIQUE,
                    label TEXT,
                    is_active INTEGER DEFAULT 1,
                    last_scanned_at TEXT,
                    asset_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 2. Duplicate groups (grouping similar/identical assets)
                CREATE TABLE IF NOT EXISTS duplicate_group (
                    group_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_type TEXT NOT NULL,
                    primary_uid TEXT,
                    member_count INTEGER DEFAULT 0,
                    total_size_bytes INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    resolved_at TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 3. Duplicate group members
                CREATE TABLE IF NOT EXISTS duplicate_group_member (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL REFERENCES duplicate_group(group_id),
                    uid TEXT NOT NULL,
                    fingerprint_distance INTEGER DEFAULT 0,
                    file_size INTEGER,
                    resolution TEXT,
                    codec TEXT,
                    keep_decision TEXT DEFAULT 'undecided',
                    UNIQUE(group_id, uid)
                );
                CREATE INDEX IF NOT EXISTS idx_dup_member_uid ON duplicate_group_member(uid);
                CREATE INDEX IF NOT EXISTS idx_dup_member_group ON duplicate_group_member(group_id);

                -- 4. Path change audit log
                CREATE TABLE IF NOT EXISTS path_change_log (
                    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT NOT NULL,
                    old_path TEXT,
                    new_path TEXT,
                    change_type TEXT NOT NULL,
                    source TEXT DEFAULT 'system',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_path_change_uid ON path_change_log(uid);
                CREATE INDEX IF NOT EXISTS idx_path_change_time ON path_change_log(created_at);

                -- asset_locations indexes for path lookup and availability filtering
                CREATE INDEX IF NOT EXISTS idx_locations_path ON asset_locations(path);
                CREATE INDEX IF NOT EXISTS idx_locations_available ON asset_locations(is_available, uid);

                -- 5. Project relink job tracking
                CREATE TABLE IF NOT EXISTS project_relink_job (
                    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_path TEXT NOT NULL,
                    project_type TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    total_refs INTEGER DEFAULT 0,
                    stable_refs INTEGER DEFAULT 0,
                    changed_refs INTEGER DEFAULT 0,
                    missing_refs INTEGER DEFAULT 0,
                    unmatched_refs INTEGER DEFAULT 0,
                    result_json TEXT,
                    error_message TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- 6. Project relink item details
                CREATE TABLE IF NOT EXISTS project_relink_item (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL REFERENCES project_relink_job(job_id),
                    uid TEXT,
                    asset_name TEXT,
                    old_path TEXT,
                    new_path TEXT,
                    status TEXT NOT NULL,
                    source_ref TEXT,
                    fingerprint_match_type TEXT,
                    media_type TEXT,
                    match_confidence REAL,
                    reason TEXT,
                    applied INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_relink_item_job ON project_relink_item(job_id);
                """
            )

            # Unique indexes created separately (IF NOT EXISTS + UNIQUE in executescript can be tricky)
            for idx_sql in [
                "CREATE UNIQUE INDEX IF NOT EXISTS uk_tag_norm_cat ON tag(normalized_name, category_id)",
                "CREATE UNIQUE INDEX IF NOT EXISTS uk_tag_alias ON tag_alias(tag_id, normalized_alias)",
                "CREATE UNIQUE INDEX IF NOT EXISTS uk_relation ON tag_relation(from_tag_id, to_tag_id, relation_type)",
                "CREATE UNIQUE INDEX IF NOT EXISTS uk_asset_tag ON asset_tag_result(asset_id, segment_id, tag_id, result_scope)",
                "CREATE UNIQUE INDEX IF NOT EXISTS uk_user_custom ON custom_tag(user_id, normalized_name)",
                "CREATE UNIQUE INDEX IF NOT EXISTS uk_candidate ON learning_candidate(normalized_text, source_kind)",
            ]:
                try:
                    conn.execute(idx_sql)
                except Exception:
                    pass  # index may already exist

            # C-2 schema migration: add columns safely (no IF NOT EXISTS for ALTER in SQLite)
            for alter_sql in [
                "ALTER TABLE project_relink_job ADD COLUMN version_info TEXT",
                "ALTER TABLE project_relink_job ADD COLUMN apply_count INTEGER DEFAULT 0",
                "ALTER TABLE project_relink_item ADD COLUMN applied_at TEXT",
            ]:
                try:
                    conn.execute(alter_sql)
                except Exception:
                    pass  # Column already exists

            # D-1 schema migration: task lifecycle + retry support
            for alter_sql in [
                "ALTER TABLE project_relink_job ADD COLUMN retry_of INTEGER",
                "ALTER TABLE project_relink_job ADD COLUMN retry_count INTEGER DEFAULT 0",
                "ALTER TABLE project_relink_job ADD COLUMN last_error_at TEXT",
            ]:
                try:
                    conn.execute(alter_sql)
                except Exception:
                    pass  # Column already exists

            # D-2 schema migration: manual binding fields
            for alter_sql in [
                "ALTER TABLE project_relink_item ADD COLUMN manual_uid TEXT",
                "ALTER TABLE project_relink_item ADD COLUMN manual_new_path TEXT",
                "ALTER TABLE project_relink_item ADD COLUMN manual_decision_source TEXT",
                "ALTER TABLE project_relink_item ADD COLUMN manual_bound_at TEXT",
            ]:
                try:
                    conn.execute(alter_sql)
                except Exception:
                    pass  # Column already exists

            # D-3 schema migration: action log + output tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_relink_action_log (
                    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    item_id INTEGER,
                    action_type TEXT NOT NULL,
                    operator TEXT DEFAULT 'system',
                    payload_json TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relink_action_job ON project_relink_action_log(job_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relink_action_item ON project_relink_action_log(item_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relink_action_time ON project_relink_action_log(created_at)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_relink_output (
                    output_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    output_path TEXT NOT NULL,
                    naming_rule TEXT,
                    applied_count INTEGER DEFAULT 0,
                    skipped_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relink_output_job ON project_relink_output(job_id)")

            # ── D-4 schema migration: long-term sync + handover closure ──
            for alter_sql in [
                # job: predecessor chain + handover
                "ALTER TABLE project_relink_job ADD COLUMN predecessor_job_id INTEGER",
                "ALTER TABLE project_relink_job ADD COLUMN handover_at TEXT",
                "ALTER TABLE project_relink_job ADD COLUMN handover_snapshot TEXT",
                # item: inheritance tracing + verification
                "ALTER TABLE project_relink_item ADD COLUMN inherited_from_item_id INTEGER",
                "ALTER TABLE project_relink_item ADD COLUMN verified_at TEXT",
            ]:
                try:
                    conn.execute(alter_sql)
                except Exception:
                    pass

            # Seed tag library on first run
            self._seed_tag_library_if_empty(conn)

            self._ensure_assets_columns(conn)
            self._backfill_semantic_columns(conn)

    # ------------------------------------------------------------------
    # v0.6 Semantic engine – seed data import
    # ------------------------------------------------------------------

    def _seed_tag_library_if_empty(self, conn: sqlite3.Connection):
        """Import ChatGPT seed data into tag tables on first run."""
        count = conn.execute("SELECT count(*) FROM tag").fetchone()[0]
        if count > 0:
            return  # already seeded

        jsonl_path = _SEED_DATA_DIR / "semantic_keyword_library_flat.jsonl"
        json_path = _SEED_DATA_DIR / "semantic_keyword_library_zh_v1.json"
        rules_path = _SEED_DATA_DIR / "semantic_tag_scoring_rules_v1.json"

        seed_available = jsonl_path.exists()
        if seed_available:
            try:
                jsonl_path.open("r").close()
            except (PermissionError, OSError):
                seed_available = False

        if not seed_available:
            self._seed_minimal_tags(conn)
            return

        # ── Step 1: Insert tag_category ──
        # ChatGPT's 12 top_categories + our extra system categories
        category_map = {}  # category_code → category_id
        all_categories = [
            ("地点", "place", 1),
            ("场景", "scene", 2),
            ("物品", "object", 3),
            ("人物", "person", 4),
            ("动作", "action", 5),
            ("时间与环境", "time_environment", 6),
            ("动物", "animal", 7),
            ("植物", "plant", 8),
            ("交通与建筑", "infrastructure", 9),
            ("视觉风格", "visual_style", 10),
            ("文本与媒体", "text_media", 11),
            ("抽象语义", "abstract_theme", 12),
            # System categories for A-layer slots not in ChatGPT data
            ("事件", "event", 13),
            ("美食", "food", 14),
            ("氛围", "mood", 15),
            ("拍摄风格", "style", 16),
            ("天气", "weather", 17),
            ("季节", "season", 18),
            ("自然景观", "nature", 19),
            ("室内外", "indoor_outdoor", 20),
            ("时间段", "time_of_day", 21),
            ("镜头类型", "shot_type", 22),
        ]
        for cat_name, cat_code, sort_order in all_categories:
            conn.execute(
                "INSERT INTO tag_category (category_name, category_code, sort_order) VALUES (?, ?, ?)",
                (cat_name, cat_code, sort_order),
            )
            cid = conn.execute(
                "SELECT category_id FROM tag_category WHERE category_code = ?",
                (cat_code,),
            ).fetchone()[0]
            category_map[cat_code] = cid

        # ── Step 2: Parse JSONL and insert tags + aliases ──
        tag_name_to_id = {}  # tag_name → tag_id (for relation insertion)
        seen_codes = set()
        tag_counter = 0

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                keyword = entry["keyword"]
                top_cat = entry.get("top_category", "")
                subcategory = entry.get("subcategory", "")
                kind = entry.get("kind", "object")
                aliases = entry.get("aliases", [])

                # Determine category_id
                cat_code = _TOPCATEGORY_TO_CODE.get(top_cat, "object")
                cat_id = category_map.get(cat_code, category_map.get("object", 1))

                # Determine semantic_slot
                semantic_slot = _KIND_TO_SLOT.get(kind, "object")
                # Refine: environment → check subcategory for weather vs season vs time
                if kind == "environment":
                    sub_lower = subcategory.lower()
                    if "季节" in sub_lower or "四季" in sub_lower:
                        semantic_slot = "season"
                    elif "天气" in sub_lower or "气象" in sub_lower:
                        semantic_slot = "weather"
                    elif "时间" in sub_lower or "时段" in sub_lower:
                        semantic_slot = "time_of_day"
                    else:
                        semantic_slot = "weather"

                # Generate unique tag_code
                normalized = keyword.lower().strip()
                tag_code = f"{cat_code}_{tag_counter:04d}"
                while tag_code in seen_codes:
                    tag_counter += 1
                    tag_code = f"{cat_code}_{tag_counter:04d}"
                seen_codes.add(tag_code)
                tag_counter += 1

                # Skip duplicates (same normalized_name + category)
                if keyword in tag_name_to_id:
                    existing_tag_id = tag_name_to_id[keyword]
                    # Still insert aliases for the existing tag
                    for alias in aliases:
                        alias_norm = alias.lower().strip()
                        if alias_norm and alias_norm != normalized:
                            try:
                                conn.execute(
                                    "INSERT OR IGNORE INTO tag_alias (tag_id, alias_name, normalized_alias, source_type) VALUES (?, ?, ?, 'seed')",
                                    (existing_tag_id, alias, alias_norm),
                                )
                            except Exception:
                                pass
                    continue

                # Insert tag
                try:
                    conn.execute(
                        """INSERT INTO tag (tag_name, normalized_name, tag_code, category_id,
                            semantic_slot, source_type) VALUES (?, ?, ?, ?, ?, 'seed')""",
                        (keyword, normalized, tag_code, cat_id, semantic_slot),
                    )
                    tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    tag_name_to_id[keyword] = tid
                except Exception:
                    continue  # skip on constraint violation

                # Insert aliases
                for alias in aliases:
                    alias_norm = alias.lower().strip()
                    if alias_norm and alias_norm != normalized:
                        try:
                            conn.execute(
                                "INSERT OR IGNORE INTO tag_alias (tag_id, alias_name, normalized_alias, source_type) VALUES (?, ?, ?, 'seed')",
                                (tid, alias, alias_norm),
                            )
                        except Exception:
                            pass

        # ── Step 2b: Create subcategory tags + parent/child hierarchy ──
        # Collect subcategory → keyword mapping from JSONL entries
        subcat_keywords = {}  # (top_cat, subcategory) → [keyword_name, ...]
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                kw = entry["keyword"]
                tc = entry.get("top_category", "")
                sc = entry.get("subcategory", "")
                if tc and sc:
                    subcat_keywords.setdefault((tc, sc), []).append(kw)

        subcat_name_to_id = {}  # subcategory_name → tag_id
        subcat_counter = 9000  # high offset to avoid tag_code collision
        for (top_cat, subcat_name), kw_list in subcat_keywords.items():
            if subcat_name in subcat_name_to_id:
                continue  # already created
            cat_code = _TOPCATEGORY_TO_CODE.get(top_cat, "object")
            cat_id = category_map.get(cat_code, category_map.get("object", 1))
            # Determine semantic_slot from the first keyword's slot
            first_kw_id = tag_name_to_id.get(kw_list[0])
            if first_kw_id:
                row = conn.execute("SELECT semantic_slot FROM tag WHERE tag_id = ?", (first_kw_id,)).fetchone()
                slot = row[0] if row else "object"
            else:
                slot = _KIND_TO_SLOT.get(cat_code, "object")
            normalized = subcat_name.lower().strip()
            tag_code = f"sub_{subcat_counter:04d}"
            seen_codes.add(tag_code)
            subcat_counter += 1
            try:
                conn.execute(
                    """INSERT INTO tag (tag_name, normalized_name, tag_code, category_id,
                        semantic_slot, level_no, source_type) VALUES (?, ?, ?, ?, ?, 1, 'seed')""",
                    (subcat_name, normalized, tag_code, cat_id, slot),
                )
                sub_tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                subcat_name_to_id[subcat_name] = sub_tid
                tag_name_to_id[subcat_name] = sub_tid
            except Exception:
                continue

        # Set parent_tag_id on keyword tags + create tag_relation entries
        for (top_cat, subcat_name), kw_list in subcat_keywords.items():
            sub_tid = subcat_name_to_id.get(subcat_name)
            if not sub_tid:
                continue
            for kw in kw_list:
                kw_tid = tag_name_to_id.get(kw)
                if not kw_tid or kw_tid == sub_tid:
                    continue
                # Update parent_tag_id and level_no on the keyword tag
                conn.execute(
                    "UPDATE tag SET parent_tag_id = ?, level_no = 2 WHERE tag_id = ?",
                    (sub_tid, kw_tid),
                )
                # parent relation: subcategory → keyword (搜父包含子)
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO tag_relation (from_tag_id, to_tag_id, relation_type, relation_weight, participates_in_search) VALUES (?, ?, 'parent', 0.8, 1)",
                        (sub_tid, kw_tid),
                    )
                except Exception:
                    pass
                # child relation: keyword → subcategory
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO tag_relation (from_tag_id, to_tag_id, relation_type, relation_weight, participates_in_search) VALUES (?, ?, 'child', 0.5, 0)",
                        (kw_tid, sub_tid),
                    )
                except Exception:
                    pass

        # ── Step 2c: Seed system tags for empty slots ──
        _system_seed_tags = {
            "object": [
                "桌子", "椅子", "车辆", "汽车", "手机", "电脑", "杯子", "瓶子",
                "包", "书本", "钥匙", "伞", "灯", "镜子", "窗户", "门",
                "花瓶", "钟表", "相框", "玩具", "行李箱", "自行车", "摩托车",
            ],
            "place": [
                "城市", "街道", "公园", "商场", "学校", "医院", "车站", "广场",
                "市场", "超市", "图书馆", "博物馆", "体育馆", "停车场",
            ],
            "action": [
                "行走", "奔跑", "跳舞", "游泳", "骑行", "开车", "烹饪", "购物",
                "拍照", "阅读", "写字", "唱歌", "演奏", "绘画", "聊天",
            ],
            "person": [
                "儿童", "青年", "中年", "老人", "婴儿", "少年",
                "男性", "女性", "情侣", "家庭", "朋友", "同事",
            ],
            "mood": [
                "温馨", "浪漫", "欢乐", "宁静", "紧张", "感动", "活力", "忧伤",
                "神秘", "庄严", "轻松", "热闹", "孤独", "自由",
            ],
            "nature": [
                "山", "海", "河", "湖", "森林", "草原", "沙漠", "瀑布", "日落",
                "日出", "星空", "花", "树", "云",
            ],
            "weather": [
                "晴天", "雨天", "雪天", "阴天", "多云", "雾天", "大风",
                "风景", "夜景", "日出", "日落", "彩虹",
            ],
            "style": [
                "电影感", "纪录片", "Vlog", "低饱和", "高对比", "复古",
                "黑白", "暖色调", "冷色调", "柔和", "鲜艳",
            ],
            "food": [
                "中餐", "西餐", "日料", "韩餐", "甜点", "蛋糕", "咖啡", "奶茶",
                "火锅", "烧烤", "面包", "寿司", "披萨", "沙拉", "冰淇淋",
                "水果", "小吃", "快餐", "早餐", "午餐", "晚餐", "下午茶",
                "夜宵", "酒水", "饮品", "面条", "米饭", "粥", "汤",
            ],
            "event": [
                "婚礼", "生日", "毕业", "旅行", "聚会", "节日", "春节", "圣诞",
                "中秋", "开学", "搬家", "求婚", "周年纪念", "运动会", "演出",
                "展览", "音乐节", "比赛", "典礼", "纪念日", "满月", "百日宴",
                "入职", "退休", "开业", "乔迁", "年会",
            ],
            "indoor_outdoor": [
                "室内", "户外", "半户外",
            ],
            "shot_type": [
                "特写", "中景", "全景", "远景", "广角", "航拍", "俯拍", "仰拍",
                "侧拍", "跟拍", "固定镜头", "手持", "稳定器", "延时摄影",
                "慢动作", "微距", "自拍", "剪影", "逆光", "平拍",
            ],
            "animal": [
                "猫", "狗", "鸟", "鱼", "兔子", "马", "牛", "羊", "鸡", "鸭",
                "蝴蝶", "蜜蜂", "乌龟", "松鼠", "海豚",
            ],
            "season": [
                "春天", "夏天", "秋天", "冬天",
            ],
            "time_of_day": [
                "白天", "夜晚", "黄昏", "黎明", "清晨", "傍晚", "午后",
            ],
        }
        sys_counter = 8000
        for slot, tags in _system_seed_tags.items():
            cat_id = category_map.get(slot, category_map.get("object", 1))
            for t in tags:
                if t in tag_name_to_id:
                    continue  # already exists from JSONL
                normalized = t.lower().strip()
                tag_code = f"sys_{sys_counter:04d}"
                seen_codes.add(tag_code)
                sys_counter += 1
                try:
                    conn.execute(
                        """INSERT INTO tag (tag_name, normalized_name, tag_code, category_id,
                            semantic_slot, source_type) VALUES (?, ?, ?, ?, ?, 'seed')""",
                        (t, normalized, tag_code, cat_id, slot),
                    )
                    tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    tag_name_to_id[t] = tid
                except Exception:
                    pass

        # ── Step 3: Import synonym_groups from JSON ──
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    lib_data = json.load(f)
                synonym_groups = lib_data.get("synonym_groups", {})
                for main_term, synonyms in synonym_groups.items():
                    main_id = tag_name_to_id.get(main_term)
                    if not main_id:
                        continue
                    for syn in synonyms:
                        syn_id = tag_name_to_id.get(syn)
                        if not syn_id or syn_id == main_id:
                            continue
                        # Bidirectional synonym relation
                        for a, b in [(main_id, syn_id), (syn_id, main_id)]:
                            try:
                                conn.execute(
                                    "INSERT OR IGNORE INTO tag_relation (from_tag_id, to_tag_id, relation_type, relation_weight, participates_in_search) VALUES (?, ?, 'synonym', 0.9, 1)",
                                    (a, b),
                                )
                            except Exception:
                                pass
            except Exception:
                pass

        # ── Step 4: Import rules from scoring config ──
        if rules_path.exists():
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    rules_data = json.load(f)

                # Cooccurrence rules
                for rule in rules_data.get("cooccurrence_examples", []):
                    target_name = rule.get("then_tag", "")
                    target_id = tag_name_to_id.get(target_name)
                    if not target_id:
                        continue
                    bonus_range = rule.get("bonus_range", [0.1, 0.18])
                    avg_bonus = sum(bonus_range) / len(bonus_range) if bonus_range else 0.1
                    conn.execute(
                        """INSERT INTO composite_rule (rule_name, target_tag_id, rule_type,
                            min_match_count, score_bonus, expr_json) VALUES (?, ?, 'cooccurrence', ?, ?, ?)""",
                        (
                            f"cooccur_{target_name}",
                            target_id,
                            len(rule.get("if_tags", [])),
                            avg_bonus,
                            json.dumps({"if_tags": rule.get("if_tags", [])}, ensure_ascii=False),
                        ),
                    )

                # Conflict pairs → bidirectional conflict relations
                for pair in rules_data.get("conflict_pairs", []):
                    if len(pair) != 2:
                        continue
                    a_id = tag_name_to_id.get(pair[0])
                    b_id = tag_name_to_id.get(pair[1])
                    if not a_id or not b_id:
                        continue
                    for x, y in [(a_id, b_id), (b_id, a_id)]:
                        try:
                            conn.execute(
                                "INSERT OR IGNORE INTO tag_relation (from_tag_id, to_tag_id, relation_type, relation_weight, participates_in_search) VALUES (?, ?, 'conflict', 0.15, 0)",
                                (x, y),
                            )
                        except Exception:
                            pass

                # Negative rules
                for nrule in rules_data.get("negative_rule_examples", []):
                    target_name = nrule.get("tag", "")
                    target_id = tag_name_to_id.get(target_name)
                    if not target_id:
                        continue
                    expr = {}
                    penalty = 0.12
                    if "require_any" in nrule:
                        expr = {"require_any": nrule["require_any"]}
                        penalty = nrule.get("otherwise_penalty", 0.18)
                    elif "negative_any" in nrule:
                        expr = {"negative_any": nrule["negative_any"]}
                        penalty = nrule.get("penalty", 0.14)
                    conn.execute(
                        """INSERT INTO composite_rule (rule_name, target_tag_id, rule_type,
                            penalty_value, expr_json) VALUES (?, ?, 'negative', ?, ?)""",
                        (
                            f"neg_{target_name}",
                            target_id,
                            penalty,
                            json.dumps(expr, ensure_ascii=False),
                        ),
                    )
            except Exception:
                pass

        # ── Step 5: Seed learning stopwords (~100 entries) ──
        stopwords = [
            # OCR noise
            ("ocr_noise", [
                "乱码", "...", "|||", "---", "===", "***", "###",
                "□□□", "■■■", "◆◆◆", "???", "///", "\\\\\\",
            ]),
            # Spoken fillers
            ("spoken_filler", [
                "嗯嗯嗯", "那个", "就是说", "然后呢", "对对对", "啊啊啊", "嗯", "呃",
                "哈哈哈", "呵呵", "额", "好的好的", "是吧", "对吧", "你知道吗",
                "怎么说呢", "反正就是", "所以说", "其实吧",
            ]),
            # Device names
            ("device_name", [
                "iPhone", "Canon EOS", "Sony", "Nikon", "GoPro", "DJI", "Samsung Galaxy",
                "Huawei", "Xiaomi", "OPPO", "Vivo", "OnePlus", "Pixel", "iPad",
                "MacBook", "Surface",
            ]),
            # Timestamp patterns
            ("timestamp", [
                "2024", "2025", "2026", "15:30", "20:00",
                "IMG_", "DSC_", "VID_", "MVI_", "MOV_", "DCIM", "Screenshot",
            ]),
            # Logo/watermark
            ("logo", [
                "抖音", "微博", "版权所有", "TikTok", "Instagram", "Bilibili", "水印", "logo",
                "YouTube", "快手", "小红书", "微信", "QQ", "WeChat", "Douyin",
            ]),
            # Ad text
            ("ad", [
                "立即购买", "限时优惠", "点击链接", "关注我", "扫码", "优惠券", "打折",
                "免费领取", "仅限今日", "秒杀", "抢购", "特价", "促销",
            ]),
            # Functional UI text
            ("functional", [
                "加载中", "请稍候", "缓冲中", "播放失败", "网络错误", "404", "loading",
                "请登录", "注册", "密码", "验证码", "提交", "取消", "确定",
                "返回", "下一步", "上一页",
            ]),
        ]
        for reason, words in stopwords:
            for w in words:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO learning_stopword (normalized_text, block_reason) VALUES (?, ?)",
                        (w.lower().strip(), reason),
                    )
                except Exception:
                    pass

        conn.commit()

    def _ensure_assets_columns(self, conn: sqlite3.Connection):
        rows = conn.execute("PRAGMA table_info(assets)").fetchall()
        existing_columns = {row["name"] for row in rows}
        extra_columns = {
            "semantic_json": "TEXT",
            "semantic_text": "TEXT",
            "keywords_json": "TEXT",
            "semantic_version": "TEXT",
            "gps_latitude": "REAL",
            "gps_longitude": "REAL",
            # v0.7 fingerprint columns
            "content_fingerprint": "TEXT",
            "thumbnail_hash": "TEXT",
            "fingerprint_version": "INTEGER DEFAULT 0",
        }
        for col, col_type in extra_columns.items():
            if col not in existing_columns:
                conn.execute(f"ALTER TABLE assets ADD COLUMN {col} {col_type}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_semantic_version ON assets(semantic_version)")
        # v0.7 fingerprint indexes (partial – only non-NULL rows)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assets_content_fp ON assets(content_fingerprint)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assets_phash ON assets(phash)"
        )
        # v0.8 usability scoring columns
        usability_columns = {
            "usability_score": "REAL DEFAULT NULL",
            "usability_tier": "TEXT DEFAULT NULL",
            "material_type": "TEXT DEFAULT NULL",
            "trash_level": "TEXT DEFAULT 'none'",
        }
        for col, col_type in usability_columns.items():
            if col not in existing_columns:
                conn.execute(f"ALTER TABLE assets ADD COLUMN {col} {col_type}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_usability ON assets(usability_score)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_trash ON assets(trash_level)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_material_type ON assets(material_type)")

    def _seed_minimal_tags(self, conn: sqlite3.Connection):
        """Fallback seed when external JSONL data is unavailable."""
        categories = [
            ("场景", "scene", 1), ("人物", "person", 2), ("动作", "action", 3),
            ("情绪", "mood", 4), ("构图", "composition", 5), ("色调", "color_tone", 6),
            ("画质", "quality", 7),
        ]
        cat_ids = {}
        for name, code, order in categories:
            conn.execute(
                "INSERT OR IGNORE INTO tag_category (category_name, category_code, sort_order) VALUES (?, ?, ?)",
                (name, code, order),
            )
            row = conn.execute("SELECT category_id FROM tag_category WHERE category_code = ?", (code,)).fetchone()
            if row:
                cat_ids[code] = row[0]
        tags = [
            ("scene", [("室内", "indoor"), ("室外", "outdoor"), ("城市", "city"), ("自然", "nature"), ("水面", "water"), ("山地", "mountain"), ("夜景", "night")]),
            ("person", [("单人", "single_person"), ("多人", "multi_person"), ("无人", "no_person"), ("近景人物", "closeup_person"), ("群体", "crowd")]),
            ("action", [("行走", "walking"), ("静止", "still"), ("运动", "sports"), ("交谈", "talking"), ("特写动作", "action_closeup")]),
            ("mood", [("轻松", "relaxed"), ("活力", "energetic"), ("安静", "quiet"), ("戏剧性", "dramatic")]),
            ("composition", [("横构图", "landscape"), ("竖构图", "portrait"), ("中心构图", "center"), ("三分法", "rule_of_thirds")]),
            ("color_tone", [("暖色调", "warm"), ("冷色调", "cool"), ("高饱和", "saturated"), ("低饱和", "desaturated")]),
            ("quality", [("高清", "hd"), ("标清", "sd"), ("4K", "4k"), ("模糊", "blurry")]),
        ]
        for cat_code, tag_list in tags:
            cid = cat_ids.get(cat_code)
            if not cid:
                continue
            for tag_name, tag_code in tag_list:
                full_code = f"{cat_code}_{tag_code}"
                conn.execute(
                    "INSERT OR IGNORE INTO tag (tag_name, normalized_name, tag_code, category_id, semantic_slot, source_type) VALUES (?, ?, ?, ?, ?, ?)",
                    (tag_name, tag_name.lower(), full_code, cid, "object", "system_seed"),
                )

    def _get_library_stats(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """收集素材库统计信息，供独特性评分使用。"""
        try:
            total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            rows = conn.execute("""
                SELECT json_extract(analysis_json, '$.semantic.scene_description') as scene, COUNT(*) as cnt
                FROM assets
                WHERE analysis_json IS NOT NULL
                GROUP BY scene
            """).fetchall()
            scene_counts = {r[0]: r[1] for r in rows if r[0]}
            return {
                "total_assets": total,
                "scene_type_counts": scene_counts,
                "similar_assets_count": 0,
            }
        except Exception:
            return None

    def _backfill_semantic_columns(self, conn: sqlite3.Connection):
        rows = conn.execute(
            """
            SELECT uid, filename, primary_path, analysis_json, mood, scene_description, objects_json, quality_score
            FROM assets
            WHERE semantic_version IS NULL
               OR semantic_version != ?
               OR semantic_json IS NULL
               OR semantic_json = ''
            """,
            (SEMANTIC_SCHEMA_VERSION,),
        ).fetchall()
        if not rows:
            return

        now = self._now()
        payload = []
        # 启动阶段只做轻量字段回填，避免大库初始化时阻塞 UI。
        live_reanalyzed = 0
        max_live_reanalyze = 0
        for row in rows:
            path_hint = row["primary_path"] or row["filename"] or row["uid"]
            path_obj = Path(path_hint)
            analysis = self._safe_json_loads(row["analysis_json"], {})
            fallback_objects = self._safe_json_loads(row["objects_json"], [])
            if not isinstance(fallback_objects, list):
                fallback_objects = []
            semantic_bundle = None
            if live_reanalyzed < max_live_reanalyze and path_obj.exists():
                try:
                    live = self._analyze_video(path_obj)
                    semantic_bundle = {
                        "semantic": live.get("semantic_json", {}),
                        "semantic_text": live.get("semantic_text", ""),
                        "search_keywords": live.get("search_keywords", []),
                    }
                    live_reanalyzed += 1
                except Exception:
                    semantic_bundle = None

            if semantic_bundle is None:
                semantic_bundle = self._semantic_from_saved_analysis(
                    path=path_obj,
                    analysis=analysis,
                    fallback_mood=row["mood"] or "",
                    fallback_scene=row["scene_description"] or "",
                    fallback_objects=fallback_objects,
                    quality_score=row["quality_score"],
                )
            payload.append(
                (
                    json.dumps(semantic_bundle["semantic"], ensure_ascii=False),
                    semantic_bundle["semantic_text"],
                    json.dumps(semantic_bundle["search_keywords"], ensure_ascii=False),
                    SEMANTIC_SCHEMA_VERSION,
                    now,
                    row["uid"],
                )
            )

        conn.executemany(
            """
            UPDATE assets
            SET semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?, updated_at=?
            WHERE uid=?
            """,
            payload,
        )

        # Update FTS5 index
        try:
            for sem_json, sem_text, kw_json, ver, ts, uid in payload:
                conn.execute(
                    "INSERT OR REPLACE INTO assets_fts(rowid, uid, semantic_text) "
                    "SELECT rowid, uid, ? FROM assets WHERE uid=?",
                    (sem_text, uid),
                )
        except Exception:
            pass  # FTS5 may not be available


    # Core methods (analysis, search, ingestion) → CoreMixin (core/core_mixin.py)    def get_assets(self, uids: List[str]) -> List[Dict]:
        if not uids:
            return []

