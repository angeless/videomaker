# 模块索引（阶段1最终版）

更新时间：2026-02-22
适用仓库：`/Users/angelwang/videoeditor`

## 1. 目标

将历史遗留项目拆成可并行演进的模块体系，满足：
- 物理隔离：目录独立
- 接口隔离：仅通过公开 API 调用
- 权限隔离：核心边界受保护

## 2. 模块总览

### 2.1 七个业务功能模块（可独立细化）

1. `step1_material_analysis`
- 职责：素材分析、元数据提取、质量评估
- 对外 API：`analyze_videos`、`extract_metadata`
- 主要来源：`video_asset_toolkit.py`

2. `step2_topic_planning`
- 职责：选题生成、选题审核输入输出
- 对外 API：`generate_topics`（由 workflow step2 调用）
- 主要来源：`workflow.py` step2 + `ai_client.py`

3. `step3_script_generation`
- 职责：完整脚本生成、JSON 解析兜底
- 对外 API：`generate_script`、`parse_script_json`
- 主要来源：`workflow.py` step3 + `ai_client.py`

4. `step4_material_matching`
- 职责：素材匹配、脚本改写、覆盖率分析
- 对外 API：`rewrite_script`、`analyze_coverage`
- 主要来源：`adaptive_rewriter.py` + `workflow.py` step4

5. `step5_frame_preview`
- 职责：按脚本片段提取帧预览
- 对外 API：`generate_frame_previews`
- 主要来源：`workflow.py` step5

6. `step6_rough_cut`
- 职责：低质量粗剪预览生成
- 对外 API：`build_rough_cut`
- 主要来源：`workflow.py` step6

7. `step7_final_render`
- 职责：分阶段精渲染、字幕、音频混合、输出
- 对外 API：`render_final_video`
- 主要来源：`render/pipeline.py` + `auto_render.py` + `workflow.py` step7

### 2.2 基础支撑模块（非业务步骤）

- `contracts`
  - 统一数据契约（materials/workflow/render）
- `adapters`
  - 跨模块胶水层，禁止跨模块直接访问私有方法
- `library`
  - 全局素材库与入库检索服务
- `app_api`
  - Flask 路由与任务调度服务
- `desktop_app`
  - pywebview 启动与前端 UI
- `legacy_lab`
  - 旧 demo/test/learn 脚本隔离区

## 3. 目标目录建议

```text
/Users/angelwang/videoeditor
├── modules/
│   ├── contracts/
│   ├── adapters/
│   ├── workflow_engine/
│   ├── step1_material_analysis/
│   ├── step2_topic_planning/
│   ├── step3_script_generation/
│   ├── step4_material_matching/
│   ├── step5_frame_preview/
│   ├── step6_rough_cut/
│   ├── step7_final_render/
│   ├── library/
│   └── app_api/
├── apps/
│   ├── desktop/
│   └── cli/
└── docs/
```

## 4. 受保护区与可改区

### 4.1 受保护区（默认禁止普通功能分支改动）

- `/Users/angelwang/videoeditor/modules/contracts/**`
- `/Users/angelwang/videoeditor/modules/adapters/**`
- `/Users/angelwang/videoeditor/modules/app_api/**`
- `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/*.py`（兼容壳）
- `/Users/angelwang/videoeditor/.agents/skills/manage-videos/*.py`（兼容壳）

### 4.2 功能分支可改区

- `/Users/angelwang/videoeditor/modules/step1_material_analysis/**`
- `/Users/angelwang/videoeditor/modules/step2_topic_planning/**`
- `/Users/angelwang/videoeditor/modules/step3_script_generation/**`
- `/Users/angelwang/videoeditor/modules/step4_material_matching/**`
- `/Users/angelwang/videoeditor/modules/step5_frame_preview/**`
- `/Users/angelwang/videoeditor/modules/step6_rough_cut/**`
- `/Users/angelwang/videoeditor/modules/step7_final_render/**`
- `/Users/angelwang/videoeditor/modules/library/**`
- `/Users/angelwang/videoeditor/apps/desktop/**`
- `/Users/angelwang/videoeditor/modules/legacy_lab/**`
