"""
素材综合可用性评分引擎

七维评分模型：技术质量 / 画面美感 / 音频质量 / 叙事价值 / 独特性 / 编辑适用性 / 内容丰富度
支持素材类型自适应权重 + 垃圾素材识别

对接:
  - 输入: video_asset_toolkit._get_visual_stats() 的返回值
  - 输入: audio_quality.analyze_audio_quality() 的返回值
  - 输入: global_media_library._build_semantic_bundle() 的返回值
  - 输出: 写入 analysis_json['quality_assessment'] 及 assets 表新列
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------- 版本 ----------
USABILITY_SCHEMA_VERSION = "1.0"

# ===== 素材类型自适应权重 =====
WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "talking_head": {
        "tech": 0.12, "aesthetic": 0.12, "audio": 0.22,
        "narrative": 0.25, "unique": 0.05, "edit": 0.14, "content": 0.10,
    },
    "broll_scenery": {
        "tech": 0.15, "aesthetic": 0.30, "audio": 0.05,
        "narrative": 0.12, "unique": 0.12, "edit": 0.16, "content": 0.10,
    },
    "broll_action": {
        "tech": 0.20, "aesthetic": 0.15, "audio": 0.10,
        "narrative": 0.15, "unique": 0.08, "edit": 0.22, "content": 0.10,
    },
    "interview": {
        "tech": 0.10, "aesthetic": 0.08, "audio": 0.28,
        "narrative": 0.28, "unique": 0.04, "edit": 0.12, "content": 0.10,
    },
    "product_demo": {
        "tech": 0.22, "aesthetic": 0.25, "audio": 0.10,
        "narrative": 0.12, "unique": 0.06, "edit": 0.15, "content": 0.10,
    },
    "default": {
        "tech": 0.15, "aesthetic": 0.20, "audio": 0.12,
        "narrative": 0.18, "unique": 0.08, "edit": 0.15, "content": 0.12,
    },
}

# ===== 分级阈值 =====
TIER_THRESHOLDS: List[Tuple[float, str, str]] = [
    (0.92, "S+", "殿堂级"),
    (0.85, "S",  "精品"),
    (0.78, "A+", "优秀"),
    (0.70, "A",  "良好"),
    (0.60, "B+", "可用偏上"),
    (0.50, "B",  "可用"),
    (0.35, "C",  "勉强"),
    (0.20, "D",  "差"),
    (0.00, "F",  "垃圾"),
]

# ===== 叙事角色价值映射 =====
NARRATIVE_ROLE_VALUES: Dict[str, float] = {
    "hero_shot": 0.95,
    "climax": 0.90,
    "establishing": 0.85,
    "explanation": 0.80,
    "interview": 0.80,
    "atmospheric_broll": 0.65,
    "hook": 0.70,
    "transition": 0.60,
    "broll": 0.45,
    "general_broll": 0.45,
    "filler": 0.25,
}

# ===== 强情感关键词 =====
STRONG_EMOTION_KEYWORDS = frozenset({
    "震撼", "感动", "恐惧", "兴奋", "悲伤", "愤怒", "惊喜", "壮观", "治愈", "紧张",
    "stunning", "emotional", "exciting", "dramatic", "intense",
    "breathtaking", "heartwarming", "thrilling", "melancholy",
})

# ===== 稀缺时间段 =====
RARE_TIME_OF_DAY = frozenset({
    "golden_hour", "blue_hour", "dawn", "dusk", "night", "sunrise", "sunset",
})

# ===== 空镜评语模板 =====
BROLL_COMMENT_TEMPLATES = {
    "S+": "绝美空镜，极佳的构图和光影，可作为视频高光",
    "S": "精品空镜，画面优美，氛围感强",
    "A+": "优质空镜，色彩和构图都很好",
    "A": "不错的空镜，整体质量良好",
    "B+": "可用空镜，有一定视觉吸引力",
    "B": "一般空镜，可作为过渡使用",
    "C": "品质较差的空镜，建议有更好替代时替换",
    "D": "低质量空镜：{reasons}",
    "F": "建议删除：{reasons}",
}


# =====================================================================
# 公开接口
# =====================================================================

def score_asset(
    *,
    asset_row: Dict[str, Any],
    visual_stats: Dict[str, Any],
    audio_info: Optional[Dict[str, Any]],
    analysis_json: Dict[str, Any],
    tag_results: List[Dict[str, Any]],
    library_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    计算素材的综合可用性评分。

    Parameters
    ----------
    asset_row : dict
        来自 assets 表的一行，至少包含:
        uid, duration, width, height, fps, codec, quality_score, phash

    visual_stats : dict
        来自 VideoAssetToolkit._get_visual_stats() 的返回值。

    audio_info : dict | None
        来自 analyze_audio_quality() 的返回值。空镜素材可能为 None。

    analysis_json : dict
        来自 _build_semantic_bundle() 后写入 DB 的 analysis_json blob。

    tag_results : list[dict]
        来自 asset_tag_result 表查询结果。

    library_stats : dict | None
        素材库统计信息（可选）。

    Returns
    -------
    dict — 完整评分结果
    """
    # 1. 判定素材类型
    material_type = _detect_material_type(visual_stats, analysis_json)

    # 2. 计算七维分数
    tech      = _compute_tech_score(asset_row, visual_stats)
    aesthetic  = _compute_aesthetic_score(visual_stats)
    audio     = _compute_audio_score(audio_info)
    narrative = _compute_narrative_score(asset_row, analysis_json)
    unique    = _compute_uniqueness_score(asset_row, analysis_json, library_stats)
    edit      = _compute_edit_fitness(asset_row, visual_stats, audio_info)
    content   = _compute_content_richness(analysis_json, tag_results)

    # 3. 加权汇总
    dim_scores = {
        "tech": tech["score"],
        "aesthetic": aesthetic["score"],
        "audio": audio["score"],
        "narrative": narrative["score"],
        "unique": unique["score"],
        "edit": edit["score"],
        "content": content["score"],
    }
    usability = _compute_weighted_total(dim_scores, material_type)

    # 4. 分级
    tier_code, tier_label = _resolve_tier(usability)

    # 5. 垃圾判定
    trash_bundle = {
        **dim_scores,
        "usability_score": usability,
        "material_type": material_type,
        "duration": asset_row.get("duration", 0),
        "has_voiceover": narrative.get("has_voiceover", False),
        "is_duplicate": unique.get("is_duplicate", False),
        "aesthetic_sub": aesthetic.get("sub", {}),
        "audio_score": audio["score"],
        "uniqueness_score": unique["score"],
        "aesthetic_score": aesthetic["score"],
        "narrative_score": narrative["score"],
        "tech_score": tech["score"],
    }
    trash_eval = _evaluate_trash(trash_bundle)

    # 6. 生成评语 & 建议
    dim_results = {
        "tech": tech, "aesthetic": aesthetic, "audio": audio,
        "narrative": narrative, "uniqueness": unique,
        "edit_fitness": edit, "content_richness": content,
    }
    comment = _generate_comment(material_type, tier_code, trash_eval, dim_results)
    suggested_use = _suggest_uses(material_type, dim_results)
    improvement_hints = _suggest_improvements(dim_results)

    return {
        "schema_version": USABILITY_SCHEMA_VERSION,
        "usability_score": round(usability, 4),
        "usability_tier": tier_code,
        "usability_tier_label": tier_label,
        "material_type": material_type,
        "weight_profile_used": material_type,
        "dimensions": {
            "tech": tech,
            "aesthetic": aesthetic,
            "audio": audio,
            "narrative": narrative,
            "uniqueness": unique,
            "edit_fitness": edit,
            "content_richness": content,
        },
        "trash_evaluation": trash_eval,
        "comment": comment,
        "suggested_use": suggested_use,
        "improvement_hints": improvement_hints,
    }


# =====================================================================
# 内部函数
# =====================================================================

def _detect_material_type(
    visual_stats: Dict[str, Any],
    analysis_json: Dict[str, Any],
) -> str:
    """返回: 'talking_head' | 'interview' | 'broll_scenery' | 'broll_action' | 'product_demo' | 'default'"""
    face_ratio = visual_stats.get("face_ratio", 0)
    motion = visual_stats.get("motion_score", 0)
    asr_text = analysis_json.get("asr_text", "")
    narrative_role = analysis_json.get("semantic", {}).get("narrative_role", "")

    if face_ratio >= 0.50 and len(asr_text) > 20:
        return "talking_head"
    elif face_ratio >= 0.30 and len(asr_text) > 50:
        return "interview"
    elif narrative_role in ("atmospheric_broll", "establishing") and face_ratio < 0.10:
        return "broll_scenery"
    elif motion >= 15 and face_ratio < 0.20:
        return "broll_action"
    elif face_ratio < 0.05 and len(asr_text) < 5:
        return "broll_scenery"
    else:
        return "default"


def _compute_tech_score(
    asset_row: Dict[str, Any],
    visual_stats: Dict[str, Any],
) -> Dict[str, Any]:
    # --- 分辨率评分 ---
    width = asset_row.get("width", 0) or 0
    height = asset_row.get("height", 0) or 0
    pixels = width * height
    if pixels >= 3840 * 2160:
        resolution_score = 0.95
    elif pixels >= 2560 * 1440:
        resolution_score = 0.85
    elif pixels >= 1920 * 1080:
        resolution_score = 0.75
    elif pixels >= 1280 * 720:
        resolution_score = 0.60
    elif pixels >= 640 * 480:
        resolution_score = 0.40
    else:
        resolution_score = 0.30

    # --- 码率评分（复用原有 quality_score 作为近似） ---
    bitrate_score = float(asset_row.get("quality_score", 0.5) or 0.5)

    # --- 稳定性评分 ---
    motion = visual_stats.get("motion_score", 0)
    if motion < 3:
        stability_score = 0.95
    elif motion < 8:
        stability_score = 0.85
    elif motion < 15:
        stability_score = 0.70
    elif motion < 25:
        stability_score = 0.50
    else:
        stability_score = 0.30

    # --- 清晰度评分 ---
    edge = visual_stats.get("edge_density", 0)
    texture = visual_stats.get("texture_complexity", 0)
    if edge >= 0.08 and texture >= 0.10:
        sharpness_score = 0.90
    elif edge >= 0.05:
        sharpness_score = 0.70
    elif edge >= 0.03:
        sharpness_score = 0.50
    else:
        sharpness_score = 0.30

    score = (
        resolution_score * 0.30
        + bitrate_score * 0.25
        + stability_score * 0.25
        + sharpness_score * 0.20
    )
    return {
        "score": round(score, 4),
        "sub": {
            "resolution": round(resolution_score, 4),
            "bitrate": round(bitrate_score, 4),
            "stability": round(stability_score, 4),
            "sharpness": round(sharpness_score, 4),
        },
    }


def _compute_aesthetic_score(
    visual_stats: Dict[str, Any],
) -> Dict[str, Any]:
    sub = {}

    # --- 曝光评分 ---
    brightness = visual_stats.get("brightness", 0.5)
    brightness_std = visual_stats.get("brightness_std", 0.15)
    if 0.35 <= brightness <= 0.65:
        exposure_base = 0.95
    elif 0.25 <= brightness <= 0.75:
        exposure_base = 0.80
    elif 0.15 <= brightness <= 0.85:
        exposure_base = 0.55
    else:
        exposure_base = 0.25

    if 0.08 <= brightness_std <= 0.25:
        dynamic_bonus = 0.10
    elif brightness_std > 0.30:
        dynamic_bonus = -0.05
    else:
        dynamic_bonus = 0.0
    sub["exposure"] = min(1.0, max(0.0, exposure_base + dynamic_bonus))

    # --- 色彩和谐度 ---
    saturation = visual_stats.get("saturation", 0.3)
    saturation_std = visual_stats.get("saturation_std", 0.1)
    color_temp = visual_stats.get("color_temp", 0.0)
    blue_ratio = visual_stats.get("blue_ratio", 0.33)
    green_ratio = visual_stats.get("green_ratio", 0.33)
    red_ratio = visual_stats.get("red_ratio", 0.33)

    if 0.25 <= saturation <= 0.55:
        sat_score = 0.90
    elif 0.15 <= saturation <= 0.65:
        sat_score = 0.70
    elif saturation > 0.75:
        sat_score = 0.45
    else:
        sat_score = 0.50

    if saturation_std < 0.08:
        uniformity_bonus = 0.10
    elif saturation_std < 0.15:
        uniformity_bonus = 0.05
    else:
        uniformity_bonus = -0.05

    color_max = max(blue_ratio, green_ratio, red_ratio)
    color_min = min(blue_ratio, green_ratio, red_ratio)
    if (color_max - color_min) > 0.08:
        tonal_bonus = 0.05
    else:
        tonal_bonus = 0.0
    sub["color_harmony"] = min(1.0, max(0.0, sat_score + uniformity_bonus + tonal_bonus))

    # --- 构图复杂度 ---
    edge_density = visual_stats.get("edge_density", 0.1)
    face_ratio = visual_stats.get("face_ratio", 0.0)

    if 0.06 <= edge_density <= 0.18:
        complexity = 0.90
    elif 0.04 <= edge_density <= 0.25:
        complexity = 0.70
    elif edge_density > 0.30:
        complexity = 0.40
    else:
        complexity = 0.50

    if 0.15 <= face_ratio <= 0.60:
        face_bonus = 0.08
    elif face_ratio > 0.80:
        face_bonus = -0.03
    else:
        face_bonus = 0.0
    sub["composition"] = min(1.0, max(0.0, complexity + face_bonus))

    # --- 运动美感 ---
    motion = visual_stats.get("motion_score", 0)
    if 2 <= motion <= 12:
        motion_beauty = 0.90
    elif motion < 2:
        motion_beauty = 0.70
    elif 12 < motion <= 20:
        motion_beauty = 0.65
    elif 20 < motion <= 35:
        motion_beauty = 0.45
    else:
        motion_beauty = 0.25
    sub["motion_aesthetic"] = motion_beauty

    # --- 光影质量 ---
    if 0.30 <= brightness <= 0.70 and brightness_std >= 0.10:
        lighting = 0.85
    elif 0.20 <= brightness <= 0.80:
        lighting = 0.65
    else:
        lighting = 0.35
    if abs(color_temp) > 0.04:
        lighting += 0.08
    sub["lighting"] = min(1.0, max(0.0, lighting))

    # --- 汇总 ---
    score = (
        sub["exposure"] * 0.20
        + sub["color_harmony"] * 0.25
        + sub["composition"] * 0.25
        + sub["motion_aesthetic"] * 0.15
        + sub["lighting"] * 0.15
    )
    tier = (
        "stunning" if score >= 0.85 else
        "beautiful" if score >= 0.70 else
        "decent" if score >= 0.50 else
        "mediocre" if score >= 0.35 else
        "poor"
    )
    return {"score": round(score, 4), "tier": tier, "sub": {k: round(v, 4) for k, v in sub.items()}}


def _compute_audio_score(
    audio_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if audio_info is None:
        return {"score": 0.5, "note": "无音轨（空镜素材，不惩罚）"}

    base_score = audio_info.get("quality_score", 0.5)
    issues = audio_info.get("issues", [])
    penalty = len(issues) * 0.03

    snr = audio_info.get("snr_db", 0)
    env_bonus = 0.05 if snr >= 25 else 0.0

    score = min(1.0, max(0.0, base_score - penalty + env_bonus))
    note = audio_info.get("quality_level", "unknown")
    if issues:
        note += f"（问题: {', '.join(issues[:3])}）"
    return {"score": round(score, 4), "note": note}


def _compute_narrative_score(
    asset_row: Dict[str, Any],
    analysis_json: Dict[str, Any],
) -> Dict[str, Any]:
    sub = {}

    # --- 旁白伴随度 ---
    asr_text = analysis_json.get("asr_text", "")
    asr_word_count = len(asr_text.split()) if asr_text else 0
    duration = asset_row.get("duration", 0) or 0

    if duration > 0 and asr_word_count > 0:
        words_per_sec = asr_word_count / duration
        if words_per_sec >= 1.5:
            sub["voiceover"] = 0.95
        elif words_per_sec >= 0.5:
            sub["voiceover"] = 0.75
        else:
            sub["voiceover"] = 0.55
    else:
        sub["voiceover"] = 0.20

    # --- 信息密度 ---
    ocr_text = analysis_json.get("ocr_text", "")
    objects = analysis_json.get("objects", [])
    tags = analysis_json.get("tags", [])
    info_signals = 0
    if asr_word_count > 10:
        info_signals += 1
    if len(ocr_text) > 5:
        info_signals += 1
    if len(objects) >= 3:
        info_signals += 1
    if len(tags) >= 5:
        info_signals += 1
    sub["info_density"] = min(1.0, 0.30 + info_signals * 0.18)

    # --- 情感强度 ---
    mood = analysis_json.get("semantic", {}).get("mood", "")
    emotion_intensity = analysis_json.get("semantic", {}).get("emotion_intensity", 0.5)
    has_strong = any(e in str(mood).lower() for e in STRONG_EMOTION_KEYWORDS)
    if has_strong or emotion_intensity >= 0.8:
        sub["emotion"] = 0.90
    elif emotion_intensity >= 0.6:
        sub["emotion"] = 0.70
    elif emotion_intensity >= 0.4:
        sub["emotion"] = 0.50
    else:
        sub["emotion"] = 0.30

    # --- 叙事角色 ---
    narrative_role = analysis_json.get("semantic", {}).get("narrative_role", "general_broll")
    sub["role"] = NARRATIVE_ROLE_VALUES.get(narrative_role, 0.45)

    # --- 时长适用性 ---
    if 3 <= duration <= 15:
        sub["duration_fit"] = 0.90
    elif 1.5 <= duration <= 30:
        sub["duration_fit"] = 0.75
    elif 0.5 <= duration <= 60:
        sub["duration_fit"] = 0.55
    elif duration < 0.5:
        sub["duration_fit"] = 0.15
    else:
        sub["duration_fit"] = 0.45

    score = (
        sub["voiceover"] * 0.30
        + sub["info_density"] * 0.20
        + sub["emotion"] * 0.20
        + sub["role"] * 0.15
        + sub["duration_fit"] * 0.15
    )
    return {
        "score": round(score, 4),
        "has_voiceover": asr_word_count > 0,
        "is_pure_broll": asr_word_count == 0 and len(ocr_text) < 5,
        "sub": {k: round(v, 4) for k, v in sub.items()},
    }


def _compute_uniqueness_score(
    asset_row: Dict[str, Any],
    analysis_json: Dict[str, Any],
    library_stats: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    sub = {}
    stats = library_stats or {}

    # --- 视觉去重 ---
    similar_count = stats.get("similar_assets_count", 0)
    if similar_count == 0:
        sub["visual_unique"] = 1.0
    elif similar_count == 1:
        sub["visual_unique"] = 0.70
    elif similar_count <= 3:
        sub["visual_unique"] = 0.45
    else:
        sub["visual_unique"] = 0.20

    # --- 场景稀缺度 ---
    scene_desc = analysis_json.get("semantic", {}).get("scene_description", "unknown")
    scene_counts = stats.get("scene_type_counts", {})
    total_assets = stats.get("total_assets", 1)
    scene_count = scene_counts.get(scene_desc, 0)
    scene_ratio = scene_count / max(total_assets, 1)
    if scene_ratio < 0.02:
        sub["scene_rarity"] = 0.95
    elif scene_ratio < 0.05:
        sub["scene_rarity"] = 0.80
    elif scene_ratio < 0.15:
        sub["scene_rarity"] = 0.60
    elif scene_ratio < 0.30:
        sub["scene_rarity"] = 0.40
    else:
        sub["scene_rarity"] = 0.25

    # --- 时间独特性 ---
    time_of_day = analysis_json.get("semantic", {}).get("time_of_day", "unknown")
    sub["temporal_rare"] = 0.85 if time_of_day in RARE_TIME_OF_DAY else 0.45

    score = sub["visual_unique"] * 0.50 + sub["scene_rarity"] * 0.30 + sub["temporal_rare"] * 0.20
    return {
        "score": round(score, 4),
        "is_duplicate": similar_count >= 3,
        "sub": {k: round(v, 4) for k, v in sub.items()},
    }


def _compute_edit_fitness(
    asset_row: Dict[str, Any],
    visual_stats: Dict[str, Any],
    audio_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    sub = {}

    # --- 入点/出点干净度 ---
    motion = visual_stats.get("motion_score", 0)
    if motion < 8:
        sub["cut_clean"] = 0.90
    elif motion < 15:
        sub["cut_clean"] = 0.70
    elif motion < 25:
        sub["cut_clean"] = 0.50
    else:
        sub["cut_clean"] = 0.30

    # --- 速度适应性 ---
    fps = float(asset_row.get("fps", 30) or 30)
    if fps >= 60:
        sub["speed_adapt"] = 0.95
    elif fps >= 30:
        sub["speed_adapt"] = 0.75
    elif fps >= 24:
        sub["speed_adapt"] = 0.60
    else:
        sub["speed_adapt"] = 0.35

    # --- 裁剪灵活度 ---
    width = asset_row.get("width", 1920) or 1920
    height = asset_row.get("height", 1080) or 1080
    area = width * height
    if area >= 3840 * 2160:
        sub["crop_flex"] = 0.95
    elif area >= 1920 * 1080:
        sub["crop_flex"] = 0.75
    elif area >= 1280 * 720:
        sub["crop_flex"] = 0.50
    else:
        sub["crop_flex"] = 0.25

    # --- 音画同步度 ---
    if audio_info and audio_info.get("quality_score", 0) >= 0.7:
        sub["av_sync"] = 0.90
    elif audio_info and audio_info.get("quality_score", 0) >= 0.4:
        sub["av_sync"] = 0.65
    elif audio_info:
        sub["av_sync"] = 0.40
    else:
        sub["av_sync"] = 0.50

    # --- 色彩后期空间 ---
    brightness = visual_stats.get("brightness", 0.5)
    saturation = visual_stats.get("saturation", 0.3)
    if 0.30 <= brightness <= 0.70 and 0.20 <= saturation <= 0.55:
        sub["color_potential"] = 0.90
    elif 0.20 <= brightness <= 0.80:
        sub["color_potential"] = 0.65
    else:
        sub["color_potential"] = 0.35

    score = (
        sub["cut_clean"] * 0.25
        + sub["speed_adapt"] * 0.15
        + sub["crop_flex"] * 0.20
        + sub["av_sync"] * 0.20
        + sub["color_potential"] * 0.20
    )
    return {"score": round(score, 4), "sub": {k: round(v, 4) for k, v in sub.items()}}


def _compute_content_richness(
    analysis_json: Dict[str, Any],
    tag_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    sub = {}

    # --- 标签丰富度 ---
    high_conf_tags = [t for t in tag_results if t.get("score", 0) >= 0.55]
    tag_count = len(high_conf_tags)
    if tag_count >= 15:
        sub["tag_rich"] = 0.95
    elif tag_count >= 10:
        sub["tag_rich"] = 0.80
    elif tag_count >= 5:
        sub["tag_rich"] = 0.60
    elif tag_count >= 2:
        sub["tag_rich"] = 0.40
    else:
        sub["tag_rich"] = 0.20

    # --- 语义维度覆盖 ---
    semantic = analysis_json.get("semantic", {})
    filled = sum(1 for v in semantic.values() if v and v != "unknown")
    sub["semantic_cover"] = min(1.0, (filled / 62) * 1.5)

    # --- 多模态信息源 ---
    sources = set()
    if analysis_json.get("asr_text"):
        sources.add("asr")
    if analysis_json.get("ocr_text"):
        sources.add("ocr")
    if analysis_json.get("objects"):
        sources.add("vision")
    if analysis_json.get("gps"):
        sources.add("gps")
    sub["multimodal"] = min(1.0, 0.25 + len(sources) * 0.20)

    # --- 可检索性 ---
    has_text = bool(analysis_json.get("asr_text") or analysis_json.get("ocr_text"))
    has_tags = tag_count >= 3
    has_embedding = analysis_json.get("has_clip_embedding", False)
    has_desc = bool(analysis_json.get("scene_description") or
                    semantic.get("scene_description"))
    sub["searchability"] = min(1.0, 0.20 + sum([has_text, has_tags, has_embedding, has_desc]) * 0.22)

    score = (
        sub["tag_rich"] * 0.30
        + sub["semantic_cover"] * 0.25
        + sub["multimodal"] * 0.25
        + sub["searchability"] * 0.20
    )
    return {"score": round(score, 4), "sub": {k: round(v, 4) for k, v in sub.items()}}


def _compute_weighted_total(
    dim_scores: Dict[str, float],
    material_type: str,
) -> float:
    """根据 material_type 选择 WEIGHT_PROFILES，加权求和，返回 0-1 float。"""
    profile = WEIGHT_PROFILES.get(material_type, WEIGHT_PROFILES["default"])
    total = sum(dim_scores.get(k, 0) * w for k, w in profile.items())
    return round(min(1.0, max(0.0, total)), 4)


def _resolve_tier(score: float) -> Tuple[str, str]:
    """返回 (tier_code, tier_label)，如 ('A+', '优秀')。"""
    for threshold, code, label in TIER_THRESHOLDS:
        if score >= threshold:
            return code, label
    return "F", "垃圾"


def _evaluate_trash(
    score_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    TRASH_RULES = [
        {
            "id": "TRASH_001", "name": "严重技术缺陷",
            "condition": lambda s: s.get("tech_score", 1) < 0.25,
            "severity": "critical",
            "reason_zh": "技术质量极差（模糊/低分辨率/严重抖动）",
            "auto_delete": True,
        },
        {
            "id": "TRASH_002", "name": "既不好看又没用",
            "condition": lambda s: s.get("aesthetic_score", 1) < 0.35 and s.get("narrative_score", 1) < 0.30,
            "severity": "high",
            "reason_zh": "美感差且无叙事价值",
            "auto_delete": True,
        },
        {
            "id": "TRASH_003", "name": "全维度低分",
            "condition": lambda s: s.get("usability_score", 1) < 0.25,
            "severity": "critical",
            "reason_zh": "综合评分极低，各维度均不合格",
            "auto_delete": True,
        },
        {
            "id": "TRASH_004", "name": "近乎重复",
            "condition": lambda s: s.get("is_duplicate", False),
            "severity": "medium",
            "reason_zh": "与库中其他素材高度相似（pHash Hamming ≤ 5）",
            "auto_delete": False,
        },
        {
            "id": "TRASH_005", "name": "残片",
            "condition": lambda s: (s.get("duration", 999) < 0.8 and s.get("narrative_score", 1) < 0.40),
            "severity": "medium",
            "reason_zh": "时长过短(<0.8s)且无特殊用途",
            "auto_delete": True,
        },
        {
            "id": "TRASH_006", "name": "严重曝光问题",
            "condition": lambda s: (
                s.get("aesthetic_sub", {}).get("exposure", 1) < 0.30
                and s.get("narrative_score", 1) < 0.50
            ),
            "severity": "medium",
            "reason_zh": "严重过曝/欠曝，且叙事价值不足以弥补",
            "auto_delete": False,
        },
        {
            "id": "TRASH_007", "name": "音频严重损坏",
            "condition": lambda s: (
                s.get("audio_score", 1) < 0.20
                and s.get("material_type") in ("talking_head", "interview")
            ),
            "severity": "high",
            "reason_zh": "对话类素材但音频质量极差",
            "auto_delete": True,
        },
        {
            "id": "TRASH_008", "name": "空镜纯垃圾",
            "condition": lambda s: (
                s.get("material_type") == "broll_scenery"
                and s.get("aesthetic_score", 1) < 0.35
                and not s.get("has_voiceover", False)
                and s.get("uniqueness_score", 1) < 0.40
            ),
            "severity": "high",
            "reason_zh": "空镜素材：不好看 + 无旁白 + 不稀缺 = 无使用价值",
            "auto_delete": True,
        },
    ]

    triggered = [r for r in TRASH_RULES if r["condition"](score_bundle)]

    if not triggered:
        return {
            "is_trash": False, "trash_level": "none",
            "triggered_rules": [], "primary_reason": None,
            "all_reasons": [], "can_be_saved_by": [],
        }

    max_severity = max(
        ("critical", "high", "medium").index(t["severity"]) for t in triggered
    )
    severity_name = ("critical", "high", "medium")[max_severity]
    auto_deletes = [t for t in triggered if t["auto_delete"]]

    # 救赎机制
    saveable_by = []
    if score_bundle.get("uniqueness_score", 0) >= 0.85:
        saveable_by.append("极高独特性（稀缺场景）")
    if score_bundle.get("narrative_score", 0) >= 0.80:
        saveable_by.append("高叙事价值（有重要旁白）")
    if score_bundle.get("aesthetic_score", 0) >= 0.85:
        saveable_by.append("极高美感（画面精美）")

    if saveable_by and severity_name != "critical":
        trash_level = "warn"
    elif auto_deletes and severity_name == "critical":
        trash_level = "strong_suggest_delete"
    elif auto_deletes:
        trash_level = "suggest_delete"
    else:
        trash_level = "warn"

    return {
        "is_trash": True,
        "trash_level": trash_level,
        "triggered_rules": [t["id"] for t in triggered],
        "primary_reason": triggered[0]["reason_zh"],
        "all_reasons": [t["reason_zh"] for t in triggered],
        "can_be_saved_by": saveable_by,
    }


def _generate_comment(
    material_type: str,
    tier_code: str,
    trash_eval: Dict[str, Any],
    dim_results: Dict[str, Any],
) -> str:
    """返回中文评语字符串。"""
    if material_type == "broll_scenery":
        template = BROLL_COMMENT_TEMPLATES.get(tier_code, "")
        if "{reasons}" in template and trash_eval.get("all_reasons"):
            return template.format(reasons="；".join(trash_eval["all_reasons"][:2]))
        return template

    # 通用评语
    if trash_eval.get("is_trash"):
        return f"建议处理：{trash_eval.get('primary_reason', '综合质量较差')}"
    tier_labels = dict((t[1], t[2]) for t in TIER_THRESHOLDS)
    label = tier_labels.get(tier_code, "")
    return f"{label}素材" if label else f"评级 {tier_code}"


def _suggest_uses(
    material_type: str,
    dim_results: Dict[str, Any],
) -> List[str]:
    """返回推荐用途列表。"""
    uses = []
    aesthetic = dim_results.get("aesthetic", {}).get("score", 0)
    narrative = dim_results.get("narrative", {}).get("score", 0)
    edit = dim_results.get("edit_fitness", {}).get("score", 0)

    if aesthetic >= 0.80:
        uses.append("高光镜头 / 封面截图")
    if material_type == "broll_scenery" and aesthetic >= 0.60:
        uses.append("氛围渲染 / 场景建立")
    if edit >= 0.70 and material_type in ("broll_scenery", "broll_action"):
        uses.append("过渡 / 转场")
    if narrative >= 0.70:
        uses.append("核心叙事段落")
    if material_type == "talking_head" and narrative >= 0.60:
        uses.append("主讲镜头")
    if not uses:
        uses.append("备选素材")
    return uses


def _suggest_improvements(
    dim_results: Dict[str, Any],
) -> List[str]:
    """返回改进建议列表。"""
    hints = []
    tech = dim_results.get("tech", {})
    aesthetic = dim_results.get("aesthetic", {})
    narrative = dim_results.get("narrative", {})
    audio = dim_results.get("audio", {})

    if tech.get("sub", {}).get("stability", 1) < 0.50:
        hints.append("后期可加入防抖处理")
    if aesthetic.get("sub", {}).get("exposure", 1) < 0.40:
        hints.append("后期可调整曝光/亮度")
    if aesthetic.get("sub", {}).get("color_harmony", 1) < 0.40:
        hints.append("后期可调色改善画面色彩")
    if narrative.get("is_pure_broll") and narrative.get("score", 1) < 0.40:
        hints.append("可考虑加入旁白提升叙事绑定")
    if audio.get("score", 1) < 0.40:
        hints.append("可考虑替换或修复音频轨道")
    return hints
