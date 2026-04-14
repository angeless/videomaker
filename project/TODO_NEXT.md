# VideoEditor — 待办进度

> 更新于 2026-04-14

## 当前版本：v0.18.0 — 四大基础设施升级 ✅ 完成
## 当前状态：四轮交叉审查修复完成 — commit 291cce5（共修复43个问题）

## 版本完成记录

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | Done |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Done |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Done |
| v0.17.0 | VLM 画笔分析引擎 | 18 | `docs/dev-plans/dev-plan-v0.17.0.md` | Done |
| v0.18.0 | MCP + VLM 流 + 多轨 + GPU 渲染 | 27 | `docs/dev-plans/dev-plan-v0.18.0.md` | **Done** |

## 上次停在
- 分支：`main`，commit 291cce5
- 四轮独立交叉审查完成，43个问题全部修复（10 P1 + 10 业务/UX + 11 + 12）
- 测试：1623 passed, 5 skipped（+7 新增回归测试）

## 下一步
- 规划 v0.19.0（参考已知遗留问题列表）
- 考虑方向：v0.19.0（质量修复+生产化）或 v1.0

## 已知遗留（待 v0.19.0）
- 3 pre-existing test failures in test_fingerprint_relink.py（pre-existing）
- VLM settings→adapter env var bridge（v0.17 遗留）
- RenderManager._concat_segments() stream normalization（异构源需重编码）
- API response envelope 不一致（部分旧路由仍用 {ok/error} 格式）
- /vlm/diagnose 同步 vs analyze-stream 异步语义不一致
- POST /timeline/clips 绕过 `_assert_no_overlap`（需 TimelineOps add_clip wrapper）
- VLM 多图片 prompt（transition 当前只送单帧，理想是并排双帧）
