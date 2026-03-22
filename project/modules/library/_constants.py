"""Shared constants for the library module.

Extracted to avoid circular imports between global_media_library.py
and its mixin sub-modules.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Set

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

# ── FAISS / vector index ──
DEFAULT_FAISS_INDEX_DIR = "cache/faiss"  # relative to library_dir
DEFAULT_EMBEDDING_DIM = 1536

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
