# 下一步开发计划（2026-03-01）

目标：把当前“功能可用”推进到“可维护、可发布、可扩展”的产品级状态。

当前增量（已完成）：
- 发布链路已从纯模拟升级为「Blog 真实落盘 + Webhook Connector 实际调用」。
- 本地 API 已加入 token 握手防护（桌面启动默认开启）。
- 写请求已加入 CSRF + Origin 校验，前端自动注入安全头。
- 任务状态已持久化到 SQLite（`jobs/job_events`），并在启动时自动恢复（未完成任务标记为 `interrupted`）。
- 已引入 SQLite migration runner（当前用于 `app_state.db`）。
- 已完成后端第八批拆分：`session/bootstrap`、`settings/*`、`status/system/queue`、`library/*`、`workflows/*`、`job/*`、`capabilities/content_publish/*`、`capabilities/subtitle_calibration/*`、`capabilities/image_semantic/*`、`capabilities/article_expand/*`、`capabilities/social_export/*`、`capabilities/audio_voice/*`、`capabilities/topic_library/*`、`capabilities/topic_copy/*`、`capabilities/text_rough_cut/*`、`capabilities/short_clip/*`、`capabilities/refinement/*`、`agent/capabilities`、`agent/skills/invoke`、`agent/observability*`、`agent/tasks(status/history/export/replay/plan/run)`、`legacy project routes`、`ui routes` 已迁移到独立 blueprints。
- 已完成前端首批拆分：新增 `apps/desktop/ui/modules/workflow_builder_mixin.js`、`apps/desktop/ui/modules/runtime_mixin.js`、`apps/desktop/ui/modules/library_mixin.js`，把连线工作流、运行时/API、素材库入库逻辑从 `app.js` 抽离，页面改为多脚本装配。
- 已完成前端第二批拆分：新增 `apps/desktop/ui/modules/settings_mixin.js`，把 AI 设置、应用设置、首次引导从 `app.js` 抽离。
- 已完成前端第三批拆分：新增 `apps/desktop/ui/modules/agent_templates_mixin.js`，把 Agent 模板列表/编辑/批量回填逻辑从 `app.js` 抽离。
- 已完成前端第四批拆分：新增 `apps/desktop/ui/modules/distribution_audio_mixin.js`，把社媒导出与配乐配音能力面板逻辑从 `app.js` 抽离。
- 已完成前端第五批拆分：新增 `apps/desktop/ui/modules/semantic_publish_mixin.js`，把字幕校准/图像语义/公众号扩写/发布文案/内容发布逻辑从 `app.js` 抽离。
- 已完成前端第六批拆分：新增 `apps/desktop/ui/modules/editing_capabilities_mixin.js`，把 topic/text/refinement 能力面板逻辑从 `app.js` 抽离。
- 已完成前端第七批拆分：新增 `apps/desktop/ui/modules/material_semantics_mixin.js`，把素材加载与语义词典映射逻辑从 `app.js` 抽离。
- 已完成前端第八批拆分：新增 `apps/desktop/ui/modules/project_workflow_mixin.js`，把项目创建/打开、7 步流程执行与轮询、脚本编辑、渲染状态与导航逻辑从 `app.js` 抽离。
- 已完成前端第九批拆分：新增 `apps/desktop/ui/modules/capability_admin_mixin.js`，把能力入口治理、幂等缓存、Agent 观测/重放/导出逻辑从 `app.js` 抽离。
- 已完成前端第十批拆分：新增 `apps/desktop/ui/modules/app_store.js`，把初始化状态从 `app.js` 抽离为 store 首版。
- 已完成前端第十一批拆分：新增 `apps/desktop/ui/modules/common_utils_mixin.js`，把模板 ID 与区间表达式工具方法从 `app.js` 抽离。
- 当前前端主文件规模：`app.js` 已降至 54 行（低于单文件 1200 行目标）。
- 已完成 AI Key 安全存储首版：新增 `modules/app_api/secure_store.py`，macOS 优先写入 Keychain，`app_settings.json` 仅保留 key 引用字段。
- 已完成任务调度服务化首版：新增 `modules/app_api/services/job_runtime.py`，`_run_in_bg`、重任务队列与 worker 执行已迁移。
- 已完成幂等存储服务化首版：新增 `modules/app_api/services/idempotency_store.py`，capability idempotency 读写/过期/裁剪逻辑已迁移。

### v0.3.1 增量（2026-03-01）
- **P0.4 OpenCV 帧读取安全上限**：`beauty.py`、`pipeline.py`、`auto_render.py` 三个文件的 `while True` 循环改为 `while idx < max_frames`，`max_frames = max(2 * 报告帧数, fps * 600)`，防止损坏视频导致无限循环。
- P2.8（README 重写）和 P2.9（Blog 真实导出）在 main 分支已有，无需移植。
- 回归验证：136/136 测试通过。
- 详见 `docs/changelog-v0.3.1.md`。

### v0.3.2–v0.3.5 增量（2026-03-02）
- **v0.3.2 安全边界测试**：新增 S1-S3 安全测试（伪造 CSRF→403、不存在 job→404、缺失 token→401），验证安全守卫完备。
- **v0.3.3 输入验证增强**：为 `capability_editing`/`idempotency`/`social_export` 路由中 10+ 个数值参数添加 try/except + 边界检查。
- **v0.3.4 测试覆盖**：新增 5 个 GET 端点测试（status/system_load/tasks_queue/library_stats/workflows_catalog）；补全 `audio_voice` 混音参数 + `content_publish` 会话过期时间边界。
- **v0.3.5 JSON 错误响应**：404/405/通用 HTTPException 全部改为 JSON 响应，替代 Flask 默认 HTML。
- 回归验证：146/146 测试通过。
- 详见 `docs/changelog-v0.3.1.md`。

### v0.3.6 SQLite 连接泄漏修复（2026-03-02）
- **SQLite 连接泄漏修复**：`job_store.py`/`migrations.py`/`topic_library.py` 全部改为显式 `conn.close()`，消除 ResourceWarning。
- 回归验证：146/146 测试通过，0 warnings。
- 详见 `docs/changelog-v0.3.1.md`。

### v0.3.7 资源泄漏防护 + 错误处理增强（2026-03-02）
- **cv2 资源异常安全**：`beauty.py`/`pipeline.py`/`auto_render.py`/`video_asset_toolkit.py` 的 VideoCapture/Writer 全部加 `try/finally` 防护。
- **裸 except 修复**：`video_asset_toolkit.py` 3 处 `except:` 改为具体异常类型。
- **静默异常日志化**：`job_runtime.py` 3 处 `except: pass` 改为 `traceback.print_exc()`。
- 回归验证：146/146 测试通过，0 warnings。
- 详见 `docs/changelog-v0.3.1.md`。

### v0.3.8 子进程超时 + 裸 except 修复（2026-03-02）
- **subprocess 超时防护**：`auto_render.py`(8处)/`pipeline.py`(2处)/`rough_cut.py`(2处)/`video_asset_toolkit.py`(1处) 全部添加 `timeout` 参数。
- **裸 except 修复第二批**：`search_videos.py`(3处) + `materials_mapper.py`(1处)。
- 回归验证：146/146 测试通过，0 warnings。
- 详见 `docs/changelog-v0.3.1.md`。

### v0.3.9 进程管理 + 临时目录清理（2026-03-02）
- **Popen→subprocess.run**：`workflow.py`(3处) + `legacy_project_routes.py`(2处) 消除僵尸进程风险。
- **临时目录 try/finally**：`workflow.py:_run_render()` 渲染异常时保证清理。
- **裸 except 修复第三批**：`jianying_draft.py`(1处)。
- 回归验证：146/146 测试通过，0 warnings。
- 详见 `docs/changelog-v0.3.1.md`。

### v0.3.10 参数解析工具 + POST 端点测试覆盖（2026-03-02）
- **新增 `param_utils.py`**：`parse_int_param()` + `parse_float_param()` 通用解析工具。
- **新增 4 个测试**：参数工具边界 + 编辑能力端点项目依赖 + topic_library inline 模式。
- 回归验证：150/150 测试通过，0 warnings。
- 详见 `docs/changelog-v0.3.1.md`。

### v0.3.11 参数解析统一 + subprocess 超时补全 + 裸 except 修复（2026-03-02）
- **路由参数解析统一**：7 个路由文件 24 处重复的 try/except+clamp 模式替换为 `parse_int_param()`/`parse_float_param()`。
- **subprocess 超时补全**：`server.py`（osascript 120s）+ `frame_preview.py`（FFmpeg 30s）。
- **裸 except 修复第四批**：legacy_lab 5 处 `except:` → `except Exception:`。
- 回归验证：150/150 测试通过，0 warnings。
- 详见 `docs/changelog-v0.3.1.md`。

## Phase 1（高优先，1-2 周）

1. 真实发布引擎（替换模拟）
   - 交付：在现有 connector 抽象层上补官方平台适配器（平台适配器 + 会话管理 + 回执标准化）
   - 范围：`youtube / xiaohongshu / douyin / wechat_channels`（`blog` 已完成）
   - 验收：真实发布成功可回写 `post_id/url`，会话过期转 `waiting_auth`

2. 安全基础线
   - 交付：细粒度权限模型（按 capability/敏感动作限制）
   - 交付：安全事件审计（token/CSRF失败、origin拦截、敏感操作）
   - 交付：敏感操作审计日志（发布/删除/导出/设置变更）
   - 验收：越权操作可拦截，安全日志可检索与导出

3. 队列恢复体验增强（持久化后续）
   - 交付：重启后“中断任务”批量重试入口 + 失败原因分类
   - 交付：任务详情页显示“来源于恢复/实时运行”标记
   - 验收：重启后用户可一键恢复工作，不需手工查找历史

## Phase 2（高优先，2-3 周）

1. 架构拆分（后端）
   - 交付：将 `server.py` 拆分为：
     - `routes/settings.py`
     - `routes/library.py`
     - `routes/capabilities/*.py`
     - `routes/workflows.py`
     - `services/jobs.py`
   - 当前：路由层已拆分完成（包含 `agent-task-run` 与 `legacy-project`）；`server.py` 无内联 `@app.route`
   - 当前：任务调度已迁移到 `services/job_runtime.py`（`_run_in_bg/_dispatch_heavy_queue_locked` 已服务化）
   - 下一步：迁移 agent 治理/计费/模板逻辑到 `services/agent_runtime.py`
   - 验收：`server.py` 仅保留 app factory、守卫与依赖装配

2. 架构拆分（前端）
   - 交付：将 `app.js/index.html` 拆成模块：
     - `stores/app-store.js`
     - `views/analysis-view.js`
     - `views/production-hub-view.js`
     - `views/workflow-view.js`
     - `components/*`
   - 当前：`workflow builder`、`runtime(api/session)`、`library ingest/search`、`settings/onboarding`、`project flow(step1-7)`、`capability governance`、`state store` 已拆到 `modules/*.js`
   - 下一步：引入 `views/*` + `components/*`，把展示层从 `index.html` 完整拆分
   - 验收：单文件不超过 1200 行，功能回归全通过

3. Migration 体系
   - 交付：引入 schema migration runner（版本号+升级脚本）
   - 覆盖：`app_settings`、`topic_library`、`global_media_library`（`jobs` 已接入）
   - 验收：新旧库自动升级，失败可回滚

## Phase 3（中优先，2 周）

1. 可视化时间线编辑器 v1
   - 交付：轨道视图（视频/字幕/音频）+ 拖拽裁剪 + 吸附
   - 验收：可完成“粗剪-字幕-配音”基本编辑并回写计划

2. 美颜与审美增强 v2
   - 交付：人脸区域分级磨皮、肤色保护、场景 LUT 预设
   - 验收：提供 A/B 对比预览与导出质量评分

3. 渲染 ETA 预估
   - 当前：已交付 v1（`/api/job/<id>.eta`，历史样本 + 实时进度混合估算，前端已展示）
   - 下一步：引入文件大小/分辨率/时长等特征模型，校准长任务 ETA
   - 验收：长任务 ETA 误差控制在可接受范围（<35%）

## Phase 4（中优先，持续）

1. 术语与体验统一
   - 全面替换技术术语默认文案，保留“高级模式”展开
   - 优化 Capability 与流程模式的场景引导

2. 响应式与可访问性
   - 完整断点（13/14/16 寸）
   - 字号、对比度、键盘可达性

3. 安全与合规
   - API Key 改为系统凭据存储（macOS Keychain）: 已完成首版
   - 下一步：补 Windows Credential Manager / Linux Secret Service 后端，消除降级明文场景
   - 命令参数审计与黑/白名单策略

## 本周执行顺序（建议）

1. `content_publish` connector 抽象 + YouTube/Blog 真实发布首版
2. `services/agent_runtime.py` 落地，迁移技能执行/预算治理逻辑
3. 前端落地 `views + components` 分层（先拆 `workflow-view.js` 与能力面板组件）
4. 迁移体系扩展到 `library/topic/settings` 三类数据库

## 风险与依赖

1. 平台发布 API 的官方限制与账号风控策略差异大，需分平台推进。
2. 本地自动化发布（浏览器驱动）需要额外稳定性与风控兜底。
3. 大文件架构拆分需分批进行，避免一次性改动过大。
