# VideoEditor — 待办进度

> 更新于 2026-04-03

## 当前版本：v0.16.0 — AI 重编辑引擎 + 增强能力
## 当前状态：Phase 6 收尾完成，待 commit + PR

## 三版本规划

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | Done (merged PR #7) |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Done (merged PR #8) |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Phase 6 完成 |

总参考文档: `docs/dev-plans/timeline-review-ai-reedit.md`

## v0.16.0 完成总结

- **25 R 任务**: 全部完成
  - 6 桥接层模块 (comment_resolver/intent_router/edit_planner)
  - 3 DAG + 渲染 (node_manager/render_incremental)
  - 8 增强能力 (audio/tts/bgm/transition/stock/reframe/style/export)
  - 4 API 路由 (review新端点/enhance/stock/style)
  - 3 Vue 组件 (VersionDiff/EnhancePanel/ExportDialog)
  - 1 集成测试套件
- **148 new tests**: 全部通过 (118 unit + 30 integration/smoke)
- **全量回归**: 1289 passed, 54 skipped, 0 new failures
- **审计**: A 级通过 (5 Critical 已修复, 4 IMPORTANT → WISHLIST)
- **分支**: feat/v0.16.0-ai-reedit
- **审计报告**: `docs/audit/2026-04-03-v0.16.0-phase2-audit.md`
- **测试报告**: `docs/test-reports/test-report-v0.16.0-phase2.md`

## 下一步

1. **Commit + PR** — 提交 v0.16.0 代码，创建 PR 合并到 main
2. **进入 v0.17.0 规划** — 可选方向:
   - GPU 加速渲染
   - 动态字幕样式
   - VLM 画笔分析
   - 多轨道时间线编辑器

## WISHLIST 新增 (v0.16.0 审计)

- W-023: 增强模块 except Exception 细化
- W-024: audio_enhancer 重试区分超时与错误
- W-025: stock_media urlretrieve 超时
- W-026: enhance_routes session 数据校验

## 注意事项

- 基线 commit: main HEAD (v0.15.0 merged)
- review_engine 独立于 step pipeline (并行路径)
- 异常继承自 VideoEditorError (modules/exceptions.py)
- 外部 API (Pexels/TTS) 走 adapters/ 层
- loudnorm 必须加 `-ar 44100`
- 大文件 (>50MB) artifact 使用 symlink
- _error_response 格式: {success, error, message, code, timestamp, trace_id}
- ReviewStore.execute_locked() 是外部模块访问 DB 的公共 API
- style_skills 依赖 pyyaml (可选, 无 yaml 时报 ReviewEngineError)
- librosa beat 分析依赖 scipy (可选, 不兼容时返回空节拍列表)
