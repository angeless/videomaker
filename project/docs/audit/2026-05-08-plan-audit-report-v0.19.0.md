# 计划审计总报告 — v0.19.0 Feature L/M/N 扩展

**审计时间**: 2026-05-08
**审计对象**: `docs/dev-plans/dev-plan-v0.19.0.md` Feature L (L1-L7) + M (M1-M7) + N (N1-N8)
**审计方式**: 三维度独立子 Agent 并行审计
**审计结论**: ⚠️ **需修改后确认** — 5 Critical 阻断

| 维度 | 报告 | 结论 | Critical |
|---|---|---|---|
| A — 架构一致性 | [plan-audit-A-architecture-v0.19.0.md](./2026-05-08-plan-audit-A-architecture-v0.19.0.md) | ⚠️ 需修改 | 0 |
| B — 闭环完整性 | [plan-audit-B-closure-v0.19.0.md](./2026-05-08-plan-audit-B-closure-v0.19.0.md) | ⚠️ 条件通过 | 2 |
| C — 产品对齐 | [plan-audit-C-product-v0.19.0.md](./2026-05-08-plan-audit-C-product-v0.19.0.md) | ❌ 需修改 | 3 |

---

## 5 Critical 发现（阻断进入 Phase 2，必须修正）

### Critical-1（C-1）: 用户语言"指纹"概念错配被回避

用户报告"素材**指纹**和**标签**打的还是不对"。代码里：
- 指纹 = pHash 去重（OpenCV 感知哈希，与 LLM 无关）
- 标签 = `_heuristic_*` 或 `_llm_structured_tags`（用户期待 AI）

L/M/N 全部聚焦"标签"，**没有任何任务区分这两个概念**。用户看到 UI 上"指纹"统计卡时仍会困惑。

**修正**：新增 **M8** — 在 LibraryHealthPanel 区分"指纹（去重）"vs"AI 标签"两块统计 + 文案；FAQ 入口或 i18n hint 解释技术差别。

---

### Critical-2（C-2）: env var 桥接断裂

**已验证**：
```
settings_service.py:604  →  os.environ["ANTHROPIC_API_KEY"] = ...
_vlm_claude.py:19        →  API_KEY_ENV = "VIDEOEDITOR_CLAUDE_API_KEY"
```

用户在 Settings UI 设 Anthropic key → 写入 `ANTHROPIC_API_KEY` → Claude adapter 读 `VIDEOEDITOR_CLAUDE_API_KEY` → **永远找不到** → adapter `is_available() = False`。

**即使 L1 让 `_llm_tagging_enabled` 接受 Anthropic key**，下游 adapter 仍拿不到 key，整个 L 系列形同虚设。

**修正**：新增 **L8** — env var 命名统一（settings_service 同时写 `ANTHROPIC_API_KEY` 和 `VIDEOEDITOR_CLAUDE_API_KEY`，或反向：让 adapter 优先读标准名 `ANTHROPIC_API_KEY` 兼容旧名）。**必须与 L1 同 Wave 完成**。

---

### Critical-3（C-3）: 优先级反转 — 用户先报布局，计划反而排到最后

用户原文："**1) 产品的功能布局混乱  2) 素材指纹和标签打的还是不对**"

但当前 Wave 排程：
- M（标签 UX）→ Wave 1（P0）
- L（标签后端）→ Wave 2（P0）
- N（布局）→ Wave 4（P1）← **最后**

这把用户排第一的痛点延后 8 周。

**修正**：把 N 系列**部分**提前：
- **Wave 1.5**（与 M1-3 同期）：**N6**（删除 production redirect，0.5 天，零风险）+ **N5**（`/create/workflow` 改名 `/create/guide`，与 N5 影响面修正配套）
- **Wave 4**：N1-N4 + N7-N8（导航栏重构主体）

---

### Critical-4（B-1）: N5 改名影响面被严重低估

子 Agent B 实测发现 N5（`/create/workflow` → `/create/guide`）涉及：
- 14 个 .vue/.js 文件
- 20+ 处硬编码字符串
- i18n labels.js 至少 5 处
- 路由守卫 + 测试 fixture

但计划仅写"UI labels 同步"。

**修正**：N5 任务说明升级为：
- 验收 step 1: `grep -rn "/create/workflow" apps/desktop/ui-vue/src/` 在改完后 = 0（除了兼容 redirect 配置）
- 验收 step 2: `grep -rn "create/workflow" apps/desktop/ui-vue/src/i18n/` 同步
- 子任务清单：N5a (路由层) / N5b (i18n) / N5c (Vue 组件硬编码) / N5d (测试) / N5e (旧路径 redirect)

---

### Critical-5（B-2）: M1 跨 Wave 依赖 L6 → Wave 1 上线后 M1 不工作

M1（badge 显示 `model_version`）在 Wave 1，但其依赖的 `_meta.model_version` 字段由 L6 设置，L6 在 Wave 2。

→ Wave 1 发布时 M1 显示空 badge 或假数据。

**修正**：把 **L6 提到 Wave 1 末**（与 M1 同 Wave）。L6 工作量小（半天），不会影响 Wave 2 节奏。

---

## High 发现（建议但不强制）

| # | 来源 | 描述 | 修正 |
|---|---|---|---|
| H-1 | C/U6 | `_vision_enrich_tags` (line 352, image-only ingestion) 也是 OpenAI-only | 新增 **L9**：`_vision_enrich_tags` 走 vlm_adapter |
| H-2 | C/U5 | `_call_openai_embedding` (line 1024, 3 处调用) 是 OpenAI-only，Anthropic 用户语义搜索仍坏 | 新增 **L10**：embedding 走 OpenAI 或 Voyage（Anthropic 推荐）|
| H-3 | A/AX1 | L4 错误分类与 F1 重叠，应抽 `VLMProviderError` 共享枚举 | 添加约束到 L4 + F1 |
| H-4 | A/AX3 | M2 横幅应抽 `MissingKeyBanner.vue` 组件而非复制 DiagnosticsPanel 样式 | 添加约束到 M2 |
| H-5 | B | M4/M5 重命名验收只 grep 定义遗漏调用点 | 升级验收：grep 定义 + 调用 |
| H-6 | C/U7 | review_engine VLM 依赖 H3，未与 L 同 Wave → library 能用而 review 不能用 | 把 H3 提到 Wave 2 与 L 同期 |
| H-7 | C/U8 | M3 onboarding 对老用户不可见，提报问题的用户**永远看不到** | M3 + 在 LibraryView 加"未配置 → 引导 modal"入口（M9） |
| H-8 | A | N1"≤4 个"未数 `/`(startup) 实际 8→5 | 修订 N1 验收文字 |

---

## Minor / Observation（记录）

- L5 漏列 SettingsView.vue 修改
- L7 health 字段需上 OpenAPI 契约
- 启用 LLM 后的隐私 / 成本告知（U9）建议进 K（时间允许）

---

## 修正后影响

| 项目 | 修正前 | 修正后 |
|---|---|---|
| Critical 数 | 5 | 0（应用全部修正） |
| 任务总数（L+M+N） | 22 | 27（+L8/L9/L10 + M8 + M9 + N5 拆分为 5 子任务但合并为 N5 单任务） |
| 估时 | 9.5w | ~11w |
| 用户视角覆盖率（C 评估） | 60% | ~85% |

---

## 修正完毕后的下一步

1. ✅ 应用上述修正到 `dev-plan-v0.19.0.md`
2. ✅ 更新 TODO_NEXT.md
3. ✅ Wave 1 起点：**M2** (Library "AI 未启用" 横幅) — 与 N6（删除 production redirect）并行
4. （可选）派 Critical-only 重审，确认全部消除

**审计判定**：⚠️ 必须先应用 5 Critical 修正才能进 Phase 2 编码。
