# VideoEditor 版本开发计划（v0.11.0）

**文档版本：** V5.0（全部待确认项已解决，无阻塞）
**日期：** 2026-03-21
**基线 Commit：** c410ba7 (upgrade: stage 7 - E2E verification passed)
**基线 VERSION：** 0.10.0
**计划依据：** 2026-03-21 全面审计报告 R2（AUDIT-2026-0321-R2）
**UI 规范依据：** `docs/VideoEditor-Design-System-v1.0.html`
**文案占位清单：** `project/docs/copy-placeholders.md`

> **V5.0 说明**：所有待确认项已全部解决（UI 规范 + 文案占位 + 代码读取 + 产品授权）。
> **无任何阻塞项，所有 R 任务可按顺序立即执行。**

---

## 1. 版本目标

消除 v0.10.0 全面审计（R2）发现的所有问题，实现「审计清零」：包括 P0 稳定性崩溃、安全防护默认失效、P1 接口断链与功能缺失、全部 P2/P3 UX 问题、数据完整性与依赖管理、视觉一致性，以及 Library 单体模块拆分。

---

## 2. 版本范围

### 包含的需求

| 优先级 | 问题 ID | 描述 |
|--------|---------|------|
| P0 | BUG-001 | `null` 参数传入 `/api/init` → 500 + Segfault |
| P0 | BUG-002 | `step=99` 越界 `/api/run_step` → AttributeError + Segfault |
| P0 | SEC-001 | CSRF 双开关逻辑缺陷，默认从不执行 |
| P1 | BUG-003 | Step 3 AI 脚本生成未实现（代码内显式 TODO）|
| P1 | BUG-004 | `provider` 字段无枚举校验，任意字符串被持久化 |
| P1 | BUG-006 | 多个关键路由 404（health / projects / workflow/status / settings）|
| P1 | BUG-007 | `content_publish/platforms` UnicodeDecodeError |
| P1 | BUG-008 | `/api/run_step` 无参数默认执行 step=1，无防御 |
| P1 | ARCH-001 | global_media_library.py 13,245 行单体文件 |
| P1 | UX-P1-001 | 预检 error 后无路由守卫，用户可在异常状态操作 |
| P1 | UX-P1-002 | 引导向导有断点，跳过后无补救引导 |
| P2 | DATA-001 | tag / tag_category 表无种子数据，标签系统不可用 |
| P2 | DATA-002 | SQLite 未启用外键约束 |
| P2 | DEP-001 | requirements.txt 未区分必选/可选 |
| P2 | SEC-002 | 搜索 query 无长度限制 |
| P2 | UX-P2-001 | 项目新建弹窗：路径 readonly / 两目录无解释 / 项目名无效 |
| P2 | UX-P2-002 | 工作流侧栏无步骤完成状态标记 |
| P2 | UX-P2-003 | 破坏性操作无二次确认（删除工作流、断开 YouTube）|
| P2 | UX-P2-004 | AI 设置无"测试连接"功能 |
| P2 | UX-P2-005 | Job 进度不直观（job_id 暴露给用户）|
| P2 | UX-P2-006 | 无项目状态下缺乏明确新建引导 |
| P2 | UX-P2-007 | 用户填写项目名后系统自动覆盖，用户无感知 |
| P3 | UX-P3-001 | 图标三套体系混用（Emoji / 文字 / CSS）|
| P3 | UX-P3-002 | 标签浏览器空库无说明文字 |
| P3 | UX-P3-003 | 弹窗无 ESC 键关闭支持 |
| P3 | UX-P3-004 | 应用标题中英文不统一 |
| P3 | UX-P3-005 | Canvas vs 引导式工作流无使用场景说明 |

### 不包含的需求（Future）

无。本版本目标为全量审计清零。

---

## 3. 任务列表

| 任务ID | 任务名称 | 所属模块 | 目标版本 | 状态 | 优先级 |
|--------|---------|---------|---------|------|--------|
| R1 | 两处 Segfault 修复 | app_api / job_runtime | v0.11.0 | Done | P0 |
| R2 | 安全修复（CSRF + 枚举校验 + query 长度）| app_api / middleware | v0.11.0 | Done | P0 |
| R3 | 接口补全与编码修复 | app_api / routes | v0.11.0 | Done | P1 |
| R4 | UX 引导体验修复（预检守卫 + 向导断点）| vue_ui | v0.11.0 | Done | P1 |
| R5 | 项目弹窗优化与项目名生效 | vue_ui / app_api | v0.11.0 | Done | P2 |
| R6 | 操作确认机制 + AI 测试连接 | vue_ui / app_api | v0.11.0 | Done | P2 |
| R7 | Job 进度 + 无项目引导 + 标签种子数据 | vue_ui / app_api / library | v0.11.0 | Planned | P2 |
| R8 | Step 3 AI 脚本生成实现 | step3_script_generation | v0.11.0 | Planned | P1 |
| R9 | 数据库外键约束 + 依赖分层 | library / 工程配置 | v0.11.0 | Planned | P2 |
| R10 | 视觉一致性修复（图标 + 空状态 + ESC + 标题 + Canvas 说明）| vue_ui | v0.11.0 | Planned | P3 |
| R11 | Library 模块拆分 | library | v0.11.0 | Planned | P1 |

---

## 4. 各任务详细定义

---

### R1：两处 Segfault 修复

**目标：**
修复 `POST /api/init` 传入 null 参数和 `POST /api/run_step` 传入越界 step 值时触发的 100% 必现 Segfault，消除进程级崩溃。

**根本原因（已确认）：**
1. `project_dir=null` → `Path(None)` 触发 TypeError → Flask 500，但 `Tee` 对象在异常清理阶段调用 `._real.write()` 时 `_real` 已失效 → AttributeError → Segfault（BUG-001）
2. `step=99` 越界 → `Tee` 对象内部步骤索引越界访问 → AttributeError → Segfault（BUG-002）

**涉及文件：**
- `modules/app_api/routes/workflow_routes.py` — 修改：在 `/api/init` handler 入口对 `project_dir` 做显式 null 检查
- `modules/app_api/routes/step_routes.py` — 修改：在 `/api/run_step` handler 入口对 `step` 做范围校验（合法范围 1-7）
- `modules/app_api/services/job_runtime.py` — 修改：`Tee` 类的 `write()` 方法和 `__del__` 方法增加 `hasattr` 检查及 try/except 防御

**输入：**
- `POST /api/init`：`{ "videos_dir": string, "project_dir": string | null }`
- `POST /api/run_step`：`{ "step": integer }`

**输出：**
- 修复后：非法输入返回 400 `{ "error": "..." }`，进程不崩溃
- 正常输入：行为与修复前相同

**验收标准：**
- [ ] `POST /api/init {"project_dir": null}` → HTTP 400，响应含明确错误信息，进程不崩溃
- [ ] `POST /api/init {"project_dir": ""}` → 原有 400 逻辑不受影响
- [ ] `POST /api/run_step {"step": 99}` → HTTP 400，进程不崩溃
- [ ] `POST /api/run_step {"step": 0}` → HTTP 400，进程不崩溃
- [ ] `POST /api/run_step {"step": -1}` → HTTP 400，进程不崩溃
- [ ] 回归：正常 `POST /api/init` 流程（有效路径）返回 200，行为不变
- [ ] 回归：正常 `POST /api/run_step {"step": 1}` 返回预期结果，行为不变
- [ ] 全量回归测试通过：`pytest tests/ -v`

**依赖项：**
- 无

**已知约束：**
- `Tee` 的防御代码不能改变正常日志写入的逻辑和输出
- step 合法范围定为 1-7，若未来步骤增加，需同步更新校验边界（记录到 WISHLIST.md）

---

### R2：安全修复（CSRF + provider 枚举校验 + query 长度限制）

**目标：**
修复默认失效的 CSRF 保护，防止任意 provider 字符串写入数据库，限制搜索 query 长度。

**根本原因（已确认）：**
- `enforce_csrf = bool(req_csrf and req_token)` — `req_token`（对应环境变量 `VIDEOEDITOR_REQUIRE_LOCAL_TOKEN`）默认为 `False`，导致 CSRF 永不执行，即使 `REQUIRE_CSRF_PROTECTION=True`（SEC-001）
- `/api/settings/ai` 的 `provider` 字段直接写入，无枚举校验（BUG-004）
- 搜索 `query` 参数无最大长度限制（SEC-002）

**涉及文件：**
- `modules/app_api/middleware/security.py` — 修改：CSRF 逻辑解耦，`enforce_csrf` 不再依赖 token 开关
- `modules/app_api/routes/settings_routes.py` — 修改：`POST /api/settings/ai` 增加 `provider` 枚举校验
- `modules/app_api/routes/library_routes.py` — 修改：搜索接口 `query` 参数增加长度校验

**输入：**
- 跨域 POST 请求（含 `Origin: http://evil.com`）
- `POST /api/settings/ai`：`{ "provider": string, ... }`
- 搜索请求：`query=<超长字符串>`

**输出：**
- CSRF 修复后：跨域请求返回 403
- provider 校验：非法值返回 400 `{"error": "provider 不合法，合法值为：openai / anthropic / moonshot / qwen / gemini / maxmini"}`
- query 长度限制：超限返回 400 `{"error": "query 长度超出限制（最大 500 字符）"}`

**验收标准：**
- [ ] `POST /api/settings/ai` 携带 `Origin: http://evil.com` → HTTP 403
- [ ] 同源正常 POST → HTTP 200，功能不受影响
- [ ] `POST /api/settings/ai {"provider": "unknown_xyz"}` → HTTP 400，错误信息含 6 个合法值
- [ ] `POST /api/settings/ai {"provider": "openai"}` → HTTP 200
- [ ] `POST /api/settings/ai {"provider": "moonshot"}` → HTTP 200（moonshot 是合法值）
- [ ] 搜索 query 超出 500 字符 → HTTP 400
- [ ] 搜索 query ≤ 500 字符 → 正常返回，不受影响
- [ ] Bootstrap 握手（前端初始化）流程不受 CSRF 修改影响
- [ ] 全量回归测试通过

**依赖项：**
- R1 完成后再执行（稳定的进程是安全测试的前提）

**已知约束：**
- **已解决 Q1**：`provider` 合法枚举值从 `_AI_PROVIDER_CATALOG` 读取，固定为：`openai`、`anthropic`、`moonshot`（alias: kimi）、`qwen`、`gemini`、`maxmini`（alias: minimax）
- **已解决**：query 最大长度定为 **500 字符**
- CSRF 修复必须保留 token 认证逻辑的独立分支（两者不互相影响）

---

### R3：接口补全与编码修复

**目标：**
补全前端依赖但不存在的关键路由，修复响应编码异常，防止 run_step 无参数时默认执行。

**问题清单（已确认）：**
- `GET /api/system/health` — 404（BUG-006）
- `GET /api/projects` — 404（BUG-006）
- `GET /api/workflow/status` — 404，前端 workflow store 调用此路由导致 `guidedAvailable=false`（BUG-006）
- `GET /api/settings` — 404（BUG-006）
- `GET /api/capabilities/content_publish/platforms` — UnicodeDecodeError（BUG-007）
- `POST /api/run_step {}` — 默认执行 step=1 无防御（BUG-008，R1 已加范围校验，此处补必填校验）

**涉及文件：**
- `modules/app_api/routes/system_routes.py` — 修改：新增 `GET /api/system/health`
- `modules/app_api/routes/project_routes.py` — 修改/新增：新增 `GET /api/projects`、`GET /api/workflow/status`
- `modules/app_api/routes/settings_routes.py` — 修改：新增 `GET /api/settings`（聚合）
- `modules/app_api/routes/capabilities_routes.py` — 修改：修复 content_publish/platforms 响应编码
- `modules/app_api/routes/step_routes.py` — 修改：无 `step` 参数时返回 400

**输入：**
- `GET /api/system/health`：无参数
- `GET /api/projects`：无参数
- `GET /api/workflow/status`：无参数
- `GET /api/settings`：无参数
- `GET /api/capabilities/content_publish/platforms`：无参数
- `POST /api/run_step`：`{}` 或缺少 `step` 字段

**输出（已确认字段结构）：**
- `GET /api/system/health` → `{"status": "ok", "version": "0.11.0"}`
- `GET /api/projects` → `{"projects": [{"project_id", "name", "project_dir", "videos_dir", "created_at", "updated_at", "workflow_count"}], "count": N}`
- `GET /api/workflow/status` → `{"persisted": bool, "current_run_id": string|null, "status": "idle"|"running"|"error", "current_step": int|null, "guidedAvailable": bool}`
- `GET /api/settings` → `{"ai": {"provider", "model", "api_key": "****xxxx"}, "ui": {...}}`（api_key 用 `_mask_secret()` 脱敏）
- `GET /api/capabilities/content_publish/platforms` → 正确编码的 JSON，Content-Type: application/json; charset=utf-8
- `POST /api/run_step {}` → HTTP 400 `{"error": "step 参数不能为空"}`

**验收标准：**
- [ ] `GET /api/system/health` → HTTP 200，含 status 和 version 字段
- [ ] `GET /api/projects` → HTTP 200，返回含 project_id / name / project_dir / videos_dir / created_at / updated_at / workflow_count 的项目数组
- [ ] `GET /api/workflow/status` → HTTP 200，含 persisted / current_run_id / status / current_step / guidedAvailable 字段
- [ ] `GET /api/workflow/status` 返回后，前端 workflow store 的 `guidedAvailable` 不再强制为 false
- [ ] `GET /api/settings` → HTTP 200，ai.api_key 已脱敏（`****xxxx` 格式），不暴露完整 Key
- [ ] `GET /api/capabilities/content_publish/platforms` → HTTP 200，无 UnicodeDecodeError，Content-Type 含 charset=utf-8
- [ ] `POST /api/run_step {}` → HTTP 400，含明确错误信息
- [ ] 全量回归测试通过

**依赖项：**
- R1、R2 完成后再执行

**已知约束：**
- **已解决 Q3**：`GET /api/projects` 响应字段：project_id / name / project_dir / videos_dir / created_at / updated_at / workflow_count
- **已解决 Q4**：`GET /api/workflow/status` 字段：persisted / current_run_id / status / current_step / guidedAvailable（不暴露原始 workflow.json）
- **已解决 Q5**：`GET /api/settings` 聚合 ai + ui；api_key 用现有 `_mask_secret()` 处理
- 新增路由必须注册到对应 Blueprint，不能新建新的 Blueprint 文件

---

### R4：UX 引导体验修复（预检路由守卫 + 向导断点补救）

**目标：**
修复新用户首次使用时两处关键路径断点：预检 error 后可绕过进主界面；向导跳过后无任何补救引导。

**问题（已确认）：**
- UX-P1-001：StartupView.vue 预检 3 项 error 后无路由守卫，用户可手动导航至主界面在异常状态下操作
- UX-P1-002：OnboardingModal.vue 向导跳过后 `onboarding_completed=true`，再次打开应用无任何补救引导

**涉及文件：**
- `apps/desktop/ui-vue/src/views/StartupView.vue` — 修改：预检有 error 时添加拦截提示
- `apps/desktop/ui-vue/src/router/index.js` — 修改：添加路由守卫逻辑
- `apps/desktop/ui-vue/src/stores/app.js` — 修改：新增 `preflight_acknowledged` 状态字段
- `apps/desktop/ui-vue/src/components/common/OnboardingModal.vue` — 修改：向导跳过后的补救引导

**输入：**
- 预检接口响应（含 error 项）
- 用户导航行为（路由变化）
- 向导完成/跳过状态 + 素材库资产数量

**输出：**
- 预检有 error 时：导航被软拦截，显示 `modal-confirm` 对话框（含"了解风险，继续进入"和"返回检查"按钮）
- 用户确认后：允许进入，顶部显示持续警告横幅（`COPY-005`）
- 向导跳过 + 素材库为空：显示 `empty-state` 补救引导区块（`COPY-006~008`）

**验收标准：**
- [ ] 模拟预检返回 error：从 StartupView 导航到 `/create/workflow` 时出现 `modal-confirm` 弹窗，包含 error 列表（文案见 COPY-001~004）
- [ ] 用户点击"了解风险，继续进入"：允许进入主界面，`preflight_acknowledged=true` 写入 store
- [ ] 用户点击"返回检查"：停留在 StartupView
- [ ] 用户进入主界面后：顶部显示警告横幅（文案见 COPY-005）
- [ ] 向导跳过 + `library.asset_count === 0`：界面上显示 `empty-state` 补救引导区块（文案见 COPY-006~008）
- [ ] 向导跳过 + 素材库有内容（`asset_count > 0`）：不显示补救引导（避免干扰老用户）
- [ ] 已正常完成向导（非跳过）的用户：不受影响
- [ ] 预检全部通过时：无任何拦截，行为与原来相同
- [ ] 全量回归测试通过

**依赖项：**
- R3 完成后再执行（`/api/projects` 和 `workflow/status` 路由补全后，前端 store 初始化才正确）

**已知约束：**
- **已解决（UI 规范）**：预检 error 拦截策略为**软提示 + 确认**（`modal-confirm` 组件），不硬拦截；用户确认后进入主界面，顶部持续显示警告横幅。依 Design System Principle 6 容错设计原则。文案见 `copy-placeholders.md` COPY-001~005
- **已解决（UI 规范 + 文案）**：向导跳过后的补救引导使用 `empty-state` 组件（空状态区块）。文案见 `copy-placeholders.md` COPY-006~008
- `preflight_acknowledged` 状态仅存 session 级别（不持久化），用户下次启动重新评估

---

### R5：项目弹窗优化与项目名生效

**目标：**
修复 ProjectDialog 中三处误导性交互，并使用户填写的项目名真正影响显示名称。

**问题（已确认）：**
- UX-P2-001：路径输入框 readonly，高级用户无法手动输入；两目录用途无解释；项目名输入框无说明会被覆盖
- UX-P2-007：用户填写的项目名被系统自动生成的目录名（`proj_xxx_yyyymmdd`）覆盖，ProductionView 显示与预期不符

**涉及文件：**
- `apps/desktop/ui-vue/src/components/common/ProjectDialog.vue` — 修改：三处交互改进
- `modules/app_api/routes/workflow_routes.py` — 修改：保存 `project_display_name` 到 workflow.json
- `apps/desktop/ui-vue/src/views/ProductionView.vue` — 修改：优先读取 `project_display_name`

**输入：**
- `POST /api/init`：新增 `project_name` 字段（可选，string）
- `workflow.json`：新增 `project_display_name` 字段

**输出：**
- ProjectDialog：用户看到的两路径框有说明文字；可手动输入路径；项目名框有提示文字
- `workflow.json`：持久化 `project_display_name`
- ProductionView：侧栏显示用户填写的名称（若有）；无填写时回退 `humanizeProjectName()`

**验收标准：**
- [ ] ProjectDialog 中"素材目录"输入框下方有说明文字（文案见 `copy-placeholders.md` COPY-009）
- [ ] ProjectDialog 中"项目保存位置"输入框下方有说明文字（文案见 `copy-placeholders.md` COPY-010）
- [ ] 两路径输入框去掉 `readonly`，支持用户手动粘贴路径（文件选择器按钮保留）
- [ ] "项目名称"输入框下方有说明文字（文案见 `copy-placeholders.md` COPY-011）
- [ ] 用户填写项目名"我的旅行视频"提交后，workflow.json 中 `project_display_name = "我的旅行视频"`
- [ ] ProductionView 侧栏显示"我的旅行视频"
- [ ] 用户未填写项目名时，ProductionView 回退到 `humanizeProjectName()` 逻辑（行为不变）
- [ ] 旧项目（无 `project_display_name` 字段）打开时，不报错，回退正常
- [ ] 全量回归测试通过

**依赖项：**
- R4 完成后再执行

**已知约束：**
- `workflow.json` 新增 `project_display_name` 字段必须向后兼容（旧文件不含此字段时，前端和后端均不报错）
- 不修改目录实际命名规则（`proj_xxx_yyyymmdd` 格式保持不变），仅增加显示层字段
- **已解决（文案）**：三处说明文字见 `copy-placeholders.md` COPY-009~011，开发直接使用占位文案

---

### R6：操作确认机制 + AI 测试连接

**目标：**
为关键破坏性操作添加二次确认；为 AI 配置页新增连通性测试能力。

**问题（已确认）：**
- UX-P2-003：删除工作流、断开 YouTube 授权、填写中关闭弹窗均直接执行，无任何确认
- UX-P2-004：AI Key 配置后无"测试连接"按钮，用户不知道 Key 是否有效

**涉及文件：**
- `apps/desktop/ui-vue/src/views/WorkflowManagerView.vue` — 修改：删除工作流加确认
- `apps/desktop/ui-vue/src/views/SettingsView.vue` — 修改：断开 YouTube 加确认；新增"测试连接"按钮
- `apps/desktop/ui-vue/src/components/common/ProjectDialog.vue` — 修改：填写中关闭加确认
- `modules/app_api/routes/settings_routes.py` — 新增：`POST /api/settings/ai/test` 路由

**输入：**
- 用户点击"删除工作流"
- 用户点击"断开 YouTube"
- 用户点击 ProjectDialog 遮罩（表单已有内容时）
- `POST /api/settings/ai/test`：无参数（使用当前已保存的 AI 配置）

**输出：**
- 删除/断开：操作前出现 `modal-danger` 确认对话框，用户确认后才执行
- 关闭弹窗：表单有内容时出现 `modal-confirm` 确认提示
- `POST /api/settings/ai/test` → `{"ok": true}` 或 `{"ok": false, "error": "具体错误信息"}`

**验收标准：**
- [ ] 点击"删除工作流" → 出现 `modal-danger` 确认对话框（文案见 `copy-placeholders.md` COPY-012~013）
- [ ] 确认删除后：工作流从列表中移除，CRUD 行为正常
- [ ] 取消删除：无任何变更
- [ ] 点击"断开 YouTube" → 出现 `modal-danger` 确认对话框（文案见 COPY-014）
- [ ] 确认断开后：授权状态重置，按钮变回"连接"
- [ ] ProjectDialog 已有内容时点击遮罩 → 出现 `modal-confirm` 关闭确认提示（文案见 COPY-015）
- [ ] ProjectDialog 空表单时点击遮罩 → 直接关闭（原有行为保留）
- [ ] 点击"测试连接"按钮 → 有 loading 状态（按钮 disabled + 文字变化，文案见 COPY-016）
- [ ] 连接成功 → 显示成功提示（文案见 COPY-017）
- [ ] 连接失败 → 显示具体错误信息（文案见 COPY-018，不暴露 stack trace）
- [ ] 全量回归测试通过

**依赖项：**
- R2 完成后再执行（`/api/settings/ai/test` 属于设置模块，且需要 CSRF 修复在前）

**已知约束：**
- **已解决（UI 规范）**：删除工作流和断开 YouTube 均使用 `modal-danger` 确认对话框（不可逆操作），遮罩关闭使用 `modal-confirm`，依 Design System Principle 6。文案见 `copy-placeholders.md` COPY-012~015
- **已解决（文案）**：测试连接状态文案见 `copy-placeholders.md` COPY-016~018
- `/api/settings/ai/test` 必须有超时控制（建议 30 秒），超时也需返回 `ok: false` 而非让请求挂起
- 测试连接不发送真实业务数据，仅发最小验证请求

---

### R7：Job 进度可视化 + 无项目引导 + 标签种子数据

**目标：**
改善 Job 执行进度的可读性，修复无项目时 CreateView 无引导，补充标签系统的基础数据。

**问题（已确认）：**
- UX-P2-005：Job 运行时界面显示 `job_id`（如 `job_20260321_abc123`），进度只有百分比，无"已处理/总计"数量
- UX-P2-006：无项目时 `/create/workflow` 侧栏显示"暂无项目"但无"新建项目"引导
- DATA-001：`tag` 和 `tag_category` 表为空，素材导入后无法打系统标签，TagBrowser 永远为空

**涉及文件：**
- `modules/app_api/routes/job_routes.py` — 修改：job 状态响应新增 `description`、`processed`、`total` 字段
- `apps/desktop/ui-vue/src/stores/workflow.js` — 修改：Job 状态展示使用 `description` 替代 `job_id`
- `apps/desktop/ui-vue/src/components/library/LibraryPanel.vue`（或对应 Job 进度展示组件）— 修改：展示"已处理 N / M 个文件"
- `apps/desktop/ui-vue/src/views/CreateView.vue` — 修改：无项目状态时显示引导区块
- `modules/library/db/seeds/tag_seeds.py`（新增文件）— 新增：种子数据脚本
- `modules/library/global_media_library.py` — 修改：初始化时检查并幂等填充种子数据

**输入：**
- Job 状态轮询响应（当前返回 `job_id`、`progress` 等字段）
- 素材库初始化事件
- `recentProjects` 列表（来自 app store）

**输出：**
- Job 进度组件：显示友好描述文字（见 COPY-022）+ 进度条 + "已处理 N / M 个文件"（见 COPY-023，N/M 不可用时不显示）
- CreateView 无项目时：显示 `empty-state` 新建引导区块（文案见 COPY-019~021）
- 新数据库初始化后：`tag_category` 和 `tag` 表有基础占位数据（7 个分类，见 COPY-SEED-01~08）

**验收标准：**
- [ ] Job 运行时：界面显示 job `description` 字段内容（若字段存在），而非 job_id
- [ ] Job response 包含 `processed` / `total` 时：界面显示"已处理 N / M 个文件"（文案格式见 COPY-023）
- [ ] `processed` / `total` 字段不存在或为 null 时：进度展示降级为仅显示百分比（不报错）
- [ ] 无项目时访问 `/create/workflow`：显示 `empty-state` 引导区块（文案见 COPY-019~021）
- [ ] 有项目时：不显示新建引导（原有项目列表行为不变）
- [ ] 新初始化数据库：`tag_category` 表有 7 条记录（场景/人物/动作/情绪/构图/色调/画质），`tag` 表有 ≥30 条记录
- [ ] 种子填充幂等：已有数据的数据库执行初始化后，不重复插入
- [ ] 全量回归测试通过

**依赖项：**
- R4 完成后执行（路由和 store 修复完成后，前端状态更可预期）
- 可与 R5、R6 并行推进

**已知约束：**
- **已解决（文案占位）**：标签种子数据分类和标签内容已在 `copy-placeholders.md` COPY-SEED-01~08 中写入占位内容，开发时使用，正式发布前内容运营确认替换
- **已解决（UI 规范 + 文案）**：无项目时的引导区块使用 `empty-state` 组件，文案见 `copy-placeholders.md` COPY-019~021
- **已解决（文案）**：Job 进度描述文案见 `copy-placeholders.md` COPY-022~023
- job_routes 新增的 `processed` / `total` / `description` 字段，需确认现有 Job 运行时能否提供这些数据；若不能，前端需做 null 降级

---

### R8：Step 3 AI 脚本生成实现

**目标：**
实现 7 步工作流中唯一未完成的核心步骤：AI 脚本自动生成（代码内显式 TODO）。

**问题（已确认）：**
- `modules/step3_script_generation/jianying_draft.py` line 466 有显式 `TODO`，脚本生成逻辑未实现
- 缺失导致标准流程中 Step 4-7 无法触达

**涉及文件：**
- `modules/step3_script_generation/jianying_draft.py` — 修改：实现 TODO 处的 AI 调用逻辑
- `modules/step3_script_generation/prompt_templates/`（新增目录）— 新增：脚本生成 prompt 模板文件
- `modules/app_api/routes/step_routes.py` — 修改：Step 3 执行前检查 AI Key 是否已配置
- `apps/desktop/ui-vue/src/views/CreateView.vue`（或对应 Step 3 展示组件）— 修改：AI 未配置时展示引导提示

**输入：**
- Step 2 产出的选题数据（从 `workflow.json` 读取）
- Step 1 产出的素材分析结果（从 `workflow.json` 读取）
- 当前 AI 配置（从设置数据库读取：provider、model、api_key）

**Step 3 脚本输出 JSON 格式（已确认）：**

```json
{
  "title": "视频标题",
  "description": "视频简介",
  "clips": [
    {
      "source_asset_id": "uuid-xxx",
      "start_ms": 0,
      "end_ms": 5000,
      "description": "场景描述"
    }
  ],
  "subtitles": [
    {
      "start_ms": 0,
      "end_ms": 2000,
      "text": "字幕文本"
    }
  ],
  "bgm": {
    "source": "local_library",
    "asset_id": "uuid-yyy",
    "volume": 0.3
  }
}
```

> 此格式从 `jianying_draft.py` 第 466-531 行代码反推，Step 4 通过 `"shot_list": "$paper_cut"` 读取 clips 数据。

**输出：**
- Step 3 执行成功：脚本内容（上述 JSON）写入 `workflow.json` 的 `paper_cut` 字段
- AI Key 未配置：返回 HTTP 400，含明确错误信息

**验收标准：**
- [ ] AI Key 已配置时：Step 3 触发后，Job 正常运行，`workflow.json` 写入符合上述格式的 paper_cut 脚本内容
- [ ] Step 4 可读取 Step 3 产出（`shot_list` 来自 `$paper_cut`），主链路（Step 1 → 2 → 3 → 4）基本可跑通
- [ ] AI Key 未配置时：Step 3 返回 HTTP 400，含"请先在设置中配置 AI Key"提示
- [ ] AI 调用超时（≥30 秒）：Job 标记失败，返回明确错误信息，进程不崩溃
- [ ] AI 返回非预期格式：有错误处理，Job 标记失败，不写入损坏的数据
- [ ] 回归：Step 1/2/4-7 执行路径不受影响
- [ ] 全量回归测试通过

**依赖项：**
- R1-R7 全部完成后再执行（系统稳定为前提）

**已知约束：**
- **已解决 Q12**：Step 3 脚本输出 JSON 格式已从代码反推确认（见上方格式定义），无需额外 PRD
- AI 调用必须有超时控制（30 秒）和重试机制（最多 3 次）
- Prompt 模板放在独立文件，不硬编码在业务逻辑中

---

### R9：数据库外键约束 + 依赖分层

**目标：**
启用 SQLite 外键完整性约束；将 `requirements.txt` 拆分为必选和可选两个文件。

**问题（已确认）：**
- DATA-002：SQLite 连接未执行 `PRAGMA foreign_keys=ON`，孤立记录可能积累
- DEP-001：`requirements.txt` 将 torch（>3GB）与 Flask 等轻量依赖混在一起，新用户安装成功率低

**涉及文件：**
- `modules/library/db/connection.py`（或数据库初始化模块）— 修改：每次建连执行 `PRAGMA foreign_keys=ON`
- `requirements.txt` — 修改：仅保留必选依赖
- `requirements-optional.txt` — 新增：可选 AI 相关依赖
- `project/README.md` — 修改：更新安装说明

**输入：**
- 数据库连接建立事件
- 安装命令执行

**输出：**
- 新连接：`PRAGMA foreign_keys` 返回 1
- `requirements.txt`（必选）：numpy / Pillow / opencv-python / tqdm / ffmpeg-python / requests / Flask / pywebview / python-dotenv
- `requirements-optional.txt`（可选）：torch / torchvision / transformers / sentence-transformers / ftfy / regex / mediapipe / librosa / faster-whisper

**验收标准：**
- [ ] 新建 SQLite 连接后：执行 `PRAGMA foreign_keys` 返回 `1`
- [ ] 现有数据库（已有数据）启用外键约束后：应用正常启动，不崩溃
- [ ] 若现有数据有外键违规：启动时打印警告日志，但不阻断启动（给迁移窗口）
- [ ] `pip install -r requirements.txt` 完成后：Flask 应用可正常启动（无 torch 依赖）
- [ ] `pip install -r requirements-optional.txt` 完成后：AI 功能可正常调用（有 torch 等）
- [ ] README 安装步骤更新，新用户按步骤可成功安装
- [ ] 全量回归测试通过

**依赖项：**
- 可与 R8 并行
- 建议在 R8 前完成（外键约束有助于 Step 3 写入数据时的一致性保障）

**已知约束：**
- **已解决 Q13**：必选/可选分类依据现有 requirements.txt 注释：Flask/numpy/Pillow/opencv/ffmpeg-python/pywebview = 必选；torch/transformers/mediapipe/librosa = 可选
- 外键约束启用不能破坏现有数据读写逻辑；若有违规数据，不强制回滚，记录日志供后续处理

---

### R10：视觉一致性修复（图标 + 空状态 + ESC + 标题 + Canvas 说明）

**目标：**
修复审计发现的 5 项 P3 视觉与交互一致性问题。

**问题（已确认）：**
- UX-P3-001：导航 Emoji / 文字图标 / CSS 按钮图标三套体系混用
- UX-P3-002：TagBrowser 空库时展示空面板，无说明文字
- UX-P3-003：ProjectDialog 和 OnboardingModal 无 ESC 键关闭支持
- UX-P3-004：`index.html` `<title>` 为"视频制作助手"，代码和文档中为"VideoEditor"，不统一
- UX-P3-005：Canvas 入口无使用场景说明，与引导式工作流的关系不明确

**涉及文件：**
- `apps/desktop/ui-vue/src/views/CreateView.vue` — 修改：导航图标统一；Canvas 说明文字
- `apps/desktop/ui-vue/src/components/library/TagBrowser.vue` — 修改：空状态说明文字
- `apps/desktop/ui-vue/src/components/common/ProjectDialog.vue` — 修改：ESC 键关闭
- `apps/desktop/ui-vue/src/components/common/OnboardingModal.vue` — 修改：ESC 键关闭
- `apps/desktop/dist/index.html` 或 Vite 构建模板 — 修改：`<title>` 统一为 `VideoEditor`

**输入：**
- 用户按 ESC 键（在弹窗打开时）
- 素材库为空时的 TagBrowser 渲染
- Canvas 入口展示时机

**输出：**
- 图标风格统一为 Unicode 符号方案（不引入新图标库）
- TagBrowser 空时：显示说明文字（文案见 COPY-024）
- ESC 键：正确关闭弹窗（有内容时走 R6 的确认逻辑）
- `<title>`：统一为 **VideoEditor**
- Canvas 说明文字（文案见 COPY-025）；引导式工作流说明（文案见 COPY-026）

**验收标准：**
- [ ] 侧栏导航图标统一为 Unicode 符号，去除 Emoji 和 CSS 图标混用
- [ ] TagBrowser 空库时显示说明文字（文案见 `copy-placeholders.md` COPY-024）
- [ ] 打开 ProjectDialog 后按 ESC → 弹窗关闭（有内容时弹确认，依 R6 逻辑）
- [ ] 打开 OnboardingModal 后按 ESC → 弹窗关闭
- [ ] 浏览器标签页 `<title>` 显示为 **VideoEditor**
- [ ] Canvas 入口附近有使用场景说明文字（文案见 `copy-placeholders.md` COPY-025~026）
- [ ] 全量回归测试通过

**依赖项：**
- R6 完成后再执行（ESC 键关闭依赖 R6 的确认逻辑）

**已知约束：**
- **已解决（UI 规范）**：UX-P3-001 图标统一方案为 **Unicode 符号方案**，不引入新图标库
- **已解决（文案）**：TagBrowser 空状态、Canvas 说明文字见 `copy-placeholders.md` COPY-024~026
- **已解决 Q15**：品牌名称统一为 **VideoEditor**（与代码/文档/commit 一致），中文说明文字用"视频编辑器"
- ESC 键关闭弹窗不能影响弹窗内部输入框的正常输入行为

---

### R11：Library 模块拆分（ARCH-001）

**目标：**
将 `global_media_library.py`（13,245 行）拆分为职责清晰的子模块，消除单体文件风险，同时对外公共接口**严格不变**。

**问题（已确认）：**
- ARCH-001：13,245 行单文件包含资产入库、语义分析、指纹计算、标签管理、搜索、GDrive 集成、路径重链接、重复检测、学习候选等所有逻辑，任何改动风险极高

**拆分边界设计（已确认）：**

```
modules/library/
├── global_media_library.py      ← 精简为 Facade（仅调度，< 300 行）
├── core/
│   ├── asset_ingestion.py       ← 资产入库
│   ├── asset_search.py          ← 搜索（关键词 + 向量）
│   └── asset_analysis.py        ← 语义分析、CLIP 调用
├── maintenance/
│   ├── duplicate_detection.py   ← 重复检测
│   ├── path_relink.py           ← 路径重链接
│   └── fingerprint.py           ← 指纹计算
├── tagging/
│   ├── tag_manager.py           ← 标签 CRUD
│   └── auto_tagger.py           ← 自动打标
├── integrations/
│   └── gdrive.py                ← Google Drive 集成
└── db/
    ├── connection.py            ← 已有
    └── seeds/                   ← R7 新增
```

**涉及文件：**
- `modules/library/global_media_library.py` — 修改：精简为 Facade，内部调用子模块
- `modules/library/core/*.py` — 新增：从 global_media_library.py 迁移对应逻辑
- `modules/library/maintenance/*.py` — 新增：迁移对应逻辑
- `modules/library/tagging/*.py` — 新增：迁移对应逻辑
- `modules/library/integrations/gdrive.py` — 新增：迁移 GDrive 逻辑
- `tests/library/` — 修改/新增：补充子模块单元测试

**输入：**
- 现有 `global_media_library.py` 的所有公共方法调用（内外部调用不变）

**输出：**
- 拆分后所有现有调用行为**严格一致**
- `global_media_library.py` 行数 < 300

**验收标准：**
- [ ] `global_media_library.py` 行数降至 < 300（仅保留 Facade 调度逻辑）
- [ ] 全量回归测试通过：`pytest tests/ -v`（100% 通过，不新增失败）
- [ ] 所有现有 `import global_media_library` 调用方式不变，无需修改调用代码
- [ ] 所有公共方法签名不变，返回格式不变
- [ ] 核心功能真实场景验证：素材导入、搜索、重复检测全流程可正常使用
- [ ] 新增各子模块独立单元测试，覆盖关键路径
- [ ] 无新的 import 循环

**依赖项：**
- R1-R10 **全部完成后**最后执行

**已知约束：**
- **已解决 Q17**：Library 拆分目录结构已确认（core / maintenance / tagging / integrations / db，Facade 模式）
- 这是本版本风险最高的任务，任何单次子模块迁移后必须立即运行全量测试
- 迁移顺序建议：每次只迁移一个子模块（如先迁移 gdrive.py，验证通过后再迁移下一个），不做大爆炸式迁移
- 若迁移过程中任一测试失败，立即停止并等待人类 review，不继续推进

---

## 5. 完成状态追踪

| 任务 | 覆盖问题 | 预估工作量 | 启动日期 | 实际完成日期 | 迭代次数 | 备注 |
|------|---------|----------|---------|------------|---------|------|
| R1 | BUG-001, BUG-002 | 低 | — | — | 0 | 未开始，无阻塞 |
| R2 | SEC-001, BUG-004, SEC-002 | 低-中 | — | — | 0 | 未开始，无阻塞 |
| R3 | BUG-006, BUG-007, BUG-008 | 中 | — | — | 0 | 未开始，无阻塞（Q3/Q4/Q5 已解决）|
| R4 | UX-P1-001, UX-P1-002 | 中 | — | — | 0 | 未开始，无阻塞 |
| R5 | UX-P2-001, UX-P2-007 | 中 | — | — | 0 | 未开始，无阻塞 |
| R6 | UX-P2-003, UX-P2-004 | 中 | — | — | 0 | 未开始，无阻塞 |
| R7 | UX-P2-005, UX-P2-006, DATA-001 | 中 | — | — | 0 | 未开始，无阻塞 |
| R8 | BUG-003 | 高 | — | — | 0 | 未开始，Q12 格式已从代码反推确认 |
| R9 | DATA-002, DEP-001 | 低-中 | — | — | 0 | 未开始，Q13 依赖分类已确认 |
| R10 | UX-P3-001~005 | 低-中 | — | — | 0 | 未开始，Q15 品牌名已确认（VideoEditor）|
| R11 | ARCH-001 | 极高 | — | — | 0 | 未开始，Q17 拆分结构已确认；最后执行 |

---

## 6. 已解决项汇总（全量）

所有待确认项已于 2026-03-21 V5.0 完全解决，**无任何阻塞项**。

### 通过 UI 规范解决（9 项）

| 原编号 | 解决方式 | 解决依据 |
|--------|---------|---------|
| Q2（query 长度限制）| ✅ 500 字符 | 无需确认 |
| Q6（预检 error UI 形态）| ✅ `modal-confirm` + 警告横幅 | Design System Principle 6 |
| Q7（向导跳过补救引导）| ✅ `empty-state` 组件 | Design System empty-state |
| Q8（ProjectDialog 文案）| ✅ 占位文案 COPY-009~011 | copy-placeholders.md |
| Q9（删除工作流确认形态）| ✅ `modal-danger` | Design System Principle 6 |
| Q10（无项目引导 UI）| ✅ `empty-state` + COPY-019~021 | Design System empty-state |
| Q11（标签种子数据内容）| ✅ 占位数据 COPY-SEED-01~08 | copy-placeholders.md |
| Q14（图标统一方案）| ✅ Unicode 符号，不引入新库 | Design System 一致性原则 |
| Q16（TagBrowser/Canvas 文案）| ✅ COPY-024~026 | copy-placeholders.md |

### 通过代码读取 / 产品授权解决（8 项）

| 编号 | 解决内容 | 解决结果 |
|------|---------|---------|
| Q1 | provider 枚举值 | ✅ openai / anthropic / moonshot / qwen / gemini / maxmini（来自 `_AI_PROVIDER_CATALOG`）|
| Q3 | `GET /api/projects` 字段 | ✅ project_id / name / project_dir / videos_dir / created_at / updated_at / workflow_count |
| Q4 | `GET /api/workflow/status` 字段 | ✅ persisted / current_run_id / status / current_step / guidedAvailable |
| Q5 | `GET /api/settings` 聚合范围 | ✅ ai（provider/model/api_key 脱敏）+ ui；用 `_mask_secret()` |
| Q12 | Step 3 脚本输出 JSON 格式 | ✅ `{ title, description, clips[{source_asset_id, start_ms, end_ms, description}], subtitles[{start_ms, end_ms, text}], bgm{source, asset_id, volume} }` |
| Q13 | requirements.txt 分类 | ✅ Flask/numpy/Pillow/opencv/ffmpeg-python/pywebview = 必选；torch/AI = 可选 |
| Q15 | 应用品牌名称 | ✅ **VideoEditor**（中文说明文字用"视频编辑器"）|
| Q17 | Library 拆分结构 | ✅ 确认 core / maintenance / tagging / integrations / db 方案 |

---

## 7. 执行顺序建议

```
R1 → R2 → R3 → R4 → [R5 / R6 / R7 并行] → R8 → [R9 / R10 并行] → R11
```

- **R1**：P0，无依赖，立即开始
- **R2**：P0，依赖 R1
- **R3**：依赖 R1+R2
- **R4**：依赖 R3
- **R5、R6、R7**：均依赖 R4，可并行
- **R8**：依赖 R1-R7，工程量最大
- **R9、R10**：可与 R8 并行
- **R11**：最后，依赖 R1-R10 全部完成，风险最高

---

## 8. 变更记录

| 日期 | 版本 | 变更内容 | 责任人 |
|------|------|---------|--------|
| 2026-03-21 | V1.0 | 初始版本，R1-R7（7 个任务）| Cowork |
| 2026-03-21 | V2.0 | 纳入全量问题，扩展至 R1-R11（11 个任务）| Cowork |
| 2026-03-21 | V3.0 | 按 dev-governance.md 规范重写；增加输入/输出/依赖/约束字段；标注全部待确认项 | Cowork |
| 2026-03-21 | V4.0 | 通过 UI 规范 + 文案占位解决 9 项 UI 类待确认；各任务约束/验收标准更新 | Cowork |
| 2026-03-21 | V5.0 | 通过代码读取 + 产品授权解决剩余 8 项；全部 17 项待确认清零；Step 3 输出格式从代码反推确认；Q15 品牌名确认为 VideoEditor；新增执行顺序建议章节 | Cowork |

---

*计划版本 V5.0 | 2026-03-21 | 无任何阻塞项，R1 可立即开始*
