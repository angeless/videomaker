# VideoEditor — 待办进度

> 更新于 2026-04-04

## 当前版本：v0.17.0 — VLM 画笔分析引擎
## 当前状态：Phase 1 — 计划已完成，待确认后进入编码

## 三版本规划

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | Done (merged PR #7) |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Done (merged PR #8) |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Done (merged) |
| v0.17.0 | VLM 画笔分析引擎 | 18 | `docs/dev-plans/dev-plan-v0.17.0.md` | Phase 1 计划完成 |

## v0.17.0 任务总览

| 层级 | 任务 | 状态 |
|------|------|------|
| **核心能力** | R1 VLMAdapter 抽象层 | Planned |
| | R2 LocalLlavaAdapter 本地推理 | Planned |
| | R3 APIVisionAdapter 云端 API | Planned |
| | R4 RegionExtractor 画笔区域裁剪 | Planned |
| | R5 VLMAnalyzer 区域画面描述 | Planned |
| **数据+UI** | R6 ReviewStore migration | Planned |
| | R7 CommentInput AI 预填充 | Planned |
| | R8 DrawingOverlay 事件扩展 | Planned |
| **多模态理解** | R9 IntentRouter 多模态升级 | Planned |
| | R10 指代消解 | Planned |
| **AI 诊断** | R11 构图检查 | Planned |
| | R12 曝光/色温检查 | Planned |
| | R13 连续性检查 | Planned |
| | R14 AI 评审员 | Planned |
| | R15 DiagnosticsPanel.vue | Planned |
| **API+设置** | R16 VLM API 端点 | Planned |
| | R17 VLM 设置页 | Planned |
| **验收** | R18 集成测试 + 回归 | Planned |

## 下一步

1. **确认计划** — 用户确认 v0.17.0 开发计划
2. **创建分支** — `feat/v0.17.0-vlm-analysis`
3. **开始 R1** — VLMAdapter 抽象层（无依赖，可立即开始）

## 已知遗留

- 3 pre-existing test failures in test_fingerprint_relink.py (duplicate detection)
- test_openapi_publish.py requires pyyaml (skipped)
- Dependabot: 1 moderate vulnerability on default branch

## 注意事项

- VLM 模块遵循优雅降级原则：VLM 不可用 → 所有现有功能不受影响
- LLaVA 依赖标记为可选（requirements.txt 中 `# optional: vlm`）
- review_engine 独立于 step pipeline（并行路径）
- 异常继承自 VideoEditorError (modules/exceptions.py)
- Python 3.9: 禁止 `X | None` 语法，用 `Optional[X]`
- loudnorm 必须加 `-ar 44100`
