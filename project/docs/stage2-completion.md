# 阶段2隔离重构完成说明

更新时间：2026-02-22

## 1. 已完成的隔离目标

- 物理隔离：核心实现迁入 `modules/` 与 `apps/`。
- 接口隔离：旧路径保留兼容壳（wrapper），统一转发到新模块。
- 权限隔离：`modules/*` 成为后续主要开发面，`.agents/skills/*` 作为兼容入口层。

## 2. 现行目录索引（核心）

```text
/Users/angelwang/videoeditor
├── modules/
│   ├── workflow_engine/workflow.py
│   ├── app_api/server.py
│   ├── library/global_media_library.py
│   ├── adapters/materials_mapper.py
│   ├── step1_material_analysis/...
│   ├── step2_topic_planning/...
│   ├── step3_script_generation/...
│   ├── step4_material_matching/{adaptive_rewriter.py,search_videos.py}
│   ├── step5_frame_preview/frame_preview.py
│   ├── step6_rough_cut/rough_cut.py
│   ├── step7_final_render/...
│   └── legacy_lab/manage_videos/{demo,tests,learn,...}
├── apps/
│   ├── desktop/{launcher.py,ui/*}
│   └── cli/run_toolkit.py
└── .agents/skills/
    ├── video-editor/scripts/*.py    (兼容壳)
    └── manage-videos/*.py           (兼容壳 + 遗留入口)
```

## 3. 关键迁移映射（实际落地）

| 旧路径 | 新路径 |
|---|---|
| `.agents/skills/video-editor/scripts/workflow.py` | `modules/workflow_engine/workflow.py` |
| `.agents/skills/video-editor/scripts/server.py` | `modules/app_api/server.py` |
| `.agents/skills/video-editor/scripts/library.py` | `modules/library/global_media_library.py` |
| `.agents/skills/video-editor/scripts/app.py` | `apps/desktop/launcher.py` |
| `.agents/skills/video-editor/scripts/convert_index.py` | `modules/adapters/materials_mapper.py` |
| `.agents/skills/manage-videos/search_videos.py` | `modules/step4_material_matching/search_videos.py` |
| `.agents/skills/manage-videos/run_toolkit.py` | `apps/cli/run_toolkit.py` |
| `.agents/skills/video-editor/scripts/ui/*` | `apps/desktop/ui/*` |
| `.agents/skills/manage-videos/demo_*.py` | `modules/legacy_lab/manage_videos/demo/*` |
| `.agents/skills/manage-videos/test_*.py` | `modules/legacy_lab/manage_videos/tests/*` |
| `.agents/skills/manage-videos/learn_*.py` | `modules/legacy_lab/manage_videos/learn/*` |
| `.agents/skills/manage-videos/{fingerprint_system.py,improved_fingerprint.py,chinese_search_ui.py,video_search_ui.py}` | `modules/legacy_lab/manage_videos/*` |

## 4. 接口边界补充

- `modules/library/global_media_library.py` 新增公开方法：`discover_videos(...)`
- `modules/adapters/materials_mapper.py` 新增适配方法：`materials_to_search_index(...)`
- `modules/workflow_engine/workflow.py`：
  - Step1/Step4 搜索与分析直接依赖 `modules.*`，不再依赖 `manage-videos` 私有路径注入
  - 搜索索引转换通过 `modules.adapters` 统一处理

## 5. 兼容策略

- 所有历史入口文件保留原路径与调用方式。
- 旧入口仅作为薄壳转发：
  - import 场景：`from ... import *` 转发
  - 脚本场景：`runpy.run_path(..., run_name="__main__")`

## 6. 验证命令

- `python3 .agents/skills/video-editor/scripts/workflow.py --help`
- `python3 .agents/skills/video-editor/scripts/convert_index.py --help`
- `python3 .agents/skills/manage-videos/run_toolkit.py --help`
- `python3 .agents/skills/manage-videos/search_videos.py --help`
- `python3 .agents/skills/video-editor/scripts/app.py --help`
- `python3 -m py_compile modules/workflow_engine/workflow.py modules/app_api/server.py modules/library/global_media_library.py`

## 7. 回滚

- 全量回滚：`git revert <本次提交>`
- 按文件回滚：
  - `git restore --source=HEAD -- <file-path>`
  - 按映射将新模块文件回退后，恢复旧入口壳前版本
