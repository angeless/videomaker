---
session_id: cc:2026-05-08-videoeditor-v019-plan-extension
parent_session_id: cc:2026-04-14-videoeditor-v018-final
source: claude-code
---

# VideoEditor — 待办进度

> 更新于 2026-05-08

## 当前版本：v0.18.0 — 四大基础设施升级 ✅ 完成
## 当前状态：v0.19.0 计划已经 plan-audit 三维度审计 + Critical 修正完成；准备进 Wave 1

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
- 分支：`main`，commit 4106ced
- 六轮独立交叉审查完成，69个问题全部修复
- 测试：1626 passed, 5 skipped（+10 新增回归测试）
- 第六轮发现 3 个 CRITICAL：review/roughcut store _fetch 签名不匹配 + 缺 auth header
  → Comment Export / TTS / BGM / transition / reframe 自 v0.15.0 起从未工作过

## 下一步（Wave 1 启动）

### Wave 1 任务清单（含 audit 后新增）
**用户头牌问题立即缓解**：M2 + M8 + N6 → **0.5-1 天可见效果**
- **M2** Library "AI 未启用"横幅（含 Settings 链接）— TDD 起点
- **M8** 指纹/标签概念区分（HealthPanel 拆两块）
- **N6** 删除 `/production` redirect（零风险清理，跑 grep + redirect 测试）

**信任修复地基**：M1 + M3 + M9 + L6
- **M1** AssetDetailPanel 标签来源徽章
- **M3** OnboardingModal 加 API key 引导 step
- **M9** Library 横幅 → Settings AI section 一键直达
- **L6** `_meta.model_version` 反映真实 provider（前移以满足 M1 依赖）

**复杂任务（Wave 1 末）**：N5 改名 + 影响面 5 步验收

**已规划（按原 v0.19 计划）**：E1-E4 + F1-F3

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
