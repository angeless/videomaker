# VideoEditor — 待办进度

> 更新于 2026-03-31

## 当前版本：v0.14.0 ✅ 已完成
## 当前状态：Phase 6 收尾完成，可合并到 main

## 三版本规划

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | ✅ Done |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Planned |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Planned |

总参考文档: `docs/dev-plans/timeline-review-ai-reedit.md`

## v0.14.0 完成总结

- **29 任务 (R1-R29)**: 28 完成 + 1 按计划推迟 (R15 VLM)
- **125 tests**: 全部通过 (75 unit + 23 API + 5 integration + 16 smoke)
- **审计**: A 级通过 (Part A/B/C/D 全部通过 + Phase 4.5 子 Agent 验收通过)
- **分支**: `feat/v0.14.0-review-engine`
- **审计报告**: `docs/audit/2026-03-31-v0.14.0-audit.md`
- **测试报告**: `docs/test-reports/test-report-v0.14.0-release.md`

## 下一步

1. **合并分支** — `feat/v0.14.0-review-engine` → `main`
2. **进入 v0.15.0 开发** — 核心评审 UI + 高级标注
   - 读取 `docs/dev-plans/dev-plan-v0.15.0.md`
   - Phase 0 零代码前置检查
   - Phase 1 理解与计划

## 改进建议 (记入 WISHLIST)

1. `_find_ffmpeg()` 重复 3 处 → 提取为 `review_engine/_ffmpeg_utils.py`
2. roughcut_routes.py L77 宽泛 except → 细化为具体异常类型

## 注意事项

- 基线 commit: `5a48ef9`
- review_engine 独立于 step pipeline (并行路径)
- 异常继承自 VideoEditorError (modules/exceptions.py)
- 外部 API (Pexels/TTS) 走 adapters/ 层
- loudnorm 必须加 `-ar 44100`
- 大文件 (>50MB) artifact 使用 symlink
- _error_response 格式: {success, error, message, code, timestamp, trace_id}
