#!/usr/bin/env python3
"""Global media library for semantic analysis and selection."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import sqlite3
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

try:
    import numpy as np
except Exception:
    np = None

try:
    from modules.library.project_relink_adapter import get_adapter as _get_relink_adapter
except ImportError:
    _get_relink_adapter = None

try:
    from modules.step1_material_analysis.usability_scorer import score_asset as _score_asset
except ImportError:
    _score_asset = None

_gml_logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_LIBRARY_DIR = REPO_ROOT / ".video_library"
DEFAULT_LIBRARY_DB = DEFAULT_LIBRARY_DIR / "library.db"
DEFAULT_CACHE_DIR = DEFAULT_LIBRARY_DIR / "cache" / "gdrive"

try:
    import cv2
except Exception:
    cv2 = None

try:
    from modules.step1_material_analysis.video_asset_toolkit import VideoAssetToolkit
except Exception as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(f"无法导入 VideoAssetToolkit: {exc}") from exc

try:
    from modules.step1_material_analysis.indexer.fingerprint import VideoHasher
except Exception:
    VideoHasher = None

from modules.library.maintenance.fingerprint import FingerprintMixin

try:
    import gdown
except Exception:
    gdown = None
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".hevc", ".flv", ".wmv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
GDOWN_FOLDER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
)
SEMANTIC_SCHEMA_VERSION = "3.0"
EMBEDDING_SCHEMA_VERSION = "1.0"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_RRF_K = 60

# ── 25-category taxonomy ──
TAG_CATEGORIES = (
    "objects", "actions", "scene", "mood", "concepts", "style", "use_cases",
    "materials_textures", "architecture_style", "food_cuisine", "animal_species",
    "vehicle_transport", "clothing_fashion", "body_language", "spatial_relations",
    "cultural_elements", "brand_product", "audio_mood", "color_palette",
    "composition", "nature_landscape", "weather_atmosphere", "social_context",
    "industry_domain", "narrative_technique",
)

TAG_TAXONOMY = {
    "objects":              {"parent": None,      "limit": 30, "zh": "物体"},
    "actions":              {"parent": None,      "limit": 25, "zh": "动作"},
    "scene":                {"parent": None,      "limit": 30, "zh": "场景"},
    "mood":                 {"parent": None,      "limit": 20, "zh": "氛围"},
    "concepts":             {"parent": None,      "limit": 30, "zh": "概念"},
    "style":                {"parent": None,      "limit": 25, "zh": "风格"},
    "use_cases":            {"parent": None,      "limit": 30, "zh": "用途"},
    "materials_textures":   {"parent": "objects",  "limit": 40, "zh": "材质纹理"},
    "architecture_style":   {"parent": "scene",    "limit": 30, "zh": "建筑风格"},
    "food_cuisine":         {"parent": "objects",  "limit": 30, "zh": "美食类型"},
    "animal_species":       {"parent": "objects",  "limit": 30, "zh": "动物种类"},
    "vehicle_transport":    {"parent": "objects",  "limit": 25, "zh": "交通工具"},
    "clothing_fashion":     {"parent": "objects",  "limit": 25, "zh": "服饰时尚"},
    "body_language":        {"parent": "actions",  "limit": 25, "zh": "身体语言"},
    "spatial_relations":    {"parent": "scene",    "limit": 20, "zh": "空间关系"},
    "cultural_elements":    {"parent": "concepts", "limit": 30, "zh": "文化元素"},
    "brand_product":        {"parent": "concepts", "limit": 25, "zh": "品牌产品"},
    "audio_mood":           {"parent": "mood",     "limit": 20, "zh": "音频氛围"},
    "color_palette":        {"parent": "style",    "limit": 25, "zh": "色彩搭配"},
    "composition":          {"parent": "style",    "limit": 20, "zh": "构图方式"},
    "nature_landscape":     {"parent": "scene",    "limit": 30, "zh": "自然景观"},
    "weather_atmosphere":   {"parent": "scene",    "limit": 20, "zh": "天气氛围"},
    "social_context":       {"parent": "concepts", "limit": 25, "zh": "社交语境"},
    "industry_domain":      {"parent": "use_cases","limit": 30, "zh": "行业领域"},
    "narrative_technique":  {"parent": "style",    "limit": 20, "zh": "叙事手法"},
}

GENERIC_TAG_TERMS = {
    "video", "footage", "clip", "scene", "person", "people", "thing", "background",
    "素材", "视频", "镜头", "片段", "人物", "人群", "东西", "背景",
    "unknown", "general", "内容", "content", "activity", "活动",
    "hook", "main shot", "开场钩子", "主镜头",
}

# ── 16 semantic slots (A-layer) ──
SEMANTIC_SLOTS = (
    "object", "place", "scene", "action", "person", "event", "mood", "style",
    "weather", "season", "nature", "food", "animal",
    "indoor_outdoor", "time_of_day", "shot_type",
)

# Mapping from ChatGPT JSONL `kind` → our semantic_slot
_KIND_TO_SLOT = {
    "place": "place",
    "scene": "scene",
    "object": "object",
    "person": "person",
    "action": "action",
    "animal": "animal",
    "plant": "nature",
    "environment": "weather",      # 时间与环境 → weather/season (refined per subcategory)
    "infrastructure": "place",     # 交通与建筑 → place
    "visual_style": "style",
    "text_media": "object",        # 文本与媒体 → object
    "abstract_theme": "mood",      # 抽象语义 → mood
}

# Mapping from ChatGPT top_category (zh) → tag_category_code
_TOPCATEGORY_TO_CODE = {
    "地点": "place",
    "场景": "scene",
    "物品": "object",
    "人物": "person",
    "动作": "action",
    "时间与环境": "time_environment",
    "动物": "animal",
    "植物": "plant",
    "交通与建筑": "infrastructure",
    "视觉风格": "visual_style",
    "文本与媒体": "text_media",
    "抽象语义": "abstract_theme",
    # Additional system categories (not from ChatGPT data)
    "事件": "event",
    "美食": "food",
    "氛围": "mood",
    "风格": "style",
}

# ── Scoring configuration (model-led, rules as light correction) ──
SCORING_CONFIG = {
    "source_weight": {
        "llm": 1.0,
        "vision_object": 0.85,
        "vision_scene": 0.80,
        "vision_action": 0.80,
        "ocr": 0.70,
        "asr": 0.68,
        "gps": 0.60,
        "exif": 0.55,
        "metadata": 0.45,
        "rule": 0.30,
        "user": 1.1,
    },
    "display_threshold": 0.55,
    "write_threshold": 0.45,
    "hierarchy_bonus": 0.12,
    "conflict_penalty": 0.15,
    "cooccurrence_bonus": 0.10,
    "negative_penalty": 0.12,
    "confidence_bands": {
        "high": 0.80,
        "medium": 0.55,
        "low": 0.0,
    },
}

# ── Video aggregation thresholds (configurable per semantic_slot) ──
AGGREGATION_CONFIG = {
    "frame_to_segment": {
        "default": {"sustained_threshold": 0.6, "brief_threshold": 0.3},
        "event": {"sustained_threshold": 0.3, "brief_threshold": 0.1},
        "person": {"sustained_threshold": 0.4, "brief_threshold": 0.15},
        "object": {"sustained_threshold": 0.5, "brief_threshold": 0.2},
    },
    "segment_to_asset": {
        "default": {"global_theme_threshold": 0.5, "local_content_threshold": 0.15},
        "event": {"global_theme_threshold": 0.25, "local_content_threshold": 0.1},
        "mood": {"global_theme_threshold": 0.4, "local_content_threshold": 0.2},
    },
}

# ── Search hybrid recall weights ──
SEARCH_WEIGHTS = {
    "tag_match": 0.50,
    "fts_match": 0.30,
    "embedding_match": 0.20,
    "custom_tag_boost": 0.10,
}

# ── Evidence limits ──
EVIDENCE_LIMITS = {
    "max_per_asset": 100,
    "max_per_segment_tag": 5,
}

# ── Phase 3: Tag hit strength tiers ──
TAG_HIT_STRENGTH = {
    "exact": 1.00,
    "normalized": 0.95,
    "alias": 0.90,
    "custom": 0.85,
    "synonym": 0.80,
    "parent_child": 0.72,
}

# ── Phase 3: Dynamic weights by query type ──
QUERY_TYPE_WEIGHTS = {
    "exact_tag": {"tag": 0.65, "fts": 0.20, "embedding": 0.15},
    "alias_tag": {"tag": 0.60, "fts": 0.25, "embedding": 0.15},
    "composed_query": {"tag": 0.40, "fts": 0.25, "embedding": 0.35},
    "abstract_intent": {"tag": 0.25, "fts": 0.20, "embedding": 0.55},
}

# ── Phase 3: Abstract intent signal words ──
ABSTRACT_INTENT_KEYWORDS: Set[str] = {
    "感", "氛围", "适合", "风格", "像", "片段", "封面", "开场", "治愈", "高级",
}

# ── Map 25 TAG_CATEGORIES → 16 SEMANTIC_SLOTS ──
_TAG_CATEGORY_TO_SLOT = {
    "objects": "object",
    "actions": "action",
    "scene": "scene",
    "mood": "mood",
    "concepts": "scene",
    "style": "style",
    "use_cases": "event",
    "materials_textures": "object",
    "architecture_style": "place",
    "food_cuisine": "food",
    "animal_species": "animal",
    "vehicle_transport": "object",
    "clothing_fashion": "person",
    "body_language": "action",
    "spatial_relations": "scene",
    "cultural_elements": "scene",
    "brand_product": "object",
    "audio_mood": "mood",
    "color_palette": "style",
    "composition": "shot_type",
    "nature_landscape": "nature",
    "weather_atmosphere": "weather",
    "social_context": "scene",
    "industry_domain": "event",
    "narrative_technique": "style",
}

# ── Map flat semantic_json fields → SEMANTIC_SLOTS ──
_FIELD_TO_SLOT = {
    "setting": "place",
    "activity": "action",
    "weather": "weather",
    "time_of_day": "time_of_day",
    "season": "season",
    "visual_style": "style",
    "camera_movement": "shot_type",
    "shot_type": "shot_type",
    "perspective": "shot_type",
}

# Path to ChatGPT seed data (used once during first init)
_SEED_DATA_DIR = Path(os.path.expanduser(
    "~/Downloads/语义数据库-chatgpt-20260306"
))

# ── 62 semantic dimension fields ──
SEMANTIC_DIMENSIONS = [
    # original 43
    "scene_description", "mood", "primary_subject", "secondary_subjects",
    "content_type", "activity", "action_intensity", "setting", "location_type",
    "time_of_day", "season", "weather", "camera_movement", "camera_platform",
    "shot_type", "framing", "perspective", "visual_style", "color_tone",
    "lighting_condition", "narrative_role", "clip_purpose", "emotion_intensity",
    "people_presence", "quality_tier", "duration_bucket", "aspect_ratio_bucket",
    "orientation", "stability_level", "dominant_color", "brightness_level",
    "saturation_level", "motion_level", "texture_complexity", "face_presence_level",
    "use_cases", "audience_intent", "business_tags", "topics", "search_keywords",
    "structured_tags", "search_facets", "index_layers",
    # new 19 dimension fields for expanded taxonomy
    "material_type", "texture_detail", "architecture_style_field",
    "food_type", "animal_species_field", "vehicle_type", "clothing_type",
    "body_language_cues", "spatial_layout", "cultural_context", "brand_hints",
    "audio_character", "color_palette_type", "composition_technique",
    "nature_subtype", "weather_detail", "social_setting", "industry_context",
    "narrative_device",
]
class GlobalMediaLibrary(FingerprintMixin):
    def __init__(self, db_path: Optional[Path] = None, cache_dir: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_LIBRARY_DB)
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._toolkit: Optional[VideoAssetToolkit] = None
        self._relink_checked: Dict[str, float] = {}
        self._semantic_refresh_checked: Dict[str, float] = {}
        self._vector_cache: Dict[str, Any] = {
            "model": "",
            "updated_at": "",
            "uids": [],
            "matrix": None,
        }
        self._query_embedding_cache: Dict[str, Dict[str, Any]] = {}
        self._init_db()

    # ------------------------------------------------------------------
    # DB basics

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        # WAL 提升并发读写能力，降低搜索与入库互相阻塞概率。
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            pass
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

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

    # ------------------------------------------------------------------
    # Helpers

    @staticmethod
    def _is_video_file(path: Path) -> bool:
        return path.suffix.lower() in VIDEO_EXTENSIONS

    @staticmethod
    def _is_image_file(path: Path) -> bool:
        return path.suffix.lower() in IMAGE_EXTENSIONS

    @staticmethod
    def _infer_asset_kind(filename: Optional[str], path_text: Optional[str]) -> str:
        raw = str(path_text or filename or "").strip()
        suffix = Path(raw).suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            return "video"
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        return "unknown"

    @staticmethod
    def _normalize_media_type(media_type: Optional[str]) -> str:
        m = str(media_type or "").strip().lower()
        if m in {"video", "videos"}:
            return "video"
        if m in {"image", "images", "photo", "photos", "picture", "pictures"}:
            return "image"
        return "all"

    @staticmethod
    def _media_type_where_sql(media_type: str, alias: str = "") -> str:
        m = GlobalMediaLibrary._normalize_media_type(media_type)
        if m == "all":
            return ""
        col = f"{alias}.filename" if alias else "filename"
        if m == "video":
            exts = sorted(VIDEO_EXTENSIONS)
        else:
            exts = sorted(IMAGE_EXTENSIONS)
        return "(" + " OR ".join([f"lower({col}) GLOB '*{ext}'" for ext in exts]) + ")"

    @staticmethod
    def _run_with_retry(fn, attempts: int = 3, base_delay: float = 1.5):
        last_error = None
        for i in range(attempts):
            try:
                return fn()
            except Exception as exc:
                last_error = exc
                if i >= attempts - 1:
                    raise
                time.sleep(base_delay * (2 ** i))
        if last_error is not None:
            raise last_error
        return None

    def _discover_videos(self, input_path: Path) -> List[Path]:
        if input_path.is_file() and self._is_video_file(input_path):
            return [input_path]
        if input_path.is_dir():
            return sorted(
                p for p in input_path.rglob("*")
                if p.is_file() and self._is_video_file(p)
            )
        return []

    def _discover_images(self, input_path: Path) -> List[Path]:
        if input_path.is_file() and self._is_image_file(input_path):
            return [input_path]
        if input_path.is_dir():
            return sorted(
                p for p in input_path.rglob("*")
                if p.is_file() and self._is_image_file(p)
            )
        return []

    # Public adapter surface for app_api; do not call private helpers跨模块。
    def discover_videos(self, input_path: Path) -> List[Path]:
        return self._discover_videos(input_path)

    def discover_images(self, input_path: Path) -> List[Path]:
        return self._discover_images(input_path)

    # _compute_sha256 → FingerprintMixin

    @staticmethod
    def _parse_fps(raw) -> Optional[float]:
        if raw is None:
            return None
        s = str(raw).strip()
        if not s:
            return None
        if "/" in s:
            num, den = s.split("/", 1)
            try:
                den_f = float(den)
                if den_f == 0:
                    return None
                return float(num) / den_f
            except Exception:
                return None
        try:
            return float(s)
        except Exception:
            return None

    @staticmethod
    def _parse_resolution(resolution: Optional[str]) -> tuple[Optional[int], Optional[int]]:
        if not resolution or "x" not in str(resolution):
            return None, None
        try:
            w, h = str(resolution).lower().split("x", 1)
            return int(w), int(h)
        except Exception:
            return None, None

    # _compute_phash, _compute_image_phash → FingerprintMixin

    # _phash_distance, FINGERPRINT_VERSION → FingerprintMixin

    # _compute_content_fingerprint, _compute_thumbnail_hash → FingerprintMixin

    def _toolkit_instance(self) -> VideoAssetToolkit:
        if self._toolkit is None:
            self._toolkit = VideoAssetToolkit()
        return self._toolkit

    @staticmethod
    def _vision_enrich_enabled() -> bool:
        if str(os.environ.get("VIDEOEDITOR_DISABLE_VISION_ENRICH", "")).strip() == "1":
            return False
        return bool(str(os.environ.get("OPENAI_API_KEY", "")).strip())

    @staticmethod
    def _llm_tagging_enabled() -> bool:
        if str(os.environ.get("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", "")).strip() == "1":
            return False
        return bool(str(os.environ.get("OPENAI_API_KEY", "")).strip())

    # ------------------------------------------------------------------
    # Thumbnail generation

    def _thumbnail_dir(self) -> Path:
        return self.db_path.parent / "thumbnails"

    def thumbnail_path(self, uid: str) -> Optional[str]:
        """Return the absolute path to a thumbnail if it exists, else None."""
        if not uid:
            return None
        p = self._thumbnail_dir() / uid[:2] / f"{uid}.jpg"
        return str(p) if p.exists() else None

    def _generate_thumbnail(self, uid: str, file_path: Path, asset_kind: str = "video") -> bool:
        """Generate a 320px JPEG thumbnail for an asset. Returns True on success."""
        if cv2 is None:
            return False
        try:
            thumb_dir = self._thumbnail_dir() / uid[:2]
            thumb_dir.mkdir(parents=True, exist_ok=True)
            out_path = thumb_dir / f"{uid}.jpg"
            if out_path.exists():
                return True

            frame = None
            if asset_kind == "image" or self._is_image_file(file_path):
                frame = cv2.imread(str(file_path))
            else:
                cap = cv2.VideoCapture(str(file_path))
                if not cap.isOpened():
                    cap.release()
                    return False
                try:
                    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    target = int(max(total - 1, 0) * 0.35) if total > 0 else 0
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        return False
                finally:
                    cap.release()

            if frame is None:
                return False
            h, w = frame.shape[:2]
            if max(h, w) > 320:
                scale = 320.0 / max(h, w)
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(out_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            return out_path.exists()
        except Exception:
            return False

    def generate_missing_thumbnails(self, progress_cb=None) -> Dict[str, int]:
        """Generate thumbnails for all assets that don't have one yet."""
        stats = {"generated": 0, "skipped": 0, "failed": 0}
        with self._connect() as conn:
            rows = conn.execute("SELECT uid, primary_path, filename FROM assets").fetchall()
        for i, row in enumerate(rows):
            uid = row["uid"]
            if self.thumbnail_path(uid):
                stats["skipped"] += 1
                continue
            fpath = Path(row["primary_path"] or "")
            if not fpath.exists():
                stats["failed"] += 1
                continue
            kind = self._infer_asset_kind(row["filename"], str(fpath))
            if self._generate_thumbnail(uid, fpath, kind):
                stats["generated"] += 1
            else:
                stats["failed"] += 1
            if progress_cb and len(rows) > 0:
                progress_cb(int((i + 1) * 100 / len(rows)))
        return stats

    # ------------------------------------------------------------------
    # Keyframe extraction (data URLs for LLM vision)

    @staticmethod
    def _extract_keyframe_data_urls(
        path: Path,
        ratios: Optional[List[float]] = None,
        jpeg_quality: int = 82,
    ) -> List[str]:
        if GlobalMediaLibrary._is_image_file(path):
            img_url = GlobalMediaLibrary._extract_image_data_url(path, jpeg_quality=jpeg_quality)
            return [img_url] if img_url else []
        if cv2 is None:
            return []
        ratios = ratios or [0.12, 0.42, 0.75]
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            cap.release()
            return []
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_indexes = []
        if total <= 0:
            frame_indexes = [0]
        else:
            for r in ratios:
                try:
                    idx = int(max(0.0, min(1.0, float(r))) * max(total - 1, 0))
                except Exception:
                    idx = 0
                frame_indexes.append(idx)
        dedup_indexes = []
        seen = set()
        for idx in frame_indexes:
            if idx in seen:
                continue
            seen.add(idx)
            dedup_indexes.append(idx)

        out: List[str] = []
        try:
            for frame_idx in dedup_indexes:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                if not ok:
                    continue
                b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
                out.append(f"data:image/jpeg;base64,{b64}")
        finally:
            cap.release()
        return out

    @staticmethod
    def _extract_keyframe_data_url(path: Path) -> Optional[str]:
        urls = GlobalMediaLibrary._extract_keyframe_data_urls(path, ratios=[0.35], jpeg_quality=82)
        return urls[0] if urls else None

    @staticmethod
    def _extract_image_data_url(path: Path, jpeg_quality: int = 86) -> Optional[str]:
        if cv2 is None:
            return None
        img = cv2.imread(str(path))
        if img is None:
            return None
        ok, encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
        if not ok:
            return None
        b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def _vision_enrich_tags(self, path: Path) -> Dict:
        if not self._vision_enrich_enabled():
            return {}
        data_url = self._extract_keyframe_data_url(path)
        if not data_url:
            return {}
        try:
            import openai
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            model = os.environ.get("OPENAI_VISION_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
            prompt = (
                "你是素材语义标注器（图片/视频均可）。请识别画面里的建筑类型、地标线索、桥梁类型和场景要素。"
                "只返回 JSON，不要解释。格式："
                "{\"scene\":\"\",\"keywords\":[],\"landmarks\":[],\"architecture_style\":[]}"
                "关键词尽量中英混合，最多12个。"
            )
            rsp = client.chat.completions.create(
                model=model,
                max_tokens=280,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": "你是严格 JSON 输出助手。"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                        ],
                    },
                ],
            )
            raw = (rsp.choices[0].message.content or "").strip()
            if not raw:
                return {}
            raw = raw.strip("` \n")
            if raw.startswith("json"):
                raw = raw[4:].strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return {}
            return parsed
        except Exception:
            return {}

    @staticmethod
    def _safe_json_loads(raw: Optional[str], default):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    @staticmethod
    def _empty_structured_tag_schema() -> Dict[str, Any]:
        return {
            "tags": {
                cat: {"zh": [], "en": [], "confidence": 0.0}
                for cat in TAG_TAXONOMY
            },
            "quality_checks": {
                "generic_terms_removed": True,
                "duplicate_terms_removed": True,
                "covers_literal_and_abstract": False,
                "search_ready": False,
            },
        }

    @staticmethod
    def _seed_concept_library() -> Dict[str, List[tuple[str, str]]]:
        return {
            "concepts": [
                ("生活方式", "lifestyle"), ("自由", "freedom"), ("成就", "achievement"),
                ("自律", "discipline"), ("松弛感", "relaxed vibe"), ("治愈", "healing"),
                ("孤独", "loneliness"), ("连接", "connection"), ("成长", "growth"),
                ("焦虑", "anxiety"), ("逃离", "escape"), ("仪式感", "ritual"),
                ("高效", "productivity"), ("极简", "minimalism"), ("都市感", "urban"),
                ("自然疗愈", "nature therapy"), ("数字游民", "digital nomad"),
                ("远程工作", "remote work"), ("探索", "exploration"), ("归属感", "belonging"),
                ("亲密", "intimacy"), ("健康", "wellness"), ("怀旧", "nostalgia"),
                ("创造力", "creativity"), ("可持续", "sustainability"), ("平衡", "balance"),
            ],
            "use_cases": [
                ("旅行vlog", "travel vlog"), ("城市宣传", "city promo"),
                ("酒店民宿", "hotel/airbnb"), ("咖啡品牌", "coffee brand"),
                ("健身瑜伽", "fitness/yoga"), ("心理疗愈", "mental health"),
                ("创业职场", "startup/career"), ("纪录片", "doc style"),
                ("广告片", "commercial"), ("社媒短视频", "social short"),
                ("教育培训", "education"), ("产品评测", "product review"),
                ("婚礼活动", "wedding"), ("音乐MV", "music video"),
                ("房产展示", "real estate"), ("企业宣传", "corporate"),
            ],
            "mood": [
                ("治愈", "healing"), ("宁静", "calm"), ("活力", "energetic"),
                ("史诗感", "epic"), ("孤独", "lonely"), ("温暖", "warm"),
                ("紧张", "tense"), ("轻松", "relaxed"), ("忧郁", "melancholic"),
                ("欢快", "joyful"), ("神秘", "mysterious"), ("浪漫", "romantic"),
                ("庄严", "solemn"), ("激昂", "passionate"), ("慵懒", "lazy"),
            ],
            "style": [
                ("电影感", "cinematic"), ("纪实", "documentary"), ("vlog", "vlog"),
                ("广告感", "commercial style"), ("手持纪实", "handheld doc"),
                ("航拍", "aerial"), ("夜景氛围", "night aesthetic"), ("极简", "minimal"),
                ("复古", "retro"), ("赛博朋克", "cyberpunk"), ("水墨风", "ink wash"),
                ("胶片感", "film grain"), ("高饱和", "high saturation"),
                ("低饱和", "desaturated"), ("延时", "timelapse"),
            ],
            "objects": [
                ("建筑", "building"), ("桥梁", "bridge"), ("植物", "plant"),
                ("花朵", "flower"), ("手机", "phone"), ("电脑", "computer"),
                ("书籍", "book"), ("灯光", "light"), ("镜子", "mirror"),
                ("窗户", "window"), ("门", "door"), ("杯子", "cup"),
                ("家具", "furniture"), ("乐器", "instrument"), ("画作", "painting"),
            ],
            "actions": [
                ("行走", "walking"), ("奔跑", "running"), ("跳跃", "jumping"),
                ("游泳", "swimming"), ("骑行", "cycling"), ("烹饪", "cooking"),
                ("阅读", "reading"), ("写作", "writing"), ("舞蹈", "dancing"),
                ("拍照", "photographing"), ("交谈", "chatting"), ("拥抱", "hugging"),
                ("冥想", "meditating"), ("攀登", "climbing"), ("驾驶", "driving"),
            ],
            "scene": [
                ("街道", "street"), ("咖啡馆", "cafe"), ("图书馆", "library"),
                ("公园", "park"), ("海边", "seaside"), ("山顶", "summit"),
                ("市集", "market"), ("车站", "station"), ("机场", "airport"),
                ("教室", "classroom"), ("办公室", "office"), ("厨房", "kitchen"),
                ("卧室", "bedroom"), ("阳台", "balcony"), ("屋顶", "rooftop"),
            ],
            "materials_textures": [
                ("木质", "wood"), ("金属", "metal"), ("玻璃", "glass"),
                ("石材", "stone"), ("混凝土", "concrete"), ("皮革", "leather"),
                ("丝绸", "silk"), ("棉麻", "linen"), ("陶瓷", "ceramic"),
                ("竹子", "bamboo"), ("纸张", "paper"), ("砖块", "brick"),
                ("大理石", "marble"), ("铁锈", "rust"), ("毛绒", "plush"),
            ],
            "architecture_style": [
                ("哥特式", "gothic"), ("巴洛克", "baroque"), ("现代主义", "modernist"),
                ("中式传统", "chinese traditional"), ("日式和风", "japanese style"),
                ("地中海", "mediterranean"), ("工业风", "industrial"),
                ("包豪斯", "bauhaus"), ("新古典", "neoclassical"),
                ("后现代", "postmodern"), ("装饰艺术", "art deco"),
                ("极简建筑", "minimalist architecture"),
            ],
            "food_cuisine": [
                ("中餐", "chinese food"), ("日料", "japanese food"),
                ("西餐", "western food"), ("甜点", "dessert"), ("咖啡", "coffee"),
                ("茶", "tea"), ("鸡尾酒", "cocktail"), ("烧烤", "barbecue"),
                ("面包", "bread"), ("沙拉", "salad"), ("火锅", "hotpot"),
                ("寿司", "sushi"), ("披萨", "pizza"), ("冰淇淋", "ice cream"),
            ],
            "animal_species": [
                ("猫", "cat"), ("狗", "dog"), ("鸟类", "bird"),
                ("鱼类", "fish"), ("蝴蝶", "butterfly"), ("马", "horse"),
                ("海豚", "dolphin"), ("鹿", "deer"), ("兔子", "rabbit"),
                ("松鼠", "squirrel"), ("海鸥", "seagull"), ("蜜蜂", "bee"),
            ],
            "vehicle_transport": [
                ("汽车", "car"), ("自行车", "bicycle"), ("摩托车", "motorcycle"),
                ("火车", "train"), ("飞机", "airplane"), ("船", "boat"),
                ("电车", "tram"), ("缆车", "cable car"), ("帆船", "sailboat"),
                ("滑板", "skateboard"),
            ],
            "clothing_fashion": [
                ("西装", "suit"), ("连衣裙", "dress"), ("运动装", "sportswear"),
                ("汉服", "hanfu"), ("和服", "kimono"), ("牛仔", "denim"),
                ("配饰", "accessories"), ("帽子", "hat"), ("围巾", "scarf"),
                ("运动鞋", "sneakers"),
            ],
            "body_language": [
                ("微笑", "smiling"), ("思考", "thinking"), ("指向", "pointing"),
                ("鼓掌", "clapping"), ("挥手", "waving"), ("叉腰", "hands on hips"),
                ("俯身", "leaning"), ("仰望", "looking up"), ("低头", "head down"),
                ("双臂交叉", "arms crossed"),
            ],
            "spatial_relations": [
                ("前景", "foreground"), ("背景", "background"), ("左侧", "left side"),
                ("右侧", "right side"), ("中心", "center"), ("边缘", "edge"),
                ("对称", "symmetry"), ("引导线", "leading line"),
            ],
            "cultural_elements": [
                ("节日", "festival"), ("传统", "tradition"), ("宗教", "religion"),
                ("民俗", "folklore"), ("书法", "calligraphy"), ("手工艺", "craft"),
                ("庙会", "temple fair"), ("婚俗", "wedding customs"),
                ("茶道", "tea ceremony"), ("花道", "ikebana"),
                ("舞龙", "dragon dance"), ("灯笼", "lantern"),
            ],
            "brand_product": [
                ("科技产品", "tech product"), ("美妆", "beauty/cosmetics"),
                ("时装", "fashion brand"), ("运动品牌", "sports brand"),
                ("家居", "home brand"), ("汽车品牌", "auto brand"),
                ("奢侈品", "luxury"), ("快消品", "FMCG"),
                ("母婴", "baby/maternity"), ("宠物用品", "pet products"),
            ],
            "audio_mood": [
                ("轻音乐", "light music"), ("电子乐", "electronic"),
                ("古典", "classical"), ("爵士", "jazz"), ("环境音", "ambient"),
                ("节奏感", "rhythmic"), ("人声清唱", "a cappella"),
                ("自然声", "nature sounds"), ("白噪音", "white noise"),
            ],
            "color_palette": [
                ("暖色调", "warm tones"), ("冷色调", "cool tones"),
                ("莫兰迪", "morandi"), ("撞色", "color blocking"),
                ("黑白", "monochrome"), ("渐变", "gradient"),
                ("高对比", "high contrast"), ("柔和", "soft palette"),
                ("金色", "golden"), ("蓝调", "blue tones"),
            ],
            "composition": [
                ("三分法", "rule of thirds"), ("居中", "centered"),
                ("对角线", "diagonal"), ("框中框", "frame within frame"),
                ("留白", "negative space"), ("黄金螺旋", "golden spiral"),
                ("俯拍", "overhead"), ("仰拍", "low angle"),
            ],
            "nature_landscape": [
                ("山脉", "mountains"), ("湖泊", "lake"), ("河流", "river"),
                ("瀑布", "waterfall"), ("沙漠", "desert"), ("草原", "grassland"),
                ("冰川", "glacier"), ("珊瑚礁", "coral reef"), ("峡谷", "canyon"),
                ("火山", "volcano"), ("湿地", "wetland"), ("洞穴", "cave"),
            ],
            "weather_atmosphere": [
                ("晴天", "sunny"), ("多云", "cloudy"), ("雨天", "rainy"),
                ("雪天", "snowy"), ("雾", "foggy"), ("彩虹", "rainbow"),
                ("暴风雨", "storm"), ("星空", "starry"), ("极光", "aurora"),
            ],
            "social_context": [
                ("独处", "solitude"), ("约会", "date"), ("家庭", "family"),
                ("朋友聚会", "friends gathering"), ("团队", "team"),
                ("派对", "party"), ("会议", "meeting"), ("社区", "community"),
                ("仪式", "ceremony"), ("游行", "parade"),
            ],
            "industry_domain": [
                ("科技", "technology"), ("医疗", "healthcare"), ("教育", "education"),
                ("金融", "finance"), ("零售", "retail"), ("餐饮", "food service"),
                ("房地产", "real estate"), ("旅游", "tourism"),
                ("制造业", "manufacturing"), ("创意产业", "creative industry"),
                ("体育", "sports"), ("娱乐", "entertainment"),
            ],
            "narrative_technique": [
                ("蒙太奇", "montage"), ("平行叙事", "parallel narrative"),
                ("倒叙", "flashback"), ("悬念", "suspense"),
                ("象征", "symbolism"), ("隐喻", "metaphor"),
                ("对比", "contrast"), ("重复", "repetition"),
            ],
        }

    @staticmethod
    def _bilingual_term_map() -> Dict[str, str]:
        pairs = [
            # landmark / place
            ("教堂", "church"), ("大教堂", "cathedral"), ("礼拜堂", "chapel"),
            ("桥梁", "bridge"), ("铁桥", "iron bridge"), ("钢桥", "steel bridge"),
            ("城堡", "castle"), ("寺庙", "temple"), ("修道院", "monastery"),
            ("建筑", "architecture"), ("地标", "landmark"), ("城市", "city"),
            ("街道", "street"), ("山地", "mountain"), ("海边", "beach"),
            ("森林", "forest"), ("树木", "tree"), ("自然", "nature"),
            ("风景", "landscape"), ("天空", "sky"), ("水域", "water"),
            ("雪景", "snow"), ("日落", "sunset"), ("夜景", "night"),
            ("咖啡馆", "cafe"), ("公园", "park"), ("广场", "plaza"),
            ("屋顶", "rooftop"), ("小巷", "alley"), ("市中心", "downtown"),
            ("天际线", "skyline"), ("老城区", "old town"),
            # camera / style
            ("航拍", "aerial"), ("手持", "handheld"), ("固定机位", "static"),
            ("特写", "close-up"), ("远景", "wide shot"), ("延时", "timelapse"),
            ("复古", "retro"), ("赛博朋克", "cyberpunk"), ("胶片感", "film grain"),
            ("水墨风", "ink wash"), ("高饱和", "high saturation"), ("低饱和", "desaturated"),
            # mood / concept
            ("治愈", "healing"), ("松弛感", "relaxed vibe"), ("探索", "exploration"),
            ("怀旧", "nostalgia"), ("创造力", "creativity"), ("可持续", "sustainability"),
            ("平衡", "balance"), ("忧郁", "melancholic"), ("欢快", "joyful"),
            ("神秘", "mysterious"), ("浪漫", "romantic"), ("庄严", "solemn"),
            ("激昂", "passionate"), ("慵懒", "lazy"),
            # use case
            ("旅行vlog", "travel vlog"), ("旅行vlog", "travel_vlog"),
            ("城市宣传", "city promo"), ("纪录片", "doc style"),
            ("广告片", "commercial"), ("教育培训", "education"),
            ("产品评测", "product review"), ("婚礼活动", "wedding"),
            ("音乐MV", "music video"), ("房产展示", "real estate"),
            ("企业宣传", "corporate"), ("社媒短视频", "social short"),
            # action
            ("动作混剪", "action_montage"), ("地标故事", "landmark_story"),
            ("氛围空镜", "atmospheric_broll"), ("主镜头", "hero_shot"),
            ("叙事镜头", "storytelling_clip"), ("人物", "person"),
            ("人群", "people"), ("车辆", "vehicle"), ("活动", "activity"),
            ("室外", "outdoor"), ("室内", "indoor"),
            ("行走", "walking"), ("奔跑", "running"), ("跳跃", "jumping"),
            ("游泳", "swimming"), ("骑行", "cycling"), ("烹饪", "cooking"),
            ("阅读", "reading"), ("写作", "writing"), ("舞蹈", "dancing"),
            ("拍照", "photographing"), ("交谈", "chatting"), ("拥抱", "hugging"),
            ("冥想", "meditating"), ("攀登", "climbing"), ("驾驶", "driving"),
            # material
            ("木质", "wood"), ("金属", "metal"), ("玻璃", "glass"),
            ("石材", "stone"), ("混凝土", "concrete"), ("皮革", "leather"),
            ("丝绸", "silk"), ("棉麻", "linen"), ("陶瓷", "ceramic"),
            ("竹子", "bamboo"), ("纸张", "paper"), ("砖块", "brick"),
            ("大理石", "marble"), ("铁锈", "rust"), ("毛绒", "plush"),
            # architecture
            ("哥特式", "gothic"), ("巴洛克", "baroque"), ("现代主义", "modernist"),
            ("中式传统", "chinese traditional"), ("日式和风", "japanese style"),
            ("地中海", "mediterranean"), ("工业风", "industrial"),
            ("包豪斯", "bauhaus"), ("新古典", "neoclassical"),
            ("后现代", "postmodern"), ("装饰艺术", "art deco"),
            # food
            ("中餐", "chinese food"), ("日料", "japanese food"),
            ("西餐", "western food"), ("甜点", "dessert"), ("咖啡", "coffee"),
            ("茶", "tea"), ("鸡尾酒", "cocktail"), ("烧烤", "barbecue"),
            ("面包", "bread"), ("沙拉", "salad"), ("火锅", "hotpot"),
            ("寿司", "sushi"), ("披萨", "pizza"), ("冰淇淋", "ice cream"),
            # animal
            ("猫", "cat"), ("狗", "dog"), ("鸟类", "bird"),
            ("鱼类", "fish"), ("蝴蝶", "butterfly"), ("马", "horse"),
            ("海豚", "dolphin"), ("鹿", "deer"), ("兔子", "rabbit"),
            ("海鸥", "seagull"), ("蜜蜂", "bee"), ("松鼠", "squirrel"),
            # vehicle
            ("汽车", "car"), ("自行车", "bicycle"), ("摩托车", "motorcycle"),
            ("火车", "train"), ("飞机", "airplane"), ("船", "boat"),
            ("电车", "tram"), ("缆车", "cable car"), ("帆船", "sailboat"),
            ("滑板", "skateboard"),
            # clothing
            ("西装", "suit"), ("连衣裙", "dress"), ("运动装", "sportswear"),
            ("汉服", "hanfu"), ("和服", "kimono"), ("牛仔", "denim"),
            ("配饰", "accessories"), ("帽子", "hat"), ("围巾", "scarf"),
            ("运动鞋", "sneakers"),
            # body language
            ("微笑", "smiling"), ("思考", "thinking"), ("指向", "pointing"),
            ("鼓掌", "clapping"), ("挥手", "waving"), ("叉腰", "hands on hips"),
            ("俯身", "leaning"), ("仰望", "looking up"), ("低头", "head down"),
            ("双臂交叉", "arms crossed"),
            # cultural
            ("节日", "festival"), ("传统", "tradition"), ("宗教", "religion"),
            ("民俗", "folklore"), ("书法", "calligraphy"), ("手工艺", "craft"),
            ("庙会", "temple fair"), ("婚俗", "wedding customs"),
            ("茶道", "tea ceremony"), ("花道", "ikebana"),
            ("舞龙", "dragon dance"), ("灯笼", "lantern"),
            # brand / product
            ("科技产品", "tech product"), ("美妆", "beauty/cosmetics"),
            ("时装", "fashion brand"), ("运动品牌", "sports brand"),
            ("家居", "home brand"), ("奢侈品", "luxury"), ("快消品", "FMCG"),
            # audio
            ("轻音乐", "light music"), ("电子乐", "electronic"),
            ("古典", "classical"), ("爵士", "jazz"), ("环境音", "ambient"),
            ("节奏感", "rhythmic"), ("自然声", "nature sounds"),
            # color palette
            ("暖色调", "warm tones"), ("冷色调", "cool tones"),
            ("莫兰迪", "morandi"), ("撞色", "color blocking"),
            ("黑白", "monochrome"), ("渐变", "gradient"),
            ("高对比", "high contrast"), ("柔和", "soft palette"),
            # composition
            ("三分法", "rule of thirds"), ("居中", "centered"),
            ("对角线", "diagonal"), ("框中框", "frame within frame"),
            ("留白", "negative space"), ("黄金螺旋", "golden spiral"),
            ("俯拍", "overhead"), ("仰拍", "low angle"),
            # nature
            ("山脉", "mountains"), ("湖泊", "lake"), ("河流", "river"),
            ("瀑布", "waterfall"), ("沙漠", "desert"), ("草原", "grassland"),
            ("冰川", "glacier"), ("珊瑚礁", "coral reef"), ("峡谷", "canyon"),
            ("火山", "volcano"), ("湿地", "wetland"), ("洞穴", "cave"),
            # weather
            ("晴天", "sunny"), ("多云", "cloudy"), ("雨天", "rainy"),
            ("雪天", "snowy"), ("雾", "foggy"), ("彩虹", "rainbow"),
            ("暴风雨", "storm"), ("星空", "starry"), ("极光", "aurora"),
            # social
            ("独处", "solitude"), ("约会", "date"), ("家庭", "family"),
            ("朋友聚会", "friends gathering"), ("团队", "team"),
            ("派对", "party"), ("会议", "meeting"), ("社区", "community"),
            # industry
            ("科技", "technology"), ("医疗", "healthcare"), ("教育", "education"),
            ("金融", "finance"), ("零售", "retail"), ("餐饮", "food service"),
            ("房地产", "real estate"), ("旅游", "tourism"),
            ("制造业", "manufacturing"), ("创意产业", "creative industry"),
            ("体育", "sports"), ("娱乐", "entertainment"),
            # narrative
            ("蒙太奇", "montage"), ("平行叙事", "parallel narrative"),
            ("倒叙", "flashback"), ("悬念", "suspense"),
            ("象征", "symbolism"), ("隐喻", "metaphor"),
            ("对比", "contrast"), ("重复", "repetition"),
        ]
        for cat_pairs in GlobalMediaLibrary._seed_concept_library().values():
            pairs.extend(cat_pairs)
        mapping: Dict[str, str] = {}
        for zh, en in pairs:
            zh_key = str(zh).strip().lower()
            en_key = str(en).strip().lower()
            if zh_key and en_key:
                mapping[zh_key] = en
                mapping[en_key] = zh
        return mapping

    @staticmethod
    def _split_terms(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            out = []
            for item in value:
                out.extend(GlobalMediaLibrary._split_terms(item))
            return out
        text = str(value).strip()
        if not text:
            return []
        return [x.strip() for x in re.split(r"[\n,，;；|/]+", text) if x.strip()]

    @staticmethod
    def _normalize_terms(items: Iterable[str], lang: str = "en", max_items: int = 18) -> List[str]:
        out = []
        seen = set()
        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            if lang == "en":
                text = text.lower()
            key = text.lower()
            if key in GENERIC_TAG_TERMS:
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= max_items:
                break
        return out

    @staticmethod
    def _safe_json_object_from_text(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        text = str(raw or "").strip()
        if not text:
            return {}
        text = text.strip("` \n")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            parsed = json.loads(m.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _clamp_confidence(value: Any, default: float = 0.55) -> float:
        try:
            f = float(value)
        except Exception:
            f = default
        if f < 0.0:
            return 0.0
        if f > 1.0:
            return 1.0
        return round(f, 3)

    @staticmethod
    def _seed_expand_terms(category: str, evidence_text: str) -> Dict[str, List[str]]:
        pool = GlobalMediaLibrary._seed_concept_library().get(category, [])
        if not pool:
            return {"zh": [], "en": []}
        text = str(evidence_text or "").lower()
        pool_dict = {str(zh): str(en) for zh, en in pool}
        zh_terms = []
        en_terms = []
        for zh, en in pool:
            if str(zh).lower() in text or str(en).lower() in text:
                zh_terms.append(zh)
                en_terms.append(en)
        if not zh_terms and category == "concepts":
            if any(k in text for k in ["beach", "ocean", "coast", "forest", "mountain", "nature", "sunset", "疗愈", "自然"]):
                zh_terms.extend(["自然疗愈", "治愈", "探索", "逃离", "松弛感"])
            if any(k in text for k in ["city", "urban", "street", "night", "城市", "街头"]):
                zh_terms.extend(["都市感", "连接", "成长", "归属感"])
            if any(k in text for k in ["person", "people", "vlog", "talk", "人物", "口播"]):
                zh_terms.extend(["生活方式", "连接", "亲密"])
            if any(k in text for k in ["laptop", "cafe", "workspace", "remote", "工作", "咖啡"]):
                zh_terms.extend(["数字游民", "远程工作", "高效"])
            if any(k in text for k in ["sports", "ski", "action", "运动", "滑雪"]):
                zh_terms.extend(["成就", "自律", "探索"])
            for zh in zh_terms[:]:
                en = pool_dict.get(zh)
                if en:
                    en_terms.append(en)
        if not zh_terms and category == "use_cases":
            if any(k in text for k in ["travel", "trip", "journey", "mountain", "beach", "city", "旅行", "地标"]):
                zh_terms.extend(["旅行vlog", "城市宣传", "社媒短视频"])
            if any(k in text for k in ["hotel", "room", "interior", "室内", "民宿"]):
                zh_terms.extend(["酒店民宿", "广告片"])
            if any(k in text for k in ["coffee", "cafe", "咖啡"]):
                zh_terms.extend(["咖啡品牌", "社媒短视频"])
            if any(k in text for k in ["fitness", "yoga", "sports", "健身", "瑜伽"]):
                zh_terms.extend(["健身瑜伽", "社媒短视频"])
            if any(k in text for k in ["documentary", "interview", "history", "church", "cathedral", "纪录"]):
                zh_terms.extend(["纪录片", "城市宣传"])
            if any(k in text for k in ["office", "laptop", "career", "创业", "职场"]):
                zh_terms.extend(["创业职场", "社媒短视频"])
            for zh in zh_terms[:]:
                en = pool_dict.get(zh)
                if en:
                    en_terms.append(en)
        return {"zh": zh_terms, "en": en_terms}

    @staticmethod
    def _openai_client():
        api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
        if not api_key:
            return None
        try:
            import openai
        except Exception:
            return None
        kwargs = {"api_key": api_key}
        base_url = str(os.environ.get("OPENAI_BASE_URL", "")).strip()
        if base_url:
            kwargs["base_url"] = base_url
        try:
            return openai.OpenAI(**kwargs)
        except Exception:
            return None

    def _call_openai_json(self, messages: List[Dict[str, Any]], max_tokens: int = 1200, temperature: float = 0.15) -> Dict[str, Any]:
        client = self._openai_client()
        if client is None:
            return {}
        model = (
            str(os.environ.get("OPENAI_MODEL", "")).strip()
            or str(os.environ.get("OPENAI_VISION_MODEL", "")).strip()
            or "gpt-4o-mini"
        )
        try:
            rsp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = (rsp.choices[0].message.content or "").strip()
            return self._safe_json_object_from_text(content)
        except Exception:
            return {}

    def _call_openai_text(self, messages: List[Dict[str, Any]], max_tokens: int = 1200, temperature: float = 0.15) -> str:
        client = self._openai_client()
        if client is None:
            return ""
        model = (
            str(os.environ.get("OPENAI_MODEL", "")).strip()
            or str(os.environ.get("OPENAI_VISION_MODEL", "")).strip()
            or "gpt-4o-mini"
        )
        try:
            rsp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return str(rsp.choices[0].message.content or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _has_openai_sdk() -> bool:
        try:
            import openai  # noqa: F401
            return True
        except Exception:
            return False

    def _embedding_runtime_status(self) -> Dict[str, Any]:
        has_key = bool(str(os.environ.get("OPENAI_API_KEY", "")).strip())
        has_sdk = self._has_openai_sdk()
        has_numpy = np is not None
        if not has_key:
            return {
                "enabled": False,
                "reason": "missing_api_key",
                "message": "未配置 OpenAI API Key",
            }
        if not has_sdk:
            return {
                "enabled": False,
                "reason": "missing_openai_sdk",
                "message": "未安装 openai SDK",
            }
        if not has_numpy:
            return {
                "enabled": False,
                "reason": "missing_numpy",
                "message": "未安装 numpy",
            }
        return {
            "enabled": True,
            "reason": "ready",
            "message": "向量能力已启用",
        }

    @staticmethod
    def _embedding_model() -> str:
        return (
            str(os.environ.get("OPENAI_EMBEDDING_MODEL", "")).strip()
            or str(os.environ.get("OPENAI_EMBED_MODEL", "")).strip()
            or DEFAULT_EMBEDDING_MODEL
        )

    @staticmethod
    def _embedding_content_hash(content: str) -> str:
        return hashlib.sha256((content or "").strip().encode("utf-8")).hexdigest()

    def _build_embedding_source(
        self,
        filename: Optional[str],
        semantic_text: Optional[str],
        keywords_json: Any,
        semantic_json: Any,
    ) -> str:
        parts: List[str] = []
        if filename:
            parts.append(str(filename).strip())
        if semantic_text:
            parts.append(str(semantic_text).strip())

        keywords = self._safe_json_loads(keywords_json, [])
        if isinstance(keywords, list) and keywords:
            parts.extend([str(x).strip() for x in keywords if str(x).strip()])

        semantic = semantic_json
        if isinstance(semantic_json, str):
            semantic = self._safe_json_loads(semantic_json, {})
        if isinstance(semantic, dict):
            layers = semantic.get("index_layers", {}) if isinstance(semantic.get("index_layers"), dict) else {}
            core = layers.get("core_search_tags", {}) if isinstance(layers, dict) else {}
            secondary = layers.get("secondary_tags", {}) if isinstance(layers, dict) else {}
            for bucket in (core, secondary):
                if isinstance(bucket, dict):
                    for lang in ("zh", "en"):
                        vals = bucket.get(lang, [])
                        if isinstance(vals, list):
                            parts.extend([str(x).strip() for x in vals if str(x).strip()])

            for key in ("scene_description", "mood", "setting", "time_of_day", "activity", "visual_style"):
                val = semantic.get(key)
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
                elif isinstance(val, list):
                    parts.extend([str(x).strip() for x in val if str(x).strip()])

        compact = " | ".join([p for p in parts if p])
        if len(compact) > 6000:
            compact = compact[:6000]
        return compact

    def _call_openai_embedding(self, text: str) -> List[float]:
        query = str(text or "").strip()
        if not query:
            return []
        client = self._openai_client()
        if client is None:
            return []
        try:
            rsp = client.embeddings.create(
                model=self._embedding_model(),
                input=query,
            )
            data = getattr(rsp, "data", []) or []
            if not data:
                return []
            vec = getattr(data[0], "embedding", None)
            if not isinstance(vec, list):
                return []
            return [float(x) for x in vec]
        except Exception:
            return []

    def _get_query_embedding(self, query: str) -> List[float]:
        q = str(query or "").strip().lower()
        if not q:
            return []
        now_ts = time.time()
        cached = self._query_embedding_cache.get(q)
        if cached and (now_ts - float(cached.get("ts", 0.0))) < 3600:
            vec = cached.get("vec")
            if isinstance(vec, list) and vec:
                return vec

        vec = self._call_openai_embedding(q)
        if vec:
            self._query_embedding_cache[q] = {"ts": now_ts, "vec": vec}
            if len(self._query_embedding_cache) > 128:
                # 简单淘汰最旧项
                oldest = sorted(
                    self._query_embedding_cache.items(),
                    key=lambda kv: float(kv[1].get("ts", 0.0))
                )[:32]
                for k, _ in oldest:
                    self._query_embedding_cache.pop(k, None)
        return vec

    def _invalidate_vector_cache(self):
        self._vector_cache = {
            "model": "",
            "updated_at": "",
            "uids": [],
            "matrix": None,
        }

    def _refresh_vector_cache(self, conn: sqlite3.Connection, model: str):
        if np is None:
            return

        meta = conn.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(MAX(updated_at), '') AS max_updated
            FROM asset_embeddings
            WHERE model = ? AND embedding_version = ?
            """,
            (model, EMBEDDING_SCHEMA_VERSION),
        ).fetchone()
        cnt = int(meta["cnt"] or 0)
        max_updated = str(meta["max_updated"] or "")
        cached = self._vector_cache
        if (
            cached.get("model") == model
            and cached.get("updated_at") == max_updated
            and len(cached.get("uids", [])) == cnt
            and cached.get("matrix") is not None
        ):
            return

        rows = conn.execute(
            """
            SELECT uid, embedding_json
            FROM asset_embeddings
            WHERE model = ? AND embedding_version = ?
            """,
            (model, EMBEDDING_SCHEMA_VERSION),
        ).fetchall()

        uids: List[str] = []
        vectors: List[List[float]] = []
        dim = None
        for row in rows:
            vec = self._safe_json_loads(row["embedding_json"], [])
            if not isinstance(vec, list) or not vec:
                continue
            try:
                arr = [float(x) for x in vec]
            except Exception:
                continue
            if dim is None:
                dim = len(arr)
            if len(arr) != dim:
                continue
            uids.append(str(row["uid"]))
            vectors.append(arr)

        if not vectors:
            self._vector_cache = {
                "model": model,
                "updated_at": max_updated,
                "uids": [],
                "matrix": None,
            }
            return

        matrix = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.maximum(norms, 1e-8)
        self._vector_cache = {
            "model": model,
            "updated_at": max_updated,
            "uids": uids,
            "matrix": matrix,
        }

    def _vector_search(self, conn: sqlite3.Connection, query: str, top_k: int = 1200) -> Dict[str, float]:
        if np is None:
            return {}
        qvec = self._get_query_embedding(query)
        if not qvec:
            return {}
        model = self._embedding_model()
        self._refresh_vector_cache(conn, model)
        matrix = self._vector_cache.get("matrix")
        uids = self._vector_cache.get("uids", [])
        if matrix is None or not uids:
            return {}

        q = np.array([float(x) for x in qvec], dtype=np.float32)
        if matrix.shape[1] != q.shape[0]:
            return {}
        q = q / max(float(np.linalg.norm(q)), 1e-8)
        sims = matrix @ q
        count = int(sims.shape[0])
        if count <= 0:
            return {}

        k = min(max(1, int(top_k)), count)
        if k >= count:
            top_idx = np.arange(count)
        else:
            top_idx = np.argpartition(-sims, k - 1)[:k]
        sorted_idx = top_idx[np.argsort(sims[top_idx])[::-1]]
        out: Dict[str, float] = {}
        for idx in sorted_idx:
            score = float(sims[idx])
            if score < 0.08:
                continue
            out[uids[int(idx)]] = score
        return out

    def _upsert_embedding_for_asset(
        self,
        conn: sqlite3.Connection,
        uid: str,
        filename: Optional[str],
        semantic_text: Optional[str],
        keywords_json: Any,
        semantic_json: Any,
    ) -> bool:
        source = self._build_embedding_source(
            filename=filename,
            semantic_text=semantic_text,
            keywords_json=keywords_json,
            semantic_json=semantic_json,
        )
        if not source:
            return False
        content_hash = self._embedding_content_hash(source)
        model = self._embedding_model()
        existing = conn.execute(
            """
            SELECT content_hash, model, embedding_version
            FROM asset_embeddings
            WHERE uid = ?
            """,
            (uid,),
        ).fetchone()
        if (
            existing
            and str(existing["content_hash"] or "") == content_hash
            and str(existing["model"] or "") == model
            and str(existing["embedding_version"] or "") == EMBEDDING_SCHEMA_VERSION
        ):
            return False

        vec = self._call_openai_embedding(source)
        if not vec:
            return False

        conn.execute(
            """
            INSERT INTO asset_embeddings (
                uid, model, embedding_json, embedding_dim,
                content_hash, embedding_version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                model=excluded.model,
                embedding_json=excluded.embedding_json,
                embedding_dim=excluded.embedding_dim,
                content_hash=excluded.content_hash,
                embedding_version=excluded.embedding_version,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                model,
                json.dumps(vec, ensure_ascii=False),
                len(vec),
                content_hash,
                EMBEDDING_SCHEMA_VERSION,
                self._now(),
            ),
        )
        self._invalidate_vector_cache()
        return True

    def _refresh_embeddings_incremental(self, conn: sqlite3.Connection, max_items: int = 12) -> int:
        _re_t0 = time.perf_counter()
        if max_items <= 0:
            return 0
        client = self._openai_client()
        if client is None:
            return 0
        rows = conn.execute(
            """
            SELECT a.uid, a.filename, a.semantic_text, a.keywords_json, a.semantic_json,
                   e.content_hash, e.model, e.embedding_version
            FROM assets a
            LEFT JOIN asset_embeddings e ON e.uid = a.uid
            ORDER BY a.updated_at DESC
            LIMIT 600
            """
        ).fetchall()
        done = 0
        model = self._embedding_model()
        for row in rows:
            source = self._build_embedding_source(
                filename=row["filename"],
                semantic_text=row["semantic_text"],
                keywords_json=row["keywords_json"],
                semantic_json=row["semantic_json"],
            )
            if not source:
                continue
            expected_hash = self._embedding_content_hash(source)
            same = (
                str(row["content_hash"] or "") == expected_hash
                and str(row["model"] or "") == model
                and str(row["embedding_version"] or "") == EMBEDDING_SCHEMA_VERSION
            )
            if same:
                continue
            if self._upsert_embedding_for_asset(
                conn=conn,
                uid=str(row["uid"]),
                filename=row["filename"],
                semantic_text=row["semantic_text"],
                keywords_json=row["keywords_json"],
                semantic_json=row["semantic_json"],
            ):
                done += 1
                if done >= max_items:
                    break
        _re_elapsed = (time.perf_counter() - _re_t0) * 1000
        _gml_logger.info("[perf] refresh_embeddings: %.1fms refreshed=%d", _re_elapsed, done)
        try:
            from modules.app_api.services.perf_log import record as _perf_rec
            _perf_rec("refresh_embeddings", _re_elapsed, {"refreshed": done})
        except Exception:
            pass
        return done

    def _heuristic_structured_tags(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        schema = self._empty_structured_tag_schema()
        mapping = self._bilingual_term_map()

        def _push(cat: str, value: Any):
            text = str(value or "").strip()
            if not text:
                return
            lowered = text.lower()
            if self._contains_cjk(text):
                schema["tags"][cat]["zh"].append(text)
                if lowered in mapping:
                    schema["tags"][cat]["en"].append(mapping[lowered])
            else:
                schema["tags"][cat]["en"].append(lowered)
                if lowered in mapping:
                    schema["tags"][cat]["zh"].append(mapping[lowered])

        for item in evidence.get("objects", []) or []:
            _push("objects", item)
        for item in [evidence.get("activity"), evidence.get("camera_movement"), evidence.get("narrative_role")]:
            _push("actions", item)
        for item in [evidence.get("setting"), evidence.get("time_of_day"), evidence.get("weather"), evidence.get("scene_description")]:
            _push("scene", item)
        for item in [evidence.get("mood"), evidence.get("emotion_intensity")]:
            for part in self._split_terms(item):
                _push("mood", part)
        for item in [evidence.get("visual_style"), evidence.get("shot_type"), evidence.get("perspective"), evidence.get("color_tone")]:
            _push("style", item)
        for item in evidence.get("use_cases", []) or []:
            _push("use_cases", item)

        # 概念层：用 seed 做补全，避免只停留在物体层
        seed_concepts = self._seed_expand_terms("concepts", evidence.get("evidence_text", ""))
        for zh in seed_concepts["zh"]:
            _push("concepts", zh)
        for en in seed_concepts["en"]:
            _push("concepts", en)

        seed_use_cases = self._seed_expand_terms("use_cases", evidence.get("evidence_text", ""))
        for zh in seed_use_cases["zh"]:
            _push("use_cases", zh)
        for en in seed_use_cases["en"]:
            _push("use_cases", en)

        for cat in TAG_CATEGORIES:
            zh_terms = self._normalize_terms(schema["tags"][cat]["zh"], lang="zh")
            en_terms = self._normalize_terms(schema["tags"][cat]["en"], lang="en")
            if not zh_terms and en_terms:
                zh_terms = [mapping.get(t.lower(), t) for t in en_terms[:10]]
                zh_terms = self._normalize_terms(zh_terms, lang="zh")
            if not en_terms and zh_terms:
                en_terms = [mapping.get(t.lower(), t) for t in zh_terms[:10]]
                en_terms = self._normalize_terms(en_terms, lang="en")
            conf = 0.62
            if cat in {"objects", "scene"} and (zh_terms or en_terms):
                conf = 0.72
            if cat in {"concepts", "use_cases"} and len(zh_terms) + len(en_terms) >= 6:
                conf = 0.68
            schema["tags"][cat] = {
                "zh": zh_terms[:18],
                "en": en_terms[:18],
                "confidence": conf,
            }

        return schema

    def _normalize_structured_tags(self, raw: Dict[str, Any], evidence_text: str) -> Dict[str, Any]:
        normalized = self._empty_structured_tag_schema()
        mapping = self._bilingual_term_map()
        source_tags = raw.get("tags", raw) if isinstance(raw, dict) else {}
        if not isinstance(source_tags, dict):
            source_tags = {}

        for cat in TAG_CATEGORIES:
            node = source_tags.get(cat, {})
            if isinstance(node, list):
                node = {"en": node}
            if not isinstance(node, dict):
                node = {}
            zh_terms = self._split_terms(node.get("zh"))
            en_terms = self._split_terms(node.get("en"))
            seed_terms = self._seed_expand_terms(cat, evidence_text)
            zh_terms.extend(seed_terms["zh"])
            en_terms.extend(seed_terms["en"])

            zh_terms = self._normalize_terms(zh_terms, lang="zh")
            en_terms = self._normalize_terms(en_terms, lang="en")

            if not zh_terms and en_terms:
                zh_terms = self._normalize_terms([mapping.get(x.lower(), x) for x in en_terms], lang="zh")
            if not en_terms and zh_terms:
                en_terms = self._normalize_terms([mapping.get(x.lower(), x) for x in zh_terms], lang="en")

            min_target = 8 if cat in {"concepts", "use_cases"} else 4
            if len(zh_terms) < min_target or len(en_terms) < min_target:
                seed_fill = self._seed_expand_terms(cat, evidence_text)
                zh_terms = self._normalize_terms(zh_terms + seed_fill["zh"], lang="zh")
                en_terms = self._normalize_terms(en_terms + seed_fill["en"], lang="en")

            normalized["tags"][cat] = {
                "zh": zh_terms[:18],
                "en": en_terms[:18],
                "confidence": self._clamp_confidence(node.get("confidence"), default=0.6),
            }

        objects_count = len(normalized["tags"]["objects"]["zh"]) + len(normalized["tags"]["objects"]["en"])
        scene_count = len(normalized["tags"]["scene"]["zh"]) + len(normalized["tags"]["scene"]["en"])
        concept_count = len(normalized["tags"]["concepts"]["zh"]) + len(normalized["tags"]["concepts"]["en"])
        use_case_count = len(normalized["tags"]["use_cases"]["zh"]) + len(normalized["tags"]["use_cases"]["en"])
        total_terms = 0
        for cat in TAG_CATEGORIES:
            total_terms += len(normalized["tags"][cat]["zh"]) + len(normalized["tags"][cat]["en"])
        normalized["quality_checks"] = {
            "generic_terms_removed": True,
            "duplicate_terms_removed": True,
            "covers_literal_and_abstract": bool(objects_count + scene_count > 0 and concept_count + use_case_count > 0),
            "search_ready": total_terms >= 20,
        }
        return normalized

    def _flatten_structured_tag_terms(self, schema: Dict[str, Any]) -> List[str]:
        tags = schema.get("tags", {}) if isinstance(schema, dict) else {}
        out: List[str] = []
        for cat in TAG_CATEGORIES:
            node = tags.get(cat, {})
            if not isinstance(node, dict):
                continue
            zh_list = node.get("zh", [])
            en_list = node.get("en", [])
            for item in zh_list if isinstance(zh_list, list) else []:
                text = str(item or "").strip()
                if text:
                    out.append(text)
                    out.append(f"{cat}:{text}")
            for item in en_list if isinstance(en_list, list) else []:
                text = str(item or "").strip().lower()
                if text:
                    out.append(text)
                    out.append(f"{cat}:{text}")
        return self._dedupe_list(out)

    @staticmethod
    def _build_tag_schema_json() -> str:
        """Dynamically build the JSON schema string from TAG_TAXONOMY (25 categories)."""
        cats = {}
        for cat in TAG_TAXONOMY:
            cats[cat] = {"zh": [], "en": [], "confidence": 0.0}
        schema = {
            "tags": cats,
            "quality_checks": {
                "generic_terms_removed": True,
                "duplicate_terms_removed": True,
                "covers_literal_and_abstract": True,
                "search_ready": True,
            },
        }
        return json.dumps(schema, ensure_ascii=False)

    def _llm_structured_tags(self, path: Path, evidence: Dict[str, Any], draft_schema: Dict[str, Any]) -> Dict[str, Any]:
        if not self._llm_tagging_enabled():
            return {}

        keyframes = self._extract_keyframe_data_urls(path)

        # Build category list string for prompt
        cat_list = ", ".join(f"{c}({TAG_TAXONOMY[c]['zh']})" for c in TAG_TAXONOMY)
        schema_json = self._build_tag_schema_json()

        system_prompt = (
            "You are a professional stock-media semantic tagging editor.\n"
            "Goal: produce search-optimized tags for a media asset management system.\n"
            "Do NOT describe the media. Produce tags that maximize future retrievability.\n"
            "Output JSON only and keep tags concise, lowercase, search-friendly.\n"
            f"Tag categories (25 total): {cat_list}\n"
            "Internally expand semantic dimensions: marketing themes, storytelling arcs, industry use, "
            "emotions, social context, season/time/weather, camera language, audio mood, "
            "materials/textures, architecture, food, animals, vehicles, clothing, body language, "
            "spatial relations, color palette, composition, nature, narrative technique.\n"
            "Fill relevant categories only. Skip categories with no evidence.\n"
            f"Return schema: {schema_json}"
        )

        user_text = (
            "Structured evidence:\n"
            f"{json.dumps(evidence, ensure_ascii=False)}\n\n"
            "Draft tags:\n"
            f"{json.dumps(draft_schema, ensure_ascii=False)}\n\n"
            "Improve tags:\n"
            "- remove weak/generic terms\n"
            "- add high-value commercial concepts\n"
            "- normalize vocabulary\n"
            "- keep category diversity across all 25 categories\n"
            "- do not invent unsupported specifics\n"
            "- if Chinese evidence exists, provide both zh and en arrays"
        )
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
        for url in keyframes[:3]:
            user_content.append({"type": "image_url", "image_url": {"url": url, "detail": "low"}})

        primary = self._call_openai_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2500,
            temperature=0.12,
        )
        if not primary:
            return {}

        refine_prompt = (
            "You are given draft tags across 25 categories. Improve them:\n"
            "- remove weak, generic, overly broad tags\n"
            "- add missing high-value commercial concepts\n"
            "- normalize to consistent vocabulary\n"
            f"- ensure category diversity across: {cat_list}\n"
            "- keep each list compact and useful\n"
            "- do not invent specifics not supported by evidence\n"
            "Return JSON in the same schema, replacing the draft."
        )
        refined = self._call_openai_json(
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {
                    "role": "user",
                    "content": (
                        refine_prompt
                        + "\nEvidence:\n"
                        + json.dumps(evidence, ensure_ascii=False)
                        + "\nDraft:\n"
                        + json.dumps(primary, ensure_ascii=False)
                    ),
                },
            ],
            max_tokens=2000,
            temperature=0.08,
        )
        result = refined if refined else primary
        # Inject model name for _meta tracking
        if result and isinstance(result, dict):
            model_name = (
                str(os.environ.get("OPENAI_MODEL", "")).strip()
                or str(os.environ.get("OPENAI_VISION_MODEL", "")).strip()
                or "gpt-4o-mini"
            )
            result["_model"] = model_name
        return result

    @staticmethod
    def _canonical_tag_catalog() -> Dict[str, Dict[str, str]]:
        return {
            # landmark (10)
            "church": {"zh": "教堂", "en": "church", "class": "landmark"},
            "temple": {"zh": "寺庙", "en": "temple", "class": "landmark"},
            "mosque": {"zh": "清真寺", "en": "mosque", "class": "landmark"},
            "bridge": {"zh": "桥梁", "en": "bridge", "class": "landmark"},
            "tower": {"zh": "塔", "en": "tower", "class": "landmark"},
            "castle": {"zh": "城堡", "en": "castle", "class": "landmark"},
            "statue": {"zh": "雕像", "en": "statue", "class": "landmark"},
            "mountain": {"zh": "山地", "en": "mountain", "class": "landmark"},
            "beach": {"zh": "海滩", "en": "beach", "class": "landmark"},
            "forest": {"zh": "森林", "en": "forest", "class": "landmark"},
            # place (10)
            "street": {"zh": "街道", "en": "street", "class": "place"},
            "downtown": {"zh": "市中心", "en": "downtown", "class": "place"},
            "old town": {"zh": "老城区", "en": "old town", "class": "place"},
            "skyline": {"zh": "天际线", "en": "skyline", "class": "place"},
            "plaza": {"zh": "广场", "en": "plaza", "class": "place"},
            "alley": {"zh": "小巷", "en": "alley", "class": "place"},
            "city": {"zh": "城市", "en": "city", "class": "place"},
            "cafe": {"zh": "咖啡馆", "en": "cafe", "class": "place"},
            "park": {"zh": "公园", "en": "park", "class": "place"},
            "rooftop": {"zh": "屋顶", "en": "rooftop", "class": "place"},
            # people (2)
            "person": {"zh": "人物", "en": "person", "class": "people"},
            "people": {"zh": "人群", "en": "people", "class": "people"},
            # object (12)
            "car": {"zh": "汽车", "en": "car", "class": "object"},
            "road": {"zh": "道路", "en": "road", "class": "object"},
            "building": {"zh": "建筑", "en": "building", "class": "object"},
            "tree": {"zh": "树木", "en": "tree", "class": "object"},
            "water": {"zh": "水域", "en": "water", "class": "object"},
            "boat": {"zh": "船", "en": "boat", "class": "object"},
            "food": {"zh": "食物", "en": "food", "class": "object"},
            "snow": {"zh": "雪景", "en": "snow", "class": "object"},
            "flower": {"zh": "花朵", "en": "flower", "class": "object"},
            "window": {"zh": "窗户", "en": "window", "class": "object"},
            "door": {"zh": "门", "en": "door", "class": "object"},
            "light": {"zh": "灯光", "en": "light", "class": "object"},
            # time (9)
            "daytime": {"zh": "白天", "en": "daytime", "class": "time"},
            "afternoon": {"zh": "下午", "en": "afternoon", "class": "time"},
            "night": {"zh": "夜晚", "en": "night", "class": "time"},
            "sunrise": {"zh": "日出", "en": "sunrise", "class": "time"},
            "sunset": {"zh": "日落", "en": "sunset", "class": "time"},
            "spring": {"zh": "春季", "en": "spring", "class": "time"},
            "summer": {"zh": "夏季", "en": "summer", "class": "time"},
            "autumn": {"zh": "秋季", "en": "autumn", "class": "time"},
            "winter": {"zh": "冬季", "en": "winter", "class": "time"},
            # action (15)
            "walking": {"zh": "行走", "en": "walking", "class": "action"},
            "running": {"zh": "奔跑", "en": "running", "class": "action"},
            "driving": {"zh": "驾驶", "en": "driving", "class": "action"},
            "talking": {"zh": "讲述", "en": "talking", "class": "action"},
            "hiking": {"zh": "徒步", "en": "hiking", "class": "action"},
            "skiing": {"zh": "滑雪", "en": "skiing", "class": "action"},
            "surfing": {"zh": "冲浪", "en": "surfing", "class": "action"},
            "cooking": {"zh": "烹饪", "en": "cooking", "class": "action"},
            "reading": {"zh": "阅读", "en": "reading", "class": "action"},
            "dancing": {"zh": "舞蹈", "en": "dancing", "class": "action"},
            "swimming": {"zh": "游泳", "en": "swimming", "class": "action"},
            "cycling": {"zh": "骑行", "en": "cycling", "class": "action"},
            "meditating": {"zh": "冥想", "en": "meditating", "class": "action"},
            "climbing": {"zh": "攀登", "en": "climbing", "class": "action"},
            "jumping": {"zh": "跳跃", "en": "jumping", "class": "action"},
            # abstract / concept (14)
            "lifestyle": {"zh": "生活方式", "en": "lifestyle", "class": "abstract"},
            "travel vlog": {"zh": "旅行vlog", "en": "travel vlog", "class": "abstract"},
            "city promo": {"zh": "城市宣传", "en": "city promo", "class": "abstract"},
            "opening hook": {"zh": "开场钩子", "en": "opening hook", "class": "abstract"},
            "use case": {"zh": "使用场景", "en": "use case", "class": "abstract"},
            "exploration": {"zh": "探索", "en": "exploration", "class": "abstract"},
            "healing": {"zh": "治愈", "en": "healing", "class": "abstract"},
            "relaxed vibe": {"zh": "松弛感", "en": "relaxed vibe", "class": "abstract"},
            "cinematic": {"zh": "电影感", "en": "cinematic", "class": "abstract"},
            "documentary": {"zh": "纪录感", "en": "documentary", "class": "abstract"},
            "nostalgia": {"zh": "怀旧", "en": "nostalgia", "class": "abstract"},
            "sustainability": {"zh": "可持续", "en": "sustainability", "class": "abstract"},
            "creativity": {"zh": "创造力", "en": "creativity", "class": "abstract"},
            "balance": {"zh": "平衡", "en": "balance", "class": "abstract"},
            # material (12)
            "wood": {"zh": "木质", "en": "wood", "class": "material"},
            "metal": {"zh": "金属", "en": "metal", "class": "material"},
            "glass": {"zh": "玻璃", "en": "glass", "class": "material"},
            "stone": {"zh": "石材", "en": "stone", "class": "material"},
            "concrete": {"zh": "混凝土", "en": "concrete", "class": "material"},
            "leather": {"zh": "皮革", "en": "leather", "class": "material"},
            "silk": {"zh": "丝绸", "en": "silk", "class": "material"},
            "ceramic": {"zh": "陶瓷", "en": "ceramic", "class": "material"},
            "bamboo": {"zh": "竹子", "en": "bamboo", "class": "material"},
            "marble": {"zh": "大理石", "en": "marble", "class": "material"},
            "brick": {"zh": "砖块", "en": "brick", "class": "material"},
            "rust": {"zh": "铁锈", "en": "rust", "class": "material"},
            # architecture (10)
            "gothic": {"zh": "哥特式", "en": "gothic", "class": "architecture"},
            "baroque": {"zh": "巴洛克", "en": "baroque", "class": "architecture"},
            "modernist": {"zh": "现代主义", "en": "modernist", "class": "architecture"},
            "art deco": {"zh": "装饰艺术", "en": "art deco", "class": "architecture"},
            "industrial": {"zh": "工业风", "en": "industrial", "class": "architecture"},
            "bauhaus": {"zh": "包豪斯", "en": "bauhaus", "class": "architecture"},
            "neoclassical": {"zh": "新古典", "en": "neoclassical", "class": "architecture"},
            "postmodern": {"zh": "后现代", "en": "postmodern", "class": "architecture"},
            "mediterranean": {"zh": "地中海", "en": "mediterranean", "class": "architecture"},
            "chinese traditional": {"zh": "中式传统", "en": "chinese traditional", "class": "architecture"},
            # food (12)
            "chinese food": {"zh": "中餐", "en": "chinese food", "class": "food"},
            "japanese food": {"zh": "日料", "en": "japanese food", "class": "food"},
            "dessert": {"zh": "甜点", "en": "dessert", "class": "food"},
            "coffee": {"zh": "咖啡", "en": "coffee", "class": "food"},
            "tea": {"zh": "茶", "en": "tea", "class": "food"},
            "cocktail": {"zh": "鸡尾酒", "en": "cocktail", "class": "food"},
            "barbecue": {"zh": "烧烤", "en": "barbecue", "class": "food"},
            "bread": {"zh": "面包", "en": "bread", "class": "food"},
            "sushi": {"zh": "寿司", "en": "sushi", "class": "food"},
            "pizza": {"zh": "披萨", "en": "pizza", "class": "food"},
            "hotpot": {"zh": "火锅", "en": "hotpot", "class": "food"},
            "ice cream": {"zh": "冰淇淋", "en": "ice cream", "class": "food"},
            # animal (10)
            "cat": {"zh": "猫", "en": "cat", "class": "animal"},
            "dog": {"zh": "狗", "en": "dog", "class": "animal"},
            "bird": {"zh": "鸟类", "en": "bird", "class": "animal"},
            "fish": {"zh": "鱼类", "en": "fish", "class": "animal"},
            "horse": {"zh": "马", "en": "horse", "class": "animal"},
            "butterfly": {"zh": "蝴蝶", "en": "butterfly", "class": "animal"},
            "dolphin": {"zh": "海豚", "en": "dolphin", "class": "animal"},
            "deer": {"zh": "鹿", "en": "deer", "class": "animal"},
            "rabbit": {"zh": "兔子", "en": "rabbit", "class": "animal"},
            "seagull": {"zh": "海鸥", "en": "seagull", "class": "animal"},
            # vehicle (8)
            "bicycle": {"zh": "自行车", "en": "bicycle", "class": "vehicle"},
            "motorcycle": {"zh": "摩托车", "en": "motorcycle", "class": "vehicle"},
            "train": {"zh": "火车", "en": "train", "class": "vehicle"},
            "airplane": {"zh": "飞机", "en": "airplane", "class": "vehicle"},
            "tram": {"zh": "电车", "en": "tram", "class": "vehicle"},
            "cable car": {"zh": "缆车", "en": "cable car", "class": "vehicle"},
            "sailboat": {"zh": "帆船", "en": "sailboat", "class": "vehicle"},
            "skateboard": {"zh": "滑板", "en": "skateboard", "class": "vehicle"},
            # clothing (8)
            "suit": {"zh": "西装", "en": "suit", "class": "clothing"},
            "dress": {"zh": "连衣裙", "en": "dress", "class": "clothing"},
            "sportswear": {"zh": "运动装", "en": "sportswear", "class": "clothing"},
            "hanfu": {"zh": "汉服", "en": "hanfu", "class": "clothing"},
            "kimono": {"zh": "和服", "en": "kimono", "class": "clothing"},
            "denim": {"zh": "牛仔", "en": "denim", "class": "clothing"},
            "hat": {"zh": "帽子", "en": "hat", "class": "clothing"},
            "scarf": {"zh": "围巾", "en": "scarf", "class": "clothing"},
            # body_language (8)
            "smiling": {"zh": "微笑", "en": "smiling", "class": "body_language"},
            "thinking": {"zh": "思考", "en": "thinking", "class": "body_language"},
            "pointing": {"zh": "指向", "en": "pointing", "class": "body_language"},
            "clapping": {"zh": "鼓掌", "en": "clapping", "class": "body_language"},
            "waving": {"zh": "挥手", "en": "waving", "class": "body_language"},
            "looking up": {"zh": "仰望", "en": "looking up", "class": "body_language"},
            "head down": {"zh": "低头", "en": "head down", "class": "body_language"},
            "arms crossed": {"zh": "双臂交叉", "en": "arms crossed", "class": "body_language"},
            # nature (10)
            "lake": {"zh": "湖泊", "en": "lake", "class": "nature"},
            "river": {"zh": "河流", "en": "river", "class": "nature"},
            "waterfall": {"zh": "瀑布", "en": "waterfall", "class": "nature"},
            "desert": {"zh": "沙漠", "en": "desert", "class": "nature"},
            "grassland": {"zh": "草原", "en": "grassland", "class": "nature"},
            "glacier": {"zh": "冰川", "en": "glacier", "class": "nature"},
            "canyon": {"zh": "峡谷", "en": "canyon", "class": "nature"},
            "volcano": {"zh": "火山", "en": "volcano", "class": "nature"},
            "wetland": {"zh": "湿地", "en": "wetland", "class": "nature"},
            "cave": {"zh": "洞穴", "en": "cave", "class": "nature"},
            # weather (8)
            "sunny": {"zh": "晴天", "en": "sunny", "class": "weather"},
            "cloudy": {"zh": "多云", "en": "cloudy", "class": "weather"},
            "rainy": {"zh": "雨天", "en": "rainy", "class": "weather"},
            "foggy": {"zh": "雾", "en": "foggy", "class": "weather"},
            "rainbow": {"zh": "彩虹", "en": "rainbow", "class": "weather"},
            "storm": {"zh": "暴风雨", "en": "storm", "class": "weather"},
            "starry": {"zh": "星空", "en": "starry", "class": "weather"},
            "aurora": {"zh": "极光", "en": "aurora", "class": "weather"},
            # cultural (8)
            "festival": {"zh": "节日", "en": "festival", "class": "cultural"},
            "tradition": {"zh": "传统", "en": "tradition", "class": "cultural"},
            "calligraphy": {"zh": "书法", "en": "calligraphy", "class": "cultural"},
            "craft": {"zh": "手工艺", "en": "craft", "class": "cultural"},
            "tea ceremony": {"zh": "茶道", "en": "tea ceremony", "class": "cultural"},
            "lantern": {"zh": "灯笼", "en": "lantern", "class": "cultural"},
            "dragon dance": {"zh": "舞龙", "en": "dragon dance", "class": "cultural"},
            "temple fair": {"zh": "庙会", "en": "temple fair", "class": "cultural"},
            # composition (6)
            "rule of thirds": {"zh": "三分法", "en": "rule of thirds", "class": "composition"},
            "centered": {"zh": "居中", "en": "centered", "class": "composition"},
            "diagonal": {"zh": "对角线", "en": "diagonal", "class": "composition"},
            "negative space": {"zh": "留白", "en": "negative space", "class": "composition"},
            "frame within frame": {"zh": "框中框", "en": "frame within frame", "class": "composition"},
            "leading line": {"zh": "引导线", "en": "leading line", "class": "composition"},
            # social (6)
            "solitude": {"zh": "独处", "en": "solitude", "class": "social"},
            "family": {"zh": "家庭", "en": "family", "class": "social"},
            "friends gathering": {"zh": "朋友聚会", "en": "friends gathering", "class": "social"},
            "team": {"zh": "团队", "en": "team", "class": "social"},
            "party": {"zh": "派对", "en": "party", "class": "social"},
            "ceremony": {"zh": "仪式", "en": "ceremony", "class": "social"},
            # industry (8)
            "technology": {"zh": "科技", "en": "technology", "class": "industry"},
            "healthcare": {"zh": "医疗", "en": "healthcare", "class": "industry"},
            "education": {"zh": "教育", "en": "education", "class": "industry"},
            "finance": {"zh": "金融", "en": "finance", "class": "industry"},
            "retail": {"zh": "零售", "en": "retail", "class": "industry"},
            "tourism": {"zh": "旅游", "en": "tourism", "class": "industry"},
            "sports": {"zh": "体育", "en": "sports", "class": "industry"},
            "entertainment": {"zh": "娱乐", "en": "entertainment", "class": "industry"},
            # narrative (6)
            "montage": {"zh": "蒙太奇", "en": "montage", "class": "narrative"},
            "flashback": {"zh": "倒叙", "en": "flashback", "class": "narrative"},
            "suspense": {"zh": "悬念", "en": "suspense", "class": "narrative"},
            "symbolism": {"zh": "象征", "en": "symbolism", "class": "narrative"},
            "metaphor": {"zh": "隐喻", "en": "metaphor", "class": "narrative"},
            "contrast": {"zh": "对比", "en": "contrast", "class": "narrative"},
        }

    @staticmethod
    def _canonical_alias_map() -> Dict[str, str]:
        catalog = GlobalMediaLibrary._canonical_tag_catalog()
        alias: Dict[str, str] = {}
        for key, meta in catalog.items():
            alias[key.lower()] = key
            alias[str(meta.get("en", "")).strip().lower()] = key
            alias[str(meta.get("zh", "")).strip().lower()] = key
        alias.update({
            "cathedral": "church",
            "chapel": "church",
            "basilica": "church",
            "大教堂": "church",
            "礼拜堂": "church",
            "圣堂": "church",
            "教会": "church",
            "古教堂": "church",
            "iron bridge": "bridge",
            "steel bridge": "bridge",
            "viaduct": "bridge",
            "overpass": "bridge",
            "铁桥": "bridge",
            "钢桥": "bridge",
            "大桥": "bridge",
            "桥": "bridge",
            "shrine": "temple",
            "monastery": "temple",
            "abbey": "temple",
            "修道院": "temple",
            "神社": "temple",
            "fortress": "castle",
            "古堡": "castle",
            "尖塔": "tower",
            "塔楼": "tower",
            "雕塑": "statue",
            "石像": "statue",
            "山": "mountain",
            "雪山": "mountain",
            "海边": "beach",
            "沙滩": "beach",
            "海岸": "beach",
            "树林": "forest",
            "林地": "forest",
            "city center": "downtown",
            "city centre": "downtown",
            "cbd": "downtown",
            "市中心": "downtown",
            "中心城区": "downtown",
            "historic center": "old town",
            "historic centre": "old town",
            "oldtown": "old town",
            "old town": "old town",
            "古城": "old town",
            "老城区": "old town",
            "老街区": "old town",
            "city skyline": "skyline",
            "天际线": "skyline",
            "高楼群": "skyline",
            "square": "plaza",
            "广场": "plaza",
            "lane": "alley",
            "小巷": "alley",
            "巷子": "alley",
            "street view": "street",
            "街道": "street",
            "街头": "street",
            "town": "city",
            "urban": "city",
            "城区": "city",
            "白天": "daytime",
            "day": "daytime",
            "日间": "daytime",
            "午后": "afternoon",
            "下午": "afternoon",
            "夜景": "night",
            "夜晚": "night",
            "晚上": "night",
            "日出": "sunrise",
            "清晨": "sunrise",
            "dawn": "sunrise",
            "日落": "sunset",
            "傍晚": "sunset",
            "黄昏": "sunset",
            "walk": "walking",
            "walks": "walking",
            "行走": "walking",
            "徒步": "hiking",
            "hike": "hiking",
            "drive": "driving",
            "驾驶": "driving",
            "talk": "talking",
            "speak": "talking",
            "讲解": "talking",
            "口播": "talking",
            "ski": "skiing",
            "滑雪": "skiing",
            "surf": "surfing",
            "冲浪": "surfing",
            "travel_vlog": "travel vlog",
            "travel vlog": "travel vlog",
            "旅行vlog": "travel vlog",
            "city_promo": "city promo",
            "city promo": "city promo",
            "opening hook": "opening hook",
            "hook": "opening hook",
            "开场钩子": "opening hook",
            "use_case": "use case",
            "use cases": "use case",
            "使用场景": "use case",
            "lifestyle": "lifestyle",
            "生活方式": "lifestyle",
        })
        return alias

    def _normalize_tag_to_key(self, term: str) -> Optional[str]:
        text = re.sub(r"\s+", " ", str(term or "").strip().lower().replace("_", " "))
        if not text:
            return None
        alias_map = self._canonical_alias_map()
        if text in alias_map:
            return alias_map[text]
        for alias, key in sorted(alias_map.items(), key=lambda x: len(x[0]), reverse=True):
            if len(alias) < 3:
                continue
            if re.search(r"^[a-z0-9\s\-]+$", alias):
                if re.search(rf"\b{re.escape(alias)}\b", text):
                    return key
            elif alias in text:
                return key
        return None

    def _entry_from_key(self, key: str) -> Optional[Dict[str, str]]:
        catalog = self._canonical_tag_catalog()
        meta = catalog.get(key)
        if not meta:
            return None
        return {
            "key": key,
            "zh": str(meta.get("zh", "")).strip(),
            "en": str(meta.get("en", "")).strip().lower(),
            "class": str(meta.get("class", "object")).strip(),
        }

    def _term_to_entry(self, term: str, fallback_class: str = "object") -> Optional[Dict[str, str]]:
        text = re.sub(r"\s+", " ", str(term or "").strip())
        if not text:
            return None
        lowered = text.lower()
        if lowered in GENERIC_TAG_TERMS:
            return None
        if any(
            marker in lowered
            for marker in (
                "unknown",
                "mixed environment",
                "stable framing",
                "soft natural light",
                "bright daylight",
                "low-light",
                "audio present",
            )
        ):
            return None
        if lowered in {
            "static", "handheld", "aerial", "drone", "outdoor", "indoor",
            "固定机位", "手持", "航拍", "室外", "室内",
        }:
            return None
        if ";" in text:
            return None
        canonical = self._normalize_tag_to_key(text)
        if canonical:
            return self._entry_from_key(canonical)

        # 仅保留短词/短语，避免把句子塞进检索标签。
        if len(text) > 24 or len(text.split()) > 3:
            return None
        if any(ch in text for ch in "\n\t[]{}<>"):
            return None

        bi_map = self._bilingual_term_map()
        zh = ""
        en = ""
        if self._contains_cjk(text):
            zh = text
            en = str(bi_map.get(lowered, "")).strip().lower()
        else:
            en = lowered
            zh = str(bi_map.get(lowered, "")).strip()
        if not zh and not en:
            return None
        key = f"custom:{en or zh.lower()}"
        return {"key": key, "zh": zh, "en": en, "class": fallback_class}

    def _landmark_gate(self, evidence: Dict[str, Any]) -> List[str]:
        text_parts = []
        for k in ("scene_description", "mood", "transcript", "evidence_text"):
            v = evidence.get(k)
            if v:
                text_parts.append(str(v))
        for frame in evidence.get("keyframes", []) or []:
            if isinstance(frame, dict):
                text_parts.append(str(frame.get("caption", "")))
        for item in evidence.get("ocr", []) or []:
            if isinstance(item, dict):
                text_parts.append(str(item.get("text", "")))
        for obj in evidence.get("objects", []) or []:
            text_parts.append(str(obj))
        source = " ".join(text_parts).lower()
        if not source:
            return []

        gate_aliases = {
            "church": ["church", "cathedral", "chapel", "basilica", "教堂", "大教堂", "礼拜堂"],
            "temple": ["temple", "shrine", "monastery", "abbey", "寺庙", "神社", "修道院"],
            "mosque": ["mosque", "清真寺"],
            "bridge": ["bridge", "viaduct", "overpass", "铁桥", "钢桥", "桥梁", "大桥", "桥"],
            "tower": ["tower", "尖塔", "塔楼", "钟楼", "塔"],
            "castle": ["castle", "fortress", "古堡", "城堡", "要塞"],
            "statue": ["statue", "sculpture", "雕像", "雕塑", "石像"],
            "mountain": ["mountain", "alpine", "mount", "高山", "山地", "山脉", "雪山"],
            "beach": ["beach", "coast", "shore", "海滩", "海边", "沙滩", "海岸"],
            "forest": ["forest", "woods", "树林", "森林", "林地"],
        }
        hits: List[str] = []
        for key, aliases in gate_aliases.items():
            if any(a in source for a in aliases):
                hits.append(key)
        hits = self._dedupe_list(hits)
        return hits[:3]

    def _infer_time_tag_keys(self, evidence: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        time_of_day = str(evidence.get("time_of_day", "") or "").strip().lower()
        season = str(evidence.get("season", "") or "").strip().lower()
        source = str(evidence.get("evidence_text", "") or "").lower()
        if time_of_day in {"sunset"} or any(x in source for x in ["sunset", "日落", "黄昏", "dusk"]):
            out.append("sunset")
        elif time_of_day in {"night"} or any(x in source for x in ["night", "夜景", "夜晚", "晚上"]):
            out.append("night")
        elif time_of_day in {"afternoon"} or any(x in source for x in ["afternoon", "午后", "下午"]):
            out.append("afternoon")
        elif time_of_day in {"morning"} or any(x in source for x in ["sunrise", "日出", "清晨", "dawn"]):
            out.append("sunrise")
        else:
            out.append("daytime")
        if season in {"spring", "summer", "autumn", "winter"}:
            out.append(season)
        return self._dedupe_list(out)

    def _city_specific_place_keys(self, evidence_text: str) -> List[str]:
        text = str(evidence_text or "").lower()
        hits: List[str] = []
        if any(k in text for k in ["skyline", "city skyline", "天际线", "高楼", "高楼群"]):
            hits.append("skyline")
        if any(k in text for k in ["old town", "historic", "古城", "老城区", "老街区"]):
            hits.append("old town")
        if any(k in text for k in ["plaza", "square", "广场"]):
            hits.append("plaza")
        if any(k in text for k in ["alley", "lane", "小巷", "巷子"]):
            hits.append("alley")
        if any(k in text for k in ["downtown", "city center", "cbd", "市中心", "中心城区"]):
            hits.append("downtown")

        has_city_signal = any(k in text for k in ["city", "urban", "street", "城市", "街头", "城区", "都市"])
        if not hits and has_city_signal:
            hits.append("street")
        return self._dedupe_list(hits)[:2]

    @staticmethod
    def _parse_section_terms(value: str) -> List[str]:
        return [x.strip() for x in re.split(r"[，,;；|/]+", str(value or "")) if x.strip()]

    def _parse_plain_text_index_layers(self, raw_text: str) -> Dict[str, Any]:
        parsed = {
            "core_search_tags": {"zh": [], "en": []},
            "secondary_tags": {"zh": [], "en": []},
            "tech_meta": {},
        }
        if not raw_text:
            return parsed
        section = ""
        for raw_line in str(raw_text).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            upper = line.upper()
            if upper == "[CORE]":
                section = "core"
                continue
            if upper == "[SECONDARY]":
                section = "secondary"
                continue
            if upper == "[TECH_META]":
                section = "tech"
                continue
            if section == "core" and line.lower().startswith("zh:"):
                parsed["core_search_tags"]["zh"] = self._parse_section_terms(line.split(":", 1)[1])
                continue
            if section == "core" and line.lower().startswith("en:"):
                parsed["core_search_tags"]["en"] = [x.lower() for x in self._parse_section_terms(line.split(":", 1)[1])]
                continue
            if section == "secondary" and line.lower().startswith("zh:"):
                parsed["secondary_tags"]["zh"] = self._parse_section_terms(line.split(":", 1)[1])
                continue
            if section == "secondary" and line.lower().startswith("en:"):
                parsed["secondary_tags"]["en"] = [x.lower() for x in self._parse_section_terms(line.split(":", 1)[1])]
                continue
            if section == "tech":
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                parsed["tech_meta"][k.strip().lower()] = v.strip()
        return parsed

    def _llm_refine_index_layers(
        self,
        evidence: Dict[str, Any],
        draft_layers: Dict[str, Any],
        landmark_gate: List[str],
    ) -> Dict[str, Any]:
        if not self._llm_tagging_enabled():
            return {}
        prompt = (
            "You are a video asset indexing assistant. Your output is used for keyword search.\n\n"
            "Generate tags in THREE LAYERS:\n"
            "A) core_search_tags (user-visible, highest priority for retrieval)\n"
            "B) secondary_tags (index-only, not shown by default)\n"
            "C) tech_meta (stored only, never shown; includes resolution/duration/orientation)\n\n"
            "Rules:\n"
            "- NO duplicates across tags.\n"
            "- Merge synonyms (e.g., church/cathedral = church; 教堂/大教堂 = 教堂).\n"
            "- core_search_tags must prioritize concrete visible entities:\n"
            "  landmark/place > people > objects > time > actions.\n"
            "- If a landmark category is visible (church, bridge, tower, castle, mosque, temple, mountain, beach, forest), it MUST appear in core_search_tags.\n"
            "- Avoid generic tags: video, footage, scene, content, hook, main shot, general, activity.\n"
            "- Provide both Chinese and English tags.\n"
            "- Output as plain text sections (not JSON).\n\n"
            "Output format exactly:\n\n"
            "[CORE]\n"
            "zh: ...\n"
            "en: ...\n\n"
            "[SECONDARY]\n"
            "zh: ...\n"
            "en: ...\n\n"
            "[TECH_META]\n"
            "orientation: portrait|landscape\n"
            "resolution: WxH\n"
            "duration_sec: number\n"
            "motion_level: low|moderate|high\n"
        )
        user_msg = (
            "landmark_gate(must inject to CORE if present): "
            + ", ".join(landmark_gate or [])
            + "\n\nEvidence:\n"
            + json.dumps(evidence, ensure_ascii=False)
            + "\n\nDraft layers:\n"
            + json.dumps(draft_layers, ensure_ascii=False)
            + "\n\nYou are given draft tags. Fix them:\n"
            "1) remove duplicates and generic terms\n"
            "2) enforce landmark/place/person/object/time/action order in [CORE]\n"
            "3) add missing concrete entities that improve search recall\n"
            "4) move abstract terms into [SECONDARY]\n"
            "5) ensure [TECH_META] has orientation + resolution, and no tech terms appear in [CORE]/[SECONDARY]\n"
            "Return only in the required plain text format."
        )
        output = self._call_openai_text(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=900,
            temperature=0.05,
        )
        if not output:
            return {}
        return self._parse_plain_text_index_layers(output)

    def _normalize_index_layers(
        self,
        raw_layers: Dict[str, Any],
        evidence: Dict[str, Any],
        forced_landmarks: List[str],
        tech_meta_default: Dict[str, Any],
    ) -> Dict[str, Any]:
        buckets = {
            "landmark": [],
            "place": [],
            "people": [],
            "object": [],
            "time": [],
            "action": [],
        }
        bucket_seen = {k: set() for k in buckets}
        secondary_entries: List[Dict[str, str]] = []
        secondary_seen = set()

        def _push_bucket(entry: Dict[str, str]):
            cls = entry.get("class", "object")
            key = entry.get("key", "")
            if cls not in buckets:
                cls = "object"
            if key in bucket_seen[cls]:
                return
            bucket_seen[cls].add(key)
            buckets[cls].append(entry)

        def _push_secondary(entry: Dict[str, str]):
            key = entry.get("key", "")
            if not key or key in secondary_seen:
                return
            secondary_seen.add(key)
            secondary_entries.append(entry)

        core_src = raw_layers.get("core_search_tags", {}) if isinstance(raw_layers, dict) else {}
        sec_src = raw_layers.get("secondary_tags", {}) if isinstance(raw_layers, dict) else {}
        core_terms = []
        if isinstance(core_src, dict):
            core_terms.extend(core_src.get("zh", []) if isinstance(core_src.get("zh"), list) else [])
            core_terms.extend(core_src.get("en", []) if isinstance(core_src.get("en"), list) else [])
        secondary_terms = []
        if isinstance(sec_src, dict):
            secondary_terms.extend(sec_src.get("zh", []) if isinstance(sec_src.get("zh"), list) else [])
            secondary_terms.extend(sec_src.get("en", []) if isinstance(sec_src.get("en"), list) else [])

        for term in core_terms:
            entry = self._term_to_entry(term, fallback_class="object")
            if not entry:
                continue
            if str(entry.get("key", "")).startswith("custom:"):
                _push_secondary(entry)
                continue
            if entry.get("class") == "abstract":
                _push_secondary(entry)
            else:
                _push_bucket(entry)
        for term in secondary_terms:
            entry = self._term_to_entry(term, fallback_class="abstract")
            if not entry:
                continue
            _push_secondary(entry)

        # 强制 landmark_gate 注入
        for key in forced_landmarks or []:
            entry = self._entry_from_key(key)
            if entry:
                _push_bucket(entry)

        # people: 如果检测到人物，则确保 person 在 core。
        people_presence = str(evidence.get("people_presence", "") or "").lower()
        if people_presence in {"present", "high_face_presence", "medium_face_presence"}:
            person_entry = self._entry_from_key("person")
            if person_entry:
                _push_bucket(person_entry)

        # 城市场景必须给具体可见类别，避免只留 city。
        place_keys = {x["key"] for x in buckets["place"]}
        if "city" in place_keys or not place_keys:
            specific = self._city_specific_place_keys(str(evidence.get("evidence_text", "")))
            for key in specific:
                e = self._entry_from_key(key)
                if e:
                    _push_bucket(e)
            if "city" in {x["key"] for x in buckets["place"]}:
                city_entries = [x for x in buckets["place"] if x["key"] == "city"]
                buckets["place"] = [x for x in buckets["place"] if x["key"] != "city"]
                for city_e in city_entries:
                    _push_secondary(city_e)

        # time 维度固定为 daytime/afternoon/night/sunrise/sunset + season(optional)
        for key in self._infer_time_tag_keys(evidence):
            e = self._entry_from_key(key)
            if e:
                _push_bucket(e)

        # 防止 tech 字段污染 core/secondary
        tech_words = {"portrait", "landscape", "resolution", "duration", "motion", "fps", "1080p", "4k"}
        for cls in list(buckets.keys()):
            cleaned = []
            for e in buckets[cls]:
                joined = f"{e.get('zh', '')} {e.get('en', '')}".lower()
                if any(w in joined for w in tech_words):
                    continue
                cleaned.append(e)
            buckets[cls] = cleaned
        cleaned_secondary = []
        for e in secondary_entries:
            joined = f"{e.get('zh', '')} {e.get('en', '')}".lower()
            if any(w in joined for w in tech_words):
                continue
            cleaned_secondary.append(e)
        secondary_entries = cleaned_secondary

        order = ["landmark", "place", "people", "object", "time", "action"]
        core_entries: List[Dict[str, str]] = []
        core_keys_seen = set()
        for cls in order:
            for e in buckets[cls]:
                key = e.get("key", "")
                if not key or key in core_keys_seen:
                    continue
                core_keys_seen.add(key)
                core_entries.append(e)

        # secondary 不允许与 core 重复
        sec_final: List[Dict[str, str]] = []
        sec_seen = set()
        for e in secondary_entries:
            key = e.get("key", "")
            if not key or key in core_keys_seen or key in sec_seen:
                continue
            sec_seen.add(key)
            sec_final.append(e)

        core_zh = self._normalize_terms([e.get("zh", "") for e in core_entries], lang="zh", max_items=22)
        core_en = self._normalize_terms([e.get("en", "") for e in core_entries], lang="en", max_items=22)
        sec_zh = self._normalize_terms([e.get("zh", "") for e in sec_final], lang="zh", max_items=28)
        sec_en = self._normalize_terms([e.get("en", "") for e in sec_final], lang="en", max_items=28)
        bi_map = self._bilingual_term_map()
        if not core_zh and core_en:
            core_zh = self._normalize_terms([bi_map.get(x.lower(), x) for x in core_en], lang="zh", max_items=22)
        if not core_en and core_zh:
            core_en = self._normalize_terms([bi_map.get(x.lower(), x) for x in core_zh], lang="en", max_items=22)
        if not sec_zh and sec_en:
            sec_zh = self._normalize_terms([bi_map.get(x.lower(), x) for x in sec_en], lang="zh", max_items=28)
        if not sec_en and sec_zh:
            sec_en = self._normalize_terms([bi_map.get(x.lower(), x) for x in sec_zh], lang="en", max_items=28)

        tm = dict(tech_meta_default or {})
        raw_tm = raw_layers.get("tech_meta", {}) if isinstance(raw_layers, dict) else {}
        if isinstance(raw_tm, dict):
            orientation = str(raw_tm.get("orientation", tm.get("orientation", ""))).strip().lower()
            tm["orientation"] = "portrait" if orientation == "portrait" else "landscape"
            resolution = str(raw_tm.get("resolution", tm.get("resolution", ""))).strip()
            tm["resolution"] = resolution if re.match(r"^\d{2,5}x\d{2,5}$", resolution) else str(tm.get("resolution", ""))
            try:
                tm["duration_sec"] = float(raw_tm.get("duration_sec", tm.get("duration_sec", 0)))
            except Exception:
                pass
            mv = str(raw_tm.get("motion_level", tm.get("motion_level", ""))).strip().lower()
            tm["motion_level"] = mv if mv in {"low", "moderate", "high"} else str(tm.get("motion_level", "low"))

        return {
            "core_search_tags": {"zh": core_zh, "en": core_en},
            "secondary_tags": {"zh": sec_zh, "en": sec_en},
            "tech_meta": {
                "orientation": "portrait" if str(tm.get("orientation", "")).lower() == "portrait" else "landscape",
                "resolution": str(tm.get("resolution", "")).strip(),
                "duration_sec": round(float(tm.get("duration_sec", 0) or 0), 3),
                "motion_level": str(tm.get("motion_level", "low")).strip().lower()
                if str(tm.get("motion_level", "")).strip().lower() in {"low", "moderate", "high"}
                else "low",
            },
            "landmark_gate": self._dedupe_list(forced_landmarks or [])[:3],
        }

    def _draft_index_layers_from_structured(
        self,
        structured_tags: Dict[str, Any],
        evidence: Dict[str, Any],
        forced_landmarks: List[str],
        tech_meta_default: Dict[str, Any],
    ) -> Dict[str, Any]:
        tags = structured_tags.get("tags", {}) if isinstance(structured_tags, dict) else {}
        draft = {
            "core_search_tags": {"zh": [], "en": []},
            "secondary_tags": {"zh": [], "en": []},
            "tech_meta": dict(tech_meta_default or {}),
        }

        def _append(dst: str, vals: List[str], limit: int = 20):
            arr = draft[dst]
            if not isinstance(arr, dict):
                return
            for x in vals:
                text = str(x or "").strip()
                if not text:
                    continue
                if self._contains_cjk(text):
                    arr.setdefault("zh", []).append(text)
                else:
                    arr.setdefault("en", []).append(text.lower())
                if len(arr.get("zh", [])) + len(arr.get("en", [])) >= limit:
                    break

        scene_node = tags.get("scene", {}) if isinstance(tags.get("scene"), dict) else {}
        objects_node = tags.get("objects", {}) if isinstance(tags.get("objects"), dict) else {}
        actions_node = tags.get("actions", {}) if isinstance(tags.get("actions"), dict) else {}
        mood_node = tags.get("mood", {}) if isinstance(tags.get("mood"), dict) else {}
        style_node = tags.get("style", {}) if isinstance(tags.get("style"), dict) else {}
        concept_node = tags.get("concepts", {}) if isinstance(tags.get("concepts"), dict) else {}
        use_case_node = tags.get("use_cases", {}) if isinstance(tags.get("use_cases"), dict) else {}

        _append("core_search_tags", (scene_node.get("zh", []) or []) + (scene_node.get("en", []) or []), limit=16)
        _append("core_search_tags", (objects_node.get("zh", []) or []) + (objects_node.get("en", []) or []), limit=20)
        _append("core_search_tags", (actions_node.get("zh", []) or []) + (actions_node.get("en", []) or []), limit=24)

        for k in forced_landmarks or []:
            e = self._entry_from_key(k)
            if e:
                draft["core_search_tags"]["zh"].append(e["zh"])
                draft["core_search_tags"]["en"].append(e["en"])

        # 抽象词默认进 secondary
        _append("secondary_tags", (mood_node.get("zh", []) or []) + (mood_node.get("en", []) or []), limit=30)
        _append("secondary_tags", (concept_node.get("zh", []) or []) + (concept_node.get("en", []) or []), limit=34)
        _append("secondary_tags", (style_node.get("zh", []) or []) + (style_node.get("en", []) or []), limit=38)
        _append("secondary_tags", (use_case_node.get("zh", []) or []) + (use_case_node.get("en", []) or []), limit=42)

        return self._normalize_index_layers(draft, evidence, forced_landmarks, tech_meta_default)

    def _flatten_index_layer_terms(self, index_layers: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        core = index_layers.get("core_search_tags", {}) if isinstance(index_layers, dict) else {}
        secondary = index_layers.get("secondary_tags", {}) if isinstance(index_layers, dict) else {}
        for layer_name, node in (("core", core), ("secondary", secondary)):
            if not isinstance(node, dict):
                continue
            for lang_key in ("zh", "en"):
                vals = node.get(lang_key, [])
                if not isinstance(vals, list):
                    continue
                for item in vals:
                    term = str(item or "").strip()
                    if not term:
                        continue
                    if lang_key == "en":
                        term = term.lower()
                    out.append(term)
                    out.append(f"{layer_name}:{term}")
        return self._dedupe_list(out)

    @staticmethod
    def _dedupe_list(items: Iterable[str]) -> List[str]:
        out = []
        seen = set()
        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text or ""))

    @staticmethod
    def _split_filename_tokens(stem: str) -> List[str]:
        raw = re.split(r"[_\-\s\.\(\)\[\],]+", stem or "")
        tokens = []
        for part in raw:
            t = part.strip()
            if not t:
                continue
            if len(t) == 1 and not GlobalMediaLibrary._contains_cjk(t):
                continue
            tokens.append(t)
        return tokens

    def _split_path_tokens(self, path: Path, depth: int = 6) -> List[str]:
        try:
            parts = list(path.parts)
        except Exception:
            return []
        out: List[str] = []
        for part in parts[-max(depth, 1):]:
            p = str(part).strip().replace("\\", "/")
            if not p or p in {"/", "."}:
                continue
            leaf = Path(p).stem if "." in p else p
            out.extend(self._split_filename_tokens(leaf))
        return self._dedupe_list(out)

    def _metadata_terms(self, tags: Dict) -> List[str]:
        if not isinstance(tags, dict):
            return []
        terms: List[str] = []
        for k, v in tags.items():
            key = str(k or "").strip().lower()
            val = str(v or "").strip()
            if not key or not val:
                continue
            val = val[:160]
            terms.append(val)
            terms.extend(self._split_filename_tokens(val))
            if any(
                marker in key
                for marker in (
                    "location", "title", "comment", "description",
                    "keyword", "subject", "artist", "make", "model",
                    "software", "copyright", "com.apple.quicktime",
                )
            ):
                terms.append(key.replace("_", " "))
                terms.append(f"{key}:{val}")
        return self._dedupe_list(terms)

    @staticmethod
    def _query_synonyms(token: str) -> List[str]:
        t = str(token or "").strip().lower()
        if not t:
            return []
        rules = [
            (["教堂", "大教堂", "教会", "church", "cathedral", "chapel", "basilica"],
             ["教堂", "大教堂", "church", "cathedral", "chapel", "basilica", "教会", "宗教建筑", "朝圣"]),
            (["哥特", "哥特式", "gothic"],
             ["哥特", "哥特式", "gothic", "gothic architecture", "尖拱", "飞扶壁"]),
            (["铁桥", "钢桥", "桥梁", "桥", "bridge", "viaduct", "overpass", "大桥", "拱桥"],
             ["铁桥", "桥", "bridge", "iron bridge", "steel bridge", "viaduct", "overpass", "大桥", "拱桥"]),
            (["城堡", "castle", "fortress"],
             ["城堡", "castle", "fortress", "古堡", "中世纪"]),
            (["寺庙", "庙", "temple", "shrine"],
             ["寺庙", "temple", "shrine", "古建筑", "religious"]),
            (["修道院", "monastery", "abbey"],
             ["修道院", "monastery", "abbey", "church"]),
            (["清真寺", "mosque"],
             ["清真寺", "mosque", "religious", "宗教建筑"]),
            (["塔", "塔楼", "tower", "bell tower"],
             ["塔", "塔楼", "tower", "地标", "landmark"]),
            (["雕像", "雕塑", "statue", "sculpture"],
             ["雕像", "雕塑", "statue", "sculpture", "landmark"]),
            (["山", "高山", "mountain", "alpine"],
             ["山地", "高山", "mountain", "alpine"]),
            (["海滩", "沙滩", "beach", "coast", "shore"],
             ["海滩", "沙滩", "海边", "beach", "coast"]),
            (["森林", "树林", "forest", "woods"],
             ["森林", "树林", "forest", "woods"]),
        ]
        out: List[str] = []
        for keys, vals in rules:
            if any(k in t for k in keys):
                out.extend(vals)
        return out

    @staticmethod
    def _label_aliases() -> Dict[str, List[str]]:
        return {
            "mountain": ["mountain", "alpine", "高山", "山地", "雪山"],
            "beach": ["beach", "ocean", "coast", "海边", "沙滩", "海岸"],
            "city": ["city", "urban", "street", "城市", "街头", "城区"],
            "forest": ["forest", "woods", "tree", "森林", "树林"],
            "waterfall": ["waterfall", "river", "stream", "瀑布", "河流", "溪流"],
            "snow": ["snow", "ice", "winter", "雪地", "冰川", "滑雪"],
            "indoor": ["indoor", "room", "室内", "房间"],
            "walking": ["walk", "hike", "徒步", "散步", "行走"],
            "sports": ["sports", "ski", "snowboard", "运动", "滑雪", "冲浪"],
            "driving": ["drive", "car", "road", "驾驶", "公路"],
            "talking": ["talk", "speak", "vlog", "解说", "讲述"],
            "food": ["food", "eat", "cook", "美食", "探店", "餐厅"],
            "scenic": ["scenic", "landscape", "风景", "航拍", "观景"],
            "aerial": ["aerial", "drone", "航拍", "无人机"],
            "tracking": ["tracking", "follow", "跟拍", "追踪"],
            "handheld": ["handheld", "手持"],
            "static": ["static", "tripod", "固定机位", "静止"],
            "close_up": ["close-up", "特写", "近景"],
            "medium": ["medium shot", "中景"],
            "wide": ["wide", "landscape", "全景", "远景", "大景"],
            "macro": ["macro", "微距"],
            "first_person": ["first person", "fpv", "第一视角", "主观视角"],
            "third_person": ["third person", "第三视角"],
            "drone_view": ["drone view", "航拍视角", "俯拍"],
            "eye_level": ["eye level", "平视"],
            "warm": ["warm", "golden", "暖色", "金色"],
            "cool": ["cool", "blue", "冷色", "蓝调"],
            "high_contrast": ["contrast", "高对比", "强烈光影"],
            "natural": ["natural", "neutral", "自然色"],
            "morning": ["morning", "sunrise", "清晨", "早上", "日出"],
            "afternoon": ["afternoon", "noon", "中午", "午后"],
            "sunset": ["sunset", "dusk", "黄昏", "日落", "傍晚"],
            "night": ["night", "evening", "夜景", "夜晚", "晚上"],
            "rain": ["rain", "storm", "雨天", "下雨"],
            "fog": ["fog", "mist", "雾天", "薄雾"],
            "sunny": ["sunny", "sunlight", "晴天", "阳光"],
            "cloudy": ["cloudy", "overcast", "阴天", "多云"],
            "travel_vlog": ["travel vlog", "旅行vlog", "旅拍", "旅行记录"],
            "action_montage": ["action montage", "动作剪辑", "燃向混剪"],
            "landmark_story": ["landmark story", "地标故事", "建筑地标", "人文地标", "architecture story"],
            "atmospheric_broll": ["atmospheric broll", "氛围空镜", "治愈空镜"],
            "hero_shot": ["hero shot", "主视觉", "主打镜头"],
            "storytelling_clip": ["storytelling", "叙事镜头", "口播讲述"],
            "hook": ["hook", "开场钩子", "前三秒"],
            "establishing": ["establishing shot", "环境建立镜头", "开场全景"],
            "climax": ["climax", "高潮段", "高能"],
            "explanation": ["explanation", "讲解段", "信息段"],
            "broll": ["b-roll", "过渡镜头", "补充素材"],
            "portrait": ["portrait", "竖屏", "9:16"],
            "landscape": ["landscape", "横屏", "16:9"],
            "square": ["square", "方屏", "1:1"],
            "church": ["church", "cathedral", "chapel", "basilica", "教堂", "大教堂"],
            "gothic": ["gothic", "gothic style", "哥特", "哥特式", "尖拱", "飞扶壁"],
            "bridge": ["bridge", "iron bridge", "steel bridge", "viaduct", "桥", "铁桥", "钢桥", "桥梁"],
            "castle": ["castle", "fortress", "城堡", "古堡", "中世纪建筑"],
            "temple": ["temple", "shrine", "寺庙", "神社", "宗教建筑"],
            "architecture": ["architecture", "building", "建筑", "地标", "landmark"],
            "religious": ["religious", "church", "cathedral", "宗教", "教堂", "寺庙"],
        }

    def _expand_label_aliases(self, labels: Iterable[str]) -> List[str]:
        aliases = self._label_aliases()
        expanded = []
        for label in labels:
            key = str(label or "").strip()
            if not key:
                continue
            expanded.append(key)
            expanded.extend(aliases.get(key, []))
        return self._dedupe_list(expanded)

    @staticmethod
    def _contains_any(text: str, terms: List[str]) -> bool:
        t = text.lower()
        return any(term in t for term in terms)

    @staticmethod
    def _infer_by_keyword(text: str, mapping: Dict[str, List[str]], default: str = "unknown") -> str:
        t = text.lower()
        best_label = default
        best_score = 0
        for label, terms in mapping.items():
            score = 0
            for term in terms:
                if term in t:
                    score += 1
            if score > best_score:
                best_score = score
                best_label = label
        return best_label

    def _infer_time_of_day(self, creation_time: Optional[str], text: str) -> str:
        t = text.lower()
        if self._contains_any(t, ["sunrise", "dawn", "morning", "清晨", "早上", "日出"]):
            return "morning"
        if self._contains_any(t, ["afternoon", "noon", "中午", "午后"]):
            return "afternoon"
        if self._contains_any(t, ["sunset", "dusk", "golden hour", "傍晚", "黄昏", "日落"]):
            return "sunset"
        if self._contains_any(t, ["night", "evening", "夜晚", "晚上", "深夜"]):
            return "night"

        if creation_time and "T" in creation_time:
            try:
                hour = int(str(creation_time).split("T", 1)[1][:2])
                if 5 <= hour < 11:
                    return "morning"
                if 11 <= hour < 16:
                    return "afternoon"
                if 16 <= hour < 20:
                    return "sunset"
                return "night"
            except Exception:
                pass
        return "unknown"

    @staticmethod
    def _infer_emotion_intensity(mood: str, text: str) -> str:
        source = f"{mood} {text}".lower()
        if any(k in source for k in ["intense", "energetic", "excited", "紧张", "激烈", "刺激"]):
            return "high"
        if any(k in source for k in ["calm", "serene", "gentle", "平静", "舒缓", "治愈"]):
            return "low"
        return "medium"

    @staticmethod
    def _infer_quality_tier(quality_score) -> str:
        try:
            q = float(quality_score)
        except Exception:
            return "unknown"
        if q >= 0.85:
            return "high"
        if q >= 0.65:
            return "medium"
        return "low"

    @staticmethod
    def _infer_season(text: str) -> str:
        t = text.lower()
        if any(k in t for k in ["winter", "snow", "ice", "冬", "雪"]):
            return "winter"
        if any(k in t for k in ["spring", "blossom", "花", "春"]):
            return "spring"
        if any(k in t for k in ["summer", "beach", "sunny", "夏", "海边"]):
            return "summer"
        if any(k in t for k in ["autumn", "fall", "枫", "秋"]):
            return "autumn"
        return "unknown"

    @staticmethod
    def _infer_lighting(time_of_day: str, weather: str, text: str) -> str:
        t = text.lower()
        if "backlit" in t or "逆光" in t:
            return "backlit"
        if weather == "fog":
            return "diffused"
        if weather == "night" or time_of_day == "night":
            return "low_light"
        if time_of_day in {"sunrise", "sunset"}:
            return "golden_hour"
        if weather == "sunny":
            return "hard_light"
        return "natural_light"

    @staticmethod
    def _infer_duration_bucket(duration_seconds: float) -> str:
        if duration_seconds <= 0:
            return "unknown"
        if duration_seconds <= 3:
            return "ultra_short"
        if duration_seconds <= 8:
            return "short"
        if duration_seconds <= 20:
            return "medium"
        if duration_seconds <= 60:
            return "long"
        return "extended"

    @staticmethod
    def _infer_orientation(width: Optional[int], height: Optional[int]) -> tuple[str, str]:
        if not width or not height:
            return "unknown", "unknown"
        ratio = float(width) / float(height)
        if ratio < 0.8:
            return "portrait", "9:16_like"
        if ratio > 1.3:
            return "landscape", "16:9_like"
        return "square", "1:1_like"

    @staticmethod
    def _infer_content_type(activity: str, people_presence: str, setting: str, visual_style: str) -> str:
        if activity == "talking":
            return "talking_head"
        if activity == "architecture_tour" or setting in {"church", "bridge", "castle", "temple"}:
            return "architecture_documentary"
        if activity in {"sports", "driving"}:
            return "action"
        if setting in {"mountain", "beach", "forest", "waterfall", "snow"}:
            return "scenery"
        if visual_style in {"vlog", "travel"} and people_presence == "present":
            return "travel_lifestyle"
        return "general"

    @staticmethod
    def _infer_action_intensity(activity: str, camera_movement: str, emotion_intensity: str) -> str:
        if activity in {"sports", "driving"}:
            return "high"
        if camera_movement in {"tracking", "handheld"} and emotion_intensity == "high":
            return "high"
        if activity in {"walking", "scenic"}:
            return "medium"
        return "low"

    @staticmethod
    def _infer_stability_level(camera_movement: str, action_intensity: str) -> str:
        if camera_movement in {"static", "pan_tilt"} and action_intensity != "high":
            return "stable"
        if camera_movement in {"handheld", "tracking"} or action_intensity == "high":
            return "dynamic"
        return "balanced"

    @staticmethod
    def _infer_audience_intent(content_type: str, activity: str, narrative_role: str) -> str:
        if activity == "talking" or narrative_role == "explanation":
            return "information"
        if content_type == "architecture_documentary" or activity == "architecture_tour":
            return "information"
        if content_type in {"scenery", "travel_lifestyle"}:
            return "inspiration"
        if content_type == "action":
            return "entertainment"
        return "general"

    @staticmethod
    def _infer_clip_purpose(narrative_role: str, use_cases: List[str]) -> str:
        if narrative_role == "hook":
            return "opening"
        if narrative_role == "establishing":
            return "context"
        if narrative_role == "climax":
            return "highlight"
        if "atmospheric_broll" in use_cases:
            return "transition"
        return "supporting"

    @staticmethod
    def _tokenize_query(query: str) -> List[str]:
        raw = re.split(r"[\s,，;；|/]+", query.strip().lower())
        tokens: List[str] = []
        for part in raw:
            p = part.strip()
            if not p:
                continue
            tokens.append(p)
            if re.search(r"[\u4e00-\u9fff]", p) and len(p) >= 4:
                for n in (2, 3, 4):
                    for i in range(0, len(p) - n + 1):
                        tokens.append(p[i:i + n])
        deduped = []
        seen = set()
        for t in tokens:
            if len(t) <= 1:
                continue
            if t in seen:
                continue
            seen.add(t)
            deduped.append(t)

        expanded = list(deduped)
        for t in deduped:
            expanded.extend(GlobalMediaLibrary._query_synonyms(t))

        final = []
        seen2 = set()
        for t in expanded:
            text = str(t or "").strip().lower()
            if len(text) <= 1:
                continue
            if text in seen2:
                continue
            seen2.add(text)
            final.append(text)
        return final[:120]

    @staticmethod
    def _relaxed_query_tokens(tokens: List[str]) -> List[str]:
        raw = [str(t or "").strip().lower() for t in tokens if str(t or "").strip()]
        if not raw:
            return []
        out = list(raw)
        token_text = " ".join(raw)
        if any(k in token_text for k in ["教堂", "church", "cathedral", "chapel", "basilica", "religious", "朝圣"]):
            out.extend(["architecture", "religious", "building", "landmark", "城市", "建筑", "朝圣"])
        if any(k in token_text for k in ["哥特", "gothic"]):
            out.extend(["gothic", "architecture", "building", "中世纪", "castle", "cathedral", "古建筑"])
        if any(k in token_text for k in ["铁桥", "桥", "bridge", "viaduct", "overpass"]):
            out.extend(["bridge", "river", "water", "city", "architecture", "landscape", "桥"])

        dedup = []
        seen = set()
        for t in out:
            if t in seen:
                continue
            seen.add(t)
            dedup.append(t)
        return dedup[:80]

    # ── Phase 2: Evidence persistence + tag resolution ──

    # Sentinel: returned by _resolve_tag_id when term is a stopword
    _STOPWORD_SENTINEL = -1

    def _resolve_tag_id(
        self, term: str, conn: sqlite3.Connection, *, _cache: Optional[Dict] = None,
        context: str = "ingest",
    ) -> Optional[int]:
        """Resolve a term to a tag_id via the matching chain.

        Chain: stopword → exact tag_name → normalized_name → alias → custom_tag.
        Returns tag_id, _STOPWORD_SENTINEL (-1) for stopwords, or None for unknown.

        context="ingest": existing behaviour (may write learning_candidate in future).
        context="search": purely read-only, no side-effects.
        """
        if not term or not term.strip():
            return None
        normalized = term.lower().strip()
        if len(normalized) < 2:
            return None

        # Check cache first
        if _cache is not None and normalized in _cache:
            return _cache[normalized]

        # 1. Stopword check
        stop = conn.execute(
            "SELECT 1 FROM learning_stopword WHERE normalized_text = ?",
            (normalized,),
        ).fetchone()
        if stop:
            if _cache is not None:
                _cache[normalized] = self._STOPWORD_SENTINEL
            return self._STOPWORD_SENTINEL

        # 2. Exact match tag.tag_name
        row = conn.execute(
            "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1 LIMIT 1",
            (term.strip(),),
        ).fetchone()
        if row:
            tid = row[0]
            if _cache is not None:
                _cache[normalized] = tid
            return tid

        # 3. Normalized match
        row = conn.execute(
            "SELECT tag_id FROM tag WHERE normalized_name = ? AND is_active = 1 LIMIT 1",
            (normalized,),
        ).fetchone()
        if row:
            tid = row[0]
            if _cache is not None:
                _cache[normalized] = tid
            return tid

        # 4. Alias match
        row = conn.execute(
            "SELECT tag_id FROM tag_alias WHERE normalized_alias = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if row:
            tid = row[0]
            if _cache is not None:
                _cache[normalized] = tid
            return tid

        # 5. Custom tag match
        row = conn.execute(
            "SELECT parent_system_tag_id FROM custom_tag WHERE normalized_name = ? AND status != 'archived' LIMIT 1",
            (normalized,),
        ).fetchone()
        if row and row[0]:
            tid = row[0]
            if _cache is not None:
                _cache[normalized] = tid
            return tid

        # No match
        if _cache is not None:
            _cache[normalized] = None
        return None

    # ── Phase 3: helpers for tag recall ──

    def _classify_resolution(
        self, term: str, tag_id: int, conn: sqlite3.Connection,
    ) -> str:
        """Classify how *term* resolved to *tag_id*.

        Returns one of: exact, normalized, alias, custom.
        """
        normalized = term.lower().strip()
        row = conn.execute(
            "SELECT tag_name, normalized_name FROM tag WHERE tag_id = ? LIMIT 1",
            (tag_id,),
        ).fetchone()
        if row:
            if row[0] == term.strip():
                return "exact"
            if row[1] == normalized:
                return "normalized"
        alias_row = conn.execute(
            "SELECT 1 FROM tag_alias WHERE tag_id = ? AND normalized_alias = ? LIMIT 1",
            (tag_id, normalized),
        ).fetchone()
        if alias_row:
            return "alias"
        custom_row = conn.execute(
            "SELECT 1 FROM custom_tag WHERE parent_system_tag_id = ? AND normalized_name = ? LIMIT 1",
            (tag_id, normalized),
        ).fetchone()
        if custom_row:
            return "custom"
        return "exact"  # fallback

    _tag_name_cache: Dict[int, str] = {}

    def _get_tag_name_cached(self, tag_id: int, conn: sqlite3.Connection) -> str:
        """Return tag_name for tag_id, using instance-level cache."""
        if tag_id in self._tag_name_cache:
            return self._tag_name_cache[tag_id]
        row = conn.execute(
            "SELECT tag_name FROM tag WHERE tag_id = ? LIMIT 1", (tag_id,),
        ).fetchone()
        name = row[0] if row else f"tag_{tag_id}"
        self._tag_name_cache[tag_id] = name
        return name

    def _classify_query(
        self,
        query: str,
        resolved_tags: Dict[str, int],
        resolution_info: Dict[str, Dict],
        conn: sqlite3.Connection,
    ) -> str:
        """Classify query type for dynamic weight selection.

        Returns: exact_tag | alias_tag | composed_query | abstract_intent
        """
        n_resolved = len(resolved_tags)

        if n_resolved >= 2:
            return "composed_query"

        if n_resolved == 0:
            return "abstract_intent"

        # n_resolved == 1: check for abstract intent signals
        q_lower = query.lower()
        if any(kw in q_lower for kw in ABSTRACT_INTENT_KEYWORDS):
            return "abstract_intent"

        # Single resolved tag — classify by hit_type
        info = next(iter(resolution_info.values()), {})
        hit_type = info.get("hit_type", "exact")
        if hit_type in ("exact", "normalized"):
            return "exact_tag"
        if hit_type in ("alias", "custom"):
            return "alias_tag"
        return "exact_tag"

    def _persist_evidence_and_tags(
        self, uid: str, semantic_json: Dict, conn: sqlite3.Connection,
    ) -> int:
        """Dual-write: persist evidence + compute & write asset_tag_result.

        Extracts terms from structured_tags and flat semantic fields,
        resolves to tag_id, computes scores with rule corrections,
        writes evidence + asset_tag_result rows.

        Returns the number of tag results written.
        """
        if not semantic_json or not isinstance(semantic_json, dict):
            return 0

        structured_tags = semantic_json.get("structured_tags", {})
        if not isinstance(structured_tags, dict):
            return 0
        tags_dict = structured_tags.get("tags", structured_tags)
        if not isinstance(tags_dict, dict):
            return 0

        now = self._now()
        tag_cache = {}  # term → tag_id (per-call resolution cache)
        tag_scores = {}  # tag_id → {base_score, source_summary, slot, term, decision_reasons}
        unresolved = []  # (term, category_hint)
        model_version = (semantic_json.get("_meta") or {}).get("model_version", "unknown")

        # ── Idempotency: clear prior evidence for this asset ──
        try:
            conn.execute("DELETE FROM evidence WHERE asset_id = ?", (uid,))
        except Exception:
            pass

        # ── A. Extract from structured_tags (25 categories) ──
        for cat, cat_data in tags_dict.items():
            if not isinstance(cat_data, dict):
                continue
            zh_terms = cat_data.get("zh", [])
            if not isinstance(zh_terms, list):
                continue
            confidence = float(cat_data.get("confidence", 0.6))
            slot = _TAG_CATEGORY_TO_SLOT.get(cat, "object")

            for term in zh_terms:
                if not isinstance(term, str) or not term.strip():
                    continue
                tag_id = self._resolve_tag_id(term, conn, _cache=tag_cache)
                if tag_id is None or tag_id == self._STOPWORD_SENTINEL:
                    if tag_id is None:  # genuinely unknown → learning candidate
                        t = term.strip()
                        if t and len(t) >= 2:
                            unresolved.append((t, cat))
                    # stopword → silently skip (no learning_candidate)
                    continue

                source_weight = SCORING_CONFIG["source_weight"].get("llm", 1.0)
                weighted = min(confidence * source_weight, 1.0)

                # Write evidence (one per tag per source_kind)
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO evidence
                           (asset_id, tag_id, semantic_slot, source_kind, source_model,
                            raw_value, base_score, weighted_score, created_at)
                           VALUES (?, ?, ?, 'llm', ?, ?, ?, ?, ?)""",
                        (uid, tag_id, slot, model_version,
                         term, confidence, weighted, now),
                    )
                except Exception:
                    pass

                # Keep best score per tag_id
                if tag_id not in tag_scores or weighted > tag_scores[tag_id]["base_score"]:
                    tag_scores[tag_id] = {
                        "base_score": weighted,
                        "source_summary": "llm",
                        "slot": slot,
                        "term": term,
                    }

        # ── B. Extract from flat semantic fields ──
        for field, slot in _FIELD_TO_SLOT.items():
            val = semantic_json.get(field)
            if not val or not isinstance(val, str) or val in ("unknown", "general", "none"):
                continue
            tag_id = self._resolve_tag_id(val, conn, _cache=tag_cache)
            if tag_id and tag_id != self._STOPWORD_SENTINEL and tag_id not in tag_scores:
                source_weight = SCORING_CONFIG["source_weight"].get("llm", 1.0)
                weighted = min(0.70 * source_weight, 1.0)
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO evidence
                           (asset_id, tag_id, semantic_slot, source_kind, source_model,
                            raw_value, base_score, weighted_score, created_at)
                           VALUES (?, ?, ?, 'llm', ?, ?, ?, ?, ?)""",
                        (uid, tag_id, slot, model_version, val, 0.70, weighted, now),
                    )
                except Exception:
                    pass
                tag_scores[tag_id] = {
                    "base_score": weighted,
                    "source_summary": "llm",
                    "slot": slot,
                    "term": val,
                }

        # ── C. Rule corrections ──
        tag_ids_present = set(tag_scores.keys())

        # C1. Hierarchy bonus — child confirmed → parent gets bonus
        hierarchy_bonus = {}
        for tag_id in list(tag_ids_present):
            parents = conn.execute(
                "SELECT to_tag_id FROM tag_relation WHERE from_tag_id = ? AND relation_type = 'child'",
                (tag_id,),
            ).fetchall()
            for pr in parents:
                pid = pr[0]
                hierarchy_bonus[pid] = max(
                    hierarchy_bonus.get(pid, 0.0),
                    SCORING_CONFIG["hierarchy_bonus"],
                )

        # C2. Conflict penalty — conflicting tags penalize each other
        conflict_penalty = {}
        for tag_id in list(tag_ids_present):
            conflicts = conn.execute(
                "SELECT to_tag_id FROM tag_relation WHERE from_tag_id = ? AND relation_type = 'conflict'",
                (tag_id,),
            ).fetchall()
            for cr in conflicts:
                if cr[0] in tag_ids_present:
                    conflict_penalty[tag_id] = max(
                        conflict_penalty.get(tag_id, 0.0),
                        SCORING_CONFIG["conflict_penalty"],
                    )
                    conflict_penalty[cr[0]] = max(
                        conflict_penalty.get(cr[0], 0.0),
                        SCORING_CONFIG["conflict_penalty"],
                    )

        # C3. Cooccurrence bonus
        cooccurrence_bonus = {}
        cooc_rules = conn.execute(
            "SELECT target_tag_id, min_match_count, score_bonus, expr_json "
            "FROM composite_rule WHERE rule_type = 'cooccurrence' AND is_active = 1",
        ).fetchall()
        for rule in cooc_rules:
            expr = json.loads(rule[3] or "{}")
            if_tags = expr.get("if_tags", [])
            matched = 0
            for t in if_tags:
                resolved = self._resolve_tag_id(t, conn, _cache=tag_cache)
                if resolved and resolved in tag_ids_present:
                    matched += 1
            if matched >= rule[1]:
                target = rule[0]
                cooccurrence_bonus[target] = max(
                    cooccurrence_bonus.get(target, 0.0),
                    rule[2],
                )

        # C4. Negative penalty
        negative_penalty = {}
        neg_rules = conn.execute(
            "SELECT target_tag_id, penalty_value, expr_json "
            "FROM composite_rule WHERE rule_type = 'negative' AND is_active = 1",
        ).fetchall()
        for rule in neg_rules:
            target = rule[0]
            if target not in tag_ids_present:
                continue
            expr = json.loads(rule[2] or "{}")
            penalty_val = rule[1]
            # require_any: target tag needs at least one support tag
            require_any = expr.get("require_any", [])
            if require_any:
                has_support = any(
                    self._resolve_tag_id(t, conn, _cache=tag_cache) in tag_ids_present
                    for t in require_any
                )
                if not has_support:
                    negative_penalty[target] = max(
                        negative_penalty.get(target, 0.0), penalty_val,
                    )
            # negative_any: if negative tag is present, penalize target
            negative_any = expr.get("negative_any", [])
            for neg_term in negative_any:
                neg_id = self._resolve_tag_id(neg_term, conn, _cache=tag_cache)
                if neg_id and neg_id in tag_ids_present:
                    negative_penalty[target] = max(
                        negative_penalty.get(target, 0.0), penalty_val,
                    )

        # ── D. Write asset_tag_result ──
        write_threshold = SCORING_CONFIG["write_threshold"]
        display_threshold = SCORING_CONFIG["display_threshold"]
        bands = SCORING_CONFIG["confidence_bands"]
        written = 0

        for tag_id, info in tag_scores.items():
            base = info["base_score"]
            cooc = cooccurrence_bonus.get(tag_id, 0.0)
            hier = hierarchy_bonus.get(tag_id, 0.0)
            conf = conflict_penalty.get(tag_id, 0.0)
            neg = negative_penalty.get(tag_id, 0.0)

            final_score = max(0.0, min(1.0, base + cooc + hier - conf - neg))
            effective_score = max(0.0, min(1.0, final_score))  # user_adjustment=0 initially

            if effective_score < write_threshold:
                continue

            if effective_score >= bands["high"]:
                band = "high"
            elif effective_score >= bands["medium"]:
                band = "medium"
            else:
                band = "low"

            is_displayed = 1 if effective_score >= display_threshold else 0
            decision_reason = json.dumps(
                [{"source": info["source_summary"], "term": info["term"],
                  "score": round(base, 3)}],
                ensure_ascii=False,
            )

            try:
                conn.execute(
                    """INSERT OR REPLACE INTO asset_tag_result
                       (asset_id, segment_id, tag_id, result_scope,
                        base_score, source_bonus, cooccurrence_bonus, hierarchy_bonus,
                        conflict_penalty, negative_penalty,
                        final_score, user_adjustment, effective_score,
                        rank_no, is_displayed, source_summary, confidence_band,
                        user_confirm_state, decision_reason, created_at, updated_at)
                       VALUES (?, '', ?, 'asset',
                               ?, 0.0, ?, ?,
                               ?, ?,
                               ?, 0.0, ?,
                               0, ?, ?, ?,
                               'none', ?, ?, ?)""",
                    (uid, tag_id,
                     base, cooc, hier,
                     conf, neg,
                     final_score, effective_score,
                     is_displayed, info["source_summary"], band,
                     decision_reason, now, now),
                )
                written += 1
            except Exception:
                pass

        # ── E. Write unresolved terms to learning_candidate ──
        for term, cat in unresolved:
            normalized = term.lower().strip()
            try:
                conn.execute(
                    """INSERT INTO learning_candidate
                       (candidate_text, normalized_text, category_hint, source_kind,
                        occurrence_count, asset_count)
                       VALUES (?, ?, ?, 'llm', 1, 1)
                       ON CONFLICT(normalized_text, source_kind) DO UPDATE SET
                           occurrence_count = occurrence_count + 1,
                           asset_count = asset_count + 1""",
                    (term, normalized, cat),
                )
            except Exception:
                pass

        # ── F. Enforce evidence limits ──
        ev_count = conn.execute(
            "SELECT count(*) FROM evidence WHERE asset_id = ?", (uid,),
        ).fetchone()[0]
        if ev_count > EVIDENCE_LIMITS["max_per_asset"]:
            conn.execute(
                """DELETE FROM evidence WHERE evidence_id IN (
                       SELECT evidence_id FROM evidence
                       WHERE asset_id = ?
                       ORDER BY weighted_score ASC
                       LIMIT ?
                   )""",
                (uid, ev_count - EVIDENCE_LIMITS["max_per_asset"]),
            )

        return written

    def _build_semantic_bundle(
        self,
        path: Path,
        analysis: Dict,
        scene_description: Optional[str],
        mood: Optional[str],
        objects: List[str],
        quality_score,
    ) -> Dict:
        metadata = analysis.get("metadata", {}) if isinstance(analysis, dict) else {}
        local = analysis.get("local_analysis", {}) if isinstance(analysis, dict) else {}
        technical = local.get("technical", {}) if isinstance(local, dict) else {}
        tags = metadata.get("tags") if isinstance(metadata, dict) else {}
        tags = tags if isinstance(tags, dict) else {}
        tag_values = [str(v).strip() for v in tags.values() if isinstance(v, (str, int, float))]
        metadata_terms = self._metadata_terms(tags)
        recommendations = analysis.get("recommendations", []) if isinstance(analysis, dict) else []
        rec_text = " ".join(
            f"{str(r.get('type', ''))} {str(r.get('priority', ''))} {str(r.get('message', ''))} {str(r.get('action', ''))}"
            for r in recommendations
            if isinstance(r, dict)
        )

        scene_text = str(scene_description or "")
        mood_text = str(mood or "")
        object_list = [str(o).strip() for o in (objects or []) if str(o).strip()]
        object_text = " ".join(object_list)
        filename_text = path.stem
        filename_tokens = self._split_filename_tokens(filename_text)
        path_tokens = self._split_path_tokens(path)

        duration_f = 0.0
        try:
            duration_f = float(metadata.get("duration") or 0.0)
        except Exception:
            duration_f = 0.0

        width, height = self._parse_resolution(technical.get("resolution"))
        streams = metadata.get("video_streams") if isinstance(metadata, dict) else []
        if (not width or not height) and isinstance(streams, list) and streams:
            first_stream = streams[0] if isinstance(streams[0], dict) else {}
            try:
                width = width or int(first_stream.get("width") or 0)
                height = height or int(first_stream.get("height") or 0)
            except Exception:
                pass

        scene_visual = {}
        if isinstance(local, dict):
            scene_local = local.get("scene", {})
            if isinstance(scene_local, dict):
                raw_visual = scene_local.get("visual_features", {})
                if isinstance(raw_visual, dict):
                    scene_visual = raw_visual

        def _vf(key: str, default: float) -> float:
            try:
                return float(scene_visual.get(key, default))
            except Exception:
                return default

        brightness_v = _vf("brightness", 0.5)
        saturation_v = _vf("saturation", 0.35)
        edge_v = _vf("edge_density", 0.1)
        motion_v = _vf("motion_score", 0.0)
        face_ratio_v = _vf("face_ratio", 0.0)
        red_ratio_v = _vf("red_ratio", 0.33)
        green_ratio_v = _vf("green_ratio", 0.33)
        blue_ratio_v = _vf("blue_ratio", 0.33)

        if blue_ratio_v >= green_ratio_v and blue_ratio_v >= red_ratio_v:
            dominant_color = "blue_dominant"
        elif green_ratio_v >= red_ratio_v:
            dominant_color = "green_dominant"
        else:
            dominant_color = "red_dominant"

        if brightness_v >= 0.72:
            brightness_level = "bright"
        elif brightness_v <= 0.38:
            brightness_level = "dim"
        else:
            brightness_level = "balanced_brightness"

        if saturation_v >= 0.48:
            saturation_level = "vivid"
        elif saturation_v <= 0.26:
            saturation_level = "desaturated"
        else:
            saturation_level = "neutral_saturation"

        if motion_v >= 24.0:
            motion_level = "fast_motion"
        elif motion_v >= 10.0:
            motion_level = "moderate_motion"
        else:
            motion_level = "static_motion"

        if edge_v >= 0.16:
            texture_complexity = "complex_texture"
        elif edge_v <= 0.07:
            texture_complexity = "simple_texture"
        else:
            texture_complexity = "medium_texture"

        if face_ratio_v >= 0.30:
            face_presence_level = "high_face_presence"
        elif face_ratio_v >= 0.10:
            face_presence_level = "medium_face_presence"
        else:
            face_presence_level = "low_face_presence"

        inferred_arch_tokens = []
        corpus_seed = " ".join(
            [
                filename_text,
                " ".join(filename_tokens),
                " ".join(path_tokens),
                " ".join(metadata_terms),
                scene_text,
                mood_text,
                object_text,
                " ".join(tag_values),
                rec_text,
            ]
        ).lower()
        if self._contains_any(corpus_seed, ["教堂", "church", "cathedral", "chapel", "basilica", "朝圣", "pilgrimage", "圣地", "holy"]):
            inferred_arch_tokens.extend(["church", "architecture", "religious"])
        if self._contains_any(corpus_seed, ["哥特", "gothic"]):
            inferred_arch_tokens.extend(["gothic", "architecture"])
        if self._contains_any(corpus_seed, ["铁桥", "钢桥", "桥", "bridge", "viaduct", "overpass", "大桥", "拱桥"]):
            inferred_arch_tokens.extend(["bridge", "architecture"])
        if self._contains_any(corpus_seed, ["城堡", "castle", "fortress"]):
            inferred_arch_tokens.extend(["castle", "architecture"])
        if self._contains_any(corpus_seed, ["寺庙", "temple", "shrine", "修道院", "monastery"]):
            inferred_arch_tokens.extend(["temple", "religious", "architecture"])
        if inferred_arch_tokens:
            object_list = self._dedupe_list(object_list + inferred_arch_tokens)
            object_text = " ".join(object_list)

        corpus = " ".join(
            [
                filename_text,
                " ".join(filename_tokens),
                " ".join(path_tokens),
                " ".join(metadata_terms),
                scene_text,
                mood_text,
                object_text,
                " ".join(tag_values),
                rec_text,
                dominant_color,
                brightness_level,
                saturation_level,
                motion_level,
                texture_complexity,
            ]
        ).lower()

        location_mapping = {
            "mountain": ["mountain", "alpine", "hill", "雪山", "高山", "山脉"],
            "beach": ["beach", "sea", "ocean", "coast", "沙滩", "海边", "海岸"],
            "city": ["city", "street", "urban", "building", "城市", "街头", "城区"],
            "indoor": ["indoor", "room", "studio", "kitchen", "室内", "房间", "客厅", "厨房"],
            "forest": ["forest", "tree", "woods", "树林", "森林"],
            "snow": ["snow", "ice", "winter", "滑雪", "雪地", "冰川"],
            "waterfall": ["waterfall", "river", "stream", "瀑布", "河流", "溪流"],
            "church": ["church", "cathedral", "chapel", "basilica", "教堂", "大教堂"],
            "bridge": ["bridge", "iron bridge", "steel bridge", "viaduct", "桥", "铁桥", "钢桥"],
            "castle": ["castle", "fortress", "城堡", "古堡", "要塞"],
            "temple": ["temple", "shrine", "monastery", "abbey", "寺庙", "修道院", "神社"],
        }
        activity_mapping = {
            "walking": ["walk", "walking", "hiking", "徒步", "行走"],
            "sports": ["ski", "snowboard", "surf", "run", "运动", "滑雪", "冲浪", "跑步"],
            "driving": ["drive", "car", "road", "驾驶", "公路", "车"],
            "talking": ["talk", "speak", "vlog", "分享", "解说", "讲解"],
            "food": ["food", "cook", "eat", "餐厅", "美食", "做饭", "吃"],
            "scenic": ["scenic", "landscape", "view", "风景", "观景", "航拍"],
            "architecture_tour": ["architecture", "gothic", "church", "cathedral", "bridge", "landmark", "建筑", "地标", "古建"],
        }
        style_mapping = {
            "vlog": ["vlog", "daily", "日常", "记录"],
            "cinematic": ["cinematic", "film", "大片", "电影感"],
            "documentary": ["documentary", "纪录", "采访", "讲述"],
            "tutorial": ["tutorial", "how to", "教程", "教学", "攻略"],
            "travel": ["travel", "trip", "journey", "旅行", "旅途"],
        }
        movement_mapping = {
            "aerial": ["drone", "aerial", "航拍", "俯拍"],
            "tracking": ["tracking", "follow", "跟拍", "追踪"],
            "pan_tilt": ["pan", "tilt", "横移", "摇镜"],
            "handheld": ["handheld", "手持"],
            "static": ["static", "tripod", "固定机位", "静止"],
        }
        shot_mapping = {
            "close_up": ["close-up", "close up", "特写", "近景", "portrait"],
            "medium": ["medium shot", "中景"],
            "wide": ["wide", "landscape", "远景", "全景", "大景"],
            "macro": ["macro", "微距"],
        }
        perspective_mapping = {
            "first_person": ["first person", "fpv", "第一视角", "主观视角"],
            "third_person": ["third person", "第三视角"],
            "drone_view": ["drone", "aerial", "航拍"],
            "eye_level": ["eye level", "平视"],
        }
        framing_mapping = {
            "subject_centered": ["center", "居中"],
            "rule_of_thirds": ["rule of thirds", "三分法"],
            "symmetry": ["symmetry", "对称"],
            "dynamic": ["dynamic", "动感"],
        }
        color_mapping = {
            "warm": ["warm", "golden", "sunset", "暖色", "金色"],
            "cool": ["cool", "blue", "cold", "冷色", "蓝调"],
            "high_contrast": ["contrast", "高对比", "强烈光影"],
            "natural": ["natural", "neutral", "自然色"],
        }
        weather_mapping = {
            "snow": ["snow", "blizzard", "雪", "冰"],
            "rain": ["rain", "storm", "雨", "暴雨"],
            "fog": ["fog", "mist", "雾", "薄雾"],
            "sunny": ["sunny", "sunlight", "晴天", "阳光"],
            "cloudy": ["cloud", "overcast", "阴天", "多云"],
        }

        setting = self._infer_by_keyword(corpus, location_mapping, default="general")
        activity = self._infer_by_keyword(corpus, activity_mapping, default="general")
        visual_style = self._infer_by_keyword(corpus, style_mapping, default="general")
        camera_movement = self._infer_by_keyword(corpus, movement_mapping, default="unknown")
        shot_type = self._infer_by_keyword(corpus, shot_mapping, default="unknown")
        perspective = self._infer_by_keyword(corpus, perspective_mapping, default="unknown")
        framing = self._infer_by_keyword(corpus, framing_mapping, default="unknown")
        color_tone = self._infer_by_keyword(corpus, color_mapping, default="natural")
        weather = self._infer_by_keyword(corpus, weather_mapping, default="unknown")
        location_type = "indoor" if setting == "indoor" else ("outdoor" if setting != "general" else "unknown")

        if setting == "general":
            if dominant_color == "green_dominant":
                setting = "forest"
            elif dominant_color == "blue_dominant" and "water" in object_list:
                setting = "beach"
            elif texture_complexity == "complex_texture":
                setting = "city"
            elif brightness_level == "dim":
                setting = "indoor"
        if activity == "general":
            if motion_level in {"fast_motion", "moderate_motion"}:
                activity = "walking"
            else:
                activity = "scenic"
        if weather == "unknown":
            if brightness_level == "bright":
                weather = "sunny"
            elif brightness_level == "dim" and saturation_level == "desaturated":
                weather = "cloudy"
        location_type = "indoor" if setting == "indoor" else ("outdoor" if setting != "general" else "unknown")

        creation_time = tags.get("creation_time") if isinstance(tags, dict) else None
        time_of_day = self._infer_time_of_day(str(creation_time) if creation_time else None, corpus)
        season = self._infer_season(corpus)
        lighting_condition = self._infer_lighting(time_of_day, weather, corpus)

        primary_subject = "person" if any(o.lower() == "person" for o in object_list) else (object_list[0] if object_list else "unknown")
        people_presence = "present" if any(o.lower() in {"person", "people", "human"} for o in object_list) else "none"
        if people_presence == "none" and face_presence_level in {"medium_face_presence", "high_face_presence"}:
            people_presence = "present"
            if primary_subject == "unknown":
                primary_subject = "person"
        quality_tier = self._infer_quality_tier(quality_score)
        emotion_intensity = self._infer_emotion_intensity(mood_text, corpus)

        use_cases = []
        if visual_style in {"travel", "vlog", "cinematic"} or setting in {"mountain", "beach", "city", "forest", "snow", "waterfall"}:
            use_cases.append("travel_vlog")
        if activity in {"sports", "driving"} or motion_level == "fast_motion":
            use_cases.append("action_montage")
        if setting in {"church", "bridge", "castle", "temple"} or activity == "architecture_tour":
            use_cases.append("landmark_story")
        if emotion_intensity == "low":
            use_cases.append("atmospheric_broll")
        if quality_tier == "high":
            use_cases.append("hero_shot")
        if activity == "talking":
            use_cases.append("storytelling_clip")
        if not use_cases:
            use_cases.append("general_broll")

        narrative_role = "hook" if 0 < duration_f <= 6 else "broll"
        if activity == "talking":
            narrative_role = "explanation"
        elif activity == "sports":
            narrative_role = "climax"
        elif shot_type == "wide":
            narrative_role = "establishing"

        orientation, aspect_ratio_bucket = self._infer_orientation(width, height)
        duration_bucket = self._infer_duration_bucket(duration_f)
        content_type = self._infer_content_type(activity, people_presence, setting, visual_style)
        action_intensity = self._infer_action_intensity(activity, camera_movement, emotion_intensity)
        stability_level = self._infer_stability_level(camera_movement, action_intensity)
        clip_purpose = self._infer_clip_purpose(narrative_role, use_cases)
        audience_intent = self._infer_audience_intent(content_type, activity, narrative_role)
        camera_platform = "drone" if camera_movement == "aerial" else ("vehicle" if activity == "driving" else ("tripod" if camera_movement == "static" else "handheld"))

        business_tags = []
        for rec in recommendations:
            if not isinstance(rec, dict):
                continue
            rec_type = str(rec.get("type", "")).strip().lower()
            rec_priority = str(rec.get("priority", "")).strip().lower()
            message = f"{rec.get('message', '')} {rec.get('action', '')}".lower()
            if rec_type:
                business_tags.append(rec_type)
            if rec_priority:
                business_tags.append(f"priority_{rec_priority}")
            if any(k in message for k in ["旅行", "travel", "vlog", "冒险"]):
                business_tags.append("travel_content")
            if any(k in message for k in ["教程", "教学", "guide", "攻略"]):
                business_tags.append("tutorial_content")
            if any(k in message for k in ["文化", "heritage", "教育"]):
                business_tags.append("culture_content")
        if not business_tags:
            business_tags = ["general_content"]
        business_tags = self._dedupe_list(business_tags)

        topic_labels = [
            setting,
            activity,
            visual_style,
            mood_text,
            weather,
            time_of_day,
            season,
            narrative_role,
            clip_purpose,
            content_type,
            audience_intent,
            orientation,
            duration_bucket,
            dominant_color,
            brightness_level,
            saturation_level,
            motion_level,
            texture_complexity,
            face_presence_level,
        ]
        topics = self._dedupe_list(object_list + topic_labels + use_cases + business_tags)

        label_keywords = self._expand_label_aliases(
            [
                setting,
                activity,
                visual_style,
                camera_movement,
                shot_type,
                perspective,
                framing,
                color_tone,
                weather,
                time_of_day,
                season,
                narrative_role,
                clip_purpose,
                orientation,
                content_type,
                audience_intent,
                dominant_color,
                brightness_level,
                saturation_level,
                motion_level,
                texture_complexity,
                face_presence_level,
            ]
            + use_cases
        )
        audio_streams = metadata.get("audio_streams") if isinstance(metadata, dict) else []
        audio_cues = []
        if isinstance(audio_streams, list) and audio_streams:
            audio_cues.append("audio present")
            for stream in audio_streams[:2]:
                if isinstance(stream, dict):
                    codec_name = str(stream.get("codec", "")).strip()
                    channels = stream.get("channels")
                    if codec_name:
                        audio_cues.append(codec_name)
                    if channels:
                        audio_cues.append(f"{channels}ch")

        transcript_hint = ""
        for k, v in tags.items():
            key = str(k or "").lower()
            if any(x in key for x in ("comment", "description", "lyrics", "subtitle", "transcript")):
                transcript_hint += f" {v}"
        transcript_hint = transcript_hint.strip()

        evidence_payload = {
            "video_id": str(path),
            "duration_sec": duration_f,
            "keyframes": [
                {"t": 0.0, "caption": scene_text},
                {"t": max(duration_f * 0.45, 0.0), "caption": " ".join(object_list[:8])},
                {"t": max(duration_f * 0.8, 0.0), "caption": " ".join(path_tokens[:10])},
            ],
            "ocr": [{"t": 0.0, "text": t} for t in metadata_terms[:12]],
            "transcript": transcript_hint,
            "audio_cues": audio_cues[:8],
            "objects": object_list,
            "activity": activity,
            "setting": setting,
            "mood": mood_text,
            "visual_style": visual_style,
            "camera_movement": camera_movement,
            "shot_type": shot_type,
            "perspective": perspective,
            "time_of_day": time_of_day,
            "season": season,
            "weather": weather,
            "narrative_role": narrative_role,
            "emotion_intensity": emotion_intensity,
            "use_cases": use_cases,
            "scene_description": scene_text,
            "color_tone": color_tone,
            "evidence_text": corpus,
        }
        draft_tag_schema = self._heuristic_structured_tags(evidence_payload)
        llm_tag_schema = self._llm_structured_tags(path, evidence_payload, draft_tag_schema)
        structured_tag_schema = self._normalize_structured_tags(
            llm_tag_schema if llm_tag_schema else draft_tag_schema,
            corpus,
        )
        orientation_binary = "landscape"
        if width and height and int(height) > int(width):
            orientation_binary = "portrait"
        elif orientation == "portrait":
            orientation_binary = "portrait"
        resolution_text = ""
        if width and height:
            resolution_text = f"{int(width)}x{int(height)}"
        elif resolution and "x" in str(resolution):
            resolution_text = str(resolution)
        if motion_level == "fast_motion":
            motion_level_index = "high"
        elif motion_level == "moderate_motion":
            motion_level_index = "moderate"
        else:
            motion_level_index = "low"
        tech_meta_default = {
            "orientation": orientation_binary,
            "resolution": resolution_text,
            "duration_sec": round(float(duration_f or 0.0), 3),
            "motion_level": motion_level_index,
        }
        landmark_gate = self._landmark_gate(evidence_payload)
        draft_index_layers = self._draft_index_layers_from_structured(
            structured_tags=structured_tag_schema,
            evidence=evidence_payload,
            forced_landmarks=landmark_gate,
            tech_meta_default=tech_meta_default,
        )
        llm_index_layers = self._llm_refine_index_layers(
            evidence=evidence_payload,
            draft_layers=draft_index_layers,
            landmark_gate=landmark_gate,
        )
        index_layers = self._normalize_index_layers(
            raw_layers=llm_index_layers if llm_index_layers else draft_index_layers,
            evidence=evidence_payload,
            forced_landmarks=landmark_gate,
            tech_meta_default=tech_meta_default,
        )
        structured_terms = self._flatten_structured_tag_terms(structured_tag_schema)
        index_layer_terms = self._flatten_index_layer_terms(index_layers)
        search_facets = {}
        tags_node = structured_tag_schema.get("tags", {}) if isinstance(structured_tag_schema, dict) else {}
        for cat in TAG_CATEGORIES:
            node = tags_node.get(cat, {}) if isinstance(tags_node, dict) else {}
            zh_list = node.get("zh", []) if isinstance(node, dict) else []
            en_list = node.get("en", []) if isinstance(node, dict) else []
            facets = []
            if isinstance(zh_list, list):
                facets.extend([str(x).strip() for x in zh_list if str(x).strip()])
            if isinstance(en_list, list):
                facets.extend([str(x).strip().lower() for x in en_list if str(x).strip()])
            search_facets[cat] = self._dedupe_list(facets)[:18]
        core_layer = index_layers.get("core_search_tags", {}) if isinstance(index_layers, dict) else {}
        secondary_layer = index_layers.get("secondary_tags", {}) if isinstance(index_layers, dict) else {}
        core_facets = []
        secondary_facets = []
        if isinstance(core_layer, dict):
            core_facets.extend(core_layer.get("zh", []) if isinstance(core_layer.get("zh"), list) else [])
            core_facets.extend(core_layer.get("en", []) if isinstance(core_layer.get("en"), list) else [])
        if isinstance(secondary_layer, dict):
            secondary_facets.extend(secondary_layer.get("zh", []) if isinstance(secondary_layer.get("zh"), list) else [])
            secondary_facets.extend(secondary_layer.get("en", []) if isinstance(secondary_layer.get("en"), list) else [])
        search_facets["core_search_tags"] = self._dedupe_list([str(x).strip() for x in core_facets if str(x).strip()])[:24]
        search_facets["secondary_tags"] = self._dedupe_list([str(x).strip() for x in secondary_facets if str(x).strip()])[:36]

        searchable_tags = [v for v in (tag_values + metadata_terms) if len(v) <= 72]
        search_keywords = self._dedupe_list(
            topics
            + label_keywords
            + structured_terms
            + index_layer_terms
            + [
                scene_text,
                mood_text,
                filename_text,
                primary_subject,
                location_type,
                camera_platform,
                aspect_ratio_bucket,
                stability_level,
                lighting_condition,
                dominant_color,
                brightness_level,
                saturation_level,
                motion_level,
                texture_complexity,
                face_presence_level,
            ]
            + filename_tokens
            + path_tokens
            + searchable_tags
        )
        semantic_text = " | ".join(search_keywords)

        semantic = {
            "scene_description": scene_text,
            "mood": mood_text,
            "primary_subject": primary_subject,
            "secondary_subjects": self._dedupe_list(object_list),
            "content_type": content_type,
            "activity": activity,
            "action_intensity": action_intensity,
            "setting": setting,
            "location_type": location_type,
            "time_of_day": time_of_day,
            "season": season,
            "weather": weather,
            "camera_movement": camera_movement,
            "camera_platform": camera_platform,
            "shot_type": shot_type,
            "framing": framing,
            "perspective": perspective,
            "visual_style": visual_style,
            "color_tone": color_tone,
            "lighting_condition": lighting_condition,
            "narrative_role": narrative_role,
            "clip_purpose": clip_purpose,
            "emotion_intensity": emotion_intensity,
            "people_presence": people_presence,
            "quality_tier": quality_tier,
            "duration_bucket": duration_bucket,
            "aspect_ratio_bucket": aspect_ratio_bucket,
            "orientation": orientation,
            "stability_level": stability_level,
            "dominant_color": dominant_color,
            "brightness_level": brightness_level,
            "saturation_level": saturation_level,
            "motion_level": motion_level,
            "texture_complexity": texture_complexity,
            "face_presence_level": face_presence_level,
            "use_cases": use_cases,
            "audience_intent": audience_intent,
            "business_tags": business_tags,
            "topics": topics,
            "structured_tags": structured_tag_schema,
            "index_layers": index_layers,
            "search_facets": search_facets,
            "search_keywords": search_keywords,
        }

        # v0.6: Add _meta for version tracking
        semantic["_meta"] = {
            "semantic_version": SEMANTIC_SCHEMA_VERSION,
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "extraction_time": self._now(),
            "tag_library_version": "chatgpt_v1_2124",
        }
        # Model/prompt version injected by _llm_structured_tags if LLM was used
        if structured_tag_schema and isinstance(structured_tag_schema, dict):
            semantic["_meta"]["model_version"] = structured_tag_schema.get(
                "_model", "heuristic_only"
            )
            semantic["_meta"]["prompt_version"] = "v3.0_25cat"

        return {
            "semantic": semantic,
            "semantic_text": semantic_text,
            "search_keywords": search_keywords,
        }

    def _semantic_from_saved_analysis(self, path: Path, analysis: Dict, fallback_mood: str, fallback_scene: str, fallback_objects: List[str], quality_score):
        scene_text = fallback_scene
        mood_text = fallback_mood
        objects = list(fallback_objects or [])
        if isinstance(analysis, dict):
            local = analysis.get("local_analysis", {})
            scene = local.get("scene", {}) if isinstance(local, dict) else {}
            obj = local.get("objects", {}) if isinstance(local, dict) else {}
            scene_text = scene.get("description") or scene_text
            mood_text = scene.get("mood") or mood_text
            detected = obj.get("detected_objects") if isinstance(obj, dict) else None
            if isinstance(detected, list) and detected:
                objects = detected
        return self._build_semantic_bundle(path, analysis or {}, scene_text, mood_text, objects, quality_score)

    def _analyze_video(self, path: Path) -> Dict:
        _av_t0 = time.perf_counter()
        toolkit = self._toolkit_instance()
        analysis = toolkit.analyze_single_video(path)

        metadata = analysis.get("metadata", {})
        local = analysis.get("local_analysis", {})
        technical = local.get("technical", {})
        scene = local.get("scene", {})
        objects = local.get("objects", {})

        duration = None
        try:
            duration = float(metadata.get("duration")) if metadata.get("duration") else None
        except Exception:
            duration = None

        size_bytes = None
        try:
            size_bytes = int(metadata.get("size")) if metadata.get("size") else path.stat().st_size
        except Exception:
            size_bytes = None

        resolution = technical.get("resolution")
        width, height = self._parse_resolution(resolution)
        if width is None or height is None:
            streams = metadata.get("video_streams") or []
            if streams:
                try:
                    width = int(streams[0].get("width")) if streams[0].get("width") else None
                    height = int(streams[0].get("height")) if streams[0].get("height") else None
                    if width and height:
                        resolution = f"{width}x{height}"
                except Exception:
                    width, height = None, None

        streams = metadata.get("video_streams") or []
        fps_raw = technical.get("fps")
        codec = technical.get("codec")
        if streams:
            fps_raw = fps_raw or streams[0].get("fps")
            codec = codec or streams[0].get("codec")

        scene_description = scene.get("description")
        mood_text = scene.get("mood")
        detected_objects = objects.get("detected_objects") or []
        generic_scene = not str(scene_description or "").strip() or "mixed environment scene" in str(scene_description).lower()
        generic_objects = len(detected_objects) <= 3
        vision_enrich = {}
        if generic_scene or generic_objects:
            vision_enrich = self._vision_enrich_tags(path)
            vision_scene = str(vision_enrich.get("scene", "") or "").strip()
            vision_keywords = vision_enrich.get("keywords") or []
            if not isinstance(vision_keywords, list):
                vision_keywords = []
            landmarks = vision_enrich.get("landmarks") or []
            if not isinstance(landmarks, list):
                landmarks = []
            arch_styles = vision_enrich.get("architecture_style") or []
            if not isinstance(arch_styles, list):
                arch_styles = []

            merged_terms = [
                str(x).strip()
                for x in (vision_keywords + landmarks + arch_styles)
                if str(x).strip()
            ]
            if vision_scene:
                if scene_description:
                    scene_description = f"{scene_description}; {vision_scene}"
                else:
                    scene_description = vision_scene
            if merged_terms:
                detected_objects = self._dedupe_list([str(x) for x in detected_objects] + merged_terms[:14])
            if vision_enrich:
                analysis["vision_enrich"] = {
                    "scene": vision_scene,
                    "keywords": merged_terms[:16],
                }
        quality_score = technical.get("overall_quality")
        semantic_bundle = self._build_semantic_bundle(
            path=path,
            analysis=analysis,
            scene_description=scene_description,
            mood=mood_text,
            objects=detected_objects,
            quality_score=quality_score,
        )

        # GPS extraction from metadata
        gps = metadata.get("gps")
        gps_latitude = gps["latitude"] if isinstance(gps, dict) and gps.get("latitude") is not None else None
        gps_longitude = gps["longitude"] if isinstance(gps, dict) and gps.get("longitude") is not None else None

        # ---- 综合可用性评分 ----
        _usability_result = None
        if _score_asset is not None:
            try:
                _vs = toolkit._get_visual_stats(path) if hasattr(toolkit, '_get_visual_stats') else {}
                _ai = analysis.get("audio_quality") or None
                if isinstance(_ai, dict) and not _ai:
                    _ai = None
                _usability_result = _score_asset(
                    asset_row={
                        "uid": sha256 if 'sha256' in dir() else "",
                        "duration": duration,
                        "width": width,
                        "height": height,
                        "fps": self._parse_fps(fps_raw),
                        "codec": codec,
                        "quality_score": quality_score,
                        "phash": None,
                    },
                    visual_stats=_vs,
                    audio_info=_ai,
                    analysis_json={
                        "asr_text": analysis.get("transcription", {}).get("text", ""),
                        "ocr_text": "",
                        "objects": detected_objects,
                        "semantic": semantic_bundle.get("semantic", {}),
                        "gps": {"lat": gps_latitude, "lon": gps_longitude} if gps_latitude else None,
                        "tags": [],
                    },
                    tag_results=[],
                    library_stats=None,
                )
            except Exception as e:
                _gml_logger.warning("usability scoring failed for %s: %s", path.name, e)
                _usability_result = None

        _av_elapsed = (time.perf_counter() - _av_t0) * 1000
        _gml_logger.info("[perf] analyze_video: %.1fms path=%s", _av_elapsed, path.name)
        try:
            from modules.app_api.services.perf_log import record as _perf_rec
            _perf_rec("analyze_video", _av_elapsed, {"path": str(path.name)})
        except Exception:
            pass

        _result = {
            "analysis": analysis,
            "duration": duration,
            "size_bytes": size_bytes,
            "resolution": resolution,
            "width": width,
            "height": height,
            "fps": self._parse_fps(fps_raw),
            "codec": codec,
            "quality_score": quality_score,
            "scene_description": scene_description,
            "mood": mood_text,
            "objects": detected_objects,
            "semantic_json": semantic_bundle["semantic"],
            "semantic_text": semantic_bundle["semantic_text"],
            "search_keywords": semantic_bundle["search_keywords"],
            "semantic_version": SEMANTIC_SCHEMA_VERSION,
            "gps_latitude": gps_latitude,
            "gps_longitude": gps_longitude,
        }
        if _usability_result:
            _result["quality_assessment"] = _usability_result
        return _result

    def _analyze_image(self, path: Path) -> Dict:
        if cv2 is None or np is None:
            raise RuntimeError("缺少图像分析依赖（opencv-python / numpy）")

        img = cv2.imread(str(path))
        if img is None:
            raise RuntimeError(f"无法读取图片: {path}")

        height, width = img.shape[:2]
        resolution = f"{int(width)}x{int(height)}" if width and height else ""

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        brightness = float(np.mean(gray) / 255.0)
        saturation = float(np.mean(hsv[:, :, 1]) / 255.0)
        edges = cv2.Canny(gray, 70, 160)
        edge_density = float(np.mean(edges > 0))

        b_mean = float(np.mean(img[:, :, 0]))
        g_mean = float(np.mean(img[:, :, 1]))
        r_mean = float(np.mean(img[:, :, 2]))
        rgb_sum = max(r_mean + g_mean + b_mean, 1e-6)
        red_ratio = r_mean / rgb_sum
        green_ratio = g_mean / rgb_sum
        blue_ratio = b_mean / rgb_sum

        # 静态图片没有真实 motion/face score，保留 0 以避免误导。
        motion_score = 0.0
        face_ratio = 0.0

        try:
            size_bytes = int(path.stat().st_size)
        except Exception:
            size_bytes = None

        file_mtime_iso = ""
        try:
            file_mtime_iso = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            file_mtime_iso = ""

        orientation, _ = self._infer_orientation(width, height)
        megapixels = float(width * height) / 1_000_000.0 if width and height else 0.0
        if megapixels >= 12:
            quality_score = 0.94
        elif megapixels >= 6:
            quality_score = 0.88
        elif megapixels >= 3:
            quality_score = 0.80
        else:
            quality_score = 0.72

        scene_parts: List[str] = []
        if orientation == "portrait":
            scene_parts.append("portrait photo")
        elif orientation == "landscape":
            scene_parts.append("landscape photo")
        if brightness >= 0.72:
            scene_parts.append("bright daylight")
        elif brightness <= 0.34:
            scene_parts.append("low light")
        if saturation >= 0.50:
            scene_parts.append("vivid color")
        elif saturation <= 0.25:
            scene_parts.append("muted color")
        scene_description = "; ".join(scene_parts) if scene_parts else "still image"

        if brightness >= 0.72 and saturation >= 0.45:
            mood_text = "bright energetic"
        elif brightness <= 0.34:
            mood_text = "moody calm"
        else:
            mood_text = "natural"

        objects: List[str] = []
        filename_tokens = self._split_filename_tokens(path.stem)
        for token in filename_tokens:
            key = self._normalize_tag_to_key(token)
            if not key:
                continue
            entry = self._entry_from_key(key)
            if not entry:
                continue
            if entry.get("en"):
                objects.append(entry["en"])
            if entry.get("zh"):
                objects.append(entry["zh"])

        vision_enrich = self._vision_enrich_tags(path)
        vision_scene = str(vision_enrich.get("scene", "") or "").strip()
        vision_keywords = vision_enrich.get("keywords") or []
        landmarks = vision_enrich.get("landmarks") or []
        arch_styles = vision_enrich.get("architecture_style") or []
        if not isinstance(vision_keywords, list):
            vision_keywords = []
        if not isinstance(landmarks, list):
            landmarks = []
        if not isinstance(arch_styles, list):
            arch_styles = []
        if vision_scene:
            scene_description = f"{scene_description}; {vision_scene}" if scene_description else vision_scene
        objects = self._dedupe_list(
            objects + [str(x).strip() for x in (vision_keywords + landmarks + arch_styles) if str(x).strip()]
        )

        if not objects:
            if orientation == "portrait":
                objects.extend(["person", "portrait"])
            else:
                objects.extend(["landscape", "city"])

        analysis = {
            "metadata": {
                "duration": "0",
                "size": str(size_bytes or 0),
                "video_streams": [],
                "audio_streams": [],
                "tags": {
                    "creation_time": file_mtime_iso,
                    "file_name": path.name,
                    "parent_folder": path.parent.name,
                    "media_type": "image",
                },
            },
            "local_analysis": {
                "technical": {
                    "resolution": resolution,
                    "fps": None,
                    "codec": "image",
                    "overall_quality": quality_score,
                },
                "scene": {
                    "description": scene_description,
                    "mood": mood_text,
                    "method": "image_heuristic",
                    "visual_features": {
                        "brightness": brightness,
                        "saturation": saturation,
                        "edge_density": edge_density,
                        "motion_score": motion_score,
                        "face_ratio": face_ratio,
                        "red_ratio": red_ratio,
                        "green_ratio": green_ratio,
                        "blue_ratio": blue_ratio,
                    },
                },
                "objects": {
                    "detected_objects": objects,
                    "confidence": 0.66 if vision_enrich else 0.52,
                    "method": "image_vision_enrich" if vision_enrich else "image_heuristic",
                },
            },
            "recommendations": [],
        }
        if vision_enrich:
            analysis["vision_enrich"] = {
                "scene": vision_scene,
                "keywords": self._dedupe_list(
                    [str(x).strip() for x in (vision_keywords + landmarks + arch_styles) if str(x).strip()]
                )[:16],
            }

        semantic_bundle = self._build_semantic_bundle(
            path=path,
            analysis=analysis,
            scene_description=scene_description,
            mood=mood_text,
            objects=objects,
            quality_score=quality_score,
        )

        return {
            "analysis": analysis,
            "duration": None,
            "size_bytes": size_bytes,
            "resolution": resolution,
            "width": int(width) if width else None,
            "height": int(height) if height else None,
            "fps": None,
            "codec": "image",
            "quality_score": quality_score,
            "scene_description": scene_description,
            "mood": mood_text,
            "objects": objects,
            "semantic_json": semantic_bundle["semantic"],
            "semantic_text": semantic_bundle["semantic_text"],
            "search_keywords": semantic_bundle["search_keywords"],
            "semantic_version": SEMANTIC_SCHEMA_VERSION,
        }

    @staticmethod
    def _choose_primary_path(current_path: Optional[str], current_source: Optional[str], new_path: str, new_source: str) -> str:
        # Keep local path as primary when available; otherwise latest wins.
        if current_path and current_source == "local" and new_source != "local" and Path(current_path).exists():
            return current_path
        return new_path

    def _upsert_location(self, conn: sqlite3.Connection, uid: str, path: str, source_type: str, source_ref: Optional[str]):
        now = self._now()
        conn.execute(
            """
            INSERT INTO asset_locations (uid, path, source_type, source_ref, is_available, last_seen_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(path) DO UPDATE SET
                uid=excluded.uid,
                source_type=excluded.source_type,
                source_ref=excluded.source_ref,
                is_available=1,
                last_seen_at=excluded.last_seen_at
            """,
            (uid, path, source_type, source_ref, now),
        )

    def _find_similar_by_phash(self, conn: sqlite3.Connection, phash: Optional[str], threshold: int = 5) -> tuple[Optional[str], Optional[int]]:
        if not phash:
            return None, None
        rows = conn.execute(
            "SELECT uid, phash FROM assets WHERE phash IS NOT NULL AND phash != ''"
        ).fetchall()
        best_uid = None
        best_dist = None
        for row in rows:
            candidate = row["phash"]
            dist = None
            if VideoHasher is not None:
                try:
                    dist = VideoHasher.hamming_distance(phash, candidate)
                except Exception:
                    dist = None
            if dist is None:
                dist = self._phash_distance(phash, candidate)
            if dist is None:
                continue
            if dist <= threshold and (best_dist is None or dist < best_dist):
                best_uid = row["uid"]
                best_dist = dist
        return best_uid, best_dist

    def _ingest_video_file(self, conn: sqlite3.Connection, path: Path, source_type: str, source_ref: Optional[str]) -> Dict:
        sha256 = self._compute_sha256(path)
        now = self._now()

        existing = conn.execute(
            """
            SELECT uid, primary_path, source_type, phash, resolution, duration,
                   mood, scene_description, objects_json, quality_score,
                   analysis_json, semantic_json, semantic_text, keywords_json, semantic_version
            FROM assets
            WHERE sha256 = ?
            """,
            (sha256,),
        ).fetchone()

        uid = existing["uid"] if existing else sha256
        prev_path = existing["primary_path"] if existing else None
        prev_source = existing["source_type"] if existing else None
        primary_path = self._choose_primary_path(prev_path, prev_source, str(path), source_type)

        if existing:
            asset_source = prev_source if (prev_source == "local" and source_type != "local") else source_type
            semantic_json = self._safe_json_loads(existing["semantic_json"], {})
            search_keywords = self._safe_json_loads(existing["keywords_json"], [])
            semantic_text = existing["semantic_text"] or ""
            semantic_version = existing["semantic_version"]
            analysis_from_db = self._safe_json_loads(existing["analysis_json"], {})
            fallback_objects = self._safe_json_loads(existing["objects_json"], [])
            refreshed_bundle = None

            needs_semantic_upgrade = (
                semantic_version != SEMANTIC_SCHEMA_VERSION
                or not isinstance(semantic_json, dict)
                or not semantic_json
            )

            scene_legacy = str(existing["scene_description"] or "").strip().lower()
            mood_legacy = str(existing["mood"] or "").strip().lower()
            local = analysis_from_db.get("local_analysis", {}) if isinstance(analysis_from_db, dict) else {}
            scene_method = str((local.get("scene", {}) or {}).get("method", "")).lower() if isinstance(local, dict) else ""
            obj_method = str((local.get("objects", {}) or {}).get("method", "")).lower() if isinstance(local, dict) else ""
            looks_legacy = (
                "模拟" in scene_method
                or "simulation" in scene_method
                or "模拟" in obj_method
                or "simulation" in obj_method
                or scene_legacy in {"scenic landscape or urban environment", ""}
                or mood_legacy in {"varied", ""}
            )
            needs_refresh_analysis = needs_semantic_upgrade or looks_legacy

            if needs_refresh_analysis and path.exists():
                try:
                    refreshed_bundle = self._analyze_video(path)
                    semantic_json = refreshed_bundle["semantic_json"]
                    semantic_text = refreshed_bundle["semantic_text"]
                    search_keywords = refreshed_bundle["search_keywords"]
                    semantic_version = refreshed_bundle["semantic_version"]
                except Exception:
                    refreshed_bundle = None

            if refreshed_bundle is None and needs_semantic_upgrade:
                semantic_bundle = self._semantic_from_saved_analysis(
                    path=path,
                    analysis=analysis_from_db,
                    fallback_mood=existing["mood"] or "",
                    fallback_scene=existing["scene_description"] or "",
                    fallback_objects=fallback_objects if isinstance(fallback_objects, list) else [],
                    quality_score=existing["quality_score"],
                )
                semantic_json = semantic_bundle["semantic"]
                semantic_text = semantic_bundle["semantic_text"]
                search_keywords = semantic_bundle["search_keywords"]
                semantic_version = SEMANTIC_SCHEMA_VERSION

            if refreshed_bundle is not None:
                # Extract usability results from refreshed analysis
                _ref_usability = refreshed_bundle.get("quality_assessment")
                _ref_u_score = _ref_usability["usability_score"] if _ref_usability else None
                _ref_u_tier = _ref_usability["usability_tier"] if _ref_usability else None
                _ref_u_mtype = _ref_usability["material_type"] if _ref_usability else None
                _ref_u_trash = _ref_usability["trash_evaluation"]["trash_level"] if _ref_usability else "none"

                conn.execute(
                    """
                    UPDATE assets
                    SET filename=?, primary_path=?, source_type=?,
                        duration=?, size_bytes=?, resolution=?, width=?, height=?, fps=?, codec=?,
                        quality_score=?, scene_description=?, mood=?, objects_json=?,
                        analysis_json=?, semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?,
                        gps_latitude=?, gps_longitude=?,
                        usability_score=?, usability_tier=?, material_type=?, trash_level=?,
                        updated_at=?
                    WHERE uid=?
                    """,
                    (
                        path.name,
                        primary_path,
                        asset_source,
                        refreshed_bundle["duration"],
                        refreshed_bundle["size_bytes"],
                        refreshed_bundle["resolution"],
                        refreshed_bundle["width"],
                        refreshed_bundle["height"],
                        refreshed_bundle["fps"],
                        refreshed_bundle["codec"],
                        refreshed_bundle["quality_score"],
                        refreshed_bundle["scene_description"],
                        refreshed_bundle["mood"],
                        json.dumps(refreshed_bundle["objects"], ensure_ascii=False),
                        json.dumps(refreshed_bundle["analysis"], ensure_ascii=False),
                        json.dumps(semantic_json, ensure_ascii=False),
                        semantic_text,
                        json.dumps(search_keywords, ensure_ascii=False),
                        semantic_version,
                        refreshed_bundle.get("gps_latitude"),
                        refreshed_bundle.get("gps_longitude"),
                        _ref_u_score,
                        _ref_u_tier,
                        _ref_u_mtype,
                        _ref_u_trash,
                        now,
                        uid,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE assets
                    SET filename=?, primary_path=?, source_type=?,
                        semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?,
                        updated_at=?
                    WHERE uid=?
                    """,
                    (
                        path.name,
                        primary_path,
                        asset_source,
                        json.dumps(semantic_json, ensure_ascii=False),
                        semantic_text,
                        json.dumps(search_keywords, ensure_ascii=False),
                        semantic_version,
                        now,
                        uid,
                    ),
                )
            self._upsert_location(conn, uid, str(path), source_type, source_ref)
            self._upsert_embedding_for_asset(
                conn=conn,
                uid=uid,
                filename=path.name,
                semantic_text=semantic_text,
                keywords_json=search_keywords,
                semantic_json=semantic_json,
            )
            try:
                sj = semantic_json if isinstance(semantic_json, dict) else self._safe_json_loads(semantic_json, {})
                self._persist_evidence_and_tags(uid, sj, conn)
            except Exception:
                pass
            return {
                "uid": uid,
                "filename": path.name,
                "path": str(path),
                "sha256": sha256,
                "phash": existing["phash"],
                "dedup_hit": True,
                "similar_uid": uid if existing["phash"] else None,
                "phash_distance": 0 if existing["phash"] else None,
                "resolution": refreshed_bundle["resolution"] if refreshed_bundle else existing["resolution"],
                "duration": refreshed_bundle["duration"] if refreshed_bundle else existing["duration"],
                "semantic_dimensions_count": len((semantic_json or {}).keys()) if isinstance(semantic_json, dict) else 0,
                "semantic_refreshed": bool(refreshed_bundle is not None),
            }

        analysis_bundle = self._analyze_video(path)
        phash = self._compute_phash(path)
        similar_uid, similar_distance = self._find_similar_by_phash(conn, phash)

        # v0.7 fingerprint computation
        content_fp = self._compute_content_fingerprint(path, "video")
        thumb_hash = self._compute_thumbnail_hash(path, "video")

        created_at = now

        # Extract usability scoring results from analysis_bundle
        _usability = analysis_bundle.get("quality_assessment")
        _u_score = _usability["usability_score"] if _usability else None
        _u_tier = _usability["usability_tier"] if _usability else None
        _u_mtype = _usability["material_type"] if _usability else None
        _u_trash = _usability["trash_evaluation"]["trash_level"] if _usability else "none"

        conn.execute(
            """
            INSERT INTO assets (
                uid, sha256, phash, filename, primary_path, source_type,
                duration, size_bytes, resolution, width, height, fps, codec,
                quality_score, scene_description, mood, objects_json,
                analysis_json, semantic_json, semantic_text, keywords_json, semantic_version,
                gps_latitude, gps_longitude,
                content_fingerprint, thumbnail_hash, fingerprint_version,
                usability_score, usability_tier, material_type, trash_level,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                sha256=excluded.sha256,
                phash=COALESCE(excluded.phash, assets.phash),
                filename=excluded.filename,
                primary_path=excluded.primary_path,
                source_type=excluded.source_type,
                duration=excluded.duration,
                size_bytes=excluded.size_bytes,
                resolution=excluded.resolution,
                width=excluded.width,
                height=excluded.height,
                fps=excluded.fps,
                codec=excluded.codec,
                quality_score=excluded.quality_score,
                scene_description=excluded.scene_description,
                mood=excluded.mood,
                objects_json=excluded.objects_json,
                analysis_json=excluded.analysis_json,
                semantic_json=excluded.semantic_json,
                semantic_text=excluded.semantic_text,
                keywords_json=excluded.keywords_json,
                semantic_version=excluded.semantic_version,
                gps_latitude=excluded.gps_latitude,
                gps_longitude=excluded.gps_longitude,
                content_fingerprint=COALESCE(excluded.content_fingerprint, assets.content_fingerprint),
                thumbnail_hash=COALESCE(excluded.thumbnail_hash, assets.thumbnail_hash),
                fingerprint_version=excluded.fingerprint_version,
                usability_score=excluded.usability_score,
                usability_tier=excluded.usability_tier,
                material_type=excluded.material_type,
                trash_level=excluded.trash_level,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                sha256,
                phash,
                path.name,
                primary_path,
                source_type,
                analysis_bundle["duration"],
                analysis_bundle["size_bytes"],
                analysis_bundle["resolution"],
                analysis_bundle["width"],
                analysis_bundle["height"],
                analysis_bundle["fps"],
                analysis_bundle["codec"],
                analysis_bundle["quality_score"],
                analysis_bundle["scene_description"],
                analysis_bundle["mood"],
                json.dumps(analysis_bundle["objects"], ensure_ascii=False),
                json.dumps(analysis_bundle["analysis"], ensure_ascii=False),
                json.dumps(analysis_bundle["semantic_json"], ensure_ascii=False),
                analysis_bundle["semantic_text"],
                json.dumps(analysis_bundle["search_keywords"], ensure_ascii=False),
                analysis_bundle["semantic_version"],
                analysis_bundle.get("gps_latitude"),
                analysis_bundle.get("gps_longitude"),
                content_fp,
                thumb_hash,
                self.FINGERPRINT_VERSION,
                _u_score,
                _u_tier,
                _u_mtype,
                _u_trash,
                created_at,
                now,
            ),
        )

        self._upsert_location(conn, uid, str(path), source_type, source_ref)
        self._upsert_embedding_for_asset(
            conn=conn,
            uid=uid,
            filename=path.name,
            semantic_text=analysis_bundle["semantic_text"],
            keywords_json=analysis_bundle["search_keywords"],
            semantic_json=analysis_bundle["semantic_json"],
        )
        try:
            self._persist_evidence_and_tags(uid, analysis_bundle["semantic_json"], conn)
        except Exception:
            pass
        self._generate_thumbnail(uid, path, "video")

        return {
            "uid": uid,
            "filename": path.name,
            "path": str(path),
            "sha256": sha256,
            "phash": phash,
            "content_fingerprint": content_fp,
            "thumbnail_hash": thumb_hash,
            "dedup_hit": bool(existing),
            "similar_uid": similar_uid,
            "phash_distance": similar_distance,
            "resolution": analysis_bundle["resolution"],
            "duration": analysis_bundle["duration"],
            "semantic_dimensions_count": len((analysis_bundle.get("semantic_json") or {}).keys()),
        }

    def _ingest_image_file(self, conn: sqlite3.Connection, path: Path, source_type: str, source_ref: Optional[str]) -> Dict:
        sha256 = self._compute_sha256(path)
        now = self._now()

        existing = conn.execute(
            """
            SELECT uid, primary_path, source_type, phash, resolution, duration,
                   mood, scene_description, objects_json, quality_score,
                   analysis_json, semantic_json, semantic_text, keywords_json, semantic_version
            FROM assets
            WHERE sha256 = ?
            """,
            (sha256,),
        ).fetchone()

        uid = existing["uid"] if existing else sha256
        prev_path = existing["primary_path"] if existing else None
        prev_source = existing["source_type"] if existing else None
        primary_path = self._choose_primary_path(prev_path, prev_source, str(path), source_type)

        if existing:
            asset_source = prev_source if (prev_source == "local" and source_type != "local") else source_type
            semantic_json = self._safe_json_loads(existing["semantic_json"], {})
            search_keywords = self._safe_json_loads(existing["keywords_json"], [])
            semantic_text = existing["semantic_text"] or ""
            semantic_version = existing["semantic_version"]
            analysis_from_db = self._safe_json_loads(existing["analysis_json"], {})
            fallback_objects = self._safe_json_loads(existing["objects_json"], [])
            refreshed_bundle = None

            needs_semantic_upgrade = (
                semantic_version != SEMANTIC_SCHEMA_VERSION
                or not isinstance(semantic_json, dict)
                or not semantic_json
            )
            needs_refresh_analysis = needs_semantic_upgrade

            if needs_refresh_analysis and path.exists():
                try:
                    refreshed_bundle = self._analyze_image(path)
                    semantic_json = refreshed_bundle["semantic_json"]
                    semantic_text = refreshed_bundle["semantic_text"]
                    search_keywords = refreshed_bundle["search_keywords"]
                    semantic_version = refreshed_bundle["semantic_version"]
                except Exception:
                    refreshed_bundle = None

            if refreshed_bundle is None and needs_semantic_upgrade:
                semantic_bundle = self._semantic_from_saved_analysis(
                    path=path,
                    analysis=analysis_from_db,
                    fallback_mood=existing["mood"] or "",
                    fallback_scene=existing["scene_description"] or "",
                    fallback_objects=fallback_objects if isinstance(fallback_objects, list) else [],
                    quality_score=existing["quality_score"],
                )
                semantic_json = semantic_bundle["semantic"]
                semantic_text = semantic_bundle["semantic_text"]
                search_keywords = semantic_bundle["search_keywords"]
                semantic_version = SEMANTIC_SCHEMA_VERSION

            if refreshed_bundle is not None:
                conn.execute(
                    """
                    UPDATE assets
                    SET filename=?, primary_path=?, source_type=?,
                        duration=?, size_bytes=?, resolution=?, width=?, height=?, fps=?, codec=?,
                        quality_score=?, scene_description=?, mood=?, objects_json=?,
                        analysis_json=?, semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?,
                        gps_latitude=?, gps_longitude=?,
                        updated_at=?
                    WHERE uid=?
                    """,
                    (
                        path.name,
                        primary_path,
                        asset_source,
                        refreshed_bundle["duration"],
                        refreshed_bundle["size_bytes"],
                        refreshed_bundle["resolution"],
                        refreshed_bundle["width"],
                        refreshed_bundle["height"],
                        refreshed_bundle["fps"],
                        refreshed_bundle["codec"],
                        refreshed_bundle["quality_score"],
                        refreshed_bundle["scene_description"],
                        refreshed_bundle["mood"],
                        json.dumps(refreshed_bundle["objects"], ensure_ascii=False),
                        json.dumps(refreshed_bundle["analysis"], ensure_ascii=False),
                        json.dumps(semantic_json, ensure_ascii=False),
                        semantic_text,
                        json.dumps(search_keywords, ensure_ascii=False),
                        semantic_version,
                        refreshed_bundle.get("gps_latitude"),
                        refreshed_bundle.get("gps_longitude"),
                        now,
                        uid,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE assets
                    SET filename=?, primary_path=?, source_type=?,
                        semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?,
                        updated_at=?
                    WHERE uid=?
                    """,
                    (
                        path.name,
                        primary_path,
                        asset_source,
                        json.dumps(semantic_json, ensure_ascii=False),
                        semantic_text,
                        json.dumps(search_keywords, ensure_ascii=False),
                        semantic_version,
                        now,
                        uid,
                    ),
                )
            self._upsert_location(conn, uid, str(path), source_type, source_ref)
            self._upsert_embedding_for_asset(
                conn=conn,
                uid=uid,
                filename=path.name,
                semantic_text=semantic_text,
                keywords_json=search_keywords,
                semantic_json=semantic_json,
            )
            try:
                sj = semantic_json if isinstance(semantic_json, dict) else self._safe_json_loads(semantic_json, {})
                self._persist_evidence_and_tags(uid, sj, conn)
            except Exception:
                pass
            return {
                "uid": uid,
                "filename": path.name,
                "path": str(path),
                "sha256": sha256,
                "phash": existing["phash"],
                "dedup_hit": True,
                "similar_uid": uid if existing["phash"] else None,
                "phash_distance": 0 if existing["phash"] else None,
                "resolution": refreshed_bundle["resolution"] if refreshed_bundle else existing["resolution"],
                "duration": refreshed_bundle["duration"] if refreshed_bundle else existing["duration"],
                "semantic_dimensions_count": len((semantic_json or {}).keys()) if isinstance(semantic_json, dict) else 0,
                "semantic_refreshed": bool(refreshed_bundle is not None),
            }

        analysis_bundle = self._analyze_image(path)
        phash = self._compute_image_phash(path)
        similar_uid, similar_distance = self._find_similar_by_phash(conn, phash)

        # v0.7 fingerprint computation (image)
        content_fp = self._compute_content_fingerprint(path, "image")
        thumb_hash = self._compute_thumbnail_hash(path, "image")

        created_at = now

        conn.execute(
            """
            INSERT INTO assets (
                uid, sha256, phash, filename, primary_path, source_type,
                duration, size_bytes, resolution, width, height, fps, codec,
                quality_score, scene_description, mood, objects_json,
                analysis_json, semantic_json, semantic_text, keywords_json, semantic_version,
                gps_latitude, gps_longitude,
                content_fingerprint, thumbnail_hash, fingerprint_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                sha256=excluded.sha256,
                phash=COALESCE(excluded.phash, assets.phash),
                filename=excluded.filename,
                primary_path=excluded.primary_path,
                source_type=excluded.source_type,
                duration=excluded.duration,
                size_bytes=excluded.size_bytes,
                resolution=excluded.resolution,
                width=excluded.width,
                height=excluded.height,
                fps=excluded.fps,
                codec=excluded.codec,
                quality_score=excluded.quality_score,
                scene_description=excluded.scene_description,
                mood=excluded.mood,
                objects_json=excluded.objects_json,
                analysis_json=excluded.analysis_json,
                semantic_json=excluded.semantic_json,
                semantic_text=excluded.semantic_text,
                keywords_json=excluded.keywords_json,
                semantic_version=excluded.semantic_version,
                gps_latitude=excluded.gps_latitude,
                gps_longitude=excluded.gps_longitude,
                content_fingerprint=COALESCE(excluded.content_fingerprint, assets.content_fingerprint),
                thumbnail_hash=COALESCE(excluded.thumbnail_hash, assets.thumbnail_hash),
                fingerprint_version=excluded.fingerprint_version,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                sha256,
                phash,
                path.name,
                primary_path,
                source_type,
                analysis_bundle["duration"],
                analysis_bundle["size_bytes"],
                analysis_bundle["resolution"],
                analysis_bundle["width"],
                analysis_bundle["height"],
                analysis_bundle["fps"],
                analysis_bundle["codec"],
                analysis_bundle["quality_score"],
                analysis_bundle["scene_description"],
                analysis_bundle["mood"],
                json.dumps(analysis_bundle["objects"], ensure_ascii=False),
                json.dumps(analysis_bundle["analysis"], ensure_ascii=False),
                json.dumps(analysis_bundle["semantic_json"], ensure_ascii=False),
                analysis_bundle["semantic_text"],
                json.dumps(analysis_bundle["search_keywords"], ensure_ascii=False),
                analysis_bundle["semantic_version"],
                analysis_bundle.get("gps_latitude"),
                analysis_bundle.get("gps_longitude"),
                content_fp,
                thumb_hash,
                self.FINGERPRINT_VERSION,
                created_at,
                now,
            ),
        )

        self._upsert_location(conn, uid, str(path), source_type, source_ref)
        self._upsert_embedding_for_asset(
            conn=conn,
            uid=uid,
            filename=path.name,
            semantic_text=analysis_bundle["semantic_text"],
            keywords_json=analysis_bundle["search_keywords"],
            semantic_json=analysis_bundle["semantic_json"],
        )
        try:
            self._persist_evidence_and_tags(uid, analysis_bundle["semantic_json"], conn)
        except Exception:
            pass
        self._generate_thumbnail(uid, path, "image")

        return {
            "uid": uid,
            "filename": path.name,
            "path": str(path),
            "sha256": sha256,
            "phash": phash,
            "content_fingerprint": content_fp,
            "thumbnail_hash": thumb_hash,
            "dedup_hit": bool(existing),
            "similar_uid": similar_uid,
            "phash_distance": similar_distance,
            "resolution": analysis_bundle["resolution"],
            "duration": analysis_bundle["duration"],
            "semantic_dimensions_count": len((analysis_bundle.get("semantic_json") or {}).keys()),
        }

    def _ingest_video_paths(
        self,
        videos: Iterable[Path],
        source_type: str,
        source_ref: Optional[str],
        source_display: Optional[str] = None,
        progress_callback=None,
        should_cancel=None,
    ) -> Dict:
        _ivp_t0 = time.perf_counter()
        video_list = [Path(p).resolve() for p in videos]
        result = {
            "source_type": source_type,
            "source": source_display or source_ref or "",
            "scanned": len(video_list),
            "indexed": 0,
            "dedup_hits": 0,
            "failed": 0,
            "assets": [],
        }
        total = len(video_list)
        done = 0

        with self._connect() as conn:
            for p in video_list:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            result["cancelled"] = True
                            result["cancelled_after"] = done
                            break
                    except Exception:
                        result["cancelled"] = True
                        result["cancelled_after"] = done
                        break
                try:
                    item = self._ingest_video_file(conn, p, source_type, source_ref)
                    result["indexed"] += 1
                    if item["dedup_hit"]:
                        result["dedup_hits"] += 1
                    result["assets"].append(item)
                except Exception as exc:
                    result["failed"] += 1
                    result.setdefault("errors", []).append(f"{p.name}: {exc}")
                finally:
                    done += 1
                    # 短事务提交，避免一次大批量入库长时间持有写锁。
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    if callable(progress_callback):
                        try:
                            progress_callback(done, total, str(p))
                        except Exception:
                            pass

            # 持续更新：每轮入库后补齐一批历史缺失 embedding，避免一次性重算阻塞。
            try:
                result["embedding_refreshed"] = self._refresh_embeddings_incremental(
                    conn,
                    max_items=max(6, min(60, result["indexed"] // 2 + 6)),
                )
            except Exception:
                result["embedding_refreshed"] = 0
            try:
                conn.commit()
            except Exception:
                pass

        _ivp_elapsed = (time.perf_counter() - _ivp_t0) * 1000
        _gml_logger.info("[perf] ingest_video_paths: %.1fms scanned=%d indexed=%d",
                         _ivp_elapsed, result["scanned"], result["indexed"])
        try:
            from modules.app_api.services.perf_log import record as _perf_rec
            _perf_rec("ingest_video_paths", _ivp_elapsed,
                      {"scanned": result["scanned"], "indexed": result["indexed"]})
        except Exception:
            pass
        return result

    def _ingest_image_paths(
        self,
        images: Iterable[Path],
        source_type: str,
        source_ref: Optional[str],
        source_display: Optional[str] = None,
        progress_callback=None,
        should_cancel=None,
    ) -> Dict:
        _iip_t0 = time.perf_counter()
        image_list = [Path(p).resolve() for p in images]
        result = {
            "source_type": source_type,
            "source": source_display or source_ref or "",
            "scanned": len(image_list),
            "indexed": 0,
            "dedup_hits": 0,
            "failed": 0,
            "assets": [],
        }
        total = len(image_list)
        done = 0

        with self._connect() as conn:
            for p in image_list:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            result["cancelled"] = True
                            result["cancelled_after"] = done
                            break
                    except Exception:
                        result["cancelled"] = True
                        result["cancelled_after"] = done
                        break
                try:
                    item = self._ingest_image_file(conn, p, source_type, source_ref)
                    result["indexed"] += 1
                    if item["dedup_hit"]:
                        result["dedup_hits"] += 1
                    result["assets"].append(item)
                except Exception as exc:
                    result["failed"] += 1
                    result.setdefault("errors", []).append(f"{p.name}: {exc}")
                finally:
                    done += 1
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    if callable(progress_callback):
                        try:
                            progress_callback(done, total, str(p))
                        except Exception:
                            pass

            try:
                result["embedding_refreshed"] = self._refresh_embeddings_incremental(
                    conn,
                    max_items=max(6, min(60, result["indexed"] // 2 + 6)),
                )
            except Exception:
                result["embedding_refreshed"] = 0
            try:
                conn.commit()
            except Exception:
                pass

        _iip_elapsed = (time.perf_counter() - _iip_t0) * 1000
        _gml_logger.info("[perf] ingest_image_paths: %.1fms scanned=%d indexed=%d",
                         _iip_elapsed, result["scanned"], result["indexed"])
        try:
            from modules.app_api.services.perf_log import record as _perf_rec
            _perf_rec("ingest_image_paths", _iip_elapsed,
                      {"scanned": result["scanned"], "indexed": result["indexed"]})
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # Public ingest APIs

    def ingest_local_path(self, source_path: str, max_videos: int = 600, progress_callback=None, should_cancel=None) -> Dict:
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"路径不存在: {root}")

        videos = self._discover_videos(root)
        total_candidates = len(videos)
        try:
            max_videos = int(max_videos)
        except Exception:
            max_videos = 600
        if max_videos <= 0:
            max_videos = 600
        max_videos = min(max_videos, 5000)

        selected = videos[:max_videos]
        result = self._ingest_video_paths(
            selected,
            source_type="local",
            source_ref=str(root),
            source_display=str(root),
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )
        result["total_candidates"] = total_candidates
        result["max_videos"] = max_videos
        result["truncated"] = total_candidates > len(selected)
        return result

    def ingest_local_images(self, source_path: str, max_images: int = 1200, progress_callback=None, should_cancel=None) -> Dict:
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"路径不存在: {root}")

        images = self._discover_images(root)
        total_candidates = len(images)
        try:
            max_images = int(max_images)
        except Exception:
            max_images = 1200
        if max_images <= 0:
            max_images = 1200
        max_images = min(max_images, 8000)

        selected = images[:max_images]
        result = self._ingest_image_paths(
            selected,
            source_type="local",
            source_ref=str(root),
            source_display=str(root),
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )
        result["total_candidates"] = total_candidates
        result["max_images"] = max_images
        result["truncated"] = total_candidates > len(selected)
        return result

    @staticmethod
    def _is_drive_folder_url(url: str) -> bool:
        return "drive.google.com" in url and ("/folders/" in url or "drive/folders" in url)

    @staticmethod
    def _normalize_priority_keywords(priority_subdirs) -> List[str]:
        if not priority_subdirs:
            return []
        if isinstance(priority_subdirs, str):
            raw = [x.strip() for x in re.split(r"[,\n;，；]+", priority_subdirs) if x.strip()]
        elif isinstance(priority_subdirs, list):
            raw = [str(x).strip() for x in priority_subdirs if str(x).strip()]
        else:
            raw = [str(priority_subdirs).strip()] if str(priority_subdirs).strip() else []
        out = []
        seen = set()
        for item in raw:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out

    @staticmethod
    def _extract_drive_folder_id(url: str) -> Optional[str]:
        parsed = urlparse(url)
        m = re.search(r"/folders/([a-zA-Z0-9_-]+)", parsed.path or "")
        if m:
            return m.group(1)
        q = parse_qs(parsed.query or "")
        folder_ids = q.get("id") or []
        return folder_ids[0] if folder_ids else None

    @staticmethod
    def _sanitize_drive_name(name: str) -> str:
        s = str(name or "").replace("/", "_").replace("\\", "_").strip()
        return s or "untitled"

    @staticmethod
    def _path_priority_score(path_text: str, priority_keywords: List[str]) -> int:
        if not priority_keywords:
            return 0
        text = (path_text or "").lower()
        return sum(1 for kw in priority_keywords if kw and kw in text)

    def _create_gdrive_folder_session(self):
        gdown_folder_mod = importlib.import_module("gdown.download_folder")
        folder_type = gdown_folder_mod._GoogleDriveFile.TYPE_FOLDER
        sess = gdown_folder_mod._get_session(
            proxy=None,
            use_cookies=False,
            user_agent=GDOWN_FOLDER_USER_AGENT,
        )
        return gdown_folder_mod, folder_type, sess

    def _fetch_gdrive_children(self, gdown_folder_mod, sess, folder_id: str):
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}"

        def _do_fetch():
            req_url = folder_url + ("&hl=en" if "?" in folder_url else "?hl=en")
            res = sess.get(req_url, verify=True, timeout=(10, 30))
            if res.status_code != 200:
                raise RuntimeError(f"扫描文件夹失败，HTTP {res.status_code}")
            gdrive_file, id_name_type_iter = gdown_folder_mod._parse_google_drive_file(
                url=req_url,
                content=res.text,
            )
            folder_name = self._sanitize_drive_name(gdrive_file.name)
            children = []
            for child_id, child_name, child_type in id_name_type_iter:
                children.append((child_id, self._sanitize_drive_name(child_name), child_type))
            return folder_name, children

        return self._run_with_retry(_do_fetch, attempts=3, base_delay=1.2)

    def _scan_gdrive_videos_priority(
        self,
        url: str,
        target_dir: Path,
        max_videos: int,
        priority_keywords: List[str],
        max_scan_folders: int,
        should_cancel=None,
    ) -> Dict:
        folder_id = self._extract_drive_folder_id(url)
        if not folder_id:
            raise RuntimeError("无法从链接解析 Google Drive 文件夹 ID")

        gdown_folder_mod, folder_type, sess = self._create_gdrive_folder_session()

        preferred = deque([(folder_id, [])])
        normal = deque()
        visited = set()
        candidates = []
        listed_files = 0
        scanned_folders = 0
        folder_budget_hit = False
        cancelled = False

        try:
            while (preferred or normal) and len(candidates) < max_videos:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            cancelled = True
                            break
                    except Exception:
                        cancelled = True
                        break
                if scanned_folders >= max_scan_folders:
                    folder_budget_hit = True
                    break

                queue = preferred if preferred else normal
                current_id, parent_parts = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)

                folder_name, children = self._fetch_gdrive_children(gdown_folder_mod, sess, current_id)
                scanned_folders += 1
                current_parts = parent_parts if parent_parts else [folder_name]

                for child_id, child_name, child_type in children:
                    rel_parts = current_parts + [child_name]
                    rel_path = "/".join(rel_parts)

                    if child_type == folder_type:
                        entry = (child_id, rel_parts)
                        if self._path_priority_score(rel_path, priority_keywords) > 0:
                            preferred.append(entry)
                        else:
                            normal.append(entry)
                        continue

                    listed_files += 1
                    if not self._is_video_file(Path(child_name)):
                        continue

                    candidates.append(
                        {
                            "id": child_id,
                            "path": rel_path,
                            "local_path": str(target_dir / Path(*rel_parts)),
                            "priority_score": self._path_priority_score(rel_path, priority_keywords),
                        }
                    )
                    if len(candidates) >= max_videos:
                        break
        finally:
            try:
                sess.close()
            except Exception:
                pass

        candidates.sort(
            key=lambda x: (x.get("priority_score", 0), x.get("path", "")),
            reverse=True,
        )
        is_partial = folder_budget_hit or bool(preferred or normal) or (len(candidates) >= max_videos)
        return {
            "items": candidates[:max_videos],
            "listed_files": listed_files,
            "video_candidates": len(candidates),
            "scanned_folders": scanned_folders,
            "folder_budget_hit": folder_budget_hit,
            "scan_partial": is_partial or cancelled,
            "priority_keywords": priority_keywords,
            "cancelled": cancelled,
        }

    def _scan_gdrive_images_priority(
        self,
        url: str,
        target_dir: Path,
        max_images: int,
        priority_keywords: List[str],
        max_scan_folders: int,
        should_cancel=None,
    ) -> Dict:
        folder_id = self._extract_drive_folder_id(url)
        if not folder_id:
            raise RuntimeError("无法从链接解析 Google Drive 文件夹 ID")

        gdown_folder_mod, folder_type, sess = self._create_gdrive_folder_session()

        preferred = deque([(folder_id, [])])
        normal = deque()
        visited = set()
        candidates = []
        listed_files = 0
        scanned_folders = 0
        folder_budget_hit = False
        cancelled = False

        try:
            while (preferred or normal) and len(candidates) < max_images:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            cancelled = True
                            break
                    except Exception:
                        cancelled = True
                        break
                if scanned_folders >= max_scan_folders:
                    folder_budget_hit = True
                    break

                queue = preferred if preferred else normal
                current_id, parent_parts = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)

                folder_name, children = self._fetch_gdrive_children(gdown_folder_mod, sess, current_id)
                scanned_folders += 1
                current_parts = parent_parts if parent_parts else [folder_name]

                for child_id, child_name, child_type in children:
                    rel_parts = current_parts + [child_name]
                    rel_path = "/".join(rel_parts)

                    if child_type == folder_type:
                        entry = (child_id, rel_parts)
                        if self._path_priority_score(rel_path, priority_keywords) > 0:
                            preferred.append(entry)
                        else:
                            normal.append(entry)
                        continue

                    listed_files += 1
                    if not self._is_image_file(Path(child_name)):
                        continue

                    candidates.append(
                        {
                            "id": child_id,
                            "path": rel_path,
                            "local_path": str(target_dir / Path(*rel_parts)),
                            "priority_score": self._path_priority_score(rel_path, priority_keywords),
                        }
                    )
                    if len(candidates) >= max_images:
                        break
        finally:
            try:
                sess.close()
            except Exception:
                pass

        candidates.sort(
            key=lambda x: (x.get("priority_score", 0), x.get("path", "")),
            reverse=True,
        )
        is_partial = folder_budget_hit or bool(preferred or normal) or (len(candidates) >= max_images)
        return {
            "items": candidates[:max_images],
            "listed_files": listed_files,
            "image_candidates": len(candidates),
            "scanned_folders": scanned_folders,
            "folder_budget_hit": folder_budget_hit,
            "scan_partial": is_partial or cancelled,
            "priority_keywords": priority_keywords,
            "cancelled": cancelled,
        }

    def preview_google_drive(
        self,
        url: str,
        priority_subdirs=None,
        max_scan_folders: int = 120,
        max_results: int = 30,
    ) -> Dict:
        if gdown is None:
            raise RuntimeError("未安装 gdown，无法处理 Google Drive 链接")
        if not self._is_drive_folder_url(url):
            raise RuntimeError("仅支持 Google Drive 文件夹链接预览")

        try:
            max_scan_folders = int(max_scan_folders)
        except Exception:
            max_scan_folders = 120
        if max_scan_folders <= 0:
            max_scan_folders = 120
        max_scan_folders = min(max_scan_folders, 2000)

        try:
            max_results = int(max_results)
        except Exception:
            max_results = 30
        if max_results <= 0:
            max_results = 30
        max_results = min(max_results, 200)

        priority_keywords = self._normalize_priority_keywords(priority_subdirs)
        folder_id = self._extract_drive_folder_id(url)
        if not folder_id:
            raise RuntimeError("无法从链接解析 Google Drive 文件夹 ID")

        gdown_folder_mod, folder_type, sess = self._create_gdrive_folder_session()
        preferred = deque([(folder_id, [])])
        normal = deque()
        visited = set()
        folder_stats = {}
        sample_videos = []
        listed_files = 0
        video_files = 0
        scanned_folders = 0
        folder_budget_hit = False

        try:
            while preferred or normal:
                if scanned_folders >= max_scan_folders:
                    folder_budget_hit = True
                    break

                queue = preferred if preferred else normal
                current_id, parent_parts = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)

                folder_name, children = self._fetch_gdrive_children(gdown_folder_mod, sess, current_id)
                scanned_folders += 1
                current_parts = parent_parts if parent_parts else [folder_name]
                folder_path = "/".join(current_parts)
                stat = folder_stats.setdefault(
                    folder_path,
                    {"path": folder_path, "total_files": 0, "video_files": 0, "priority_hits": 0},
                )

                for child_id, child_name, child_type in children:
                    rel_parts = current_parts + [child_name]
                    rel_path = "/".join(rel_parts)

                    if child_type == folder_type:
                        entry = (child_id, rel_parts)
                        if self._path_priority_score(rel_path, priority_keywords) > 0:
                            preferred.append(entry)
                        else:
                            normal.append(entry)
                        continue

                    listed_files += 1
                    stat["total_files"] += 1
                    if not self._is_video_file(Path(child_name)):
                        continue

                    video_files += 1
                    score = self._path_priority_score(rel_path, priority_keywords)
                    stat["video_files"] += 1
                    stat["priority_hits"] += score
                    if len(sample_videos) < max_results:
                        sample_videos.append(
                            {
                                "path": rel_path,
                                "priority_score": score,
                            }
                        )
        finally:
            try:
                sess.close()
            except Exception:
                pass

        folders = [x for x in folder_stats.values() if x["total_files"] > 0]
        folders.sort(
            key=lambda x: (x["video_files"], x["priority_hits"], x["total_files"], x["path"]),
            reverse=True,
        )

        sample_videos.sort(key=lambda x: (x["priority_score"], x["path"]), reverse=True)
        sample_videos = sample_videos[:max_results]

        return {
            "url": url,
            "priority_subdirs": priority_keywords,
            "max_scan_folders": max_scan_folders,
            "scanned_folders": scanned_folders,
            "listed_files": listed_files,
            "video_files": video_files,
            "scan_partial": folder_budget_hit or bool(preferred or normal),
            "folder_stats": folders[:max_results],
            "sample_videos": sample_videos,
        }

    def preview_google_drive_images(
        self,
        url: str,
        priority_subdirs=None,
        max_scan_folders: int = 120,
        max_results: int = 30,
    ) -> Dict:
        if gdown is None:
            raise RuntimeError("未安装 gdown，无法处理 Google Drive 链接")
        if not self._is_drive_folder_url(url):
            raise RuntimeError("仅支持 Google Drive 文件夹链接预览")

        try:
            max_scan_folders = int(max_scan_folders)
        except Exception:
            max_scan_folders = 120
        if max_scan_folders <= 0:
            max_scan_folders = 120
        max_scan_folders = min(max_scan_folders, 2000)

        try:
            max_results = int(max_results)
        except Exception:
            max_results = 30
        if max_results <= 0:
            max_results = 30
        max_results = min(max_results, 200)

        priority_keywords = self._normalize_priority_keywords(priority_subdirs)
        folder_id = self._extract_drive_folder_id(url)
        if not folder_id:
            raise RuntimeError("无法从链接解析 Google Drive 文件夹 ID")

        gdown_folder_mod, folder_type, sess = self._create_gdrive_folder_session()
        preferred = deque([(folder_id, [])])
        normal = deque()
        visited = set()
        folder_stats = {}
        sample_images = []
        listed_files = 0
        image_files = 0
        scanned_folders = 0
        folder_budget_hit = False

        try:
            while preferred or normal:
                if scanned_folders >= max_scan_folders:
                    folder_budget_hit = True
                    break

                queue = preferred if preferred else normal
                current_id, parent_parts = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)

                folder_name, children = self._fetch_gdrive_children(gdown_folder_mod, sess, current_id)
                scanned_folders += 1
                current_parts = parent_parts if parent_parts else [folder_name]
                folder_path = "/".join(current_parts)
                stat = folder_stats.setdefault(
                    folder_path,
                    {"path": folder_path, "total_files": 0, "image_files": 0, "priority_hits": 0},
                )

                for child_id, child_name, child_type in children:
                    rel_parts = current_parts + [child_name]
                    rel_path = "/".join(rel_parts)

                    if child_type == folder_type:
                        entry = (child_id, rel_parts)
                        if self._path_priority_score(rel_path, priority_keywords) > 0:
                            preferred.append(entry)
                        else:
                            normal.append(entry)
                        continue

                    listed_files += 1
                    stat["total_files"] += 1
                    if not self._is_image_file(Path(child_name)):
                        continue

                    image_files += 1
                    score = self._path_priority_score(rel_path, priority_keywords)
                    stat["image_files"] += 1
                    stat["priority_hits"] += score
                    if len(sample_images) < max_results:
                        sample_images.append(
                            {
                                "path": rel_path,
                                "priority_score": score,
                            }
                        )
        finally:
            try:
                sess.close()
            except Exception:
                pass

        folders = [x for x in folder_stats.values() if x["total_files"] > 0]
        folders.sort(
            key=lambda x: (x["image_files"], x["priority_hits"], x["total_files"], x["path"]),
            reverse=True,
        )

        sample_images.sort(key=lambda x: (x["priority_score"], x["path"]), reverse=True)
        sample_images = sample_images[:max_results]

        return {
            "url": url,
            "priority_subdirs": priority_keywords,
            "max_scan_folders": max_scan_folders,
            "scanned_folders": scanned_folders,
            "listed_files": listed_files,
            "image_files": image_files,
            "scan_partial": folder_budget_hit or bool(preferred or normal),
            "folder_stats": folders[:max_results],
            "sample_images": sample_images,
        }

    def ingest_google_drive(
        self,
        url: str,
        refresh: bool = False,
        max_videos: int = 80,
        priority_subdirs=None,
        max_scan_folders: int = 120,
        progress_callback=None,
        should_cancel=None,
    ) -> Dict:
        if gdown is None:
            raise RuntimeError("未安装 gdown，无法处理 Google Drive 链接")

        try:
            max_videos = int(max_videos)
        except Exception:
            max_videos = 80
        if max_videos <= 0:
            max_videos = 80
        max_videos = min(max_videos, 500)
        try:
            max_scan_folders = int(max_scan_folders)
        except Exception:
            max_scan_folders = 120
        if max_scan_folders <= 0:
            max_scan_folders = 120
        max_scan_folders = min(max_scan_folders, 2000)
        priority_keywords = self._normalize_priority_keywords(priority_subdirs)

        safe_key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        target_dir = self.cache_dir / safe_key

        if refresh and target_dir.exists():
            shutil.rmtree(target_dir)

        target_dir.mkdir(parents=True, exist_ok=True)

        if not refresh:
            cached_videos = self._discover_videos(target_dir)
            if cached_videos:
                video_candidates = len(cached_videos)
                if priority_keywords:
                    cached_videos.sort(
                        key=lambda p: self._path_priority_score(
                            str(p.relative_to(target_dir)) if p.is_relative_to(target_dir) else str(p),
                            priority_keywords,
                        ),
                        reverse=True,
                    )
                selected_cached = cached_videos[:max_videos]
                ingest_result = self._ingest_video_paths(
                    selected_cached,
                    source_type="gdrive",
                    source_ref=url,
                    source_display=url,
                    progress_callback=progress_callback,
                    should_cancel=should_cancel,
                )
                ingest_result["listed_files"] = 0
                ingest_result["video_candidates"] = video_candidates
                ingest_result["downloaded_videos"] = len(selected_cached)
                ingest_result["truncated"] = video_candidates > max_videos
                ingest_result["max_videos"] = max_videos
                ingest_result["download_failed"] = 0
                ingest_result["skipped_non_video"] = 0
                ingest_result["cache_dir"] = str(target_dir)
                ingest_result["used_cache_only"] = True
                ingest_result["scan_mode"] = "cache_only"
                ingest_result["scanned_folders"] = 0
                ingest_result["priority_subdirs"] = priority_keywords
                ingest_result["max_scan_folders"] = max_scan_folders
                return ingest_result

        listed_files = 0
        video_candidates = 0
        downloaded_videos = 0
        truncated = False
        download_failed = 0
        downloaded_paths: List[Path] = []

        if self._is_drive_folder_url(url):
            scan_mode = "priority_fast_scan"
            priority_scan_error = None
            scanned_folders = 0
            try:
                scan_result = self._scan_gdrive_videos_priority(
                    url=url,
                    target_dir=target_dir,
                    max_videos=max_videos,
                    priority_keywords=priority_keywords,
                    max_scan_folders=max_scan_folders,
                    should_cancel=should_cancel,
                )
            except Exception as exc:
                scan_result = None
                priority_scan_error = str(exc)

            if scan_result and scan_result.get("items"):
                selected = scan_result["items"]
                listed_files = int(scan_result.get("listed_files", 0))
                video_candidates = int(scan_result.get("video_candidates", len(selected)))
                scanned_folders = int(scan_result.get("scanned_folders", 0))
                truncated = bool(scan_result.get("scan_partial", False))
            else:
                scan_mode = "full_recursive_scan"
                try:
                    listing = self._run_with_retry(
                        lambda: gdown.download_folder(
                            url=url,
                            output=str(target_dir),
                            quiet=True,
                            remaining_ok=True,
                            use_cookies=False,
                            skip_download=True,
                            resume=True,
                        ),
                        attempts=3,
                    )
                except Exception as exc:
                    if priority_scan_error:
                        raise RuntimeError(
                            f"优先扫描失败: {priority_scan_error}; 完整扫描也失败: {exc}"
                        ) from exc
                    raise RuntimeError(f"Google Drive 文件夹扫描失败（已重试 3 次）: {exc}") from exc
                if listing is None:
                    raise RuntimeError("Google Drive 文件夹扫描失败")

                listed_files = len(listing)
                selected = []
                for item in listing:
                    file_id = getattr(item, "id", None)
                    rel_path = str(getattr(item, "path", "") or "")
                    local_path = str(getattr(item, "local_path", "") or "")
                    if not file_id:
                        continue
                    suffix_source = rel_path or local_path
                    if not suffix_source or not self._is_video_file(Path(suffix_source)):
                        continue
                    selected.append(
                        {
                            "id": file_id,
                            "path": rel_path,
                            "local_path": local_path,
                            "priority_score": self._path_priority_score(rel_path, priority_keywords),
                        }
                    )
                video_candidates = len(selected)
                if video_candidates > max_videos:
                    truncated = True
                selected = selected[:max_videos]

            for item in selected:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            truncated = True
                            break
                    except Exception:
                        truncated = True
                        break
                item_id = item["id"] if isinstance(item, dict) else getattr(item, "id", None)
                item_local_path = (
                    item["local_path"] if isinstance(item, dict) else str(getattr(item, "local_path", ""))
                )
                if not item_id or not item_local_path:
                    download_failed += 1
                    continue
                out_path = Path(str(item_local_path))
                out_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    downloaded = self._run_with_retry(
                        lambda: gdown.download(
                            url=f"https://drive.google.com/uc?id={item_id}",
                            output=str(out_path),
                            quiet=True,
                            use_cookies=False,
                            resume=True,
                        ),
                        attempts=3,
                    )
                except Exception:
                    download_failed += 1
                    continue
                final_path = Path(downloaded) if downloaded else out_path
                if final_path.exists():
                    downloaded_paths.append(final_path.resolve())
                else:
                    download_failed += 1
        else:
            scan_mode = "single_file"
            scanned_folders = 0
            priority_scan_error = None
            try:
                file_out = self._run_with_retry(
                    lambda: gdown.download(
                        url=url,
                        output=str(target_dir),
                        quiet=True,
                        fuzzy=True,
                        use_cookies=False,
                        resume=True,
                    ),
                    attempts=3,
                )
            except Exception as exc:
                raise RuntimeError(f"Google Drive 文件下载失败（已重试 3 次）: {exc}") from exc
            if not file_out:
                raise RuntimeError("Google Drive 文件下载失败")
            downloaded_paths = [Path(file_out).resolve()]
            listed_files = 1
            video_candidates = 1

        downloaded_videos = len(downloaded_paths)
        ingest_input = [p for p in downloaded_paths if self._is_video_file(p)]
        ingest_result = self._ingest_video_paths(
            ingest_input,
            source_type="gdrive",
            source_ref=url,
            source_display=url,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )

        ingest_result["listed_files"] = listed_files
        ingest_result["video_candidates"] = video_candidates
        ingest_result["downloaded_videos"] = downloaded_videos
        ingest_result["truncated"] = truncated
        ingest_result["max_videos"] = max_videos
        ingest_result["download_failed"] = download_failed
        skipped_non_video = max(downloaded_videos - len(ingest_input), 0)
        ingest_result["skipped_non_video"] = skipped_non_video
        ingest_result["cache_dir"] = str(target_dir)
        ingest_result["used_cache_only"] = False
        ingest_result["scan_mode"] = scan_mode
        ingest_result["scanned_folders"] = scanned_folders
        ingest_result["priority_subdirs"] = priority_keywords
        ingest_result["max_scan_folders"] = max_scan_folders
        if priority_scan_error:
            ingest_result["priority_scan_error"] = priority_scan_error
        if callable(should_cancel):
            try:
                ingest_result["cancelled"] = bool(should_cancel()) or bool(ingest_result.get("cancelled"))
            except Exception:
                ingest_result["cancelled"] = bool(ingest_result.get("cancelled"))

        # Patch source type/ref for new cache locations.
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE asset_locations
                SET source_type='gdrive', source_ref=?
                WHERE path LIKE ?
                """,
                (url, f"{target_dir}%"),
            )
            conn.execute(
                """
                UPDATE assets
                SET source_type=CASE
                    WHEN source_type='local' THEN source_type
                    ELSE 'gdrive'
                END
                WHERE uid IN (
                    SELECT uid FROM asset_locations WHERE path LIKE ?
                )
                """,
                (f"{target_dir}%",),
            )

        return ingest_result

    def ingest_google_drive_images(
        self,
        url: str,
        refresh: bool = False,
        max_images: int = 200,
        priority_subdirs=None,
        max_scan_folders: int = 120,
        progress_callback=None,
        should_cancel=None,
    ) -> Dict:
        if gdown is None:
            raise RuntimeError("未安装 gdown，无法处理 Google Drive 链接")

        try:
            max_images = int(max_images)
        except Exception:
            max_images = 200
        if max_images <= 0:
            max_images = 200
        max_images = min(max_images, 2000)
        try:
            max_scan_folders = int(max_scan_folders)
        except Exception:
            max_scan_folders = 120
        if max_scan_folders <= 0:
            max_scan_folders = 120
        max_scan_folders = min(max_scan_folders, 2000)
        priority_keywords = self._normalize_priority_keywords(priority_subdirs)

        safe_key = hashlib.sha1(f"{url}|images".encode("utf-8")).hexdigest()[:16]
        target_dir = self.cache_dir / safe_key

        if refresh and target_dir.exists():
            shutil.rmtree(target_dir)

        target_dir.mkdir(parents=True, exist_ok=True)

        if not refresh:
            cached_images = self._discover_images(target_dir)
            if cached_images:
                image_candidates = len(cached_images)
                if priority_keywords:
                    cached_images.sort(
                        key=lambda p: self._path_priority_score(
                            str(p.relative_to(target_dir)) if p.is_relative_to(target_dir) else str(p),
                            priority_keywords,
                        ),
                        reverse=True,
                    )
                selected_cached = cached_images[:max_images]
                ingest_result = self._ingest_image_paths(
                    selected_cached,
                    source_type="gdrive",
                    source_ref=url,
                    source_display=url,
                    progress_callback=progress_callback,
                    should_cancel=should_cancel,
                )
                ingest_result["listed_files"] = 0
                ingest_result["image_candidates"] = image_candidates
                ingest_result["downloaded_images"] = len(selected_cached)
                ingest_result["truncated"] = image_candidates > max_images
                ingest_result["max_images"] = max_images
                ingest_result["download_failed"] = 0
                ingest_result["skipped_non_image"] = 0
                ingest_result["cache_dir"] = str(target_dir)
                ingest_result["used_cache_only"] = True
                ingest_result["scan_mode"] = "cache_only"
                ingest_result["scanned_folders"] = 0
                ingest_result["priority_subdirs"] = priority_keywords
                ingest_result["max_scan_folders"] = max_scan_folders
                return ingest_result

        listed_files = 0
        image_candidates = 0
        downloaded_images = 0
        truncated = False
        download_failed = 0
        downloaded_paths: List[Path] = []

        if self._is_drive_folder_url(url):
            scan_mode = "priority_fast_scan"
            priority_scan_error = None
            scanned_folders = 0
            try:
                scan_result = self._scan_gdrive_images_priority(
                    url=url,
                    target_dir=target_dir,
                    max_images=max_images,
                    priority_keywords=priority_keywords,
                    max_scan_folders=max_scan_folders,
                    should_cancel=should_cancel,
                )
            except Exception as exc:
                scan_result = None
                priority_scan_error = str(exc)

            if scan_result and scan_result.get("items"):
                selected = scan_result["items"]
                listed_files = int(scan_result.get("listed_files", 0))
                image_candidates = int(scan_result.get("image_candidates", len(selected)))
                scanned_folders = int(scan_result.get("scanned_folders", 0))
                truncated = bool(scan_result.get("scan_partial", False))
            else:
                scan_mode = "full_recursive_scan"
                try:
                    listing = self._run_with_retry(
                        lambda: gdown.download_folder(
                            url=url,
                            output=str(target_dir),
                            quiet=True,
                            remaining_ok=True,
                            use_cookies=False,
                            skip_download=True,
                            resume=True,
                        ),
                        attempts=3,
                    )
                except Exception as exc:
                    if priority_scan_error:
                        raise RuntimeError(
                            f"优先扫描失败: {priority_scan_error}; 完整扫描也失败: {exc}"
                        ) from exc
                    raise RuntimeError(f"Google Drive 文件夹扫描失败（已重试 3 次）: {exc}") from exc
                if listing is None:
                    raise RuntimeError("Google Drive 文件夹扫描失败")

                listed_files = len(listing)
                selected = []
                for item in listing:
                    file_id = getattr(item, "id", None)
                    rel_path = str(getattr(item, "path", "") or "")
                    local_path = str(getattr(item, "local_path", "") or "")
                    if not file_id:
                        continue
                    suffix_source = rel_path or local_path
                    if not suffix_source or not self._is_image_file(Path(suffix_source)):
                        continue
                    selected.append(
                        {
                            "id": file_id,
                            "path": rel_path,
                            "local_path": local_path,
                            "priority_score": self._path_priority_score(rel_path, priority_keywords),
                        }
                    )
                image_candidates = len(selected)
                if image_candidates > max_images:
                    truncated = True
                selected = selected[:max_images]

            for item in selected:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            truncated = True
                            break
                    except Exception:
                        truncated = True
                        break
                item_id = item["id"] if isinstance(item, dict) else getattr(item, "id", None)
                item_local_path = (
                    item["local_path"] if isinstance(item, dict) else str(getattr(item, "local_path", ""))
                )
                if not item_id or not item_local_path:
                    download_failed += 1
                    continue
                out_path = Path(str(item_local_path))
                out_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    downloaded = self._run_with_retry(
                        lambda: gdown.download(
                            url=f"https://drive.google.com/uc?id={item_id}",
                            output=str(out_path),
                            quiet=True,
                            use_cookies=False,
                            resume=True,
                        ),
                        attempts=3,
                    )
                except Exception:
                    download_failed += 1
                    continue
                final_path = Path(downloaded) if downloaded else out_path
                if final_path.exists():
                    downloaded_paths.append(final_path.resolve())
                else:
                    download_failed += 1
        else:
            scan_mode = "single_file"
            scanned_folders = 0
            priority_scan_error = None
            try:
                file_out = self._run_with_retry(
                    lambda: gdown.download(
                        url=url,
                        output=str(target_dir),
                        quiet=True,
                        fuzzy=True,
                        use_cookies=False,
                        resume=True,
                    ),
                    attempts=3,
                )
            except Exception as exc:
                raise RuntimeError(f"Google Drive 文件下载失败（已重试 3 次）: {exc}") from exc
            if not file_out:
                raise RuntimeError("Google Drive 文件下载失败")
            downloaded_paths = [Path(file_out).resolve()]
            listed_files = 1
            image_candidates = 1

        downloaded_images = len(downloaded_paths)
        ingest_input = [p for p in downloaded_paths if self._is_image_file(p)]
        ingest_result = self._ingest_image_paths(
            ingest_input,
            source_type="gdrive",
            source_ref=url,
            source_display=url,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )

        ingest_result["listed_files"] = listed_files
        ingest_result["image_candidates"] = image_candidates
        ingest_result["downloaded_images"] = downloaded_images
        ingest_result["truncated"] = truncated
        ingest_result["max_images"] = max_images
        ingest_result["download_failed"] = download_failed
        skipped_non_image = max(downloaded_images - len(ingest_input), 0)
        ingest_result["skipped_non_image"] = skipped_non_image
        ingest_result["cache_dir"] = str(target_dir)
        ingest_result["used_cache_only"] = False
        ingest_result["scan_mode"] = scan_mode
        ingest_result["scanned_folders"] = scanned_folders
        ingest_result["priority_subdirs"] = priority_keywords
        ingest_result["max_scan_folders"] = max_scan_folders
        if priority_scan_error:
            ingest_result["priority_scan_error"] = priority_scan_error
        if callable(should_cancel):
            try:
                ingest_result["cancelled"] = bool(should_cancel()) or bool(ingest_result.get("cancelled"))
            except Exception:
                ingest_result["cancelled"] = bool(ingest_result.get("cancelled"))

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE asset_locations
                SET source_type='gdrive', source_ref=?
                WHERE path LIKE ?
                """,
                (url, f"{target_dir}%"),
            )
            conn.execute(
                """
                UPDATE assets
                SET source_type=CASE
                    WHEN source_type='local' THEN source_type
                    ELSE 'gdrive'
                END
                WHERE uid IN (
                    SELECT uid FROM asset_locations WHERE path LIKE ?
                )
                """,
                (f"{target_dir}%",),
            )

        return ingest_result

    # ------------------------------------------------------------------
    # Query APIs

    def _candidate_local_roots(self, conn: sqlite3.Connection) -> List[Path]:
        rows = conn.execute(
            """
            SELECT DISTINCT source_ref, path
            FROM asset_locations
            WHERE source_type='local'
            """
        ).fetchall()
        roots: List[Path] = []
        seen = set()

        def _push_dir(p: Path):
            try:
                resolved = p.expanduser().resolve()
            except Exception:
                return
            if not resolved.exists() or not resolved.is_dir():
                return
            key = str(resolved)
            if key in seen:
                return
            seen.add(key)
            roots.append(resolved)

        for row in rows:
            raw_ref = str(row["source_ref"] or "").strip()
            if raw_ref:
                _push_dir(Path(raw_ref))

            raw_path = str(row["path"] or "").strip()
            if raw_path:
                p = Path(raw_path).expanduser()
                if p.exists() and p.is_file():
                    _push_dir(p.parent)
                elif p.exists() and p.is_dir():
                    _push_dir(p)

        expanded = list(roots)
        for root in expanded:
            parent = root.parent
            grand = parent.parent if parent != root else parent
            _push_dir(parent)
            _push_dir(grand)
            if root.name.lower() in {"dcim", "clips", "videos", "footage"}:
                _push_dir(parent)

        _push_dir(Path.cwd())

        return expanded + [p for p in roots if p not in expanded]

    def _try_relocate_asset(
        self,
        conn: sqlite3.Connection,
        uid: str,
        filename: Optional[str],
        sha256: Optional[str],
        size_bytes: Optional[int] = None,
    ) -> Optional[str]:
        if not filename or not sha256:
            return None

        now_ts = time.time()
        last_checked = self._relink_checked.get(uid, 0.0)
        if now_ts - last_checked < 30.0:
            return None
        self._relink_checked[uid] = now_ts

        roots = self._candidate_local_roots(conn)
        if not roots:
            return None

        checked = 0
        max_candidates = 2400
        deadline = time.time() + 8.0
        target_size = int(size_bytes) if size_bytes is not None else None

        for root in roots[:14]:
            if time.time() > deadline:
                return None
            try:
                walker = os.walk(root)
            except Exception:
                continue
            for cur_dir, _, files in walker:
                if time.time() > deadline:
                    return None
                if filename not in files:
                    continue
                cand = Path(cur_dir) / filename
                checked += 1
                if checked > max_candidates:
                    return None
                if time.time() > deadline:
                    return None

                try:
                    stat = cand.stat()
                except Exception:
                    continue
                if target_size is not None and int(stat.st_size) != target_size:
                    continue
                try:
                    cand_sha = self._compute_sha256(cand)
                except Exception:
                    continue
                if cand_sha != sha256:
                    continue

                resolved = str(cand.resolve())
                try:
                    self._upsert_location(conn, uid, resolved, "local", str(root))
                    conn.execute(
                        """
                        UPDATE assets
                        SET primary_path=?, source_type='local', updated_at=?
                        WHERE uid=?
                        """,
                        (resolved, self._now(), uid),
                    )
                except sqlite3.OperationalError as exc:
                    if "database is locked" in str(exc).lower():
                        return None
                    raise
                return resolved
        return None

    def _best_existing_path(
        self,
        conn: sqlite3.Connection,
        uid: str,
        fallback: Optional[str],
        filename: Optional[str] = None,
        sha256: Optional[str] = None,
        size_bytes: Optional[int] = None,
        allow_relocate: bool = True,
        update_availability: bool = True,
    ) -> Optional[str]:
        rows = conn.execute(
            """
            SELECT path, source_type
            FROM asset_locations
            WHERE uid = ?
            ORDER BY CASE WHEN source_type='local' THEN 0 ELSE 1 END, id DESC
            """,
            (uid,),
        ).fetchall()

        for row in rows:
            p = Path(row["path"])
            exists = p.exists()
            if update_availability:
                try:
                    conn.execute(
                        "UPDATE asset_locations SET is_available=?, last_seen_at=? WHERE path=?",
                        (1 if exists else 0, self._now(), row["path"]),
                    )
                except sqlite3.OperationalError as exc:
                    if "database is locked" not in str(exc).lower():
                        raise
            if exists:
                return str(p)

        if fallback and Path(fallback).exists():
            return fallback
        if not allow_relocate:
            return fallback
        relocated = self._try_relocate_asset(
            conn=conn,
            uid=uid,
            filename=filename,
            sha256=sha256,
            size_bytes=size_bytes,
        )
        if relocated:
            return relocated
        return fallback

    # ── Phase 3: structured tag recall ──

    def _tag_recall(
        self,
        conn: sqlite3.Connection,
        query: str,
        top_k: int = 500,
    ) -> Tuple[Dict[str, float], Dict[str, Dict], str]:
        """Three-path tag recall: resolve tokens → expand via tag_relation → score assets.

        Returns (tag_scores, tag_match_info, query_type).
        tag_scores: {uid: normalized_score}
        tag_match_info: {uid: {matched_tags, matched_aliases, expanded_tags, hit_details, query_type, has_custom_tag}}
        query_type: exact_tag | alias_tag | composed_query | abstract_intent
        """
        tokens = self._tokenize_query(query)
        if not tokens:
            return {}, {}, "abstract_intent"

        # Extract original query tokens (before synonym expansion) for classification.
        # _tokenize_query adds synonyms; classification should reflect user intent, not expansions.
        _orig_raw = re.split(r"[\s,，;；|/]+", query.strip().lower())
        original_tokens = {p.strip() for p in _orig_raw if len(p.strip()) >= 2}

        tag_cache: Dict[str, Optional[int]] = {}
        resolved_tags: Dict[str, int] = {}      # token → tag_id (all tokens)
        resolution_info: Dict[str, Dict] = {}   # token → {tag_id, hit_type, tag_name}
        unresolved_terms: List[str] = []

        # For classification: only count original user tokens
        orig_resolved: Dict[str, int] = {}
        orig_info: Dict[str, Dict] = {}

        # Step 2: resolve tokens
        for token in tokens:
            tag_id = self._resolve_tag_id(token, conn, _cache=tag_cache, context="search")
            if tag_id == self._STOPWORD_SENTINEL:
                continue
            if tag_id is not None and tag_id > 0:
                hit_type = self._classify_resolution(token, tag_id, conn)
                tag_name = self._get_tag_name_cached(tag_id, conn)
                resolved_tags[token] = tag_id
                info_entry = {
                    "tag_id": tag_id,
                    "hit_type": hit_type,
                    "tag_name": tag_name,
                    "original_term": token,
                }
                resolution_info[token] = info_entry
                # Track original-only resolutions for query classification
                if token in original_tokens:
                    orig_resolved[token] = tag_id
                    orig_info[token] = info_entry
            elif tag_id is None:
                unresolved_terms.append(token)

        # Step 3: classify query type (based on original user tokens only)
        query_type = self._classify_query(query, orig_resolved, orig_info, conn)

        if not resolved_tags:
            return {}, {}, query_type

        # Step 4: expand via tag_relation only
        # expanded_tags: tag_id → (hit_strength, relation_type, from_tag_id)
        expanded_tags: Dict[int, Tuple[float, str, int]] = {}
        direct_tag_ids = set(resolved_tags.values())

        for tag_id in direct_tag_ids:
            # Direct hit gets the strength from how it was resolved
            best_strength = 0.0
            for info in resolution_info.values():
                if info["tag_id"] == tag_id:
                    s = TAG_HIT_STRENGTH.get(info["hit_type"], 1.0)
                    if s > best_strength:
                        best_strength = s
            expanded_tags[tag_id] = (best_strength, "direct", tag_id)

        # Expand synonyms and parent→child via tag_relation
        if direct_tag_ids:
            placeholders = ",".join("?" for _ in direct_tag_ids)
            tag_id_list = list(direct_tag_ids)

            # synonym expansion
            syn_rows = conn.execute(
                f"""SELECT from_tag_id, to_tag_id FROM tag_relation
                    WHERE relation_type = 'synonym'
                    AND (from_tag_id IN ({placeholders}) OR to_tag_id IN ({placeholders}))""",
                tag_id_list + tag_id_list,
            ).fetchall()
            for sr in syn_rows:
                peer = sr[1] if sr[0] in direct_tag_ids else sr[0]
                if peer not in expanded_tags:
                    expanded_tags[peer] = (TAG_HIT_STRENGTH["synonym"], "synonym", sr[0] if sr[0] in direct_tag_ids else sr[1])

            # parent → child expansion
            child_rows = conn.execute(
                f"""SELECT from_tag_id, to_tag_id FROM tag_relation
                    WHERE relation_type = 'parent_child'
                    AND from_tag_id IN ({placeholders})""",
                tag_id_list,
            ).fetchall()
            for cr in child_rows:
                child_id = cr[1]
                if child_id not in expanded_tags:
                    expanded_tags[child_id] = (TAG_HIT_STRENGTH["parent_child"], "parent_child", cr[0])

        if not expanded_tags:
            return {}, {}, query_type

        # Step 5: query asset_tag_result
        all_tag_ids = list(expanded_tags.keys())
        placeholders = ",".join("?" for _ in all_tag_ids)
        atr_rows = conn.execute(
            f"""SELECT asset_id, tag_id, effective_score, source_summary
                FROM asset_tag_result
                WHERE tag_id IN ({placeholders})
                AND result_scope = 'asset'
                AND is_displayed = 1""",
            all_tag_ids,
        ).fetchall()

        # Step 6: aggregate per-asset scores
        asset_scores: Dict[str, float] = {}       # uid → total_score
        asset_details: Dict[str, List[Dict]] = {}  # uid → [hit_detail, ...]

        for atr in atr_rows:
            uid = str(atr[0])  # asset_id stores assets.uid (TEXT)
            tag_id = atr[1]
            eff_score = float(atr[2]) if atr[2] is not None else 0.5
            hit_strength, relation_type, source_tag_id = expanded_tags.get(tag_id, (0.5, "unknown", tag_id))
            weighted = eff_score * hit_strength

            asset_scores[uid] = asset_scores.get(uid, 0.0) + weighted

            tag_name = self._get_tag_name_cached(tag_id, conn)
            detail = {
                "tag_id": tag_id,
                "tag_name": tag_name,
                "hit_strength": hit_strength,
                "relation_type": relation_type,
                "effective_score": eff_score,
                "weighted_score": weighted,
            }
            if relation_type != "direct":
                detail["source_tag_name"] = self._get_tag_name_cached(source_tag_id, conn)
            asset_details.setdefault(uid, []).append(detail)

        if not asset_scores:
            return {}, {}, query_type

        # Step 7: normalize to [0, 1]
        max_score = max(asset_scores.values())
        if max_score > 0:
            tag_scores = {uid: score / max_score for uid, score in asset_scores.items()}
        else:
            tag_scores = dict(asset_scores)

        # Sort and truncate to top_k
        sorted_uids = sorted(tag_scores.keys(), key=lambda u: tag_scores[u], reverse=True)[:top_k]
        tag_scores = {uid: tag_scores[uid] for uid in sorted_uids}

        # Build match_info per uid
        has_custom_tag = any(
            info.get("hit_type") == "custom" for info in resolution_info.values()
        )
        matched_tags = [info["tag_name"] for info in resolution_info.values()]
        matched_aliases = [
            info["original_term"]
            for info in resolution_info.values()
            if info["hit_type"] in ("alias", "custom")
        ]
        expanded_tag_names = [
            self._get_tag_name_cached(tid, conn)
            for tid, (_, rtype, _) in expanded_tags.items()
            if rtype != "direct"
        ]

        tag_match_info: Dict[str, Dict] = {}
        for uid in sorted_uids:
            tag_match_info[uid] = {
                "matched_tags": matched_tags,
                "matched_aliases": matched_aliases,
                "expanded_tags": expanded_tag_names,
                "hit_details": asset_details.get(uid, []),
                "query_type": query_type,
                "has_custom_tag": has_custom_tag,
            }

        return tag_scores, tag_match_info, query_type

    def _score_asset(self, row: sqlite3.Row, keywords: List[str]) -> int:
        filename = (row["filename"] or "").lower()
        path_text = (row["primary_path"] or "").lower()
        scene = (row["scene_description"] or "").lower()
        mood = (row["mood"] or "").lower()
        resolution = (row["resolution"] or "").lower()
        objects = (row["objects_json"] or "").lower()
        semantic_text = (row["semantic_text"] or "").lower()
        semantic_json_text = (row["semantic_json"] or "").lower()
        keywords_text = (row["keywords_json"] or "").lower()

        score = 0
        for kw in keywords:
            if kw in filename:
                score += 10
            if kw in path_text:
                score += 11
            if kw in scene:
                score += 8
            if kw in objects:
                score += 6
            if kw in mood:
                score += 4
            if kw in resolution:
                score += 3
            if kw in semantic_text:
                score += 7
            if kw in keywords_text:
                score += 9
            if f"core:{kw}" in keywords_text:
                score += 13
            if f"secondary:{kw}" in keywords_text:
                score += 4
            if kw in semantic_json_text:
                score += 6
        return score

    def _fetch_assets_by_uids(self, conn: sqlite3.Connection, uids: List[str]) -> List[sqlite3.Row]:
        if not uids:
            return []
        ordered = [u for u in uids if u]
        placeholders = ",".join("?" for _ in ordered)
        return conn.execute(
            f"""
            SELECT uid, filename, sha256, size_bytes, primary_path, source_type, duration, resolution,
                   quality_score, scene_description, mood, objects_json,
                   semantic_json, semantic_text, keywords_json, updated_at,
                   gps_latitude, gps_longitude
            FROM assets
            WHERE uid IN ({placeholders})
            """,
            tuple(ordered),
        ).fetchall()

    # ── Phase 3: shared candidate builder ──

    def _build_search_candidates(
        self,
        conn: sqlite3.Connection,
        q: str,
        keywords: List[str],
        mode: str,
        media: str,
    ) -> Tuple[List[sqlite3.Row], Dict[str, float], Dict[str, float], Dict[str, Dict], str]:
        """Build unified candidate set from FTS5 + vector + tag recall.

        Ensures search_assets() and count_matching_assets() use the same candidate pool.
        Returns (rows, vector_scores, tag_scores, tag_match_info, query_type).
        """
        where_clause = self._media_type_where_sql(media, alias="")

        # FTS5 recall
        fts_uids: set = set()
        if mode in {"keyword", "hybrid"} and keywords:
            try:
                fts_query = " OR ".join(f'"{kw}"' for kw in keywords if kw)
                if fts_query:
                    fts_rows = conn.execute(
                        "SELECT uid FROM assets_fts WHERE semantic_text MATCH ? LIMIT 2000",
                        (fts_query,),
                    ).fetchall()
                    fts_uids = {r["uid"] for r in fts_rows}
            except Exception:
                fts_uids = set()

        # Base rows
        sql = """
            SELECT uid, filename, sha256, size_bytes, primary_path, source_type, duration, resolution,
                   quality_score, scene_description, mood, objects_json,
                   semantic_json, semantic_text, keywords_json, updated_at,
                   gps_latitude, gps_longitude
            FROM assets
        """
        if where_clause:
            sql += f" WHERE {where_clause}"
        sql += " ORDER BY updated_at DESC LIMIT 4000"
        rows = list(conn.execute(sql).fetchall())
        existing_uids = {str(r["uid"]) for r in rows}

        # Merge FTS hits
        if fts_uids:
            fts_missing = [uid for uid in fts_uids if uid not in existing_uids][:500]
            if fts_missing:
                fts_fetched = self._fetch_assets_by_uids(conn, fts_missing)
                if media != "all":
                    fts_fetched = [
                        r for r in fts_fetched
                        if self._infer_asset_kind(r["filename"], r["primary_path"]) == media
                    ]
                rows.extend(fts_fetched)
                existing_uids.update(str(r["uid"]) for r in fts_fetched)

        # Vector recall
        vector_scores: Dict[str, float] = {}
        if q and mode in {"hybrid", "vector"}:
            vector_scores = self._vector_search(conn, q, top_k=1400)
            if vector_scores:
                vec_missing = [uid for uid in vector_scores if uid not in existing_uids][:1200]
                if vec_missing:
                    vec_fetched = self._fetch_assets_by_uids(conn, vec_missing)
                    if media != "all":
                        vec_fetched = [
                            r for r in vec_fetched
                            if self._infer_asset_kind(r["filename"], r["primary_path"]) == media
                        ]
                    rows.extend(vec_fetched)
                    existing_uids.update(str(r["uid"]) for r in vec_fetched)

        # Tag recall
        tag_scores: Dict[str, float] = {}
        tag_match_info: Dict[str, Dict] = {}
        query_type = "composed_query"
        if q and mode in {"keyword", "hybrid"}:
            tag_scores, tag_match_info, query_type = self._tag_recall(conn, q, top_k=500)
            if tag_scores:
                tag_missing = [uid for uid in tag_scores if uid not in existing_uids][:500]
                if tag_missing:
                    tag_fetched = self._fetch_assets_by_uids(conn, tag_missing)
                    if media != "all":
                        tag_fetched = [
                            r for r in tag_fetched
                            if self._infer_asset_kind(r["filename"], r["primary_path"]) == media
                        ]
                    rows.extend(tag_fetched)
                    existing_uids.update(str(r["uid"]) for r in tag_fetched)

        return rows, vector_scores, tag_scores, tag_match_info, query_type

    def _hybrid_rank_candidates(
        self,
        conn: sqlite3.Connection,
        rows: List[sqlite3.Row],
        query: str,
        keywords: List[str],
        retrieval_mode: str = "hybrid",
        vector_scores: Optional[Dict[str, float]] = None,
        tag_scores: Optional[Dict[str, float]] = None,
        tag_match_info: Optional[Dict[str, Dict]] = None,
        query_type: str = "composed_query",
    ) -> List[Dict[str, Any]]:
        if not rows:
            return []
        mode = str(retrieval_mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "keyword", "vector"}:
            mode = "hybrid"

        if tag_scores is None:
            tag_scores = {}
        if tag_match_info is None:
            tag_match_info = {}

        row_by_uid: Dict[str, sqlite3.Row] = {}
        for row in rows:
            uid = str(row["uid"])
            if uid not in row_by_uid:
                row_by_uid[uid] = row

        # FTS scoring
        lexical_scores: Dict[str, int] = {}
        if mode in {"hybrid", "keyword"}:
            for uid, row in row_by_uid.items():
                score = self._score_asset(row, keywords) if keywords else 0
                if score > 0:
                    lexical_scores[uid] = score
            if keywords and not lexical_scores:
                relaxed_keywords = self._relaxed_query_tokens(keywords)
                if relaxed_keywords and relaxed_keywords != keywords:
                    for uid, row in row_by_uid.items():
                        score = self._score_asset(row, relaxed_keywords)
                        if score > 0:
                            lexical_scores[uid] = score

        # Vector scores
        if mode in {"hybrid", "vector"}:
            if vector_scores is None:
                vector_scores = self._vector_search(conn, query, top_k=1400)
            else:
                vector_scores = dict(vector_scores)
        else:
            vector_scores = {}

        # Dynamic weights by query_type
        weights = QUERY_TYPE_WEIGHTS.get(query_type, QUERY_TYPE_WEIGHTS["composed_query"])

        # Normalize each path to [0, 1]
        max_tag = max(tag_scores.values()) if tag_scores else 0.0
        max_fts = max(lexical_scores.values()) if lexical_scores else 0

        # Collect all candidate uids that have at least one non-zero signal
        all_candidate_uids: Set[str] = set()
        for uid in tag_scores:
            if uid in row_by_uid:
                all_candidate_uids.add(uid)
        for uid in lexical_scores:
            if uid in row_by_uid:
                all_candidate_uids.add(uid)
        for uid, vs in vector_scores.items():
            if uid in row_by_uid and float(vs) >= 0.08:
                all_candidate_uids.add(uid)

        if not all_candidate_uids:
            return []

        # Weighted fusion
        combined_scores: Dict[str, float] = {}
        for uid in all_candidate_uids:
            tag_norm = (tag_scores.get(uid, 0.0) / max_tag) if max_tag > 0 else 0.0
            fts_norm = (float(lexical_scores.get(uid, 0)) / float(max_fts)) if max_fts > 0 else 0.0
            raw_vec = float(vector_scores.get(uid, -1.0))
            vec_norm = max(0.0, min(1.0, (raw_vec + 1.0) / 2.0))

            score = (
                weights["tag"] * tag_norm
                + weights["fts"] * fts_norm
                + weights["embedding"] * vec_norm
            )

            # custom_tag boost
            uid_info = tag_match_info.get(uid, {})
            if uid_info.get("has_custom_tag"):
                score += SEARCH_WEIGHTS.get("custom_tag_boost", 0.10)

            combined_scores[uid] = score

        ranked_uids = sorted(
            combined_scores.keys(),
            key=lambda u: (
                combined_scores.get(u, 0.0),
                tag_scores.get(u, 0.0),
                float(lexical_scores.get(u, 0)),
                float(vector_scores.get(u, -1.0)),
                str(row_by_uid[u]["updated_at"] or ""),
            ),
            reverse=True,
        )

        # Build match_sources list
        ranked: List[Dict[str, Any]] = []
        for uid in ranked_uids:
            sources = []
            if uid in tag_scores and tag_scores[uid] > 0:
                sources.append("tag")
            if uid in lexical_scores and lexical_scores[uid] > 0:
                sources.append("fts")
            if uid in vector_scores and float(vector_scores[uid]) >= 0.08:
                sources.append("embedding")

            uid_info = tag_match_info.get(uid, {})
            match_info = {
                "match_sources": sources,
                "combined_score": round(combined_scores.get(uid, 0.0), 4),
                "tag_score": round(tag_scores.get(uid, 0.0), 4),
                "fts_score": int(lexical_scores.get(uid, 0)),
                "embedding_score": round(float(vector_scores.get(uid, 0.0)), 4),
                "query_type": query_type,
                "weights_used": weights,
                "matched_tags": uid_info.get("matched_tags", []),
                "matched_aliases": uid_info.get("matched_aliases", []),
                "expanded_tags": uid_info.get("expanded_tags", []),
                "hit_details": uid_info.get("hit_details", []),
            }
            ranked.append({
                "row": row_by_uid[uid],
                "uid": uid,
                "match_score": float(combined_scores.get(uid, 0.0)),
                "keyword_score": int(lexical_scores.get(uid, 0)),
                "vector_score": float(vector_scores.get(uid, 0.0)),
                "tag_score": round(tag_scores.get(uid, 0.0), 4),
                "match_info": match_info,
            })
        return ranked

    def count_matching_assets(self, query: str = "", retrieval_mode: str = "hybrid", media_type: str = "all") -> int:
        q = (query or "").strip().lower()
        keywords = self._tokenize_query(q) if q else []
        mode = str(retrieval_mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "keyword", "vector"}:
            mode = "hybrid"
        media = self._normalize_media_type(media_type)
        with self._connect() as conn:
            if not q:
                where_clause = self._media_type_where_sql(media, alias="")
                sql = "SELECT COUNT(*) FROM assets"
                if where_clause:
                    sql += f" WHERE {where_clause}"
                return int(conn.execute(sql).fetchone()[0])

            rows, vector_scores, tag_scores, tag_match_info, query_type = (
                self._build_search_candidates(conn, q, keywords, mode, media)
            )
            ranked = self._hybrid_rank_candidates(
                conn=conn,
                rows=rows,
                query=q,
                keywords=keywords,
                retrieval_mode=mode,
                vector_scores=vector_scores,
                tag_scores=tag_scores,
                tag_match_info=tag_match_info,
                query_type=query_type,
            )
            return len(ranked)

    def search_assets(
        self,
        query: str = "",
        limit: int = 100,
        offset: int = 0,
        retrieval_mode: str = "hybrid",
        media_type: str = "all",
    ) -> List[Dict]:
        import time as _time_mod
        _search_t0 = _time_mod.monotonic()
        q = (query or "").strip().lower()
        keywords = self._tokenize_query(q) if q else []
        mode = str(retrieval_mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "keyword", "vector"}:
            mode = "hybrid"
        media = self._normalize_media_type(media_type)
        try:
            limit = max(1, int(limit))
        except Exception:
            limit = 100
        try:
            offset = max(0, int(offset))
        except Exception:
            offset = 0

        with self._connect() as conn:
            if not q:
                where_clause = self._media_type_where_sql(media, alias="a")
                sql = """
                    SELECT a.uid, a.filename, a.sha256, a.size_bytes, a.primary_path, a.source_type,
                           a.duration, a.resolution, a.quality_score, a.scene_description, a.mood,
                           a.objects_json, a.semantic_json, a.keywords_json, a.updated_at,
                           a.gps_latitude, a.gps_longitude,
                           COALESCE(
                               (
                                   SELECT l.path
                                   FROM asset_locations l
                                   WHERE l.uid = a.uid AND l.is_available = 1
                                   ORDER BY CASE WHEN l.source_type='local' THEN 0 ELSE 1 END, l.id DESC
                                   LIMIT 1
                               ),
                               a.primary_path
                           ) AS best_path,
                           CASE WHEN EXISTS (
                               SELECT 1 FROM asset_locations l2
                               WHERE l2.uid = a.uid AND l2.is_available = 1
                           ) THEN 1 ELSE 0 END AS available_hint
                    FROM assets a
                """
                if where_clause:
                    sql += f" WHERE {where_clause}"
                sql += """
                    ORDER BY a.updated_at DESC
                    LIMIT ? OFFSET ?
                """
                rows = conn.execute(
                    sql,
                    (limit, offset),
                ).fetchall()
                results = []
                for row in rows:
                    objects = self._safe_json_loads(row["objects_json"], [])
                    if not isinstance(objects, list):
                        objects = []
                    semantic = self._safe_json_loads(row["semantic_json"], {})
                    semantic_keywords = self._safe_json_loads(row["keywords_json"], [])
                    if not isinstance(semantic_keywords, list):
                        semantic_keywords = []
                    _uid = row["uid"]
                    results.append(
                        {
                            "uid": _uid,
                            "filename": row["filename"],
                            "path": row["best_path"],
                            "asset_kind": self._infer_asset_kind(row["filename"], row["best_path"] or row["primary_path"]),
                            "available": bool(row["available_hint"]),
                            "source_type": row["source_type"],
                            "duration": row["duration"],
                            "resolution": row["resolution"],
                            "quality_score": row["quality_score"],
                            "scene_description": row["scene_description"],
                            "mood": row["mood"],
                            "objects": objects,
                            "semantic": semantic if isinstance(semantic, dict) else {},
                            "semantic_keywords": semantic_keywords,
                            "semantic_dimensions_count": len(semantic.keys()) if isinstance(semantic, dict) else 0,
                            "semantic_dimension_names": list(semantic.keys()) if isinstance(semantic, dict) else [],
                            "updated_at": row["updated_at"],
                            "gps_latitude": row["gps_latitude"],
                            "gps_longitude": row["gps_longitude"],
                            "thumbnail_url": f"/api/library/thumbnail/{_uid}" if self.thumbnail_path(_uid) else None,
                            "match_score": 1,
                            "keyword_score": 0,
                            "vector_score": 0.0,
                        }
                    )
                return results

            rows, vector_scores, tag_scores, tag_match_info, query_type = (
                self._build_search_candidates(conn, q, keywords, mode, media)
            )
            ranked = self._hybrid_rank_candidates(
                conn=conn,
                rows=rows,
                query=q,
                keywords=keywords,
                retrieval_mode=mode,
                vector_scores=vector_scores,
                tag_scores=tag_scores,
                tag_match_info=tag_match_info,
                query_type=query_type,
            )

            # Record search signal (best-effort, before returning)
            _elapsed_ms = int((_time_mod.monotonic() - _search_t0) * 1000)
            try:
                self._record_search_signal(
                    conn=conn, query=q, query_type=query_type,
                    retrieval_mode=mode, result_count=len(ranked),
                    tag_match_info=tag_match_info, tag_scores=tag_scores,
                    vector_scores=vector_scores, ranked_count=len(ranked),
                    search_duration_ms=_elapsed_ms,
                )
                conn.commit()
            except Exception:
                pass
            try:
                from modules.app_api.services.perf_log import record as _perf_rec
                _perf_rec("search_assets", _elapsed_ms, {"query": q, "results": len(ranked), "mode": mode})
            except Exception:
                pass

            if not ranked:
                return []

            paged = ranked[offset: offset + limit]
            if not paged:
                return []

            results = []
            for cand in paged:
                row = cand["row"]
                best_path = self._best_existing_path(
                    conn,
                    row["uid"],
                    row["primary_path"],
                    filename=row["filename"],
                    sha256=row["sha256"],
                    size_bytes=row["size_bytes"],
                    allow_relocate=False,
                    update_availability=False,
                )
                objects = []
                try:
                    objects = json.loads(row["objects_json"] or "[]")
                except Exception:
                    objects = []
                semantic = self._safe_json_loads(row["semantic_json"], {})
                semantic_keywords = self._safe_json_loads(row["keywords_json"], [])

                _uid = row["uid"]
                results.append(
                    {
                        "uid": _uid,
                        "filename": row["filename"],
                        "path": best_path,
                        "asset_kind": self._infer_asset_kind(row["filename"], best_path or row["primary_path"]),
                        "available": bool(best_path and Path(best_path).exists()),
                        "source_type": row["source_type"],
                        "duration": row["duration"],
                        "resolution": row["resolution"],
                        "quality_score": row["quality_score"],
                        "scene_description": row["scene_description"],
                        "mood": row["mood"],
                        "objects": objects,
                        "semantic": semantic,
                        "semantic_keywords": semantic_keywords,
                        "semantic_dimensions_count": len(semantic.keys()) if isinstance(semantic, dict) else 0,
                        "semantic_dimension_names": list(semantic.keys()) if isinstance(semantic, dict) else [],
                        "updated_at": row["updated_at"],
                        "gps_latitude": row["gps_latitude"],
                        "gps_longitude": row["gps_longitude"],
                        "thumbnail_url": f"/api/library/thumbnail/{_uid}" if self.thumbnail_path(_uid) else None,
                        "match_score": cand["match_score"],
                        "keyword_score": cand["keyword_score"],
                        "vector_score": cand["vector_score"],
                        "tag_score": cand.get("tag_score", 0.0),
                        "match_info": cand.get("match_info", {}),
                    }
                )
            return results

    # ── Search signal learning loop ──

    def _record_search_signal(
        self,
        conn: sqlite3.Connection,
        query: str,
        query_type: str,
        retrieval_mode: str,
        result_count: int,
        tag_match_info: Dict[str, Dict],
        tag_scores: Dict[str, float],
        vector_scores: Dict[str, float],
        ranked_count: int,
        search_duration_ms: int = 0,
    ) -> None:
        """Record a search event to search_log and write unresolved search terms to learning_candidate.

        Called at the end of search_assets() for every non-empty query.
        Writes are best-effort — failures are silently ignored.
        """
        if not query or not query.strip():
            return

        normalized = query.strip().lower()

        # Gather resolved / unresolved info from tag_match_info
        resolved_tags_set: set = set()
        for uid_info in tag_match_info.values():
            for t in uid_info.get("matched_tags", []):
                resolved_tags_set.add(t)
            break  # All uids share the same matched_tags

        # Count hits per path
        tag_hit_count = sum(1 for v in tag_scores.values() if v > 0)
        vector_hit_count = sum(1 for v in vector_scores.values() if float(v) >= 0.08)
        # fts_hit_count is not directly available here; use ranked_count - tag - vector overlap estimate
        fts_hit_count = max(0, ranked_count - tag_hit_count)  # approximation

        is_zero_hit = 1 if ranked_count == 0 else 0

        # Resolve only original user tokens (not n-gram sub-tokens) to avoid
        # flooding learning_candidate with noise like "选词", "词管" etc.
        _orig_parts = re.split(r"[\s,，;；|/]+", normalized)
        original_tokens = [p.strip() for p in _orig_parts if len(p.strip()) >= 2]
        tag_cache: Dict[str, Optional[int]] = {}
        unresolved_terms: List[str] = []
        for token in original_tokens:
            tag_id = self._resolve_tag_id(token, conn, _cache=tag_cache, context="search")
            if tag_id is None:
                unresolved_terms.append(token)

        # Write to search_log
        try:
            conn.execute(
                """INSERT INTO search_log
                   (query_text, normalized_query, query_type, retrieval_mode,
                    result_count, tag_hit_count, fts_hit_count, vector_hit_count,
                    resolved_tags, unresolved_terms, is_zero_hit,
                    search_duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query.strip(), normalized, query_type, retrieval_mode,
                 ranked_count, tag_hit_count, fts_hit_count, vector_hit_count,
                 json.dumps(list(resolved_tags_set), ensure_ascii=False) if resolved_tags_set else None,
                 json.dumps(unresolved_terms, ensure_ascii=False) if unresolved_terms else None,
                 is_zero_hit, search_duration_ms),
            )
        except Exception:
            pass

        # Write unresolved search terms to learning_candidate (source_kind='search_query')
        for term in unresolved_terms:
            norm_term = term.lower().strip()
            if len(norm_term) < 2:
                continue
            try:
                conn.execute(
                    """INSERT INTO learning_candidate
                       (candidate_text, normalized_text, category_hint, source_kind,
                        occurrence_count, asset_count)
                       VALUES (?, ?, 'search', 'search_query', 1, 0)
                       ON CONFLICT(normalized_text, source_kind) DO UPDATE SET
                           occurrence_count = occurrence_count + 1""",
                    (term, norm_term),
                )
            except Exception:
                pass

    # ── Search analytics methods ──

    def get_search_analytics(self, days: int = 30, limit: int = 50) -> Dict:
        """Return search analytics: popular queries, zero-hit queries, unresolved terms.

        Args:
            days: Look back N days.
            limit: Max entries per category.
        """
        with self._connect() as conn:
            cutoff = f"datetime('now', '-{int(days)} days')"

            # Popular queries (by frequency)
            popular = conn.execute(
                f"""SELECT normalized_query, COUNT(*) as search_count,
                           SUM(result_count) as total_results,
                           AVG(result_count) as avg_results,
                           MAX(created_at) as last_searched
                    FROM search_log
                    WHERE created_at >= {cutoff}
                    GROUP BY normalized_query
                    ORDER BY search_count DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()

            # Zero-hit queries (unique queries that returned 0 results)
            zero_hits = conn.execute(
                f"""SELECT normalized_query, COUNT(*) as occurrence_count,
                           MAX(created_at) as last_searched
                    FROM search_log
                    WHERE is_zero_hit = 1 AND created_at >= {cutoff}
                    GROUP BY normalized_query
                    ORDER BY occurrence_count DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()

            # Unresolved search terms from learning_candidate
            unresolved = conn.execute(
                """SELECT candidate_text, normalized_text, occurrence_count,
                          review_status, suggested_action, created_at
                   FROM learning_candidate
                   WHERE source_kind = 'search_query'
                   ORDER BY occurrence_count DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            # Summary stats
            total_searches = conn.execute(
                f"SELECT COUNT(*) FROM search_log WHERE created_at >= {cutoff}",
            ).fetchone()[0]
            zero_hit_total = conn.execute(
                f"SELECT COUNT(*) FROM search_log WHERE is_zero_hit = 1 AND created_at >= {cutoff}",
            ).fetchone()[0]
            unique_queries = conn.execute(
                f"SELECT COUNT(DISTINCT normalized_query) FROM search_log WHERE created_at >= {cutoff}",
            ).fetchone()[0]
            _agg = conn.execute(
                f"""SELECT AVG(result_count), AVG(search_duration_ms)
                    FROM search_log WHERE created_at >= {cutoff}""",
            ).fetchone()
            avg_results = round(_agg[0], 1) if _agg and _agg[0] is not None else None
            avg_duration = int(_agg[1]) if _agg and _agg[1] is not None else None

            return {
                "summary": {
                    "total_searches": total_searches,
                    "unique_queries": unique_queries,
                    "zero_hit_count": zero_hit_total,
                    "zero_hit_rate": round(zero_hit_total / max(total_searches, 1), 3),
                    "avg_results": avg_results,
                    "avg_duration_ms": avg_duration,
                    "days": days,
                },
                "popular_queries": [
                    {
                        "query": r[0],
                        "search_count": r[1],
                        "total_results": r[2],
                        "avg_results": round(r[3], 1) if r[3] else 0,
                        "last_searched": r[4],
                    }
                    for r in popular
                ],
                "zero_hit_queries": [
                    {
                        "query": r[0],
                        "occurrence_count": r[1],
                        "last_searched": r[2],
                    }
                    for r in zero_hits
                ],
                "unresolved_search_terms": [
                    {
                        "term": r[0],
                        "normalized": r[1],
                        "occurrence_count": r[2],
                        "review_status": r[3],
                        "suggested_action": r[4],
                        "first_seen": r[5],
                    }
                    for r in unresolved
                ],
            }

    def get_zero_hit_queries(self, days: int = 30, limit: int = 50) -> List[Dict]:
        """Return queries that produced zero results, ordered by frequency."""
        with self._connect() as conn:
            cutoff = f"datetime('now', '-{int(days)} days')"
            rows = conn.execute(
                f"""SELECT normalized_query, COUNT(*) as cnt,
                           MAX(created_at) as last_at
                    FROM search_log
                    WHERE is_zero_hit = 1 AND created_at >= {cutoff}
                    GROUP BY normalized_query
                    ORDER BY cnt DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()
            return [{"query": r[0], "count": r[1], "last_searched": r[2]} for r in rows]

    def get_popular_searches(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """Return most frequently searched queries."""
        with self._connect() as conn:
            cutoff = f"datetime('now', '-{int(days)} days')"
            rows = conn.execute(
                f"""SELECT normalized_query, COUNT(*) as cnt,
                           AVG(result_count) as avg_res,
                           MAX(created_at) as last_at
                    FROM search_log
                    WHERE created_at >= {cutoff}
                    GROUP BY normalized_query
                    ORDER BY cnt DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()
            return [
                {"query": r[0], "count": r[1], "avg_results": round(r[2], 1) if r[2] else 0, "last_searched": r[3]}
                for r in rows
            ]

    def get_learning_candidates(self, source_kind: str = None, status: str = "pending", limit: int = 50) -> List[Dict]:
        """Return learning candidates, optionally filtered by source_kind and review_status."""
        with self._connect() as conn:
            conditions = []
            params: list = []
            if source_kind:
                conditions.append("source_kind = ?")
                params.append(source_kind)
            if status:
                conditions.append("review_status = ?")
                params.append(status)
            where = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            rows = conn.execute(
                f"""SELECT candidate_id, candidate_text, normalized_text, category_hint,
                           source_kind, occurrence_count, asset_count, confirmed_count,
                           suggested_action, review_status, blocked_reason, created_at,
                           cooccur_json
                    FROM learning_candidate
                    WHERE {where}
                    ORDER BY occurrence_count DESC
                    LIMIT ?""",
                tuple(params),
            ).fetchall()
            return [
                {
                    "candidate_id": r[0], "candidate_text": r[1], "normalized": r[2],
                    "category_hint": r[3], "source_kind": r[4],
                    "occurrence_count": r[5], "asset_count": r[6],
                    "confirmed_count": r[7], "suggested_action": r[8],
                    "review_status": r[9], "blocked_reason": r[10],
                    "first_seen": r[11], "cooccur_json": r[12],
                }
                for r in rows
            ]

    def review_learning_candidate(self, candidate_id: int, action: str, reviewed_by: str = "user") -> Dict:
        """Review a learning candidate: approve, reject, or block.

        Args:
            candidate_id: The candidate to review.
            action: One of 'approve', 'reject', 'block'.
            reviewed_by: Who reviewed it.
        """
        if action not in ("approve", "reject", "block"):
            return {"error": f"Invalid action: {action}. Must be approve/reject/block."}

        status_map = {"approve": "approved", "reject": "rejected", "block": "blocked"}
        new_status = status_map[action]

        with self._connect() as conn:
            row = conn.execute(
                "SELECT candidate_id, candidate_text, normalized_text FROM learning_candidate WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if not row:
                return {"error": f"Candidate {candidate_id} not found."}

            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                """UPDATE learning_candidate
                   SET review_status = ?, reviewed_by = ?, reviewed_at = ?
                   WHERE candidate_id = ?""",
                (new_status, reviewed_by, now, candidate_id),
            )

            # If blocked, also add to learning_stopword
            if action == "block":
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO learning_stopword
                           (normalized_text, block_reason, blocked_by)
                           VALUES (?, 'user_blocked', ?)""",
                        (row[2], reviewed_by),
                    )
                except Exception:
                    pass

            conn.commit()
            return {"ok": True, "candidate_id": candidate_id, "new_status": new_status}

    def classify_learning_candidates(self, limit: int = 200) -> Dict:
        """Analyze pending learning candidates and auto-classify suggested_action + cooccur_json.

        Classification logic (from Design Note 4):
          merge_to_alias  — co-occurrence rate >= 0.7 with an existing tag + semantic overlap
          upgrade_to_new_tag — belongs to a known category + occurs in >= 5 assets + high stability
          become_rule_trigger — co-occurs strongly with 2+ tags in fixed patterns
          reject_noise — short/numeric/single-char/low-info patterns

        Returns summary dict with counts per action.
        """
        import re as _re_mod

        # ── Noise patterns (cheap, run first) ──
        _NOISE_RX = _re_mod.compile(
            r"^[\d\s\.\-:_/\\]+$"          # pure numeric / timestamp / path fragments
            r"|^[a-zA-Z]{1,2}$"             # single/double ascii chars
            r"|^\w{1,1}$"                   # single unicode char
            r"|^(img|dsc|mov|mp4|jpg|png|heic|aac|wav)[_\-]?\d*$"  # filename fragments
            r"|^https?://"                  # URLs
            r"|^\d{2,4}[\-/]\d{1,2}[\-/]\d{1,2}"  # date patterns
            r"|^[\u2000-\u206f\u2190-\u21ff\u25a0-\u25ff\u2600-\u26ff]"  # symbol-heavy
            , _re_mod.IGNORECASE
        )
        _FILLER_WORDS = {
            "嗯", "啊", "哦", "呃", "哈", "嘛", "吧", "呀", "喂", "哎",
            "那个", "就是", "然后", "这个", "所以", "其实", "可能", "应该",
            "加载中", "请稍候", "版权所有", "立即购买", "限时优惠",
            "点击查看", "关注我", "转发", "评论", "点赞",
        }

        with self._connect() as conn:
            # Fetch pending candidates
            rows = conn.execute(
                """SELECT candidate_id, candidate_text, normalized_text,
                          category_hint, source_kind, occurrence_count, asset_count
                   FROM learning_candidate
                   WHERE review_status = 'pending'
                   ORDER BY occurrence_count DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            if not rows:
                return {"classified": 0, "actions": {}}

            # Pre-load existing tag names and aliases for co-occurrence matching
            all_tags = {}
            for r in conn.execute("SELECT tag_id, normalized_name, tag_name FROM tag WHERE is_active = 1").fetchall():
                all_tags[r[1]] = {"tag_id": r[0], "tag_name": r[2]}
            all_aliases = {}
            for r in conn.execute(
                "SELECT a.normalized_alias, a.tag_id, t.tag_name FROM tag_alias a "
                "JOIN tag t ON a.tag_id = t.tag_id WHERE t.is_active = 1"
            ).fetchall():
                all_aliases[r[0]] = {"tag_id": r[1], "tag_name": r[2]}

            counts = {"merge_to_alias": 0, "upgrade_to_new_tag": 0,
                       "become_rule_trigger": 0, "reject_noise": 0, "review": 0}

            for row in rows:
                cid, text, norm, cat_hint, source, occ, assets = (
                    row[0], row[1], row[2], row[3], row[4], row[5], row[6],
                )
                action = "review"
                cooccur = {}

                # ── Step 1: Noise detection ──
                if (norm in _FILLER_WORDS
                    or _NOISE_RX.match(norm)
                    or len(norm) <= 1):
                    action = "reject_noise"
                else:
                    # ── Step 2: Substring / near-match with existing tags → merge_to_alias ──
                    best_match = None
                    best_score = 0.0
                    for tag_norm, tag_info in all_tags.items():
                        # Exact substring check (candidate is substring of tag or vice versa)
                        if len(norm) >= 2 and len(tag_norm) >= 2:
                            if norm in tag_norm or tag_norm in norm:
                                overlap = min(len(norm), len(tag_norm)) / max(len(norm), len(tag_norm))
                                if overlap > best_score and overlap >= 0.5:
                                    best_score = overlap
                                    best_match = tag_info
                    # Also check aliases
                    for alias_norm, alias_info in all_aliases.items():
                        if len(norm) >= 2 and len(alias_norm) >= 2:
                            if norm in alias_norm or alias_norm in norm:
                                overlap = min(len(norm), len(alias_norm)) / max(len(norm), len(alias_norm))
                                if overlap > best_score and overlap >= 0.5:
                                    best_score = overlap
                                    best_match = alias_info

                    if best_match and best_score >= 0.6:
                        action = "merge_to_alias"
                        cooccur = {"merge_target_tag_id": best_match["tag_id"],
                                   "merge_target_name": best_match["tag_name"],
                                   "similarity": round(best_score, 2)}

                    # ── Step 3: Co-occurrence analysis with asset_tag_result ──
                    elif source == "llm" and assets >= 3:
                        # Find which existing tags co-occur with this candidate in the same assets
                        # Look at assets where this candidate's source term appears in semantic_json
                        cooccur_tags = conn.execute(
                            """SELECT atr.tag_id, t.tag_name, COUNT(*) as co_count
                               FROM asset_tag_result atr
                               JOIN tag t ON atr.tag_id = t.tag_id
                               WHERE atr.asset_id IN (
                                   SELECT e.asset_id FROM evidence e
                                   WHERE e.raw_value = ? AND e.source_kind = 'llm'
                               )
                               AND atr.is_displayed = 1
                               GROUP BY atr.tag_id
                               ORDER BY co_count DESC
                               LIMIT 10""",
                            (text,),
                        ).fetchall()

                        if cooccur_tags:
                            cooccur = {
                                "cooccurring_tags": [
                                    {"tag_id": r[0], "tag_name": r[1], "count": r[2]}
                                    for r in cooccur_tags[:5]
                                ]
                            }
                            # If high co-occurrence with 2+ tags → rule trigger candidate
                            if len(cooccur_tags) >= 2 and cooccur_tags[0][2] >= 3:
                                action = "become_rule_trigger"
                            # Has known category + enough assets → upgrade candidate
                            elif cat_hint and cat_hint != "search" and assets >= 5 and occ >= 10:
                                action = "upgrade_to_new_tag"

                    # ── Step 4: Fallback heuristics for upgrade ──
                    if action == "review" and cat_hint and cat_hint != "search":
                        if assets >= 5 and occ >= 15:
                            action = "upgrade_to_new_tag"

                # Write classification result
                try:
                    cooccur_str = json.dumps(cooccur, ensure_ascii=False) if cooccur else None
                    conn.execute(
                        """UPDATE learning_candidate
                           SET suggested_action = ?, cooccur_json = ?
                           WHERE candidate_id = ?""",
                        (action, cooccur_str, cid),
                    )
                except Exception:
                    pass

                counts[action] = counts.get(action, 0) + 1

            conn.commit()
            return {
                "classified": len(rows),
                "actions": counts,
            }

    def promote_candidate(self, candidate_id: int, reviewed_by: str = "user") -> Dict:
        """Promote an approved learning candidate into the tag system.

        Based on suggested_action:
          merge_to_alias  → create tag_alias pointing to the merge target
          upgrade_to_new_tag → create a new tag entry
          become_rule_trigger → (future) create composite_rule; for now just approve
          reject_noise → add to learning_stopword

        Returns result dict with the action taken.
        """
        with self._connect() as conn:
            row = conn.execute(
                """SELECT candidate_id, candidate_text, normalized_text,
                          category_hint, source_kind, suggested_action, cooccur_json,
                          review_status
                   FROM learning_candidate WHERE candidate_id = ?""",
                (candidate_id,),
            ).fetchone()
            if not row:
                return {"error": f"Candidate {candidate_id} not found."}

            cid, text, norm, cat_hint, source, action, cooccur_raw, status = (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7],
            )

            if status in ("blocked",):
                return {"error": f"Candidate {cid} is already blocked."}

            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            result_info = {"candidate_id": cid, "candidate_text": text, "action": action}

            if action == "merge_to_alias":
                # Parse cooccur_json to find merge target
                target_tag_id = None
                if cooccur_raw:
                    try:
                        cooccur = json.loads(cooccur_raw)
                        target_tag_id = cooccur.get("merge_target_tag_id")
                    except Exception:
                        pass
                if not target_tag_id:
                    return {"error": "No merge target found in cooccur_json. Run classify first."}

                # Check target tag exists
                target = conn.execute(
                    "SELECT tag_id, tag_name FROM tag WHERE tag_id = ? AND is_active = 1",
                    (target_tag_id,),
                ).fetchone()
                if not target:
                    return {"error": f"Target tag {target_tag_id} not found or inactive."}

                # Check alias doesn't already exist
                existing = conn.execute(
                    "SELECT alias_id FROM tag_alias WHERE tag_id = ? AND normalized_alias = ?",
                    (target_tag_id, norm),
                ).fetchone()
                if existing:
                    result_info["note"] = "Alias already exists"
                else:
                    conn.execute(
                        """INSERT INTO tag_alias
                           (tag_id, alias_name, normalized_alias, alias_type,
                            source_type, confidence)
                           VALUES (?, ?, ?, 'alias', 'learned', 0.9)""",
                        (target_tag_id, text, norm),
                    )
                    result_info["created_alias"] = text
                    result_info["target_tag_name"] = target[1]

                # Mark as promoted
                conn.execute(
                    """UPDATE learning_candidate
                       SET review_status = 'approved', suggested_action = 'merge_to_alias',
                           reviewed_by = ?, reviewed_at = ?
                       WHERE candidate_id = ?""",
                    (reviewed_by, now, cid),
                )

            elif action == "upgrade_to_new_tag":
                # Resolve category_id and semantic_slot from category_hint
                slot = _TAG_CATEGORY_TO_SLOT.get(cat_hint, "object") if cat_hint else "object"
                cat_row = conn.execute(
                    "SELECT category_id, category_code FROM tag_category WHERE category_code = ? LIMIT 1",
                    (slot,),
                ).fetchone()
                if not cat_row:
                    # Fallback: find any active category that matches the slot
                    cat_row = conn.execute(
                        """SELECT tc.category_id, tc.category_code FROM tag_category tc
                           JOIN tag t ON t.category_id = tc.category_id
                           WHERE t.semantic_slot = ? AND tc.is_active = 1
                           LIMIT 1""",
                        (slot,),
                    ).fetchone()
                if not cat_row:
                    # Last resort: use first active category
                    cat_row = conn.execute(
                        "SELECT category_id, category_code FROM tag_category WHERE is_active = 1 ORDER BY sort_order LIMIT 1"
                    ).fetchone()

                category_id = cat_row[0]
                cat_code = cat_row[1]

                # Generate unique tag_code
                max_code = conn.execute(
                    "SELECT MAX(CAST(SUBSTR(tag_code, LENGTH(?) + 2) AS INTEGER)) FROM tag WHERE tag_code LIKE ?",
                    (cat_code, f"{cat_code}_%"),
                ).fetchone()[0]
                next_num = (max_code or 0) + 1
                tag_code = f"{cat_code}_{next_num:04d}"

                # Check for duplicate
                existing = conn.execute(
                    "SELECT tag_id FROM tag WHERE normalized_name = ? AND category_id = ?",
                    (norm, category_id),
                ).fetchone()
                if existing:
                    result_info["note"] = f"Tag already exists (tag_id={existing[0]})"
                else:
                    conn.execute(
                        """INSERT INTO tag
                           (tag_name, normalized_name, tag_code, category_id,
                            semantic_slot, source_type, is_active)
                           VALUES (?, ?, ?, ?, ?, 'learned', 1)""",
                        (text, norm, tag_code, category_id, slot),
                    )
                    new_tag_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    result_info["created_tag_id"] = new_tag_id
                    result_info["tag_code"] = tag_code
                    result_info["semantic_slot"] = slot

                # Mark as promoted
                conn.execute(
                    """UPDATE learning_candidate
                       SET review_status = 'approved', suggested_action = 'upgrade_to_new_tag',
                           reviewed_by = ?, reviewed_at = ?
                       WHERE candidate_id = ?""",
                    (reviewed_by, now, cid),
                )

            elif action == "reject_noise":
                # Add to stopword and block
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO learning_stopword
                           (normalized_text, block_reason, blocked_by)
                           VALUES (?, 'auto_noise', ?)""",
                        (norm, reviewed_by),
                    )
                except Exception:
                    pass
                conn.execute(
                    """UPDATE learning_candidate
                       SET review_status = 'blocked', blocked_reason = 'auto_noise',
                           reviewed_by = ?, reviewed_at = ?
                       WHERE candidate_id = ?""",
                    (reviewed_by, now, cid),
                )
                result_info["blocked"] = True

            else:
                # become_rule_trigger or review → just mark approved for now
                conn.execute(
                    """UPDATE learning_candidate
                       SET review_status = 'approved',
                           reviewed_by = ?, reviewed_at = ?
                       WHERE candidate_id = ?""",
                    (reviewed_by, now, cid),
                )

            conn.commit()
            result_info["ok"] = True
            return result_info

    def batch_reject_noise(self, limit: int = 100) -> Dict:
        """Batch-reject all candidates classified as reject_noise.

        Adds them to learning_stopword and sets review_status='blocked'.
        Returns count of rejected candidates.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT candidate_id, normalized_text
                   FROM learning_candidate
                   WHERE suggested_action = 'reject_noise'
                     AND review_status = 'pending'
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            if not rows:
                return {"rejected": 0}

            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            rejected = 0
            for r in rows:
                cid, norm = r[0], r[1]
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO learning_stopword
                           (normalized_text, block_reason, blocked_by)
                           VALUES (?, 'auto_noise', 'system')""",
                        (norm,),
                    )
                    conn.execute(
                        """UPDATE learning_candidate
                           SET review_status = 'blocked', blocked_reason = 'auto_noise',
                               reviewed_by = 'system', reviewed_at = ?
                           WHERE candidate_id = ?""",
                        (now, cid),
                    )
                    rejected += 1
                except Exception:
                    pass

            conn.commit()
            return {"rejected": rejected}

    # ── Library Health & Tag Coverage ──

    def get_library_health(self) -> Dict:
        """Return comprehensive library health metrics.

        Provides:
        - Asset coverage: how many assets have tags, evidence, embeddings
        - Tag distribution: tags per semantic_slot with asset counts
        - Pipeline health: learning candidates, stopwords, feedback stats
        - Quality metrics: avg tag score, confidence band distribution
        - Weakest assets: assets with lowest tag coverage (candidates for re-analysis)
        """
        with self._connect() as conn:
            # ── 1. Asset counts ──
            total_assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

            assets_with_tags = conn.execute(
                """SELECT COUNT(DISTINCT asset_id) FROM asset_tag_result
                   WHERE result_scope = 'asset' AND is_displayed = 1"""
            ).fetchone()[0]

            assets_with_evidence = conn.execute(
                "SELECT COUNT(DISTINCT asset_id) FROM evidence"
            ).fetchone()[0]

            assets_with_embedding = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE uid IN (SELECT uid FROM asset_embeddings)"
            ).fetchone()[0] if self._table_exists(conn, "asset_embeddings") else 0

            assets_with_semantic = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE semantic_json IS NOT NULL AND semantic_json != ''"
            ).fetchone()[0]

            # ── 2. Tag distribution by semantic_slot ──
            slot_dist = conn.execute(
                """SELECT t.semantic_slot,
                          COUNT(DISTINCT t.tag_id) AS tag_count,
                          COUNT(DISTINCT atr.asset_id) AS asset_count
                   FROM tag t
                   LEFT JOIN asset_tag_result atr ON atr.tag_id = t.tag_id
                       AND atr.result_scope = 'asset' AND atr.is_displayed = 1
                   WHERE t.is_active = 1
                   GROUP BY t.semantic_slot
                   ORDER BY asset_count DESC"""
            ).fetchall()

            tag_distribution = [
                {
                    "semantic_slot": r[0],
                    "tag_count": r[1],
                    "asset_count": r[2],
                    "coverage_pct": round(100.0 * r[2] / total_assets, 1) if total_assets > 0 else 0.0,
                }
                for r in slot_dist
            ]

            # ── 3. Top tags by usage ──
            top_tags = conn.execute(
                """SELECT t.tag_name, t.semantic_slot, COUNT(DISTINCT atr.asset_id) AS cnt
                   FROM tag t
                   JOIN asset_tag_result atr ON atr.tag_id = t.tag_id
                       AND atr.result_scope = 'asset' AND atr.is_displayed = 1
                   WHERE t.is_active = 1
                   GROUP BY t.tag_id
                   ORDER BY cnt DESC
                   LIMIT 20"""
            ).fetchall()

            top_tags_list = [
                {"tag_name": r[0], "semantic_slot": r[1], "asset_count": r[2]}
                for r in top_tags
            ]

            # ── 4. Quality metrics ──
            quality_row = conn.execute(
                """SELECT AVG(effective_score), AVG(final_score),
                          COUNT(CASE WHEN confidence_band = 'high' THEN 1 END),
                          COUNT(CASE WHEN confidence_band = 'medium' THEN 1 END),
                          COUNT(CASE WHEN confidence_band = 'low' THEN 1 END),
                          COUNT(*)
                   FROM asset_tag_result
                   WHERE result_scope = 'asset' AND is_displayed = 1"""
            ).fetchone()

            total_tag_results = quality_row[5] if quality_row else 0
            quality_metrics = {
                "avg_effective_score": round(quality_row[0], 3) if quality_row and quality_row[0] else 0.0,
                "avg_final_score": round(quality_row[1], 3) if quality_row and quality_row[1] else 0.0,
                "confidence_high": quality_row[2] if quality_row else 0,
                "confidence_medium": quality_row[3] if quality_row else 0,
                "confidence_low": quality_row[4] if quality_row else 0,
                "total_tag_results": total_tag_results,
                "avg_tags_per_asset": round(total_tag_results / assets_with_tags, 1) if assets_with_tags > 0 else 0.0,
            }

            # ── 5. User feedback stats ──
            feedback_counts = conn.execute(
                """SELECT feedback_type, COUNT(*)
                   FROM feedback_event
                   GROUP BY feedback_type"""
            ).fetchall()
            feedback_stats = {r[0]: r[1] for r in feedback_counts}

            user_confirmed = conn.execute(
                "SELECT COUNT(*) FROM asset_tag_result WHERE user_confirm_state = 'confirmed'"
            ).fetchone()[0]
            user_rejected = conn.execute(
                "SELECT COUNT(*) FROM asset_tag_result WHERE user_confirm_state = 'rejected'"
            ).fetchone()[0]

            # ── 6. Pipeline health ──
            candidate_counts = conn.execute(
                """SELECT review_status, COUNT(*)
                   FROM learning_candidate
                   GROUP BY review_status"""
            ).fetchall()
            candidate_stats = {r[0]: r[1] for r in candidate_counts}

            stopword_count = conn.execute(
                "SELECT COUNT(*) FROM learning_stopword"
            ).fetchone()[0]

            total_aliases = conn.execute(
                "SELECT COUNT(*) FROM tag_alias"
            ).fetchone()[0]
            learned_aliases = conn.execute(
                "SELECT COUNT(*) FROM tag_alias WHERE source_type = 'learned'"
            ).fetchone()[0]
            learned_tags = conn.execute(
                "SELECT COUNT(*) FROM tag WHERE source_type = 'learned'"
            ).fetchone()[0]

            custom_tags_active = conn.execute(
                "SELECT COUNT(*) FROM custom_tag WHERE status != 'archived'"
            ).fetchone()[0]

            composite_rules = conn.execute(
                "SELECT COUNT(*) FROM composite_rule WHERE is_active = 1"
            ).fetchone()[0]

            # ── 7. Weakest assets (lowest tag coverage) ──
            # Assets with fewest displayed tags (or no tags at all)
            weak_assets = conn.execute(
                """SELECT a.uid, a.filename,
                          COALESCE(tc.tag_count, 0) AS tag_count,
                          COALESCE(tc.avg_score, 0) AS avg_score
                   FROM assets a
                   LEFT JOIN (
                       SELECT asset_id,
                              COUNT(*) AS tag_count,
                              AVG(effective_score) AS avg_score
                       FROM asset_tag_result
                       WHERE result_scope = 'asset' AND is_displayed = 1
                       GROUP BY asset_id
                   ) tc ON tc.asset_id = a.uid
                   ORDER BY tag_count ASC, avg_score ASC
                   LIMIT 10"""
            ).fetchall()

            weakest_assets = [
                {
                    "uid": r[0],
                    "filename": r[1],
                    "tag_count": r[2],
                    "avg_score": round(r[3], 3) if r[3] else 0.0,
                }
                for r in weak_assets
            ]

            # ── 8. Evidence source distribution ──
            evidence_sources = conn.execute(
                """SELECT source_kind, COUNT(*) AS cnt
                   FROM evidence
                   GROUP BY source_kind
                   ORDER BY cnt DESC"""
            ).fetchall()
            evidence_by_source = {r[0]: r[1] for r in evidence_sources}

            return {
                "asset_coverage": {
                    "total_assets": total_assets,
                    "with_tags": assets_with_tags,
                    "with_evidence": assets_with_evidence,
                    "with_embedding": assets_with_embedding,
                    "with_semantic_json": assets_with_semantic,
                    "tag_coverage_pct": round(100.0 * assets_with_tags / total_assets, 1) if total_assets > 0 else 0.0,
                    "evidence_coverage_pct": round(100.0 * assets_with_evidence / total_assets, 1) if total_assets > 0 else 0.0,
                },
                "tag_distribution": tag_distribution,
                "top_tags": top_tags_list,
                "quality_metrics": quality_metrics,
                "feedback_stats": {
                    "by_type": feedback_stats,
                    "user_confirmed_tags": user_confirmed,
                    "user_rejected_tags": user_rejected,
                },
                "pipeline_health": {
                    "candidates": candidate_stats,
                    "stopword_count": stopword_count,
                    "total_aliases": total_aliases,
                    "learned_aliases": learned_aliases,
                    "learned_tags": learned_tags,
                    "custom_tags_active": custom_tags_active,
                    "composite_rules_active": composite_rules,
                },
                "weakest_assets": weakest_assets,
                "evidence_by_source": evidence_by_source,
            }

    def _table_exists(self, conn, table_name: str) -> bool:
        """Check if a table exists in the database."""
        r = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return r[0] > 0

    # ── Phase 3: tag tree, tag search, evidence chain ──

    def get_tag_tree(self) -> List[Dict]:
        """Return tag_category grouped view of all active tags.

        Returns list of category dicts, each containing tags with asset counts.
        Frontend reads len(result) for category count — never hardcode.
        """
        with self._connect() as conn:
            cats = conn.execute(
                "SELECT category_id, category_name, category_code FROM tag_category ORDER BY sort_order, category_id"
            ).fetchall()
            result = []
            for cat in cats:
                cat_id = cat[0]
                tags = conn.execute(
                    """SELECT t.tag_id, t.tag_name, t.semantic_slot,
                              (SELECT COUNT(DISTINCT atr.asset_id) FROM asset_tag_result atr
                               WHERE atr.tag_id = t.tag_id AND atr.result_scope='asset' AND atr.is_displayed=1) AS asset_count
                       FROM tag t
                       WHERE t.category_id = ? AND t.is_active = 1
                       ORDER BY t.tag_name""",
                    (cat_id,),
                ).fetchall()
                result.append({
                    "category_id": cat_id,
                    "category_name": cat[1],
                    "category_code": cat[2],
                    "tag_count": len(tags),
                    "tags": [
                        {
                            "tag_id": t[0],
                            "tag_name": t[1],
                            "semantic_slot": t[2],
                            "asset_count": t[3],
                        }
                        for t in tags
                    ],
                })
            return result

    def search_tags(self, q: str, limit: int = 20) -> List[Dict]:
        """Autocomplete: search tag_name + alias + custom_tag.

        Dedup key: (tag_id, matched_via). Same tag can appear for both tag_name and alias hits.
        """
        if not q or not q.strip():
            return []
        normalized = q.strip().lower()
        results: List[Dict] = []
        seen: set = set()

        with self._connect() as conn:
            # tag_name matches
            tag_rows = conn.execute(
                """SELECT t.tag_id, t.tag_name, tc.category_name, t.semantic_slot
                   FROM tag t
                   LEFT JOIN tag_category tc ON t.category_id = tc.category_id
                   WHERE t.is_active = 1 AND t.normalized_name LIKE ?
                   ORDER BY t.tag_name LIMIT ?""",
                (f"%{normalized}%", limit),
            ).fetchall()
            for r in tag_rows:
                key = (r[0], "tag_name")
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "tag_id": r[0], "tag_name": r[1],
                        "category_name": r[2], "semantic_slot": r[3],
                        "matched_via": "tag_name", "matched_text": r[1],
                    })

            # alias matches
            alias_rows = conn.execute(
                """SELECT ta.tag_id, t.tag_name, tc.category_name, t.semantic_slot, ta.alias_name
                   FROM tag_alias ta
                   JOIN tag t ON ta.tag_id = t.tag_id AND t.is_active = 1
                   LEFT JOIN tag_category tc ON t.category_id = tc.category_id
                   WHERE ta.normalized_alias LIKE ?
                   ORDER BY ta.alias_name LIMIT ?""",
                (f"%{normalized}%", limit),
            ).fetchall()
            for r in alias_rows:
                key = (r[0], "alias")
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "tag_id": r[0], "tag_name": r[1],
                        "category_name": r[2], "semantic_slot": r[3],
                        "matched_via": "alias", "matched_text": r[4],
                    })

            # custom_tag matches (LEFT JOIN so custom tags without parent are included)
            custom_rows = conn.execute(
                """SELECT ct.custom_tag_id, ct.parent_system_tag_id,
                          t.tag_name, tc.category_name, t.semantic_slot,
                          ct.custom_tag_name, ct.semantic_slot AS ct_slot
                   FROM custom_tag ct
                   LEFT JOIN tag t ON ct.parent_system_tag_id = t.tag_id AND t.is_active = 1
                   LEFT JOIN tag_category tc ON t.category_id = tc.category_id
                   WHERE ct.normalized_name LIKE ? AND ct.status != 'archived'
                   ORDER BY ct.custom_tag_name LIMIT ?""",
                (f"%{normalized}%", limit),
            ).fetchall()
            for r in custom_rows:
                ct_id = r[0]
                parent_tag_id = r[1]
                key = (f"ct_{ct_id}", "custom_tag")
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "tag_id": parent_tag_id,
                        "custom_tag_id": ct_id,
                        "tag_name": r[2] or r[5],  # parent tag_name or custom_tag_name
                        "category_name": r[3],
                        "semantic_slot": r[4] or r[6],  # parent slot or custom slot
                        "matched_via": "custom_tag",
                        "matched_text": r[5],  # custom_tag_name
                    })

        # Sort: tag_name > alias > custom_tag
        priority = {"tag_name": 0, "alias": 1, "custom_tag": 2}
        results.sort(key=lambda x: priority.get(x["matched_via"], 9))
        return results[:limit]

    def get_evidence_chain(self, asset_id: str, tag_id: Optional[int] = None) -> Dict:
        """Return structured evidence chain for an asset.

        Returns tag_results + evidence in minimal structured format.
        """
        with self._connect() as conn:
            # Tag results
            atr_sql = """
                SELECT atr.tag_id, t.tag_name, atr.source_summary, atr.decision_reason,
                       atr.base_score, atr.source_bonus, atr.cooccurrence_bonus,
                       atr.hierarchy_bonus, atr.conflict_penalty, atr.negative_penalty,
                       atr.final_score, atr.user_adjustment, atr.effective_score,
                       atr.confidence_band, atr.user_confirm_state
                FROM asset_tag_result atr
                JOIN tag t ON atr.tag_id = t.tag_id
                WHERE atr.asset_id = ? AND atr.result_scope = 'asset'
            """
            atr_params: list = [asset_id]
            if tag_id is not None:
                atr_sql += " AND atr.tag_id = ?"
                atr_params.append(tag_id)
            atr_sql += " ORDER BY atr.effective_score DESC"

            atr_rows = conn.execute(atr_sql, atr_params).fetchall()
            tag_results = []
            for r in atr_rows:
                decision_reason = r[3]
                if isinstance(decision_reason, str):
                    try:
                        decision_reason = json.loads(decision_reason)
                    except Exception:
                        decision_reason = [decision_reason] if decision_reason else []
                tag_results.append({
                    "tag_id": r[0],
                    "tag_name": r[1],
                    "source_summary": r[2],
                    "decision_reason": decision_reason or [],
                    "score_breakdown": {
                        "base_score": r[4],
                        "source_bonus": r[5],
                        "cooccurrence_bonus": r[6],
                        "hierarchy_bonus": r[7],
                        "conflict_penalty": r[8],
                        "negative_penalty": r[9],
                        "final_score": r[10],
                        "user_adjustment": r[11],
                        "effective_score": r[12],
                    },
                    "confidence_band": r[13],
                    "user_confirm_state": r[14],
                })

            # Evidence
            ev_sql = """
                SELECT source_kind, source_model, raw_value, base_score, weighted_score,
                       tag_id, semantic_slot
                FROM evidence
                WHERE asset_id = ?
            """
            ev_params: list = [asset_id]
            if tag_id is not None:
                ev_sql += " AND tag_id = ?"
                ev_params.append(tag_id)
            ev_sql += " ORDER BY weighted_score DESC LIMIT 100"

            ev_rows = conn.execute(ev_sql, ev_params).fetchall()
            evidence_list = []
            for e in ev_rows:
                evidence_list.append({
                    "source_kind": e[0],
                    "source_model": e[1],
                    "raw_value": e[2],
                    "base_score": e[3],
                    "weighted_score": e[4],
                    "tag_id": e[5],
                    "semantic_slot": e[6],
                })

            return {
                "asset_id": asset_id,
                "tag_results": tag_results,
                "evidence_list": evidence_list,
                "total_tag_results": len(tag_results),
                "total_evidence": len(evidence_list),
            }

    # ────────────────────────────────────────────────
    # Phase 5: Custom Tag CRUD
    # ────────────────────────────────────────────────

    def create_custom_tag(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new custom tag. Returns the created tag record."""
        name = str(data.get("custom_tag_name", "")).strip()
        if not name:
            return {"error": "custom_tag_name is required"}

        normalized = name.lower().strip()
        now = self._now()

        with self._connect() as conn:
            # Check duplicate
            existing = conn.execute(
                "SELECT custom_tag_id FROM custom_tag WHERE normalized_name = ? AND status != 'archived'",
                (normalized,),
            ).fetchone()
            if existing:
                return {"error": f"Custom tag '{name}' already exists", "custom_tag_id": existing[0]}

            # Resolve parent system tag if specified
            parent_tag_id = None
            parent_name = str(data.get("parent_tag_name", "")).strip()
            if parent_name:
                row = conn.execute(
                    "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1", (parent_name,)
                ).fetchone()
                if row:
                    parent_tag_id = row[0]

            conn.execute(
                """INSERT INTO custom_tag
                   (user_id, custom_tag_name, normalized_name, parent_system_tag_id,
                    category_id, semantic_slot, aliases, related_objects,
                    trigger_texts, negative_terms, composite_logic,
                    threshold_value, status, match_count, last_used_at,
                    created_at, updated_at)
                   VALUES (?,?,?,?, ?,?,?,?, ?,?,?, ?,?,0,NULL, ?,?)""",
                (
                    int(data.get("user_id", 0)),
                    name,
                    normalized,
                    parent_tag_id,
                    data.get("category_id"),
                    data.get("semantic_slot"),
                    data.get("aliases"),
                    data.get("related_objects"),
                    data.get("trigger_texts"),
                    data.get("negative_terms"),
                    data.get("composite_logic"),
                    float(data.get("threshold_value", 0.72)),
                    "active",
                    now,
                    now,
                ),
            )
            ct_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()

        return self._get_custom_tag_detail(ct_id)

    def list_custom_tags(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        """List all custom tags."""
        with self._connect() as conn:
            sql = """SELECT ct.custom_tag_id, ct.custom_tag_name, ct.normalized_name,
                            ct.parent_system_tag_id, ct.aliases, ct.trigger_texts,
                            ct.negative_terms, ct.composite_logic,
                            ct.status, ct.match_count, ct.last_used_at,
                            ct.created_at, ct.updated_at,
                            t.tag_name AS parent_tag_name
                     FROM custom_tag ct
                     LEFT JOIN tag t ON ct.parent_system_tag_id = t.tag_id"""
            if not include_archived:
                sql += " WHERE ct.status != 'archived'"
            sql += " ORDER BY ct.updated_at DESC"
            rows = conn.execute(sql).fetchall()
            return [
                {
                    "custom_tag_id": r[0],
                    "custom_tag_name": r[1],
                    "normalized_name": r[2],
                    "parent_system_tag_id": r[3],
                    "aliases": r[4],
                    "trigger_texts": r[5],
                    "negative_terms": r[6],
                    "composite_logic": r[7],
                    "status": r[8],
                    "match_count": r[9],
                    "last_used_at": r[10],
                    "created_at": r[11],
                    "updated_at": r[12],
                    "parent_tag_name": r[13],
                }
                for r in rows
            ]

    def update_custom_tag(self, custom_tag_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a custom tag by ID. Returns updated record."""
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT custom_tag_id FROM custom_tag WHERE custom_tag_id = ?", (custom_tag_id,)
            ).fetchone()
            if not existing:
                return {"error": f"Custom tag {custom_tag_id} not found"}

            updates = []
            params = []

            if "custom_tag_name" in data:
                name = str(data["custom_tag_name"]).strip()
                if name:
                    updates.extend(["custom_tag_name = ?", "normalized_name = ?"])
                    params.extend([name, name.lower().strip()])

            for field in ("aliases", "trigger_texts", "negative_terms", "composite_logic",
                          "semantic_slot", "related_objects"):
                if field in data:
                    updates.append(f"{field} = ?")
                    params.append(data[field])

            if "threshold_value" in data:
                updates.append("threshold_value = ?")
                params.append(float(data["threshold_value"]))

            if "status" in data and data["status"] in ("active", "gray", "archived"):
                updates.append("status = ?")
                params.append(data["status"])

            if "parent_tag_name" in data:
                parent_name = str(data["parent_tag_name"]).strip()
                if parent_name:
                    row = conn.execute(
                        "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1", (parent_name,)
                    ).fetchone()
                    updates.append("parent_system_tag_id = ?")
                    params.append(row[0] if row else None)
                else:
                    updates.append("parent_system_tag_id = ?")
                    params.append(None)

            if not updates:
                return {"error": "No valid fields to update"}

            updates.append("updated_at = ?")
            params.append(now)
            params.append(custom_tag_id)

            conn.execute(
                f"UPDATE custom_tag SET {', '.join(updates)} WHERE custom_tag_id = ?",
                params,
            )
            conn.commit()

        return self._get_custom_tag_detail(custom_tag_id)

    def archive_custom_tag(self, custom_tag_id: int) -> Dict[str, Any]:
        """Soft-delete a custom tag by setting status to 'archived'."""
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT custom_tag_id, status FROM custom_tag WHERE custom_tag_id = ?",
                (custom_tag_id,),
            ).fetchone()
            if not existing:
                return {"error": f"Custom tag {custom_tag_id} not found"}
            if existing[1] == "archived":
                return {"ok": True, "message": "Already archived"}

            conn.execute(
                "UPDATE custom_tag SET status = 'archived', updated_at = ? WHERE custom_tag_id = ?",
                (now, custom_tag_id),
            )
            conn.commit()
        return {"ok": True, "custom_tag_id": custom_tag_id}

    def _get_custom_tag_detail(self, custom_tag_id: int) -> Dict[str, Any]:
        """Get single custom tag detail."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT ct.custom_tag_id, ct.custom_tag_name, ct.normalized_name,
                          ct.parent_system_tag_id, ct.aliases, ct.trigger_texts,
                          ct.negative_terms, ct.composite_logic,
                          ct.threshold_value, ct.status, ct.match_count,
                          ct.last_used_at, ct.created_at, ct.updated_at,
                          t.tag_name AS parent_tag_name
                   FROM custom_tag ct
                   LEFT JOIN tag t ON ct.parent_system_tag_id = t.tag_id
                   WHERE ct.custom_tag_id = ?""",
                (custom_tag_id,),
            ).fetchone()
            if not row:
                return {"error": f"Custom tag {custom_tag_id} not found"}
            return {
                "custom_tag_id": row[0],
                "custom_tag_name": row[1],
                "normalized_name": row[2],
                "parent_system_tag_id": row[3],
                "aliases": row[4],
                "trigger_texts": row[5],
                "negative_terms": row[6],
                "composite_logic": row[7],
                "threshold_value": row[8],
                "status": row[9],
                "match_count": row[10],
                "last_used_at": row[11],
                "created_at": row[12],
                "updated_at": row[13],
                "parent_tag_name": row[14],
            }

    # ────────────────────────────────────────────────
    # Phase 5: Feedback API
    # ────────────────────────────────────────────────

    def submit_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit user feedback on an asset-tag pair.

        Supported feedback_type:
          - confirm_correct: user agrees with a tag (user_confirm_state → 'confirmed')
          - reject_wrong: user disagrees (user_confirm_state → 'rejected', user_adjustment -= penalty)
          - add_missing: user proposes a tag the system missed
          - remove_irrelevant: user marks tag as irrelevant (user_confirm_state → 'rejected')

        Rules:
          - feedback_event is ALWAYS appended (immutable log).
          - final_score is NEVER modified.
          - Only user_adjustment and user_confirm_state are updated.
          - effective_score = final_score + user_adjustment.
        """
        asset_id = str(data.get("asset_id", "")).strip()
        feedback_type = str(data.get("feedback_type", "")).strip()
        note = str(data.get("note", "")).strip()

        if not asset_id:
            return {"error": "asset_id is required"}
        if feedback_type not in ("confirm_correct", "reject_wrong", "add_missing", "remove_irrelevant"):
            return {"error": f"Invalid feedback_type: {feedback_type}"}

        tag_id = data.get("tag_id")
        custom_tag_id = data.get("custom_tag_id")
        tag_name = str(data.get("tag_name", "")).strip()
        now = self._now()

        with self._connect() as conn:
            # Resolve tag_id from tag_name if not given directly
            if tag_id is None and tag_name:
                row = conn.execute(
                    "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1", (tag_name,)
                ).fetchone()
                if row:
                    tag_id = row[0]

            # 1. Always record the feedback event (immutable log)
            conn.execute(
                """INSERT INTO feedback_event
                   (user_id, asset_id, segment_id, tag_id, custom_tag_id,
                    feedback_type, note, created_at)
                   VALUES (?,?,NULL,?,?, ?,?,?)""",
                (
                    int(data.get("user_id", 0)),
                    asset_id,
                    tag_id,
                    custom_tag_id,
                    feedback_type,
                    note,
                    now,
                ),
            )

            result = {"ok": True, "feedback_type": feedback_type, "asset_id": asset_id}

            # 2. Apply effect based on type
            if feedback_type == "confirm_correct" and tag_id is not None:
                conn.execute(
                    """UPDATE asset_tag_result
                       SET user_confirm_state = 'confirmed',
                           user_adjustment = MAX(user_adjustment, 0.05),
                           effective_score = final_score + MAX(user_adjustment, 0.05),
                           updated_at = ?
                       WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                    (now, asset_id, tag_id),
                )
                result["confirm_state"] = "confirmed"

            elif feedback_type == "reject_wrong" and tag_id is not None:
                conn.execute(
                    """UPDATE asset_tag_result
                       SET user_confirm_state = 'rejected',
                           user_adjustment = MIN(user_adjustment, -0.30),
                           effective_score = final_score + MIN(user_adjustment, -0.30),
                           updated_at = ?
                       WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                    (now, asset_id, tag_id),
                )
                result["confirm_state"] = "rejected"

            elif feedback_type == "remove_irrelevant" and tag_id is not None:
                conn.execute(
                    """UPDATE asset_tag_result
                       SET user_confirm_state = 'rejected',
                           user_adjustment = -1.0,
                           effective_score = final_score - 1.0,
                           is_displayed = 0,
                           updated_at = ?
                       WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                    (now, asset_id, tag_id),
                )
                result["confirm_state"] = "rejected"
                result["is_displayed"] = False

            elif feedback_type == "add_missing":
                # User says this asset should have a tag it currently lacks.
                # Create asset_tag_result with user-origin score.
                if tag_id is not None:
                    existing = conn.execute(
                        """SELECT result_id FROM asset_tag_result
                           WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                        (asset_id, tag_id),
                    ).fetchone()
                    if existing:
                        # Already exists — just confirm
                        conn.execute(
                            """UPDATE asset_tag_result
                               SET user_confirm_state = 'confirmed',
                                   user_adjustment = MAX(user_adjustment, 0.10),
                                   effective_score = final_score + MAX(user_adjustment, 0.10),
                                   is_displayed = 1,
                                   updated_at = ?
                               WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                            (now, asset_id, tag_id),
                        )
                    else:
                        # New — user-created tag result
                        conn.execute(
                            """INSERT INTO asset_tag_result
                               (asset_id, tag_id, result_scope, is_displayed,
                                base_score, final_score, user_adjustment, effective_score,
                                confidence_band, source_summary, decision_reason,
                                user_confirm_state, created_at, updated_at)
                               VALUES (?,?,'asset',1,
                                       0.0, 0.0, 0.50, 0.50,
                                       'user','user_feedback','user added missing tag',
                                       'confirmed',?,?)""",
                            (asset_id, tag_id, now, now),
                        )
                    result["tag_id"] = tag_id
                    result["confirm_state"] = "confirmed"

            conn.commit()
            return result

    def get_feedback_history(self, asset_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get feedback events for an asset."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT fe.feedback_id, fe.asset_id, fe.tag_id, fe.custom_tag_id,
                          fe.feedback_type, fe.note, fe.created_at,
                          t.tag_name
                   FROM feedback_event fe
                   LEFT JOIN tag t ON fe.tag_id = t.tag_id
                   WHERE fe.asset_id = ?
                   ORDER BY fe.created_at DESC
                   LIMIT ?""",
                (asset_id, limit),
            ).fetchall()
            return [
                {
                    "feedback_id": r[0],
                    "asset_id": r[1],
                    "tag_id": r[2],
                    "custom_tag_id": r[3],
                    "feedback_type": r[4],
                    "note": r[5],
                    "created_at": r[6],
                    "tag_name": r[7],
                }
                for r in rows
            ]

    def get_assets(self, uids: List[str]) -> List[Dict]:
        if not uids:
            return []

        placeholder = ",".join("?" for _ in uids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT uid, filename, sha256, size_bytes, primary_path, source_type, duration, resolution,
                       quality_score, scene_description, mood, objects_json,
                       semantic_json, semantic_text, keywords_json, updated_at,
                       gps_latitude, gps_longitude
                FROM assets
                WHERE uid IN ({placeholder})
                """,
                tuple(uids),
            ).fetchall()

            by_uid = {}
            for row in rows:
                best_path = self._best_existing_path(
                    conn,
                    row["uid"],
                    row["primary_path"],
                    filename=row["filename"],
                    sha256=row["sha256"],
                    size_bytes=row["size_bytes"],
                )
                objects = []
                try:
                    objects = json.loads(row["objects_json"] or "[]")
                except Exception:
                    objects = []
                semantic = self._safe_json_loads(row["semantic_json"], {})
                semantic_keywords = self._safe_json_loads(row["keywords_json"], [])
                by_uid[row["uid"]] = {
                    "uid": row["uid"],
                    "filename": row["filename"],
                    "path": best_path,
                    "asset_kind": self._infer_asset_kind(row["filename"], best_path or row["primary_path"]),
                    "available": bool(best_path and Path(best_path).exists()),
                    "source_type": row["source_type"],
                    "duration": row["duration"],
                    "resolution": row["resolution"],
                    "quality_score": row["quality_score"],
                    "scene_description": row["scene_description"],
                    "mood": row["mood"],
                    "objects": objects,
                    "semantic": semantic,
                    "semantic_keywords": semantic_keywords,
                    "semantic_dimensions_count": len(semantic.keys()) if isinstance(semantic, dict) else 0,
                    "semantic_dimension_names": list(semantic.keys()) if isinstance(semantic, dict) else [],
                    "updated_at": row["updated_at"],
                    "gps_latitude": row["gps_latitude"],
                    "gps_longitude": row["gps_longitude"],
                    "thumbnail_url": f"/api/library/thumbnail/{row['uid']}" if self.thumbnail_path(row["uid"]) else None,
                }

            return [by_uid[uid] for uid in uids if uid in by_uid]

    def build_workflow_materials(self, uids: List[str]) -> Dict:
        if not uids:
            return {}

        placeholder = ",".join("?" for _ in uids)
        materials: Dict = {}

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT uid, filename, sha256, size_bytes, primary_path, analysis_json, semantic_json, keywords_json, updated_at FROM assets WHERE uid IN ({placeholder})",
                tuple(uids),
            ).fetchall()

            for row in rows:
                path = self._best_existing_path(
                    conn,
                    row["uid"],
                    row["primary_path"],
                    filename=row["filename"],
                    sha256=row["sha256"],
                    size_bytes=row["size_bytes"],
                )
                if not path:
                    continue
                if self._infer_asset_kind(row["filename"], path) != "video":
                    continue

                analysis = {}
                try:
                    analysis = json.loads(row["analysis_json"] or "{}")
                except Exception:
                    analysis = {}
                semantic = self._safe_json_loads(row["semantic_json"], {})
                semantic_keywords = self._safe_json_loads(row["keywords_json"], [])

                analysis.setdefault("metadata", {})
                analysis["metadata"]["path"] = path

                materials[row["uid"]] = {
                    "filename": row["filename"],
                    "path": path,
                    "asset_kind": self._infer_asset_kind(row["filename"], path),
                    "hash": row["uid"],
                    "analysis": analysis,
                    "semantic": semantic if isinstance(semantic, dict) else {},
                    "semantic_keywords": semantic_keywords if isinstance(semantic_keywords, list) else [],
                    "timestamp": row["updated_at"],
                }

        return materials

    def stats(self) -> Dict:
        runtime = self._embedding_runtime_status()
        with self._connect() as conn:
            total_assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            video_assets = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE lower(filename) GLOB '*.mp4' OR lower(filename) GLOB '*.mov' OR lower(filename) GLOB '*.avi' OR lower(filename) GLOB '*.mkv' OR lower(filename) GLOB '*.m4v' OR lower(filename) GLOB '*.hevc' OR lower(filename) GLOB '*.flv' OR lower(filename) GLOB '*.wmv'"
            ).fetchone()[0]
            image_assets = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE lower(filename) GLOB '*.jpg' OR lower(filename) GLOB '*.jpeg' OR lower(filename) GLOB '*.png' OR lower(filename) GLOB '*.webp' OR lower(filename) GLOB '*.bmp' OR lower(filename) GLOB '*.tif' OR lower(filename) GLOB '*.tiff' OR lower(filename) GLOB '*.heic'"
            ).fetchone()[0]
            total_locations = conn.execute("SELECT COUNT(*) FROM asset_locations").fetchone()[0]
            local_assets = conn.execute("SELECT COUNT(*) FROM assets WHERE source_type='local'").fetchone()[0]
            gdrive_assets = conn.execute("SELECT COUNT(*) FROM assets WHERE source_type='gdrive'").fetchone()[0]
            semantic_ready_assets = conn.execute(
                """
                SELECT COUNT(*)
                FROM assets
                WHERE semantic_version = ?
                  AND semantic_json IS NOT NULL
                  AND semantic_json != ''
                """,
                (SEMANTIC_SCHEMA_VERSION,),
            ).fetchone()[0]
            semantic_pending_assets = conn.execute(
                """
                SELECT COUNT(*)
                FROM assets
                WHERE semantic_version IS NULL
                   OR semantic_version != ?
                   OR semantic_json IS NULL
                   OR semantic_json = ''
                """,
                (SEMANTIC_SCHEMA_VERSION,),
            ).fetchone()[0]
            available_assets = conn.execute(
                """
                SELECT COUNT(DISTINCT uid)
                FROM asset_locations
                WHERE is_available=1
                """
            ).fetchone()[0]
            embedding_ready_assets = conn.execute(
                """
                SELECT COUNT(*)
                FROM asset_embeddings
                WHERE embedding_version = ?
                """,
                (EMBEDDING_SCHEMA_VERSION,),
            ).fetchone()[0]

        return {
            "db_path": str(self.db_path),
            "cache_dir": str(self.cache_dir),
            "total_assets": total_assets,
            "video_assets": video_assets,
            "image_assets": image_assets,
            "total_locations": total_locations,
            "available_assets": available_assets,
            "local_assets": local_assets,
            "gdrive_assets": gdrive_assets,
            "semantic_schema_version": SEMANTIC_SCHEMA_VERSION,
            "semantic_dimensions_supported": len(SEMANTIC_DIMENSIONS),
            "semantic_ready_assets": semantic_ready_assets,
            "semantic_pending_assets": semantic_pending_assets,
            "embedding_enabled": bool(runtime.get("enabled", False)),
            "embedding_status": runtime.get("reason", ""),
            "embedding_status_message": runtime.get("message", ""),
            "embedding_model": self._embedding_model(),
            "embedding_version": EMBEDDING_SCHEMA_VERSION,
            "embedding_ready_assets": embedding_ready_assets,
            "embedding_pending_assets": max(0, int(total_assets) - int(embedding_ready_assets)),
            "hybrid_search_enabled": True,
        }

    # ------------------------------------------------------------------
    # v0.7 – Known media roots management
    # ------------------------------------------------------------------

    def add_known_root(self, root_path: str, label: Optional[str] = None) -> Dict:
        """Register a known media root directory."""
        rp = str(Path(root_path).resolve())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO known_media_roots (root_path, label)
                VALUES (?, ?)
                ON CONFLICT(root_path) DO UPDATE SET
                    label=COALESCE(excluded.label, known_media_roots.label),
                    is_active=1
                """,
                (rp, label),
            )
            row = conn.execute(
                "SELECT * FROM known_media_roots WHERE root_path=?", (rp,)
            ).fetchone()
            return dict(row) if row else {"root_path": rp, "label": label}

    def list_known_roots(self, active_only: bool = True) -> List[Dict]:
        """List all known media root directories."""
        with self._connect() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM known_media_roots WHERE is_active=1 ORDER BY root_id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM known_media_roots ORDER BY root_id"
                ).fetchall()
            return [dict(r) for r in rows]

    def remove_known_root(self, root_id: int) -> bool:
        """Soft-delete a known media root by setting is_active=0."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE known_media_roots SET is_active=0 WHERE root_id=?",
                (root_id,),
            )
            return conn.execute(
                "SELECT COUNT(*) FROM known_media_roots WHERE root_id=? AND is_active=0",
                (root_id,),
            ).fetchone()[0] > 0

    # ------------------------------------------------------------------
    # v0.7 – Path change audit log
    # ------------------------------------------------------------------

    def _log_path_change(
        self,
        conn: sqlite3.Connection,
        uid: str,
        old_path: Optional[str],
        new_path: Optional[str],
        change_type: str,
        source: str = "system",
    ):
        """Record a path change event in path_change_log."""
        conn.execute(
            """
            INSERT INTO path_change_log (uid, old_path, new_path, change_type, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (uid, old_path, new_path, change_type, source),
        )

    # ------------------------------------------------------------------
    # v0.7 – Asset availability scanning
    # ------------------------------------------------------------------

    def scan_asset_availability(self) -> Dict:
        """
        Batch-check all asset_locations for file existence.
        Updates is_available flag and logs path changes.

        Returns summary: {checked, available, unavailable, changed}.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, uid, path, is_available FROM asset_locations"
            ).fetchall()

            checked = 0
            available = 0
            unavailable = 0
            changed = 0

            for row in rows:
                loc_id = row["id"]
                uid = row["uid"]
                loc_path = row["path"]
                was_available = bool(row["is_available"])
                is_now_available = Path(loc_path).exists()

                checked += 1
                if is_now_available:
                    available += 1
                else:
                    unavailable += 1

                if was_available and not is_now_available:
                    conn.execute(
                        "UPDATE asset_locations SET is_available=0 WHERE id=?",
                        (loc_id,),
                    )
                    self._log_path_change(conn, uid, loc_path, None, "unavailable", "batch_scan")
                    changed += 1
                elif not was_available and is_now_available:
                    conn.execute(
                        "UPDATE asset_locations SET is_available=1, last_seen_at=? WHERE id=?",
                        (self._now(), loc_id),
                    )
                    self._log_path_change(conn, uid, None, loc_path, "added", "batch_scan")
                    changed += 1

        return {
            "checked": checked,
            "available": available,
            "unavailable": unavailable,
            "changed": changed,
        }

    # ------------------------------------------------------------------
    # v0.7 – Batch relocate
    # ------------------------------------------------------------------

    def batch_relocate(self, root_paths: Optional[List[str]] = None) -> Dict:
        """
        Attempt to relocate all unavailable assets by searching known roots
        and optionally additional root_paths.

        IMPORTANT design constraint:
        - Only sha256 EXACT match triggers automatic relink (updates primary_path).
        - content_fingerprint similarity is NEVER used for auto-relocation.
          Fingerprint-based candidates require future human confirmation (Phase B).
        - Every successful relocation MUST update assets.primary_path AND
          write to path_change_log (incomplete without both).

        Returns: {attempted, relocated, failed, details: [{uid, old_path, new_path}]}
        """
        with self._connect() as conn:
            # Gather unavailable assets
            unavailable = conn.execute(
                """
                SELECT DISTINCT a.uid, a.filename, a.sha256, a.size_bytes, a.primary_path
                FROM assets a
                JOIN asset_locations al ON a.uid = al.uid
                WHERE al.is_available = 0
                """
            ).fetchall()

            if not unavailable:
                return {"attempted": 0, "relocated": 0, "failed": 0, "details": []}

            # Build search roots from known_media_roots + provided root_paths
            search_roots = []
            known = conn.execute(
                "SELECT root_path FROM known_media_roots WHERE is_active=1"
            ).fetchall()
            for kr in known:
                p = Path(kr["root_path"])
                if p.is_dir():
                    search_roots.append(p)
            if root_paths:
                for rp in root_paths:
                    p = Path(rp)
                    if p.is_dir() and p not in search_roots:
                        search_roots.append(p)

            # Also include candidate roots from existing locations
            candidate_roots = self._candidate_local_roots(conn)
            for cr in candidate_roots:
                if cr not in search_roots:
                    search_roots.append(cr)

            attempted = 0
            relocated = 0
            failed = 0
            details = []

            for row in unavailable:
                uid = row["uid"]
                filename = row["filename"]
                sha256_val = row["sha256"]
                size_bytes = row["size_bytes"]
                old_primary = row["primary_path"]

                if not filename or not sha256_val:
                    failed += 1
                    continue

                attempted += 1
                found_path = None
                target_size = int(size_bytes) if size_bytes is not None else None

                for root in search_roots[:20]:
                    try:
                        for cur_dir, _, files in os.walk(root):
                            if filename not in files:
                                continue
                            cand = Path(cur_dir) / filename
                            try:
                                stat = cand.stat()
                            except Exception:
                                continue
                            if target_size is not None and int(stat.st_size) != target_size:
                                continue
                            try:
                                cand_sha = self._compute_sha256(cand)
                            except Exception:
                                continue
                            if cand_sha == sha256_val:
                                found_path = str(cand.resolve())
                                break
                    except Exception:
                        continue
                    if found_path:
                        break

                if found_path:
                    self._upsert_location(conn, uid, found_path, "local", None)
                    conn.execute(
                        "UPDATE assets SET primary_path=?, updated_at=? WHERE uid=?",
                        (found_path, self._now(), uid),
                    )
                    self._log_path_change(conn, uid, old_primary, found_path, "relocated", "batch_scan")
                    relocated += 1
                    details.append({"uid": uid, "old_path": old_primary, "new_path": found_path})
                else:
                    failed += 1

        return {
            "attempted": attempted,
            "relocated": relocated,
            "failed": failed,
            "details": details,
        }

    # ------------------------------------------------------------------
    # v0.7 – Duplicate detection
    # ------------------------------------------------------------------

    SIMILARITY_THRESHOLDS = {
        "near_identical": 3,
        "very_similar": 6,
        "similar": 10,
    }

    def detect_duplicates(self, threshold: int = 6) -> Dict:
        """
        Scan entire library for duplicate/similar assets.

        Detection strategy:
        1. Exact duplicates: same sha256 but different uid (shouldn't happen, but check)
        2. Near-identical: content_fingerprint hamming distance <= threshold

        Writes results to duplicate_group + duplicate_group_member tables.
        Returns: {groups_found, exact_groups, similar_groups, total_duplicate_assets}.
        """
        with self._connect() as conn:
            # Clear old pending groups (keep resolved/ignored)
            conn.execute("DELETE FROM duplicate_group_member WHERE group_id IN (SELECT group_id FROM duplicate_group WHERE status='pending')")
            conn.execute("DELETE FROM duplicate_group WHERE status='pending'")

            groups_found = 0
            exact_groups = 0
            similar_groups = 0
            total_dup_assets = 0

            # ── Phase 1: Exact sha256 duplicates across different uid ──
            # (edge case: shouldn't normally happen, but files ingested differently could create this)
            sha256_dups = conn.execute(
                """
                SELECT sha256, GROUP_CONCAT(uid) as uids, COUNT(*) as cnt
                FROM assets
                GROUP BY sha256
                HAVING cnt > 1
                """
            ).fetchall()

            for row in sha256_dups:
                uids = row["uids"].split(",")
                if len(uids) < 2:
                    continue

                # Create group
                conn.execute(
                    """
                    INSERT INTO duplicate_group (group_type, primary_uid, member_count, total_size_bytes, status)
                    VALUES ('exact_sha', ?, ?, 0, 'pending')
                    """,
                    (uids[0], len(uids)),
                )
                group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                total_size = 0
                for u in uids:
                    info = conn.execute(
                        "SELECT size_bytes, resolution, codec FROM assets WHERE uid=?", (u,)
                    ).fetchone()
                    sz = info["size_bytes"] or 0 if info else 0
                    total_size += sz
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO duplicate_group_member
                            (group_id, uid, fingerprint_distance, file_size, resolution, codec)
                        VALUES (?, ?, 0, ?, ?, ?)
                        """,
                        (group_id, u, sz,
                         info["resolution"] if info else None,
                         info["codec"] if info else None),
                    )
                conn.execute(
                    "UPDATE duplicate_group SET total_size_bytes=? WHERE group_id=?",
                    (total_size, group_id),
                )
                groups_found += 1
                exact_groups += 1
                total_dup_assets += len(uids)

            # ── Phase 2: Similar content_fingerprint ──
            # Two-stage: coarse filter (thumbnail_hash) → fine distance (content_fingerprint)
            # Note: idx_assets_content_fp is a B-tree index for IS NOT NULL queries only,
            # NOT a distance-aware index. All hamming distance computations happen in
            # application code. Future optimization: VP-tree or BK-tree for sub-linear lookup.
            fp_rows = conn.execute(
                """
                SELECT uid, content_fingerprint, thumbnail_hash, size_bytes, resolution, codec
                FROM assets
                WHERE content_fingerprint IS NOT NULL AND content_fingerprint != ''
                """
            ).fetchall()

            # Stage 1 (coarse): build thumbnail_hash → uid list for fast pre-grouping
            # Assets with very different thumbnails (distance > threshold * 2) are skipped
            # to avoid unnecessary content_fingerprint distance computation.
            # Stage 2 (fine): compute exact hamming distance on content_fingerprint for
            # pairs that survived the coarse filter.
            visited = set()
            for i, row_i in enumerate(fp_rows):
                uid_i = row_i["uid"]
                if uid_i in visited:
                    continue
                fp_i = row_i["content_fingerprint"]
                thumb_i = row_i["thumbnail_hash"]
                group_members = [(uid_i, 0)]

                for row_j in fp_rows[i + 1:]:
                    uid_j = row_j["uid"]
                    if uid_j in visited:
                        continue

                    # ── Coarse filter: thumbnail_hash pre-screen ──
                    # If both have thumbnail hashes, skip pair if thumbnails are very different
                    thumb_j = row_j["thumbnail_hash"]
                    if thumb_i and thumb_j:
                        thumb_dist = self._phash_distance(thumb_i, thumb_j)
                        if thumb_dist is not None and thumb_dist > threshold * 2:
                            continue  # thumbnails too different, skip expensive comparison

                    # ── Fine filter: content_fingerprint distance ──
                    fp_j = row_j["content_fingerprint"]
                    dist = self._phash_distance(fp_i, fp_j)
                    if dist is not None and dist <= threshold:
                        group_members.append((uid_j, dist))
                        visited.add(uid_j)

                if len(group_members) < 2:
                    continue

                visited.add(uid_i)
                # Classify group type by max distance
                max_dist = max(d for _, d in group_members)
                if max_dist <= self.SIMILARITY_THRESHOLDS["near_identical"]:
                    group_type = "near_identical"
                elif max_dist <= self.SIMILARITY_THRESHOLDS["very_similar"]:
                    group_type = "very_similar"
                else:
                    group_type = "similar"

                conn.execute(
                    """
                    INSERT INTO duplicate_group (group_type, primary_uid, member_count, total_size_bytes, status)
                    VALUES (?, ?, ?, 0, 'pending')
                    """,
                    (group_type, uid_i, len(group_members)),
                )
                group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                total_size = 0
                for uid_m, dist_m in group_members:
                    info = conn.execute(
                        "SELECT size_bytes, resolution, codec FROM assets WHERE uid=?", (uid_m,)
                    ).fetchone()
                    sz = info["size_bytes"] or 0 if info else 0
                    total_size += sz
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO duplicate_group_member
                            (group_id, uid, fingerprint_distance, file_size, resolution, codec)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (group_id, uid_m, dist_m, sz,
                         info["resolution"] if info else None,
                         info["codec"] if info else None),
                    )

                conn.execute(
                    "UPDATE duplicate_group SET total_size_bytes=? WHERE group_id=?",
                    (total_size, group_id),
                )
                groups_found += 1
                similar_groups += 1
                total_dup_assets += len(group_members)

        return {
            "groups_found": groups_found,
            "exact_groups": exact_groups,
            "similar_groups": similar_groups,
            "total_duplicate_assets": total_dup_assets,
        }

    def list_duplicate_groups(self, status: Optional[str] = None) -> List[Dict]:
        """List duplicate groups with their members."""
        with self._connect() as conn:
            if status:
                groups = conn.execute(
                    "SELECT * FROM duplicate_group WHERE status=? ORDER BY group_id",
                    (status,),
                ).fetchall()
            else:
                groups = conn.execute(
                    "SELECT * FROM duplicate_group ORDER BY group_id"
                ).fetchall()

            result = []
            for g in groups:
                members = conn.execute(
                    """
                    SELECT dgm.*, a.filename, a.primary_path
                    FROM duplicate_group_member dgm
                    LEFT JOIN assets a ON dgm.uid = a.uid
                    WHERE dgm.group_id = ?
                    ORDER BY dgm.fingerprint_distance
                    """,
                    (g["group_id"],),
                ).fetchall()
                result.append({
                    **dict(g),
                    "members": [dict(m) for m in members],
                })
            return result

    # ------------------------------------------------------------------
    # v0.7 Phase B – Duplicate resolution + unavailable assets
    # ------------------------------------------------------------------

    def resolve_duplicate_group(self, group_id: int) -> Dict:
        """Mark a duplicate group as resolved."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_group WHERE group_id=?", (group_id,)
            ).fetchone()
            if not row:
                return {"error": f"group {group_id} not found"}
            conn.execute(
                "UPDATE duplicate_group SET status='resolved', resolved_at=? WHERE group_id=?",
                (self._now(), group_id),
            )
            return {"ok": True, "group_id": group_id, "status": "resolved"}

    def ignore_duplicate_group(self, group_id: int) -> Dict:
        """Mark a duplicate group as ignored."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_group WHERE group_id=?", (group_id,)
            ).fetchone()
            if not row:
                return {"error": f"group {group_id} not found"}
            conn.execute(
                "UPDATE duplicate_group SET status='ignored', resolved_at=? WHERE group_id=?",
                (self._now(), group_id),
            )
            return {"ok": True, "group_id": group_id, "status": "ignored"}

    def set_duplicate_primary(self, group_id: int, uid: str) -> Dict:
        """Set the primary (keep) member of a duplicate group."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_group WHERE group_id=?", (group_id,)
            ).fetchone()
            if not row:
                return {"error": f"group {group_id} not found"}
            member = conn.execute(
                "SELECT * FROM duplicate_group_member WHERE group_id=? AND uid=?",
                (group_id, uid),
            ).fetchone()
            if not member:
                return {"error": f"uid {uid} is not a member of group {group_id}"}
            conn.execute(
                "UPDATE duplicate_group SET primary_uid=? WHERE group_id=?",
                (uid, group_id),
            )
            return {"ok": True, "group_id": group_id, "primary_uid": uid}

    def set_member_decision(self, group_id: int, member_id: int, decision: str) -> Dict:
        """Set keep/remove decision for a duplicate group member."""
        if decision not in ("keep", "remove", "undecided"):
            return {"error": f"invalid decision: {decision}, must be keep|remove|undecided"}
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_group_member WHERE id=? AND group_id=?",
                (member_id, group_id),
            ).fetchone()
            if not row:
                return {"error": f"member {member_id} not found in group {group_id}"}
            conn.execute(
                "UPDATE duplicate_group_member SET keep_decision=? WHERE id=?",
                (decision, member_id),
            )
            return {"ok": True, "member_id": member_id, "decision": decision}

    def list_unavailable_assets(self) -> List[Dict]:
        """List all asset locations that are currently unavailable."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT al.id, al.uid, al.path, al.source_type, al.last_seen_at,
                       a.filename, a.primary_path
                FROM asset_locations al
                JOIN assets a ON al.uid = a.uid
                WHERE al.is_available = 0
                ORDER BY al.last_seen_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # v0.7 – Relink report
    # ------------------------------------------------------------------

    def relink_report(self, uids: Optional[List[str]] = None, since: Optional[str] = None) -> List[Dict]:
        """
        Get path change history for specified assets.

        Args:
            uids: list of asset uids (None = all)
            since: ISO datetime string — only return changes after this time

        Returns: [{uid, changes: [{change_id, old_path, new_path, change_type, source, created_at}]}]
        """
        with self._connect() as conn:
            if uids:
                placeholders = ",".join("?" for _ in uids)
                if since:
                    rows = conn.execute(
                        f"""
                        SELECT * FROM path_change_log
                        WHERE uid IN ({placeholders}) AND created_at > ?
                        ORDER BY uid, created_at
                        """,
                        (*uids, since),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"""
                        SELECT * FROM path_change_log
                        WHERE uid IN ({placeholders})
                        ORDER BY uid, created_at
                        """,
                        tuple(uids),
                    ).fetchall()
            else:
                if since:
                    rows = conn.execute(
                        "SELECT * FROM path_change_log WHERE created_at > ? ORDER BY uid, created_at",
                        (since,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM path_change_log ORDER BY uid, created_at"
                    ).fetchall()

            # Group by uid
            from collections import defaultdict
            grouped: Dict[str, List[Dict]] = defaultdict(list)
            for r in rows:
                grouped[r["uid"]].append(dict(r))

            return [{"uid": uid, "changes": changes} for uid, changes in grouped.items()]

    # ------------------------------------------------------------------
    # v0.7 Phase C-1 – Project relink (Jianying工程自动relink)
    # ------------------------------------------------------------------

    def _match_path_to_uid(
        self,
        conn: sqlite3.Connection,
        path: str,
        filename: str,
        size_hint: Optional[int] = None,
    ) -> Tuple[Optional[str], str, float, str]:
        """
        Reverse-lookup: given a file path and filename, find the asset uid.

        Returns (uid, match_type, confidence, reason).
        Match priority:
          1. Exact path in asset_locations  → confidence 1.0
          2. primary_path in assets         → confidence 1.0
          3. filename in assets with secondary validation (size check)
             - unique filename match + size matches → confidence 0.9
             - unique filename match, size unknown  → confidence 0.7
             - multiple filename matches, one size matches → confidence 0.6
             - multiple filename matches, no size info → confidence 0.3
        """
        # 1. Exact path match in asset_locations
        row = conn.execute(
            "SELECT uid FROM asset_locations WHERE path = ?", (path,)
        ).fetchone()
        if row:
            return (row["uid"], "path", 1.0, "exact_path_in_locations")

        # 2. primary_path match in assets
        row = conn.execute(
            "SELECT uid FROM assets WHERE primary_path = ?", (path,)
        ).fetchone()
        if row:
            return (row["uid"], "path", 1.0, "primary_path_match")

        # 3. filename match with secondary validation
        if filename:
            rows = conn.execute(
                "SELECT uid, size_bytes FROM assets WHERE filename = ?", (filename,)
            ).fetchall()

            if not rows:
                return (None, "none", 0.0, "no_match")

            if len(rows) == 1:
                # Unique filename match
                candidate = rows[0]
                if size_hint and candidate["size_bytes"]:
                    if size_hint == candidate["size_bytes"]:
                        return (candidate["uid"], "filename", 0.9, "unique_filename_size_confirmed")
                    else:
                        # Size mismatch — likely a different file with the same name
                        return (None, "none", 0.0, "filename_match_size_mismatch")
                # No size info to validate — lower confidence
                return (candidate["uid"], "filename", 0.7, "unique_filename_no_size_check")

            # Multiple filename matches — try size-based disambiguation
            if size_hint:
                size_matches = [r for r in rows if r["size_bytes"] == size_hint]
                if len(size_matches) == 1:
                    return (size_matches[0]["uid"], "filename", 0.6, "filename_multi_size_disambiguated")
                elif len(size_matches) > 1:
                    # Multiple size matches — ambiguous, pick first but low confidence
                    return (size_matches[0]["uid"], "filename", 0.3, "filename_multi_size_ambiguous")
            # Multiple filename matches, no size info — too risky
            return (None, "none", 0.0, "filename_multi_no_size")

        return (None, "none", 0.0, "no_match")

    def parse_project_references(self, project_path: str, project_type: str = "jianying") -> List[Dict]:
        """
        Parse media references from a project file.

        Delegates to the appropriate ProjectRelinkAdapter.

        Returns: [{asset_name, old_path, source_ref, media_type}]
        """
        p = Path(project_path)
        if not p.exists():
            return []
        try:
            adapter = _get_relink_adapter(project_type)
            return adapter.parse_references(str(p))
        except Exception:
            return []

    def validate_project(self, project_path: str, project_type: str = "jianying") -> Dict:
        """
        Validate a project file structure before analysis.

        Delegates to the appropriate ProjectRelinkAdapter.

        Returns: {valid, errors, warnings, version_info}
        """
        p = Path(project_path)
        if not p.exists():
            return {"valid": False, "errors": [f"File not found: {project_path}"], "warnings": [], "version_info": {}}
        try:
            adapter = _get_relink_adapter(project_type)
            return adapter.validate(str(p))
        except Exception as exc:
            return {"valid": False, "errors": [str(exc)], "warnings": [], "version_info": {}}

    def build_project_relink_map(self, project_path: str, project_type: str = "jianying") -> Dict:
        """
        Build a structured relink map for a project.

        For each media reference in the project, determine:
        - stable: old_path still exists on disk
        - relinked: old_path broken but new path found via library
        - missing: uid found in library but no available path
        - unmatched: cannot match to any library asset

        Returns: {
            project_path, project_type,
            summary: {total_refs, stable_refs, changed_refs, missing_refs, unmatched_refs},
            items: [{uid, asset_name, source_ref, old_path, new_path, status,
                     fingerprint_match_type, media_type, match_confidence, reason}]
        }
        """
        refs = self.parse_project_references(project_path, project_type)
        items: List[Dict] = []

        # Build size map from parsed refs (adapter may return size_bytes) + raw JSON fallback
        size_map: Dict[str, int] = {}
        for ref in refs:
            sz = ref.get("size_bytes")
            if sz and isinstance(sz, (int, float)) and sz > 0:
                size_map[ref["old_path"]] = int(sz)
        # Also try to extract sizes from raw project JSON (e.g. Jianying "size" / "file_size" fields)
        try:
            with open(project_path, "r", encoding="utf-8") as f:
                draft = json.load(f)
            for category in ("videos", "audios"):
                for entry in draft.get("materials", {}).get(category, []):
                    p = (entry.get("path") or "").strip()
                    sz = entry.get("size") or entry.get("file_size") or 0
                    if p and p not in size_map and isinstance(sz, (int, float)) and sz > 0:
                        size_map[p] = int(sz)
        except Exception:
            pass

        with self._connect() as conn:
            for ref in refs:
                old_path = ref["old_path"]
                asset_name = ref["asset_name"]
                source_ref = ref.get("source_ref", "")
                media_type = ref.get("media_type", "")

                # 1. Check if old_path still exists
                if Path(old_path).exists():
                    items.append({
                        "uid": None,
                        "asset_name": asset_name,
                        "source_ref": source_ref,
                        "old_path": old_path,
                        "new_path": None,
                        "status": "stable",
                        "fingerprint_match_type": None,
                        "media_type": media_type,
                        "match_confidence": 1.0,
                        "reason": "path_exists",
                    })
                    continue

                # 2-4. Try to match to library uid (with size hint for secondary validation)
                size_hint = size_map.get(old_path)
                uid, match_type, confidence, reason = self._match_path_to_uid(
                    conn, old_path, asset_name, size_hint=size_hint
                )

                if uid is None:
                    # unmatched
                    items.append({
                        "uid": None,
                        "asset_name": asset_name,
                        "source_ref": source_ref,
                        "old_path": old_path,
                        "new_path": None,
                        "status": "unmatched",
                        "fingerprint_match_type": "none",
                        "media_type": media_type,
                        "match_confidence": 0.0,
                        "reason": reason,
                    })
                    continue

                # 5. Found uid — get asset info for _best_existing_path
                asset_row = conn.execute(
                    "SELECT filename, sha256, size_bytes, primary_path FROM assets WHERE uid = ?",
                    (uid,),
                ).fetchone()

                if asset_row:
                    best = self._best_existing_path(
                        conn,
                        uid,
                        fallback=old_path,
                        filename=asset_row["filename"],
                        sha256=asset_row["sha256"],
                        size_bytes=asset_row["size_bytes"],
                        allow_relocate=True,
                        update_availability=False,
                    )
                else:
                    best = None

                if best and Path(best).exists() and best != old_path:
                    items.append({
                        "uid": uid,
                        "asset_name": asset_name,
                        "source_ref": source_ref,
                        "old_path": old_path,
                        "new_path": best,
                        "status": "relinked",
                        "fingerprint_match_type": match_type,
                        "media_type": media_type,
                        "match_confidence": confidence,
                        "reason": reason,
                    })
                else:
                    items.append({
                        "uid": uid,
                        "asset_name": asset_name,
                        "source_ref": source_ref,
                        "old_path": old_path,
                        "new_path": None,
                        "status": "missing",
                        "fingerprint_match_type": match_type,
                        "media_type": media_type,
                        "match_confidence": confidence,
                        "reason": reason,
                    })

        # Build summary
        stable = sum(1 for i in items if i["status"] == "stable")
        relinked = sum(1 for i in items if i["status"] == "relinked")
        missing = sum(1 for i in items if i["status"] == "missing")
        unmatched = sum(1 for i in items if i["status"] == "unmatched")

        return {
            "project_path": str(project_path),
            "project_type": project_type,
            "summary": {
                "total_refs": len(items),
                "stable_refs": stable,
                "changed_refs": relinked,
                "missing_refs": missing,
                "unmatched_refs": unmatched,
            },
            "items": items,
        }

    def create_project_relink_job(self, project_path: str, project_type: str = "jianying") -> Dict:
        """
        Create a relink analysis job, run build_project_relink_map, and persist results.

        Returns: {job_id, project_path, project_type, status, summary, items}
        """
        p = Path(project_path)
        if not p.exists():
            return {"error": f"Project file not found: {project_path}"}

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO project_relink_job (project_path, project_type, status)
                VALUES (?, ?, 'running')
                """,
                (str(p), project_type),
            )
            job_id = cursor.lastrowid

        try:
            # Extract version info via adapter
            version_info_str = None
            try:
                adapter = _get_relink_adapter(project_type)
                vi = adapter.get_version_info(str(p))
                if vi:
                    version_info_str = json.dumps(vi, ensure_ascii=False)
            except Exception:
                pass

            result = self.build_project_relink_map(str(p), project_type)
            summary = result["summary"]
            items = result["items"]

            with self._connect() as conn:
                for item in items:
                    conn.execute(
                        """
                        INSERT INTO project_relink_item
                            (job_id, uid, asset_name, old_path, new_path, status,
                             source_ref, fingerprint_match_type, media_type,
                             match_confidence, reason, applied)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            job_id,
                            item.get("uid"),
                            item.get("asset_name"),
                            item.get("old_path"),
                            item.get("new_path"),
                            item["status"],
                            item.get("source_ref"),
                            item.get("fingerprint_match_type"),
                            item.get("media_type"),
                            item.get("match_confidence"),
                            item.get("reason"),
                        ),
                    )
                conn.execute(
                    """
                    UPDATE project_relink_job
                    SET status='done',
                        total_refs=?, stable_refs=?, changed_refs=?,
                        missing_refs=?, unmatched_refs=?,
                        result_json=?, version_info=?,
                        updated_at=?
                    WHERE job_id=?
                    """,
                    (
                        summary["total_refs"],
                        summary["stable_refs"],
                        summary["changed_refs"],
                        summary["missing_refs"],
                        summary["unmatched_refs"],
                        json.dumps(result, ensure_ascii=False),
                        version_info_str,
                        self._now(),
                        job_id,
                    ),
                )

            return {
                "job_id": job_id,
                "project_path": str(p),
                "project_type": project_type,
                "status": "done",
                "summary": summary,
                "items": items,
            }

        except Exception as exc:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE project_relink_job SET status='failed', error_message=?, updated_at=? WHERE job_id=?",
                    (str(exc), self._now(), job_id),
                )
            return {"error": str(exc), "job_id": job_id, "status": "failed"}

    def get_project_relink_job(self, job_id: int) -> Dict:
        """Get a relink job with its items."""
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? ORDER BY item_id",
                (job_id,),
            ).fetchall()

            job = dict(job_row)
            job.pop("result_json", None)  # Don't send full blob in normal queries
            job["items"] = [self._item_with_effective_fields(r) for r in items]
            return job

    def export_project_relink_map(self, job_id: int) -> Dict:
        """Export a relink job as a standardized relink map for download."""
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT uid, asset_name, old_path, new_path, status, source_ref, "
                "fingerprint_match_type, media_type, match_confidence, reason, applied "
                "FROM project_relink_item WHERE job_id = ? ORDER BY item_id",
                (job_id,),
            ).fetchall()

            return {
                "project_path": job_row["project_path"],
                "project_type": job_row["project_type"],
                "summary": {
                    "total_refs": job_row["total_refs"],
                    "stable_refs": job_row["stable_refs"],
                    "changed_refs": job_row["changed_refs"],
                    "missing_refs": job_row["missing_refs"],
                    "unmatched_refs": job_row["unmatched_refs"],
                },
                "items": [dict(r) for r in items],
            }

    def list_project_relink_jobs(
        self, project_path: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> List[Dict]:
        """
        List recent relink jobs, optionally filtered by project_path.

        Returns list of job dicts (without items), ordered by created_at DESC.
        """
        with self._connect() as conn:
            cols = (
                "job_id, project_path, project_type, status, total_refs, "
                "stable_refs, changed_refs, missing_refs, unmatched_refs, "
                "apply_count, version_info, error_message, "
                "retry_of, retry_count, last_error_at, "
                "predecessor_job_id, handover_at, "
                "created_at, updated_at"
            )
            if project_path:
                rows = conn.execute(
                    f"SELECT {cols} FROM project_relink_job WHERE project_path = ? "
                    "ORDER BY job_id DESC LIMIT ? OFFSET ?",
                    (project_path, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {cols} FROM project_relink_job "
                    "ORDER BY job_id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [dict(r) for r in rows]

    def compare_project_relink_jobs(self, job_id_a: int, job_id_b: int) -> Dict:
        """
        Compare two relink jobs and return delta analysis.

        Tracks which items changed status between job A and job B:
        - newly_relinked: was missing/unmatched in A, now relinked in B
        - newly_missing: was stable/relinked in A, now missing/unmatched in B
        - still_unmatched: unmatched in both
        - status_changed: any status change

        Returns: {job_id_a, job_id_b, newly_relinked, newly_missing,
                  still_unmatched, status_changed, summary}
        """
        with self._connect() as conn:
            rows_a = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ?", (job_id_a,)
            ).fetchall()
            rows_b = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ?", (job_id_b,)
            ).fetchall()

        if not rows_a and not rows_b:
            return {"error": f"No items found for job_id {job_id_a} or {job_id_b}"}

        items_a = {i["old_path"]: dict(i) for i in rows_a}
        items_b = {i["old_path"]: dict(i) for i in rows_b}

        newly_relinked: List[Dict] = []
        newly_missing: List[Dict] = []
        still_unmatched: List[Dict] = []
        status_changed: List[Dict] = []

        all_paths = sorted(set(items_a.keys()) | set(items_b.keys()))
        for path in all_paths:
            a = items_a.get(path)
            b = items_b.get(path)
            sa = a["status"] if a else None
            sb = b["status"] if b else None
            name = (b or a or {}).get("asset_name", "")

            if sa != sb:
                entry = {"old_path": path, "status_a": sa, "status_b": sb, "asset_name": name}
                status_changed.append(entry)
                if sb == "relinked" and sa in (None, "missing", "unmatched"):
                    newly_relinked.append(entry)
                elif sb in ("missing", "unmatched") and sa in ("stable", "relinked"):
                    newly_missing.append(entry)
            elif sa == "unmatched" and sb == "unmatched":
                still_unmatched.append({"old_path": path, "asset_name": name})

        return {
            "job_id_a": job_id_a,
            "job_id_b": job_id_b,
            "newly_relinked": newly_relinked,
            "newly_missing": newly_missing,
            "still_unmatched": still_unmatched,
            "status_changed": status_changed,
            "summary": {
                "newly_relinked": len(newly_relinked),
                "newly_missing": len(newly_missing),
                "still_unmatched": len(still_unmatched),
                "total_changes": len(status_changed),
            },
        }

    def apply_project_relink(
        self,
        job_id: int,
        output_path: Optional[str] = None,
        force: bool = False,
        naming_rule: str = "default",
    ) -> Dict:
        """
        Apply relink results to a project copy.

        Safety rules (hardcoded, cannot be overridden):
        1. ONLY items with status='relinked' are processed.
        2. Output is ALWAYS written to a new file — original is NEVER modified.
        3. If output_path == project_path, it is rejected.
        4. new_path must exist on disk at apply time; stale entries are skipped.
        5. Each applied item is marked with applied=1, applied_at set.
        6. Idempotent: if all relinked items already applied, returns error (unless force=True).
        7. apply_count on job is incremented.

        Args:
            job_id:      ID of a 'done' relink job.
            output_path: Optional explicit output path. If None, auto-generated.
            force:       If True, skip idempotency guard and allow re-apply.
            naming_rule: "default" → {stem}_relinked_{job_id}{suffix}
                         "timestamped" → {stem}_relinked_{job_id}_{TS}{suffix}

        Returns: {output_path, applied, skipped, apply_detail}
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            if job_row["status"] != "done":
                return {"error": f"Job {job_id} status is '{job_row['status']}', expected 'done'"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? AND status = 'relinked'",
                (job_id,),
            ).fetchall()

        if not items:
            return {"output_path": None, "applied": 0, "skipped": 0}

        # Idempotency guard
        if not force:
            already_applied = all(item["applied"] == 1 for item in items)
            if already_applied:
                return {
                    "error": "All relinked items already applied. Use force=True to re-apply.",
                    "already_applied": True,
                }

        project_path = Path(job_row["project_path"])
        if not project_path.exists():
            return {"error": f"Original project file not found: {project_path}"}

        # Determine output path
        if not output_path:
            stem = project_path.stem
            suffix = project_path.suffix
            if naming_rule == "timestamped":
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = str(project_path.parent / f"{stem}_relinked_{job_id}_{ts}{suffix}")
            else:
                candidate = project_path.parent / f"{stem}_relinked_{job_id}{suffix}"
                if candidate.exists():
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_path = str(project_path.parent / f"{stem}_relinked_{job_id}_{ts}{suffix}")
                else:
                    output_path = str(candidate)

        out = Path(output_path).resolve()

        # Safety rule 3: never overwrite the original
        if out == project_path.resolve():
            return {"error": "output_path must differ from the original project file"}

        # D-1 hard rule #3: if output file exists and not force, conflict
        if out.exists() and not force:
            return {
                "error": f"Output file already exists: {out}. Use force=True to overwrite.",
                "output_conflict": True,
            }

        # Build old_path → (new_path, item_id, asset_name) mapping — ONLY relinked items
        path_map: Dict[str, Tuple[str, int, str]] = {}
        skipped_items: List[Dict] = []
        for item in items:
            old = item["old_path"]
            # D-2: prefer manual_new_path when manually bound
            new = item["manual_new_path"] or item["new_path"]
            item_id = item["item_id"]
            name = item["asset_name"] or ""
            # Safety rule 4: verify new_path still exists on disk
            if old and new and Path(new).exists():
                path_map[old] = (new, item_id, name)
            else:
                reason = "new_path does not exist" if new else "no new_path"
                skipped_items.append({"item_id": item_id, "old_path": old, "new_path": new, "asset_name": name, "reason": reason})

        # Delegate file rewriting to adapter
        project_type = job_row["project_type"] or "jianying"
        try:
            adapter = _get_relink_adapter(project_type)
            simple_map = {old: new for old, (new, _, _) in path_map.items()}
            adapter.apply_relink(str(project_path), str(out), simple_map)
        except Exception as exc:
            return {"error": f"Adapter apply failed: {exc}"}

        # Collect applied items detail
        applied_item_ids: List[int] = []
        applied_items_detail: List[Dict] = []
        for old_p, (new_p, item_id, name) in path_map.items():
            applied_item_ids.append(item_id)
            applied_items_detail.append({
                "item_id": item_id,
                "old_path": old_p,
                "new_path": new_p,
                "asset_name": name,
            })

        now = self._now()

        # Mark applied items in DB + increment apply_count
        with self._connect() as conn:
            if applied_item_ids:
                placeholders = ",".join("?" for _ in applied_item_ids)
                conn.execute(
                    f"UPDATE project_relink_item SET applied = 1, applied_at = ? WHERE item_id IN ({placeholders})",
                    [now] + applied_item_ids,
                )
            conn.execute(
                "UPDATE project_relink_job SET apply_count = apply_count + 1, updated_at = ? WHERE job_id = ?",
                (now, job_id),
            )
            # Log path changes
            for old_p, (new_p, _, _) in path_map.items():
                uid_row = conn.execute(
                    "SELECT uid FROM asset_locations WHERE path = ? OR path = ?",
                    (old_p, new_p),
                ).fetchone()
                if uid_row:
                    self._log_path_change(
                        conn, uid_row["uid"], old_p, new_p, "relocated", "project_relink"
                    )

            # D-3: write output record
            cursor = conn.execute(
                "INSERT INTO project_relink_output (job_id, output_path, naming_rule, applied_count, skipped_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, str(out), naming_rule, len(applied_item_ids), len(skipped_items), now),
            )
            output_id = cursor.lastrowid

            # D-3: audit log
            self._log_project_relink_action(
                conn, job_id, "apply",
                payload={"output_path": str(out), "applied": len(applied_item_ids), "skipped": len(skipped_items), "output_id": output_id},
            )

        return {
            "output_path": str(out),
            "applied": len(applied_item_ids),
            "skipped": len(skipped_items),
            "output_id": output_id,
            "apply_detail": {
                "applied_items": applied_items_detail,
                "skipped_items": skipped_items,
            },
        }

    # ------------------------------------------------------------------
    # v0.7 Phase D-1 – Task Center + Missing Fix
    # ------------------------------------------------------------------

    def retry_project_relink_job(self, job_id: int) -> Dict:
        """
        Retry a *failed* relink job by creating a new job that re-reads the
        current project file.  The original job is never overwritten.

        Rules (D-1 hard rule #2):
          - Only jobs with status='failed' can be retried.
          - A new job row is always created (retry_of → original job_id).
          - retry_count on original job is incremented.
        """
        with self._connect() as conn:
            original = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()

        if not original:
            return {"error": f"Job {job_id} not found"}

        if original["status"] != "failed":
            return {"error": f"Only failed jobs can be retried. Job {job_id} status is '{original['status']}'"}

        project_path = original["project_path"]
        project_type = original["project_type"] or "jianying"

        # Create new job with retry_of pointing to original
        p = Path(project_path)
        if not p.exists():
            return {"error": f"Project file not found: {project_path}"}

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO project_relink_job
                    (project_path, project_type, status, retry_of)
                VALUES (?, ?, 'running', ?)
                """,
                (str(p), project_type, job_id),
            )
            new_job_id = cursor.lastrowid
            # Increment retry_count on original
            conn.execute(
                "UPDATE project_relink_job SET retry_count = retry_count + 1, updated_at = ? WHERE job_id = ?",
                (self._now(), job_id),
            )

        try:
            # Extract version info
            version_info_str = None
            try:
                adapter = _get_relink_adapter(project_type)
                vi = adapter.get_version_info(str(p))
                if vi:
                    version_info_str = json.dumps(vi, ensure_ascii=False)
            except Exception:
                pass

            result = self.build_project_relink_map(str(p), project_type)
            summary = result["summary"]
            items = result["items"]

            with self._connect() as conn:
                for item in items:
                    conn.execute(
                        """
                        INSERT INTO project_relink_item
                            (job_id, uid, asset_name, old_path, new_path, status,
                             source_ref, fingerprint_match_type, media_type,
                             match_confidence, reason, applied)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            new_job_id,
                            item.get("uid"),
                            item.get("asset_name"),
                            item.get("old_path"),
                            item.get("new_path"),
                            item["status"],
                            item.get("source_ref"),
                            item.get("fingerprint_match_type"),
                            item.get("media_type"),
                            item.get("match_confidence"),
                            item.get("reason"),
                        ),
                    )
                conn.execute(
                    """
                    UPDATE project_relink_job
                    SET status='done',
                        total_refs=?, stable_refs=?, changed_refs=?,
                        missing_refs=?, unmatched_refs=?,
                        result_json=?, version_info=?,
                        updated_at=?
                    WHERE job_id=?
                    """,
                    (
                        summary["total_refs"],
                        summary["stable_refs"],
                        summary["changed_refs"],
                        summary["missing_refs"],
                        summary["unmatched_refs"],
                        json.dumps(result, ensure_ascii=False),
                        version_info_str,
                        self._now(),
                        new_job_id,
                    ),
                )

            # D-3: audit log
            self._log_project_relink_action(
                conn, new_job_id, "retry",
                payload={"retry_of": job_id, "project_path": str(p)},
            )

            return {
                "job_id": new_job_id,
                "retry_of": job_id,
                "project_path": str(p),
                "project_type": project_type,
                "status": "done",
                "summary": summary,
                "items": items,
            }

        except Exception as exc:
            now = self._now()
            with self._connect() as conn:
                conn.execute(
                    "UPDATE project_relink_job SET status='failed', error_message=?, last_error_at=?, updated_at=? WHERE job_id=?",
                    (str(exc), now, now, new_job_id),
                )
            return {"error": str(exc), "job_id": new_job_id, "status": "failed"}

    def preview_project_relink_apply(self, job_id: int) -> Dict:
        """
        Read-only preview of what apply_project_relink would do.

        D-1 hard rule #3: must check output path conflicts.
        Does NOT modify any state.
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            if job_row["status"] != "done":
                return {"error": f"Job {job_id} status is '{job_row['status']}', expected 'done'"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? AND status = 'relinked'",
                (job_id,),
            ).fetchall()

        project_path = Path(job_row["project_path"])
        if not project_path.exists():
            return {"error": f"Original project file not found: {project_path}"}

        # Generate preview output path (same logic as apply)
        stem = project_path.stem
        suffix = project_path.suffix
        candidate = project_path.parent / f"{stem}_relinked_{job_id}{suffix}"
        output_exists = candidate.exists()
        if output_exists:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_preview = str(project_path.parent / f"{stem}_relinked_{job_id}_{ts}{suffix}")
        else:
            output_preview = str(candidate)

        will_apply = []
        will_skip = []
        already_applied_count = 0

        for item in items:
            # D-2: prefer manual_new_path when manually bound
            effective_new = item["manual_new_path"] or item["new_path"]
            d = {
                "item_id": item["item_id"],
                "asset_name": item["asset_name"] or "",
                "old_path": item["old_path"],
                "new_path": effective_new,
                "manual_uid": item["manual_uid"],
                "binding_mode": "manual" if item["manual_uid"] else "system",
            }
            if item["applied"] == 1:
                already_applied_count += 1
            if effective_new and Path(effective_new).exists():
                will_apply.append(d)
            else:
                reason = "new_path does not exist" if effective_new else "no new_path"
                d["reason"] = reason
                will_skip.append(d)

        warnings = []
        if already_applied_count > 0:
            warnings.append(f"{already_applied_count} item(s) already applied previously")
        if already_applied_count == len(items) and items:
            warnings.append("All relinked items already applied. Will need force=True to re-apply.")
        if output_exists:
            warnings.append(f"Default output path already exists; using timestamped name instead")

        # D-3: diff_items = will_apply + will_skip combined with reason/binding_mode
        diff_items = []
        for d in will_apply:
            di = dict(d)
            di["action"] = "apply"
            di.setdefault("reason", "")
            diff_items.append(di)
        for d in will_skip:
            di = dict(d)
            di["action"] = "skip"
            diff_items.append(di)

        # D-3: audit log (preview is read-only, but we record it)
        with self._connect() as conn2:
            self._log_project_relink_action(
                conn2, job_id, "preview_apply",
                payload={"will_apply": len(will_apply), "will_skip": len(will_skip)},
            )

        return {
            "job_id": job_id,
            "project_path": str(project_path),
            "total_relinked": len(items),
            "will_apply": will_apply,
            "will_skip": will_skip,
            "diff_items": diff_items,
            "already_applied": already_applied_count,
            "output_path_preview": output_preview,
            "output_path_conflict": output_exists,
            "warnings": warnings,
            "summary": {
                "total_refs": job_row["total_refs"],
                "stable_refs": job_row["stable_refs"],
                "changed_refs": job_row["changed_refs"],
                "missing_refs": job_row["missing_refs"],
                "unmatched_refs": job_row["unmatched_refs"],
            },
        }

    def export_missing_items(self, job_id: int, fmt: str = "json") -> Dict:
        """
        Export missing + unmatched items with standardized reason field.

        D-1 hard rule #4: every item must include reason for traceability.
        Reads from project_relink_item (source of truth, hard rule #1).
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT job_id, project_path, project_type FROM project_relink_job WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                """
                SELECT item_id, uid, asset_name, old_path, status,
                       source_ref, fingerprint_match_type, media_type,
                       match_confidence, reason
                FROM project_relink_item
                WHERE job_id = ? AND status IN ('missing', 'unmatched')
                ORDER BY status, asset_name
                """,
                (job_id,),
            ).fetchall()

        item_list = [dict(r) for r in items]
        filenames = set(r["asset_name"] for r in item_list if r["asset_name"])
        missing_count = sum(1 for r in item_list if r["status"] == "missing")
        unmatched_count = sum(1 for r in item_list if r["status"] == "unmatched")

        # D-3: audit log
        with self._connect() as conn2:
            self._log_project_relink_action(
                conn2, job_id, "export_missing",
                payload={"format": fmt, "total": len(item_list)},
            )

        summary = {
            "total_missing": missing_count,
            "total_unmatched": unmatched_count,
            "unique_filenames": len(filenames),
        }

        if fmt == "csv":
            import io
            import csv
            output = io.StringIO()
            writer = csv.writer(output)
            header = [
                "item_id", "status", "asset_name", "old_path", "uid",
                "source_ref", "media_type", "fingerprint_match_type",
                "match_confidence", "reason",
            ]
            writer.writerow(header)
            for r in item_list:
                writer.writerow([r.get(h, "") for h in header])
            return {
                "csv_content": output.getvalue(),
                "filename": f"missing_items_{job_id}.csv",
                "summary": summary,
            }

        return {
            "items": item_list,
            "summary": summary,
            "filename": f"missing_items_{job_id}.json",
            "project_path": job_row["project_path"],
        }

    # ------------------------------------------------------------------
    # v0.7 Phase D-1 – Candidate suggestion for missing items
    # ------------------------------------------------------------------

    def suggest_candidates_for_missing(
        self, job_id: int, max_candidates: int = 5
    ) -> Dict:
        """
        Suggest library assets that may match missing/unmatched items.

        For each missing/unmatched item, search by filename similarity.
        Uses difflib.SequenceMatcher — no new dependencies.

        D-1 hard rule #5: read-only, never auto-write to new_path or change status.
        """
        import difflib

        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT job_id, project_path FROM project_relink_job WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                """
                SELECT item_id, uid, asset_name, old_path, status, reason
                FROM project_relink_item
                WHERE job_id = ? AND status IN ('missing', 'unmatched')
                ORDER BY asset_name
                """,
                (job_id,),
            ).fetchall()

            if not items:
                return {"job_id": job_id, "suggestions": [], "total_items": 0}

            suggestions = []

            for item in items:
                asset_name = item["asset_name"] or ""
                stem = Path(asset_name).stem if asset_name else ""
                if not stem:
                    suggestions.append(
                        {
                            "item_id": item["item_id"],
                            "asset_name": asset_name,
                            "status": item["status"],
                            "candidates": [],
                        }
                    )
                    continue

                # Search for similar filenames in assets table
                like_pattern = f"%{stem}%"
                rows = conn.execute(
                    """
                    SELECT uid, filename, primary_path, source_type
                    FROM assets
                    WHERE filename LIKE ?
                    ORDER BY filename
                    LIMIT ?
                    """,
                    (like_pattern, max_candidates * 3),
                ).fetchall()

                # Score by similarity and pick top N
                scored = []
                for r in rows:
                    candidate_stem = Path(r["filename"]).stem if r["filename"] else ""
                    sim = difflib.SequenceMatcher(
                        None, stem.lower(), candidate_stem.lower()
                    ).ratio()
                    # Check availability via best existing path
                    best = self._best_existing_path(
                        conn,
                        r["uid"],
                        r["primary_path"],
                        filename=r["filename"],
                        update_availability=False,
                    )
                    scored.append(
                        {
                            "uid": r["uid"],
                            "filename": r["filename"],
                            "path": best or r["primary_path"],
                            "available": best is not None and Path(best).exists(),
                            "similarity": round(sim, 3),
                        }
                    )

                # Sort by similarity descending, take top N
                scored.sort(key=lambda x: x["similarity"], reverse=True)
                top = scored[:max_candidates]

                suggestions.append(
                    {
                        "item_id": item["item_id"],
                        "asset_name": asset_name,
                        "status": item["status"],
                        "candidates": top,
                    }
                )

            return {
                "job_id": job_id,
                "suggestions": suggestions,
                "total_items": len(suggestions),
            }

    # ------------------------------------------------------------------
    # v0.7 Phase D-3 – Reason Enum + Action Log + Workbench
    # ------------------------------------------------------------------

    PROJECT_RELINK_REASON_LABELS = {
        "path_still_valid": "原路径仍可用",
        "path_matched_in_locations": "通过历史路径匹配到素材",
        "primary_path_matched": "通过主路径匹配到素材",
        "filename_matched": "通过文件名匹配到素材",
        "filename_ambiguous": "同名素材过多，无法安全确认",
        "uid_has_no_available_path": "已识别素材，但当前没有可用路径",
        "manual_binding_applied": "已使用人工绑定路径",
        "manual_binding_missing": "已人工绑定素材，但绑定素材当前无可用路径",
        "no_library_match": "未匹配到素材库",
        "media_type_conflict": "素材类型不兼容",
    }

    @staticmethod
    def _log_project_relink_action(conn, job_id, action_type, item_id=None, payload=None, operator="system"):
        """Write an audit log entry to project_relink_action_log."""
        import json as _json
        payload_str = _json.dumps(payload, ensure_ascii=False) if payload else None
        conn.execute(
            "INSERT INTO project_relink_action_log (job_id, item_id, action_type, operator, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (job_id, item_id, action_type, operator, payload_str),
        )

    def get_project_relink_action_log(self, job_id: int, item_id: int = None) -> List[Dict]:
        """Return audit log entries for a job, optionally filtered by item."""
        with self._connect() as conn:
            if item_id:
                rows = conn.execute(
                    "SELECT * FROM project_relink_action_log WHERE job_id = ? AND item_id = ? ORDER BY action_id",
                    (job_id, item_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM project_relink_action_log WHERE job_id = ? ORDER BY action_id",
                    (job_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # v0.7 Phase D-2 – Manual Binding Loop
    # ------------------------------------------------------------------
    #
    # STATE MACHINE for project_relink_item (D-2 complete):
    #
    # [Initial scan] build_project_relink_map
    #   stable     <- Path(old_path).exists()
    #   relinked   <- uid matched + _best_existing_path found
    #   missing    <- uid matched + no available path
    #   unmatched  <- no uid match
    #
    # [Manual binding] bind_project_relink_item
    #   missing/unmatched  --bind(uid)--> relinked  (if path found)
    #   missing/unmatched  --bind(uid)--> missing   (uid set, no file)
    #   stable             --bind()-->    ERROR
    #
    # [Unbind] unbind_project_relink_item
    #   any(manual_uid)  --unbind()--> recalculate from original system match
    #
    # [Refresh] refresh_project_relink_items
    #   all non-stable  --> re-check _best_existing_path --> update status+path
    #
    # [Apply] apply_project_relink
    #   relinked --> path_map: prefer manual_new_path > system new_path

    def _recalc_project_relink_job_summary(
        self, conn, job_id: int
    ) -> None:
        """
        Recalculate job summary counts from current item statuses.

        D-2 rule #1: must be called after bind/unbind/refresh to keep
        job-level summary consistent with item-level truth.
        """
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='stable' THEN 1 ELSE 0 END) AS stable,
                SUM(CASE WHEN status='relinked' THEN 1 ELSE 0 END) AS changed,
                SUM(CASE WHEN status='missing' THEN 1 ELSE 0 END) AS missing,
                SUM(CASE WHEN status='unmatched' THEN 1 ELSE 0 END) AS unmatched
            FROM project_relink_item
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        conn.execute(
            """
            UPDATE project_relink_job
            SET total_refs=?, stable_refs=?, changed_refs=?,
                missing_refs=?, unmatched_refs=?, updated_at=?
            WHERE job_id=?
            """,
            (
                row["total"],
                row["stable"],
                row["changed"],
                row["missing"],
                row["unmatched"],
                self._now(),
                job_id,
            ),
        )

    @staticmethod
    def _infer_media_category(filename: str) -> Optional[str]:
        """Infer media category from filename extension for bind validation."""
        if not filename:
            return None
        ext = Path(filename).suffix.lower()
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mts"}
        audio_exts = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"}
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic"}
        if ext in video_exts:
            return "video"
        if ext in audio_exts:
            return "audio"
        if ext in image_exts:
            return "image"
        return None

    def bind_project_relink_item(
        self, item_id: int, uid: str, decision_source: str = "candidate"
    ) -> Dict:
        """
        Bind a library asset to a missing/unmatched item.

        D-2 rules:
        - Only missing/unmatched items can be bound (not stable).
        - Sets manual_uid/manual_new_path/manual_decision_source/manual_bound_at.
        - NEVER overwrites system fields: uid, fingerprint_match_type,
          match_confidence, reason.
        - Validates media_type compatibility (rule #5).
        - Recalculates job summary after change (rule #1).
        - Returns item with effective_uid/effective_new_path/binding_mode (rule #4).
        """
        with self._connect() as conn:
            item = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if not item:
                return {"error": f"Item {item_id} not found"}

            if item["status"] not in ("missing", "unmatched"):
                return {
                    "error": f"Can only bind missing or unmatched items, "
                    f"got status='{item['status']}'"
                }

            # Validate uid exists in library
            asset_row = conn.execute(
                "SELECT uid, filename, source_type FROM assets WHERE uid = ?",
                (uid,),
            ).fetchone()
            if not asset_row:
                return {"error": f"Asset uid '{uid}' not found in library"}

            # Rule #5: validate media_type compatibility
            item_media = item["media_type"]  # video / audio from project parse
            asset_category = self._infer_media_category(asset_row["filename"])
            if (
                item_media
                and asset_category
                and item_media != asset_category
            ):
                return {
                    "error": f"Media type mismatch: item is '{item_media}' "
                    f"but asset '{asset_row['filename']}' is '{asset_category}'"
                }

            # Find best existing path for the bound uid
            best_path = self._best_existing_path(
                conn,
                uid,
                fallback=None,
                filename=asset_row["filename"],
                update_availability=False,
            )

            now = self._now()
            if best_path and Path(best_path).exists():
                # Freeze rule §2.4: bind must NOT overwrite system new_path.
                # Manual path goes to manual_new_path only; system new_path preserved.
                conn.execute(
                    """
                    UPDATE project_relink_item
                    SET manual_uid=?, manual_new_path=?,
                        manual_decision_source=?, manual_bound_at=?,
                        status='relinked'
                    WHERE item_id=?
                    """,
                    (uid, best_path, decision_source, now, item_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE project_relink_item
                    SET manual_uid=?, manual_new_path=NULL,
                        manual_decision_source=?, manual_bound_at=?,
                        status='missing'
                    WHERE item_id=?
                    """,
                    (uid, decision_source, now, item_id),
                )

            # Rule #1: recalculate job summary
            self._recalc_project_relink_job_summary(conn, item["job_id"])

            # D-3: audit log
            self._log_project_relink_action(
                conn, item["job_id"], "bind", item_id=item_id,
                payload={"uid": uid, "decision_source": decision_source, "best_path": best_path},
            )

            # Re-read and return with effective fields (rule #4)
            updated = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            return self._item_with_effective_fields(updated)

    def unbind_project_relink_item(self, item_id: int) -> Dict:
        """
        Remove manual binding from an item, restoring system match status.

        D-2 rules:
        - Clears all manual_* fields.
        - Recalculates status from original system uid.
        - Recalculates job summary (rule #1).
        """
        with self._connect() as conn:
            item = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if not item:
                return {"error": f"Item {item_id} not found"}

            if not item["manual_uid"]:
                # Nothing to unbind — return as-is
                return self._item_with_effective_fields(item)

            # Clear manual fields
            original_uid = item["uid"]
            if original_uid:
                # Re-check system match
                asset_row = conn.execute(
                    "SELECT filename FROM assets WHERE uid = ?",
                    (original_uid,),
                ).fetchone()
                fname = asset_row["filename"] if asset_row else None
                best_path = self._best_existing_path(
                    conn,
                    original_uid,
                    fallback=None,
                    filename=fname,
                    update_availability=False,
                )
                if best_path and Path(best_path).exists():
                    new_status = "relinked"
                    new_path = best_path
                else:
                    new_status = "missing"
                    new_path = None
            else:
                new_status = "unmatched"
                new_path = None

            conn.execute(
                """
                UPDATE project_relink_item
                SET manual_uid=NULL, manual_new_path=NULL,
                    manual_decision_source=NULL, manual_bound_at=NULL,
                    status=?, new_path=?
                WHERE item_id=?
                """,
                (new_status, new_path, item_id),
            )

            # Rule #1: recalculate job summary
            self._recalc_project_relink_job_summary(conn, item["job_id"])

            # D-3: audit log
            self._log_project_relink_action(
                conn, item["job_id"], "unbind", item_id=item_id,
                payload={"old_manual_uid": item["manual_uid"], "new_status": new_status},
            )

            updated = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            return self._item_with_effective_fields(updated)

    def refresh_project_relink_items(self, job_id: int) -> Dict:
        """
        Refresh all non-stable item paths for a job.

        D-2 rule #3: when manual_uid is set, only update manual_new_path + status.
        D-2 rule #6: only refreshes paths, never re-parses the project file.
        D-2 rule #1: recalculates job summary after changes.
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT job_id FROM project_relink_job WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? AND status != 'stable'",
                (job_id,),
            ).fetchall()

            changed = 0
            unchanged = 0

            for item in items:
                manual_uid = item["manual_uid"]
                system_uid = item["uid"]
                effective_uid = manual_uid or system_uid

                if not effective_uid:
                    unchanged += 1
                    continue

                asset_row = conn.execute(
                    "SELECT filename FROM assets WHERE uid = ?",
                    (effective_uid,),
                ).fetchone()
                fname = asset_row["filename"] if asset_row else None
                best_path = self._best_existing_path(
                    conn,
                    effective_uid,
                    fallback=None,
                    filename=fname,
                    update_availability=False,
                )

                if best_path and Path(best_path).exists():
                    new_status = "relinked"
                else:
                    new_status = "missing"
                    best_path = None

                old_status = item["status"]
                old_path = (
                    item["manual_new_path"] if manual_uid else item["new_path"]
                )

                if new_status != old_status or best_path != old_path:
                    # Rule #3: manual_uid items → update manual_new_path only
                    if manual_uid:
                        conn.execute(
                            """
                            UPDATE project_relink_item
                            SET manual_new_path=?, status=?, new_path=?
                            WHERE item_id=?
                            """,
                            (best_path, new_status, best_path, item["item_id"]),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE project_relink_item
                            SET new_path=?, status=?
                            WHERE item_id=?
                            """,
                            (best_path, new_status, item["item_id"]),
                        )
                    changed += 1
                else:
                    unchanged += 1

            # Rule #1: recalculate job summary
            self._recalc_project_relink_job_summary(conn, job_id)

            # D-3: audit log
            self._log_project_relink_action(
                conn, job_id, "refresh_items",
                payload={"refreshed": len(items), "changed": changed, "unchanged": unchanged},
            )

            return {
                "job_id": job_id,
                "refreshed": len(items),
                "changed": changed,
                "unchanged": unchanged,
            }

    @staticmethod
    def _item_with_effective_fields(item) -> Dict:
        """
        Add effective_uid, effective_new_path, binding_mode to item dict.

        D-2 rule #4: frontend reads only these computed fields,
        does not assemble logic from raw manual_*/system fields.
        """
        d = dict(item)
        manual_uid = d.get("manual_uid")
        d["effective_uid"] = manual_uid or d.get("uid")
        d["effective_new_path"] = d.get("manual_new_path") or d.get("new_path")
        if manual_uid:
            d["binding_mode"] = "manual"
        elif d.get("uid"):
            d["binding_mode"] = "system"
        else:
            d["binding_mode"] = "none"
        return d

    # ------------------------------------------------------------------
    # v0.7 Phase D-3 – Batch Bind, History, Undo, Outputs, Workbench
    # ------------------------------------------------------------------

    def batch_bind_project_relink_items(
        self, bindings: List[Dict], decision_source: str = "candidate"
    ) -> Dict:
        """
        Batch-bind multiple items in one call.

        bindings = [{"item_id": 1, "uid": "..."}, ...]
        Each item validated independently; single failure doesn't block others.
        Recalculates affected job summaries once at end.
        """
        results = []
        affected_jobs = set()

        for b in bindings:
            item_id = b.get("item_id")
            uid = b.get("uid")
            if not item_id or not uid:
                results.append({"item_id": item_id, "ok": False, "error": "Missing item_id or uid"})
                continue
            r = self.bind_project_relink_item(item_id, uid, decision_source)
            if "error" in r:
                results.append({"item_id": item_id, "ok": False, "error": r["error"]})
            else:
                results.append({"item_id": item_id, "ok": True, "item": r})
                if r.get("job_id"):
                    affected_jobs.add(r["job_id"])

        success = sum(1 for r in results if r["ok"])
        failed = len(results) - success

        # Write batch_bind action log
        if affected_jobs:
            with self._connect() as conn:
                for jid in affected_jobs:
                    self._log_project_relink_action(
                        conn, jid, "batch_bind",
                        payload={"total": len(bindings), "success": success, "failed": failed, "decision_source": decision_source},
                    )

        return {
            "success_count": success,
            "failed_count": failed,
            "items": results,
        }

    def list_project_relink_item_history(self, item_id: int) -> List[Dict]:
        """Return bind/unbind/undo history for a specific item from action log."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT action_id, job_id, item_id, action_type, operator, payload_json, created_at
                FROM project_relink_action_log
                WHERE item_id = ? AND action_type IN ('bind', 'unbind', 'undo_bind', 'batch_bind')
                ORDER BY action_id DESC
                """,
                (item_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def undo_last_project_relink_action(self, item_id: int) -> Dict:
        """
        Undo the most recent manual bind on an item.

        Rules:
        - Only undoes the last 'bind' action (not apply, not unbind).
        - Cross-item undo not allowed.
        - Under the hood calls unbind_project_relink_item.
        - Writes undo_bind to action log.
        """
        with self._connect() as conn:
            item = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if not item:
                return {"error": f"Item {item_id} not found"}

            if not item["manual_uid"]:
                return {"error": "No manual binding to undo"}

            # Save old state for log
            old_manual_uid = item["manual_uid"]
            job_id = item["job_id"]

        # Perform unbind
        result = self.unbind_project_relink_item(item_id)
        if "error" in result:
            return result

        # Write undo_bind action log
        with self._connect() as conn:
            self._log_project_relink_action(
                conn, job_id, "undo_bind", item_id=item_id,
                payload={"undone_manual_uid": old_manual_uid},
            )

        return result

    def list_project_relink_outputs(self, job_id: int) -> List[Dict]:
        """List all output copies generated for a job."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_relink_output WHERE job_id = ? ORDER BY output_id DESC",
                (job_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_project_relink_workbench(self, job_id: int) -> Dict:
        """
        Return items grouped by workbench view categories.

        Groups:
        - stable
        - relinked_system (uid match, no manual_uid)
        - relinked_manual (manual_uid set, status=relinked)
        - missing
        - unmatched
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? ORDER BY item_id",
                (job_id,),
            ).fetchall()

            groups = {
                "missing": [],
                "unmatched": [],
                "relinked_manual": [],
                "relinked_system": [],
                "stable": [],
            }

            for item in items:
                d = self._item_with_effective_fields(item)
                if d["status"] == "stable":
                    groups["stable"].append(d)
                elif d["status"] == "relinked" and d.get("manual_uid"):
                    groups["relinked_manual"].append(d)
                elif d["status"] == "relinked":
                    groups["relinked_system"].append(d)
                elif d["status"] == "missing":
                    groups["missing"].append(d)
                else:
                    groups["unmatched"].append(d)

            return {
                "job_id": job_id,
                "groups": groups,
                "summary": {
                    "total": len(items),
                    "stable": len(groups["stable"]),
                    "relinked_system": len(groups["relinked_system"]),
                    "relinked_manual": len(groups["relinked_manual"]),
                    "missing": len(groups["missing"]),
                    "unmatched": len(groups["unmatched"]),
                },
            }

    # ------------------------------------------------------------------
    # v0.7 Phase D-4 – Long-term sync + Handover closure
    # ------------------------------------------------------------------
    #
    # D-4 RULES:
    #
    # 1. job.status enum is FIXED: pending / running / done / failed.
    #    "Has this job been applied?" is expressed via apply_count / applied_at / output records.
    #    Predecessor selection uses status='done' only.
    #
    # 2. Manual binding inheritance uses 3-tier priority:
    #    (a) source_ref (Jianying material_id) — exact project-internal ID
    #    (b) old_path — filesystem path fallback
    #    (c) asset_name + media_type — filename + type fallback
    #    inherited_from_item_id MUST point to the actually matched predecessor item.
    #
    # 3. verify is read-only: sets verified_at, NEVER changes item.status.
    #    status (stable/relinked/missing/unmatched) and verify health
    #    (valid/stale/unchecked) are two independent dimensions.
    #
    # 4. handover_snapshot is a frozen snapshot at generation time.
    #    It is NOT a live view. Re-running generate_handover_report()
    #    replaces the snapshot; it does NOT auto-update.
    #
    # 5. "Recommended handover version" rule (for documentation/future UI):
    #    Same project_path, pick in order:
    #    (a) Latest job: status='done', handover_at IS NOT NULL, closure_status='complete'
    #    (b) Latest job: status='done', handover_at IS NOT NULL, closure_status='incomplete'
    #    (c) None — no recommended version
    #

    def reanalyze_project_relink(
        self, project_path: str, project_type: str = "jianying"
    ) -> Dict:
        """
        Re-analyze a project, carrying forward manual bindings from the
        latest predecessor job for the same project_path.

        Inheritance priority (D-4 rule #2):
          1. source_ref match (Jianying material_id)
          2. old_path match
          3. asset_name + media_type match

        Predecessor selection (D-4 rule #1):
          Latest job with status='done' for the same project_path.

        Returns: {job_id, predecessor_job_id, inherited_bindings,
                  delta_vs_predecessor, summary, items}
        """
        p = Path(project_path)
        if not p.exists():
            return {"error": f"Project file not found: {project_path}"}

        # 1. Find predecessor: latest done job for this project
        predecessor_job_id = None
        predecessor_bindings_by_source_ref = {}  # source_ref -> binding dict
        predecessor_bindings_by_old_path = {}    # old_path -> binding dict
        predecessor_bindings_by_name_type = {}   # (asset_name, media_type) -> binding dict

        with self._connect() as conn:
            pred_row = conn.execute(
                """SELECT job_id FROM project_relink_job
                   WHERE project_path = ? AND status = 'done'
                   ORDER BY job_id DESC LIMIT 1""",
                (str(p),),
            ).fetchone()

            if pred_row:
                predecessor_job_id = pred_row["job_id"]
                pred_items = conn.execute(
                    "SELECT * FROM project_relink_item WHERE job_id = ? AND manual_uid IS NOT NULL",
                    (predecessor_job_id,),
                ).fetchall()
                for pi in pred_items:
                    binding = {
                        "manual_uid": pi["manual_uid"],
                        "manual_decision_source": pi["manual_decision_source"],
                        "item_id": pi["item_id"],
                    }
                    # Index by all three keys
                    sr = (pi["source_ref"] or "").strip()
                    if sr:
                        predecessor_bindings_by_source_ref[sr] = binding
                    op = (pi["old_path"] or "").strip()
                    if op:
                        predecessor_bindings_by_old_path[op] = binding
                    aname = (pi["asset_name"] or "").strip()
                    mtype = (pi["media_type"] or "").strip()
                    if aname:
                        predecessor_bindings_by_name_type[(aname, mtype)] = binding

        # 2. Create new job with predecessor link
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO project_relink_job
                    (project_path, project_type, status, predecessor_job_id)
                VALUES (?, ?, 'running', ?)""",
                (str(p), project_type, predecessor_job_id),
            )
            new_job_id = cursor.lastrowid

        try:
            # 3. Extract version info
            version_info_str = None
            try:
                adapter = _get_relink_adapter(project_type)
                vi = adapter.get_version_info(str(p))
                if vi:
                    version_info_str = json.dumps(vi, ensure_ascii=False)
            except Exception:
                pass

            # 4. Fresh scan
            result = self.build_project_relink_map(str(p), project_type)
            summary = result["summary"]
            items = result["items"]

            # 5. Insert items with carry-forward
            inherited_count = 0
            with self._connect() as conn:
                for item in items:
                    inherited_from = None
                    manual_uid = None
                    manual_new_path = None
                    manual_decision_source = None
                    manual_bound_at = None
                    item_status = item["status"]

                    # Only inherit for non-stable items when we have a predecessor
                    if predecessor_job_id and item_status != "stable":
                        # 3-tier matching priority
                        binding = None
                        sr = (item.get("source_ref") or "").strip()
                        op = (item.get("old_path") or "").strip()
                        aname = (item.get("asset_name") or "").strip()
                        mtype = (item.get("media_type") or "").strip()

                        if sr and sr in predecessor_bindings_by_source_ref:
                            binding = predecessor_bindings_by_source_ref[sr]
                        elif op and op in predecessor_bindings_by_old_path:
                            binding = predecessor_bindings_by_old_path[op]
                        elif aname and (aname, mtype) in predecessor_bindings_by_name_type:
                            binding = predecessor_bindings_by_name_type[(aname, mtype)]

                        if binding:
                            manual_uid = binding["manual_uid"]
                            manual_decision_source = binding["manual_decision_source"]
                            inherited_from = binding["item_id"]
                            manual_bound_at = self._now()

                            # Re-verify the inherited uid's path
                            asset_row = conn.execute(
                                "SELECT filename FROM assets WHERE uid = ?",
                                (manual_uid,),
                            ).fetchone()
                            asset_filename = asset_row["filename"] if asset_row else None
                            best_path = self._best_existing_path(
                                conn, manual_uid, fallback=None,
                                filename=asset_filename,
                                update_availability=False,
                            )
                            if best_path and Path(best_path).exists():
                                manual_new_path = best_path
                                item_status = "relinked"
                            else:
                                manual_new_path = None
                                # Keep system status if system also found it relinked;
                                # otherwise mark missing since we have the uid
                                if item_status not in ("relinked",):
                                    item_status = "missing"

                            inherited_count += 1

                    conn.execute(
                        """INSERT INTO project_relink_item
                            (job_id, uid, asset_name, old_path, new_path, status,
                             source_ref, fingerprint_match_type, media_type,
                             match_confidence, reason, applied,
                             manual_uid, manual_new_path, manual_decision_source,
                             manual_bound_at, inherited_from_item_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,
                                ?, ?, ?, ?, ?)""",
                        (
                            new_job_id,
                            item.get("uid"),
                            item.get("asset_name"),
                            item.get("old_path"),
                            manual_new_path or item.get("new_path"),
                            item_status,
                            item.get("source_ref"),
                            item.get("fingerprint_match_type"),
                            item.get("media_type"),
                            item.get("match_confidence"),
                            item.get("reason"),
                            manual_uid,
                            manual_new_path,
                            manual_decision_source,
                            manual_bound_at,
                            inherited_from,
                        ),
                    )

                # 6. Recalc summary
                self._recalc_project_relink_job_summary(conn, new_job_id)

                conn.execute(
                    """UPDATE project_relink_job
                       SET status='done', version_info=?, updated_at=?
                       WHERE job_id=?""",
                    (version_info_str, self._now(), new_job_id),
                )

                # 7. Audit log
                self._log_project_relink_action(
                    conn, new_job_id, "reanalyze", payload={
                        "predecessor_job_id": predecessor_job_id,
                        "inherited_bindings": inherited_count,
                    },
                )

            # 8. Auto-compare with predecessor
            delta = None
            if predecessor_job_id:
                delta = self.compare_project_relink_jobs(predecessor_job_id, new_job_id)

            # Read back summary
            job = self.get_project_relink_job(new_job_id)

            return {
                "job_id": new_job_id,
                "predecessor_job_id": predecessor_job_id,
                "inherited_bindings": inherited_count,
                "delta_vs_predecessor": delta,
                "project_path": str(p),
                "project_type": project_type,
                "status": "done",
                "summary": job.get("summary") or summary,
                "items": job.get("items", []),
            }

        except Exception as exc:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE project_relink_job SET status='failed', error_message=?, updated_at=? WHERE job_id=?",
                    (str(exc), self._now(), new_job_id),
                )
            return {"error": str(exc), "job_id": new_job_id, "status": "failed"}

    def get_project_job_chain(self, project_path: str) -> Dict:
        """
        Return the chronological chain of relink jobs for a project path.

        Each entry includes predecessor linkage, summary counts,
        handover status, and apply info.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT job_id, status, predecessor_job_id,
                          total_refs, stable_refs, changed_refs,
                          missing_refs, unmatched_refs,
                          apply_count, handover_at,
                          created_at, updated_at
                   FROM project_relink_job
                   WHERE project_path = ?
                   ORDER BY job_id ASC""",
                (project_path,),
            ).fetchall()

            chain = []
            for r in rows:
                entry = dict(r)
                # Count inherited items for this job
                inh = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM project_relink_item WHERE job_id = ? AND inherited_from_item_id IS NOT NULL",
                    (r["job_id"],),
                ).fetchone()
                entry["inherited_count"] = inh["cnt"] if inh else 0
                chain.append(entry)

            return {
                "project_path": project_path,
                "chain": chain,
            }

    def verify_project_relink_state(self, job_id: int) -> Dict:
        """
        Verify that all resolved/stable item paths still exist on disk.

        D-4 rule #3: This is READ-ONLY with respect to item.status.
        Only sets verified_at timestamp and reports stale items.
        Status (stable/relinked/missing/unmatched) is NEVER changed.

        Returns: {job_id, verified, stale_count, stale_items, all_valid}
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ?",
                (job_id,),
            ).fetchall()

            now = self._now()
            verified_count = 0
            stale_items = []

            for item in items:
                status = item["status"]
                # Determine the effective path to check
                if status == "stable":
                    check_path = item["old_path"]
                elif status == "relinked":
                    check_path = item["manual_new_path"] or item["new_path"]
                else:
                    # missing/unmatched — no path to verify
                    continue

                verified_count += 1
                is_valid = bool(check_path and Path(check_path).exists())

                # Update verified_at (D-4 rule #3: do NOT change status)
                conn.execute(
                    "UPDATE project_relink_item SET verified_at = ? WHERE item_id = ?",
                    (now, item["item_id"]),
                )

                if not is_valid:
                    stale_items.append({
                        "item_id": item["item_id"],
                        "asset_name": item["asset_name"],
                        "path": check_path,
                        "status": status,
                    })

            all_valid = len(stale_items) == 0

            # Audit log
            self._log_project_relink_action(
                conn, job_id, "verify", payload={
                    "verified": verified_count,
                    "stale_count": len(stale_items),
                    "all_valid": all_valid,
                },
            )

            return {
                "job_id": job_id,
                "verified": verified_count,
                "stale_count": len(stale_items),
                "stale_items": stale_items,
                "all_valid": all_valid,
            }

    def generate_handover_report(self, job_id: int, auto_verify: bool = True) -> Dict:
        """
        Generate a handover closure report for a completed relink job.

        D-4 rule #4: The handover_snapshot is a frozen snapshot.
        It captures state at generation time and does NOT auto-update.
        Re-calling this method replaces the snapshot.

        D-4 rule #1: closure_status is 'complete' when no missing/unmatched
        items remain; 'incomplete' otherwise.

        Recommended handover version rule (D-4 rule #5 comment):
        Same project_path → latest job where status='done' AND
        handover_at IS NOT NULL AND closure_status='complete'
        (fallback to 'incomplete', then None).
        """
        # 1. Optional auto-verify
        verification = None
        if auto_verify:
            verification = self.verify_project_relink_state(job_id)
            if verification.get("error"):
                return verification

        with self._connect() as conn:
            _row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not _row:
                return {"error": f"Job {job_id} not found"}
            job_row = dict(_row)

            if job_row["status"] != "done":
                return {"error": f"Job {job_id} status is '{job_row['status']}', expected 'done'"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ?",
                (job_id,),
            ).fetchall()

        # 2. Group items by resolution method
        stable = []
        relinked_system = []
        relinked_manual = []
        missing_items = []
        unmatched_items = []
        manual_bindings_detail = []

        for item in items:
            d = dict(item)
            status = d["status"]
            if status == "stable":
                stable.append(d)
            elif status == "relinked" and d.get("manual_uid"):
                relinked_manual.append(d)
                manual_bindings_detail.append({
                    "asset_name": d["asset_name"],
                    "old_path": d["old_path"],
                    "bound_uid": d["manual_uid"],
                    "decision_source": d.get("manual_decision_source", ""),
                    "inherited": bool(d.get("inherited_from_item_id")),
                })
            elif status == "relinked":
                relinked_system.append(d)
            elif status == "missing":
                missing_items.append(d)
            else:
                unmatched_items.append(d)

        # 3. Get outputs and action log
        outputs = self.list_project_relink_outputs(job_id)
        action_log = self.get_project_relink_action_log(job_id)

        # 4. Build predecessor chain
        predecessor_chain = []
        with self._connect() as conn:
            chain_rows = conn.execute(
                """SELECT job_id, predecessor_job_id, created_at
                   FROM project_relink_job
                   WHERE project_path = ? AND job_id <= ?
                   ORDER BY job_id ASC""",
                (job_row["project_path"], job_id),
            ).fetchall()
            for cr in chain_rows:
                predecessor_chain.append({
                    "job_id": cr["job_id"],
                    "predecessor_job_id": cr["predecessor_job_id"],
                    "created_at": cr["created_at"],
                })

        # 5. Parse version_info
        version_info = None
        if job_row.get("version_info"):
            try:
                version_info = json.loads(job_row["version_info"])
            except Exception:
                version_info = None

        # 6. Determine closure_status
        has_unresolved = len(missing_items) > 0 or len(unmatched_items) > 0
        closure_status = "incomplete" if has_unresolved else "complete"

        # 7. Build snapshot
        now = self._now()
        snapshot = {
            "report_version": "1.0",
            "generated_at": now,
            "project": {
                "path": job_row["project_path"],
                "type": job_row["project_type"],
                "version_info": version_info,
            },
            "resolution_summary": {
                "total_refs": len(items),
                "stable": len(stable),
                "relinked_system": len(relinked_system),
                "relinked_manual": len(relinked_manual),
                "missing": len(missing_items),
                "unmatched": len(unmatched_items),
            },
            "manual_bindings": manual_bindings_detail,
            "outputs": [
                {
                    "output_path": o.get("output_path", ""),
                    "applied_count": o.get("applied_count", 0),
                    "created_at": o.get("created_at", ""),
                }
                for o in (outputs if isinstance(outputs, list) else outputs.get("outputs", []))
            ],
            "action_timeline": [
                {
                    "action": a.get("action_type", ""),
                    "time": a.get("created_at", ""),
                    "operator": a.get("operator", ""),
                    "item_id": a.get("item_id"),
                }
                for a in (action_log if isinstance(action_log, list) else [])
            ],
            "verification": verification if verification else {"all_valid": None, "stale_count": None, "checked_at": None},
            "predecessor_chain": predecessor_chain,
            "closure_status": closure_status,
        }

        # 8. Persist snapshot (D-4 rule #4: frozen, replaces any prior)
        with self._connect() as conn:
            conn.execute(
                "UPDATE project_relink_job SET handover_at = ?, handover_snapshot = ?, updated_at = ? WHERE job_id = ?",
                (now, json.dumps(snapshot, ensure_ascii=False), now, job_id),
            )
            self._log_project_relink_action(
                conn, job_id, "handover", payload={
                    "closure_status": closure_status,
                    "generated_at": now,
                },
            )

        return snapshot

    def export_handover_report(self, job_id: int, fmt: str = "json") -> Dict:
        """
        Export the handover report as JSON or Markdown.

        D-4 rule #4: If handover_snapshot exists, use the frozen snapshot.
        Otherwise generate it first.
        """
        with self._connect() as conn:
            _row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not _row:
                return {"error": f"Job {job_id} not found"}
            job_row = dict(_row)

        # Use existing snapshot or generate
        snapshot = None
        if job_row.get("handover_snapshot"):
            try:
                snapshot = json.loads(job_row["handover_snapshot"])
            except Exception:
                pass

        if not snapshot:
            snapshot = self.generate_handover_report(job_id, auto_verify=True)
            if snapshot.get("error"):
                return snapshot

        filename_base = f"handover_{job_id}"

        if fmt == "markdown":
            md = self._render_handover_markdown(snapshot, job_row)
            return {
                "markdown_content": md,
                "filename": f"{filename_base}.md",
            }
        else:
            return {
                "report": snapshot,
                "filename": f"{filename_base}.json",
            }

    def _render_handover_markdown(self, snapshot: Dict, job_row) -> str:
        """Render a handover snapshot as human-readable Markdown."""
        lines = []
        proj = snapshot.get("project", {})
        rs = snapshot.get("resolution_summary", {})
        lines.append("# 工程 Relink 交接报告\n")
        lines.append("## 工程信息\n")
        lines.append(f"- 路径: {proj.get('path', '')}")
        lines.append(f"- 类型: {proj.get('type', '')}")
        lines.append(f"- 分析日期: {job_row['created_at'] if job_row else ''}")
        lines.append(f"- 交接日期: {snapshot.get('generated_at', '')}")
        lines.append(f"- 状态: {snapshot.get('closure_status', '')}")
        lines.append("")

        lines.append("## 解决汇总\n")
        lines.append("| 分类 | 数量 |")
        lines.append("|------|------|")
        lines.append(f"| 总引用 | {rs.get('total_refs', 0)} |")
        lines.append(f"| 正常 | {rs.get('stable', 0)} |")
        lines.append(f"| 系统恢复 | {rs.get('relinked_system', 0)} |")
        lines.append(f"| 人工绑定 | {rs.get('relinked_manual', 0)} |")
        lines.append(f"| 缺失 | {rs.get('missing', 0)} |")
        lines.append(f"| 未匹配 | {rs.get('unmatched', 0)} |")
        lines.append("")

        bindings = snapshot.get("manual_bindings", [])
        if bindings:
            lines.append("## 人工绑定明细\n")
            lines.append("| 素材 | 原路径 | 绑定方式 | 来源 | 继承 |")
            lines.append("|------|--------|----------|------|------|")
            for b in bindings:
                inherited = "是" if b.get("inherited") else "否"
                lines.append(f"| {b.get('asset_name', '')} | {b.get('old_path', '')} | {b.get('bound_uid', '')} | {b.get('decision_source', '')} | {inherited} |")
            lines.append("")

        outputs = snapshot.get("outputs", [])
        if outputs:
            lines.append("## 输出副本\n")
            for o in outputs:
                lines.append(f"- {o.get('output_path', '')} (修复 {o.get('applied_count', 0)} 项, {o.get('created_at', '')})")
            lines.append("")

        v = snapshot.get("verification", {})
        lines.append("## 验证结果\n")
        if v.get("all_valid") is True:
            lines.append("全部路径有效 ✓")
        elif v.get("all_valid") is False:
            lines.append(f"{v.get('stale_count', 0)} 个路径已失效 ⚠")
        else:
            lines.append("未验证")
        lines.append("")

        timeline = snapshot.get("action_timeline", [])
        if timeline:
            lines.append("## 操作时间线\n")
            for i, a in enumerate(timeline, 1):
                lines.append(f"{i}. {a.get('time', '')} — {a.get('action', '')}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # v0.7 Phase D-1 – Per-project missing stats aggregation
    # ------------------------------------------------------------------

    def get_project_missing_stats(self, project_path: str) -> Dict:
        """
        Aggregate missing/unmatched stats across all jobs for a project path.

        Returns unique missing asset names, persistent missing items,
        and per-job trend data for visualization.
        """
        with self._connect() as conn:
            jobs = conn.execute(
                """
                SELECT job_id, status, created_at,
                       missing_refs, unmatched_refs, total_refs
                FROM project_relink_job
                WHERE project_path = ?
                ORDER BY job_id DESC
                """,
                (project_path,),
            ).fetchall()

            if not jobs:
                return {
                    "project_path": project_path,
                    "total_jobs": 0,
                    "unique_missing_assets": 0,
                    "persistent_missing": [],
                    "trend": [],
                }

            # Collect unique missing asset names across all done jobs
            done_job_ids = [j["job_id"] for j in jobs if j["status"] == "done"]
            all_missing_names: Dict[str, int] = {}  # asset_name -> count of jobs it appears in

            for jid in done_job_ids:
                names = conn.execute(
                    """
                    SELECT DISTINCT asset_name
                    FROM project_relink_item
                    WHERE job_id = ? AND status IN ('missing', 'unmatched')
                      AND asset_name IS NOT NULL AND asset_name != ''
                    """,
                    (jid,),
                ).fetchall()
                for row in names:
                    n = row["asset_name"]
                    all_missing_names[n] = all_missing_names.get(n, 0) + 1

            # Persistent = appears in more than half of done jobs
            threshold = max(1, len(done_job_ids) // 2)
            persistent = [
                {"asset_name": name, "occurrences": count}
                for name, count in sorted(
                    all_missing_names.items(), key=lambda x: x[1], reverse=True
                )
                if count >= threshold
            ]

            # Trend: per-job missing/unmatched counts over time
            trend = [
                {
                    "job_id": j["job_id"],
                    "created_at": j["created_at"],
                    "missing": j["missing_refs"] or 0,
                    "unmatched": j["unmatched_refs"] or 0,
                    "total": j["total_refs"] or 0,
                }
                for j in jobs
                if j["status"] == "done"
            ]
            trend.reverse()  # chronological order for charting

            return {
                "project_path": project_path,
                "total_jobs": len(jobs),
                "unique_missing_assets": len(all_missing_names),
                "persistent_missing": persistent,
                "trend": trend,
            }

    # backfill_fingerprints, get_fingerprint_health → FingerprintMixin
