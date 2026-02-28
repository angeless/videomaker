# Capability API（模块化能力接口）

更新时间：2026-02-25
服务：`modules/app_api/server.py`

## 1. 概览

新增 API 允许独立调用以下能力，不再只能通过 Step1~7 串行触发：

- 选题库（数据库）
- 选题 + 文案
- 文字粗剪
- 短视频快剪
- 视频精剪策略
- 字幕校准（中英+时间轴）
- 图片语义分析与检索
- 微信公众号文章扩写
- 社媒导出配置
- 内容发布（dry_run / 真实发布）
- 配乐与配音规划

所有 `/api/capabilities/*` 接口现已支持统一上下文（可选）：

- `actor_type`: `human | agent`
- `actor_id`
- `run_mode`: `interactive | headless`
- `idempotency_key`（POST 可用于幂等重放）
- `trace_id`
- `input_mode`: `project | inline`（新增能力默认支持）

幂等缓存持久化：

- 缓存文件：`data/capability_idempotency_cache.json`
- 行为：`POST /api/capabilities/*` 成功响应会写入缓存；同 `idempotency_key` 重复请求可直接重放（`idempotency.replayed=true`）。
- 默认 TTL：7 天（过期项不会被重放，可通过管理接口清理）。

并在响应中统一返回：

- `request_context`
- `plan_summary`
- `artifacts`
- `warnings`
- `idempotency`（含 `key/replayed`）

## 2. 接口清单

### 2.1 能力注册信息

- `GET /api/capabilities`
  返回全部 capability 定义和旧 step 映射关系。

- 通用可选上下文字段（所有 `/api/capabilities/*` 与 `/api/agent/*`）  
  可通过 Query / JSON / Header（`X-*`）传入：`actor_type`, `actor_id`, `run_mode`, `idempotency_key`, `trace_id`。  
  响应会统一带回 `request_context`。

- `GET /api/capabilities/idempotency/cache`
  查询幂等缓存记录（`source=memory|persisted|merged`，支持 `ttl_seconds/include_expired/limit/offset`，并支持按 `actor_id/endpoint/idempotency_key/project_path` 过滤，`match_mode=contains|exact`；返回 `stats.has_more` 便于翻页）。

- `POST /api/capabilities/idempotency/cache/prune`
  清理幂等缓存（支持 `remove_expired`、`clear_memory`、`clear_persisted`、`max_entries`、`ttl_seconds`）。

### 2.2 选题库

- `GET /api/capabilities/topic_library?q=&category=&tags=&limit=60`
  查询选题库。

- `POST /api/capabilities/topic_library`
  新增/更新选题模板。

- `POST /api/capabilities/topic_library/bootstrap`
  从当前项目 `data/materials.json` 自动生成选题模板。

说明：

- 三个接口均支持 `input_mode=project|inline`。
- `inline` 可直接传 `topics` / `materials`，不依赖项目目录或 `topic_library.db`。

### 2.3 选题 + 文案

- `POST /api/capabilities/topic_copy/draft`
  入参：`slug`, `target_duration_s`
  输出：`data/topic_copy_draft.json`

说明：

- 支持 `input_mode=project|inline`。
- `inline` 可直接传 `topic`/`topics` + `materials`（或 `material_semantics`）。

### 2.4 文字粗剪

- `GET /api/capabilities/text_rough_cut/source`
  返回脚本字幕的逐句清单（含 `index/start/end/text`），用于 Descript 风格逐句勾选。

- `POST /api/capabilities/text_rough_cut/plan`
  入参：`removed_phrases`, `target_duration_s`, `merge_gap_s`, `keep_span_indexes`, `drop_span_indexes`, `apply_removed_phrases`
  说明：`keep_span_indexes` / `drop_span_indexes` 支持 `1,2,5-8` 这种句号区间写法，支持 Filmora/Descript 类“按文本句子删改”。
  输出：`data/text_rough_plan.json`

说明：

- 支持 `input_mode=project|inline`。
- `inline` 可直接传 `script/subtitles/spans`。

### 2.5 快剪（高光提炼）

- `POST /api/capabilities/short_clip/plan`
  入参：`target_duration_s`, `max_clips`
  输出：`data/short_clip_plan.json`

说明：

- 支持 `input_mode=project|inline`。
- `inline` 可直接传 `candidates` 或 `script/clips`。

### 2.6 精剪策略

- `POST /api/capabilities/refinement/plan`
  入参：`style`, `editor`, `quality`
  可选编辑器：`internal_ffmpeg`, `davinci`, `finalcut`, `premiere`, `jianying`

- `POST /api/capabilities/refinement/handoff`
  入参：`editor`, `title`, `fps`
  输出：`data/nle_handoff/<editor>/` 下的交接文件（FCPXML / EDL / manifest）

- `POST /api/capabilities/refinement/execute`
  入参：`editor`, `title`, `fps`, `launch`, `app_name`, `timeout_seconds`
  行为：先生成交接包，再按本机平台拉起外部编辑器（macOS 默认通过 `open -a` 调用 Final Cut / Premiere / DaVinci / 剪映）。
  输出：`data/refinement_execute_last.json`

- `POST /api/capabilities/refinement/collect_master`
  入参：`editor`, `source_video`, `output_name`, `copy_mode`
  行为：把外部 NLE 导出的成片导回项目 `output/`（默认目标 `output/final.mp4`），供后续社媒导出直接复用。
  输出：`data/refinement_collect_last.json`

说明：

- `handoff/execute/collect_master` 均支持 `input_mode=project|inline`。
- `inline` 需显式传 `script/materials`（以及可选 `output_dir` / `source_video`）。

### 2.6.1 发布文案准备（增强）

- `GET /api/capabilities/publish_prep/profiles`
- `POST /api/capabilities/publish_prep/profiles`
- `POST /api/capabilities/publish_prep/generate`

新增参数：

- `input_mode=project|inline`
- `platform_content_type=video_post|article_post`
- `use_llm`
- `llm_provider`
- `llm_model`

平台覆盖（文案）：

- 国内：`xiaohongshu`、`ixigua`、`douyin`、`wechat_channels`、`wechat_mp`
- 海外：`youtube`、`instagram`、`twitter`、`threads`、`facebook`
- 自定义：`blog`
- 兼容：`tiktok`、`bilibili`

### 2.7 社媒导出

- `GET /api/capabilities/social_export/profiles`
  返回平台导出规格模板（内置 + 自定义模板；基础模板含：TikTok短视频、微信短视频、抖音短视频、小红书短视频、微信公众号、B站视频、YouTube视频）。

- `GET /api/capabilities/social_export/specs`
  返回平台导出技术规格（包含分辨率/帧率/码率/最大时长 + 容器/编码/像素格式 + 常用别名 + 说明）。

- `GET /api/capabilities/social_export/templates`
  返回自定义导出模板列表（`project` 模式读取 `data/social_export_templates.json`；`inline` 模式读取请求内 `templates/profile_overrides`）。

- `POST /api/capabilities/social_export/templates`
  入参：`platform_id`, `name`, `width`, `height`, `fps`, `video_bitrate`, `audio_bitrate`, `max_duration_s`
  行为：新增或更新自定义模板。

- `DELETE /api/capabilities/social_export/templates/<template_id>`
  删除指定自定义模板。

基础模板规格（当前内置）：

| 平台ID | 名称 | 分辨率 | 帧率 | 视频码率 | 音频码率 | 最大时长 |
|---|---|---|---|---|---|---|
| `tiktok` | TikTok短视频 9:16 | 1080x1920 | 30fps | 10M | 192k | 600s |
| `wechat_short` | 微信短视频 9:16 | 1080x1920 | 30fps | 10M | 192k | 180s |
| `douyin` | 抖音短视频 9:16 | 1080x1920 | 30fps | 12M | 192k | 180s |
| `xiaohongshu` | 小红书短视频 9:16 | 1080x1920 | 30fps | 10M | 192k | 300s |
| `wechat_mp` | 微信公众号视频 16:9 | 1920x1080 | 30fps | 10M | 192k | 1800s |
| `bilibili` | B站视频 16:9 | 1920x1080 | 30fps | 16M | 256k | 14400s |
| `youtube` | YouTube视频 16:9 | 1920x1080 | 30fps | 16M | 192k | 43200s |

扩展模板（平台矩阵补齐）：`ixigua`、`wechat_channels`、`instagram`、`twitter`、`threads`、`facebook`、`blog`，并支持别名归一（如 `thread -> threads`、`微信号 -> wechat_channels`）。

- `GET /api/capabilities/social_export/history`
  返回导出历史批次（`project` 模式来自 `workflow.json`；`inline` 模式可传 `history`）。

- `POST /api/capabilities/social_export/validate_source`
  入参：`input_video`, `platforms`, `strict_duration_limit`, `ffprobe_bin`
  行为：对源视频做平台规格校验，输出每个平台是否需要截断/补边缩放/升采样/FPS 转换等操作。
  输出：`data/social_export_validation_last.json`

- `POST /api/capabilities/social_export/plan`
  入参：`input_video`, `platforms`, `quality`, `output_dir`, `strict_duration_limit`
  输出：导出任务计划 JSON（同时写入 `data/social_export_plan.json`）
  当 `strict_duration_limit=true` 时，若源视频超平台上限，会在计划里标记 `trim_applied=true` 并自动加截断参数。

- `POST /api/capabilities/social_export/run`
  入参同 `plan`，后台任务方式执行实际转码导出（返回 `job_id`）

- `POST /api/capabilities/social_export/rerun`
  入参：`batch_id`（可选覆盖 `platforms/quality/ffmpeg_bin/timeout_seconds`）
  用历史批次参数直接复跑，返回新的 `job_id`。

说明：

- 全部社媒导出接口支持 `input_mode=project|inline`。
- `inline` 下 `plan/validate_source/run` 需显式传 `input_video`；`rerun` 可直接传 `batch`。

### 2.8 配乐和配音

- `POST /api/capabilities/audio_voice/plan`
  入参：`mood`
  输出：`data/audio_voice_plan.json`

- `POST /api/capabilities/audio_voice/pick_bgm`
  入参：`mood`, `bgm_provider`, `target_duration_s`, `bgm_library_dir`, `bgm_library_dirs`, `bgm_endpoint`, `bgm_api_key`, `bgm_download`, `bgm_cache_enabled`, `bgm_force_refresh`, `bgm_cache_max_age_days`, `bgm_strict_schema`, `max_candidates`
  行为：自动匹配背景音乐。支持本地曲库 (`local_library`) 与远端 HTTP 兼容接口 (`elevencreative_compatible`)。
  输出：`data/audio_voice_bgm_last.json`

- `POST /api/capabilities/audio_voice/synthesize`
  入参：`mood`, `provider`, `voice_id`, `api_key`, `model_id`, `output_dir`, `dry_run`, `timeout_seconds`
  行为：基于字幕分段执行配音合成（当前支持 ElevenLabs），输出音频片段到项目目录。
  输出：`data/audio_voice_synthesize_last.json`

- `POST /api/capabilities/audio_voice/build_track`
  入参：`segments`, `output_audio`, `ffmpeg_bin`, `dry_run`
  行为：按字幕时间线把配音片段自动拼成单条旁白轨（默认输出 `data/audio_voice/narration_timeline.m4a`）。
  输出：`data/audio_voice_timeline_last.json`

- `POST /api/capabilities/audio_voice/mix_master`
  入参：`mood`, `input_video`, `narration_audio`, `bgm_audio`, `auto_pick_bgm`, `bgm_provider`, `bgm_library_dir`, `bgm_library_dirs`, `bgm_endpoint`, `bgm_api_key`, `bgm_download`, `bgm_cache_enabled`, `bgm_force_refresh`, `bgm_cache_max_age_days`, `bgm_strict_schema`, `bgm_loop`, `bgm_fade_out_s`, `output_video`, `replace_master`, `origin_volume`, `narration_volume`, `bgm_volume`, `enable_ducking`, `ducking_threshold`, `ducking_ratio`, `ducking_attack_ms`, `ducking_release_ms`, `dry_run`
  行为：把旁白轨（可叠加 BGM）混到母版视频，可选覆盖 `output/final.mp4`，支持自动 Ducking；当 `bgm_audio` 为空且 `auto_pick_bgm=true` 时自动选配乐。`bgm_audio` 可为本地路径或远端 URL；`bgm_loop=true` 时会将本地 BGM 循环铺满视频并按 `bgm_fade_out_s` 片尾淡出（远端 URL 默认降级为单次混音）。
  输出：`data/audio_voice_mix_last.json`

- `POST /api/capabilities/audio_voice/run`
  入参：综合 `synthesize + build_track + mix_master` 三步参数（含 `auto_pick_bgm` / `bgm_provider` / `bgm_library_dir` / `bgm_cache_enabled` / `bgm_force_refresh` / `bgm_cache_max_age_days` / `bgm_strict_schema` / `bgm_loop`）。
  行为：后台一键执行“配音合成 -> 旁白轨 -> 自动配乐（可选）-> 混音到成片”，返回 `job_id` 轮询进度。
  输出：`data/audio_voice_pipeline_last.json`

说明：

- 全部音频能力接口支持 `input_mode=project|inline`。
- `inline` 模式建议显式传 `script/segments/input_video` 等输入，避免读取项目缓存文件。

### 2.8.1 字幕校准（新增）

- `POST /api/capabilities/subtitle_calibration/plan`
- `POST /api/capabilities/subtitle_calibration/run`

关键参数：

- `input_mode=project|inline`
- `subtitles[]`
- `mode=text_only|timeline_align`
- `translation=off|zh2en|en2zh|bilingual`
- `use_llm`（可选）

关键输出：

- `calibrated_subtitles[]`
- `timeline_changes[]`
- `quality_report`

### 2.8.2 图片语义（新增）

- `POST /api/capabilities/image_semantic/analyze`
- `POST /api/capabilities/image_semantic/search`

说明：

- 对接全局媒体库语义分析/检索能力
- 支持单图、批量图片与语义查询

### 2.8.3 微信公众号文章扩写（新增）

- `POST /api/capabilities/article_expand/generate`

关键输出：

- `title_candidates`
- `lead`
- `sections[]`
- `cta`
- `keywords`
- `markdown`

### 2.8.4 内容发布（新增）

- `GET /api/capabilities/content_publish/platforms`
- `POST /api/capabilities/content_publish/session/bootstrap`
- `POST /api/capabilities/content_publish/plan`
- `POST /api/capabilities/content_publish/run`
- `POST /api/capabilities/content_publish/rerun`

能力特性：

- `dry_run` 与真实发布双模式
- 会话过期自动返回 `waiting_auth`（扫码续登提示）
- 默认启用“模拟人类行为”节流策略
- Blog 默认输出 `Markdown+Frontmatter` 与 `HTML`

### 2.9 Agent 入口（已实现）

- `GET /api/agent/capabilities`
  返回 capability 清单 + 每个 capability 的 agent 路由映射 + `request_context_schema`。

Agent 执行入口补充：

- `POST /api/agent/tasks/plan`
- `POST /api/agent/tasks/run`
- `POST /api/agent/skills/invoke`

默认输入模式：

- 若 `input.input_mode` 未传，系统会按运行环境自动补齐：
  - 项目已加载：`project`
  - 未加载项目：`inline`

调用示例：

- 见 [agent-capability-inline-examples.md](/Users/angelwang/videoeditor/docs/agent-capability-inline-examples.md)（每能力 1 个最小可运行请求）。

- `POST /api/agent/tasks/plan`
  入参：`capability_id`, `input`, `dry_run`（可选），以及通用上下文字段。
  行为：生成单能力任务计划（不执行），返回标准化 `task_plan`（含 primary_call 与可用路由）。
  也支持 `mode=skill_sequence` + `skills[]` 生成 Skill 计划（支持 `strategy=sequential|parallel|conditional`）。
  额度治理：读取 `data/agent_governance.json`，按 `default -> actor -> capability -> actor+capability` 收紧预算与并发。
  动态额度：会叠加 `data/agent_governance_usage.json` 的历史建议额度（tighten only）。

- `POST /api/agent/tasks/run`
  入参：`capability_id`, `input`（或直接传 `task_plan`），可选 `action`, `dry_run`。
  行为：按计划异步执行单能力任务，返回 `job_id`。
  也支持执行 `mode=skill_sequence`：
  - `skills[]` 每步可定义 `skill_id`, `input`, `retry_policy`, `timeout_seconds`, `continue_on_error`, `condition`
  - 流程级可选 `budget_limit`：`max_steps`, `max_failures`, `max_duration_seconds`
  - 当前支持策略：`strategy=sequential|parallel|conditional`
  - `parallel` 可传 `max_parallel`（默认 4）
  - `conditional` 的 `condition` 字段支持：`depends_on`, `status_in`, `require_all`, `if_overall_ok`
  - 若显式参数超出治理额度，会返回 400（`治理校验失败`）
  - 非 `dry_run` 执行完成后会自动写入 `data/agent_governance_usage.json`，用于后续动态额度收紧
  - 每个 skill 步骤会记录 `usage_tokens + estimated_cost`（估算）并汇总到治理 usage
  - 成本估算支持 `data/agent_cost_model.json`（`default -> provider default -> provider model` 命中费率）
  - 动态额度支持自动调优：基于 `recent_runs` 最近窗口按失败率/成本/时长趋势收紧或放宽建议额度

- `GET /api/agent/tasks/<job_id>`
  行为：查询 Agent 任务状态、进度、日志、结果。
  说明：当内存中任务已清理时，会自动回退到 `data/agent_task_history.json` 返回历史摘要视图（`source=history`）。
  历史回退时若存在 `step_summaries`，会重建 `chain_view.nodes/edges`（含条件依赖边），便于失败定位。
  返回增强：`chain_view`（跨能力链路聚合），包含 `nodes/edges/counts/totals`，统一覆盖：
  - `single_capability`
  - `skill_sequence`
  - `skill_invoke`

- `GET /api/agent/tasks/history`
  入参：`actor_id`、`status`、`task_mode`、`kind`、`capability_id`、`skill_id`、`trace_id`、`replay_supported`、`since`、`until`、`sort=desc|asc`、`limit`、`offset`（均可选）。
  行为：按过滤条件查询 Agent 历史任务列表（分页），返回 `total_count/returned_count/has_more/items`。
  结果项会包含基础审计字段（`failed_nodes`）以及步骤摘要（`step_summaries`，如可用）。
  数据来源：`data/agent_task_history.json`。

- `POST /api/agent/tasks/<job_id>/export`
  入参：`format=json|csv`、`include_logs`（默认 `true`）、`include_result`（默认 `true`）。
  行为：导出单任务审计快照；优先导出内存任务，若任务已回收则自动从 `data/agent_task_history.json` 导出。
  输出：`data/agent_task_export_<job_id>_*.json|csv`。

- `POST /api/agent/tasks/<job_id>/replay`
  入参：`payload_overrides`（可选）、`context_overrides`（可选）、`clear_idempotency`（默认 `true`）、`new_trace_id`（可选）。
  行为：复用任务创建时记录的 replay 元数据，重放同一 Agent 任务/Skill 调用，并允许按需覆盖参数。支持从内存任务与历史文件 `data/agent_task_history.json` 回放。
  返回：重放请求快照 + 下游响应；若成功启动新任务，会返回 `new_job_id`；`source` 标记回放来源（`memory|history`）。

- `GET /api/agent/observability`
  入参：`actor_id`（可选）、`status`、`task_mode`、`kind`、`capability_id`、`skill_id`、`trace_id`、`replay_supported`、`since`、`until`、`limit`（默认 200）、`top_n`（默认 5）、`include_items`（默认 `false`）。
  行为：返回 Agent 历史任务聚合统计（成功率、重试率、模板命中率、失败 TopN）。
  数据来源：`data/agent_task_history.json`（任务完成后自动回写）。

- `POST /api/agent/observability/export`
  入参：`format=json|csv`、`actor_id`（可选）、`status`、`task_mode`、`kind`、`capability_id`、`skill_id`、`trace_id`、`replay_supported`、`since`、`until`、`limit`、`top_n`。
  行为：导出观测快照，落盘到 `data/agent_observability_*.json|csv`。

- `GET /api/agent/templates`
  入参：`capability_id`（可选）、`scope`（可选）、`actor_id`（可选）、`include_system`（默认 `true`）、`resolve`（默认 `true`）。
  行为：返回 Agent 模板列表，支持 `system/project/agent` 分层读取；`agent` 层按 `actor_id` 隔离。
  当 `resolve=true` 时，响应会补充：
  - `effective_content`：按 `base_template_id + content + overrides` 合并后的最终参数
  - `template_chain`：继承链路
  - `resolve_warnings`：变量缺失/类型不匹配/循环继承等告警

- `POST /api/agent/templates`
  入参：`template_id`, `name`, `capability_id`, `scope`, `actor_id`, `tags`, `content`, `base_template_id`, `overrides`, `variables`。
  行为：创建或更新 Agent 模板。`scope=system` 为只读，禁止写入。
  约束：
  - `base_template_id` 需在当前作用域可见（Agent: agent/project/system；Project: project/system）
  - `variables` 支持字段：`key`, `type`, `required`, `default`, `enum`, `minimum`, `maximum`
  - 若 `content/overrides` 中变量值违反约束，会在写入阶段直接返回 400

- `DELETE /api/agent/templates/<template_id>`
  入参：`scope`（必填），`actor_id`（当 `scope=agent` 时必填，可从上下文继承）。
  行为：删除 `project/agent` 模板。`scope=system` 为只读，禁止删除。

- `POST /api/agent/skills/invoke`
  入参：`skill_id`, `input`, `timeout_seconds`（可选）, `retry_policy`（可选，支持 `max_retries/backoff_ms/retry_on_http`）。
  行为：异步触发单个 Agent Skill（当前映射到已有 capability 路由），返回 `job_id` 并通过 `/api/agent/tasks/<job_id>` 轮询。
  输出：结构化 `result`，包含 `skill_id`, `capability_id`, `primary_call`, `attempts`, `status_code`, `response`。

### 2.10 自定义工作流编排（新增）

目标：

- 支持把内部已有 capability 自定义拼接成节点图，顺序与分支路由可配置；
- 支持“人用工作台”与“Agent API”统一调用；
- 支持执行计划预览、异步执行、执行历史与失败重跑（含失败分支恢复）。

接口：

- `GET /api/workflows/catalog`
  返回可编排能力目录（`capability_id -> actions -> method/endpoint`）。

- `GET /api/workflows`
  返回已保存的工作流定义（支持 `workflow_id` 过滤）。

- `POST /api/workflows`
  创建/更新工作流定义。

- `DELETE /api/workflows/<workflow_id>`
  删除指定工作流定义。

- `POST /api/workflows/plan`
  生成执行计划（不执行），会解析每个节点主调用路由。
  输出包含 `plan.graph`（`nodes/edges/transitions/start_step_id/has_cycle/unreached_nodes`），用于工作流图预览与校验。

- `POST /api/workflows/run`
  异步执行工作流，返回 `job_id` 与 `run_id`。

- `GET /api/workflows/runs`
  查询历史执行（支持分页与 `workflow_id` 过滤）。

- `GET /api/workflows/runs/<run_id>`
  查询单次执行详情。

- `POST /api/workflows/runs/<run_id>/rerun`
  重跑历史执行，支持 `rerun_failed_only=true`。
  当启用时会自动裁剪为“失败节点 + 到失败节点的必要上游依赖链”，并重算子工作流入口 `start_step_id`。
  返回 `rerun_context`（`mode/source_run_id/failed_step_ids/included_step_ids/start_step_id`）用于审计。

节点字段（`steps[]`）：

- `step_id`
- `node_type=action|condition`
- `capability_id`（`action` 节点必填）
- `action`（默认 `auto`）
- `input`（支持模板变量）
- `input_mode=auto|project|inline`
- `run_if`（仅 `action`，可选）
- `condition`（仅 `condition`，可选；默认按 truthy 计算）
- `continue_on_error`
- `enabled`
- `save_as`（把节点结果保存到 `vars.<save_as>`）
- `next_step_id`（默认跳转）
- `next_on_success`
- `next_on_error`
- `next_on_skip`

工作流附加字段：

- `start_step_id`（可选，指定入口节点；留空默认首节点）

模板变量（在 `input` 内）：

- `{{steps.<step_id>.response...}}`
- `{{steps.<step_id>.status}}`
- `{{last.response...}}`
- `{{workflow.input.<key>}}`
- `{{vars.<save_as>...}}`

能力工作台（桌面端）：

- 已提供节点卡片式编辑（新增 action/condition、删除、上下移动、启停、失败继续）。
- 已提供轻量画布视图（节点顺序可拖拽、箭头连线展示、当前节点聚焦编辑）。
- 已提供分支路由编辑：`next_step_id / next_on_success / next_on_error / next_on_skip`。
- 已提供 capability/action 下拉选择与默认模板输入。
- 保留原始 JSON 高级编辑入口，并支持“编辑器 -> JSON / JSON -> 编辑器”同步。

执行结果（`run`）关键字段：

- `execution_path[]`：本次实际走过的节点路径（按执行顺序）
- `steps[].status`：`done|error|skipped|unreached`

持久化文件：

- 定义：`data/custom_workflows.json`
- 历史：`data/custom_workflow_runs.json`

## 3. 与现有工作流关系

- Step2 会自动把素材语义同步到 `data/topic_library.db`，并把选题库摘要加入选题 prompt。
- Step6 粗剪已升级为 “文字粗剪 + 高光快剪” 组合策略，并生成 `preview/rough_plan.json`。
- 桌面端 `制作视频` 页面已加入“能力工作台”，可直接调用上述 capability API 并查看 JSON 输出。
- 精剪模块支持生成外部 NLE 交接包（DaVinci/Final Cut/Premiere）。
- 社媒导出模块支持生成计划并后台执行导出任务。
- 社媒导出执行结果会回写 `workflow.json`（`social_export_history`），并同步落盘 `data/social_export_history.json`。

## 4. Agent 兼容扩展（Roadmap，已实现基础能力 + 后续增强）

为满足“保留人用习惯，同时兼容 Agent 调用”，当前已提供 Agent API 基础能力，后续重点是治理与编排增强。核心策略：

- 人与 Agent 共用同一 capability 内核，避免实现分叉。
- 对现有接口优先采用“可选字段扩展”，不破坏当前调用。
- Agent 场景增加幂等、审计、模板覆盖与 Skill 编排能力。

已实现的 Agent 基础能力：

- 通用上下文扩展：`actor_type`, `actor_id`, `run_mode`, `idempotency_key`, `trace_id`
- Agent 路由：`/api/agent/capabilities`、`/api/agent/tasks/plan`、`/api/agent/tasks/run`、`/api/agent/tasks/<job_id>`
- 模板路由：`GET/POST/DELETE /api/agent/templates`
- Skill 路由：`POST /api/agent/skills/invoke`
- 运行统计与成本估算：`data/agent_governance_usage.json`（token/时长/估算成本）
- 成本模型配置：`data/agent_cost_model.json`（按 provider/model 精细计费）
- 自动调优窗口：`data/agent_governance_usage.json` 的 `recent_runs`（最近运行快照，默认保留 16 条）

前端看板可视化（已实现）：

- 入口：桌面端 `能力工作台 -> Agent观测`
- 支持：`actor_id`/`limit`/`top_n` 以及 `status/task_mode/capability/skill/replay_supported/since/until` 筛选、成功率与成本指标卡、模板/失败 TopN、最近任务明细
- 支持观测导出：JSON/CSV（调用 `POST /api/agent/observability/export`）
- 支持任务重放：在最近任务列表中一键重放（调用 `POST /api/agent/tasks/<job_id>/replay`）
- 支持失败定位：失败 TopN 可一键回填筛选；任务详情可查看 `chain_view/result`、重放当前任务、导出任务快照。
- 模板工作台（已实现）：桌面端 `能力工作台 -> Agent模板`
  - 支持模板筛选、继承链 `template_chain` 与解析告警 `resolve_warnings` 可视化
  - 支持批量变量回填（对勾选模板批量写入 `content/overrides`）
  - 支持单模板新建/编辑/删除（调用 `GET/POST/DELETE /api/agent/templates`）

详细见：`docs/agent-usability-roadmap-v1.md`。
