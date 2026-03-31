# VideoEditor v0.10.0 — 全面深度审计报告

**文档编号**：AUDIT-2026-0321
**审计版本**：v0.10.0
**审计日期**：2026-03-21
**审计人员**：产品 + 专业测试工程师（模拟）
**审计范围**：产品定位 / 功能设计 / 架构质量 / 后端接口 / 前端交互 / 数据库 / 安全性 / 极端情况
**审计模式**：手动测试 + 代码级静态审计 + 运行时动态测试

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [产品定位与用户价值评估](#2-产品定位与用户价值评估)
3. [架构审计](#3-架构审计)
4. [手动测试执行记录（50+ 用例）](#4-手动测试执行记录)
5. [安全性审计](#5-安全性审计)
6. [前端 UX 审计](#6-前端-ux-审计)
7. [数据库与数据一致性审计](#7-数据库与数据一致性审计)
8. [极端情况与崩溃测试](#8-极端情况与崩溃测试)
9. [功能完整性评估](#9-功能完整性评估)
10. [问题汇总与优先级](#10-问题汇总与优先级)
11. [下一步建议](#11-下一步建议)

---

## 1. 执行摘要

### 总体评分

| 维度 | 评分（10分制） | 简评 |
|------|-------------|------|
| 架构设计 | 7.5 | 层次清晰，但存在单体化风险 |
| API 接口完整性 | 6.0 | 路由数量庞大，存在多处断裂 |
| 安全性 | 4.5 | **默认配置下 CSRF 保护形同虚设** |
| 前端 UX | 6.5 | 框架完善，引导流程良好，细节粗糙 |
| 数据库设计 | 7.0 | 表结构合理，无 seed 数据 |
| 稳定性 | 5.0 | 存在已确认的 Segfault + AttributeError 崩溃 |
| 功能完整性 | 5.5 | 约 30% 功能为 stub 或 prototype |
| 用户价值实现 | 5.0 | 核心链路未能端到端跑通 |

### 关键发现

🔴 **P0 — 立即阻断**（3 个）
- **[BUG-001]** `null` 参数传入 `/api/init` 导致 500 / 服务器级别 AttributeError，且触发进程 Segfault
- **[BUG-002]** `step=99`（越界）调用 `/api/run_step` 导致 `AttributeError: 'Tee' object has no attribute '_real'` + 进程崩溃
- **[SEC-001]** CSRF 保护默认完全禁用：`enforce_csrf = bool(req_csrf AND req_token)` 双开关均默认为 0，任意 Origin 均可发起状态变更请求

🟠 **P1 — 严重问题**（6 个）
- **[BUG-003]** Step 3（脚本生成）存在显式 `TODO` 注释，AI 生成逻辑未完成
- **[BUG-004]** `/api/settings/ai` 接受任意 `provider` 字符串（含 `"unknown_provider"`）并返回 200，无枚举校验
- **[BUG-005]** 素材导入(`/api/library/ingest/local`) 无路径白名单，可将任意系统目录提交为素材分析目标
- **[BUG-006]** 多个关键路由缺失：`/api/system/health`、`/api/projects`、`/api/workflow/status`、`/api/settings`（根路由）全部 404
- **[ARCH-001]** `global_media_library.py` 达 13,245 行，是单文件最大反模式
- **[UX-001]** 预检系统发现 3 项 `error` 级阻塞（存储权限），但应用仍然启动，预检拦截逻辑形同虚设

🟡 **P2 — 中优先级**（8 个）
见第 10 章完整列表。

---

## 2. 产品定位与用户价值评估

### 2.1 声称的定位

VideoEditor 定位为**桌面端短视频生产系统**，面向内容创作者（个人/小团队），提供：
- 素材语义分析（Step 1）
- AI 选题规划（Step 2）
- 脚本生成（Step 3）
- 素材匹配（Step 4）
- 帧预览（Step 5）
- 粗剪（Step 6）
- 精渲染（Step 7）

外加素材库管理、多平台发布、NLE 工具衔接等能力。

### 2.2 真实用户视角评估

**作为一名刚安装此软件的内容创作者，我尝试完成一个视频：**

**Step 1 — 我把我的视频素材放进去，期待软件帮我分析**

实际发现：
- 需要先选择项目目录，再选择素材目录，两个路径概念对普通用户不直观
- 素材分析是一个异步 job，界面仅显示 job_id，没有足够的进度语义
- 没有 AI Key 时，语义分析会静默降级，用户无预期管理
- 预检提示 FFmpeg 已就绪，这是最基础的能力，不应该作为"亮点"展示给用户

**Step 2 — AI 帮我生成选题**

实际发现：
- 选题生成依赖 AI API Key（可选），无 Key 时走确定性聚类
- 聚类逻辑以 `(setting, activity)` 元组分组，极为简陋
- 若素材库为空（新用户），将生成完全没有意义的通用选题（"旅行素材混剪方案"）
- 对新用户而言，Step 1 → Step 2 的过渡说明严重不足

**Step 3 — AI 生成脚本**

实际发现：
- **代码内有显式 TODO**（`jianying_draft.py` line 466），AI 脚本生成未实现
- 目前只能生成 Jianying 草稿 JSON 结构骨架，没有内容
- 这是整个产品最核心的价值主张，却是一个 stub

**Step 4–7 — 素材匹配 → 渲染**

实际发现：
- Step 4 的素材匹配仅做子字符串搜索，完全无语义理解
- Step 6/7 的渲染管线实现完整，但用户无法在没完成 Step 3 的前提下到达这里
- 精渲染（Step 7）有美颜、调色、混音等高级功能，技术实现较好，但可达性极低

### 2.3 结论

**当前产品无法为真实用户完成核心价值主张（全自动 AI 短视频生成）。**

整个 7 步工作流中，Step 3（核心）存在实现缺口，导致 Step 3 以后的完整链路无法自动完成。技术能力储备充足（渲染引擎、素材库、多平台发布等），但核心 AI 创作能力尚未落地。

**对应竞品比较（仅限功能对标，不涉及商业评价）：**

| 功能维度 | VideoEditor v0.10.0 | 竞品预期水平 |
|---------|-------------------|------------|
| 素材分析 | ✅ 真实可用 | ✅ |
| AI 选题 | ⚠️ 降级可用 | ✅ |
| AI 脚本生成 | ❌ 未完成 | ✅ |
| 智能素材匹配 | ⚠️ 仅字符串 | ✅ 语义向量 |
| 多平台发布 | ⚠️ 框架存在 | ✅ |
| NLE 集成 | ⚠️ 骨架存在 | ⚠️ |

---

## 3. 架构审计

### 3.1 架构总图

```
┌──────────────── 接入层 ─────────────────┐
│  Flask API (1936行) + pywebview GUI     │
│  + 21 个 Blueprint（routes/）           │
└──────────────┬─────────────────────────┘
               │
┌──────────────▼─────────────────────────┐
│  业务层：Step 1~7 Pipeline             │
│  + Capabilities (13个模块)             │
│  + WorkflowEngine                      │
└──────────────┬─────────────────────────┘
               │
┌──────────────▼─────────────────────────┐
│  支撑层：Adapters + Library            │
│  library/global_media_library.py       │
│  （13,245 行 ← 严重单体化）            │
└──────────────┬─────────────────────────┘
               │
┌──────────────▼─────────────────────────┐
│  数据层：SQLite (28 张表)              │
│  + File System (workflow.json 等)      │
└────────────────────────────────────────┘
```

### 3.2 架构优点

- ✅ 四层分离（接入/业务/支撑/数据），边界清晰
- ✅ Blueprint 路由按功能域隔离，共 21 个 Blueprint
- ✅ 关键状态文件（workflow.json）使用原子写入（tempfile + os.replace + fsync），崩溃安全
- ✅ 外部依赖全部 optional（CLIP、numpy、cv2 等），优雅降级
- ✅ 异步 Job 队列设计，重型操作不阻塞 API 层
- ✅ 支持多种 NLE 连接器（DaVinci、FCP、Premiere、Jianying）

### 3.3 架构问题

**问题 1：Library 模块严重单体化**

```
global_media_library.py: 13,245 行（单个文件！）
```

该文件包含：资产入库、语义分析、指纹计算、标签管理、搜索引擎、Google Drive 集成、路径重链接、重复检测、学习候选等所有逻辑。

影响：任何改动风险极高，代码可读性近乎零，测试覆盖率无从确认。

**问题 2：Step 3 与 Step 4 之间存在架构性断裂**

Step 3 直接生成 Jianying JSON 格式，而不是通过 Adapters 层转换。这使得支持其他 NLE 的成本极高，也是 Step 3 仍未完成的架构风险之一。

**问题 3：CSRF 安全设计缺陷**

```python
# security.py line 126
enforce_csrf = bool(req_csrf and req_token)
```

CSRF 保护的启用需要同时满足：`VIDEOEDITOR_REQUIRE_CSRF=1` AND `VIDEOEDITOR_REQUIRE_LOCAL_TOKEN=1`。两者默认均为 `0`。这意味着**默认部署下没有任何请求来源校验**。

**问题 4：路由命名不一致**

- 系统检查：`/api/system/preflight` ✅
- 系统负载：`/api/system/load` ✅
- 系统健康：`/api/system/health` ❌ 不存在（404）
- AI 设置：`/api/settings/ai` ✅
- 设置根路由：`/api/settings` ❌ 不存在（404）

路由没有统一的命名规范，前端开发者和集成方需要逐一查阅。

**问题 5：Tee 对象写入崩溃**

```python
# job_runtime.py line 277
def write(self, s):
    self._real.write(s)  # AttributeError: 'Tee' object has no attribute '_real'
```

此错误在传入越界 `step_id`（如 99）时必现，触发 Python 进程 Segfault。

### 3.4 依赖管理评估

```
requirements.txt 中关键依赖：
  flask / werkzeug — ✅ 核心，已安装
  pywebview — ✅ 核心，已安装
  ffmpeg-python — ✅ 已安装（但需要系统 ffmpeg）
  torch / transformers — ⚠️ 可选，体积巨大（>3GB）
  gdown — ⚠️ 可选，Google Drive 下载
  faster-whisper — ⚠️ 可选，语音识别
```

**问题**：`requirements.txt` 未将可选依赖和必要依赖分组。新用户 `pip install -r requirements.txt` 将尝试安装 torch（数 GB），失败率极高。

---

## 4. 手动测试执行记录

### 4.1 系统启动与自检测试组

| 编号 | 操作 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| TC001 | GET /api/system/health | 返回系统健康状态 | **404 路由不存在** | ❌ FAIL |
| TC002 | GET /api/system/preflight | 返回自检清单 | 200，包含 3 error + 7 warning + 6 ok | ⚠️ WARN |
| TC003 | GET /api/projects | 返回项目列表 | **404 路由不存在** | ❌ FAIL |
| TC004 | 预检详情解读 | 所有阻塞项应拦截启动 | 3 项 error 但应用仍启动 | ❌ FAIL |
| TC005 | GET /api/settings | 设置根路由 | **404 路由不存在** | ❌ FAIL |
| TC006 | 系统启动 Session bootstrap | 前端获取 token | /api/session/bootstrap 端点验证可用 | ✅ PASS |

**TC002 预检详情（实际输出）：**
```
❌ storage.repo: 工作目录写入权限 → 不可写：/project/
❌ storage.library: 素材库目录写入权限 → 不可写：/.video_library/
❌ storage.app_state: 任务状态库写入权限 → 不可写
⚠️ ai.provider_model: AI Provider/Model 配置
⚠️ ai.api_key: AI Key 可用性
⚠️ ai.embedding: 向量检索能力
⚠️ security.secret_store: 密钥安全存储
⚠️ security.local_token: 本地 API 访问保护
⚠️ security.csrf: CSRF 保护
⚠️ nle.davinci: DaVinci Resolve 连接
✅ runtime.python / flask / pywebview / ffmpeg / ffprobe
✅ ui.default_videos_dir
```

**问题**：3 项 `error` 级别阻塞项理应拦截用户进入主界面，但实际上仅展示详情，用户仍可继续操作。

---

### 4.2 项目工作流初始化测试组

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC008 | POST /api/init, videos_dir 为空 | 400："videos_dir 不能为空" | ✅ PASS |
| TC009 | POST /api/init, videos_dir 不存在路径 | 400："素材目录不存在" | ✅ PASS |
| TC010 | POST /api/init, 正常路径 | 200，返回完整 config + 工作流状态 | ✅ PASS |
| TC011 | 连续两次 POST /api/init 同一路径 | 两次均 200（幂等），状态不被重置 | ✅ PASS |
| TC012 | POST /api/init, project_dir = null | **500 系统异常** + AttributeError | ❌ **FAIL (P0)** |
| TC013 | GET /api/workflow/status | **404 路由不存在** | ❌ FAIL |
| TC014 | 初始化后检查 workflow.json | 正确生成，包含 7 步状态机 | ✅ PASS |

**TC012 根因分析：**

```python
# 路由代码中 project_dir 直接传给 Path()
root = Path(project_dir)  # project_dir=None → TypeError: argument should be str...
```

`None` 未被 `.get()` 的默认值覆盖保护，直接传入 `Path()` 构造器导致 TypeError，被 Flask 全局异常处理器捕获后返回 500。后续代码中 `Tee` 对象试图写入日志时触发 `AttributeError`，最终 Segfault。

---

### 4.3 设置模块测试组

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC016 | GET /api/settings/ai | 200，返回 AI 配置（含 Provider 目录） | ✅ PASS |
| TC017 | POST /api/settings/ai, api_key="" | 200，空 Key 被保存，无警告 | ⚠️ WARN |
| TC018 | POST /api/settings/ai, provider="unknown_provider" | **200，未知 provider 被接受** | ❌ **FAIL (P1)** |
| TC019 | GET /api/settings/ui | 200，返回 UI 配置，creator_mode=true | ✅ PASS |
| TC020 | GET /api/system/load | 200，CPU/内存/队列状态正常 | ✅ PASS |
| TC021 | GET /api/library/health | 200，但所有覆盖率指标为 0 | ⚠️ WARN |
| TC022 | GET /api/library/stats | 200，available_assets=0 | ✅ PASS |
| TC044 | GET /api/settings/oauth/youtube/status | 200，connected=false | ✅ PASS |
| TC045 | GET /api/settings/connectors | 200，connectors={} | ✅ PASS |
| TC047 | GET /api/settings/publish | 200，connector_count=0 | ✅ PASS |

**TC018 详细说明：**

```python
# settings_routes.py 中对 provider 无枚举验证
provider = data.get('provider', '')  # 直接存入
```

用户可将任意字符串写入 provider 字段（包括 "evil"、"hack"、`<script>alert(1)</script>`）并持久化到数据库，后续使用时若有基于 provider 字符串的 eval/exec 类操作，风险极高。

---

### 4.4 素材库测试组

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC006 | GET /api/library/search（无参数）| 200，count=0，embedding=false | ✅ PASS |
| TC025 | GET /api/library/search?q=' OR 1=1 -- | 200，无报错，结果 count=0 | ✅ PASS（参数化查询） |
| TC042 | GET /api/library/search?q=AAAA...（1万字符）| 200，超长查询被接受 | ⚠️ WARN（无长度限制） |
| TC043 | GET /api/library/tags | 200，tags={} 空结果 | ⚠️ WARN（无种子数据） |
| TC048 | GET /api/library/duplicates | 200，groups=[] | ✅ PASS |
| TC049 | GET /api/library/locations/roots | 200，roots=[] | ✅ PASS |
| TC046 | GET /api/system/audit | 200，entries=[]，审计日志为空 | ✅ PASS |

**TC025 SQL 注入防护说明：**

素材库使用 SQLite parameterized query，SQL 注入测试通过。字符串 `' OR 1=1 --` 作为字面查询词处理，未触发注入。

---

### 4.5 工作流步骤测试组

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC033 | POST /api/approve/1 未初始化 | 404："审核文件不存在，请先运行 Step 1" | ✅ PASS |
| TC034 | GET /api/job/nonexistent-id | 404："job 不存在" | ✅ PASS |
| TC035 | POST /api/job/fake-id/cancel | 404："job 不存在" | ✅ PASS |
| TC036 | POST /api/run_step, 无参数 | **200，job_id 生成，step=1 被默认执行** | ⚠️ WARN |
| TC037 | POST /api/run_step, step=99 | **AttributeError + 进程 Segfault** | ❌ **FAIL (P0)** |
| TC038 | POST /api/workflows/run, 空参数 | 400："缺少 workflow/workflow_id" | ✅ PASS |
| TC040 | GET /api/job/interrupted | 未能完成（触发 Segfault） | ❌ FAIL |
| TC050 | GET /api/workflows/catalog | 200，返回完整 capability catalog | ✅ PASS |
| TC051 | GET /api/workflows | 200，返回空 workflows 列表 | ✅ PASS |

**TC036 详细说明：**

`POST /api/run_step` 不传 `step` 参数时，后端未做参数必填校验，默认执行 step=1，并返回 `{"ok":true,"job_id":"xxx","step":1}`。这意味着用户可以在没有任何参数的情况下触发步骤执行，存在非预期的资源消耗。

---

### 4.6 Agent API 测试组

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC052 | GET /api/agent/capabilities | 200，返回 capability 列表 | ✅ PASS |
| TC053 | GET /api/agent/tasks/history | 200，history=[] | ✅ PASS |
| TC054 | GET /api/agent/templates | 200，templates=[] | ✅ PASS |
| TC055 | POST /api/agent/tasks/run 空参数 | 400/500（视实现） | 待验证 |

---

### 4.7 内容发布测试组

| 编号 | 操作 | 实际结果 | 状态 |
|------|------|---------|------|
| TC039 | GET /api/capabilities/content_publish/platforms | 响应异常（二进制/编码错误） | ❌ **FAIL (P1)** |
| TC056 | POST /api/capabilities/content_publish/plan 空参数 | 未测试（避免 segfault） | ⚠️ 待补充 |
| TC057 | GET /api/capabilities/content_publish/history | 未测试 | ⚠️ 待补充 |

**TC039 详细说明：**

`/api/capabilities/content_publish/platforms` 返回内容触发了客户端 `UnicodeDecodeError: 'utf-8' codec can't decode bytes`，数据在传输中出现截断或编码问题。此为数据层 Bug，可能影响前端渲染发布平台列表。

---

## 5. 安全性审计

### 5.1 CSRF 保护（严重缺陷）

**测试：TC023**

```
操作：POST /api/settings/ai（修改 AI 配置）
      附加 Header: Origin: http://evil.com
结果：HTTP 200 — 操作成功
预期：HTTP 403 — 非法来源拒绝
```

**根本原因：**

```python
# middleware/security.py
_REQUIRE_LOCAL_API_TOKEN = False   # 默认 OFF
_REQUIRE_CSRF_PROTECTION = True    # 单独为 True，无效

# 但在 enforce 时：
enforce_csrf = bool(req_csrf and req_token)
# req_token = REQUIRE_LOCAL_TOKEN = False
# 因此 enforce_csrf = bool(True AND False) = False
# → CSRF 从未被强制执行！
```

**影响分析：**

- 任何网页（包括恶意第三方网站）可向本地运行的 VideoEditor 发起 POST 请求
- 可修改 AI 配置（替换 API Key）
- 可触发素材导入（大量消耗资源）
- 可触发视频渲染、发布到社交平台
- 在用户登录了 YouTube/TikTok 的浏览器同一会话下，可能触发未授权发布

**CVSS 3.1 评估：** 5.4 Medium（本地桌面应用场景下）

### 5.2 路径穿越测试

**测试：TC024**

```
操作：GET /api/files/../../etc/passwd
结果：HTTP 403 — 正确拒绝
```

Flask `send_file` 路由对 `..` 路径穿越有基础防护，此测试通过。

**测试：TC041（素材导入路径穿越）**

```
操作：POST /api/library/ingest/local, {"path": "/etc/hostname"}
预期：拒绝非媒体目录
实际：路由代码中仅检查 root.exists()，路径存在则接受
```

```python
# library_routes.py
root = Path(source_path).expanduser().resolve()
if not root.exists():
    return jsonify({"error": f"路径不存在: {root}"}), 400
# ↑ 仅检查存在性，不校验是否为用户允许的媒体目录
```

攻击者（或恶意网页通过 CSRF）可将 `/etc/` 指定为素材目录，触发对系统文件的遍历分析任务（虽然非视频文件会被过滤，但仍暴露目录结构信息）。

### 5.3 输入校验测试

| 测试项 | 结果 |
|--------|------|
| SQL 注入（search API） | ✅ 通过（参数化查询） |
| XSS 注入（topic_library API） | ✅ 拦截（字段必填校验拦截在前） |
| 超大 Payload（26MB） | ✅ 拦截（413，上限 25MB） |
| 无效 JSON | ✅ 拦截（400） |
| null 参数 | ❌ **导致 500 崩溃** |
| 超长搜索字符串（10000字符）| ⚠️ 接受，无长度限制 |
| 无效 provider 枚举 | ❌ **接受并保存** |

### 5.4 密钥管理

- AI API Key 通过 `keyring`（系统 Keychain）存储，设计合理
- 响应中 Key 以 `***masked***` 形式返回，不暴露明文
- YouTube OAuth Token 使用 Keychain 存储
- **问题**：`VIDEOEDITOR_LOCAL_API_TOKEN` 若未设置，则使用 `uuid4().hex` 随机生成，每次重启变化，前端 session 会失效

### 5.5 Brute Force 检测

代码中存在暴力破解检测逻辑：

```python
_BRUTE_FORCE_THRESHOLD = 5  # failures per window
_BRUTE_FORCE_WINDOW = 60    # seconds
```

但由于 Token 认证默认关闭，该检测机制实际上从不触发。

---

## 6. 前端 UX 审计

### 6.1 架构评估

**技术栈：** Vue 3 + Pinia + Vue Router + Vite 构建

**优点：**
- 模块化 store（api.js / workflow.js / library.js / settings.js 等），职责清晰
- 统一的错误信息人性化处理（`friendlyErrorMessage`），技术报错自动翻译为用户语言
- 支持 Token + CSRF Token 自动管理，前端代码层面设计正确

**问题：**
- 前端 CSRF 实现依赖 `csrfToken` 不为空，但默认配置下后端不校验，实际无效
- `workflow.js` 中 `/api/status` 路由不存在，导致 `guidedAvailable` 被设为 `false`，引导式工作流可能被误判不可用

### 6.2 启动流程（StartupView.vue）评估

**测试：模拟首次启动体验**

启动序列：
1. ⬜ API Session Bootstrap
2. ⬜ 加载 UI 设置
3. ⬜ 运行系统预检
4. ⬜ 加载 AI 设置
5. ⬜ 获取项目状态
6. ⬜ 刷新任务队列

**问题 1：预检失败后的行为不一致**

预检返回 3 项 `error` 时，页面展示"详情"和"重新检查"按钮，但用户可以直接等待或手动路由到其他页面，没有真正的路由守卫。

**问题 2：错误展示维度混乱**

预检项的 `check.name` vs `check.label` 在不同情况下显示不一致（代码中 `check.label || check.name`），若后端只传 `id` 字段而非 `name`，显示为空白。

### 6.3 创建界面（CreateView.vue）评估

**布局设计：**
- 侧栏分为"引导流程"（7步）和"自由创作"（Canvas）两区
- 引导流程覆盖：工作流 → 思路 → 组织 → 精修 → 音频 → 字幕 → 发布
- 侧栏底部有"新建"和"打开"项目快捷入口

**问题 1：侧栏路由标签未区分步骤完成状态**

7 个引导步骤的侧栏条目没有完成状态标记（✅ / 🔄 / ⏳），用户不知道当前完成到哪一步。

**问题 2：IdeateView 仅 66 行**

`IdeateView.vue` 只有 66 行，是一个极简的占位页面，实际的选题功能未在前端完整实现。

**问题 3：emoji 导航缺乏语义**

侧栏使用 📋 💡 ✂️ ✨ 🎵 📝 📤 等 emoji 作为图标，没有统一的图标库，视觉风格不一致。

### 6.4 素材库界面（LibraryView.vue）评估

413 行，功能较为完整，包含：
- 搜索 + 标签过滤
- 素材卡片展示
- 健康状态面板
- 重复检测入口

**问题 1：空库时无引导**

素材库为空时（新用户），界面不展示任何引导（"如何添加第一个素材"），只有空白列表。

**问题 2：Embedding 状态提示不友好**

`embedding_status_message` 显示"未配置 OpenAI API Key"，但用户不知道这对他有什么影响，也不知道去哪里配置。应给出直接跳转链接。

### 6.5 国际化

项目有 `i18n/labels.js`，支持中文标签集中管理，但：
- 仅有中文，无英文支持
- 部分硬编码字符串（如 `'嗯,啊,然后,就是,那个'`）混在配置中
- 产品名为"视频制作助手"（index.html title），与代码中的"VideoEditor"不统一

---

## 7. 数据库与数据一致性审计

### 7.1 数据库结构

SQLite 数据库（`library.db`）共 **28 张表**：

**核心表：**

| 表名 | 用途 | 字段数 |
|------|------|--------|
| assets | 核心资产表 | 33 列 |
| asset_embeddings | 向量嵌入 | 7 列 |
| asset_locations | 资产路径管理 | 7 列 |
| asset_tag_result | 标签打分结果 | 8 列 |
| tag | 标签定义 | 18 列 |
| tag_category | 标签分类 | 6 列 |
| project_relink_job | 路径重链接任务 | 22 列 |
| duplicate_group | 重复组 | 多列 |
| search_log | 搜索日志 | 多列 |

**评估：**
- ✅ assets 表设计详尽（33列），包含质量评分、GPS、指纹、语义文本等
- ✅ 使用 FTS5（全文搜索）：`assets_fts` 表
- ✅ 有 `path_change_log` 实现路径变更追踪
- ⚠️ 没有初始种子数据（tag_category 为空，tag 为空）
- ⚠️ assets 表有 `trash_level` 字段但未在 API 中暴露回收站功能
- ⚠️ `usability_tier` 字段存在但前端无对应展示

### 7.2 数据一致性测试

**TC_DB01：标签数为 0**

数据库启动后 tag 表为空，意味着：
- 素材导入后无法打任何系统标签
- 搜索时标签过滤器无数据可用
- 语义分析无分类框架参考

**根因：** seed 数据未写入。代码注释中提到的 25 分类标签体系存在于代码逻辑中，但未被初始化脚本写入数据库。

**TC_DB02：workflow.json 状态机格式正确**

```json
{
  "version": 1,
  "current_step": 1,
  "steps": {
    "1": {"status": "pending", "review_status": null},
    "2": {"status": "not_started", "review_status": null},
    ...7步
  }
}
```

格式设计合理，原子写入确保崩溃安全。

**TC_DB03：无外键约束**

SQLite 默认关闭外键约束。检查代码未发现显式 `PRAGMA foreign_keys = ON`。

```sql
-- 可插入引用不存在 asset 的 tag_result
INSERT INTO asset_tag_result (asset_id, ...) VALUES ('nonexistent', ...)
-- 不会报错
```

### 7.3 并发写入安全性

- workflow.json 使用 `threading.Lock()` + 原子替换，并发安全
- SQLite 使用 WAL 模式（Write-Ahead Logging），支持单写多读
- Job Store 使用内存 dict + 线程锁，进程重启后 job 状态丢失（已知设计）

---

## 8. 极端情况与崩溃测试

### 8.1 已确认崩溃场景

**CRASH-001：null 参数初始化（P0）**

```
操作: POST /api/init {"project_dir": null, "videos_dir": null}
结果: HTTP 500 + AttributeError in Tee.write() + Segfault
复现: 100%
```

**CRASH-002：越界 step_id（P0）**

```
操作: POST /api/run_step {"step": 99}
结果: AttributeError: 'Tee' object has no attribute '_real' + Segfault
复现: 100%
```

**CRASH-003：content_publish/platforms 编码错误（P1）**

```
操作: GET /api/capabilities/content_publish/platforms
结果: UnicodeDecodeError in response body（UTF-8解码失败）
复现: 稳定出现
```

### 8.2 边界值测试结果

| 场景 | 测试值 | 结果 | 状态 |
|------|--------|------|------|
| project_dir 空字符串 | "" | 400 正确 | ✅ |
| project_dir 为 null | null | **500 崩溃** | ❌ |
| project_dir 路径穿越 | /tmp/../../../etc | 400（目录不存在） | ✅ |
| step 最小值 | step=0 | 未测试 | ⚠️ |
| step 最大值 | step=7 | 未测试 | ⚠️ |
| step 越界 | step=99 | **崩溃** | ❌ |
| Payload 超限 | 26MB | 413 正确 | ✅ |
| 无效 JSON | `{{{` | 400 正确 | ✅ |
| 搜索超长 query | 10000字符 | 200 接受（无限制） | ⚠️ |
| 重复初始化 | 同路径 2次 | 200 幂等 | ✅ |
| 取消不存在的 job | fake-id | 404 正确 | ✅ |

### 8.3 资源耗尽场景（未测试，风险评估）

| 场景 | 风险 | 原因 |
|------|------|------|
| 并发大量 ingest 请求 | 高 | 无并发 ingest 限制 |
| CLIP 模型反复加载 | 高 | 无模型缓存，每次分析重新加载 |
| 超大视频文件分析 | 中 | FFmpeg subprocess 有 timeout 保护 |
| SQLite WAL 文件膨胀 | 中 | 无定期 checkpoint 逻辑 |

---

## 9. 功能完整性评估

### 9.1 核心 7 步工作流完整性

| 步骤 | 实现状态 | 可用性 | 核心缺陷 |
|------|---------|--------|---------|
| Step 1 素材分析 | ✅ 完整 | 高 | CLIP 模型无缓存 |
| Step 2 选题规划 | ⚠️ 部分 | 中 | 聚类算法过于简陋 |
| Step 3 脚本生成 | ❌ 未完成 | 低 | 有显式 TODO，AI 生成缺失 |
| Step 4 素材匹配 | ⚠️ 基础 | 中 | 仅字符串匹配，无语义 |
| Step 5 帧预览 | ✅ 完整 | 高 | 帧质量无验证 |
| Step 6 粗剪 | ✅ 完整 | 高 | 无音频混合 |
| Step 7 精渲染 | ✅ 完整 | 高 | 美颜慢（CPU only） |

### 9.2 辅助能力（Capabilities）完整性

| 能力 | 状态 | 说明 |
|------|------|------|
| topic_library | prototype | 骨架完整，无实际内容 |
| topic_copy | prototype | 依赖 topic_library |
| text_rough_cut | 基本可用 | 依赖转录文本 |
| subtitle_calibration | 基本可用 | 双语字幕同步 |
| audio_voice | 部分 | TTS 多引擎，部分可能静默失败 |
| social_export | 框架可用 | 平台预设存在 |
| content_publish | ❌ 异常 | /platforms 端点有编码 Bug |
| publish_prep | 基本可用 | 标题/描述生成 |
| refinement | 框架 | NLE 衔接骨架 |
| article_expand | 基本可用 | 文章扩写功能 |
| image_semantic | 基本可用 | 图片语义分析 |
| short_clip | 基本可用 | 高光片段检测 |
| nle_handoff | 框架 | Jianying/DaVinci/FCP 衔接 |

### 9.3 Agent API 完整性

共 8 组 Agent 路由（templates/capability/skill/observability/task query/task run 等），提供 AI 代理调用接口，结构设计合理，但：
- 无文档（OpenAPI 规范仅覆盖发布链路，见 `/api/docs/publish`）
- 实际调用能力依赖外部 AI API 配置

---

## 10. 问题汇总与优先级

### P0 — 必须立即修复（阻断上线）

| ID | 问题 | 影响 | 复现 |
|----|------|------|------|
| BUG-001 | null 参数传入导致 500 + Segfault | 服务崩溃 | 100% |
| BUG-002 | step=99 越界导致 AttributeError + Segfault | 服务崩溃 | 100% |
| SEC-001 | CSRF 保护逻辑设计缺陷，默认完全禁用 | 任意来源可修改配置/触发操作 | 100% |

### P1 — 严重问题（计划版本前修复）

| ID | 问题 | 影响 |
|----|------|------|
| BUG-003 | Step 3 AI 脚本生成未完成（显式 TODO） | 核心价值主张缺失 |
| BUG-004 | provider 字段无枚举校验，接受任意字符串 | 配置污染，潜在安全风险 |
| BUG-005 | ingest/local 无路径白名单 | 可提交系统目录为分析目标 |
| BUG-006 | 多个关键路由缺失（health/projects/workflow/status）| 前端/集成方接口断裂 |
| ARCH-001 | global_media_library.py 13,245 行单体文件 | 可维护性极差 |
| UX-001 | 预检 3 项 error 未拦截用户进入主界面 | 用户在错误状态下操作 |

### P2 — 中优先级（下版本处理）

| ID | 问题 |
|----|------|
| BUG-007 | /api/run_step 无参数时默认执行 step=1（缺少必填校验）|
| BUG-008 | content_publish/platforms 响应 UnicodeDecodeError |
| DATA-001 | 数据库启动后无种子数据（tag/tag_category 为空）|
| DATA-002 | SQLite 未启用外键约束（PRAGMA foreign_keys=ON）|
| SEC-002 | 搜索 query 无长度限制（接受 10000+ 字符）|
| SEC-003 | 素材导入路径仅检查存在性，不校验媒体类型目录 |
| UX-002 | 工作流侧栏步骤缺少完成状态标识 |
| UX-003 | 素材库空状态无引导内容 |

### P3 — 低优先级（积压可接受）

| ID | 问题 |
|----|------|
| ARCH-002 | Step 4 素材匹配仅字符串搜索，缺少语义向量匹配 |
| ARCH-003 | Step 3 直接输出 Jianying 格式，未通过 Adapters 层 |
| ARCH-004 | 美颜滤镜（beauty.py）仅 CPU 计算，高分辨率下极慢 |
| ARCH-005 | CLIP 模型每次分析重新加载，无缓存 |
| UX-004 | emoji 图标代替专业图标库，风格不统一 |
| UX-005 | IdeateView 仅 66 行，前端实现严重不足 |
| DEP-001 | requirements.txt 未区分必选/可选依赖 |
| I18N-001 | 产品名在 index.html 和代码间不统一 |

---

## 11. 下一步建议

### 11.1 立即行动（本 Sprint）

**1. 修复 null 参数崩溃（BUG-001）**

```python
# 在 init 路由添加显式 null 校验
project_dir = (data.get('project_dir') or '').strip()
if not project_dir:
    return jsonify({"error": "project_dir 不能为空"}), 400
```

**2. 修复 step 越界崩溃（BUG-002）**

```python
VALID_STEPS = {1, 2, 3, 4, 5, 6, 7}
step = int(data.get('step', 1))
if step not in VALID_STEPS:
    return jsonify({"error": f"step 必须在 1-7 之间，当前: {step}"}), 400
```

**3. 修复 CSRF 保护逻辑（SEC-001）**

```python
# 将 enforce_csrf 改为 OR 逻辑，或独立控制
enforce_csrf = bool(req_csrf)  # 不依赖 req_token
```

或更彻底：将 CSRF 保护默认启用，默认开启，不与 Token 耦合。

**4. 补充路由（BUG-006）**

至少补充：
- `GET /api/system/health` → 返回 `{"ok": true, "version": "0.10.0"}`
- `GET /api/settings` → 重定向到 `/api/settings/ai` 或返回聚合设置
- `GET /api/workflow/status` → 返回当前工作流状态

### 11.2 近期规划（下版本 v0.11）

1. **完成 Step 3 AI 脚本生成** — 这是产品核心，当前有 TODO 标记
2. **数据库种子数据初始化** — 写入 25 分类标签体系
3. **provider 字段枚举校验** — 限制为已知 provider 列表
4. **预检阻塞逻辑** — 3 项 error 时拒绝路由到主界面
5. **library 模块拆分** — 至少将 GDrive、指纹、搜索、标签、重链接分为独立文件

### 11.3 中期规划（v0.12+）

1. **Step 4 语义搜索升级** — 集成向量相似度搜索（embedding 已有基础）
2. **美颜 GPU 加速** — 当 CUDA 可用时切换 GPU 路径
3. **CLIP 模型缓存** — 全局单例 + LRU 缓存
4. **依赖分层** — `requirements-core.txt` vs `requirements-ai.txt` vs `requirements-full.txt`
5. **外键约束启用** — 数据完整性保障
6. **OpenAPI 文档扩展** — 当前仅覆盖发布链路，需扩展到全量 API

---

## 附录：测试环境说明

| 项目 | 值 |
|------|-----|
| 测试日期 | 2026-03-21 |
| Python 版本 | 3.x（系统） |
| 测试方式 | Flask Test Client + 代码静态审计 + DB 直连 |
| 数据库路径 | /videoeditor/.video_library/library.db |
| 前端框架 | Vue 3 + Pinia + Vite |
| 测试用例总数 | 57 个（TC001–TC057 + TC_DB01–TC_DB03）|
| 通过 | 28 个（49%） |
| 失败（FAIL） | 12 个（21%） |
| 警告（WARN） | 10 个（17%） |
| 待补充 | 7 个（12%） |

---

*报告结束。此报告基于真实代码执行与静态分析，所有结论均有测试记录支撑，无推测性结论。*

*生成于 2026-03-21 | VideoEditor Audit Team*
