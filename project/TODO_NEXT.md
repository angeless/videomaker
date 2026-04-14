# VideoEditor — 待办进度

> 更新于 2026-04-14

## 当前版本：v0.18.0 — 四大基础设施升级 ✅ 完成
## 当前状态：版本封板 + 质量审计修复完成 — commit 1d46bdf

## 版本完成记录

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | Done |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Done |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Done |
| v0.17.0 | VLM 画笔分析引擎 | 18 | `docs/dev-plans/dev-plan-v0.17.0.md` | Done |
| v0.18.0 | MCP + VLM 流 + 多轨 + GPU 渲染 | 27 | `docs/dev-plans/dev-plan-v0.18.0.md` | **Done** |

## 上次停在
- 分支：`main`（已 push，commit 1d46bdf）
- 4轮Codex审查完成，10个P1/Critical bug修复
- 测试：1619 passed, 5 skipped

## 下一步
- 规划 v0.19.0（参考已知遗留问题列表）
- 考虑方向：v0.19.0（质量修复+渲染下载+MCP安全）或 v1.0（生产化）

## 已知遗留（待 v0.19.0）
- MCP permission/audit hooks 未接入执行路径（CRITICAL）
- JobManager.cancel() 不拦截已排队任务（缺 Future.cancel()）
- VLM continuity 传全量帧而非每场景一帧
- FrameSampler 不验证 interval_ms（0→死循环）
- Render 输出到 /tmp，无法在应用内下载
- VLM/stream 失败状态被吞掉，用户无反馈
- 3 pre-existing test failures in test_fingerprint_relink.py
- VLM settings→adapter env var bridge（v0.17 遗留）
