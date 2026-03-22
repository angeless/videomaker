# VideoEditer 完整产品系统设计文档（可复刻实施版）

版本：v1.0  
发布日期：2026-02-28  
适用仓库：`/Users/angelwang/videoeditor`

## 1. 文档目标与复刻原则

本文档目标不是“介绍产品”，而是“给出可直接复刻同一产品的实施规范”。

复刻原则：
1. 单模块可独立调用：所有能力均可 `input_mode=inline` 独立运行，不依赖工作流文件。
2. 人用体验不回归：保留现有桌面 UI 和 Step1~7 使用习惯。
3. Agent 兼容默认内建：同一能力内核暴露 `/api/capabilities/*` 与 `/api/agent/*` 双入口。
4. 数据与行为可审计：幂等缓存、任务历史、导出快照、重放链路必须可用。
5. 约束优先于灵活性：平台枚举、别名、状态机、错误策略按本文件固定，不做隐式变化。

## 2. 产品范围与边界

### 2.1 当前阶段（必须实现）

能力模块（Capability）拆分与 API First：
1. `topic_library`：选题库（数据库能力）
2. `topic_copy`：选题+文案
3. `text_rough_cut`：文字粗剪
4. `short_clip`：短视频快剪
5. `refinement`：视频精剪策略 + 外部 NLE 交接
6. `social_export`：社媒导出（多平台规格）
7. `publish_prep`：发布文案准备（标题/描述/关键词）
8. `subtitle_calibration`：中英文字幕校准（含时间轴与可选翻译）
9. `image_semantic`：图片语义分析/检索
10. `article_expand`：微信公众号文章扩写
11. `audio_voice`：配乐与配音
12. `content_publish`：跨平台内容发布（dry_run + 真实发布）

### 2.2 暂缓范围（明确不做）

1. 并行执行子图与循环节点（当前工作流版本不支持）
2. 重新设计/替换现有人用流程

### 2.3 未来路线（已纳入 Roadmap）

在当前能力稳定后，进入 Agent 易用性增强：
1. 保留人用习惯不变
2. 提升 Agent 自定义模板与 Skill 编排能力
3. 让多 Agent 系统可直接调单能力 API（而非必须走工作流）

## 3. 总体架构

## 3.1 运行时组件

1. `apps/desktop/launcher.py`：桌面入口（pywebview + Flask）
2. `modules/app_api/server.py`：统一 API 服务层（Flask）
3. `modules/workflow_engine/workflow.py`：7 步工作流执行器
4. `modules/capabilities/*`：模块化能力内核
5. `modules/library/global_media_library.py`：全局素材语义库（SQLite + 可选向量）

## 3.2 架构分层

1. UI 层：`apps/desktop/ui/index.html` + `app.js`
2. API 层：`server.py`（路由、任务、上下文、幂等、Agent）
3. 能力层：`modules/capabilities/*.py`
4. 工作流层：`workflow_engine/workflow.py`（兼容旧 Step 流）
5. 数据层：项目目录 `data/` + 全局库 `.video_library/library.db`

## 3.3 目录规范（复刻必须）

项目运行目录（每个项目实例）：
1. `data/`：中间 JSON、缓存、模板、历史
2. `reviews/`：人工审核 markdown（YAML gate）
3. `preview/`：预览帧与粗剪视频
4. `output/`：成片与导出文件
5. `workflow.json`：流程状态主文件

全局数据目录：
1. `.video_library/library.db`：素材库主数据库
2. `.video_library/app_settings.json`：AI 设置
3. `.video_library/cache/gdrive/`：云端缓存

## 4. 关键设计决策（固定）

1. 能力统一支持 `input_mode=project|inline`
2. POST 能力接口支持 `idempotency_key` 幂等回放
3. 所有 `/api/capabilities*` 与 `/api/agent*` 响应统一携带 `request_context`
4. 发布平台枚举固定，中文别名强制归一
5. 内容发布支持 `dry_run` 与 live 双模式
6. Blog 输出必须双格式：`Markdown+Frontmatter` 与 `HTML`
7. `微信号` 固定映射 `wechat_channels`
8. `thread` 固定映射 `threads`
9. LLM 无可用 key 时必须降级规则引擎并输出 warning

## 5. 平台矩阵（最终版）

### 5.1 文案/发布平台矩阵

国内：
1. `xiaohongshu`
2. `ixigua`
3. `douyin`
4. `wechat_channels`
5. `wechat_mp`

国外：
1. `youtube`
2. `instagram`
3. `twitter`
4. `threads`
5. `facebook`

自定义：
1. `blog`

### 5.2 社媒导出基础模板（内置）

1. TikTok短视频：`tiktok`，1080x1920，30fps，10M，192k，600s
2. 微信短视频：`wechat_short`，1080x1920，30fps，10M，192k，180s
3. 抖音短视频：`douyin`，1080x1920，30fps，12M，192k，180s
4. 小红书短视频：`xiaohongshu`，1080x1920，30fps，10M，192k，300s
5. 微信公众号视频：`wechat_mp`，1920x1080，30fps，10M，192k，1800s
6. B站视频：`bilibili`，1920x1080，30fps，16M，256k，14400s
7. YouTube视频：`youtube`，1920x1080，30fps，16M，192k，43200s

### 5.3 扩展导出模板（内置）

1. `ixigua`
2. `wechat_channels`
3. `instagram`
4. `twitter`
5. `threads`
6. `facebook`
7. `blog`
8. `youtube_shorts`
9. `instagram_reels`

## 6. 统一请求上下文与幂等协议

## 6.1 `request_context`

可从 JSON / Query / Header(`X-*`) 传入：
1. `actor_type`: `human|agent`
2. `actor_id`
3. `run_mode`: `interactive|headless`
4. `idempotency_key`
5. `trace_id`

## 6.2 能力统一响应补充字段

1. `request_context`
2. `plan_summary`
3. `artifacts`
4. `warnings`
5. `idempotency`：`{key,replayed,source?}`

## 6.3 幂等持久化

1. 内存缓存：`_capability_idempotency_cache`
2. 项目落盘：`data/capability_idempotency_cache.json`
3. TTL：7 天
4. 缓存 key：`{project_anchor}|{path}|{actor_id}|{idempotency_key}`
5. 管理接口：
   1. `GET /api/capabilities/idempotency/cache`
   2. `POST /api/capabilities/idempotency/cache/prune`

## 7. API 总览（实施清单）

### 7.1 系统与工作流

1. `GET /api/status`
2. `GET /api/system/load`
3. `POST /api/init`
4. `POST /api/open_project`
5. `POST /api/approve/<step>`
6. `POST /api/run_step`
7. `GET /api/job/<job_id>`
8. `POST /api/job/<job_id>/cancel`

### 7.2 素材库

1. `GET /api/library/stats`
2. `GET /api/library/search`
3. `POST /api/library/assets`
4. `POST /api/library/preview/local`
5. `POST /api/library/ingest/local`
6. `POST /api/library/preview/local/images`
7. `POST /api/library/ingest/local/images`
8. `POST /api/library/preview/gdrive`
9. `POST /api/library/ingest/gdrive`
10. `POST /api/library/preview/gdrive/images`
11. `POST /api/library/ingest/gdrive/images`

### 7.3 Capability

1. `GET /api/capabilities`
2. `GET/POST /api/capabilities/topic_library`
3. `POST /api/capabilities/topic_library/bootstrap`
4. `POST /api/capabilities/topic_copy/draft`
5. `GET /api/capabilities/text_rough_cut/source`
6. `POST /api/capabilities/text_rough_cut/plan`
7. `POST /api/capabilities/short_clip/plan`
8. `POST /api/capabilities/refinement/plan`
9. `POST /api/capabilities/refinement/handoff`
10. `POST /api/capabilities/refinement/execute`
11. `POST /api/capabilities/refinement/collect_master`
12. `GET/POST /api/capabilities/publish_prep/profiles`
13. `POST /api/capabilities/publish_prep/generate`
14. `POST /api/capabilities/subtitle_calibration/plan`
15. `POST /api/capabilities/subtitle_calibration/run`
16. `POST /api/capabilities/image_semantic/analyze`
17. `POST /api/capabilities/image_semantic/search`
18. `POST /api/capabilities/article_expand/generate`
19. `GET /api/capabilities/content_publish/platforms`
20. `POST /api/capabilities/content_publish/session/bootstrap`
21. `POST /api/capabilities/content_publish/plan`
22. `POST /api/capabilities/content_publish/run`
23. `POST /api/capabilities/content_publish/rerun`
24. `GET /api/capabilities/social_export/profiles`
25. `GET /api/capabilities/social_export/specs`
26. `GET/POST /api/capabilities/social_export/templates`
27. `DELETE /api/capabilities/social_export/templates/<template_id>`
28. `GET /api/capabilities/social_export/history`
29. `POST /api/capabilities/social_export/validate_source`
30. `POST /api/capabilities/social_export/plan`
31. `POST /api/capabilities/social_export/run`
32. `POST /api/capabilities/social_export/rerun`
33. `POST /api/capabilities/audio_voice/plan`
34. `POST /api/capabilities/audio_voice/pick_bgm`
35. `POST /api/capabilities/audio_voice/synthesize`
36. `POST /api/capabilities/audio_voice/build_track`
37. `POST /api/capabilities/audio_voice/mix_master`
38. `POST /api/capabilities/audio_voice/run`

### 7.4 Agent

1. `GET /api/agent/capabilities`
2. `POST /api/agent/tasks/plan`
3. `POST /api/agent/tasks/run`
4. `GET /api/agent/tasks/<job_id>`
5. `GET /api/agent/tasks/history`
6. `POST /api/agent/tasks/<job_id>/export`
7. `POST /api/agent/tasks/<job_id>/replay`
8. `GET /api/agent/observability`
9. `POST /api/agent/observability/export`
10. `GET/POST /api/agent/templates`
11. `DELETE /api/agent/templates/<template_id>`
12. `POST /api/agent/skills/invoke`

## 8. Capability 详细规格（可复刻）

## 8.1 `topic_library`

目标：选题模板数据库化。

数据存储：`data/topic_library.db`，表 `topic_templates`。

字段：
1. `slug`(unique)
2. `title`
3. `category`
4. `audience`
5. `hook_style`
6. `outline_template`
7. `tags`(逗号字符串)
8. `enabled`
9. `updated_at`

行为：
1. `GET` 支持 `q/category/tags/include_disabled/limit`
2. `POST` Upsert by `slug`
3. `bootstrap` 从 `materials.semantic` 自动生成最多 30 条模板

`inline` 行为：直接从请求 `topics[]` 过滤/更新，不写 SQLite。

## 8.2 `topic_copy`

目标：选题 + 素材语义 => 文案草稿。

算法（确定性 fallback）：
1. 收集语义信号：`setting/activity/mood/time_of_day/weather/narrative_role`
2. 生成 `hook/outline/cta`
3. 输出 `CopyDraft`

输出主字段：
1. `title`
2. `hook`
3. `outline[]`
4. `narration_style`
5. `target_duration_s`
6. `cta`
7. `matched_signals[]`

落盘：`data/topic_copy_draft.json`（project 模式）。

## 8.3 `text_rough_cut`

目标：通过文字删除/保留生成粗剪时间线。

输入关键字段：
1. `spans[]` 或 `script/subtitles`
2. `removed_phrases`
3. `target_duration_s`
4. `merge_gap_s`
5. `keep_span_indexes`
6. `drop_span_indexes`
7. `apply_removed_phrases`

核心算法：
1. `normalize_spans`：排序、过滤非法区间
2. 按规则打标：`not_in_keep_set / in_drop_set / contains_removed_phrase`
3. 保留片段按 `merge_gap_s` 合并
4. 若设置 `target_duration_s`，按顺序裁剪总时长

扩展语法：`keep/drop` 支持 `1,2,5-8`。

输出关键字段：
1. `segments[]`
2. `duration_s`
3. `kept_spans[]`
4. `decisions[]`
5. 计数：`removed_by_phrase_count/removed_by_selection_count`

落盘：`data/text_rough_source.json`、`data/text_rough_plan.json`。

## 8.4 `short_clip`

目标：从候选高光片段提炼短视频时间线。

算法：
1. 候选按 `(score, -duration)` 降序
2. 贪心选取，不允许重叠（`min_gap_s`）
3. 超预算时裁剪最后一段
4. 最终按开始时间排序输出

输入关键字段：
1. `candidates[]`（含 `start/end/score/reason`）
2. `target_duration_s`
3. `max_clips`

输出：`clips[] + total_duration_s`。

落盘：`data/short_clip_plan.json`。

## 8.5 `refinement` + `nle_handoff`

目标：精剪策略输出 + 外部编辑器协同。

`refinement/plan`：
1. `style`：`travel_story|cinematic|clean_vlog`
2. `editor`：`internal_ffmpeg|davinci|finalcut|premiere|jianying`
3. `quality`：影响转场/磨皮强度

输出：`transition_style/color_profile/skin_smooth_strength/notes`。

`handoff`：
1. 从 `script.clips + materials` 生成 `TimelineClip[]`
2. 支持交接格式：`.fcpxml`、`.edl`、`timeline_manifest.json`
3. 按编辑器选择输出优先级

`execute`：
1. 先生成 handoff
2. macOS 用 `open -a <AppName>` 启动外部 NLE

`collect_master`：
1. 导回外部成片到项目 `output/`
2. 支持 `copy|move`
3. 写入 `data/refinement_collect_last.json`

落盘：
1. `data/refinement_plan.json`
2. `data/nle_handoff/<editor>/...`
3. `data/refinement_execute_last.json`
4. `data/refinement_collect_last.json`

## 8.6 `publish_prep`

目标：为多平台生成发布文案包（标题/正文/关键词）。

配置：
1. 内置 `DEFAULT_PROMPT_PROFILES`
2. 别名归一 `PLATFORM_ALIASES`
3. 覆盖文件：`data/publish_prep_profiles.json`

接口：
1. `GET profiles`：返回合并后 profile
2. `POST profiles`：保存覆盖
3. `POST generate`：支持 `use_llm` 与规则 fallback

新增字段：
1. `platform_content_type`: `video_post|article_post`
2. `use_llm`
3. `llm_provider`
4. `llm_model`

输入来源（project）：
1. 若缺 `script_text/voiceover_text`，自动回退读取 `script_matched.json/script_draft.json`

LLM 降级规则：无 key 时返回 warning 并 fallback。

落盘：`data/publish_prep_last.json`。

## 8.7 `subtitle_calibration`

目标：中英字幕校准（文本与时间轴）。

输入关键字段：
1. `mode`: `text_only|timeline_align`
2. `translation`: `off|zh2en|en2zh|bilingual`
3. `subtitles[]`
4. `source_audio`（预留）
5. `use_llm`（run 接口）

核心算法：
1. 字幕归一（补时长、修正负值）
2. `timeline_align`：按时间排序，解决重叠，最小 gap `0.03s`
3. 翻译：优先 LLM translator，失败用规则前缀 `[EN]/[中]`
4. 生成 `quality_report`

输出关键字段：
1. `calibrated_subtitles[]`
2. `timeline_changes[]`
3. `text_changes[]`
4. `quality_report`

落盘：`data/subtitle_calibration_last.json`。

## 8.8 `image_semantic`

目标：统一对接全局素材库图片语义能力。

接口：
1. `analyze`：单图/批量分析
2. `search`：语义检索

行为：
1. `auto_ingest=true` 时先入库再检索
2. 无 library 注入时提供占位语义输出（不中断）
3. 输出字段统一：`semantic_tags/semantic_keywords/scene_description/mood/...`

落盘：
1. `data/image_semantic_analyze_last.json`
2. `data/image_semantic_search_last.json`

## 8.9 `article_expand`

目标：微信公众号文章扩写。

输入字段：
1. `source_text`
2. `key_points`
3. `tone`
4. `length_target`
5. `title_count`
6. `use_llm`

输出字段：
1. `title_candidates[]`
2. `lead`
3. `sections[]`
4. `cta`
5. `keywords[]`
6. `markdown`

LLM 策略：可选，失败降级规则生成。

落盘：`data/article_expand_last.json`。

## 8.10 `social_export`

目标：按平台规格导出高质量成片。

核心能力：
1. profile/spec 查询
2. 自定义模板增删改
3. 源视频规格校验
4. 导出计划生成
5. 后台导出执行
6. 历史批次查询与复跑

编解码固定：
1. container: `mp4`
2. video: `h264`
3. audio: `aac`
4. pixel: `yuv420p`

`build_ffmpeg_export_cmd`：
1. 强制 `scale+pad+fps`
2. CRF 随质量映射：`premium=16/high=18/medium=22/draft=28`
3. `strict_duration_limit=true` 时超长自动 `-t` 截断

历史与模板落盘：
1. `data/social_export_templates.json`
2. `data/social_export_plan.json`
3. `data/social_export_validation_last.json`
4. `data/social_export_history.json`
5. `workflow.json.social_export_history`

## 8.11 `audio_voice`

目标：配音、配乐、音轨构建、成片混音一体化。

子能力：
1. `plan`
2. `pick_bgm`
3. `synthesize`
4. `build_track`
5. `mix_master`
6. `run`（后台流水线）

配音：
1. provider：`elevenlabs|elevenlabs_compatible`
2. API key 来源：请求体或 `ELEVENLABS_API_KEY`

BGM provider：
1. `local_library`
2. `elevencreative_compatible`（HTTP）

远端 BGM 特性：
1. 可选自动下载
2. 缓存命中/强制刷新/过期控制
3. 严格 schema 校验开关

混音策略：
1. 原声 + 旁白 + BGM（可选）
2. Ducking（`sidechaincompress`）自动降级
3. `bgm_loop` + `bgm_fade_out_s`
4. 输入输出同路径时使用临时文件防覆盖

落盘：
1. `data/audio_voice_plan.json`
2. `data/audio_voice_bgm_last.json`
3. `data/audio_voice_synthesize_last.json`
4. `data/audio_voice_timeline_last.json`
5. `data/audio_voice_mix_last.json`
6. `data/audio_voice_pipeline_last.json`

## 8.12 `content_publish`

目标：跨平台发布计划与执行。

核心对象：
1. Platform profile（区域、支持能力）
2. Session（会话、过期、认证状态）
3. Plan（步骤、策略、状态）
4. Run record（run_id、结果、重跑来源）

状态机：
1. 计划：`planned` / `waiting_auth`
2. 执行总体：`running -> posted|failed|blocked|waiting_auth|planned(dry_run)`
3. 单步：`planned|posted|failed|blocked|waiting_auth|dry_run|skipped`

默认策略：
1. `simulate_human_behavior=true`
2. `random_delay_ms=[800,2600]`
3. `input_jitter=true`
4. `action_throttle_per_minute=18`
5. `risk_protection=true`

会话策略：
1. session 过期或未认证，live run 返回 `waiting_auth`
2. 返回 `auth_hint=扫码续登`

Blog 特例：始终确保 `markdown_frontmatter + html` 双格式。

落盘：
1. `data/content_publish_sessions.json`
2. `data/content_publish_plan_last.json`
3. `data/content_publish_run_last.json`
4. `data/content_publish_history.json`

## 9. Agent 适配规范

## 9.1 Skill 注册（内置）

关键新增 Skill：
1. `skill.subtitle_calibration.run`
2. `skill.image_semantic.analyze`
3. `skill.article_expand.generate`
4. `skill.content_publish.run`

同时保留：`topic_library/topic_copy/text_rough_cut/short_clip/social_export/audio_voice/publish_prep` 等技能。

## 9.2 任务模式

1. `single_capability`
2. `skill_sequence`
   1. `strategy=sequential`
   2. `strategy=parallel`
   3. `strategy=conditional`

## 9.3 治理与预算

配置文件：
1. `data/agent_governance.json`
2. `data/agent_governance_usage.json`
3. `data/agent_cost_model.json`

预算字段：
1. `max_steps`
2. `max_failures`
3. `max_duration_seconds`
4. `max_parallel`

策略：tighten-only（仅收紧）。

## 9.4 Agent 审计与回放

1. 历史：`data/agent_task_history.json`
2. 单任务导出：`/api/agent/tasks/<job_id>/export`
3. 观测导出：`/api/agent/observability/export`
4. 回放：`/api/agent/tasks/<job_id>/replay`
5. 回放源：`memory|history`

## 10. 旧 7 步工作流（兼容保留）

步骤状态：`not_started|pending|running|waiting_review|done|error`

步骤定义：
1. Step1 选择素材：生成 `data/materials.json`，人工审核 `reviews/01_materials.md`
2. Step2 选题：生成 topics，审核 `reviews/02_topics.md`
3. Step3 脚本：生成 `data/script_draft.json`，审核 `reviews/03_script.md`
4. Step4 素材匹配：生成 `data/script_matched.json`，审核 `reviews/04_matching.md`
5. Step5 帧预览：输出 `preview/frames/*`，自动通过
6. Step6 粗剪：输出 `preview/rough_cut.mp4` + `preview/rough_plan.json`，审核 `reviews/05_render_options.md`
7. Step7 精渲染：输出 `output/final.mp4`

渲染降级机制（高负载/超时）：
1. L1：`preset=ultrafast`、提高 CRF、降 FPS、关部分特效
2. L2：进一步降分辨率、降 FPS、关调色增强

## 11. 桌面 UI 规范（保留人用习惯）

UI 技术栈：
1. `pywebview`
2. `Flask`
3. `Alpine.js`

顶层模块：
1. 素材语义分析
2. 制作视频

制作视频页包含 Capability Workbench，Tab 至少包括：
1. `topic_library`
2. `topic_copy`
3. `text_rough_cut`
4. `short_clip`
5. `refinement`
6. `subtitle_calibration`
7. `image_semantic`
8. `article_expand`
9. `content_publish`
10. `social_export`
11. `audio_voice`
12. `agent_observability`
13. `agent_templates`
14. `custom_workflow`

要求：
1. UI 调用 capability API，不绕过服务层
2. UI 不改变已有 Step 操作路径
3. 新模块以“能力工作台”方式增量接入

## 12. 数据模型与数据库

## 12.1 全局素材库 `.video_library/library.db`

表 `assets`（主资产）：
1. `uid` PK
2. `sha256` unique
3. `phash`
4. `filename`
5. `primary_path`
6. `source_type`
7. 技术字段：`duration/size_bytes/resolution/width/height/fps/codec`
8. 语义字段：`scene_description/mood/objects_json/analysis_json`
9. 扩展语义：`semantic_json/semantic_text/keywords_json/semantic_version`
10. `created_at/updated_at`

表 `asset_locations`：
1. `id` PK
2. `uid` FK
3. `path` unique
4. `source_type/source_ref`
5. `is_available`
6. `last_seen_at`

表 `asset_embeddings`：
1. `uid` PK FK
2. `model`
3. `embedding_json`
4. `embedding_dim`
5. `content_hash`
6. `embedding_version`
7. `updated_at`

检索模式：`keyword|vector|hybrid`，hybrid 使用 RRF + lexical/vector 加权。

## 12.2 项目级关键 JSON 文件

1. `workflow.json`
2. `data/materials.json`
3. `data/script_draft.json`
4. `data/script_matched.json`
5. `preview/rough_plan.json`
6. `data/social_export_*.json`
7. `data/content_publish_*.json`
8. `data/agent_*.json`
9. `data/capability_idempotency_cache.json`

## 13. 配置与环境变量

AI 设置优先顺序：请求体 > `.video_library/app_settings.json` > 环境变量。

关键环境变量：
1. `OPENAI_API_KEY`
2. `OPENAI_BASE_URL`
3. `OPENAI_MODEL`
4. `OPENAI_EMBEDDING_MODEL`
5. `ANTHROPIC_API_KEY`
6. `ELEVENLABS_API_KEY`
7. `ELEVENCREATIVE_BGM_ENDPOINT`
8. `ELEVENCREATIVE_API_KEY`
9. `VIDEOEDITOR_DISABLE_VISION_ENRICH`
10. `VIDEOEDITOR_DISABLE_SEMANTIC_LLM`

## 14. 后台任务与并发控制

后台 job 种类：
1. `workflow_step`
2. `library_ingest_*`
3. `social_export`
4. `audio_voice`
5. `agent_task`
6. `agent_skill`

重任务互斥：
1. 若已有重任务运行，`social_export/run` 与 `audio_voice/run` 返回 409。

取消机制：
1. `POST /api/job/<job_id>/cancel`
2. 内部取消标记 `CANCEL_TOKEN="__CANCELLED__"`

## 15. 错误处理与降级策略

1. LLM 缺 key：降级规则引擎 + warning
2. 外部 NLE 不可用：返回可操作错误，不影响内部流程
3. BGM 远端失败：返回错误或降级本地库
4. ffmpeg filter 缺失：ducking 自动降级普通混音
5. session 过期：发布能力进入 `waiting_auth`
6. 幂等缓存过期：不重放，正常新执行

## 16. 安全与合规控制（实现要求）

1. API key 不在响应中明文返回（前端仅展示 masked/是否已设置）
2. 仅在项目目录写入项目级数据
3. 上传/路径输入必须做绝对路径解析与存在性检查
4. Agent 受治理策略限制（能力黑名单、预算、并发）

## 17. 测试与验收标准

对应测试文件：
1. `tests/test_capabilities.py`
2. `tests/test_publish_prep.py`
3. `tests/test_publish_prep_api.py`
4. `tests/test_agent_api.py`
5. `tests/test_subtitle_calibration.py`
6. `tests/test_article_expand.py`
7. `tests/test_content_publish.py`
8. `tests/test_custom_workflow.py`

验收项（必须全部通过）：
1. 每个 capability 在 `input_mode=inline` 可独立执行
2. 字幕：`text_only` 不改轴，`timeline_align` 消除重叠
3. 图片语义：分析与检索均返回结构化字段
4. 公众号扩写：标题/导语/章节/CTA/关键词/markdown 完整
5. 发布文案：平台别名归一、平台差异化输出
6. 内容发布：`dry_run` 与 `waiting_auth` 逻辑正确
7. 社媒导出：基础模板+扩展模板+规格校验+复跑可用
8. Agent：新能力可 plan/run/history/export/replay

## 18. 复刻步骤（按顺序执行）

1. 克隆仓库并安装依赖：`pip install -r requirements.txt`
2. 安装系统依赖：`ffmpeg`、`ffprobe`
3. 启动桌面端：`python /Users/angelwang/videoeditor/apps/desktop/launcher.py`
4. 新建项目，检查 `data/reviews/preview/output/workflow.json` 自动创建
5. 运行 Step1~7 验证旧流程
6. 在能力工作台逐项验证 12 个 capability
7. 用 `input_mode=inline` 跑关键 API 验证解耦能力
8. 用 Agent API 跑 `single_capability` 与 `skill_sequence`
9. 验证幂等：同 `idempotency_key` 重放命中
10. 验证发布链路：`publish_prep -> content_publish(plan/run)`

## 19. 未来 Roadmap（锁定）

当前功能稳定后启动：
1. Agent 易用性深化
2. 模板层高级能力（更细粒度变量约束与批量策略）
3. Skill 编排治理强化（预算/成本/失败恢复）
4. 工作流增强：并行子图、循环审批节点、可视化边连线编辑

约束：
1. 不替换现有人用流程
2. 所有新能力先落地为可独立调用 API

## 20. 完成定义（Definition of Done）

当满足以下条件，视为“完整可复刻”：
1. 项目初始化、Step 流程、Capability 调用、Agent 调用均可运行
2. 平台矩阵完整覆盖：
   1. 国内：小红书、西瓜视频、抖音、微信号、微信公众号
   2. 国外：YouTube、Instagram、Twitter、Threads、Facebook
   3. 自定义：Blog
3. 文档中的所有落盘文件、接口路由、状态行为与仓库实现一致
4. 新团队成员仅凭本文件即可搭建同构系统并通过测试用例

## 21. 附录 A：关键数据契约（Canonical Contract）

以下契约用于确保不同团队实现结果一致。

### 21.1 `workflow.json`（最小完整骨架）

```json
{
  "version": 1,
  "project_dir": "/abs/path/to/project",
  "videos_dir": "/abs/path/to/videos",
  "current_step": 1,
  "steps": {
    "1": {"status": "pending", "review_status": null},
    "2": {"status": "not_started", "review_status": null},
    "3": {"status": "not_started", "review_status": null},
    "4": {"status": "not_started", "review_status": null},
    "5": {"status": "not_started", "review_status": null},
    "6": {"status": "not_started", "review_status": null},
    "7": {"status": "not_started", "review_status": null}
  },
  "config": {
    "use_semantic_index": false,
    "ai_provider": null,
    "ai_base_url": null,
    "ai_model": null,
    "render": {
      "width": 1080,
      "height": 1920,
      "fps": 30
    }
  }
}
```

### 21.2 Capability 响应统一外壳（POST/GET）

```json
{
  "ok": true,
  "request_context": {
    "actor_type": "agent",
    "actor_id": "planner_1",
    "run_mode": "headless",
    "idempotency_key": "idem_001",
    "trace_id": "trace_001"
  },
  "plan_summary": {},
  "artifacts": [],
  "warnings": [],
  "idempotency": {
    "key": "idem_001",
    "replayed": false
  }
}
```

### 21.3 `content_publish` 计划对象（Canonical）

```json
{
  "plan_id": "p_123456",
  "created_at": "2026-02-28T10:00:00",
  "input_mode": "project",
  "status": "planned",
  "dry_run": true,
  "content_type": "video_post",
  "platform_ids": ["xiaohongshu", "blog"],
  "session": {
    "session_id": "sess_001",
    "authenticated": true,
    "expired": false,
    "expires_at": "2026-02-28T12:00:00"
  },
  "strategy": {
    "simulate_human_behavior": true,
    "random_delay_ms": [800, 2600],
    "input_jitter": true,
    "action_throttle_per_minute": 18,
    "risk_protection": true
  },
  "steps": []
}
```

### 21.4 `content_publish` 运行记录（Canonical）

```json
{
  "run_id": "r_123456",
  "requested_at": "2026-02-28T10:01:00",
  "plan_id": "p_123456",
  "input_mode": "project",
  "result": {
    "status": "posted",
    "dry_run": false,
    "summary": {
      "total": 2,
      "posted": 2,
      "failed": 0,
      "blocked": 0
    },
    "steps": []
  }
}
```

## 22. 附录 B：能力到落盘文件映射（必须一致）

1. `topic_library`：`data/topic_library.db`
2. `topic_copy`：`data/topic_copy_draft.json`
3. `text_rough_cut`：`data/text_rough_source.json`、`data/text_rough_plan.json`
4. `short_clip`：`data/short_clip_plan.json`
5. `refinement`：
   1. `data/refinement_plan.json`
   2. `data/nle_handoff/<editor>/...`
   3. `data/refinement_execute_last.json`
   4. `data/refinement_collect_last.json`
6. `publish_prep`：
   1. `data/publish_prep_profiles.json`
   2. `data/publish_prep_last.json`
7. `subtitle_calibration`：`data/subtitle_calibration_last.json`
8. `image_semantic`：
   1. `data/image_semantic_analyze_last.json`
   2. `data/image_semantic_search_last.json`
9. `article_expand`：`data/article_expand_last.json`
10. `content_publish`：
   1. `data/content_publish_sessions.json`
   2. `data/content_publish_plan_last.json`
   3. `data/content_publish_run_last.json`
   4. `data/content_publish_history.json`
11. `social_export`：
   1. `data/social_export_templates.json`
   2. `data/social_export_validation_last.json`
   3. `data/social_export_plan.json`
   4. `data/social_export_history.json`
12. `audio_voice`：
   1. `data/audio_voice_plan.json`
   2. `data/audio_voice_bgm_last.json`
   3. `data/audio_voice_synthesize_last.json`
   4. `data/audio_voice_timeline_last.json`
   5. `data/audio_voice_mix_last.json`
   6. `data/audio_voice_pipeline_last.json`
13. Agent 治理与审计：
   1. `data/agent_governance.json`
   2. `data/agent_governance_usage.json`
   3. `data/agent_cost_model.json`
   4. `data/agent_task_history.json`

## 23. 附录 C：Agent 主调度契约（固定）

### 23.1 `/api/agent/tasks/plan`

单能力请求最小体：
```json
{
  "capability_id": "text_rough_cut",
  "input": {"target_duration_s": 15},
  "actor_type": "agent",
  "actor_id": "planner_1"
}
```

Skill 序列请求最小体：
```json
{
  "mode": "skill_sequence",
  "strategy": "sequential",
  "skills": [
    {"skill_id": "skill.topic_copy.draft", "input": {}},
    {"skill_id": "skill.text_rough_cut.plan", "input": {}}
  ],
  "budget_limit": {"max_steps": 20, "max_failures": 5, "max_duration_seconds": 900}
}
```

### 23.2 `/api/agent/tasks/run`

行为约束：
1. `strategy=parallel` 不允许 step `condition`
2. 条件流仅在 `strategy=conditional` 生效
3. `dry_run=true` 时自动对非 GET 子调用注入 `dry_run`
4. 超预算直接失败（步骤、失败数、时长）

### 23.3 `/api/agent/tasks/<job_id>` 链路视图

返回 `chain_view`，至少包含：
1. `mode`
2. `overall_status`
3. `counts`
4. `totals(prompt_tokens/completion_tokens/total_tokens/estimated_cost_usd)`
5. `nodes[]`
6. `edges[]`

## 24. 附录 D：操作 Runbook（生产可执行）

### 24.1 启动顺序

1. 配置 AI：`GET/POST /api/settings/ai`
2. 初始化项目：`POST /api/init`
3. 导入素材：`POST /api/library/ingest/local` 或 gdrive 路径
4. 可选：先走 Step1~7 形成母版
5. 走 capability 独立链路（推荐）
   1. `topic_library` -> `topic_copy`
   2. `text_rough_cut` -> `short_clip`
   3. `refinement` -> `audio_voice`
   4. `social_export` / `publish_prep` / `content_publish`

### 24.2 最小生产链路（不依赖工作流文件）

1. `POST /api/capabilities/topic_copy/draft`（`input_mode=inline`）
2. `POST /api/capabilities/text_rough_cut/plan`（inline spans）
3. `POST /api/capabilities/short_clip/plan`（inline candidates）
4. `POST /api/capabilities/refinement/plan`
5. `POST /api/capabilities/social_export/plan`（传 `input_video`）
6. `POST /api/capabilities/publish_prep/generate`
7. `POST /api/capabilities/content_publish/plan`

### 24.3 故障排查优先级

1. 文件不存在：优先检查 `input_mode` 与路径解析
2. LLM 不生效：检查 settings 与 API key，确认 warning 是否降级
3. ffmpeg 失败：检查命令尾部 `stderr_tail`
4. 发布 `waiting_auth`：检查 session `authenticated/expired/expires_at`
5. Agent 调用失败：先看 `/api/agent/tasks/<job_id>` 的 `chain_view.nodes[].error`

## 25. 附录 E：一致性校验清单（交付前逐项勾选）

1. 路由一致性：`/api/capabilities`、`/api/agent` 路由与本文一致
2. 平台一致性：文案/导出/发布平台枚举与别名一致
3. 落盘一致性：所有 `*_last.json`、history、templates 文件可读且结构稳定
4. 幂等一致性：POST 能力路由支持 key 重放与 TTL 过期失效
5. UI 一致性：Capability 工作台含新增模块入口，不替换旧 Step 流程
6. Agent 一致性：plan/run/history/export/replay 全链路可用
7. 测试一致性：新增能力与平台覆盖相关测试通过

## 26. 附录 F：自定义工作流编排（已实现，n8n 风格轻量版）

### 26.1 目标与边界

1. 目标：把内部已有 capability 当作节点自由拼接，节点顺序与分支路由可自定义。
2. 目标：保持现有人用 UI 习惯不变，同时提供 Agent/外部系统可直接调用的 API。
3. 边界：当前版本支持有向条件分支图（DAG-like）与错误恢复分支；不支持并行执行与无限循环（内置跳数/重复节点保护）。

### 26.2 数据模型（固定）

`workflow`：
1. `workflow_id`：唯一标识（slug）
2. `name`：工作流名
3. `description`：描述
4. `input_mode`：`auto|project|inline`
5. `start_step_id`：入口节点（可选，默认首节点）
6. `steps[]`：节点数组（可按分支路由跳转）
7. `tags[]`：标签
8. `created_at` / `updated_at`

`step`：
1. `step_id`
2. `node_type`：`action|condition`
3. `capability_id`（`action` 必填）
4. `action`（默认 `auto`）
5. `input`（对象）
6. `input_mode`（`auto|project|inline`）
7. `run_if`（仅 `action`）
8. `condition`（仅 `condition`）
9. `continue_on_error`（失败是否继续）
10. `enabled`（是否启用）
11. `save_as`（可选：把本步响应保存到 `vars.<save_as>`）
12. `next_step_id`（默认路由）
13. `next_on_success`
14. `next_on_error`
15. `next_on_skip`

### 26.3 API 契约（固定）

1. `GET /api/workflows/catalog`
2. `GET /api/workflows`
3. `POST /api/workflows`
4. `DELETE /api/workflows/<workflow_id>`
5. `POST /api/workflows/plan`
6. `POST /api/workflows/run`
7. `GET /api/workflows/runs`
8. `GET /api/workflows/runs/<run_id>`
9. `POST /api/workflows/runs/<run_id>/rerun`

### 26.4 模板变量机制（固定）

在 step `input` 中支持模板变量插值：
1. `{{steps.<step_id>.response...}}`
2. `{{steps.<step_id>.status}}`
3. `{{last.response...}}`
4. `{{workflow.input.<key>}}`
5. `{{vars.<save_as>...}}`

规则：
1. 完整占位符（整串）可替换为对象/数组/标量。
2. 字符串内占位符会按字符串替换。
3. 未命中变量保留原文本并写入 `warnings[]`。

### 26.5 执行状态机（固定）

节点级：
1. `done`
2. `error`
3. `skipped`（disabled 或 `run_if` 不满足）
4. `unreached`（未进入本次执行路径）

工作流级：
1. `done`：无失败节点
2. `partial`：有失败且至少一个成功节点
3. `failed`：全部失败或无成功节点

执行观测字段：
1. `execution_path[]`：本次实际节点路径
2. `summary.traversed_steps / unreached_steps`
3. `plan.graph`：执行前图结构审计（nodes/edges/transitions/start_step_id/has_cycle/unreached_nodes）

### 26.6 历史与重跑（固定）

1. 每次执行都会记录 `run_id`、`summary`、`steps`、`warnings`、`artifacts`、`request_context`、`workflow`、`plan`。
2. `rerun` 支持：
   1. 整条重跑
   2. `rerun_failed_only=true` 重跑失败节点并自动补齐必要上游依赖链
3. 重跑使用历史快照 workflow；若快照缺失则回退读取当前保存定义。
4. 重跑响应包含 `rerun_context`：`mode/source_run_id/failed_step_ids/included_step_ids/start_step_id`。

### 26.7 持久化文件（新增）

1. `data/custom_workflows.json`：工作流定义库
2. `data/custom_workflow_runs.json`：执行历史

### 26.8 前端入口（已实现）

Capability 工作台新增 `自定义工作流` 标签页，包含：
1. 定义编辑：`workflow_id/name/description/start_step_id/steps_json/input_json`
2. 目录查看：`catalog`（可编排 capability + action）
3. 定义管理：保存、加载、删除
4. 计划预览：`/api/workflows/plan`
   1. 返回 `plan.graph` 供可视化路由与校验使用
5. 异步执行：`/api/workflows/run` + `/api/job/<job_id>` 轮询
6. 历史面板：查看最近执行并触发重跑
7. 轻量画布视图：节点拖拽重排、顺序箭头可视化、单节点聚焦编辑
8. 节点类型编辑：`action/condition`
9. 分支路由编辑：`next_step_id/next_on_success/next_on_error/next_on_skip`

### 26.9 与 Agent 多编排系统协同

1. 外部多 Agent 系统可直接调用 `/api/workflows/run` 执行预置链路。
2. 条件分支链路可直接落在 `/api/workflows/run`；并行场景走 `/api/agent/tasks/run (mode=skill_sequence, strategy=parallel)`。
3. 统一 `request_context`（`actor_type/actor_id/run_mode/idempotency_key/trace_id`）保留审计与追踪能力。
