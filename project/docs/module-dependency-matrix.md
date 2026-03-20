# 模块依赖矩阵（阶段1最终版）

更新时间：2026-02-22

## 1. 单向依赖规则（总则）

- 仅允许单向依赖，禁止循环依赖
- 禁止跨模块调用私有方法（`_xxx`）
- 禁止运行时 `sys.path.insert` 作为模块调用手段

目标方向：

```text
contracts
  -> adapters
  -> workflow_engine
  -> step1_material_analysis
  -> step2_topic_planning
  -> step3_script_generation
  -> step4_material_matching
  -> step5_frame_preview
  -> step6_rough_cut
  -> step7_final_render
  -> library
  -> app_api

step* modules -> contracts, adapters (按需)
library -> contracts, step1_material_analysis
workflow_engine -> contracts, adapters, step* modules
app_api -> contracts, library, workflow_engine, step* modules
desktop_app -> app_api
legacy_lab -> 只可读取 contracts（可选）
```

## 2. 依赖矩阵（允许/禁止）

| 模块 | 允许依赖 | 禁止依赖 |
|---|---|---|
| `contracts` | 无 | 所有业务模块 |
| `adapters` | `contracts` | `app_api`、`desktop_app` |
| `workflow_engine` | `contracts`、`adapters`、`step*` | `desktop_app` |
| `step1_material_analysis` | `contracts` | `app_api`、`desktop_app` |
| `step2_topic_planning` | `contracts`、`adapters` | `app_api`、`desktop_app` |
| `step3_script_generation` | `contracts`、`adapters` | `app_api`、`desktop_app` |
| `step4_material_matching` | `contracts`、`adapters`、`step1_material_analysis` | `app_api`、`desktop_app` |
| `step5_frame_preview` | `contracts`、`adapters` | `app_api`、`desktop_app` |
| `step6_rough_cut` | `contracts`、`adapters` | `app_api`、`desktop_app` |
| `step7_final_render` | `contracts`、`adapters` | `app_api`、`desktop_app` |
| `library` | `contracts`、`step1_material_analysis` | `app_api` 内部实现细节 |
| `app_api` | `contracts`、`library`、`step*` | `desktop_app` 内部实现细节 |
| `desktop_app` | `app_api`（HTTP） | 直接导入 step/library |
| `legacy_lab` | `contracts`（可选） | 被生产模块依赖 |

## 3. 高风险反模式清理状态（阶段2后）

1. 动态注入路径
- 生产实现已迁入：
  - `/Users/angelwang/videoeditor/modules/workflow_engine/workflow.py`
  - `/Users/angelwang/videoeditor/modules/app_api/server.py`
  - `/Users/angelwang/videoeditor/modules/library/global_media_library.py`
- 旧路径中允许保留 `sys.path`：仅兼容壳入口（非业务实现）

2. 调用他模块私有方法
- `workflow` 已切换为 `RenderPipeline` 公共方法接口
- `server` 已切换为 `GlobalMediaLibrary.discover_videos`

3. 数据模型转换分散
- 已统一适配入口：`/Users/angelwang/videoeditor/modules/adapters/materials_mapper.py`
- `workflow` 通过 `materials_to_search_index(...)` 使用适配层

## 4. 变更审批规则（跨模块）

跨模块改动必须记录：
- 改动原因
- 影响 API
- 影响目录
- 回滚命令（`git revert <commit>`）
