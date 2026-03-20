# 文件迁移映射（阶段1最终版）

更新时间：2026-02-22
说明：本表用于阶段2逐步迁移。迁移时保留原路径兼容壳，确保可回滚。

## 1. 核心生产路径迁移

| From | To |
|---|---|
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/workflow.py` | `/Users/angelwang/videoeditor/modules/workflow_engine/workflow.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/server.py` | `/Users/angelwang/videoeditor/modules/app_api/server.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/app.py` | `/Users/angelwang/videoeditor/apps/desktop/launcher.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/library.py` | `/Users/angelwang/videoeditor/modules/library/global_media_library.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/ai_client.py` | `/Users/angelwang/videoeditor/modules/step2_topic_planning/ai_client.py`（step2/3 共享） |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/adaptive_rewriter.py` | `/Users/angelwang/videoeditor/modules/step4_material_matching/adaptive_rewriter.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/generate_jianying_json.py` | `/Users/angelwang/videoeditor/modules/step3_script_generation/jianying_draft.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/convert_index.py` | `/Users/angelwang/videoeditor/modules/adapters/materials_mapper.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/auto_render.py` | `/Users/angelwang/videoeditor/modules/step7_final_render/auto_render.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/render/pipeline.py` | `/Users/angelwang/videoeditor/modules/step7_final_render/pipeline.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/render/beauty.py` | `/Users/angelwang/videoeditor/modules/step7_final_render/beauty.py` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/ui/index.html` | `/Users/angelwang/videoeditor/apps/desktop/ui/index.html` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/ui/app.js` | `/Users/angelwang/videoeditor/apps/desktop/ui/app.js` |
| `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/ui/styles.css` | `/Users/angelwang/videoeditor/apps/desktop/ui/styles.css` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/video_asset_toolkit.py` | `/Users/angelwang/videoeditor/modules/step1_material_analysis/video_asset_toolkit.py` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/search_videos.py` | `/Users/angelwang/videoeditor/modules/step4_material_matching/search_videos.py`（match 查询适配） |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/indexer/fingerprint.py` | `/Users/angelwang/videoeditor/modules/step1_material_analysis/indexer/fingerprint.py` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/indexer/semantic.py` | `/Users/angelwang/videoeditor/modules/step1_material_analysis/indexer/semantic.py` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/run_toolkit.py` | `/Users/angelwang/videoeditor/apps/cli/run_toolkit.py` |

## 2. 遗留脚本迁移到隔离区

| From | To |
|---|---|
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/demo_*.py` | `/Users/angelwang/videoeditor/modules/legacy_lab/manage_videos/demo/` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/test_*.py` | `/Users/angelwang/videoeditor/modules/legacy_lab/manage_videos/tests/` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/learn_*.py` | `/Users/angelwang/videoeditor/modules/legacy_lab/manage_videos/learn/` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/fingerprint_system.py` | `/Users/angelwang/videoeditor/modules/legacy_lab/manage_videos/fingerprint_system.py` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/improved_fingerprint.py` | `/Users/angelwang/videoeditor/modules/legacy_lab/manage_videos/improved_fingerprint.py` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/chinese_search_ui.py` | `/Users/angelwang/videoeditor/modules/legacy_lab/manage_videos/chinese_search_ui.py` |
| `/Users/angelwang/videoeditor/.agents/skills/manage-videos/video_search_ui.py` | `/Users/angelwang/videoeditor/modules/legacy_lab/manage_videos/video_search_ui.py` |

## 3. 回滚策略（每步通用）

1. 单步回滚
- `git revert <该步提交hash>`

2. 文件级回滚（紧急）
- 按本表反向映射将 `To -> From` 恢复
- 恢复兼容壳入口后再恢复模块文件

3. 验证回滚成功
- `python3 /Users/angelwang/videoeditor/.agents/skills/manage-videos/run_toolkit.py --help`
- `python3 /Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/workflow.py --help`
- `python3 /Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/auto_render.py --help`
