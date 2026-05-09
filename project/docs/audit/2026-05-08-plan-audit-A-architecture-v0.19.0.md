# 计划审计报告 A — 架构一致性 (v0.19.0 Feature L/M/N)

**审计时间**：2026-05-08
**审计维度**：A 架构一致性（独立子 Agent）
**审计范围**：Feature L (L1-L7) + Feature M (M1-M7) + Feature N (N1-N8)
**审计依据**：
- `project/docs/dev-plans/dev-plan-v0.19.0.md` lines 109-180, 122-138 (Wave 重排)
- `project/docs/tech-specs/architecture.md` v1.0 (2026-03-19)
- `project/docs/tech-specs/coding-standards.md`
- `project/modules/adapters/vlm_adapter.py` (已实现的 v0.17 协议)
- `project/modules/library/core/core_mixin.py` (line 192-205, 859-916, 1461-1549, 3855-3866)
- `project/apps/desktop/ui-vue/src/router/index.js`

**结论**：⚠️ **需修改**（无 Critical 阻断；3 个 Important 修订；多处 Minor）

---

## 检测结果

| # | 检测项 | 状态 | 证据 |
|---|---|---|---|
| A1 | 架构冲突 | ✅ | `architecture.md:559-567` 明确"跨模块通信的唯一通道"是 adapters 层；让 library 调 vlm_adapter 与现有 review_engine（`scene_summarizer.py:32`、`video_stream_analyzer.py:26`、`frame_diagnostics.py:63`）的 DI 模式一致 |
| A2 | 重复设计 | ⚠️ | L4 的"分类错误（auth/rate_limit/network/parse）"与 Feature F1 的"VLM 失败分级显现（auth/429/timeout/network）"严重重叠；F1 + L4 应统一在同一错误分类抽象之上，而不是各做各的 |
| A3 | 命名不一致 | ⚠️ | `coding-standards.md:123-135` 定义 `snake_case`，但未规定 `_前缀` 表示私有；`core_mixin.py:310` 已用 `_extract_pcm` 风格。M4 把 `object_detection_simulation`（公共方法名，无下划线）改名为 `_detect_objects_heuristic`（带下划线）会**改变其访问性语义**——现有调用方 `video_asset_toolkit.py:321,325,644` 都是 `self.xxx()` 内部调用，没有外部调用方，可改；但需确认没有任何 mock 或 monkey-patch 依赖原名 |
| A4 | 超出边界 | ✅ | L 只动 `library/core/core_mixin.py` 与 `adapters/vlm_adapter.py`；M 只动前端 + `step1_material_analysis/video_asset_toolkit.py`；N 只动 router/labels/NavBar — 三者没有触碰 step2/3/4/5/6/7、capabilities、workflow_engine、contracts、job_store 等核心管线 |
| A5 | 依赖方向 | ✅ | `architecture.md:117-120` 把 `library` 与 `adapters` 同列于"支撑层（Infrastructure Layer）"；同层互引被允许。grep 现状：`modules/library/` 当前未 import `modules.adapters/*`，但 `app_api/server.py:506` 已经 `from modules.adapters.vlm_adapter import get_vlm_adapter`，证明这是已有合法模式 |
| A6 | 数据库兼容 | ✅ | L/M/N 均不引入新表/字段；`_meta.model_version` 字段在 `core_mixin.py:3863` 已存在，L6 只是把它从 `gpt-4o-mini` 单一 fallback 扩展为多 provider 字符串（同字段、不同值）；不需要 migration |

### 额外检测（针对此次扩展）

| # | 检测项 | 状态 | 证据 |
|---|---|---|---|
| AX1 | N "顶级 path ≤ 4" 与 architecture.md UI 分层 | ✅ | `architecture.md` 9.1-9.2 只规定 API 路由层级（`/api/*`），未约束前端路由顶级数；router 重构属于前端组件层职责，合规 |
| AX2 | L4 错误分类策略是否已有约定 | ⚠️ | `coding-standards.md:521-665` 只定义了**通用**异常体系（`VideoEditorError` 树）和五条铁律，但未定义"AI provider 错误分类"的标准枚举（auth/rate_limit/network/parse 的命名）。这是**首次引入** vendor-error-class 的命名空间，应在 J3"adapter 协议"文档中固化，避免 L4 与 F1 各定一套 |
| AX3 | M2 "AI 未配置"横幅是否复用 DiagnosticsPanel 模式 | ⚠️ | `DiagnosticsPanel.vue:30-32` 的 `dp-notice` 样式是"VLM 未配置"提示。Plan M2 写"参照 `DiagnosticsPanel.vue:31` 模式"但**只是参照样式而非组件复用**。当前 review/library 是两个独立模块，没有共享组件库；建议在 M2 之前先把"未配置警告"抽成 `components/common/MissingKeyBanner.vue`，由两边都引用，避免出现两份独立的 dp-notice 样式 + 文案 |

---

## Critical 发现（阻断）

无。

---

## Important 发现（建议修订）

### IMP-1：L4 与 F1 的 AI 错误分类必须同源

**问题**：dev-plan v0.19.0 在两处独立提到了 AI 错误分级：

- F1（line 54）：`VLM 失败分级显现（auth/429/timeout/network）→ 用户可见 toast + 指引`
- L4（line 135）：`分类错误（auth/rate_limit/network/parse）+ 日志 + UI 可见`

两处枚举值不一致：F1 用 `429`，L4 用 `rate_limit`；F1 用 `timeout`，L4 没有 timeout（只有 network）；L4 多了 `parse`。

**风险**：
- 前端会出现两套错误码处理分支（review 走 F1 体系，library 走 L4 体系）
- 用户在 settings 配置同一个 key 失败时，两个模块给出不同错误文案
- 后续 H3 "VLM settings → adapter env var 桥接" 也需要这个错误分类，会变成第三套

**建议**：
1. 在 Wave 1 之前先定义**单一**`VLMProviderError` 枚举（建议放 `modules/adapters/vlm_errors.py` 或扩展 `modules/exceptions.py:564 ExternalToolError` 子树）。
2. F1 和 L4 都基于此枚举，dev-plan 的两处描述统一术语。
3. 推荐枚举：`{auth_failed, rate_limited, timeout, network, parse, missing_key, unknown}`（覆盖两边需求）。
4. 把这个枚举固化进 J3"adapter 协议"开发者文档，作为 v0.19 的契约产出。

---

### IMP-2：M2 横幅应抽组件，不是复制样式

**问题**：M2 描述"参照 `DiagnosticsPanel.vue:31` 模式"，但 `DiagnosticsPanel.vue` 在 review 模块下，Library 在另一个独立 view 下。直接复制 `dp-notice` CSS 与文案会形成第二份"未配置警告"实现。

**架构风险**：
- v0.19 同时引入"前端 ≥10 个组件测试"（F5），如果未配置横幅是两份独立 markup，意味着两份独立测试
- 后续若 Onboarding（M3）也要展示"key 未配"提醒，会出现第三份
- 这违反 architecture.md §1.1"接口隔离"在前端的等价原则（重复 markup = 隐式接口）

**建议**：
1. 在 Wave 1 实施 M2 之前，先抽取 `apps/desktop/ui-vue/src/components/common/MissingKeyBanner.vue`（props: `provider, settingsLink, dismissible`）。
2. M2 改为"在 LibraryView 中使用 `<MissingKeyBanner :provider="'vlm'" />`"。
3. F1/F2 的"VLM 未配置"提醒在下个 Wave 重构时切到同一组件。
4. 工作量 +0.5 天（一次性建组件），但消除三份独立横幅维护成本。

---

### IMP-3：M4/M5 重命名与 v0.17 已稳定的"接口尾巴"风险

**问题**：`object_detection_simulation` / `scene_description_simulation` 是**公共方法名**（无下划线前缀），M4/M5 改成下划线前缀方法。这等于把"public API"降级为"private"。

**核查**：
- `grep -r object_detection_simulation/scene_description_simulation` 在 `tests/` 下 0 结果
- 在 `project/` 下只有 `video_asset_toolkit.py` 三处自调用
- 没有 monkey-patch 或外部引用

**结论**：技术上**安全可改**，但建议 M4/M5 在重命名前先 grep 一次完整工作区（含 `apps/cli/`、`apps/desktop/launcher.py`、`scripts/`）确认无第三方调用，再重命名。

**进一步建议**：把 plan M4/M5 的验收标准从 grep 单文件
```
grep `_simulation` 函数定义在 `video_asset_toolkit.py` = 0
```
扩展为
```
grep `simulation\|describe_scene\|detect_objects` 全工作区 = 仅出现在 _heuristic 命名下
```
以彻底关闭"漏改 import"的可能。

---

## Minor 发现 / Observation

### MIN-1：N1 "顶级 ≤ 4" 与现状 routes 定义对照

`router/index.js:5-127` 当前顶级（不含 redirect）route 是：`/`(startup)、`/library`、`/create`、`/roughcut`、`/review`、`/workflows`、`/tools`、`/settings` — 共 8 个（plan 文档说 7 个，未数 `/`）。

N1 验收"≤ 4 个（不算 redirect）"但要保留 `/`(startup) 作为入口。建议 N1 改为：
> 顶级 path 压到 5 个：`/`(startup) + `library / create / tools / settings`；其它原顶级全部 redirect 或子路由

避免审计阶段被字面值卡住。

---

### MIN-2：N5 重命名对深链的影响

N5 把 `/create/workflow` → `/create/guide`。N5 自己有 redirect 兜底，但需注意：
- `i18n/labels.js:50` 有 `workflow: '工作流'` label key — 改完后这个 key 是仍然指向 `/create/guide`，还是新建 `guide` key？
- `WorkflowPanel.vue` 组件本身是否要重命名为 `GuidePanel.vue`？

建议 N7 验收里追加一条：`grep -r "/create/workflow" 在前端代码（不含 router redirect 段）= 0`。

---

### MIN-3：L7 引入新 health 字段，但 dev-plan 未列入 contracts 变更

L7 要求 `/api/library/health` 返回 `{llm_status: ok|missing_key|auth_failed|rate_limited|...}`。

按 architecture.md §3.6"Contracts 层"，所有跨模块/跨层数据应有契约。当前 `contracts/` 下只有 4 个核心契约（materials/script/workflow/render），没有 health 契约。

**建议**：要么在 L7 验收里追加"在 `contracts/library_health.json` 新增 schema"；要么明确 `/api/library/health` 是 app_api 层的非契约响应（简单 dict），不上 schema。两种都可，但要写明，避免 v0.20 出现"为什么这个端点没契约"的回头修补。

---

### MIN-4：L 系列对 "Settings UI hint" 的修订（L5）涉及前端文案，但 dev-plan 没列文件

L5 描述"settings UI hint 修订：Anthropic 字段说...与代码一致"。需要修改的文件应该是 `apps/desktop/ui-vue/src/views/SettingsView.vue` 或类似位置。

dev-plan v0.19.0 line 124 只列 "涉及文件: `modules/library/core/core_mixin.py`、`modules/adapters/vlm_adapter.py`"——**漏列了前端 SettingsView**。

建议在 dev-plan L 段的"涉及文件"补一条 "`apps/desktop/ui-vue/src/views/SettingsView.vue`（L5 hint 文案）"。

---

### MIN-5：L+M+N 与 v0.18 audit 报告中"未释放功能"的关系

memory 提示"v0.18.0 6 个遗留问题待 v0.19"。dev-plan v0.19.0 文档没有在第 9 节"附录"或 Feature L/M/N 段明确说"这些遗留问题中是否有与 L/M/N 重叠的"。

建议 plan-audit 闭环维度（B 维度）确认"v0.18 遗留 6 项"与"L/M/N 7+7+8=22 项"的重叠/补充关系，避免双 PR 改同一段代码。

---

### MIN-6：Wave 重排的 risk

dev-plan line 187-198 把 L 切到 Wave 2、M1-M3 切到 Wave 1、M4-M7 切到 Wave 3。

风险：
- **M4/M5 重命名（Wave 3）发生在 L2 切 vlm_adapter（Wave 2）之后**——如果 L2 实现里调用 `_call_openai_text` 时也碰到 `scene_description_simulation`/`object_detection_simulation`（间接通过 evidence 字典），M4/M5 重命名会破坏 L2 已稳定的输出。
- 实操建议：**M4/M5 与 L2 在同一个 PR/Wave 内合并完成**，避免半中间态。

---

## 总结

| 维度 | 评分 |
|---|---|
| 架构冲突（A1） | ✅ 合规 |
| 重复设计（A2） | ⚠️ L4 ↔ F1 错误分类需统一 |
| 命名一致（A3） | ⚠️ M4/M5 改可见性，需补充 grep 验收 |
| 边界控制（A4） | ✅ 合规 |
| 依赖方向（A5） | ✅ 合规（同层互引允许） |
| 数据库兼容（A6） | ✅ 无 migration |
| UI 分层（AX1） | ✅ 合规 |
| 错误分类策略（AX2） | ⚠️ 首次引入，需固化 |
| 跨模块复用（AX3） | ⚠️ 应抽 MissingKeyBanner |

**整体**：架构层面 Feature L/M/N 是**良好的修复型扩展**——L 把已有 vlm_adapter 协议从 review 推到 library，闭合了 v0.17 设计但 v0.18 漏接的循环；M 解决"诚实化"的 UX 信任债；N 是纯前端路由整理。

但建议在 Wave 1 启动前**完成 IMP-1（错误枚举单源）+ IMP-2（横幅组件单源）+ MIN-6（M4/M5 与 L2 合并）三项前置改动**，避免"两套实现"在 v0.19 内固化。

---

**审计完成日期**：2026-05-08
**审计 Agent**：plan-audit 维度 A
