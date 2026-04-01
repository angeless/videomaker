# VideoEditor — 待办进度

> 更新于 2026-04-01

## 当前版本：v0.15.0 — 核心评审 UI + 高级标注
## 当前状态：Phase 6 收尾完成，待 commit + PR

## 三版本规划

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | ✅ Done (merged PR #7) |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | ✅ Phase 2-6 完成 |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Planned |

总参考文档: `docs/dev-plans/timeline-review-ai-reedit.md`

## v0.15.0 完成总结

- **23 R 任务**: 全部完成
  - 14 Vue 组件 (review/)
  - 1 Vue 页面 (ReviewView.vue)
  - 3 JS 模块 (store/config/composable)
  - 2 Python 后端生成器 (thumbnail/waveform)
  - 1 API 路由升级 + 路由注册
- **1184 tests**: 全部通过 (含 13 新增测试)
- **审计**: A 级通过 (0 Critical, 3 Important → WISHLIST)
- **分支**: feat/v0.15.0-review-ui
- **审计报告**: `docs/audit/2026-04-01-v0.15.0-phase2-audit.md`
- **测试报告**: `docs/test-reports/test-report-v0.15.0-phase2.md`

## 下一步

1. **Commit + PR** — 提交 v0.15.0 代码，创建 PR 合并到 main
2. **进入 v0.16.0 开发** — AI 重编辑引擎 + 增强能力
   - 读取 `docs/dev-plans/dev-plan-v0.16.0.md`
   - Phase 0 零代码前置检查

## WISHLIST 记录 (v0.15.0 审计)

- I1: 提取 `_find_ffmpeg()` 为共享工具函数（3 处重复）
- I2: WaveformTrack playhead 分离为独立 canvas 层（性能优化）
- I3: DrawingOverlay 添加触摸事件支持

## 注意事项

- 基线 commit: main HEAD (v0.14.0 merged)
- review_engine 独立于 step pipeline (并行路径)
- 异常继承自 VideoEditorError (modules/exceptions.py)
- 外部 API (Pexels/TTS) 走 adapters/ 层
- loudnorm 必须加 `-ar 44100`
- 大文件 (>50MB) artifact 使用 symlink
- _error_response 格式: {success, error, message, code, timestamp, trace_id}
- ReviewStore.execute_locked() 是外部模块访问 DB 的公共 API
