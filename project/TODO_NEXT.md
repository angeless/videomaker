# VideoEditor — 待办进度

> 更新于 2026-04-04

## 当前版本：v0.17.0 — VLM 画笔分析引擎
## 当前状态：版本完成 — 待 PR 合并

## 版本规划

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | Done |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Done |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Done |
| v0.17.0 | VLM 画笔分析引擎 | 18 | `docs/dev-plans/dev-plan-v0.17.0.md` | Done |

## v0.17.0 完成总结

- **18 R 任务**: 全部完成
- **86 新增测试**: 全部通过
- **全量回归**: 1504 passed, 1 skipped, 0 failures
- **审计**: 7 项发现全部修复 (2 Critical + 5 Important)
- **分支**: feat/v0.17.0-vlm-analysis

## 下一步

1. **创建 PR** — feat/v0.17.0-vlm-analysis → main
2. **进入 v0.18.0 规划** — 可选方向:
   - GPU 加速渲染
   - 动态字幕样式
   - 多轨道时间线编辑器
   - VLM 实时视频流分析

## 已知遗留

- Issue #3 (settings→adapter 连通): VLM settings UI 保存 API key 但 adapter 从 env var 读取，中间无桥接
  → 低优先级，v0.18.0 可补
- Issue #4 (thread-safety doc): _migrate_v17 需加注释说明调用须持锁
  → 观察级

## 注意事项

- VLM 模块遵循优雅降级原则：VLM 不可用 → 所有现有功能不受影响
- LLaVA 依赖标记为可选
- review_engine 独立于 step pipeline（并行路径）
- Python 3.9: 禁止 `X | None` 语法，用 `Optional[X]`
