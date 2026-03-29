# 素材质量评分体系 — 实现规格附录

**前置文档：** `素材质量评分体系_详细设计_v2.md`（算法逻辑与公式）
**本文档定位：** 开发直接上手的工程实现规格
**文档日期：** 2026-03-18

---

## A. 新增文件清单

```
modules/
  step1_material_analysis/
    usability_scorer.py          # [新增] 七维评分引擎（本文档核心）
tests/
  test_usability_scorer.py       # [新增] 评分引擎单测
```

**修改文件：**

| 文件 | 改动类型 | 改动说明 |
|------|---------|---------|
| `modules/library/global_media_library.py` | 修改 | 在 `_analyze_video()` 末尾调用评分；在 `_ingest_video_file()` 存入结果；DB migration |
| `modules/step4_material_matching/search_videos.py` | 修改 | 搜索结果排序加入 usability_score tiebreak |

---

## B. 数据库变更

### B.1 assets 表新增列

```sql
-- Migration: 在现有 CREATE TABLE assets 后追加
-- 位置: global_media_library.py 约 L353-374 的 CREATE TABLE 语句

ALTER TABLE assets ADD COLUMN usability_score REAL DEFAULT NULL;
ALTER TABLE assets ADD COLUMN usability_tier TEXT DEFAULT NULL;
ALTER TABLE assets ADD COLUMN material_type TEXT DEFAULT NULL;
ALTER TABLE assets ADD COLUMN trash_level TEXT DEFAULT 'none';
```

### B.2 Migration 实现

在 `GlobalMediaLibrary.__init__()` 中的 `_ensure_tables()` 方法里添加 migration：

```python
# 位置: global_media_library.py → _ensure_tables() 方法末尾
# 参照现有 ALTER TABLE 模式

_MIGRATIONS_USABILITY = [
    "ALTER TABLE assets ADD COLUMN usability_score REAL DEFAULT NULL",
    "ALTER TABLE assets ADD COLUMN usability_tier TEXT DEFAULT NULL",
    "ALTER TABLE assets ADD COLUMN material_type TEXT DEFAULT NULL",
    "ALTER TABLE assets ADD COLUMN trash_level TEXT DEFAULT 'none'",
]

for sql in _MIGRATIONS_USABILITY:
    try:
        conn.execute(sql)
    except sqlite3.OperationalError:
        pass  # 列已存在则跳过
```

### B.3 索引

```sql
CREATE INDEX IF NOT EXISTS idx_assets_usability ON assets(usability_score);
CREATE INDEX IF NOT EXISTS idx_assets_trash ON assets(trash_level);
CREATE INDEX IF NOT EXISTS idx_assets_material_type ON assets(material_type);
```

---

## C. 新文件 `usability_scorer.py` 完整规格

### C.1 文件头部

```python
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
```

### C.2 常量定义

```python
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
    # (min_score, tier_code, tier_label)
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
```

### C.3 公开接口 — 唯一入口函数

```python
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
        对应 global_media_library._ingest_video_file() 写入 DB 的行。

    visual_stats : dict
        来自 VideoAssetToolkit._get_visual_stats() 的返回值。
        字段: brightness, brightness_std, saturation, saturation_std,
              blue_ratio, green_ratio, red_ratio, edge_density,
              edge_density_std, motion_score, motion_std,
              face_ratio, color_temp, texture_complexity,
              hue_dominant, sample_count

    audio_info : dict | None
        来自 analyze_audio_quality() 的返回值。
        字段: snr_db, noise_floor_db, clipping_ratio, loudness_lufs,
              peak_db, dynamic_range_db, quality_score, quality_level,
              issues, method
        空镜素材可能为 None。

    analysis_json : dict
        来自 _build_semantic_bundle() 后写入 DB 的 analysis_json blob。
        结构: { 'semantic': { 62 维度... }, 'asr_text': str, 'ocr_text': str,
                'objects': [...], 'gps': {...} | None, ... }

    tag_results : list[dict]
        来自 asset_tag_result 表查询结果。
        每项: { 'tag_name': str, 'score': float, 'source': str }

    library_stats : dict | None
        素材库统计信息（可选，缺失时独特性维度使用默认值）。
        字段: total_assets, similar_assets_count,
              scene_type_counts: { scene_type: count }

    Returns
    -------
    dict — 完整评分结果，schema 见设计文档第七章 §7.1
    """
```

### C.4 内部函数签名清单

每个函数的详细算法逻辑见 v2 设计文档对应章节，此处只列签名和输入/输出约定。

```python
def _detect_material_type(
    visual_stats: Dict[str, Any],
    analysis_json: Dict[str, Any],
) -> str:
    """返回: 'talking_head' | 'interview' | 'broll_scenery' | 'broll_action' | 'product_demo' | 'default'"""

def _compute_tech_score(
    asset_row: Dict[str, Any],
    visual_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """
    返回: {
        'score': float,
        'sub': { 'resolution': float, 'bitrate': float, 'stability': float, 'sharpness': float }
    }
    注意: resolution_score 和 bitrate_score 复用 VideoAssetToolkit.technical_analysis() 的逻辑。
    不要调用 toolkit 实例，而是内联同样的阈值映射（避免引入文件路径依赖）。
    """

def _compute_aesthetic_score(
    visual_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """
    返回: {
        'score': float, 'tier': str,
        'sub': { 'exposure': float, 'color_harmony': float, 'composition': float,
                 'motion_aesthetic': float, 'lighting': float }
    }
    """

def _compute_audio_score(
    audio_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """返回: { 'score': float, 'note': str }"""

def _compute_narrative_score(
    asset_row: Dict[str, Any],
    analysis_json: Dict[str, Any],
) -> Dict[str, Any]:
    """
    返回: {
        'score': float, 'has_voiceover': bool, 'is_pure_broll': bool,
        'sub': { 'voiceover': float, 'info_density': float, 'emotion': float,
                 'role': float, 'duration_fit': float }
    }
    """

def _compute_uniqueness_score(
    asset_row: Dict[str, Any],
    analysis_json: Dict[str, Any],
    library_stats: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    返回: {
        'score': float, 'is_duplicate': bool,
        'sub': { 'visual_unique': float, 'scene_rarity': float, 'temporal_rare': float }
    }
    """

def _compute_edit_fitness(
    asset_row: Dict[str, Any],
    visual_stats: Dict[str, Any],
    audio_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    返回: {
        'score': float,
        'sub': { 'cut_clean': float, 'speed_adapt': float, 'crop_flex': float,
                 'av_sync': float, 'color_potential': float }
    }
    """

def _compute_content_richness(
    analysis_json: Dict[str, Any],
    tag_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    返回: {
        'score': float,
        'sub': { 'tag_rich': float, 'semantic_cover': float,
                 'multimodal': float, 'searchability': float }
    }
    """

def _compute_weighted_total(
    dim_scores: Dict[str, float],
    material_type: str,
) -> float:
    """根据 material_type 选择 WEIGHT_PROFILES，加权求和，返回 0-1 float。"""

def _resolve_tier(score: float) -> Tuple[str, str]:
    """返回 (tier_code, tier_label)，如 ('A+', '优秀')。"""

def _evaluate_trash(
    score_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    """
    返回: {
        'is_trash': bool,
        'trash_level': 'none' | 'warn' | 'suggest_delete' | 'strong_suggest_delete',
        'triggered_rules': [str],
        'primary_reason': str | None,
        'all_reasons': [str],
        'can_be_saved_by': [str],
    }
    """

def _generate_comment(
    material_type: str,
    tier_code: str,
    trash_eval: Dict[str, Any],
    dim_results: Dict[str, Any],
) -> str:
    """返回中文评语字符串。"""

def _suggest_uses(
    material_type: str,
    dim_results: Dict[str, Any],
) -> List[str]:
    """返回推荐用途列表，如 ['转场', '氛围渲染']。"""

def _suggest_improvements(
    dim_results: Dict[str, Any],
) -> List[str]:
    """返回改进建议列表，如 ['可考虑加入旁白提升叙事绑定']。"""
```

### C.5 score_asset() 完整编排逻辑

```python
def score_asset(*, asset_row, visual_stats, audio_info, analysis_json, tag_results, library_stats=None):
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
```

---

## D. 对接 global_media_library.py 的精确改动点

### D.1 import 新增

```python
# 位置: global_media_library.py 文件顶部 import 区域
from modules.step1_material_analysis.usability_scorer import score_asset
```

### D.2 在 `_analyze_video()` 末尾调用评分

```python
# 位置: global_media_library.py → _analyze_video() 方法
# 约 L5295-5415，在 return 之前插入

# ---- 新增: 综合可用性评分 ----
try:
    usability_result = score_asset(
        asset_row={
            "uid": uid,
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "codec": codec,
            "quality_score": quality_score,
            "phash": phash,
        },
        visual_stats=visual_stats,           # 来自 _get_visual_stats()
        audio_info=audio_quality_info,        # 来自 analyze_audio_quality()，可能为 None
        analysis_json=analysis_bundle,        # 包含 semantic + asr_text + objects 等
        tag_results=tag_results,              # 来自标签引擎，可以传空列表 []
        library_stats=self._get_library_stats(conn) if conn else None,
    )
except Exception as e:
    logger.warning("usability scoring failed: %s", e)
    usability_result = None

# 写入 analysis_json
if usability_result:
    analysis_bundle["quality_assessment"] = usability_result
```

### D.3 在 `_ingest_video_file()` 写入 DB 时设置新列

```python
# 位置: global_media_library.py → _ingest_video_file()
# 约 L5656-5931，在 INSERT INTO assets 的 SQL 和参数中添加

# 原 INSERT 语句增加 4 个列:
# ..., usability_score, usability_tier, material_type, trash_level
# 对应值:
usability_score = usability_result["usability_score"] if usability_result else None
usability_tier  = usability_result["usability_tier"] if usability_result else None
material_type   = usability_result["material_type"] if usability_result else None
trash_level     = usability_result["trash_evaluation"]["trash_level"] if usability_result else "none"
```

### D.4 新增 `_get_library_stats()` 辅助方法

```python
# 位置: GlobalMediaLibrary 类内部新增方法

def _get_library_stats(self, conn: sqlite3.Connection) -> Dict[str, Any]:
    """收集素材库统计信息，供独特性评分使用。"""
    total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

    # 场景类型分布
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
        "similar_assets_count": 0,  # 默认 0，pHash 查询在大库下开销大，按需启用
    }
```

### D.5 启用 pHash 相似度查询（可选，大库慎用）

```python
# 如果需要启用 similar_assets_count，在 _get_library_stats 中添加:

def _count_similar_assets(self, conn: sqlite3.Connection, phash: str, threshold: int = 5) -> int:
    """统计与给定 pHash 相似的素材数量。O(n) 扫描，大库慎用。"""
    if not phash:
        return 0
    all_hashes = conn.execute(
        "SELECT phash FROM assets WHERE phash IS NOT NULL AND phash != ?", (phash,)
    ).fetchall()

    from modules.step1_material_analysis.indexer.fingerprint import VideoHasher
    count = 0
    for (h,) in all_hashes:
        if VideoHasher.hamming_distance(phash, h) <= threshold:
            count += 1
    return count
```

---

## E. 对接 search_videos.py

### E.1 搜索结果排序增强

```python
# 位置: search_videos.py → VideoSearch.search() 方法
# 约 L27-89，在排序逻辑处修改

# 原逻辑: results.sort(key=lambda x: x['match_score'], reverse=True)
# 改为:
results.sort(
    key=lambda x: (
        x["match_score"],                                   # 主排序: 搜索相关度
        x.get("usability_score", 0) or 0,                   # 次排序: 可用性评分
    ),
    reverse=True,
)
```

### E.2 搜索结果附加评分字段

```python
# 在组装 result dict 时追加:
result["usability_score"] = asset.get("usability_score")
result["usability_tier"] = asset.get("usability_tier")
result["material_type"] = asset.get("material_type")
result["trash_level"] = asset.get("trash_level")
```

---

## F. 存量素材补评分 — 迁移脚本

```python
# 文件: tools/backfill_usability_scores.py  [新增]

"""
对已入库但没有 usability_score 的素材进行补评分。
用法: python tools/backfill_usability_scores.py --db-path <library.db>
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.step1_material_analysis.usability_scorer import score_asset


def backfill(db_path: str, batch_size: int = 100, dry_run: bool = False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 查找未评分的素材
    rows = conn.execute("""
        SELECT uid, duration, width, height, fps, codec, quality_score, phash,
               analysis_json
        FROM assets
        WHERE usability_score IS NULL
          AND analysis_json IS NOT NULL
        LIMIT ?
    """, (batch_size,)).fetchall()

    print(f"Found {len(rows)} assets to score")

    # 库级统计（一次性）
    total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    scene_rows = conn.execute("""
        SELECT json_extract(analysis_json, '$.semantic.scene_description'), COUNT(*)
        FROM assets WHERE analysis_json IS NOT NULL GROUP BY 1
    """).fetchall()
    library_stats = {
        "total_assets": total,
        "scene_type_counts": {r[0]: r[1] for r in scene_rows if r[0]},
        "similar_assets_count": 0,
    }

    updated = 0
    for row in rows:
        try:
            analysis = json.loads(row["analysis_json"]) if row["analysis_json"] else {}
            visual_stats = analysis.get("visual_stats", {})
            audio_info = analysis.get("audio_quality", None)

            # 查标签
            tags = conn.execute(
                "SELECT tag_name, score, source FROM asset_tag_result WHERE asset_uid = ?",
                (row["uid"],)
            ).fetchall()
            tag_results = [{"tag_name": t[0], "score": t[1], "source": t[2]} for t in tags]

            result = score_asset(
                asset_row=dict(row),
                visual_stats=visual_stats,
                audio_info=audio_info,
                analysis_json=analysis,
                tag_results=tag_results,
                library_stats=library_stats,
            )

            if not dry_run:
                # 更新 assets 表
                conn.execute("""
                    UPDATE assets SET
                        usability_score = ?,
                        usability_tier = ?,
                        material_type = ?,
                        trash_level = ?,
                        analysis_json = json_set(analysis_json, '$.quality_assessment', json(?))
                    WHERE uid = ?
                """, (
                    result["usability_score"],
                    result["usability_tier"],
                    result["material_type"],
                    result["trash_evaluation"]["trash_level"],
                    json.dumps(result, ensure_ascii=False),
                    row["uid"],
                ))
                updated += 1

            tier = result["usability_tier"]
            trash = result["trash_evaluation"]["trash_level"]
            print(f"  {row['uid'][:12]}... → {tier} ({result['usability_score']:.2f}) trash={trash}")

        except Exception as e:
            print(f"  {row['uid'][:12]}... ERROR: {e}")

    if not dry_run:
        conn.commit()
    conn.close()
    print(f"\nDone. Updated {updated}/{len(rows)} assets.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(args.db_path, args.batch_size, args.dry_run)
```

---

## G. 单元测试规格

```python
# 文件: tests/test_usability_scorer.py  [新增]

"""usability_scorer 单元测试"""

import pytest
from modules.step1_material_analysis.usability_scorer import (
    score_asset,
    _detect_material_type,
    _compute_tech_score,
    _compute_aesthetic_score,
    _compute_audio_score,
    _compute_narrative_score,
    _compute_edit_fitness,
    _compute_content_richness,
    _evaluate_trash,
    _resolve_tier,
    WEIGHT_PROFILES,
)


# ========== Fixtures ==========

@pytest.fixture
def high_quality_broll_visual_stats():
    """模拟一个高质量空镜素材的 visual_stats"""
    return {
        "sample_count": 18,
        "brightness": 0.55, "brightness_std": 0.15,
        "saturation": 0.45, "saturation_std": 0.06,
        "blue_ratio": 0.28, "green_ratio": 0.38, "red_ratio": 0.34,
        "edge_density": 0.12, "edge_density_std": 0.03,
        "motion_score": 5.0, "motion_std": 2.0,
        "face_ratio": 0.0,
        "color_temp": 0.06,
        "texture_complexity": 0.14,
        "hue_dominant": 120,
    }

@pytest.fixture
def trash_broll_visual_stats():
    """模拟一个垃圾空镜素材的 visual_stats"""
    return {
        "sample_count": 5,
        "brightness": 0.08, "brightness_std": 0.02,
        "saturation": 0.10, "saturation_std": 0.03,
        "blue_ratio": 0.34, "green_ratio": 0.33, "red_ratio": 0.33,
        "edge_density": 0.02, "edge_density_std": 0.01,
        "motion_score": 42.0, "motion_std": 15.0,
        "face_ratio": 0.0,
        "color_temp": 0.0,
        "texture_complexity": 0.02,
        "hue_dominant": 0,
    }

@pytest.fixture
def talking_head_visual_stats():
    """模拟一个说话类素材的 visual_stats"""
    return {
        "sample_count": 18,
        "brightness": 0.60, "brightness_std": 0.10,
        "saturation": 0.35, "saturation_std": 0.05,
        "blue_ratio": 0.30, "green_ratio": 0.34, "red_ratio": 0.36,
        "edge_density": 0.10, "edge_density_std": 0.02,
        "motion_score": 3.0, "motion_std": 1.0,
        "face_ratio": 0.65,
        "color_temp": 0.06,
        "texture_complexity": 0.12,
        "hue_dominant": 30,
    }

@pytest.fixture
def base_asset_row():
    return {
        "uid": "test_uid_001",
        "duration": 8.0,
        "width": 1920, "height": 1080,
        "fps": 30.0, "codec": "h264",
        "quality_score": 0.85,
        "phash": "a1b2c3d4e5f60718",
    }

@pytest.fixture
def good_audio_info():
    return {
        "snr_db": 32.0,
        "noise_floor_db": -48.0,
        "clipping_ratio": 0.0001,
        "loudness_lufs": -16.0,
        "peak_db": -1.5,
        "dynamic_range_db": 20.0,
        "quality_score": 0.85,
        "quality_level": "excellent",
        "issues": [],
        "method": "ffmpeg+numpy",
    }


# ========== 素材类型检测 ==========

class TestDetectMaterialType:
    def test_talking_head(self, talking_head_visual_stats):
        result = _detect_material_type(
            talking_head_visual_stats,
            {"asr_text": "这是一段很长的旁白文本" * 5, "semantic": {}}
        )
        assert result == "talking_head"

    def test_broll_scenery(self, high_quality_broll_visual_stats):
        result = _detect_material_type(
            high_quality_broll_visual_stats,
            {"asr_text": "", "semantic": {"narrative_role": "atmospheric_broll"}}
        )
        assert result == "broll_scenery"

    def test_broll_action(self):
        stats = {"face_ratio": 0.05, "motion_score": 25.0}
        result = _detect_material_type(stats, {"asr_text": "", "semantic": {}})
        assert result == "broll_action"


# ========== 各维度评分 ==========

class TestTechScore:
    def test_4k_high_bitrate(self):
        result = _compute_tech_score(
            {"width": 3840, "height": 2160, "fps": 60, "quality_score": 0.95, "codec": "h265"},
            {"motion_score": 2.0, "edge_density": 0.15, "texture_complexity": 0.18}
        )
        assert result["score"] >= 0.85
        assert result["sub"]["resolution"] >= 0.90
        assert result["sub"]["stability"] >= 0.90

    def test_480p_shaky(self):
        result = _compute_tech_score(
            {"width": 640, "height": 480, "fps": 24, "quality_score": 0.30, "codec": "h264"},
            {"motion_score": 30.0, "edge_density": 0.02, "texture_complexity": 0.03}
        )
        assert result["score"] < 0.40


class TestAestheticScore:
    def test_beautiful_scenery(self, high_quality_broll_visual_stats):
        result = _compute_aesthetic_score(high_quality_broll_visual_stats)
        assert result["score"] >= 0.70
        assert result["tier"] in ("stunning", "beautiful")

    def test_dark_blurry(self, trash_broll_visual_stats):
        result = _compute_aesthetic_score(trash_broll_visual_stats)
        assert result["score"] < 0.35
        assert result["tier"] in ("mediocre", "poor")


class TestNarrativeScore:
    def test_with_voiceover(self, base_asset_row):
        result = _compute_narrative_score(
            base_asset_row,
            {"asr_text": "今天我们来到了美丽的海边 这里风景非常壮观",
             "ocr_text": "", "objects": ["ocean", "sky"],
             "semantic": {"mood": "壮观", "emotion_intensity": 0.8,
                          "narrative_role": "hero_shot"}, "tags": []}
        )
        assert result["score"] >= 0.65
        assert result["has_voiceover"] is True

    def test_pure_broll_no_voice(self, base_asset_row):
        result = _compute_narrative_score(
            base_asset_row,
            {"asr_text": "", "ocr_text": "", "objects": [],
             "semantic": {"mood": "", "emotion_intensity": 0.3,
                          "narrative_role": "general_broll"}, "tags": []}
        )
        assert result["score"] < 0.40
        assert result["is_pure_broll"] is True


# ========== 综合评分 ==========

class TestScoreAsset:
    def test_high_quality_broll_gets_high_score(
        self, base_asset_row, high_quality_broll_visual_stats
    ):
        result = score_asset(
            asset_row=base_asset_row,
            visual_stats=high_quality_broll_visual_stats,
            audio_info=None,
            analysis_json={
                "asr_text": "", "ocr_text": "", "objects": ["sky", "ocean", "sunset"],
                "semantic": {
                    "narrative_role": "atmospheric_broll", "mood": "治愈",
                    "emotion_intensity": 0.7, "time_of_day": "golden_hour",
                    "scene_description": "ocean sunset",
                },
                "gps": {"lat": 25.0, "lon": 121.0},
            },
            tag_results=[
                {"tag_name": "海边", "score": 0.90, "source": "vision"},
                {"tag_name": "日落", "score": 0.85, "source": "vision"},
                {"tag_name": "治愈", "score": 0.80, "source": "llm"},
                {"tag_name": "空镜", "score": 0.75, "source": "rule"},
                {"tag_name": "风景", "score": 0.70, "source": "vision"},
            ],
        )
        assert result["usability_score"] >= 0.60
        assert result["material_type"] == "broll_scenery"
        assert result["trash_evaluation"]["is_trash"] is False
        assert "schema_version" in result

    def test_trash_broll_gets_flagged(
        self, base_asset_row, trash_broll_visual_stats
    ):
        asset = {**base_asset_row, "duration": 0.5, "width": 640, "height": 480}
        result = score_asset(
            asset_row=asset,
            visual_stats=trash_broll_visual_stats,
            audio_info=None,
            analysis_json={
                "asr_text": "", "ocr_text": "", "objects": [],
                "semantic": {"narrative_role": "broll", "mood": "",
                             "emotion_intensity": 0.2},
            },
            tag_results=[],
        )
        assert result["trash_evaluation"]["is_trash"] is True
        assert result["trash_evaluation"]["trash_level"] in (
            "suggest_delete", "strong_suggest_delete"
        )
        assert result["usability_tier"] in ("D", "F")


# ========== 分级 ==========

class TestTierResolution:
    @pytest.mark.parametrize("score,expected_tier", [
        (0.95, "S+"), (0.88, "S"), (0.80, "A+"), (0.72, "A"),
        (0.65, "B+"), (0.55, "B"), (0.42, "C"), (0.28, "D"), (0.10, "F"),
    ])
    def test_tier_boundaries(self, score, expected_tier):
        tier_code, _ = _resolve_tier(score)
        assert tier_code == expected_tier


# ========== 权重配置完整性 ==========

class TestWeightProfiles:
    @pytest.mark.parametrize("profile_name", WEIGHT_PROFILES.keys())
    def test_weights_sum_to_one(self, profile_name):
        weights = WEIGHT_PROFILES[profile_name]
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001, f"{profile_name} weights sum to {total}"

    @pytest.mark.parametrize("profile_name", WEIGHT_PROFILES.keys())
    def test_all_dimensions_present(self, profile_name):
        expected_keys = {"tech", "aesthetic", "audio", "narrative", "unique", "edit", "content"}
        assert set(WEIGHT_PROFILES[profile_name].keys()) == expected_keys


# ========== 垃圾判定 ==========

class TestTrashEvaluation:
    def test_no_trash(self):
        result = _evaluate_trash({
            "tech_score": 0.80, "aesthetic_score": 0.75, "audio_score": 0.70,
            "narrative_score": 0.65, "unique": 0.60, "edit": 0.70, "content": 0.60,
            "usability_score": 0.70, "material_type": "default",
            "duration": 8.0, "has_voiceover": True, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.80}, "uniqueness_score": 0.60,
        })
        assert result["is_trash"] is False

    def test_trash_008_empty_broll(self):
        """TRASH_008: 空镜 + 不好看 + 无旁白 + 不稀缺"""
        result = _evaluate_trash({
            "tech_score": 0.40, "aesthetic_score": 0.28, "audio_score": 0.50,
            "narrative_score": 0.20, "unique": 0.30, "edit": 0.40, "content": 0.20,
            "usability_score": 0.30, "material_type": "broll_scenery",
            "duration": 5.0, "has_voiceover": False, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.40}, "uniqueness_score": 0.30,
        })
        assert result["is_trash"] is True
        assert "TRASH_008" in result["triggered_rules"]

    def test_saveable_by_uniqueness(self):
        """独特性极高可以挽救"""
        result = _evaluate_trash({
            "tech_score": 0.40, "aesthetic_score": 0.30, "audio_score": 0.50,
            "narrative_score": 0.25, "unique": 0.90, "edit": 0.40, "content": 0.30,
            "usability_score": 0.35, "material_type": "broll_scenery",
            "duration": 5.0, "has_voiceover": False, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.40}, "uniqueness_score": 0.90,
        })
        assert result["trash_level"] == "warn"  # 降级为 warn
        assert len(result["can_be_saved_by"]) > 0
```

---

## H. 性能预算

| 操作 | 预算 | 说明 |
|------|------|------|
| `score_asset()` 单次调用 | < 5ms | 纯 Python 数学计算，无 IO |
| `_get_library_stats()` | < 50ms | 两条聚合 SQL |
| `_count_similar_assets()` | O(n) | 大库(>10K)时跳过或缓存 |
| 补评分脚本 batch=100 | < 10s | 包含 DB 读写 |

**性能守则：**
- `score_asset()` 禁止任何文件 IO、网络请求、模型推理
- 所有输入数据必须预先准备好再传入
- `_count_similar_assets()` 在素材数 > 5000 时自动跳过，similar_assets_count 默认 0

---

## I. 上线 Checklist

```
Phase 1: 核心评分引擎
  [ ] 创建 usability_scorer.py，实现所有函数
  [ ] 创建 test_usability_scorer.py，通过所有测试
  [ ] pytest tests/test_usability_scorer.py 全绿

Phase 2: DB Migration + 集成
  [ ] global_media_library.py 新增 4 列 migration
  [ ] global_media_library.py 新增 _get_library_stats()
  [ ] _analyze_video() 末尾调用 score_asset()
  [ ] _ingest_video_file() 写入新列
  [ ] 新入库素材验证评分结果正确写入 DB

Phase 3: 存量迁移
  [ ] 创建 tools/backfill_usability_scores.py
  [ ] --dry-run 验证无异常
  [ ] 正式运行补评分
  [ ] 抽查 20 个素材评分是否合理

Phase 4: 搜索集成
  [ ] search_videos.py 排序加入 usability_score tiebreak
  [ ] 搜索结果附加评分字段
  [ ] 验证搜索结果排序是否符合预期

Phase 5: 验收
  [ ] 准备 10 个素材样本（涵盖 S+/A/B/C/F 各等级）
  [ ] 人工比对评分 vs 直觉判断
  [ ] 调整阈值参数（如需要）
  [ ] 合并到 main
```

---

## J. visual_stats 字段名精确映射

为避免开发时字段名错误，此处列出 `_get_visual_stats()` 返回的 **精确字段名**与评分引擎的对应关系：

| visual_stats 字段名（精确） | 类型 | 范围 | 在评分中用于 |
|----------------------------|------|------|-------------|
| `brightness` | float | 0-1 | 曝光评分、光影评分、调色空间 |
| `brightness_std` | float | 0-1 | 动态范围奖励、光影层次 |
| `saturation` | float | 0-1 | 色彩和谐度、调色空间 |
| `saturation_std` | float | 0-1 | 色彩统一性奖惩 |
| `blue_ratio` | float | 0-1 | 色调倾向性 |
| `green_ratio` | float | 0-1 | 色调倾向性 |
| `red_ratio` | float | 0-1 | 色调倾向性 |
| `edge_density` | float | 0-1 | 构图评分、清晰度评分 |
| `edge_density_std` | float | 0-1 | （预留） |
| `motion_score` | float | 0-255 | 稳定性、运动美感、入点干净度、素材类型判定 |
| `motion_std` | float | 0-255 | （预留） |
| `face_ratio` | float | 0-1 | 构图奖励、素材类型判定 |
| `color_temp` | float | -1~1 | 光影意图判断（偏暖/偏冷） |
| `texture_complexity` | float | 0-1+ | 清晰度辅助判断 |
| `hue_dominant` | int | 0-180 | （预留） |
| `sample_count` | int | 1-18 | （预留，置信度参考） |

**注意：** v2 设计文档中部分字段名用了 `brightness_mean` / `saturation_mean`，实际代码中字段名是 `brightness` / `saturation`（无 `_mean` 后缀）。**开发时以本表为准。**
