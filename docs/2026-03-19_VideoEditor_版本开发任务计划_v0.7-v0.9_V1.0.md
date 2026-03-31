# VideoEditor 版本开发任务计划（v0.7.0 — v0.9.0）

**文档类型：** 版本开发任务计划
**覆盖范围：** v0.7.0 / v0.8.0 / v0.9.0 三个版本
**当前版本：** v0.6.0
**基线日期：** 2026-03-19
**审计依据：** `2026-03-19_VideoEditor_全面审计报告_V1.0.md`
**文档版本：** V1.0

---

## 1. 开发管理（总原则）

1. **不推倒重写**——所有改动基于现有架构增量迭代
2. **继承已有能力**——以下已有基础设施必须复用，不得重建：
   - `modules/app_api/server.py` — Flask app factory + Blueprint 注册
   - `modules/app_api/routes/*.py` — 23 个 Blueprint 路由模块
   - `modules/app_api/services/job_runtime.py` — 异步任务调度
   - `modules/app_api/services/idempotency_store.py` — 幂等缓存
   - `modules/app_api/param_utils.py` — 参数解析工具（parse_int_param / parse_float_param / parse_str_param / write_json_result）
   - `modules/app_api/audit_log.py` — 审计日志
   - `modules/app_api/secure_store.py` — macOS Keychain 安全存储
   - `modules/app_api/migrations.py` — SQLite schema migration runner
   - `modules/capabilities/registry.py` — 能力注册表（CapabilitySpec + status 字段）
   - `modules/capabilities/content_publish.py` — 939 行，含 YouTube API / Webhook / Blog 三种 connector
   - `modules/capabilities/social_export.py` — 644 行，含 14 个平台导出 profile
   - `modules/capabilities/publish_prep.py` — 608 行，含 10+ 平台文案模板
   - `apps/desktop/ui-vue/` — Vue 3 + Pinia + Vite 前端（14 views, 12 capability panels, 14 Pinia stores）
   - `apps/desktop/ui-vue/src/composables/useJobPoller.js` — Job 轮询
   - `apps/desktop/ui-vue/src/components/onboarding/OnboardingModal.vue` — 引导弹窗
   - `apps/desktop/ui-vue/src/i18n/labels.js` — 统一文案管理
3. **最小改动**——每个任务只修改与任务直接相关的文件
4. **每次只能领取一个任务**——完成汇报确认后再领下一个
5. **不弱化已有功能**——任何改动不得删除、隐藏或降级已有可用能力；若需修改已有接口，必须向后兼容

---

## 2. 当前阶段事实

### 项目目标（一句话）

AI 驱动的本地桌面短视频内容生产套件，支持素材语义分析、模块化创作、多平台发布。

### 当前基线

- **Commit:** `9aa11ec` (refactor(L1-3): extract settings_helpers.py from server.py)
- **分支:** `main`
- **版本:** v0.6.0
- **测试基线:** 173/173 通过，0 warnings

### 当前已完成能力清单

**安全层：**
- CSRF + Origin 校验（Flask before_request）
- 本地 API Token 握手（/api/session/bootstrap）
- macOS Keychain API Key 存储（secure_store.py）
- 请求大小限制（MAX_CONTENT_LENGTH 25MB）
- 参数校验统一（13 个路由文件 134 处 parse_str_param + 65 处 parse_int/float_param）
- 审计日志（audit_log.py — 发布/删除/设置变更等敏感操作）

**产品能力层（12 个能力模块）：**
- topic_library — 选题模板 CRUD + SQLite 持久化（status: prototype）
- topic_copy — AI 文案生成 + 模板 fallback（status: prototype）
- text_rough_cut — 字幕粗剪（status: prototype）
- short_clip — 亮点提取（status: prototype）
- refinement — NLE 交接（FCP/Premiere/Resolve/剪映）（status: prototype）
- social_export — 14 个平台导出 profile + FFmpeg 转码（status: prototype）
- publish_prep — 10+ 平台文案生成（status: prototype）
- subtitle_calibration — 字幕校准（status: prototype）
- image_semantic — 图像语义分析（status: prototype）
- article_expand — 公众号扩写（status: prototype）
- audio_voice — TTS + BGM + 混音（ElevenLabs 集成）（status: prototype）
- content_publish — 多平台发布引擎（Blog 真实 / YouTube API 骨架 / Webhook 通用）（status: prototype）

**基础设施层：**
- Flask Blueprint 路由拆分（23 个路由文件）
- server.py L1 拆分（已提取 agent_governance.py / custom_workflow_helpers.py / settings_helpers.py）
- 异步任务队列 + SQLite 持久化（job_runtime.py + job_store.py）
- 幂等缓存（idempotency_store.py）
- SQLite migration runner（migrations.py）
- print→logging 全量迁移（14 个生产模块 159 处）
- subprocess 超时 + cv2 资源泄漏防护

**前端层：**
- Vue 3 + Pinia + Vite 前端重写完成（v0.4.0-v0.5.0）
- 14 个 View 页面（Startup/Library/Production/Settings 等）
- 12 个能力面板 Vue 组件
- OnboardingModal 引导弹窗（3 步）
- Toast 通知系统
- AI 降级通知（degraded flag 前端消费，项目步骤 + 图像语义）
- recovery_hint 部分消费（Vue workflow store）
- i18n/labels.js 文案管理
- 能力导航 maturity badge（stable/prototype/planned）

**测试层：**
- 43+ 测试文件，173 测试通过
- conftest.py 共享 fixture（Flask test client + 临时目录 + 模拟 Library）
- 能力模块单元测试 + Agent API 集成测试 + 回归测试
- AST 静态检查（print 零残留 / json.dumps 零残留）

### 当前未完成的任务列表（本计划要解决的）

| 编号 | 问题 | 来源 | 优先级 |
|---|---|---|---|
| G-01 | 发布面板暴露 input_mode / dry-run / session_id 等开发者术语 | 审计 P0-2 | P0 |
| G-02 | 平台选择是文本输入，非 checkbox/picker | 审计 P2-1 | P1 |
| G-03 | 发布/导出结果是 raw JSON 展示（`JSON.stringify`） | 审计 P1-2 | P1 |
| G-04 | 发布面板无错误恢复引导（recovery_hint 未消费） | 审计 P1-2 + roadmap S2 | P1 |
| G-05 | 项目名不可读（`proj_selected_20260312_193013`） | 审计 P2-3 | P2 |
| G-06 | 引导流程过于简单（3 个通用步骤，无素材导入引导） | 审计 P1-1 | P1 |
| G-07 | YouTube OAuth 需用户手动粘贴 token | 审计 P0-1 + roadmap M1 | P0 |
| G-08 | 不可用平台未在 UI 标识 | 审计 P0-1 | P0 |
| G-09 | 发布历史无结构化展示 | roadmap M2 | P2 |
| G-10 | server.py 仍 5,997 行 | 审计 + roadmap L1 | P2 |
| G-11 | 无前端 E2E 测试 | 审计 | P2 |
| G-12 | 无 OpenAPI 文档 | 审计 | P3 |
| G-13 | 队列恢复无 UI 批量重试入口 | next_dev_plan Phase 1.3 | P2 |
| G-14 | 社媒导出面板平台文本输入 + raw JSON 展示 | 审计 P2-1 | P1 |
| G-15 | 能力面板表单缺少默认值和提示文案 | 审计 P2-5 | P2 |

---

## 3. 版本规划总览

| 版本 | 主题 | 任务数 | 核心目标 |
|---|---|---|---|
| **v0.7.0** | UX 体验修复与术语人性化 | 6 个任务 | 消除 P0/P1 级 UX 阻断，让目标用户能走通核心路径 |
| **v0.8.0** | 发布链路完善与平台集成 | 5 个任务 | YouTube OAuth 闭环 + 发布历史 + 队列恢复 + 平台就绪标识 |
| **v0.9.0** | 工程治理与可维护性 | 4 个任务 | server.py 继续拆分 + 前端 E2E 测试 + OpenAPI 文档 + 安全审计补全 |

---

# v0.7.0 — UX 体验修复与术语人性化

## 3.1 本轮目标与边界

### 只做什么

| 任务编号 | 任务名 |
|---|---|
| T-0701 | 发布面板（ContentPublish.vue）术语人性化 + 平台 checkbox picker |
| T-0702 | 导出面板（SocialExport.vue）平台 picker + 结果结构化展示 |
| T-0703 | 发布面板错误恢复引导（recovery_hint 消费） |
| T-0704 | 项目名可读化 + 重命名能力 |
| T-0705 | 引导流程增强（引导素材导入 + 首次创作） |
| T-0706 | 能力面板表单默认值 + 占位符文案优化（全 12 个面板） |

### 明确不做什么

- 不修改任何后端 API 签名或返回结构
- 不修改 content_publish.py / social_export.py / publish_prep.py 的业务逻辑
- 不新增后端路由（除 T-0704 项目重命名需要 1 个端点外）
- 不迁移 Alpine.js legacy UI（保留现有回退机制）
- 不做 Vue 3 组件库抽象 / 设计系统重构
- 不做多语言 i18n（保持中文为主，英文标签维持现状）
- 不修改 registry.py 的 CapabilitySpec 结构
- 不修改 7 步工作流的状态机逻辑

## 4.1 优先级与顺序（v0.7.0）

| 顺序 | 任务 | 理由 | 依赖 |
|---|---|---|---|
| 1 | T-0701 | P0 级：发布面板是审计最严重的 UX 问题，术语暴露直接阻断用户 | 无 |
| 2 | T-0702 | P1 级：导出面板与发布面板问题类似，改动模式相同可复用 | 无（可与 T-0701 并行） |
| 3 | T-0703 | P1 级：发布失败后用户无下一步引导，依赖 T-0701 的面板改造 | T-0701 |
| 4 | T-0704 | P2 级：项目名可读化是独立模块，不影响其他任务 | 无 |
| 5 | T-0705 | P1 级：引导流程需要在 T-0704 之后（引导中要展示项目名） | T-0704 |
| 6 | T-0706 | P2 级：全面板文案优化是收尾任务，需要前面改动稳定后再统一调整 | T-0701, T-0702 |

## 5.1 各任务详细定义（v0.7.0）

---

### T-0701：发布面板术语人性化 + 平台 checkbox picker

**目标：** 消除 ContentPublish.vue 中暴露的开发者术语，将平台选择从文本输入改为 checkbox 选择器，让非技术用户能正确使用发布功能。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `apps/desktop/ui-vue/src/components/capabilities/ContentPublish.vue` | 修改 | 重写表单 UI + 结果展示 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 新增 content_publish 相关中文标签 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 无新增。复用现有 API：
- `GET /api/capabilities/content_publish/platforms` — 获取平台列表（已有，返回 `platforms` 数组）
- `POST /api/capabilities/content_publish/session/bootstrap` — 初始化会话（已有）
- `POST /api/capabilities/content_publish/plan` — 生成计划（已有）
- `POST /api/capabilities/content_publish/run` — 执行发布（已有）

**业务规则：**

1. **平台列表加载：** 组件 `onMounted` 时调用 `GET /api/capabilities/content_publish/platforms`，获取完整平台列表（含 `platform_id`, `name`, `region`, `supports_video`, `supports_article`）
2. **平台 checkbox 渲染：**
   - 按 `region` 分组展示：国内平台（domestic）/ 国际平台（global）/ 自定义（custom）
   - 每个平台显示 `name`（非 `platform_id`）
   - checkbox 勾选后写入 reactive 数组 `selectedPlatforms`
   - 提交时自动将数组转为逗号分隔字符串（兼容已有 API 入参格式 `platforms: "youtube,douyin"`）
3. **术语隐藏规则：**
   - `input_mode` 选择器：**移除**。默认值逻辑：如果 `appStore.projectDir` 存在则自动设为 `"project"`，否则设为 `"inline"`。用户无需感知
   - `dry_run` checkbox：**移到"高级选项"折叠区**，标签改为"仅预览计划（不实际发布）"
   - `session_id` 输入框：**移除**。由 bootstrap 自动管理，不暴露给用户
   - `connectors_json` 输入框：**移除**。connector 配置走设置页面
   - `article_markdown` / `article_html`：仅在 `platform_content_type === 'article'` 时显示
4. **结果展示改造：**
   - 发布计划：不再用 `JSON.stringify`，改为结构化列表：每个平台一行，展示平台名称 + 状态（planned / blocked）+ 原因
   - 执行结果：每个平台一行，展示状态图标（✅ posted / ❌ failed / ⏳ planned）+ 错误摘要
   - 如果 `step.state === 'blocked'`，显示原因文案（如"未配置连接器"）并附带"前往设置"链接
5. **会话初始化自动化：**
   - 首次打开面板时自动 bootstrap（不需要用户手动点击"初始化会话"）
   - bootstrap 失败时 Toast 提示"发布服务初始化失败，请检查网络后重试"
   - 已有 session 未过期时跳过 bootstrap

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `ContentPublish.vue` | 重写 `<template>` 部分：移除 input_mode / session_id / connectors_json 表单行；平台文本输入替换为 checkbox 分组；dry_run 移入高级折叠；结果区从 `<pre>` 改为结构化列表 |
| `labels.js` | 新增 `contentPublish` 子对象：包含平台分组标题、状态文案、错误文案 |

**不做什么：**
- 不修改 content_publish.py 后端逻辑
- 不修改 API 入参/出参格式
- 不实现 OAuth 流程（v0.8.0 任务）
- 不修改 SocialExport.vue（T-0702 任务）
- 不修改设置页面的 connector 配置

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 打开内容发布面板 | 有项目目录 | 自动 bootstrap，平台以 checkbox 分组展示，无 input_mode / session_id 字段 |
| AC-02 | 勾选 2 个平台 + 点击"生成发布计划" | 勾选 blog + youtube | 计划结果以结构化列表展示：blog=planned, youtube=blocked(原因：未配置连接器) |
| AC-03 | 展开高级选项 | 勾选"仅预览计划" | dry_run=true 传给 API，计划不执行 |
| AC-04 | 发布面板无项目目录 | projectDir 为空 | input_mode 自动为 inline，"标题"等字段直接可填写 |
| AC-05 | 执行发布后查看结果 | 发布到 blog | 结果列表展示 blog ✅ posted，无 raw JSON |
| AC-06 | 回归：已有 API 调用正常 | 所有现有测试 | 173/173 通过 |

---

### T-0702：导出面板平台 picker + 结果结构化展示

**目标：** 将 SocialExport.vue 的平台选择从文本输入改为 profile 卡片点击选择器，导出结果从 raw JSON 改为结构化展示。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `apps/desktop/ui-vue/src/components/capabilities/SocialExport.vue` | 修改 | 平台选择改为 profile 卡片多选 + 结果结构化 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 新增 socialExport 相关文案 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 无新增。复用现有 API：
- `GET /api/capabilities/social_export/profiles` — 获取平台 profile 列表（已有，返回 14 个平台规格）

**业务规则：**

1. **平台选择改造：**
   - 现有 `profile-grid` 已展示平台卡片（可点击），但点击只是追加到文本输入
   - 改造为：每个 profile 卡片可 toggle 选中/取消，选中态加蓝色边框 + 勾选图标
   - 移除文本输入 `<input v-model="input.platforms">`，改为用 `selectedPlatforms: Set<string>` 管理
   - 提交时从 Set 转换为逗号分隔字符串（兼容 API）
2. **profile 卡片增强：**
   - 现有展示：平台名 + 分辨率 + fps
   - 增加展示：最大时长（如"≤ 60s"）、比例方向图标（竖屏 📱 / 横屏 🖥）
3. **导出计划结构化：**
   - 不再用 `<pre>JSON.stringify(exportPlan)</pre>`
   - 改为表格展示：平台名 | 分辨率 | 码率 | 预计文件大小 | 状态
4. **导出结果结构化：**
   - 不再用 `<pre>JSON.stringify(exportResult)</pre>`
   - 改为列表：平台名 | 输出路径 | 文件大小 | 状态（✅ / ❌）
   - 失败项展示错误原因
5. **历史记录表格化：**
   - 现有展示：batch_id + badge + 复跑按钮
   - 增加展示：创建时间、平台数量、成功/失败数

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `SocialExport.vue` | profile-grid 改为 toggle 多选；移除平台文本输入；plan/result 区改为表格展示 |
| `labels.js` | 新增 `socialExport` 子对象 |

**不做什么：**
- 不修改 social_export.py 后端逻辑
- 不修改导出 profile 的数据结构
- 不新增导出模板管理功能
- 不修改 FFmpeg 转码参数

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 打开社媒导出面板 | 有项目 | 14 个平台卡片展示，无文本输入 |
| AC-02 | 点击 tiktok 卡片 + youtube 卡片 | 点击两次 | 两个卡片高亮选中，提交时 platforms="tiktok,youtube" |
| AC-03 | 再次点击 tiktok 卡片 | 取消选中 | tiktok 卡片取消高亮，platforms="youtube" |
| AC-04 | 生成导出计划 | 选中 2 个平台 | 结果以表格展示（非 raw JSON） |
| AC-05 | 执行导出完成 | 导出成功 | 结果列表每平台一行，显示输出路径和文件大小 |
| AC-06 | 回归 | 所有现有测试 | 通过 |

---

### T-0703：发布面板错误恢复引导

**目标：** 当发布执行失败时，在 ContentPublish.vue 中消费后端返回的 `recovery_hint` 字段，展示结构化的错误分类和恢复操作按钮。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `apps/desktop/ui-vue/src/components/capabilities/ContentPublish.vue` | 修改 | 新增错误恢复 UI 区域 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 无新增。消费已有 API 返回中的字段：

content_publish `/run` 和 `/rerun` 响应中已包含：
```
{
  "run": {
    "steps": [
      {
        "state": "failed",
        "error_class": "auth_failed | config_missing | network_error | platform_rejected | quota_exceeded | params_invalid | unknown",
        "error_detail": "...",
        "recovery_hint": "..."
      }
    ]
  },
  "recovery_hint": {
    "rerun_scope": "failed_only | all",
    "error_classes": ["auth_failed", "config_missing"]
  }
}
```

**业务规则：**

1. **错误分类展示：** 当 `publishRun` 中存在 `state === 'failed'` 的 step 时，在结果区域上方展示错误摘要面板：
   - 按 `error_class` 分组聚合：如"2 个平台认证失败，1 个平台配置缺失"
   - 每种 `error_class` 映射到中文文案：
     - `auth_failed` → "平台授权失败或已过期"
     - `config_missing` → "连接器未配置"
     - `network_error` → "网络连接异常"
     - `platform_rejected` → "平台拒绝了发布请求"
     - `quota_exceeded` → "平台发布频率超限"
     - `params_invalid` → "发布参数不符合平台要求"
     - `unknown` → "未知错误"
2. **恢复操作按钮：** 根据 `recovery_hint.rerun_scope` 展示：
   - 如果 `rerun_scope === 'failed_only'`：展示"重试失败平台"按钮（调用 `/rerun` + `rerun_failed_only: true`）
   - 如果 `rerun_scope === 'all'`：展示"全部重新发布"按钮
   - 如果 `error_classes` 包含 `config_missing`：展示"前往设置"按钮（路由到 SettingsView）
   - 如果 `error_classes` 包含 `auth_failed`：展示"重新授权"按钮（触发 bootstrap）
3. **无 recovery_hint 时的兜底：** 如果后端未返回 recovery_hint（老数据或异常），展示通用提示"发布过程中出现问题，请检查设置后重试"+ 通用重试按钮

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `ContentPublish.vue` | 在执行结果区域上方新增 `<div class="recovery-panel">` 错误恢复面板 |

**不做什么：**
- 不修改后端的 recovery_hint 生成逻辑
- 不新增后端 API
- 不修改 error_class 枚举

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 发布到未配置平台 | 选择 youtube（无 connector） | 计划显示 blocked；执行后 error_class=config_missing，恢复面板显示"连接器未配置" + "前往设置"按钮 |
| AC-02 | 部分成功部分失败 | blog(成功) + youtube(失败) | blog ✅，youtube ❌，恢复面板显示"重试失败平台"按钮 |
| AC-03 | 点击"重试失败平台" | 点击恢复按钮 | 调用 `/rerun` + `rerun_failed_only: true`，仅重新发布失败平台 |
| AC-04 | 全部发布成功 | 仅发布 blog | 无恢复面板展示 |
| AC-05 | 后端无 recovery_hint | 模拟旧版响应 | 展示兜底提示 + 通用重试按钮 |

---

### T-0704：项目名可读化 + 重命名能力

**目标：** 让用户可以为项目设置可读的自定义名称，替代系统生成的 `proj_selected_20260312_193013` 格式。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `modules/app_api/routes/legacy_project_routes.py` | 修改 | 新增 rename 端点 |
| `apps/desktop/ui-vue/src/stores/project.js` | 修改 | 新增 projectName 状态 + rename action |
| `apps/desktop/ui-vue/src/components/layout/Titlebar.vue` 或等效布局组件 | 修改 | 展示项目名 + 编辑入口 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 新增项目名相关文案 |

**新增数据库表：** 无

**已有表变更：** 无

**数据存储：** 在项目目录的 `data/project_meta.json` 中新增字段：

```json
{
  "display_name": "加拿大旅行 Vlog",
  "created_at": "2026-03-12T19:30:13",
  "updated_at": "2026-03-19T10:00:00"
}
```

**API 定义：**

| 端点 | 方法 | 说明 | 入参 | 返回 |
|---|---|---|---|---|
| `/api/project/meta` | GET | 获取项目元数据 | query: `project_dir` (string, required) | `{ "ok": true, "meta": { "display_name": "...", "created_at": "...", "updated_at": "..." } }` |
| `/api/project/rename` | POST | 重命名项目 | body: `{ "project_dir": "...", "display_name": "..." }` | `{ "ok": true, "meta": {...} }` |

**业务规则：**

1. **读取项目名：**
   - 第 1 步：读取 `project_dir/data/project_meta.json` 的 `display_name` 字段
   - 第 2 步：如果文件不存在或 `display_name` 为空，从目录名提取可读部分：`proj_selected_20260312_193013` → 展示为 `项目 2026-03-12`（提取日期部分）
   - 第 3 步：返回 `{ "ok": true, "meta": {...} }`
2. **重命名规则：**
   - 第 1 步：校验 `display_name` 非空且长度 ≤ 100 字符
   - 第 2 步：校验 `display_name` 不包含 `/ \ : * ? " < > |` 等文件系统非法字符
   - 第 3 步：校验失败 → 返回 `{ "error": "项目名不能包含特殊字符 / \\ : * ? \" < > |" }, 400`
   - 第 4 步：写入 `project_meta.json`（使用 `write_json_result` 原子写入）
   - 第 5 步：写入审计日志 `_audit("project_rename", ...)`
   - 第 6 步：返回更新后的 meta
3. **前端展示：**
   - 标题栏展示 `display_name`（而非目录路径）
   - 目录路径降为灰色小字展示在项目名下方
   - 点击项目名弹出 inline 编辑（input + 确认/取消按钮）

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| Titlebar 区域 | 展示 display_name + 可编辑入口 |
| `project.js` store | 新增 `projectName` ref + `loadProjectMeta()` + `renameProject()` action |

**不做什么：**
- 不修改项目目录结构（只加 meta 文件，不重命名目录本身）
- 不实现项目列表收藏/排序功能
- 不修改项目创建流程（创建时仍用系统命名，用户创建后可改名）

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 打开已有项目 | 项目无 project_meta.json | 标题栏展示"项目 2026-03-12"（从目录名提取） |
| AC-02 | 重命名项目 | display_name = "加拿大 Vlog" | 标题栏更新为"加拿大 Vlog"，meta 文件已写入 |
| AC-03 | 重命名含非法字符 | display_name = "test/path" | 返回 400 + 错误提示，名称未变 |
| AC-04 | 重命名空字符串 | display_name = "" | 返回 400 + 提示"项目名不能为空" |
| AC-05 | 重新打开项目 | 之前已改名 | 标题栏仍展示"加拿大 Vlog" |
| AC-06 | 回归 | 所有现有测试 | 通过 |

---

### T-0705：引导流程增强

**目标：** 将 OnboardingModal 从 3 个通用文字步骤增强为引导用户完成"选择素材文件夹 → 导入素材 → 开始创作"的实操流程。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `apps/desktop/ui-vue/src/components/onboarding/OnboardingModal.vue` | 修改 | 增强步骤内容 + 交互 |
| `apps/desktop/ui-vue/src/stores/preferences.js` | 修改 | 新增 onboarding 阶段状态 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 更新 onboarding 文案 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 无新增。复用已有 API：
- `POST /api/dialog/folder` — 选择文件夹（已有）
- `POST /api/library/ingest/local` — 素材导入（已有）

**业务规则：**

1. **引导步骤重新定义（从通用文字改为实操）：**
   - **Step 1"欢迎"：** 展示产品简介（1 句话 + 3 个核心功能图标）+ "开始"按钮
   - **Step 2"导入素材"：** 展示"选择素材文件夹"按钮，调用 `/api/dialog/folder`；选择后预览发现的文件数量（如"发现 164 个视频 / 23 张图片"）；用户确认后触发 ingest
   - **Step 3"开始创作"：** 素材导入完成后，展示"前往素材库浏览"和"直接开始创作"两个按钮
2. **状态管理：**
   - `preferences.js` 新增 `onboarding_step: number`（0=未开始, 1=欢迎, 2=导入中, 3=完成）
   - 如果用户在 Step 2 关闭弹窗，下次打开继续 Step 2（不重新从 1 开始）
   - `onboarding_completed` 保持不变（Step 3 完成或跳过时设为 true）
3. **跳过机制保留：**
   - 每个步骤都有"跳过"按钮
   - 跳过 → 标记 `onboarding_completed = true`，不再弹出
4. **不弱化已有行为：**
   - 如果 `onboarding_completed === true`，不弹窗（维持已有逻辑）
   - 引导完成后 preferences 持久化到 settings API（维持已有逻辑）

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `OnboardingModal.vue` | 将 3 个纯文字 step 改为 3 个交互 step（含按钮调用 API） |
| `preferences.js` | 新增 `onboarding_step` 字段 |
| `labels.js` | 更新 onboarding.step1/2/3 文案 |

**不做什么：**
- 不修改素材导入 API 逻辑
- 不实现素材预览（只展示数量统计）
- 不修改项目创建流程
- 不增加 tooltip / 全局引导气泡系统

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 首次打开应用 | onboarding_completed = false | 弹出引导弹窗 Step 1 |
| AC-02 | Step 2 选择文件夹 | 选择含 10 个视频的文件夹 | 展示"发现 10 个视频"，确认后开始导入 |
| AC-03 | Step 2 关闭再打开 | 关闭弹窗 | 下次打开继续 Step 2（不回到 Step 1） |
| AC-04 | 跳过引导 | 点击"跳过" | onboarding_completed = true，弹窗关闭 |
| AC-05 | 已完成引导 | onboarding_completed = true | 不弹窗 |
| AC-06 | 回归 | 所有现有测试 | 通过 |

---

### T-0706：能力面板表单默认值 + 占位符文案优化

**目标：** 为全 12 个能力面板的表单字段补充合理的默认值、占位符文案和帮助提示，降低用户认知负担。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `apps/desktop/ui-vue/src/components/capabilities/*.vue` (12 个) | 修改 | 每个面板补充 placeholder / 默认值 / tooltip |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 新增各面板 placeholder 文案 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 无新增

**业务规则：**

逐面板具体规则：

| 面板 | 字段 | 当前问题 | 改为 |
|---|---|---|---|
| TopicLibrary | category 输入框 | 无 placeholder | placeholder="如：旅行、美食、科技" |
| TopicCopy | slug 输入框 | "slug" 标签用户不理解 | 标签改为"选题标识"，placeholder="如：snow_adventure" |
| TopicCopy | target_duration 输入框 | 无默认值 | 默认值 60，placeholder="目标时长（秒）" |
| TextRoughCut | removed_phrases 输入框 | 无提示 | placeholder="需删除的口头禅，逗号分隔，如：嗯、然后、那个" |
| TextRoughCut | target_duration_s 输入框 | 无默认值 | 默认值 15 |
| ShortClip | duration_budget 输入框 | 无默认值 | 默认值 60 |
| Refinement | editor 选择器 | 无提示 | 增加提示"选择已安装的 NLE 编辑器" |
| SubtitleCalibration | mode 选择器 | 枚举值不解释 | 每个选项加括号说明 |
| AudioVoice | provider 文本输入 | 要求输入"elevenlabs" | 改为下拉选择器（选项从 AI catalog 获取） |
| AudioVoice | voice_id 文本输入 | 无提示 | placeholder="语音 ID，如 EXAVITQu4vr4xnSDxMaL" |
| ImageSemantic | 分析选项 | 无默认值 | 默认勾选 objects + scene + mood |
| ArticleExpand | length_target 输入框 | 无默认值 | 默认值 1500，placeholder="目标字数" |

**通用规则：**
- 所有 placeholder 文案统一录入 `labels.js`，不在 `.vue` 文件中硬编码
- 不修改任何表单的提交逻辑或 API 调用方式
- 不修改字段名（只改标签显示和 placeholder）

**前端变更：** 12 个能力 Vue 组件的 `<template>` 部分

**不做什么：**
- 不修改后端 API
- 不修改表单校验逻辑
- 不新增字段
- 不改变任何已有字段的默认提交值（只是 UI 层面的 placeholder 和显示优化）

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 打开 TopicCopy 面板 | 无输入 | slug 标签显示"选题标识"，target_duration 默认 60 |
| AC-02 | 打开 AudioVoice 面板 | 无输入 | provider 为下拉选择器（非文本输入），展示可选列表 |
| AC-03 | 打开 TextRoughCut 面板 | 无输入 | removed_phrases 有 placeholder 提示 |
| AC-04 | 所有 12 个面板 | 逐个打开 | 每个面板的表单字段都有合理 placeholder 或默认值 |
| AC-05 | 回归 | 提交各面板表单 | API 调用正常，与改动前行为一致 |

---

# v0.8.0 — 发布链路完善与平台集成

## 3.2 本轮目标与边界

### 只做什么

| 任务编号 | 任务名 |
|---|---|
| T-0801 | YouTube OAuth 2.0 完整授权流 |
| T-0802 | 平台就绪状态标识（connector 配置检查 + UI 展示） |
| T-0803 | 发布历史结构化展示 |
| T-0804 | 队列恢复 UI（中断任务批量重试） |
| T-0805 | Webhook connector 配置向导 |

### 明确不做什么

- 不实现抖音/小红书/微信的原生 OAuth（这些平台 API 需要企业资质，当前通过 Webhook 连接）
- 不实现定时发布 / 内容日历
- 不实现多账号管理
- 不修改 7 步工作流逻辑
- 不修改 social_export 导出逻辑
- 不重构 content_publish.py 的 connector 架构
- 不做批量发布（一次只发一个计划）

## 4.2 优先级与顺序（v0.8.0）

| 顺序 | 任务 | 理由 | 依赖 |
|---|---|---|---|
| 1 | T-0801 | P0：YouTube 是第一个需完整 OAuth 的平台，是发布闭环的关键 | 无 |
| 2 | T-0802 | P0：标识哪些平台已配置/可用，防止用户选择不可用平台后静默失败 | T-0801（YouTube 配置完成后可验证） |
| 3 | T-0805 | P1：Webhook 是连接抖音/小红书的唯一方式，需要配置向导 | T-0802（依赖就绪标识逻辑） |
| 4 | T-0803 | P2：发布历史展示依赖已有 history API，独立可做 | 无 |
| 5 | T-0804 | P2：队列恢复 UI 独立于发布链路 | 无 |

## 5.2 各任务详细定义（v0.8.0）

---

### T-0801：YouTube OAuth 2.0 完整授权流

**目标：** 实现 YouTube OAuth 2.0 authorization code flow，用户在设置页面点击"连接 YouTube"后通过浏览器完成授权，token 自动持久化到安全存储。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `modules/app_api/routes/settings_routes.py` | 修改 | 新增 OAuth 启动 + 回调端点 |
| `modules/app_api/secure_store.py` | 修改 | 新增 YouTube token 读写方法 |
| `modules/capabilities/content_publish.py` | 修改 | YouTube connector 消费持久化 token（替代手动粘贴） |
| `apps/desktop/ui-vue/src/views/SettingsView.vue` | 修改 | 新增 YouTube 连接/断开 UI |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 新增 OAuth 相关文案 |

**新增数据库表：** 无（token 存储在 secure_store，不进数据库）

**已有表变更：** 无

**API 定义：**

| 端点 | 方法 | 说明 | 入参 | 返回 |
|---|---|---|---|---|
| `/api/settings/oauth/youtube/start` | POST | 生成 OAuth URL 并打开浏览器 | body: `{ "redirect_uri": "http://localhost:{port}/api/settings/oauth/youtube/callback" }` | `{ "ok": true, "auth_url": "https://accounts.google.com/o/oauth2/auth?..." }` |
| `/api/settings/oauth/youtube/callback` | GET | Google OAuth 回调（浏览器重定向到此） | query: `code` (string), `state` (string) | HTML 页面："授权成功，请返回应用" |
| `/api/settings/oauth/youtube/status` | GET | 检查 YouTube 授权状态 | 无 | `{ "connected": true, "channel_name": "...", "expires_at": "..." }` 或 `{ "connected": false }` |
| `/api/settings/oauth/youtube/disconnect` | POST | 断开 YouTube 授权 | 无 | `{ "ok": true }` |

**业务规则：**

1. **OAuth 启动流程：**
   - 第 1 步：前端调用 `/api/settings/oauth/youtube/start`
   - 第 2 步：后端生成 `state` 随机字符串（防 CSRF），存入内存
   - 第 3 步：后端拼接 Google OAuth URL（scope: `youtube.upload youtube.readonly`）
   - 第 4 步：后端调用 `webbrowser.open(auth_url)` 打开系统浏览器
   - 第 5 步：返回 `{ "ok": true, "auth_url": "..." }` 给前端（前端展示"等待授权…"状态）
2. **OAuth 回调处理：**
   - 第 1 步：校验 `state` 参数与内存中一致，不一致 → 返回 HTML "授权失败：无效请求"
   - 第 2 步：用 `code` 换取 `access_token` + `refresh_token`（POST `https://oauth2.googleapis.com/token`）
   - 第 3 步：exchange 失败 → 返回 HTML "授权失败：{error_description}"
   - 第 4 步：调用 YouTube API `GET /channels?part=snippet&mine=true` 获取频道名
   - 第 5 步：将 `access_token` / `refresh_token` / `channel_name` / `expires_at` 写入 secure_store（key: `youtube_oauth`）
   - 第 6 步：写入审计日志 `_audit("oauth_connect", "youtube", ...)`
   - 第 7 步：返回 HTML "授权成功！已连接频道：{channel_name}，请返回应用"
3. **Token 自动刷新：**
   - `content_publish.py` 的 YouTube connector 在发起上传前检查 `expires_at`
   - 如果距离过期 < 5 分钟，用 `refresh_token` 自动刷新
   - 刷新失败 → error_class = `auth_failed`，recovery_hint 建议重新授权
4. **断开连接：**
   - 从 secure_store 删除 `youtube_oauth`
   - 写入审计日志

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `SettingsView.vue` | 新增"平台连接"区域，YouTube 行：未连接 → "连接 YouTube"按钮；已连接 → 展示频道名 + "断开"按钮 |

**不做什么：**
- 不实现 Google Client Library（直接 HTTP 调用，保持轻量）
- 不实现 token 加密存储的 Windows/Linux 后端（沿用 secure_store 现有降级逻辑）
- 不实现其他平台的 OAuth
- 不修改 YouTube upload 的已有逻辑（upload 本身已实现）

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 点击"连接 YouTube" | 有 Google 账号 | 浏览器打开 Google 授权页，授权后回调成功，设置页显示频道名 |
| AC-02 | 授权状态检查 | 已连接 | `/api/settings/oauth/youtube/status` 返回 `connected: true` + 频道名 |
| AC-03 | 断开连接 | 点击"断开" | secure_store 删除 token，状态变为 `connected: false` |
| AC-04 | Token 过期自动刷新 | access_token 过期 | 发布时自动刷新，发布成功 |
| AC-05 | refresh_token 失效 | refresh_token 被吊销 | 发布失败，error_class=auth_failed，恢复面板提示"重新授权" |
| AC-06 | 回归 | 所有现有测试 | 通过 |

---

### T-0802：平台就绪状态标识

**目标：** 在发布面板的平台选择器中标识每个平台的就绪状态（已配置 / 未配置 / 不可用），防止用户选择不可用平台后静默失败。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `modules/app_api/routes/capability_content_publish_routes.py` | 修改 | `/platforms` 端点增加 `connector_ready` 字段 |
| `modules/capabilities/content_publish.py` | 修改 | `list_publish_platforms()` 增加 connector 就绪检查逻辑 |
| `apps/desktop/ui-vue/src/components/capabilities/ContentPublish.vue` | 修改 | 平台 checkbox 展示就绪状态 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 修改已有端点（向后兼容）：

| 端点 | 变更 | 新增返回字段 |
|---|---|---|
| `GET /api/capabilities/content_publish/platforms` | 增强 | 每个 platform 对象新增 `connector_ready: bool` + `connector_kind: "youtube_api" \| "webhook" \| "blog" \| "none"` + `setup_hint: string` |

**业务规则：**

1. **就绪检查逻辑（在 `list_publish_platforms()` 中）：**
   - `blog` → 始终 `connector_ready: true`（本地写入，无需配置）
   - `youtube` → 检查 secure_store 是否有 `youtube_oauth` 且未过期 → `connector_ready: true/false`
   - 其他平台 → 检查 `publish_connectors.json` 中是否有对应 webhook 配置 → `connector_ready: true/false`
2. **setup_hint 文案：**
   - youtube 未连接 → `"请在设置页面连接 YouTube 账号"`
   - webhook 未配置 → `"请在设置页面配置 Webhook 连接器"`
   - blog → `""`（无需配置）
3. **前端展示：**
   - `connector_ready: true` → 正常 checkbox，可勾选
   - `connector_ready: false` → checkbox 可勾选但带 ⚠️ 标记 + tooltip 展示 setup_hint
   - 用户仍可选择未就绪平台（plan 阶段会标记为 blocked，不阻止探索）

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `ContentPublish.vue` | 平台 checkbox 增加就绪标识 + tooltip |

**不做什么：**
- 不阻止用户选择未就绪平台（只做提示，不做拦截）
- 不修改 plan/run 的阻塞逻辑（已有 blocked 状态处理）

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 获取平台列表 | YouTube 已授权 | youtube: connector_ready=true, connector_kind=youtube_api |
| AC-02 | 获取平台列表 | YouTube 未授权 | youtube: connector_ready=false, setup_hint="请在设置页面连接 YouTube 账号" |
| AC-03 | 获取平台列表 | 抖音配置了 webhook | douyin: connector_ready=true, connector_kind=webhook |
| AC-04 | 前端展示 | 混合状态 | blog ✅, youtube ✅, douyin ⚠️(hover 展示提示) |
| AC-05 | 回归 | 已有 API 测试 | 返回结构向后兼容（新字段为增量，不破坏旧消费方） |

---

### T-0803：发布历史结构化展示

**目标：** 在内容发布面板中新增"发布历史"Tab，展示历史发布记录的结构化列表。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `apps/desktop/ui-vue/src/components/capabilities/ContentPublish.vue` | 修改 | 新增 history tab + 列表展示 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 新增 history 相关文案 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 无新增。复用已有 API：
- `GET /api/capabilities/content_publish/history` — 已有，支持分页（`limit`, `offset`），返回 `{ "history": [...], "total": N }`

**业务规则：**

1. **Tab 结构：** ContentPublish.vue 改为 3 个 Tab：
   - Tab 1"发布"（当前主界面，原有内容）
   - Tab 2"历史"（新增）
   - Tab 3"设置"（placeholder，后续版本）
2. **历史列表展示：**
   - 每条记录展示：run_id | 发布时间 | 平台列表 | 成功/失败数 | 状态（全部成功 / 部分失败 / 全部失败）
   - 点击展开详情：每个平台的发布结果（post_id, url, error_detail）
   - 失败记录展示"复跑"按钮
3. **分页：**
   - 默认加载最近 20 条
   - 底部"加载更多"按钮（每次追加 20 条）
4. **空状态：** 无历史记录时展示"暂无发布记录"

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `ContentPublish.vue` | 新增 Tab 导航 + history tab 内容 |

**不做什么：**
- 不修改 history API 逻辑
- 不实现按平台/状态筛选（建议但不在本版本）
- 不实现历史记录删除

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 切换到"历史"Tab | 有发布记录 | 展示列表，每条显示时间+平台+状态 |
| AC-02 | 切换到"历史"Tab | 无发布记录 | 展示"暂无发布记录" |
| AC-03 | 展开详情 | 点击某条记录 | 展示各平台结果详情 |
| AC-04 | 点击复跑 | 点击失败记录的复跑 | 调用 `/rerun`，结果更新 |
| AC-05 | 加载更多 | 超过 20 条 | 点击加载更多，追加显示 |

---

### T-0804：队列恢复 UI

**目标：** 在应用重启后，为中断的任务提供批量重试入口，让用户不需手动查找和重新提交。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `apps/desktop/ui-vue/src/components/common/InterruptedJobsPanel.vue` | 新增 | 中断任务面板组件 |
| `apps/desktop/ui-vue/src/stores/system.js` | 修改 | 新增 interrupted jobs 状态 + 加载 action |
| `apps/desktop/ui-vue/src/App.vue` | 修改 | 启动时检查中断任务 + 展示面板 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 新增中断任务相关文案 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 无新增。复用已有 API：
- `GET /api/status/tasks/queue` — 返回任务队列（含 interrupted 状态）
- `POST /api/job/{job_id}/rerun` — 重跑任务（如果已有此端点；否则需确认替代方案）

确认已有 API 情况：
- `GET /api/status/tasks/queue` — 已有，返回 `{ "queue": [...], "running": [...] }`
- 需确认：是否有通用的任务重跑端点。如果没有，本任务范围内新增一个。

**新增 API（仅在确认无现有端点时）：**

| 端点 | 方法 | 说明 | 入参 | 返回 |
|---|---|---|---|---|
| `/api/job/interrupted` | GET | 获取所有中断状态的任务 | 无 | `{ "jobs": [{ "job_id": "...", "kind": "social_export", "created_at": "...", "error": "interrupted" }] }` |
| `/api/job/interrupted/retry-all` | POST | 批量重试所有中断任务 | body: `{ "job_ids": ["id1", "id2"] }` | `{ "ok": true, "retried": 3, "failed": 0 }` |

**业务规则：**

1. **启动检查：**
   - App.vue 的 `onMounted` 中调用 `GET /api/job/interrupted`
   - 如果返回 jobs.length > 0，在顶部展示黄色通知条："发现 {N} 个中断的任务"
2. **面板展示：**
   - 点击通知条展开 InterruptedJobsPanel
   - 每条任务展示：任务类型（kind 映射中文名）、创建时间、中断原因
   - "全部重试"按钮 + 每条任务的单独"重试"/"忽略"按钮
3. **重试逻辑：**
   - 第 1 步：调用 `/api/job/interrupted/retry-all`（或逐个调用）
   - 第 2 步：后端将 interrupted 任务重新入队
   - 第 3 步：前端轮询任务状态
   - 第 4 步：全部完成后通知条消失
4. **忽略逻辑：**
   - "忽略"将任务标记为 `cancelled`（不再在中断列表中出现）
   - "全部忽略"批量标记
5. **task kind 中文映射：**
   - `social_export` → "社媒导出"
   - `content_publish` → "内容发布"
   - `audio_voice` → "配音混音"
   - `refinement` → "画面优化"
   - 其他 → 显示原始 kind

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `InterruptedJobsPanel.vue` | 新增组件 |
| `system.js` store | 新增 `interruptedJobs` ref + `loadInterruptedJobs()` + `retryAll()` + `ignoreAll()` |
| `App.vue` | 启动时调用 `loadInterruptedJobs()` + 展示通知条 |

**不做什么：**
- 不修改 job_runtime.py 的任务恢复逻辑（已有 interrupted 标记）
- 不实现任务优先级排序
- 不修改任务队列的并发控制

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 应用重启后有中断任务 | 3 个 interrupted 任务 | 顶部黄色通知条"发现 3 个中断的任务" |
| AC-02 | 展开面板 | 点击通知条 | 展示 3 条任务详情 |
| AC-03 | 全部重试 | 点击"全部重试" | 3 个任务重新入队，状态变为 running |
| AC-04 | 忽略单个 | 点击某任务"忽略" | 该任务标记 cancelled，从列表消失 |
| AC-05 | 无中断任务 | 正常启动 | 无通知条 |

---

### T-0805：Webhook connector 配置向导

**目标：** 在设置页面提供 Webhook 连接器的配置向导，让用户可以为抖音/小红书等平台配置自定义 Webhook 发布端点。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `apps/desktop/ui-vue/src/views/SettingsView.vue` | 修改 | 新增 Webhook 配置区域 |
| `modules/app_api/routes/settings_routes.py` | 修改 | 新增 connector 配置 CRUD 端点 |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 修改 | 新增 connector 配置文案 |

**新增数据库表：** 无（存储在 `publish_connectors.json`，已有文件格式）

**已有表变更：** 无

**API 定义：**

| 端点 | 方法 | 说明 | 入参 | 返回 |
|---|---|---|---|---|
| `/api/settings/connectors` | GET | 获取所有已配置 connector | 无 | `{ "connectors": { "douyin": { "kind": "webhook", "url": "...", "headers": {...} }, ... } }` |
| `/api/settings/connectors/<platform_id>` | PUT | 配置或更新某平台 connector | body: `{ "kind": "webhook", "url": "https://...", "headers": { "Authorization": "Bearer ..." }, "timeout_s": 30 }` | `{ "ok": true }` |
| `/api/settings/connectors/<platform_id>` | DELETE | 删除某平台 connector | 无 | `{ "ok": true }` |
| `/api/settings/connectors/<platform_id>/test` | POST | 测试连接（发送空 payload 到 webhook URL） | 无 | `{ "ok": true, "status_code": 200, "latency_ms": 150 }` 或 `{ "error": "Connection refused" }` |

**业务规则：**

1. **配置保存：**
   - 第 1 步：校验 `url` 为合法 HTTP/HTTPS URL
   - 第 2 步：校验 `timeout_s` 范围 5-120
   - 第 3 步：URL 非法 → 返回 `{ "error": "Webhook URL 格式不正确" }, 400`
   - 第 4 步：写入 `publish_connectors.json`（使用 `write_json_result` 原子写入）
   - 第 5 步：写入审计日志
2. **连接测试：**
   - 第 1 步：读取该平台的 connector 配置
   - 第 2 步：未配置 → 返回 `{ "error": "该平台尚未配置连接器" }, 404`
   - 第 3 步：发送 HTTP POST 到 webhook URL，body: `{ "test": true, "platform_id": "..." }`
   - 第 4 步：超时(30s) → 返回 `{ "error": "连接超时" }`
   - 第 5 步：成功 → 返回状态码 + 延迟
   - 第 6 步：失败 → 返回错误描述
3. **前端向导：**
   - 按平台分组展示（与发布面板一致）
   - 未配置 → 显示"配置"按钮
   - 已配置 → 显示 webhook URL（脱敏显示前 20 字符）+ "测试" + "编辑" + "删除"按钮
   - 配置表单：URL 输入 + Headers 键值对编辑器 + 超时秒数输入 + "测试连接" + "保存"

**前端变更：**

| 页面/组件 | 变更 |
|---|---|
| `SettingsView.vue` | 新增"平台连接器"区域，包含 YouTube OAuth 状态 + Webhook 配置列表 |

**不做什么：**
- 不修改 content_publish.py 的 webhook 执行逻辑
- 不实现 webhook 签名验证
- 不实现 webhook 重试策略
- 不实现 Headers 中 token 的加密存储（明文存储在 connectors JSON 中，与现有行为一致）

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 配置抖音 webhook | URL=https://hook.example.com/douyin | 保存成功，列表展示"抖音 ✅ https://hook.exampl..." |
| AC-02 | 测试连接成功 | webhook 返回 200 | 提示"连接成功，延迟 150ms" |
| AC-03 | 测试连接失败 | webhook 不可达 | 提示"连接失败：Connection refused" |
| AC-04 | 删除 connector | 点击删除 | 确认后删除，列表更新 |
| AC-05 | 配置后发布 | 配置抖音 webhook + 发布到抖音 | content_publish 使用 webhook connector 发布 |

---

# v0.9.0 — 工程治理与可维护性

## 3.3 本轮目标与边界

### 只做什么

| 任务编号 | 任务名 |
|---|---|
| T-0901 | server.py L1 继续拆分（services 层） |
| T-0902 | 前端 E2E 测试基础建设 + 核心路径覆盖 |
| T-0903 | 发布链路 OpenAPI 文档 |
| T-0904 | 安全审计补全（安全事件日志 + 输入校验收尾） |

### 明确不做什么

- 不做 GlobalMediaLibrary 拆分（评估后认为 569KB 单文件虽大但职责单一，优先级低于其他任务）
- 不做前端组件库抽象
- 不做性能优化
- 不做可视化时间线编辑器（Phase 3 任务）
- 不做 Windows/Linux 安全存储后端

## 4.3 优先级与顺序（v0.9.0）

| 顺序 | 任务 | 理由 | 依赖 |
|---|---|---|---|
| 1 | T-0901 | server.py 5,997 行是最大的工程债务，但需要先于测试基建（拆分后更易测试） | 无 |
| 2 | T-0904 | 安全事件日志是审计遗留，改动小但价值高 | 无（可与 T-0901 并行） |
| 3 | T-0902 | E2E 测试需要前面版本的 UI 改动稳定后再建设 | T-0901（server 稳定后） |
| 4 | T-0903 | OpenAPI 文档需要 API 稳定后再生成 | T-0901 |

## 5.3 各任务详细定义（v0.9.0）

---

### T-0901：server.py L1 继续拆分

**目标：** 将 server.py 从 5,997 行进一步拆分，提取 services 层和中间件层到独立文件，目标缩减到 ≤ 2,000 行。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `modules/app_api/server.py` | 修改 | 提取代码到独立模块 |
| `modules/app_api/services/workflow_runner.py` | 新增 | 工作流执行服务 |
| `modules/app_api/services/publish_orchestrator.py` | 新增 | 发布编排服务 |
| `modules/app_api/services/library_service.py` | 新增 | 素材库服务层 |
| `modules/app_api/middleware/error_handler.py` | 新增 | 错误处理中间件 |
| `modules/app_api/middleware/security.py` | 新增 | 安全校验中间件 |

**新增数据库表：** 无

**已有表变更：** 无

**API 定义：** 无变更。所有对外 API 签名保持不变。

**业务规则：**

1. **拆分原则：** 只做 extract，不做重构。每个提取的函数/类保持原有签名和行为。
2. **拆分批次：**
   - **L1-4:** 提取 workflow 相关函数（_run_step, _build_render_config 等）→ `services/workflow_runner.py`
   - **L1-5:** 提取 publish 编排函数 → `services/publish_orchestrator.py`
   - **L1-6:** 提取 library 查询/入库函数 → `services/library_service.py`
   - **L1-7:** 提取 error_handler / security before_request → `middleware/`
3. **每次拆分后必须：** 运行全量测试，确保 173+ 测试全部通过
4. **server.py 最终只保留：** app factory（create_app）、Blueprint 注册、依赖装配、启动配置

**不做什么：**
- 不改变函数签名
- 不改变 Blueprint 注册方式
- 不改变依赖注入模式（lambda 闭包）
- 不引入新的抽象层或框架
- 不合并或拆分已有的 routes 文件

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | server.py 行数 | wc -l | ≤ 2,000 行 |
| AC-02 | 全量回归 | pytest | 全部通过 |
| AC-03 | 导入关系 | 无循环依赖 | 无 ImportError |
| AC-04 | 功能回归 | 手动操作核心流程 | 7 步工作流正常、发布正常、素材库正常 |

---

### T-0902：前端 E2E 测试基础建设

**目标：** 建立 Playwright 测试基础设施，覆盖 5 条核心用户路径。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `tests/e2e/` | 新增目录 | Playwright 测试套件 |
| `tests/e2e/playwright.config.js` | 新增 | Playwright 配置 |
| `tests/e2e/fixtures/` | 新增 | 测试 fixture（样本视频/图片） |
| `tests/e2e/specs/onboarding.spec.js` | 新增 | 引导流程测试 |
| `tests/e2e/specs/library.spec.js` | 新增 | 素材库基本流程测试 |
| `tests/e2e/specs/publish.spec.js` | 新增 | 发布基本流程测试 |
| `tests/e2e/specs/export.spec.js` | 新增 | 社媒导出基本流程测试 |
| `tests/e2e/specs/settings.spec.js` | 新增 | 设置页面基本流程测试 |
| `package.json` 或 `apps/desktop/ui-vue/package.json` | 修改 | 新增 Playwright 依赖 + test 脚本 |

**新增数据库表：** 无

**已有表变更：** 无

**业务规则：**

1. **测试运行方式：** Playwright 启动 Flask dev server + Vite dev server，通过真实 HTTP 访问
2. **5 条核心路径：**
   - 路径 1：首次打开 → 引导弹窗出现 → 跳过 → 不再弹出
   - 路径 2：素材库 → 搜索 → 结果展示
   - 路径 3：发布面板 → 选择 blog → 生成计划 → 查看结构化结果
   - 路径 4：社媒导出 → 选择平台卡片 → 生成计划
   - 路径 5：设置页面 → 修改 AI provider → 保存
3. **不做全面覆盖**——只建立基础设施 + 5 条冒烟测试

**不做什么：**
- 不覆盖所有 12 个能力面板
- 不做视觉回归测试
- 不做性能测试
- 不集成 CI/CD

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 运行 E2E 测试 | `npx playwright test` | 5 个 spec 全部通过 |
| AC-02 | 引导流程测试 | 首次打开 | 弹窗出现 → 跳过 → 再次打开不弹窗 |
| AC-03 | 发布测试 | 选择 blog | 计划结构化展示（非 raw JSON） |

---

### T-0903：发布链路 OpenAPI 文档

**目标：** 为发布相关的 API 端点生成 OpenAPI 3.0 规范文档，方便 Agent 和第三方集成。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `docs/api/openapi-publish.yaml` | 新增 | 发布链路 OpenAPI 文档 |
| `modules/app_api/routes/ui_routes.py` | 修改 | 新增 `/api/docs/publish` 静态文件路由 |

**新增数据库表：** 无

**已有表变更：** 无

**业务规则：**

1. 覆盖端点范围（仅发布链路，不含全量 API）：
   - `/api/capabilities/content_publish/*` (6 个端点)
   - `/api/capabilities/social_export/*` (10 个端点)
   - `/api/capabilities/publish_prep/*` (3 个端点)
   - `/api/settings/oauth/youtube/*` (4 个端点)
   - `/api/settings/connectors/*` (4 个端点)
2. 每个端点定义：path, method, summary, parameters, requestBody, responses (200/400/404/500)
3. 文档以 YAML 文件存储在 `docs/api/`，不引入 Swagger UI（保持轻量）

**不做什么：**
- 不实现 Swagger UI 在线浏览
- 不覆盖非发布链路的 API
- 不自动生成（手工编写，确保准确性）

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | YAML 语法校验 | openapi-lint | 无 error |
| AC-02 | 端点覆盖 | 与代码对照 | 27 个端点全部记录 |
| AC-03 | 示例请求/响应 | 每个端点 | 至少有 1 个完整示例 |

---

### T-0904：安全审计补全

**目标：** 补全安全事件日志（认证失败、CSRF 拦截等），并完成剩余 ~5% 路由的输入校验。

**改动范围：**

| 文件 | 操作 | 说明 |
|---|---|---|
| `modules/app_api/server.py` 或 `middleware/security.py` | 修改 | 安全事件记录 |
| `modules/app_api/audit_log.py` | 修改 | 新增 security_event 类型 |
| 剩余未校验路由文件（约 2-3 个） | 修改 | 补全输入校验 |

**新增数据库表：** 无（使用已有 audit_log 表）

**已有表变更：** audit_log 表新增事件类型（数据层面，不改 schema）

**业务规则：**

1. **安全事件记录范围：**
   - CSRF token 校验失败 → `_audit("security_csrf_fail", ...)`
   - Origin 校验失败 → `_audit("security_origin_fail", ...)`
   - API Token 缺失/无效 → `_audit("security_token_fail", ...)`
   - 连续认证失败（5 次/分钟同 IP）→ `_audit("security_brute_force", ...)`
2. **记录内容：** 时间戳、IP（localhost 场景下为 127.0.0.1）、请求路径、失败原因
3. **best-effort 写入：** 安全日志写入失败不阻塞请求处理（沿用 audit_log 已有的 best-effort 模式）
4. **输入校验收尾：** 排查所有路由文件，找到使用 `request.json.get()` 但未经 `parse_str_param` / `parse_int_param` 处理的参数，补全校验

**不做什么：**
- 不实现安全日志查询 API（仅写入，管理员通过 SQLite 直查）
- 不实现 IP 黑名单
- 不实现速率限制（超出本版本范围）

**验收标准：**

| 编号 | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| AC-01 | 伪造 CSRF token | 发送错误 CSRF header | 返回 403 + audit_log 写入 security_csrf_fail |
| AC-02 | 缺失 API token | 不带 token 请求写端点 | 返回 401 + audit_log 写入 security_token_fail |
| AC-03 | 非法 Origin | 发送 Origin: https://evil.com | 返回 403 + audit_log 写入 security_origin_fail |
| AC-04 | 输入校验收尾 | 排查全部路由 | 零残留未校验参数 |
| AC-05 | 回归 | 所有现有测试 | 通过 |

---

## 6. 实现约束

### 目录结构规范

```
modules/app_api/
  server.py              — app factory + Blueprint 注册
  routes/                — 路由 Blueprint 模块
  services/              — 业务服务层
  middleware/            — 请求处理中间件
  param_utils.py         — 参数解析工具
  audit_log.py           — 审计日志
  secure_store.py        — 安全存储
  migrations.py          — schema migration

apps/desktop/ui-vue/src/
  components/capabilities/  — 能力面板组件
  components/common/        — 通用组件
  components/onboarding/    — 引导组件
  stores/                   — Pinia store
  composables/              — 可复用 composition
  views/                    — 页面视图
  i18n/                     — 文案管理
```

### Migration 命名规范
- 格式：`YYYYMMDD_HHMMSS_<description>.sql`
- 本计划无新增 migration（不新增数据库表）

### 审计要求
- 所有敏感操作（发布/删除/设置变更/OAuth 连接断开）必须写入 audit_log
- best-effort 写入，不阻塞主流程

### 加密要求
- OAuth token 通过 secure_store 存储（macOS Keychain 优先，降级到加密文件）
- Webhook URL/Headers 明文存储在 publish_connectors.json（与现有行为一致）

### 人工入口 + API 双入口
- 所有新增功能必须同时有前端 UI 入口和 API 端点
- 如 T-0804 的中断任务恢复：既有通知条 UI，也有 API 可调用

---

## 7. 任务领取规则

1. 每次只能领取一个任务
2. 完成后按固定汇报格式汇报，确认后再领下一个
3. 不混做不同版本的任务（v0.7.0 完成后再开始 v0.8.0）
4. 执行过程中发现的衍生任务仅记录到"建议但不在本版本范围内"，不自行执行

---

## 8. 测试要求

### 测试层次

| 层次 | 覆盖范围 | 工具 |
|---|---|---|
| 单元测试 | 新增/修改的 Python 函数 | pytest |
| 集成测试 | 新增 API 端点（Flask test client） | pytest + conftest.py fixture |
| 冒烟测试 | 核心用户路径端到端 | Playwright（v0.9.0 建设） |

### 覆盖重点

- v0.7.0：纯前端改动，主要验证 UI 行为（手动验证 + 截图留证），后端回归跑全量 pytest
- v0.8.0：涉及新 API 端点（OAuth / connector CRUD），必须补单元测试 + 集成测试
- v0.9.0：server.py 拆分必须每步全量回归

### 每个任务完成后必须说明

1. 新增测试文件及测试数量
2. 全量回归结果（X/X 通过）
3. 手动验证的场景和结果

---

## 9. 版本号管理

| 版本 | 批次编号 | 说明 |
|---|---|---|
| v0.7.0 | T-0701 ~ T-0706 | UX 修复 |
| v0.8.0 | T-0801 ~ T-0805 | 发布链路 |
| v0.9.0 | T-0901 ~ T-0904 | 工程治理 |

- 每个任务完成后版本号递增 patch（如 v0.7.1, v0.7.2...）
- 版本全部完成后打 minor tag（v0.7.0, v0.8.0, v0.9.0）
- 创建 `VERSION.md` 文件记录当前版本号（当前不存在此文件）

---

## 10. 文档产出要求

### 每个任务完成后必须更新

1. `docs/changelog-v0.7.0.md`（或对应版本号）— 增量变更记录
2. 涉及 API 变更的任务 → 更新 `docs/capabilities-api.md`
3. 涉及前端变更的任务 → 更新受影响组件的内联注释

### 版本全部完成后必须产出

| 文档 | 路径 |
|---|---|
| 版本 changelog | `docs/changelog-v{x.y.z}.md` |
| 版本发布说明 | `docs/release-notes-v{x.y.z}.md` |
| 更新后的 roadmap | `docs/roadmap_v2.0.md`（标记完成项） |
| 更新后的下一步计划 | `docs/next_dev_plan.md` |

---

## 11. 汇报格式

```
## [T-XXXX] 闭环汇报

### 1. 任务编号与目标
T-XXXX: 一句话目标

### 2. 文件清单
| 文件路径 | 操作 | 职责变化 |
|---------|------|---------|

### 3. 数据/API 影响
- 新增表：无 / 表名
- 新增 API：无 / 端点列表
- 已有 API 变更：无 / 变更说明

### 4. 实现说明
关键实现决策和技术选择

### 5. 验证结果
| 验收编号 | 场景 | 结果 |
|---------|------|------|
全量回归：X/X 通过

### 6. 影响分析
- 影响的已有模块：
- 回归风险：

### 7. Commit
commit hash + message

### 8. 是否继续下一个任务
建议 / 不建议，原因：
```

---

## 12. 新增数据库表汇总

| 版本 | 任务 | 新增表 | 说明 |
|---|---|---|---|
| v0.7.0 | 全部 | 0 张 | 纯前端改动 + 1 个 JSON 文件 |
| v0.8.0 | T-0804 | 0 张（复用 jobs 表） | 新增 API 但不新增表 |
| v0.9.0 | 全部 | 0 张 | 拆分 + 测试 + 文档 |
| **合计** | | **0 张新增表** | |

---

## 13. 开始前必须先输出

在开始 T-0701 之前，执行者必须先输出以下三项，确认后再开始写代码：

### 13.1 当前代码现状理解

需确认：
- `ContentPublish.vue` 当前有多少行、哪些 reactive 变量、哪些 API 调用
- `GET /api/capabilities/content_publish/platforms` 返回的完整数据结构
- `labels.js` 当前是否有 contentPublish 相关条目
- `POST /api/capabilities/content_publish/plan` 的完整响应结构（特别是 steps 数组的字段）

### 13.2 第一个任务的实施计划

- 按哪个顺序改（先改 labels.js → 再改 ContentPublish.vue → 最后手动验证）
- 预计改动量（行数估算）
- 需要注意的兼容性点

### 13.3 第一个任务的预计修改文件清单

- `apps/desktop/ui-vue/src/components/capabilities/ContentPublish.vue`
- `apps/desktop/ui-vue/src/i18n/labels.js`
- 其他（如有）

**在这三项输出之前，不要开始写代码。**

---

## 建议但不在本版本范围内

以下为审计中识别到但未纳入 v0.7.0-v0.9.0 的改进建议，供后续版本参考：

1. **抖音/小红书原生 API 集成**——需要企业资质和平台审核，建议单独立项
2. **可视化时间线编辑器**——roadmap Phase 3 任务，建议 v1.0.0 启动
3. **GlobalMediaLibrary 拆分**——569KB 单文件，建议在功能稳定后专项处理
4. **Windows Credential Manager / Linux Secret Service**——安全存储后端完善
5. **多语言 i18n**——当前中文为主，英文标签维持现状
6. **发布内容日历视图**——按日期展示已发布/计划发布内容
7. **发布 A/B 测试**——同内容不同文案投放对比
8. **按平台/状态筛选发布历史**——T-0803 的增强
9. **CI/CD 集成 E2E 测试**——T-0902 的后续

---

## 变更记录

| 日期 | 版本 | 说明 |
|---|---|---|
| 2026-03-19 | V1.0 | 初版，基于全面审计报告制定 3 版本 15 任务计划 |
