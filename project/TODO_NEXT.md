# VideoEditor — 待办进度

> 更新于 2026-04-06

## 当前版本：v0.18.0 — 四大基础设施升级 ✅ 完成
## 当前状态：版本封板 — 27/27 任务完成，CI 通过

## 版本完成记录

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | Done |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Done |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Done |
| v0.17.0 | VLM 画笔分析引擎 | 18 | `docs/dev-plans/dev-plan-v0.17.0.md` | Done |
| v0.18.0 | MCP + VLM 流 + 多轨 + GPU 渲染 | 27 | `docs/dev-plans/dev-plan-v0.18.0.md` | **Done** |

## 上次停在
- 分支：`feat/v0.18.0-wave3-4`
- 全部 27 任务完成，CI 通过
- 等待 merge 到 main

## 下一步
- 无已规划的下一版本
- 考虑方向：v0.19.0（协作功能/云同步）或 v1.0（生产化发布）

## 已知遗留
- 3 pre-existing test failures in test_fingerprint_relink.py
- VLM settings→adapter env var bridge（v0.17 遗留）
- `_migrate_v17` thread-safety 文档化（v0.17 遗留）
