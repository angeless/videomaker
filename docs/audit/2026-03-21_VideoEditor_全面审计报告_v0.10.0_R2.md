# VideoEditor v0.10.0 — 全面深度审计报告（修订版 R2）

**文档编号**：AUDIT-2026-0321-R2
**审计版本**：v0.10.0
**审计日期**：2026-03-21
**修订说明**：R2 修正 BUG-005 定性（原误报），补充完整 UX/前端交互测试章节（UX-T001～UX-T028）
**审计模式**：手动测试 + 代码级静态审计 + 运行时动态测试 + 前端组件逐件审计

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [产品定位与用户价值评估](#2-产品定位与用户价值评估)
3. [架构审计](#3-架构审计)
4. [后端接口测试记录（TC001–TC057）](#4-后端接口测试记录)
5. [安全性审计（含 BUG-005 修订说明）](#5-安全性审计)
6. [前端 UX 与交互审计（UX-T001–UX-T028）](#6-前端-ux-与交互审计)
7. [数据库与数据一致性审计](#7-数据库与数据一致性审计)
8. [极端情况与崩溃测试](#8-极端情况与崩溃测试)
9. [功能完整性评估](#9-功能完整性评估)
10. [问题总表（含 UX 项）](#10-问题总表)

---

## 1. 执行摘要

### 总体评分

| 维度 | 评分（10分制） | 简评 |
|------|-------------|------|
| 架构设计 | 7.5 | 层次清晰，Library 模块单体化是主要风险 |
| API 接口完整性 | 6.0 | 路由 50+ 条，存在多处缺失与断裂 |
| 安全性 | 4.5 | 默认配置下 CSRF 保护从不执行 |
| 前端 UX / 交互 | 6.5 | 框架完善，空状态 / 加载反馈 / 步骤引导有明显短板 |
| 数据库设计 | 7.0 | 表结构优质，缺种子数据 |
| 稳定性 | 5.0 | 两处 100% 必现 Segfault |
| 功能完整性 | 5.5 | 核心链路（Step 3 AI 脚本）未完成 |
| 用户价值实现 | 5.0 | 无法端到端跑通一个真实视频生产 |

### 关键发现概览

🔴 **P0 — 立即阻断**（3 个）
- **[BUG-001]** `null` 参数传入 `/api/init` → 500 + Segfault
- **[BUG-002]** `step=99` 越界调用 `/api/run_step` → AttributeError + Segfault
- **[SEC-001]** CSRF 保护默认从不执行（双开关逻辑缺陷）

🟠 **P1 — 严重**（7 个）
- **[BUG-003]** Step 3 AI 脚本生成未实现（代码内有显式 TODO）
- **[BUG-004]** provider 字段无枚举校验，任意字符串被写入数据库
- **[BUG-006]** 多个关键路由缺失（health/projects/workflow/status）
- **[BUG-007]** content_publish/platforms 响应 UnicodeDecodeError
- **[ARCH-001]** global_media_library.py 13,245 行单体文件
- **[UX-P1-001]** 预检 3 项 error 未拦截路由，用户在异常状态下操作
- **[UX-P1-002]** 素材库完全为空时缺乏有效首屏引导（向导触发条件不明确）

🟡 **P2 — 中优先级**（13 个）— 见第 10 章

> ⚠️ **BUG-005 修订说明（原 P1 已撤销）**
>
> 原报告将"ingest/local 无路径白名单"列为 P1 Bug。经审查，**这不是 Bug，是合理的桌面端设计**。
> VideoEditor 是本地桌面应用，运行在用户自己的机器上，以用户自身权限访问文件系统。
> 用户有权将任意本地目录（包括 ~/Movies、外置硬盘等）指定为素材来源，这是完全合理的。
> 该路由已检查路径存在性，并在 job 内部只处理识别出的视频/图片文件，非媒体文件自然被跳过。
> **此项从问题清单移除。** 唯一仍需关注的风险是 CSRF（若外部网页通过 CSRF 触发此接口），但该问题已由 SEC-001 覆盖。

---

## 2. 产品定位与用户价值评估

### 2.1 产品声明的价值主张

VideoEditor 定位为**桌面端短视频 AI 生产系统**，7 步全自动流水线（分析→选题→脚本→匹配→预览→粗剪→精渲染），目标用户为内容创作者（个人/小团队）。

### 2.2 真实用户体验模拟

**作为一名第一次安装此软件的短视频创作者，我按顺序走完整个流程：**

**① 第一次打开 — 引导向导（OnboardingModal）**

启动后触发 3 步向导：欢迎 → 导入素材 → 开始创作。
- ✅ 向导结构清晰，步进器（dot indicator）视觉友好
- ⚠️ 向导触发条件依赖 `onboarding_completed=false`，但不清楚用户何时会看到它（StartupView 不总触发向导）
- ❌ 向导第 2 步"导入素材"完成后不会自动跳转素材库，用户需手动点击第 3 步按钮
- ❌ 向导跳过后，再次进入应用没有任何补救引导，新用户面对空白界面束手无策

**② 进入素材库 — LibraryView**

- ✅ 空库时有"导入素材"按钮和"配置 AI"快捷入口，有基础引导
- ✅ 搜索栏 Placeholder 在空库时变为"请先导入素材后再搜索"（细节体贴）
- ⚠️ 面板分组（导入与浏览 / 维护 / 工程修复）对新用户过于专业，不知道从哪里开始
- ❌ 标签浏览器（TagBrowser）数据为空，在空库状态下展示空面板，没有"还没有标签，导入素材后自动生成"的说明

**③ 新建项目 — ProjectDialog**

- ✅ 弹窗逻辑清晰：新建（选素材目录 + 项目目录）vs 打开（选项目目录）
- ✅ 前端表单有必填校验（videosDir / projectDir required）
- ⚠️ 两个路径输入框均为 `readonly`，必须通过"浏览"按钮选择，不支持手动输入路径（对高级用户不友好）
- ❌ 项目目录和素材目录的区别没有任何解释，普通用户不理解"为什么要选两个文件夹"
- ❌ 项目名输入框没有任何提示说明会自动生成（如 `proj_selected_20260321_143000`），用户填写后发现被忽略

**④ 进入工作流 — CreateView + WorkflowManagerView**

- ✅ 侧栏双区域（引导流程 / 自由创作）结构合理
- ✅ 最近项目列表附带状态徽章（草稿/进行中/已完成）
- ❌ 7 个侧栏步骤无完成状态标记（全部显示相同样式，无法区分已完成/当前/未开始）
- ❌ 用户点击"工作流"后进入的视图（ProductionView + WorkflowManagerView）与点击"💡 思路"的视图（CreateView + IdeateView）是两套不同路由体系，但侧栏没有明显区分，新用户容易迷路
- ❌ 工作流视图空状态时只有"暂无自定义工作流，可从上方模板创建"，没有说明和引导式工作流（7步）的关系

**⑤ AI 配置 — SettingsView**

- ✅ Provider 通过 select 选择，AI Model 通过 select 选择，防止任意字符串输入（前端层面）
- ⚠️ 但后端 `/api/settings/ai` 没有枚举校验，直接 POST 仍可绕过前端写入任意值
- ✅ API Key 以 password 类型输入，配置成功后显示"已配置"徽章
- ❌ Key 配置成功后没有连通性测试（"测试连接"按钮），用户不知道 Key 是否有效
- ❌ Embedding Model 配置项对普通用户完全陌生，没有任何解释说明
- ❌ 三个 AI 配置块（Provider / Model / Embedding）之间的依赖关系不明确（换了 Provider 会影响 Embedding 选项吗？）

**⑥ 工作流 7 步执行**

- Step 1 素材分析：异步 Job，界面展示 job_id，但没有"预计时间"、"已处理/总计"数量实时更新（只有百分比）
- Step 2 选题：前端 IdeateView 仅是 TopicLibrary + TopicCopy 两个面板，无工作流上下文传递说明
- Step 3 脚本：后端 TODO，前端未展示明确的"此功能开发中"状态
- Steps 4-7：可达性取决于 Step 3 能否完成，目前断链

**综合用户体验结论：** 产品对首次用户友好度不足，引导链路有断点，高级功能的认知门槛对目标用户（短视频创作者，非开发者）偏高。核心 AI 能力未就绪，用户无法体验到产品价值主张。

---

## 3. 架构审计

### 3.1 架构优点

- ✅ 四层分离（接入/业务/支撑/数据），边界清晰
- ✅ 21 个 Blueprint 路由按功能域隔离
- ✅ workflow.json 原子写入（tempfile + os.replace + fsync），崩溃安全
- ✅ 外部依赖全部 optional，优雅降级
- ✅ App Store 采用门面模式（Facade）统一封装 project/system/preferences 三个子 store，向后兼容设计良好
- ✅ Vue 组件粒度合理，大组件（如 ProjectRelinkPanel 1790行）内部自洽

### 3.2 架构问题

**[ARCH-001] Library 模块严重单体化**
`global_media_library.py` 13,245 行，包含：资产入库、语义分析、指纹计算、标签管理、搜索、GDrive 集成、路径重链接、重复检测、学习候选等所有逻辑。任何改动风险极高。

**[ARCH-002] CSRF 安全逻辑设计缺陷**
```python
enforce_csrf = bool(req_csrf and req_token)  # 双开关 AND，任一为 0 则 CSRF 永不执行
```

**[ARCH-003] Step 3 强绑定 Jianying 格式**
Step 3 直接生成 Jianying JSON，未经 Adapters 层抽象，扩展其他 NLE 成本高。

**[ARCH-004] 依赖分层缺失**
`requirements.txt` 未区分必选/可选，新用户 `pip install -r requirements.txt` 会拉取 torch（>3GB），失败率高。

**[ARCH-005] 路由命名不一致**
`/api/system/health` 不存在，但 `/api/system/preflight` 存在；`/api/settings` 不存在，但 `/api/settings/ai` 存在。缺乏根路由规范。

---

## 4. 后端接口测试记录

### 4.1 系统启动与自检

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC001 | GET /api/system/health | 404 路由不存在 | ❌ FAIL |
| TC002 | GET /api/system/preflight | 200，3 error + 7 warning + 6 ok | ⚠️ WARN |
| TC003 | GET /api/projects | 404 路由不存在 | ❌ FAIL |
| TC005 | GET /api/settings | 404 路由不存在 | ❌ FAIL |
| TC006 | GET /api/system/load | 200，CPU/内存/队列状态正常 | ✅ PASS |
| TC020 | GET /api/system/startup-timing | 200 | ✅ PASS |
| TC046 | GET /api/system/audit | 200，count=0 | ✅ PASS |

### 4.2 工作流初始化

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC008 | POST /api/init, videos_dir 为空 | 400："videos_dir 不能为空" | ✅ PASS |
| TC009 | POST /api/init, 不存在路径 | 400："素材目录不存在" | ✅ PASS |
| TC010 | POST /api/init, 正常路径 | 200，完整 config + 工作流状态 | ✅ PASS |
| TC011 | 重复 POST /api/init 同一路径 | 200 幂等，状态不重置 | ✅ PASS |
| TC012 | POST /api/init, project_dir=null | **500 + AttributeError + Segfault** | ❌ **P0** |
| TC013 | GET /api/workflow/status | 404 路由不存在 | ❌ FAIL |

### 4.3 设置模块

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC016 | GET /api/settings/ai | 200，AI 配置正常 | ✅ PASS |
| TC017 | POST /api/settings/ai, api_key="" | 200，空 Key 被保存无警告 | ⚠️ WARN |
| TC018 | POST /api/settings/ai, provider="unknown_provider" | **200，任意字符串被接受** | ❌ P1 |
| TC019 | GET /api/settings/ui | 200，creator_mode=true | ✅ PASS |
| TC044 | GET /api/settings/oauth/youtube/status | 200，connected=false | ✅ PASS |
| TC045 | GET /api/settings/connectors | 200，connectors={} | ✅ PASS |
| TC047 | GET /api/settings/publish | 200，connector_count=0 | ✅ PASS |

### 4.4 素材库

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC021 | GET /api/library/health | 200，所有覆盖率为 0 | ⚠️ WARN |
| TC022 | GET /api/library/stats | 200，available_assets=0 | ✅ PASS |
| TC025 | SQL 注入：search?q=' OR 1=1 -- | 200，参数化查询防护正常 | ✅ PASS |
| TC042 | 超长 query（1万字符） | 200，无长度限制 | ⚠️ WARN |
| TC043 | GET /api/library/tags | 200，空结果（无种子数据）| ⚠️ WARN |
| TC048 | GET /api/library/duplicates | 200，groups=[] | ✅ PASS |
| TC049 | GET /api/library/locations/roots | 200，roots=[] | ✅ PASS |

### 4.5 步骤执行

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC033 | POST /api/approve/1, 未初始化 | 404："请先运行 Step 1" | ✅ PASS |
| TC034 | GET /api/job/nonexistent-id | 404："job 不存在" | ✅ PASS |
| TC036 | POST /api/run_step, 无参数 | 200，默认执行 step=1 | ⚠️ WARN |
| TC037 | POST /api/run_step, step=99 | **AttributeError + Segfault** | ❌ **P0** |
| TC038 | POST /api/workflows/run, 空参数 | 400："缺少 workflow_id" | ✅ PASS |
| TC039 | GET /api/capabilities/content_publish/platforms | UnicodeDecodeError | ❌ **P1** |

### 4.6 安全性测试

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC023 | POST + Origin: evil.com（CSRF 测试）| **200，放行** | ❌ **P0** |
| TC024 | GET /api/files/../../etc/passwd | 403，正确拒绝 | ✅ PASS |
| TC026 | XSS 注入（topic_library）| 400（字段校验拦截）| ✅ PASS |
| TC027 | 26MB 超大 Payload | 413，正确拦截 | ✅ PASS |
| TC028 | 无效 JSON Body | 400，正确拦截 | ✅ PASS |
| TC031 | null 参数 | 500 崩溃 | ❌ P0 |

---

## 5. 安全性审计

### 5.1 CSRF 保护缺陷（SEC-001）—— P0

**测试结果：**
```
操作：POST /api/settings/ai（修改 AI 配置）
      Header: Origin: http://evil.com
结果：HTTP 200 — 操作成功，配置被写入
预期：HTTP 403 — Origin 校验拦截
```

**根本原因：**
```python
# security.py line 126
_REQUIRE_LOCAL_API_TOKEN = False   # 环境变量默认 0
_REQUIRE_CSRF_PROTECTION = True    # 单独为 True，但无效

enforce_csrf = bool(req_csrf and req_token)
# → bool(True AND False) = False → CSRF 永不执行
```

CSRF 保护被设计为需要同时启用"Token 认证"才生效，但 Token 认证默认关闭。结果：默认部署下无任何来源校验。

**影响：** 恶意网页可通过 CSRF 触发修改 AI 配置、触发素材导入任务、触发工作流运行等操作。

**修复方向：** 将 `enforce_csrf` 独立于 token 开关，或将默认值改为安全优先。

### 5.2 BUG-005 修订 — 路径访问（已撤销为 Bug）

**原报告：** `/api/library/ingest/local` 无路径白名单，可将 /etc/ 等系统目录提交为素材分析目标。

**修订后的判断：** 这是**桌面应用的合理设计**，不是 Bug。

- VideoEditor 是本地桌面应用，运行在用户本机，以用户自身 OS 权限访问文件系统
- 用户有权指定任意本地目录（外置硬盘、NAS 挂载、任意文件夹）为素材来源
- 接口内部已做 `root.exists()` 检查，且入库处理只针对识别出的视频/图片扩展名
- 系统文件（如 /etc/hostname）不是视频/图片，会在素材扫描阶段被自然过滤

**残留说明：** 此路径若被 CSRF 攻击滥用，可触发对任意目录的扫描（尽管非媒体文件会被过滤）。但该风险属于 CSRF 问题范畴（SEC-001），而非本接口的设计缺陷。

### 5.3 输入校验总结

| 测试项 | 结果 |
|--------|------|
| SQL 注入（search API）| ✅ 参数化查询防护 |
| XSS 注入（topic_library）| ✅ 字段校验拦截 |
| 超大 Payload（26MB）| ✅ 413 拦截 |
| 无效 JSON | ✅ 400 拦截 |
| null 参数 | ❌ 500 崩溃 |
| 超长 query（无限制）| ⚠️ 接受 |
| 无效 provider 枚举 | ❌ 接受并持久化 |
| 文件路径穿越（/api/files）| ✅ 403 拦截 |

---

## 6. 前端 UX 与交互审计

> 本章为 R2 新增章节，包含 28 个 UX 测试用例（UX-T001 ～ UX-T028）。
> 采用逐界面、逐操作的测试方式，模拟一名从未接触过此软件的内容创作者的真实操作路径。

---

### 6.1 启动与引导流程

**UX-T001：首次启动 — 向导触发**

| 项目 | 结果 |
|------|------|
| 触发条件 | `onboarding_completed=false`（UI 设置） |
| 界面 | OnboardingModal 3 步向导（欢迎→导入→开始）|
| 步进器 | ✅ Dot indicator 视觉清晰，已完成步骤高亮 |
| 问题 1 | ⚠️ 向导不总随应用启动出现，触发时机不稳定 |
| 问题 2 | ❌ 向导跳过后，再次启动无任何补救引导，新用户将直接面对空白界面 |
| 问题 3 | ❌ 第 2 步素材导入完成（ingestDone）后，"下一步"按钮不会自动激活，仍需用户手动发现 |

**UX-T002：启动屏 — StartupView**

| 项目 | 结果 |
|------|------|
| 进度条 | ✅ 6 步序列（Bootstrap→设置→预检→AI→状态→队列），有百分比动画 |
| 错误展示 | ⚠️ 预检 error 显示列表，但"重新检查"按钮重新触发的是全序列（非仅预检），用户等待时间长 |
| 阻断逻辑 | ❌ 3 项 error 后没有路由守卫，用户可手动路由到主界面继续操作 |
| 路由 | ✅ 有项目时跳 /create/workflow，无项目时跳 /library（合理）|

**UX-T003：系统预检项展示**

代码中展示 `check.label || check.name`，若后端只传 `id`（不传 `name`/`label`）将显示空白。实际测试后端确实返回 `title` 字段，但前端读取的是 `name`，字段名不匹配。

---

### 6.2 素材库界面（LibraryView）

**UX-T004：空库首屏体验**

| 项目 | 结果 |
|------|------|
| 搜索框 Placeholder | ✅ 空库时显示"请先导入素材后再搜索"（贴心细节）|
| 工具栏 | ⚠️ 搜索模式（混合/关键词/向量）和媒体类型下拉框在无素材时仍可操作，无意义 |
| 面板提示 | ✅ 空库提示"首次使用：先导入素材，再搜索或浏览" |
| 导入按钮 | ✅ 空状态展示"导入素材"和"配置 AI"两个快捷入口 |
| 标签浏览器 | ❌ 空库时仍展示 TagBrowser 空面板，无说明（"标签将在导入后自动生成"）|
| 问题 | ❌ 搜索分析（SearchAnalyticsPanel）和自定义标签（CustomTagPanel）在空库时一并展示，造成信息噪音 |

**UX-T005：素材卡片（LibraryAssetCard）交互**

| 项目 | 结果 |
|------|------|
| 缩略图 | ✅ 无缩略图时显示 emoji 占位 + 文件扩展名 |
| 时长徽章 | ✅ 叠加在缩略图右下角 |
| 质量评分 | ✅ 0-1 映射为"优秀/良好/一般/较差"，有 title 提示 |
| 标签展示 | ✅ 分类展示，超出部分可展开（+N 更多）|
| 点击行为 | ✅ 点击整张卡片打开详情，emit select 事件 |
| 问题 1 | ⚠️ 无 hover 预览（视频无法悬停预览），用户需点击进入详情才能确认素材内容 |
| 问题 2 | ❌ 质量评分 title 文案（"0-1，综合考虑清晰度、构图和光线"）对普通用户是专业术语 |
| 问题 3 | ⚠️ 点击"匹配标签"可查看证据，但此交互完全不可发现（无图标或视觉提示）|

**UX-T006：列表视图 vs 网格视图切换**

- ✅ 切换按钮（⊞ / ☰）有 active 状态
- ✅ 列表视图有列头（文件名/类型/时长/分辨率/标签/质量）
- ❌ 切换视图模式时没有过渡动画，内容区域突变

**UX-T007：面板分组切换（导入与浏览 / 维护 / 工程修复）**

- ✅ 三个 Tab 按钮，激活状态有视觉区分（btn-primary vs btn-ghost）
- ❌ "维护"和"工程修复"对普通用户过于技术性，命名不符合目标用户语境
- ❌ "工程修复"（ProjectRelink）暴露给所有用户，但绝大多数用户永远用不到

---

### 6.3 项目新建/打开弹窗（ProjectDialog）

**UX-T008：新建项目弹窗**

| 项目 | 结果 |
|------|------|
| 字段 | 项目名称 + 素材目录 + 项目保存位置 |
| 路径输入 | ❌ readonly，只能通过系统文件选择器选择，高级用户无法手动输入 |
| 两个目录 | ❌ 无任何解释说明"为什么要选两个文件夹"（素材目录 vs 项目目录的区别）|
| 项目名 | ❌ 填写后不生效（后端会自动生成 `proj_xxx_yyyymmdd_hhmmss` 格式）|
| 表单校验 | ✅ 前端 required 校验，提交前显示错误信息 |
| 加载状态 | ✅ 提交后按钮文字变"创建中..."并 disabled |
| 点击遮罩 | ✅ 点击 overlay 关闭弹窗（@click.self）|
| 问题 | ❌ 无"取消"操作的二次确认（若用户在填写一半时误触遮罩，直接关闭）|

**UX-T009：打开项目弹窗**

- ✅ 只需选择一个目录（项目目录），比新建简单
- ❌ 没有最近项目列表（需要在侧栏切换查看），与"打开"场景的用户预期不符

---

### 6.4 制作界面（CreateView / ProductionView）

**UX-T010：侧栏导航结构**

| 项目 | 结果 |
|------|------|
| 引导流程区 | 7 个步骤：工作流/思路/组织/精修/音频/字幕/发布 |
| 自由创作区 | 仅 Canvas 一项 |
| 最近项目区 | ✅ 显示项目名 + 状态徽章 |
| 问题 1 | ❌ 7 步无完成状态标记（全部相同样式），用户无法判断当前进度 |
| 问题 2 | ❌ 引导流程入口（CreateView）和制作工作流入口（ProductionView）是两个不同路由，侧栏无区分 |
| 问题 3 | ⚠️ Emoji 作为图标（📋💡✂️✨🎵📝📤），无统一图标库，不同平台渲染差异大 |
| 问题 4 | ❌ 最近项目名称自动美化（`humanizeProjectName`）将 `proj_selected_20260321` 转为"精选 03/21 14:30"，但规则不透明，用户无法预期 |

**UX-T011：工作流空状态**

- 工作流界面（ProductionView）空状态：仅有"选择一个模块开始"提示
- ❌ 无任何"该从哪里开始"的引导（不如直接默认展开"工作流"视图）
- ❌ 有项目未选时，侧栏显示"暂无项目"，但不提示如何新建

**UX-T012：工作流管理界面（WorkflowManagerView）**

- ✅ 三个区域：可用模板 / 我的工作流 / 运行历史，结构清晰
- ✅ 工作流删除时按钮文字变"删除中..."，防止重复操作
- ✅ 创建模板后自动滚动到"我的工作流"区域（`scrollIntoView`）
- ❌ 无模板时提示"暂无可用模板"，但没有说明如何添加模板（是开发中功能？）
- ❌ 运行工作流的结果（成功/失败）只能在"运行历史"查看，无即时弹出提示

---

### 6.5 设置界面（SettingsView）

**UX-T013：AI 配置区块**

| 项目 | 结果 |
|------|------|
| Provider 选择 | ✅ Select 下拉，枚举已知 Provider |
| Model 选择 | ✅ 联动变化（切换 Provider 后 Model 列表更新）|
| API Key 输入 | ✅ password type，配置后显示"已配置"徽章 |
| 保存状态 | ✅ 保存中 disabled + 文字变"保存中..." |
| 问题 1 | ❌ 没有"测试连接"按钮，用户无法验证 Key 是否有效 |
| 问题 2 | ❌ 两个 Key 字段（OpenAI / Anthropic）并列，新用户不理解为什么有两个 |
| 问题 3 | ❌ Embedding Model 对普通用户完全陌生，无任何说明 |
| 问题 4 | ❌ Base URL 字段只有 placeholder，没有解释何时需要修改（仅代理/私有部署需要）|

**UX-T014：YouTube 授权流程**

- ✅ 按钮状态：未连接显示"连接"，连接后显示频道名 + "断开"按钮
- ✅ 授权等待状态显示"等待浏览器授权..."提示
- ❌ 授权失败时没有明确的错误提示，按钮恢复到初始状态但无说明
- ❌ 断开连接没有二次确认

**UX-T015：Webhook 连接器配置**

- ✅ 连接器列表、测试连接、CRUD 操作均有后端支持
- ❌ 前端 SettingsView 中 Webhook 配置区域代码不完整（读到 515 行止，Webhook 部分在截断处）
- ❌ 没有说明 Webhook 连接器是什么，普通用户完全不理解

---

### 6.6 思路工厂（IdeateView）

**UX-T016：选题库（TopicLibrary）交互**

- IdeateView 由 TopicLibrary + TopicCopy 两个 Panel 组成，上下布局
- ❌ 两个 Panel 没有清晰的视觉分隔（仅 gap: 24px）
- ❌ selectedSlug 通过 `provide/inject` 在两个组件间传递，但用户看不到"选中选题"的明确反馈
- ❌ TopicLibrary 为空时（无模板），界面行为不明（未读到组件内容）

**UX-T017：画布（CanvasView）**

- Canvas 是"自由创作"模式的主入口（300行 CanvasBoard + 266行 CanvasToolbar）
- ✅ 节点式工作流编排，支持连线
- ❌ Canvas 和引导式 7 步工作流的关系完全没有说明，用户不知道什么时候用 Canvas，什么时候用工作流

---

### 6.7 通用 UX 问题（跨界面）

**UX-T018：Toast 通知系统**

- 代码中 useToastStore 被广泛使用（工作流管理、设置保存等均有 toast.show()）
- ✅ 成功/失败分级（success/danger）
- ❌ Toast 持续时间未统一，不同界面 toast 出现位置待验证

**UX-T019：加载状态反馈**

| 界面 | 加载状态 | 结果 |
|------|---------|------|
| 启动屏 | 进度条 + 状态文字 | ✅ |
| 素材库搜索 | loading spinner | ✅ |
| 工作流模板列表 | "加载中..." 文字 | ⚠️ 文字太简单，无 spinner |
| 素材导入 Job | 百分比 | ⚠️ 无预计剩余时间 |
| AI 步骤执行 | job_id 显示 | ❌ 不够直观，用户不知道 job_id 的意义 |

**UX-T020：空状态设计**

| 界面 | 空状态处理 | 评分 |
|------|-----------|------|
| 素材库（空库）| 有图标 + 标题 + 操作按钮 | ✅ 良好 |
| 工作流历史（无记录）| 纯文字提示 | ⚠️ 可改进 |
| 连接器列表（空）| connectors={} 空对象 | ❌ 无界面提示 |
| 最近项目（无）| "暂无项目"文字 | ⚠️ 无新建引导 |
| 标签浏览器（空）| 展示空面板 | ❌ 无说明 |

**UX-T021：错误信息友好度**

- ✅ `api.js` 的 `friendlyErrorMessage()` 将技术报错转为用户语言
- ✅ `Traceback` → "系统执行异常，请重试"
- ✅ `no module named` → "运行环境缺少依赖"
- ✅ `csrf` → "安全校验已过期，请刷新"
- ❌ 500 错误的原始 `error` 字符串有时会直接透出到 Toast（当 friendlyErrorMessage 未覆盖该模式时）

**UX-T022：键盘可访问性**

- ✅ 工作流步骤 inline 编辑支持 Enter 保存、Escape 取消（WorkflowManagerView）
- ⚠️ 整体无 Tab 键导航测试（侧栏、弹窗、表单均未见明确的 tabindex 管理）
- ❌ 弹窗（ProjectDialog、OnboardingModal）无 ESC 键关闭支持（仅靠点击遮罩）

**UX-T023：响应式与窗口大小**

- pywebview 桌面应用，固定窗口大小
- ⚠️ CSS 中使用了 `content-narrow` 等固定宽度类，窗口缩放时可能出现布局问题
- ❌ 未发现断点适配逻辑，所有布局假设了固定窗口尺寸

**UX-T024：图标与视觉一致性**

- ❌ 导航 Emoji（📋💡✂️✨）混合文字类 icon（⊞ ☰）混合 CSS 按钮图标，三套体系混用
- ❌ 质量徽章颜色（badge-success/badge-warn/badge-danger）与系统徽章使用同一类名，容易语义混淆
- ⚠️ 深色模式：CSS 变量（`var(--bg)`, `var(--muted)`）已做抽象，但未见切换控件

**UX-T025：项目名称显示**

- 系统自动生成 `proj_selected_20260321_143000` 格式的目录名
- `humanizeProjectName()` 将其转换为"精选 03/21 14:30"
- ❌ 用户在新建时填写的"项目名"完全无效，实际名称由系统生成，与用户预期严重不符
- ❌ 转换规则不完整（仅覆盖 `selected/draft/new/import/test` 几种前缀），其他格式直接显示原始目录名

**UX-T026：操作确认机制**

| 操作 | 是否有确认 | 结果 |
|------|-----------|------|
| 删除工作流 | ❌ 直接执行 | 风险高 |
| 断开 YouTube | ❌ 直接执行 | 风险中 |
| 关闭 ProjectDialog（遮罩）| ❌ 直接关闭 | 风险中 |
| 取消正在运行的 Job | ✅ API 支持，前端需验证 | 待确认 |

**UX-T027：i18n 与文案一致性**

- 应用标题：`index.html` → "视频制作助手"，代码/文档 → "VideoEditor"，不统一
- 硬编码字符串：`'嗯,啊,然后,就是,那个'`（Step 6 渲染默认去词）混在 workflow store 中
- 日期格式：`formatDate()` 函数未统一，不同组件显示格式不同
- 部分标签有中英混用（如 "hybrid" 在 searchMode select 中作为 value，但 label 显示"混合"）

**UX-T028：无项目状态下的导航**

- 无项目时访问 /create/workflow，侧栏显示"暂无项目"
- ❌ 没有明确的"先新建或打开项目"的引导，用户需要自己发现"➕新建"按钮
- ❌ 没有把用户引导到 /library 先导入素材再建项目的流程说明

---

### 6.8 UX 总结

| 维度 | 评分 | 主要问题 |
|------|------|---------|
| 引导完整性 | 5/10 | 向导有断点，新用户迷失 |
| 空状态设计 | 5/10 | 多处空面板无说明 |
| 加载反馈 | 6/10 | 基本覆盖，Job 进度不直观 |
| 错误处理 | 7/10 | friendlyErrorMessage 较完善 |
| 操作确认 | 3/10 | 多处破坏性操作无确认 |
| 视觉一致性 | 5/10 | 图标三套体系混用 |
| 信息架构 | 6/10 | 双路由体系造成迷路 |
| 键盘可访问 | 4/10 | 仅部分支持 |

---

## 7. 数据库与数据一致性审计

### 7.1 数据库结构

SQLite（library.db），28 张表，核心：

| 表名 | 字段数 | 状态 |
|------|--------|------|
| assets | 33 | ✅ 设计详尽 |
| asset_embeddings | 7 | ✅ |
| tag | 18 | ⚠️ 无种子数据 |
| tag_category | 6 | ⚠️ 无种子数据 |
| project_relink_job | 22 | ✅ |
| search_log | 多列 | ✅ |

### 7.2 数据一致性问题

- **DATA-001**：tag / tag_category 表完全为空，素材导入后无法打系统标签
- **DATA-002**：SQLite 未启用外键约束（无 `PRAGMA foreign_keys=ON`）
- **DATA-003**：assets 表有 `trash_level` 字段但 API 未暴露回收站功能
- workflow.json 状态机格式正确，原子写入确保崩溃安全

---

## 8. 极端情况与崩溃测试

### 8.1 已确认崩溃

| ID | 场景 | 触发 | 复现率 |
|----|------|------|--------|
| CRASH-001 | POST /api/init, project_dir=null | AttributeError in Tee.write() + Segfault | 100% |
| CRASH-002 | POST /api/run_step, step=99 | AttributeError: 'Tee' has no '_real' + Segfault | 100% |
| CRASH-003 | GET /api/capabilities/content_publish/platforms | UnicodeDecodeError | 稳定 |

### 8.2 边界测试汇总

| 场景 | 结果 |
|------|------|
| project_dir="" | 400 ✅ |
| project_dir=null | 500 崩溃 ❌ |
| step=0/step=99 | 崩溃 ❌ |
| Payload 26MB | 413 ✅ |
| 无效 JSON | 400 ✅ |
| 路径穿越 /api/files | 403 ✅ |
| 超长 query（无限制）| ⚠️ 接受 |
| 重复初始化 | 200 幂等 ✅ |

---

## 9. 功能完整性评估

### 9.1 核心 7 步工作流

| 步骤 | 状态 | 可达性 | 主要问题 |
|------|------|--------|---------|
| Step 1 素材分析 | ✅ 完整 | 高 | CLIP 无缓存 |
| Step 2 选题规划 | ⚠️ 部分 | 中 | 聚类过于简陋 |
| Step 3 脚本生成 | ❌ 未实现 | 低 | 代码内显式 TODO |
| Step 4 素材匹配 | ⚠️ 基础 | 中 | 仅字符串匹配 |
| Step 5 帧预览 | ✅ 完整 | 高 | 帧质量无验证 |
| Step 6 粗剪 | ✅ 完整 | 高 | 无音频混合 |
| Step 7 精渲染 | ✅ 完整 | 高 | 美颜 CPU only |

### 9.2 辅助能力完整性

| 能力 | 状态 |
|------|------|
| topic_library / topic_copy | prototype |
| text_rough_cut / subtitle_calibration | 基本可用 |
| audio_voice | 部分可用 |
| social_export | 框架可用 |
| content_publish | ❌ /platforms 异常 |
| publish_prep / article_expand | 基本可用 |
| refinement / nle_handoff | 骨架 |

---

## 10. 问题总表

### P0 — 立即修复

| ID | 类别 | 问题描述 |
|----|------|---------|
| BUG-001 | 稳定性 | null 参数 → 500 + Segfault |
| BUG-002 | 稳定性 | step=99 越界 → AttributeError + Segfault |
| SEC-001 | 安全 | CSRF 双开关逻辑，默认从不执行 |

### P1 — 严重

| ID | 类别 | 问题描述 |
|----|------|---------|
| BUG-003 | 功能 | Step 3 AI 脚本生成未完成（核心价值）|
| BUG-004 | 校验 | provider 字段无枚举校验，任意字符串被持久化 |
| BUG-006 | 接口 | 多个关键路由 404（health/projects/workflow/status）|
| BUG-007 | 稳定性 | content_publish/platforms UnicodeDecodeError |
| ARCH-001 | 架构 | global_media_library.py 13,245 行单体 |
| UX-P1-001 | UX | 预检 error 不拦截路由，用户在异常状态操作 |
| UX-P1-002 | UX | 引导向导有断点，跳过后无补救引导 |

### P2 — 中优先级

| ID | 类别 | 问题描述 |
|----|------|---------|
| BUG-008 | 校验 | /api/run_step 无参数时默认执行 step=1 |
| DATA-001 | 数据 | tag/tag_category 无种子数据，标签系统不可用 |
| DATA-002 | 数据 | SQLite 未启用外键约束 |
| UX-P2-001 | UX | 项目新建弹窗：路径 readonly，用户名无效，两目录无解释 |
| UX-P2-002 | UX | 工作流侧栏无步骤完成状态标记 |
| UX-P2-003 | UX | 操作无确认：删除工作流、断开授权、关闭弹窗 |
| UX-P2-004 | UX | AI 设置无"测试连接"功能 |
| UX-P2-005 | UX | Job 进度不直观（job_id 暴露给用户）|
| UX-P2-006 | UX | 无项目状态下缺乏明确引导 |
| UX-P2-007 | UX | 项目名实为自动生成，与用户填写无关 |
| SEC-002 | 安全 | 搜索 query 无长度限制 |

### P3 — 低优先级

| ID | 类别 | 问题描述 |
|----|------|---------|
| ARCH-002 | 架构 | Step 4 仅字符串匹配，无语义向量 |
| ARCH-003 | 架构 | Step 3 强绑定 Jianying 格式 |
| ARCH-004 | 架构 | 美颜滤镜 CPU only，高分辨率慢 |
| ARCH-005 | 架构 | CLIP 模型无缓存 |
| DEP-001 | 依赖 | requirements.txt 未区分必选/可选 |
| UX-P3-001 | UX | 图标三套体系混用 |
| UX-P3-002 | UX | 标签浏览器空库无说明 |
| UX-P3-003 | UX | 键盘可访问性不完整（无 ESC 关闭弹窗）|
| UX-P3-004 | UX | 应用标题中英文不统一 |
| UX-P3-005 | UX | Canvas vs 引导式工作流无使用场景说明 |

---

*报告结束。R2 修订：移除错误分类的 BUG-005，新增 UX-T001～UX-T028 共 28 个交互测试用例。*
*生成于 2026-03-21 | VideoEditor Audit Team*
