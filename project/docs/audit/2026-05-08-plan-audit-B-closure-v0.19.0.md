# Plan Audit B — Closure Completeness (Feature L/M/N)

> **审计对象**: `project/docs/dev-plans/dev-plan-v0.19.0.md`，仅 Feature L (L1-L7) / M (M1-M7) / N (N1-N8)
> **审计维度**: 闭环完整性（Closure Completeness）
> **审计日期**: 2026-05-08
> **基线 Commit**: 95199fd（计划基线）
> **审计依据**: dev-governance §3.5 写作规范、§3.5.3 计划质量门禁
> **总体结论**: **条件通过** — 2 项 Critical 阻断 + 7 项 High 缺口 + 5 项 Medium 优化建议

---

## 一、检测结果速览

| # | 维度 | 评级 | 主要问题 |
|---|------|------|----------|
| B1 | 功能拆解完整性 | ⚠️ HIGH | M3 onboarding 步骤数与现状脱节；M2/F2 未明确组件复用边界 |
| B2 | 任务可验证性 | ✅ 通过 | 22/22 任务均含可执行验收（grep/curl/单测/操作步骤），少量需补强参数 |
| B3 | 依赖链完整性 | ⚠️ HIGH | L7 隐式依赖 L1+L4 但未声明；M1 依赖 L6；N5 与 N3/N4 共享 redirect 风险无依赖标注 |
| B4 | 边界明确性 | ⚠️ MED | L 与 M 在"UI 文案修订"上存在交叠（L5 vs M2/M6）；M 与 F 未画分 |
| B5 | Gap 分析对齐 | ⚠️ MED | L 引言遗漏 `_call_openai_text` 调用点（line 2135）；N 引言未提 ProductionView.vue 残留 |
| B6 | 编号合规 | ✅ 通过 | L1-L7 / M1-M7 / N1-N8 与 E/F/G/H/I/J/K 编号风格一致 |
| B7 | 事实准确性 | ⚠️ HIGH | 5 处文件:行号正确；DiagnosticsPanel.vue:31 引用方向偏差；N 引言"7 个一级入口"准确 |
| B8 | 跨版本推迟 | ✅ 通过 | 未发现"留给 v0.20"等推迟语句 |
| BX1 | L1 vs H3 是否重叠 | ⚠️ MED | 两者职责确有差异但表面相似，必须显式分工说明 |
| BX2 | M2 vs F2 组件复用 | ⚠️ MED | 计划未明确是否抽取共用 banner/notice 组件 |
| BX3 | N5 改名影响范围 | ❌ **CRITICAL** | 至少 14 个文件 / 20+ 处硬编码 `/create/workflow`，计划仅提"UI labels 同步" |
| BX4 | M4/M5 重命名覆盖度 | ❌ **CRITICAL** | 内部调用点 3 处全在同文件，但与外部 step1 模块的隐含契约缺审查 |

---

## 二、逐项检测详情

### B1 — 功能拆解完整性（⚠️ HIGH）

**Issue A 子点覆盖检查**：

| 用户报告子点 | 是否拆解为任务 | 备注 |
|--------------|----------------|------|
| `_llm_tagging_enabled` 仅查 OPENAI_API_KEY | ✅ L1 | 验收：单测覆盖三种场景 |
| 未配 key 时静默走 heuristic | ✅ L4 + L7 | 验收：health 端点状态字段 + UI 横幅 |
| Settings UI 暴露 Anthropic key 但未被 library 读取 | ✅ L5 + M2/M3 | hint 修订 + UI 提示 |
| Anthropic key hint 文字不准 | ✅ L5 | 验收：操作描述 |
| `_call_openai_json` 直接调 OpenAI SDK | ✅ L2 | 验收：grep `_call_openai_` = 0 |
| `_call_openai_text` 同样问题 | ✅ L3 | **遗漏**：L 引言只提 `_call_openai_json` (line 877)，但 `_call_openai_text` 在 line 898 + 调用点 line 2135 也需迁移 |
| `_meta.model_version` 不反映真实 provider | ✅ L6 | 验收清晰 |

**Issue B 子点覆盖**：

| 用户报告子点 | 拆解任务 | 备注 |
|--------------|---------|------|
| 7 个顶级入口 | ✅ N1 + N7 | |
| `/create/workflow` 与 `/workflows` 命名冲突 | ✅ N5 | 但 BX3 揭示影响面被低估 |
| 编辑动作散落 3 处 | ✅ N3 + N4 + N5 | |
| `/production` 重定向死代码 | ✅ N6 | 但 ProductionView.vue 文件本体未提 |

**遗漏（HIGH）**：

1. **L 系列遗漏 OPENAI_VISION_MODEL / OPENAI_MODEL 环境变量迁移** — `core_mixin.py:881-885, 1544-1547` 多处读 `OPENAI_MODEL`；切换到 Anthropic 时 `model_version` 字段如何决定？L6 只说"反映真实 provider"，未列出每个 provider 默认 model 名常量出处。

2. **M3 onboarding 步骤数与现状脱节** — 计划"M3 OnboardingModal.vue 新增 step：API Key 配置引导"，但 OnboardingModal.vue 当前是 3 步（step 0/1/2），且"不做边界"写"不重写 onboarding 步骤数"。**矛盾**：新增 step 等同于改步骤数。需要澄清是"插入新 step"还是"在某 step 内嵌入子区块"。

3. **N 系列未列出 14 个文件级影响**（详见 BX3）— 仅一句"UI labels 同步"无法覆盖。

---

### B2 — 任务可验证性（✅ 通过）

22 个任务每个均有可执行验收。抽样确认：

- L1：`单测：仅 ANTHROPIC_API_KEY 时返回 True` — 可直接写 monkey patch test。
- L7：`curl 端点，断言字段存在` — 端点已存在（`/api/library/health` 在 `library_routes.py:311`），仅是扩展返回 schema。
- M4/M5：`grep _simulation 函数定义在 video_asset_toolkit.py = 0` — 可机械验证。
- N1：`router/index.js 顶层 routes ≤ 4（不算 redirect）` — 可数。
- N6：`grep production in router = 0` — 可数。

**轻微改进建议（不阻断）**：
- L4 验收"单测：注入 4 类异常，断言 logger 调用与返回错误码"应明确错误码命名规范（`auth_failed` vs `AUTH_FAILED` vs `401`），与 L7 health 字段保持一致。
- M7 E2E 验收应指定测试文件路径（如 `tests/e2e/library_banner.spec.ts`）。

---

### B3 — 依赖链完整性（⚠️ HIGH）

**重建依赖图**：

```
L1 (env detect) ──┐
                  ├─→ L2 (vlm_json) ──→ L4 (异常分类) ──┐
L2 (vlm_json)  ──┘                                     ├─→ L7 (health 字段)
                                                       │
L3 (vlm_text) ──→ L4 ───────────────────────────────────┘
L5 (UI hint)  ←── 依赖 L1 已生效

M1 (badge) ←── 依赖 L6 (model_version 字段标准)
M2 (banner) ←── 依赖 L7 (health 状态)
M3 (onboarding) — 与 L1/L5 同 PR（风险表已注明）
M4/M5 (重命名) — 独立
M6 (UI 文案) ←── 依赖 M4+M5 完成
M7 (E2E) ←── 依赖 M1+M2+M3 全部完成

N1 ←── 依赖 N2/N3/N4/N5 单独减少 1 个
N2/N3/N4 — 独立，可并行
N5 (改名 guide) — 与 N3/N4 同步出 redirect，否则旧 URL 半失效
N6 — 独立
N7 (labels) ←── 依赖 N1-N6 路径已定
N8 (E2E) ←── 依赖 N1-N7 全部完成
```

**HIGH 阻断**：

1. **L7 隐式依赖未声明**：health 端点要返回 `auth_failed` 等状态，必须 L4 完成异常分类 + L1 完成 multi-key 检测。计划未在 L7 任务行写"依赖：L1+L4"。
2. **M1 隐式依赖 L6**：badge 显示 `llm:gpt-*` 需要 `_meta.model_version` 已是 provider-specific 格式，否则 badge 永远显示 `unknown`。Wave 划分把 M1 放 Wave 1，L6 放 Wave 2，**会出现 M1 上线后两周内 badge 不工作**。
3. **N3/N4/N5 共享 redirect 表**：三者都改 `/create/*` 路径，必须串行或同 PR。Wave 4 把 N3/N4/N5 都列在同期，但未明确串行。

---

### B4 — 边界明确性（⚠️ MED）

**Feature 间交叠**：

- **L5（settings UI hint）vs M2/M6（UI 文案）**：L5 改 SettingsView.vue:86 hint，M6 改"AI 场景描述"等用户可见文案。两者都是 i18n / 文案修订，可能导致同一 PR 内冲突。建议把 L5 并入 M 系列，或 L5 仅限"hint 文字"。
- **M2（Library 横幅）vs F2（DiagnosticsPanel 显示原因）**：详见 BX2。
- **M3 onboarding API Key step vs L5 settings hint**：风险表已注明"由同一人/同一 PR 完成"，但任务表未交叉引用。

**任务内重叠（MED）**：
- L2 + L3 都涉及 vlm_adapter 包装，可考虑合并为 L2a/L2b 子任务，确保签名一致。

---

### B5 — Gap 分析对齐（⚠️ MED）

**L 引言现状证据**："只走 OpenAI（line 199-202 _llm_tagging_enabled 仅检查 OPENAI_API_KEY），且通过 _call_openai_json (line 877) 直接调 OpenAI SDK"

**漏掉的代码现实**：
- `_call_openai_text` 在 line 898 — L 引言未提，L3 才提到。
- 调用点 `_call_openai_json` 在 line 1502, 1523；`_call_openai_text` 在 line 2135。**引言隐含"library 标签器"边界，但实际跨多个 mixin 方法**。
- `_openai_client()` 在 line 870 — 是 SDK 实例化的入口。L2 应明确该入口是否保留还是删除。

**N 引言现状证据**：路径表准确（`router/index.js` 7 个顶级路径已核对）；但**漏掉 ProductionView.vue 内部仍用 `/production/workflow` 调用**（line 108, 110）。该文件似乎无 import 引用（属于死代码），N6 应同时删除文件本体。

---

### B6 — 编号合规（✅ 通过）

L1-L7 / M1-M7 / N1-N8 与 E/F/G/H/I/J/K 一致。表格列数（需求 + 验收）格式相同。

---

### B7 — 事实准确性（⚠️ HIGH）

| 引用位置 | 实际代码 | 结论 |
|---------|---------|------|
| `core_mixin.py:199-202 _llm_tagging_enabled` | line 199-202 ✅ | 准确 |
| `core_mixin.py:877 _call_openai_json` | line 877 ✅ | 准确 |
| `core_mixin.py:1461 _llm_structured_tags` | line 1461 ✅ | 准确 |
| `video_asset_toolkit.py:532 object_detection_simulation` | line 532 ✅ | 准确 |
| `video_asset_toolkit.py:641 scene_description_simulation` | line 641 ✅ | 准确 |
| `DiagnosticsPanel.vue:31` | line 30-32 是"VLM 未配置..."notice 块 | **方向略偏**：line 31 是文案行，notice 容器在 line 30 (`<div v-if="!vlmAvailable" class="dp-notice">`)。M2 引用应指向"参照 dp-notice 模式"或更广义"参照 notice 块（line 30-32）" |
| OnboardingModal.vue 328 行 | 文件 328 行 ✅；3 个 step ✅ | 准确 |
| router/index.js 7 个顶级路径 | 实数 7 个（library/create/roughcut/review/workflows/tools/settings）✅ | 准确 |

**缺失的事实陈述**：
- L 引言未提 `core_mixin.py:870 _openai_client()` 是 SDK 实例化入口。
- L 引言未提 `core_mixin.py:898 _call_openai_text` 与 `core_mixin.py:2135` 调用点。
- N 引言"`/production` 重定向已无活引用"准确（其唯一 caller 是 ProductionView.vue 内部，且该文件似乎无 import）— 但应在 N6 任务列出"删除 ProductionView.vue 文件"。

---

### B8 — 跨版本推迟（✅ 通过）

22 个任务均无"留给 v0.20"语句。Wave 划分清晰，全部 22 任务在 Wave 1-4 内闭环。

---

## 三、额外检测项

### BX1 — L1 与 H3 重叠分析（⚠️ MED）

**H3 范围**：VLM settings UI（SettingsView.vue:103+，`vlmProvider` 下拉 + `vlmOpenaiKey/vlmClaudeKey` 输入）→ 适配器 env var。
**L1 范围**：library 标签器读取 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`（顶层全局 AI key 区域，SettingsView.vue:73-87）。

**结论**：两者**确实指向不同 UI 区域**（VLM 专用 key vs 全局 AI key），但代码层面环境变量 namespace 共用（都是 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` 进程级别）。

**风险**：
- 用户在 L1 完成后，仅设全局 Anthropic key，library 工作正常；但 VLM 仍需在 H3 流程下设置自己的 key（**双 source of truth**）。
- 计划应明确：是统一为单一 key store，还是保留两个独立来源。

**建议（MED）**：在 L1 任务下加一行"对齐声明：本任务仅修 library，VLM key 桥接是 H3 责任。两者在 settings_service 层共享 env var，但在 UI 层不混淆"。

---

### BX2 — M2 与 F2 复用分析（⚠️ MED）

**M2**：Library 顶部 "AI 标签未启用" 横幅（参照 `DiagnosticsPanel.vue:31` 模式）。
**F2**：DiagnosticsPanel 流分析失败时显示原因（**修改**同一组件）。

**复用潜力**：两者都是"在 Vue 组件顶部显示提示信息"，可以抽出 `<NoticeBanner severity="warning|info">` 共用组件。

**计划现状**：M2 写"参照 DiagnosticsPanel.vue:31 模式"暗示复制粘贴 CSS，**未提共用组件**。F 系列也未提。

**结论**：不算阻断，但属"做完了发现重复"的典型坑。

**建议（MED）**：增设 M2.5 任务"抽取 NoticeBanner 共用组件，M2/F2 同源使用"，或在 M2 验收中加"必须复用 F2 同款 CSS class"。

---

### BX3 — N5 改名 `/create/workflow` → `/create/guide` 影响面（❌ CRITICAL）

**实际影响范围**（grep 验证）：

```
14 个 .vue/.js 文件，20+ 处硬编码 /create/workflow 字符串：
  - layout/AppNav.vue:6
  - common/ProjectDialog.vue:147
  - capabilities/TopicCopy.vue:86
  - workflow/Step1-7Materials/Topics/Script/Match/Frames/Rough.vue（共 6 文件，多处 router.push）
  - workflow/WorkflowPanel.vue:111
  - onboarding/OnboardingModal.vue:161
  - views/StartupView.vue:121, 136
  - views/CreateView.vue:181, 230
```

外加 `i18n/labels.js` 内 workflow 相关 label。

**计划现状**：N5 验收只写"UI labels 同步；旧路径 redirect"，N7 写"i18n labels.js 同步 + NavBar 组件重构"。但**未涵盖 13 个 step/component 文件中的硬编码**。

**风险**：
- 仅做 redirect 不改硬编码 → 用户每次点"下一步"先跳 `/create/workflow/2`，浏览器历史污染（每个老路径转 301），E2E 测试用例必须显式断言 redirect 行为。
- 不改硬编码 → 改名失效（旧名仍为事实标准）。

**严重度**：CRITICAL — 计划严重低估工作量与回归测试范围。

**建议**：
1. N5 拆为 N5a（router 改名 + redirect）+ N5b（替换 14 个文件中的 20+ 处硬编码 `/create/workflow` → `/create/guide`）+ N5c（验证 hash router 兼容性，因为代码用 `createWebHashHistory`）。
2. N5b 验收必须是 `grep "/create/workflow" 在 src/ = 0`（router/index.js 中 redirect 项除外）。

---

### BX4 — M4/M5 `_simulation` 重命名覆盖度（❌ CRITICAL）

**grep 实际范围**（step1 模块全文）：

```
project/modules/step1_material_analysis/video_asset_toolkit.py:
  Line 321: result["objects"] = self.object_detection_simulation(video_path)
  Line 325: result["scene"] = self.scene_description_simulation(video_path)
  Line 532: def object_detection_simulation(self, video_path):
  Line 641: def scene_description_simulation(self, video_path):
  Line 644: objects = self.object_detection_simulation(video_path).get(...)
```

**外部依赖**（cross-module 检查）：
- `tests/` 下 — 无引用（搜索结果 0 条）。
- 其他 modules — 无 import 链。
- `.agents/skills/manage-videos/analyze_videos.py:206` 有同名风格函数 `cloud_analysis_simulation`，但**与 M4/M5 目标无关**（不同文件、不同对象）。

**结论**：M4/M5 内部覆盖度尚可（3 处 self 调用都在同一文件），但：

1. **隐含契约风险**：plan 验收只写"grep `_simulation` 函数定义在 `video_asset_toolkit.py` = 0"。但 grep 的应该是**全部出现**（包括内部调用）= 0。否则 `self.object_detection_simulation()` 调用还在，重命名不完整。
2. **跨文件残留**：`.agents/skills/manage-videos/analyze_videos.py` 也有 `cloud_analysis_simulation` 风格函数 — 不在本计划范围，但应在"不做边界"明确"M 仅限 video_asset_toolkit.py，agents skill 包另议"。

**严重度**：CRITICAL — 验收语义不严，会出现"函数定义改了但调用没改"的破坏性合并。

**建议**：
1. M4/M5 验收改为：`grep "object_detection_simulation\|scene_description_simulation" 在 project/modules/step1_material_analysis/video_asset_toolkit.py = 0`（即定义和所有调用点都消失）。
2. 在 M 不做边界增加：`不影响 .agents/skills/manage-videos/analyze_videos.py 的 cloud_analysis_simulation`。

---

## 四、建议修订清单

### Critical（合并前必修）

| 编号 | 内容 | 责任段落 |
|------|------|----------|
| C1 | N5 拆分为 N5a/N5b/N5c，验收增加"grep `/create/workflow` 在 src/ 非 router 中 = 0" | Feature N |
| C2 | M4/M5 验收改为 grep 定义+调用全消失；M 不做边界排除 .agents/ | Feature M |

### High（建议合并前修，否则在 Phase 1 实施计划中补全）

| 编号 | 内容 | 责任段落 |
|------|------|----------|
| H1 | L 系列引言补全：`_call_openai_text` (line 898) + 调用点 (line 1502, 1523, 2135) + `_openai_client` (line 870) | Feature L 引言 |
| H2 | L7 任务行加显式依赖：`依赖：L1+L4` | Feature L 表格 |
| H3 | M1 与 L6 跨 Wave 风险：把 L6 提至 Wave 1，或把 M1 推至 Wave 2 | §3 出版本流程 |
| H4 | M3 与"不做边界—不重写 onboarding 步骤数"矛盾，需澄清"插入 step" vs "嵌入子区块" | Feature M / 不做边界 |
| H5 | N6 增加"删除 `apps/desktop/ui-vue/src/views/ProductionView.vue`"任务点 | Feature N |
| H6 | N3/N4/N5 在 Wave 4 必须串行或同 PR，需在 Wave 描述明示 | §3 出版本流程 |
| H7 | DiagnosticsPanel.vue 引用调整为 `line 30-32 (.dp-notice 块)` 而非裸 line 31 | Feature M2 |

### Medium（优化建议）

| 编号 | 内容 |
|------|------|
| M1 | 抽取 `<NoticeBanner>` 共用组件（M2 + F2） |
| M2 | L4 与 L7 的错误码命名统一规范 |
| M3 | L1 加"对齐声明 vs H3"边界文字 |
| M4 | M7 / N8 E2E 验收指定测试文件路径 |
| M5 | L2 + L3 合并为 L2a/L2b 子任务，签名对齐 |

---

## 五、最终判定

- **Critical 阻断**: 2 项（C1 N5 拆分；C2 M4/M5 验收语义）
- **High 缺口**: 7 项
- **Medium 优化**: 5 项

**判定**: **条件通过** — 修正 2 项 Critical + 至少 H1/H2/H5（事实补全 + 依赖标注 + 文件清理）后可进入 Phase 1 实施。其余 High/Medium 可在 Phase 1 实施计划中详细补全，不必修改 dev-plan 主文档。

L/M/N 三个 Feature 整体方向正确，与用户报告吻合，验收基本可执行。主要风险在**改名工作的影响面被低估**（N5 / M4/M5 的硬编码扫描遗漏）以及**跨 Feature 的依赖隐式声明**（L7→L1+L4、M1→L6）。

---

**审计人**: Claude Code（plan-audit 维度 B 子 Agent）
**报告完结**
