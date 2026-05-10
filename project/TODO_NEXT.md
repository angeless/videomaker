---
session_id: cc:2026-05-08-videoeditor-v019-plan-extension
parent_session_id: cc:2026-04-14-videoeditor-v018-final
source: claude-code
---

# VideoEditor — 待办进度

> 更新于 2026-05-08

## 当前版本：v0.18.0 — 四大基础设施升级 ✅ 完成
## 当前状态：v0.19.0 Wave 1 全部完成；准备进 Wave 2

### Wave 1 完成进度

| 任务 | Commit | 状态 |
|---|---|---|
| plan-audit 三维度 + 5 Critical 修正 | 109cf0e | ✅ |
| M2 (Library AI 未启用横幅) + M9 anchor | 109cf0e | ✅ |
| M8 (LibraryHealthPanel 概念区分 — 最小) | 109cf0e | ✅ |
| N6 (孤儿 ProductionView + redirect 注释) | 109cf0e | ✅ |
| **L6** (_meta.provider 分类，17 单测) | 待 commit | ✅ |
| **M1** (AssetDetailPanel 来源徽章 5 provider) | 待 commit | ✅ |
| **M3** (OnboardingModal API key step) | 待 commit | ✅ |
| **N5** (`/create/workflow` → `/create/guide` 5 步验收) | 待 commit | ✅ |
| **基线** | — | 1690 passed, 5 skipped (v0.18 末 1626 + 64 新增) |

### 审计修订摘要（2026-05-08）
- 5 Critical 全部修正（详见 `docs/audit/2026-05-08-plan-audit-report-v0.19.0.md`）
- L 系列扩展：+L8（env var 桥接）+ L9（vision_enrich）+ L10（embedding）
- M 系列扩展：+M8（指纹/标签概念区分）+ M9（老用户 → Settings 入口）
- N 优先级修正：N5+N6 前移到 Wave 1（用户先报布局）；L6 也前移到 Wave 1（M1 依赖）
- 总任务数 22 → 27；估时 9.5w → ~10.5w

## 版本完成记录

| 版本 | 内容 | R 任务数 | 计划文档 | 状态 |
|------|------|---------|---------|------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` | Done |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` | Done |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` | Done |
| v0.17.0 | VLM 画笔分析引擎 | 18 | `docs/dev-plans/dev-plan-v0.17.0.md` | Done |
| v0.18.0 | MCP + VLM 流 + 多轨 + GPU 渲染 | 27 | `docs/dev-plans/dev-plan-v0.18.0.md` | **Done** |

## 上次停在
- 分支：`claude/funny-mestorf-142ff5`（已 push 远端），3 个 commit 待续
- v0.19.0 Wave 1 **全部完成** (109cf0e, c1c9c31)
- v0.19.0 Wave 2 **全部完成** （L1+L8+H3 + L2 + L3 + L4 + L7 + L9 + L10 + audit fix）
- 测试：1771 passed, 9 skipped, **0 failed** ✅（含 L10 specific 12/12，4 voyage SDK 路径自动 skip）
- L10 audit fix 包含 2 处加固：
  1. **Bug 1 修复**：`_embedding_runtime_status` 优先级重排——SDK 缺失诊断在 Anthropic-only 引导前面，避免误导用户
  2. **Bug A 修复**：Voyage `input_type` 参数透传（query/document）→ 5-10% 检索质量提升
- **下次会话起点**：Wave 3 起点 — F1+F2（review VLM 错误显现，复用 L4 错误枚举）

## 历史里程碑
- 2026-04-14 commit 4106ced：v0.18.0 六轮独立交叉审查完成，69 个问题全部修复（1626 passed, 5 skipped）
- 自 v0.15.0 起从未工作过的 dead code（Comment Export / TTS / BGM / transition / reframe）已修复

## 下一步（Wave 1 续做 — 新会话起点）

### 推荐顺序（依赖驱动）
1. **L6** `_meta.model_version` 反映真实 provider — M1 的依赖前置，1-2 小时
   - core_mixin.py:3863-3865 已部分实现（OpenAI 写 model_version）
   - 任务：补 Claude/Llava/heuristic 三种 provider 的写入路径
   - 测试：3 种 provider 下 `_meta.model_version` 字段不同

2. **M1** AssetDetailPanel 标签来源徽章 — 依赖 L6 完成
   - 文件：`apps/desktop/ui-vue/src/components/library/AssetDetailPanel.vue`
   - 任务：读 `asset.semantic._meta.model_version`，渲染 badge：
     `heuristic` (灰) / `llm:gpt-*` (蓝) / `llm:claude-*` (橙)
   - 测试：mock 3 种 model_version，断言 badge 正确

3. **M3** OnboardingModal API key 引导 step — UI 独立，可与 M1 并行
   - 文件：`apps/desktop/ui-vue/src/components/onboarding/OnboardingModal.vue`（328 行）
   - 任务：在现有结构里**加**一步（不重写步骤数），含跳过选项
   - 边界：跳过后由 MissingKeyBanner（M2 已上线）兜底

4. **N5** `/create/workflow` → `/create/guide` + 5 步验收 — Wave 1 末，影响面最大
   - 影响面：14 个 .vue/.js + 20+ 处硬编码 + i18n labels.js + 路由 + 测试 fixture
   - 验收：① grep `/create/workflow` = 0（除 redirect）② i18n 同步 ③ Vue 硬编码扫描 ④ 旧路径 301 ⑤ E2E 通过

### 已规划（按原 v0.19 计划）
- E1-E4（dead-stub 清理）+ F1-F3（错误显现）— 与上述 M/L 同 Wave 1 但独立线

## v0.19.0 新增 Feature（2026-05-08 用户报告驱动）

| Feature | 优先级 | 任务数 | 一句话 |
|---|---|---|---|
| **L — Library 标签器 LLM 接入 + 适配器统一** | P0 | L1-L7 | 让 Anthropic key 真正驱动 library 标签生成 |
| **M — 素材分析能力诚实化** | P0 | M1-M7 | 标签来源透明 + 文案不再过度承诺 |
| **N — 顶层导航重构** | P1 | N1-N8 | 7 个一级入口压到 4 个，消除 `/workflows` 命名碰撞 |

详见 `docs/dev-plans/dev-plan-v0.19.0.md`。

## 已知遗留（待 v0.19.0）
- 3 pre-existing test failures in test_fingerprint_relink.py（pre-existing）
- VLM settings→adapter env var bridge（v0.17 遗留）→ Feature H3 + L
- RenderManager._concat_segments() stream normalization（异构源需重编码）→ Feature H1
- API response envelope 不一致（部分旧路由仍用 {ok/error} 格式）→ Feature G
- /vlm/diagnose 同步 vs analyze-stream 异步语义不一致 → Feature H4
- VLM 多图片 prompt（transition 当前只送单帧，理想是并排双帧）→ Feature H2
- VLM 错误（429/timeout/auth）当前静默 logger.debug，应升级到用户可见 → Feature F + L4

## 注意事项
- v0.19 总计 ~9.5 周（4 个 Wave），实测可能 8-12 周
- L 系列依赖 vlm_adapter（v0.17 已就位）—— 不需再造轮子
- M3 onboarding 与 L5 settings 须同 PR 完成，避免表单冲突
- N 系列须为旧路径 100% redirect（保留 6 个版本周期）
