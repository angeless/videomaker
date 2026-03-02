# 修复项核查 Statement（更新于 2026-03-02）

说明：
- 状态定义：`已修复` / `部分修复` / `未修复` / `N/A`。
- 本文基于当前 `main` 工作区代码与测试结果（`146 passed`）核查。

| # | 需求 | 状态 | 证据 | 缺口/备注 |
|---|---|---|---|---|
| 1 | 首次启动自动检测并安装环境 | 已修复 | `apps/desktop/launcher.py` 增加 `_ensure_runtime_dependencies`；`start.command` 自动建 `.venv` 并启动 | 当前以 macOS 启动脚本为主 |
| 2 | 提供无需命令行的启动器 | 已修复 | 根目录 `start.command` 可双击启动 | 需后续补 Windows `.bat` |
| 3 | 配置均在软件内完成 | 部分修复 | `GET/POST /api/settings/ai` + 新增 `GET/POST /api/settings/ui`；前端新增“应用设置”卡片 | 仍有少量高级配置需环境变量（如部分 provider 扩展） |
| 4 | 美颜滤镜提升 | 部分修复 | 已有美颜参数与渲染开关（`renderOpts` / `modules/step7_final_render/beauty.py`） | 未形成“高阶美颜管线 + 预设对比 + 质量评估” |
| 5 | 内容发布要真实开发而非模拟 | 部分修复 | `content_publish` 已支持真实执行路径：`blog` 本地落盘（Markdown+HTML）+ 其它平台 webhook connector 发布 | 仍需补官方平台直连 connector（YouTube/抖音/小红书等） |
| 6 | NLE 交接是否丝滑/可唤起第三方 | 已修复 | `modules/capabilities/nle_handoff.py` + `/api/capabilities/refinement/*` 支持生成、唤起、导回 | 需补跨平台稳定性与失败重试 |
| 7 | n8n 风格节点 UI + 节点配置 | 部分修复 | 现有画布拖拽连线、节点编辑、历史与重跑（`apps/desktop/ui/index.html` + `app.js`） | 还缺通用节点参数 schema 驱动表单 |
| 8 | TTS 集成 | 已修复 | `modules/capabilities/audio_voice.py`（ElevenLabs 兼容）+ 对应 API 与测试 | 需补更多 TTS provider 可插拔 |
| 9 | 内嵌浏览播放器（非仅帧） | 已修复 | UI 含 `<video ... controls>` 用于粗剪/成片预览 | 需补播放器标注与段落跳转能力 |
| 10 | 可视化时间线编辑器 | 部分修复 | 有可视时间线展示（script timeline） | 仍缺拖拽裁剪/轨道编辑/吸附 |
| 11 | 拆解 `server.py` | 部分修复 | 新增 `modules/app_api/job_store.py`、`modules/app_api/migrations.py`、`modules/app_api/services/job_runtime.py`、`modules/app_api/services/idempotency_store.py`，并抽出 `routes/settings_routes.py`、`routes/system_routes.py`、`routes/library_routes.py`、`routes/workflow_routes.py`、`routes/job_routes.py`、`routes/capability_content_publish_routes.py`、`routes/capability_text_semantic_routes.py`、`routes/capability_social_export_routes.py`、`routes/capability_audio_voice_routes.py`、`routes/capability_editing_routes.py`、`routes/agent_capability_routes.py`、`routes/agent_skill_routes.py`、`routes/agent_observability_routes.py`、`routes/agent_task_query_routes.py`、`routes/agent_task_run_routes.py`、`routes/legacy_project_routes.py`、`routes/ui_routes.py` | `server.py` 已不再内联业务路由；任务调度/重任务队列与 capability 幂等存储已迁入 services。剩余待拆：agent 治理/计费服务层 |
| 12 | 拆解 `app.js/index.html` 组件化 | 部分修复 | 新增 `apps/desktop/ui/modules/workflow_builder_mixin.js`、`apps/desktop/ui/modules/runtime_mixin.js`、`apps/desktop/ui/modules/library_mixin.js`、`apps/desktop/ui/modules/settings_mixin.js`、`apps/desktop/ui/modules/agent_templates_mixin.js`、`apps/desktop/ui/modules/editing_capabilities_mixin.js`、`apps/desktop/ui/modules/semantic_publish_mixin.js`、`apps/desktop/ui/modules/distribution_audio_mixin.js`、`apps/desktop/ui/modules/material_semantics_mixin.js`、`apps/desktop/ui/modules/project_workflow_mixin.js`、`apps/desktop/ui/modules/capability_admin_mixin.js`、`apps/desktop/ui/modules/app_store.js`、`apps/desktop/ui/modules/common_utils_mixin.js`，将状态、7 步流程、能力治理（幂等缓存/Agent 观测）、n8n 连线工作流、运行时/API、素材库、设置、模板编辑、topic/text/refinement、语义发布、社媒音频与素材语义映射、公共工具方法从 `app.js` 抽离；`index.html` 改为多脚本装配 | `app.js` 由 6436 行降至 54 行；下一步是拆 `views/*` 与 `components/*`，完成展示层分离 |
| 13 | 持久化任务队列（非内存 `_jobs`） | 部分修复 | 任务状态已落库到 `app_state.db`（`jobs`/`job_events`），支持启动恢复与`/api/job/<id>`回读 | 执行队列仍为进程内调度；重启后任务需手动重试，不自动续跑 |
| 14 | SQLite schema 不硬编码，使用 migration | 部分修复 | 已引入 `modules/app_api/migrations.py` 并用于 `app_state.db` 版本化建表 | 仅覆盖 app_state；`library.db/topic_library` 仍需统一迁移体系 |
| 15 | Alpine.js CDN 离线不可用 | 已修复 | `apps/desktop/ui/vendor/alpine.min.js`；`index.html` 改本地引用 | 无 |
| 16 | README 过时 | 已修复 | `README.md` 已重写（桌面启动、能力列表、配置方式） | 需持续同步版本迭代 |
| 17 | 首次启动引导向导 | 已修复 | 前端新增首次引导弹层（AI Key/目录/功能概览）；`ui.onboarding_completed` 持久化 | 可继续增加分步状态与视频教程 |
| 18 | 前端术语不友好（开发者术语多） | 部分修复 | 新增“创作者术语模式”，关键入口文案切换 | 深层模块仍有技术术语（inline/workflow 等） |
| 19 | Capability 工作台 vs 7 步流程关系不明 | 部分修复 | 文案改为“创作工具台/连线编排”，引导中说明两者用途 | 还需更强制的场景推荐与一键切换提示 |
| 20 | 错误信息不友好 | 部分修复 | 前端 `friendlyErrorMessage()` + 后端全局异常兜底 + v0.3.5 404/405 返回 JSON 而非 HTML | 仍有部分接口返回原始技术错误 |
| 21 | 无认证机制（本地端口可被任意进程调用） | 部分修复 | 新增本地会话 token + CSRF 握手：`GET /api/session/bootstrap`，写请求校验 `X-VideoEditor-Token`/`X-VideoEditor-CSRF`，并校验 Origin | 仍需细粒度权限模型（按功能/角色） |
| 22 | 命令注入风险（FFmpeg等） | 部分修复 | 主要使用参数数组/ffmpeg-python，未见明显 shell 拼接 | 仍需系统级输入白名单审计与 fuzz |
| 23 | 无 CSRF 保护 | 已修复 | Flask `before_request` 对写请求强制 CSRF 头校验并限制本地 Origin；前端自动注入 `X-VideoEditor-CSRF` | 需后续补跨进程权限隔离策略 |
| 24 | 无输入长度限制 | 已修复 | `app.config["MAX_CONTENT_LENGTH"]` + 413 友好提示 + v0.3.3/v0.3.4 全路由数值参数边界检查 | 已基本完备 |
| 25 | API Key 明文存储 | 部分修复 | 新增 `modules/app_api/secure_store.py`，macOS 下优先写入系统 Keychain；`app_settings.json` 仅保存 `*_api_key_ref` 引用 | 非 macOS 或 Keychain 不可用时会降级明文（带 `secret_storage` 状态） |
| 26 | 无审计日志 | 部分修复 | 有任务历史与观测接口 | 缺系统级审计事件流（who/when/what） |
| 27 | 中英文混杂 | 部分修复 | 新增创作者术语模式，部分入口中文化 | 深层功能仍混杂英文枚举词 |
| 28 | 无响应式设计 | 部分修复 | 有部分布局适配与弹性网格 | 尚未形成完整断点策略 |
| 29 | 无 undo/redo | 部分修复 | 工作流画布已支持 `Ctrl/⌘+Z/Y` 与复制粘贴 | 非工作流区域仍无撤销机制 |
| 30 | 审核通过方式不友好（YAML gate） | 部分修复 | UI 侧可按钮触发审核动作 | 后端仍以 markdown/yaml gate 作为旧流程存储 |
| 31 | 字体过小，需可调 | 已修复 | 新增 `ui.font_scale` + 前端应用缩放（应用设置） | 可继续加预设（小/中/大/超大） |
| 32 | 渲染进度预估（ETA） | 部分修复 | `GET /api/job/<id>` 新增 `eta`（历史样本 + 实时进度混合估算），前端运行条与渲染日志已展示预计剩余时间 | 仍需引入文件大小/分辨率等特征回归模型，提升长任务精度 |
| 33 | （未给出具体项） | N/A | 原需求列表第 33 项为空 | 待补充具体内容 |

## 本轮新增落地（与上次相比）

1. 启动与环境
   - 新增 `start.command` 双击启动。
   - `launcher.py` 增加依赖自动检测/安装。
2. 设置与引导
   - 新增 `GET/POST /api/settings/ui`。
   - 新增“应用设置”卡（默认目录、字体缩放、术语模式、自动恢复项目）。
   - 新增首次引导弹层并可持久化完成状态。
3. 可用性与稳定性
   - 前端错误消息友好化映射。
   - 后端增加请求体大小限制与 413 友好提示。
4. 离线能力
   - Alpine.js 改本地 vendor 引用，移除 CDN 依赖。
5. 文档
   - `README.md` 已更新为当前桌面产品运行方式。
6. 发布与安全（新增）
   - `content_publish` 支持 connector 真实执行（webhook）与 blog 实际落盘。
   - 新增 `GET/POST /api/settings/publish` 维护发布连接器。
   - 新增本地 API token 机制（`/api/session/bootstrap`）。
7. 队列持久化与迁移（新增）
   - 新增 `modules/app_api/job_store.py`（SQLite 任务存储）与 `modules/app_api/migrations.py`（版本化迁移）。
   - 启动自动恢复历史任务；`running/queued` 会标记为 `interrupted`，避免假运行状态。
   - `/api/job/<job_id>` 支持从持久层按需回读历史任务。
8. 安全基线补充（新增）
   - `GET /api/session/bootstrap` 返回 `csrf_token`。
   - 写请求新增 CSRF 校验与 Origin 白名单校验。
   - 前端请求层自动携带 `X-VideoEditor-CSRF`，并在过期时自动重握手重试。
9. 后端拆分（新增）
   - 抽出 `modules/app_api/routes/settings_routes.py`，迁移 `session/bootstrap` 与 `settings/*` 路由。
   - 抽出 `modules/app_api/routes/system_routes.py`，迁移 `status/system/queue` 路由。
   - 抽出 `modules/app_api/routes/library_routes.py`，迁移 `/api/library/*` 路由。
   - 抽出 `modules/app_api/routes/workflow_routes.py`，迁移 `/api/workflows/*` 路由。
   - 抽出 `modules/app_api/routes/job_routes.py`，迁移 `/api/job/*` 查询与取消路由。
   - 抽出 `modules/app_api/routes/capability_content_publish_routes.py`，迁移 `content_publish` 能力路由。
   - 抽出 `modules/app_api/routes/capability_text_semantic_routes.py`，迁移 `subtitle_calibration`、`image_semantic`、`article_expand` 路由。
   - 抽出 `modules/app_api/routes/capability_social_export_routes.py`，迁移 `social_export` 全部路由。
   - 抽出 `modules/app_api/routes/capability_audio_voice_routes.py`，迁移 `audio_voice` 全部路由。
   - 抽出 `modules/app_api/routes/capability_editing_routes.py`，迁移 `topic_library/topic_copy/text_rough_cut/short_clip/refinement` 全部路由。
   - 抽出 `modules/app_api/routes/agent_capability_routes.py`，迁移 `/api/capabilities` 与 `/api/agent/capabilities`。
   - 抽出 `modules/app_api/routes/agent_skill_routes.py`，迁移 `/api/agent/skills/invoke`。
   - 抽出 `modules/app_api/routes/agent_observability_routes.py`，迁移 `/api/agent/observability*`。
   - 抽出 `modules/app_api/routes/agent_task_query_routes.py`，迁移 `/api/agent/tasks/<job_id>`、`/api/agent/tasks/history`、`/api/agent/tasks/<job_id>/export`、`/api/agent/tasks/<job_id>/replay`。
   - 抽出 `modules/app_api/routes/agent_task_run_routes.py`，迁移 `/api/agent/tasks/plan`、`/api/agent/tasks/run`。
   - 抽出 `modules/app_api/routes/legacy_project_routes.py`，迁移 `/api/init`、`/api/open_project`、`/api/approve/<int:step>`、`/api/run_step`、`/api/frames`、`/api/stage_files`、`/api/files/<path:rel>`、`/api/open_in_finder`、`/api/dialog/folder`、`/api/dialog/file`、`/api/script`、`/api/materials`。
   - 抽出 `modules/app_api/routes/ui_routes.py`，迁移 UI 静态路由 `/` 与 `/<path:filename>`。
   - `server.py` 目前保留 app factory、安全守卫与核心编排函数，不再承载业务路由实现。
10. 前端拆分（新增）
   - 新增 `apps/desktop/ui/modules/workflow_builder_mixin.js`，抽离工作流画布/节点连线/运行时状态/重跑等方法。
   - 新增 `apps/desktop/ui/modules/runtime_mixin.js`，抽离 `init`、会话握手、API 请求封装、任务轮询/取消逻辑。
   - 新增 `apps/desktop/ui/modules/library_mixin.js`，抽离素材库搜索/分页/本地与云端入库能力。
   - 新增 `apps/desktop/ui/modules/settings_mixin.js`，抽离 AI 设置、应用设置与首次引导逻辑。
   - 新增 `apps/desktop/ui/modules/agent_templates_mixin.js`，抽离 Agent 模板列表、批量变量回填、模板编辑/删除逻辑。
   - 新增 `apps/desktop/ui/modules/editing_capabilities_mixin.js`，抽离选题库、选题文案、文字粗剪、短视频快剪、NLE 交接/导回逻辑。
   - 新增 `apps/desktop/ui/modules/semantic_publish_mixin.js`，抽离字幕校准、图片语义、公众号扩写、发布文案、内容发布逻辑。
   - 新增 `apps/desktop/ui/modules/distribution_audio_mixin.js`，抽离社媒导出模板/计划/执行与配乐配音流水线逻辑。
   - 新增 `apps/desktop/ui/modules/material_semantics_mixin.js`，抽离素材加载、语义词典翻译与展示格式化逻辑。
   - 新增 `apps/desktop/ui/modules/project_workflow_mixin.js`，抽离项目创建/打开、7 步流程执行、审核与轮询、脚本编辑、渲染状态与导航逻辑。
   - 新增 `apps/desktop/ui/modules/capability_admin_mixin.js`，抽离能力工作台加载、能力入口治理、幂等缓存管理、Agent 观测与重放/导出逻辑。
   - 新增 `apps/desktop/ui/modules/app_store.js`，抽离全量初始化状态（store 首版），`app.js` 仅保留装配。
   - 新增 `apps/desktop/ui/modules/common_utils_mixin.js`，抽离模板 ID/区间表达式解析等公共工具方法。
   - `apps/desktop/ui/index.html` 改为装配式脚本加载，`app.js` 由 6436 行降至 54 行。
11. 密钥存储安全（新增）
   - 新增 `modules/app_api/secure_store.py`：统一 SecretStore 抽象，默认 `macOS Keychain` 后端。
   - AI 配置保存改为优先写 Keychain，设置文件仅保留 `openai_api_key_ref/anthropic_api_key_ref`。
   - `GET /api/settings/ai` 新增 `secret_storage` 字段，前端可感知当前密钥后端与可用性。
   - 新增测试覆盖：`tests/test_ai_settings_and_queue.py`（引用存储、清除、回读）。
12. ETA 预估（新增）
   - `GET /api/job/<job_id>` 增加 `eta` 字段（`remaining_seconds/source/confidence`）。
   - 估算策略：历史任务时长均值 + 当前进度实时估算混合。
   - 前端全局任务条与 Step7 执行日志增加“预计剩余时间”展示。
13. 任务调度服务化（新增）
   - 新增 `modules/app_api/services/job_runtime.py`，承接 `_run_in_bg`、重任务队列、异步 worker、恢复任务管理。
   - `server.py` 保留兼容函数签名，对外 API 与蓝图注入不变，内部改为委托 `JobRuntime`。
   - 回归：`pytest -q` 全量通过（`125 passed`）。
14. 幂等缓存服务化（新增）
   - 新增 `modules/app_api/services/idempotency_store.py`，承接 capability idempotency 的内存缓存与持久化读写、过期与裁剪逻辑。
   - `server.py` 的 `before_request/after_request` 改为委托服务，接口行为保持不变。
   - 回归：`tests/test_agent_api.py` 幂等相关用例通过 + 全量 `pytest -q` 通过。

## 回归结果

- `node --check apps/desktop/ui/app.js` 通过
- `python -m py_compile apps/desktop/launcher.py modules/app_api/server.py modules/app_api/job_store.py modules/app_api/migrations.py` 通过
- `pytest -q`：`146 passed`（v0.3.2-v0.3.5 新增 21 个测试）
