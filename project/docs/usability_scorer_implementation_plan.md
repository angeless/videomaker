# 素材综合可用性评分 — 实施计划

**日期：** 2026-03-19
**基线版本：** 9aa11ec (main)
**工作分支：** claude/eager-margulis

---

## 当前代码现状

### 主链路
- 入库：`GlobalMediaLibrary._ingest_video_file()` → `_analyze_video()` → `VideoAssetToolkit.analyze_single_video()` → INSERT/UPDATE assets
- 搜索：`search_videos.py` → `VideoSearch.search()` → JSON索引+DB → match_score 排序

### 扩展点
| 位置 | 行号 | 说明 |
|------|------|------|
| `_ensure_assets_columns()` | L1282-1307 | Migration 追加列 |
| `_analyze_video()` return 前 | L5405-5415 | 评分计算插入点 |
| `_ingest_video_file()` INSERT | L5829-5900 | 新素材写入 |
| `_ingest_video_file()` UPDATE(refresh) | L5732-5768 | 重分析更新 |
| `_ingest_video_file()` UPDATE(simple) | L5770-5789 | 简单更新 |
| `search_videos.py` sort | L88 | 排序tiebreak |

### 不能碰
- audio_quality.py / video_asset_toolkit.py / fingerprint.py / 嵌入模块 / FTS5 / 项目重链接

---

## 执行顺序

| 序号 | Phase | 任务 |
|------|-------|------|
| 1 | Phase 1 | usability_scorer.py + test_usability_scorer.py |
| 2 | Phase 2 | DB migration + _analyze_video() + _ingest_video_file() 集成 |
| 3 | Phase 3 | backfill_usability_scores.py |
| 4 | Phase 4 | search_videos.py 排序增强 |
| 5 | Phase 5 | 回归验证 |

## 文件清单

### 新增
- modules/step1_material_analysis/usability_scorer.py — 七维评分引擎
- tests/test_usability_scorer.py — 47 case 单测
- tools/backfill_usability_scores.py — 存量补评分

### 修改
- modules/library/global_media_library.py — migration + 集成
- modules/step4_material_matching/search_videos.py — 排序增强

### 删除
无

## 约束
1. score_asset() 纯计算，无IO，< 5ms
2. try/except 包裹，评分失败不阻断入库
3. quality_score 保持原义不变
4. 所有新列 DEFAULT NULL，回退透明
