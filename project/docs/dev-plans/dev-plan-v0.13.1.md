# VideoEditor 版本开发计划（v0.13.1）

**文档版本：** V1.0
**日期：** 2026-03-25
**基线 Commit：** aa46c69 (Merge pull request #3 from angeless/claude/recursing-wu)
**基线 VERSION：** 0.12.12
**开发分支：** `fix/ux-p0-runtime-failures`（基于 `claude/reverent-curran`）
**版本性质：** PATCH — 纯 Bug 修复与体验缺陷补全，无新功能

**来源报告：**
- `docs/ux-audit/UX_TEST_REPORT_20260325_Creator_Simulation.md`（代码走查，综合评分 2.9/5.0）
- `docs/ux-audit/UX_TEST_ADDENDUM_20260325_Runtime.md`（实测验证，评分修正至 2.6/5.0）

---

## 1. 版本目标

修复 UX 实测发现的 3 个 P0 运行时 Bug 与 3 个 P1 体验缺陷，使新用户能够完整走完「创建项目 → 导入素材 → 启动工作流」核心路径，且任何操作失败时均有明确的用户可见反馈。

---

## 2. 版本范围

### 包含的需求

- **R1** 消除 Step 1「分析素材」静默失败（P0）
- **R2** 修复前后端项目状态脱节，标题栏与 `/api/status` 同步（P0）
- **R3** 工具箱能力状态准确标注，区分「功能存在」与「当前可执行」（P0）
- **R4** Step 1 新增素材选择 UI，替代当前空白页面（P0）
- **R5** 素材导入进度反馈，展示文件名与百分比（P1）
- **R6** 工作流 7 步命名去技术化，改为创作者语言（P1）
- **R7** 设置页新增「测试连接」按钮，含后端验证端点（P1）
- **R8** 集成测试 + 回归验证（P0）

### 不包含的需求（Future）

- **NEW-4** 文件选择器 Web 降级（需重构文件选择架构，工程量大，留 v0.14）
- **NEW-6** 两套工作流系统整合（需产品架构决策，留 v0.13.0 规划）
- **P1-4** Step 4 素材匹配透明化（前后端改动范围较大，留 v0.13.0）
- **v0.13.0 全部新功能**（MCP Server、时间线多轨编辑器、FAISS 升级、导出适配器等）
- 国际化（留后续版本）

---

## 3. 任务列表

| 任务ID | 任务名称 | 所属模块 | 目标版本 | 状态 | 优先级 |
|--------|---------|---------|---------|------|--------|
| R1 | 消除 Step 1「分析素材」静默失败 | vue_ui / workflow | v0.13.1 | ⬜ Planned | P0 |
| R2 | 修复前后端项目状态脱节 | vue_ui / app_api | v0.13.1 | ⬜ Planned | P0 |
| R3 | 能力工具状态准确标注 | vue_ui / capabilities | v0.13.1 | ⬜ Planned | P0 |
| R4 | Step 1 新增素材选择 UI | vue_ui / library | v0.13.1 | ⬜ Planned | P0 |
| R5 | 素材导入进度反馈 | vue_ui / library / app_api | v0.13.1 | ⬜ Planned | P1 |
| R6 | 工作流步骤命名去技术化 | vue_ui / i18n | v0.13.1 | ⬜ Planned | P1 |
| R7 | 设置页新增「测试连接」按钮 | vue_ui / app_api / settings | v0.13.1 | ⬜ Planned | P1 |
| R8 | 集成测试 + 回归验证 | tests | v0.13.1 | ⬜ Planned | P0 |

---

## 4. 各任务详细定义

### R1：消除 Step 1「分析素材」静默失败

**目标：**
用户在无项目状态下点击「分析素材」时，必须看到明确错误提示（Toast + 行内引导），引导先创建/打开项目；消灭 POST 400 无 UI 反馈的静默失败反模式（来源：NEW-1 / RT-3）。

**涉及文件：**

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `apps/desktop/ui-vue/src/components/workflow/Step1Materials.vue` | Modify | 捕获 API 错误响应，触发 Toast + 行内提示 |
| `apps/desktop/ui-vue/src/stores/toast.js` | Read | 确认 Toast store API（`addToast` / `showError`） |
| `apps/desktop/ui-vue/src/composables/useApi.js` | Read | 确认错误处理约定，是否已有全局 error interceptor |
| `apps/desktop/ui-vue/src/components/common/ToastContainer.vue` | Read | 确认 Toast 组件可用性 |

**输入：**
- `POST /api/run_step` 返回 400 + `{"error": "项目未加载"}`

**输出：**
- Toast 提示：「请先创建或打开一个项目，然后再开始分析素材」（含「创建项目」跳转按钮）
- 按钮在请求期间进入 loading 状态，请求结束后恢复
- 控制台无未捕获错误

**验收标准：**
- [ ] 无项目状态下点击「分析素材」→ Toast 在 1s 内出现，文案正确
- [ ] Toast 含「创建项目」操作按钮，点击后跳转到项目创建流程
- [ ] 按钮点击期间显示 loading 状态（spinner 或禁用）
- [ ] 请求失败后按钮恢复可点击
- [ ] 有项目时点击「分析素材」正常发起请求，无多余 Toast

**依赖项：** 无

**已知约束：**
- 不改变后端 API 行为（`/api/run_step` 400 响应保持不变）
- Toast store 和组件为现有实现，不引入新 UI 库

---

### R2：修复前后端项目状态脱节

**目标：**
前端标题栏显示的项目名称必须与后端 `/api/status` 的 `ready` 状态一致；后端 `ready: false` 时清除 localStorage 缓存中的项目名，并引导用户重新打开项目（来源：NEW-2 / RT-1-B）。

**涉及文件：**

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `apps/desktop/ui-vue/src/stores/app.js` | Modify | 启动时检查 `/api/status`；`ready: false` 时清除 `projectName` 本地缓存 |
| `apps/desktop/ui-vue/src/stores/project.js` | Modify | 新增 `syncProjectState()` 方法，协调前后端项目名 |
| `apps/desktop/ui-vue/src/views/StartupView.vue` | Read | 确认 bootstrap 序列调用位置 |
| `apps/desktop/ui-vue/src/components/common/ProjectTitle.vue` | Modify | 仅在 `store.ready === true` 时显示项目名；否则显示「未打开项目」 |
| `apps/desktop/ui-vue/src/composables/useApi.js` | Read | 确认 `/api/status` 请求封装 |

**输入：**
- `GET /api/status` 响应：`{ "ready": true/false, "project_name": str | null }`

**输出：**
- `ready: false` → `ProjectTitle` 显示「未打开项目」，localStorage `projectName` 被清除
- `ready: true` → `ProjectTitle` 显示后端返回的 `project_name`（后端为权威，覆盖本地缓存）
- 状态变化在 bootstrap 序列（6 步）完成后立即生效

**验收标准：**
- [ ] 空后端状态（`ready: false`）下刷新页面 → 标题栏不显示旧项目名
- [ ] 本地 localStorage 有旧项目名，后端 `ready: false` → 启动后 localStorage 被清除
- [ ] 后端加载项目后（`ready: true`）→ 标题栏显示后端项目名
- [ ] `GET /api/status` 请求失败（网络异常）→ 标题栏显示「未知状态」，不崩溃

**依赖项：** 无

**已知约束：**
- 以后端 `/api/status` 为唯一权威来源；不改变该接口的响应结构

---

### R3：能力工具状态准确标注

**目标：**
区分「功能代码存在（工具已安装）」和「当前可执行（依赖满足）」两种状态。需要项目数据的工具在无项目时显示「需先打开项目」而非「可用」，消灭误导性状态标识（来源：NEW-3 / RT-6-A）。

**涉及文件：**

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `apps/desktop/ui-vue/src/components/capabilities/CapabilityLayout.vue` | Modify | 新增工具可执行性判断，展示细分状态 badge |
| `apps/desktop/ui-vue/src/stores/capabilities.js` | Modify | 新增 `requiresProject` / `requiresAI` 元数据字段；结合 `app.ready` 计算 `executable` |
| `apps/desktop/ui-vue/src/stores/app.js` | Read | 获取 `ready` + `aiConfigured` 状态 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | Modify | 新增「需先打开项目」「AI 未配置」等状态文案 |
| `modules/app_api/routes/agent_capability_routes.py` | Read | 确认 `/api/capabilities` 返回结构 |

**输入：**
- `/api/capabilities` 列表
- `app.ready`（来自 R2）
- `settings.aiConfigured`

**输出：**

| 状态 | 条件 | Badge 文案 | 颜色 |
|------|------|-----------|------|
| 可用 | `available && executable` | 可用 | 绿色 |
| 需先打开项目 | `available && requiresProject && !ready` | 需先打开项目 | 黄色 |
| AI 未配置 | `available && requiresAI && !aiConfigured` | AI 未配置 | 橙色 |
| 不可用 | `!available` | 不可用 | 灰色 |

需标注 `requiresProject: true` 的工具（9 个）：选题库、选题文案、公众号扩写、文字粗剪、短视频快剪、视频精剪、发布文案、社媒导出、内容发布

**验收标准：**
- [ ] 无项目状态下，需要项目的工具显示黄色「需先打开项目」badge
- [ ] AI 未配置时，依赖 AI 的工具显示橙色「AI 未配置」badge
- [ ] 点击「需先打开项目」工具 → 显示引导提示，不显示红色错误横幅
- [ ] 项目已加载时，可执行工具显示绿色「可用」badge
- [ ] 不改变 `/api/capabilities` 后端接口结构
- [ ] 新增文案通过 `labels.js` i18n 系统消费，不硬编码在组件中

**依赖项：** R2（`app.ready` 状态需先可靠）

**已知约束：**
- `requiresProject` / `requiresAI` 元数据在前端 capabilities store 维护，不修改后端 registry
- R3 仅读取 `app.js`（获取 `ready` + `aiConfigured` 状态），不向该文件写入；若 `aiConfigured` 状态尚未在 `app.js` 中暴露，则需在 R2 完成后确认字段可用再开始 R3，避免对同一文件的并发修改

---

### R4：Step 1 新增素材选择 UI

**目标：**
工作流 Step 1 当前只有一句说明文字和「分析素材」按钮，整个工作区空白。需新增素材来源选择 UI，让用户知道从哪里选素材、当前库有多少素材，无素材时给出明确引导（来源：P0-1 主报告）。

**涉及文件：**

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `apps/desktop/ui-vue/src/components/workflow/Step1Materials.vue` | Modify（重点） | 新增素材来源面板、库摘要卡片、空态引导、loading skeleton |
| `apps/desktop/ui-vue/src/stores/library.js` | Read | 获取 `stats.total_assets`、资产列表 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | Modify | 新增 Step 1 UI 文案 |
| `apps/desktop/ui-vue/src/composables/useApi.js` | Read | 确认 `GET /api/library/stats` 封装 |

**输入：**
- `GET /api/library/stats` 响应：`{ "total_assets": N, ... }`

**输出（三状态 UI）：**

1. **无素材**（`total_assets === 0`）：空态卡片「素材库为空」+ 主操作「去导入素材」→ `/library`
2. **有素材**（`total_assets > 0`）：素材库摘要卡片（素材数 + 最多 6 张缩略图）+ 「使用全部素材」/「手动选择（即将推出）」
3. **加载中**：skeleton 占位

**验收标准：**
- [ ] `total_assets === 0` → 显示空态卡片 + 「去导入素材」按钮
- [ ] `total_assets > 0` → 显示素材摘要卡片 + 正确素材数量
- [ ] 点击「使用全部素材」→ 「分析素材」按钮激活（由禁用变为可点击）
- [ ] 页面加载时显示 skeleton，API 返回后替换
- [ ] Step 1 界面视觉风格与现有工作流一致（复用现有组件，无新样式引入）
- [ ] 「去导入素材」使用 Vue Router 跳转，不强制刷新页面

**依赖项：** R1 必须先提交 — R1 和 R4 均修改 `Step1Materials.vue`，需严格按 R1 → R4 顺序提交以避免合并冲突；非功能性阻断，但文件级并发修改会导致覆盖

**已知约束：**
- 「手动选择」仅做占位（按钮存在，标注「即将推出」），完整实现留 v0.13.0
- 不重构素材库页面

---

### R5：素材导入进度反馈

**目标：**
用户点击「开始入库」后，必须看到实时进度（当前文件名 + 已处理/总数 + 百分比），消灭导入过程中的黑盒体验（来源：P1-3 主报告）。

**涉及文件：**

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `apps/desktop/ui-vue/src/components/library/IngestPanel.vue` | Modify | 点击「开始入库」后启动轮询 `GET /api/library/ingest/progress` |
| `apps/desktop/ui-vue/src/components/library/IngestProgress.vue` | Modify | 接收 `progress` prop，展示文件名 + 进度条 + 百分比 |
| `apps/desktop/ui-vue/src/composables/useJobPoller.js` | Read | 确认现有轮询 composable 是否可复用 |
| `apps/desktop/ui-vue/src/stores/library.js` | Modify | 新增 `ingestProgress` state + action |
| `modules/app_api/routes/library_routes.py` | Read/Modify | 确认 `/api/library/ingest/progress` 是否存在；不存在则补充 |

**输入：**
- `GET /api/library/ingest/progress` 响应：`{ "processed": N, "total": M, "current_file": str, "percent": float }`

**输出：**
- 导入期间：「正在处理：IMG_1307.MOV（3/150，2%）」
- 导入完成：Toast「入库完成：150 个素材」+ 自动跳转素材浏览
- 导入失败：明确错误提示 + 已成功数量

**验收标准：**
- [ ] 点击「开始入库」后 2s 内出现进度 UI
- [ ] 进度显示当前处理文件名
- [ ] 进度百分比实时更新（轮询间隔 ≤ 2s）
- [ ] 导入完成后 Toast 显示成功素材数量
- [ ] 导入中途失败：已成功数量和错误原因均可见

**依赖项：** 无 R-task 间依赖。`/api/library/ingest/progress` 端点是否已存在为实施前需确认的技术前提（见已知约束）

**已知约束：**
- 采用轮询方案，不引入 WebSocket
- 复用现有 `useJobPoller` composable 逻辑

---

### R6：工作流步骤命名去技术化

**目标：**
将 7 步工作流步骤标签从技术术语改为创作者直觉语言，降低新用户认知门槛（来源：P1-1 主报告；RT-7-A 证实 10 步模板命名更优）。

**涉及文件：**

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `apps/desktop/ui-vue/src/i18n/labels.js` | Modify | 修改 `workflow.steps` 下的步骤标签文案 |
| `apps/desktop/ui-vue/src/components/workflow/WorkflowStepper.vue` | Read | 确认步骤标签数据来源（应引用 labels.js，不硬编码） |

**输入：**
- `labels.js` 中 `workflow.steps` 的当前键值对

**输出（新命名方案）：**

| 步骤 | 旧命名 | 新命名 | 副标题（可选） |
|------|--------|--------|-------------|
| Step 1 | 材料分析 | 挑选素材 | 告诉我你拍了什么 |
| Step 2 | 主题规划 | 找选题 | 这条视频讲什么故事 |
| Step 3 | 脚本生成 | 写脚本 | AI 帮你写初稿 |
| Step 4 | 素材匹配 | 配素材 | 把故事和画面对上 |
| Step 5 | 帧预览 | 看效果 | 先看看大致感觉 |
| Step 6 | 粗剪 | 粗剪 | 拼出第一版视频 |
| Step 7 | 精渲染 | 导出 | 生成成品视频 |

**验收标准：**
- [ ] WorkflowStepper 7 个步骤显示新命名
- [ ] 路由逻辑不受影响（step 参数为数字，不依赖步骤名称字符串）
- [ ] `grep -rE "材料分析|帧预览|精渲染" apps/desktop/ui-vue/src/` 返回零匹配
- [ ] 回归：7 步工作流完整走通，无渲染错误
- [ ] DaVinci 降级提示文案同步改写（「仍可生成交接文件」→「没有剪辑软件，将使用内置渲染器输出」）

**依赖项：** 无

**已知约束：**
- 仅修改 `labels.js`，不修改路由或后端 step 标识符
- 副标题为可选实现；如 WorkflowStepper 不支持副标题字段则跳过

---

### R7：设置页新增「测试连接」按钮

**目标：**
用户配置 API Key 后，可立即验证 Key 是否有效，无需运行完整工作流才能发现配置错误（来源：NEW-5 / RT-5-B）。

**涉及文件：**

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `apps/desktop/ui-vue/src/views/SettingsView.vue` | Modify | 每个 API Key 输入框旁新增「测试连接」按钮 |
| `apps/desktop/ui-vue/src/stores/settings.js` | Modify | 新增 `testConnection(provider)` action |
| `modules/app_api/routes/settings_routes.py` | Modify | 新增 `POST /api/settings/ai/test` 端点 |
| `modules/app_api/services/settings_service.py` | Modify | 新增 `test_api_connection(provider, key)` 方法 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | Modify | 新增「测试连接」「连接成功」「连接失败」文案 |
| `tests/test_settings.py` | Create | 新增 `/api/settings/ai/test` 端点测试 |

**输入：**
- `POST /api/settings/ai/test` 请求体：`{ "provider": "openai" | "anthropic" | "moonshot" | "qwen" | "gemini" | "minimax" }`
- Key 从 macOS Keychain 读取（不经前端传输）

**输出：**
```
Response 200（成功）: { "success": true, "latency_ms": 234, "model_tested": "gpt-4o-mini" }
Response 200（失败）: { "success": false, "error": "Invalid API key" }
```
- 前端：成功 → 绿色「✓ 连接成功（234ms）」badge；失败 → 红色「✗ 连接失败：Invalid API key」badge

**验收标准：**
- [ ] 每个已填写的 API Key 旁有「测试连接」按钮
- [ ] 未填写 Key 时按钮置灰不可点击
- [ ] 点击后按钮进入 loading 状态（防止重复点击）
- [ ] 有效 Key → 绿色成功 badge + 延迟时间显示
- [ ] 无效 Key → 红色失败 badge + 具体错误原因
- [ ] `POST /api/settings/ai/test` 返回 200，用 `success` 字段区分成功/失败
- [ ] 测试请求不影响现有 Key 存储状态（只读取，不修改 Keychain）

**依赖项：** 无

**已知约束：**
- 测试请求会产生微量 API 费用，属正常使用，无需特殊处理
- Key 从 macOS Keychain 读取，不经前端明文传输

---

### R8：集成测试 + 回归验证

**目标：**
确认 R1–R7 全部修复有效，核心用户路径端到端可走通，无回归。

**涉及文件：**

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `tests/test_r1_fixes.py` | Read | 参考既有修复测试结构 |
| `tests/test_capabilities.py` | Modify | 新增 R3 能力状态测试用例 |
| `tests/test_settings.py` | Create | 新增 R7 API 端点测试（文件当前不存在） |
| `tests/test_library_ingest.py` | Create | 新增 R5 进度接口测试（文件当前不存在） |
| `docs/audit/2026-03-25-v0.13.1-audit.md` | Create | 最终审计记录 |

**输入：**
- R1–R7 全部完成后的代码库状态

**输出：**

| 场景 | 覆盖 R | 验证方式 |
|------|--------|---------|
| 无项目 + 点击「分析素材」→ Toast 出现 | R1 | 前端集成测试 |
| 后端 ready:false + 刷新 → 标题栏清空 | R2 | API mock + 前端状态验证 |
| 无项目 + 工具点击 → 引导提示而非错误 | R3 | 前端组件测试 |
| Step 1 显示素材库摘要卡片 | R4 | 快照测试 |
| 导入进度接口返回数据，前端 2s 内更新进度条 | R5 | 后端单元测试 + mock |
| API Key 有效 → 测试连接成功 | R7 | 后端单元测试 + mock |
| WorkflowStepper 显示新步骤名称 | R6 | labels.js 文案断言 |

**验收标准：**
- [ ] `python -m pytest tests/ -x -q` 全量通过（允许 skip，不允许 fail）
- [ ] `scripts/ci_verify.sh` 通过
- [ ] Flask headless 模式启动正常（port 9527，`GET /api/system/preflight` 返回 200）
- [ ] 实测核心路径：无项目 → 点击「分析素材」→ Toast 出现 → 点击「创建项目」→ 进入项目创建流程
- [ ] 审计文档记录所有 R-task 验收结果
- [ ] `project/VERSION` 更新为 `0.13.1`
- [ ] `project/CHANGELOG.md` 新增 v0.13.1 条目

**依赖项：** R1–R7 全部完成

**已知约束：**
- 前端组件测试如无 Vitest 环境，使用 playwright e2e 补充
- 不因测试基础设施问题阻塞发布

---

## 5. 完成状态追踪

| 任务 | 计划周期 | 实际完成日期 | 迭代次数 | 备注 |
|------|---------|------------|--------|------|
| R1 | 0.5 天 | — | 0 | 未开始 |
| R2 | 0.5 天 | — | 0 | 未开始 |
| R3 | 1 天 | — | 0 | 未开始；依赖 R2 |
| R4 | 1.5 天 | — | 0 | 未开始；依赖 R1 |
| R5 | 1 天 | — | 0 | 未开始；需确认后端 progress 端点 |
| R6 | 0.5 天 | — | 0 | 未开始 |
| R7 | 1 天 | — | 0 | 未开始；前后端均需改动 |
| R8 | 0.5 天 | — | 0 | 未开始；依赖 R1–R7 |

---

## 6. 变更记录

| 版本 | 日期 | 变更内容 | 原因 | 责任人 |
|-----|------|--------|------|------|
| V1.0 | 2026-03-25 | 初版发布，定义 R1–R8 | UX 实测报告（2026-03-25）触发 | Claude Code |
| V1.1 | 2026-03-25 | 修复 9 处审查问题：标题格式、R3/R4 依赖描述、R5 依赖表述、R6 grep 语法（macOS）、R7 test 文件操作类型、R8 缺少 R5 场景、§8 缺少 Step1Materials 冲突风险 | 代码审查（superpowers:code-reviewer）发现 | Claude Code |

---

## 7. 决策和假设

- **决策**：v0.13.1 作为独立 PATCH 版本发布，不合并入 v0.13.0 开发线。理由：P0 Bug 修复不应等待 v0.13.0 的大型功能（MCP、时间线编辑器）完成。
- **决策**：R3 的 `requiresProject` 元数据在前端 store 维护，不修改后端 capability registry API。理由：后端改动影响面大，前端 store 改动可随时回滚。
- **决策**：R7 的 `POST /api/settings/ai/test` 成功/失败均返回 HTTP 200，用 `success` 字段区分。理由：业务层失败（Key 无效）不是 HTTP 层错误，避免前端对 4xx 做特殊处理。
- **假设**：`/api/library/ingest/progress` 端点已存在或可低成本补充（R5 前提）。
- **假设**：WorkflowStepper 步骤标签通过 `labels.js` 读取，无硬编码（R6 前提）；如发现硬编码，R6 需额外重构。
- **假设**：现有 Toast store（`toast.js`）可直接复用，无需引入新通知库（R1 前提）。

---

## 8. 风险和缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|------|------|--------|
| WorkflowStepper 步骤名硬编码，R6 工作量扩大 | 中 | 中 | 实施前先 grep 全仓库确认数据来源；若硬编码则先重构再改名 |
| `/api/library/ingest/progress` 端点不存在，R5 需新增后端接口 | 中 | 中 | R5 开始前先 grep `library_routes.py`；如需新增，额外半天工作量 |
| R3 能力状态元数据维护成本高（14 个工具逐个标注） | 低 | 低 | 初版只标注明确需要项目的 9 个工具；剩余 5 个标注「可用」不改动 |
| macOS Keychain 在测试环境中不可用，R7 后端测试需 mock | 高 | 低 | R7 测试用 mock keychain，与 `test_r2_security_fix.py` 中的 mock 模式一致 |
| 多个 R-task 修改 `labels.js`（R3/R4/R6/R7），产生合并冲突 | 低 | 低 | 按 R3 → R6 → R4 → R7 顺序执行；每个 R 完成后立即提交 |
| R1 和 R4 同时修改 `Step1Materials.vue`，冲突概率高于 `labels.js` | 高 | 高 | 严格按 R1 → R4 顺序提交；R1 commit 合并后再开始 R4 开发 |

---

*开发计划：v0.13.1 / 2026-03-25*
*责任分支：`fix/ux-p0-runtime-failures`（基于 `claude/reverent-curran`）*
*关联报告：`docs/ux-audit/UX_TEST_REPORT_20260325_Creator_Simulation.md` + `UX_TEST_ADDENDUM_20260325_Runtime.md`*
