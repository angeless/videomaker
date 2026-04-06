# VideoEditor — 待办进度

> 更新于 2026-04-04

## 当前版本：v0.18.0 — 四大基础设施升级
## 当前状态：Phase 1 — 计划 V1.4（原子性拆分版）已完成，待确认后进入编码

## 版本完成记录

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | Done |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Done |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Done |
| v0.17.0 | VLM 画笔分析引擎 | 18 | `docs/dev-plans/dev-plan-v0.17.0.md` | Done |
| v0.18.0 | MCP + VLM 流 + 多轨 + GPU 渲染 | 27 | `docs/dev-plans/dev-plan-v0.18.0.md` | Phase 1 计划 V1.4 |

## v0.18.0 四大 Feature + 共享基础设施

| Feature | 内容 | 任务数 | 状态 |
|---------|------|--------|------|
| **X0: 异步 Job 管理器** | Job 注册/进度/取消（B4/D4 前置） | 1 | Planned |
| **A: MCP Server 扩展** | 评审/VLM/增强/只读查询工具 + 安全 | 6 | Planned |
| **B: VLM 视频流分析** | 关键帧采样 + 时序分析 + 场景聚合 | 5 | Planned |
| **C: 多轨时间线** | 数据模型 + 轨道/片段操作 + API + UI | 7 | Planned |
| **D: GPU 渲染管线** | 硬件检测→编码→并行渲染→进度 | 6 | Planned |

## 下一步

1. **确认计划** — 用户确认 v0.18.0 审计修正版开发计划
2. **创建分支** — `feat/v0.18.0-infra-upgrade`
3. **开始第 0 波** — X0（异步 Job 基础设施）
4. **开始第 1 波** — A1 + A2 + A3 + B1 + C1 + D1（各 Feature 无依赖基础任务）

## 已知遗留

- 3 pre-existing test failures in test_fingerprint_relink.py
- VLM settings→adapter env var bridge（v0.17 遗留）
- `_migrate_v17` thread-safety 文档化（v0.17 遗留）

## 注意事项

- 四个 Feature 可并行（仅 X0 是 B4/D4 的共享前置）
- MCP Server 已有 12 个工具，扩展到 29 个（A1×6 + A2×3 + A3×4 + A4×4 = 17 新）
- MCP 模块需 Python ≥ 3.10（server.py 使用 `dict | None` 语法）
- 多轨时间线是全新功能，数据模型需先行
- GPU 渲染：hardware/ 模块已有检测+策略，需落地到渲染路径
- Python 3.9: 禁止 `X | None` 语法，用 `Optional[X]`
- loudnorm 必须加 `-ar 44100`
