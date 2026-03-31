# VideoEditor 版本开发计划（v0.16.0）

**文档版本：** V1.0
**日期：** 2026-03-31
**基线 Commit：** 待定（v0.15.0 完成后）
**基线 VERSION：** 0.15.0

---

## 1. 版本目标

AI 重编辑引擎（评论→指令→DAG→渲染→版本 diff）+ 增强能力（音频增强 / TTS / BGM / 转场 / stock 素材 / reframe / style skill / 评论导出），完成智能剪辑闭环。

## 2. 版本范围

### 包含的需求

- 评论定位引擎（CommentResolver: 时间→segment 映射 + gap 检测）
- LLM 意图路由（IntentRouter: 自然语言→结构化指令）
- 编辑方案生成（EditPlanner: 指令→EDITS diff）
- 节点 DAG 管理（NodeManager: 10 节点依赖图 + 选择性重跑）
- 渲染管线增强（RenderPipeline: 支持 auto/skip/force mode）
- 版本 diff UI（VersionDiff.vue: 高亮变更片段）
- Dry run 预览（生成 diff 不渲染）
- AI 回复（每条评论的处理解释）
- 音频增强（降噪 + 均衡 + 压缩 + 响度标准化）
- TTS 配音（edge-tts/CosyVoice/Fish Speech，走 adapter）
- BGM 选择 + beat sync（librosa 节拍分析）
- 转场效果库（12 种效果）
- Stock 素材搜索（Pexels API，走 adapter）
- 多平台 reframe（9:16 / 16:9 / 1:1 / 4:5 等）
- Style Skill（YAML 风格配置 + 自动提取）
- 评论导出（JSON / CSV / EDL）

### 不包含的需求（Future）

| 需求 | 推迟原因 |
|------|---------|
| GPU 加速渲染 | CPU 满足 <5min 视频需求，v0.17+ |
| 语音克隆 | 法律风险 + 额外模型 |
| 多人协作 / @提及 | 桌面单用户产品 |
| 动态字幕样式 | 复杂度高，v0.17+ |
| VLM 画笔分析（画笔→描述） | 需 VLM API，v0.17+ |

---

## 3. 任务列表

| 任务ID | 任务名称 | 优先级 | 状态 |
|--------|---------|--------|------|
| R1 | CommentResolver — 时间→segment 映射 | P0 | Planned |
| R2 | CommentResolver — gap 检测 + 原始内容查找 | P0 | Planned |
| R3 | IntentRouter — LLM 意图解析 + schema 校验 | P0 | Planned |
| R4 | IntentRouter — 14 种指令类型支持 | P0 | Planned |
| R5 | EditPlanner — 指令→EDITS diff 生成 | P0 | Planned |
| R6 | EditPlanner — 冲突检测 + 合并策略 | P1 | Planned |
| R7 | NodeManager — DAG 定义 + 依赖追踪 | P0 | Planned |
| R8 | NodeManager — 选择性重跑 (auto/skip/force) | P0 | Planned |
| R9 | RenderPipeline — artifact 缓存 + 增量渲染 | P0 | Planned |
| R10 | AI 重编辑 API — reedit + dry-run | P0 | Planned |
| R11 | AI 回复生成 — 每条评论处理解释 | P1 | Planned |
| R12 | VersionDiff.vue — 版本 diff 高亮 | P0 | Planned |
| R13 | EnhancePanel.vue — 增强选项面板 | P1 | Planned |
| R14 | AudioEnhancer — FFmpeg filter chain | P1 | Planned |
| R15 | TTSVoiceover — adapter 集成 + 时间对齐 | P1 | Planned |
| R16 | BGMSelector — librosa beat 分析 + sync | P1 | Planned |
| R17 | TransitionEffects — 12 种转场效果 | P1 | Planned |
| R18 | StockMedia — Pexels adapter + 搜索/下载 | P2 | Planned |
| R19 | SocialReframe — 多平台裁剪 | P2 | Planned |
| R20 | StyleSkill — YAML 配置 + 自动提取 | P2 | Planned |
| R21 | ExportDialog.vue — 评论导出 (JSON/CSV/EDL) | P1 | Planned |
| R22 | 增强 API — audio/tts/bgm/transition/reframe | P1 | Planned |
| R23 | Stock API — search + download | P2 | Planned |
| R24 | Style API — list + save | P2 | Planned |
| R25 | 集成测试 + 端到端测试 | P0 | Planned |

---

## 4. 各任务详细定义

### R1: CommentResolver — 时间→segment 映射

**目标：** 将用户评论的时间戳映射到 EDITS 列表中的具体 segment。

**涉及文件：**
- `modules/review_engine/comment_resolver.py` — 新建
- `tests/unit/review_engine/test_comment_resolver.py` — 新建

**输入：** `comment (time_start_ms, time_end_ms)`, `edits: List[Segment]`
**输出：** `ResolvedComment {matched_segments[], gap_info, suggested_action}`

**验收标准：**
- [ ] 二分查找: 时间 → 包含该时间的 segment 索引
- [ ] 区间匹配: start-end 内所有 segment
- [ ] 边界: 时间在两个 segment 之间 → 返回最近的
- [ ] 时间超出范围 → 返回 None + 警告
- [ ] UT 4 条: exact_match / range_match / boundary / out_of_range

**依赖项：** v0.14.0 R1 (contracts)
**已知约束：** 无

---

### R2: CommentResolver — gap 检测 + 原始内容查找

**目标：** 检测评论是否指向被删除的内容，查找被删部分的原始文本。

**涉及文件：**
- `modules/review_engine/comment_resolver.py` — 扩展
- `tests/unit/review_engine/test_comment_resolver.py` — 扩展

**输入：** `comment`, `edits`, `original_transcript: List[Word]`
**输出：** `gap_info {gap_start_ms, gap_end_ms, original_text, removed_segments[]}`

**验收标准：**
- [ ] 评论时间落在两个 segment 之间的 gap → 查找原始转录中被砍内容
- [ ] 返回被删文本 + 原始时间范围
- [ ] 无 gap (评论在 segment 内) → gap_info = None
- [ ] UT 3 条: gap_detection / original_text_found / no_gap

**依赖项：** R1
**已知约束：** 依赖 v0.14.0 的 TranscriptDoc 保留原始词级数据

---

### R3: IntentRouter — LLM 意图解析 + schema 校验

**目标：** 将自然语言评论通过 LLM 解析为结构化编辑指令。

**涉及文件：**
- `modules/review_engine/intent_router.py` — 新建
- `tests/unit/review_engine/test_intent_router.py` — 新建

**输入：** `comment_text`, `resolved_comment`, `context (video_type, duration)`
**输出：** `List[EditInstruction]` (validated against schema)

**验收标准：**
- [ ] "这里砍了" → `[{type: "extend", segment_idx: N}]`
- [ ] "加转场" → `[{type: "transition", effect: "cross_dissolve"}]`
- [ ] "这段删掉" → `[{type: "remove", segment_idx: N}]`
- [ ] 一条评论 → 多条指令 (如 "删掉这段加转场")
- [ ] LLM 返回格式不合法 → 抛出 IntentRouterError
- [ ] schema 校验: 每个 instruction 必须有 type + 有效参数
- [ ] UT 5 条 (mock LLM): extend / remove / multi_instruction / invalid_schema / unknown_type

**依赖项：** R1
**已知约束：** LLM 响应不稳定，需 retry + 降级

---

### R4: IntentRouter — 14 种指令类型支持

**目标：** 完整支持 14 种编辑指令的解析和参数提取。

**涉及文件：**
- `modules/review_engine/intent_router.py` — 扩展
- `modules/review_engine/contracts.py` — 新增 EditInstruction 及子类型

**输入：** LLM 输出 JSON
**输出：** 类型化的 EditInstruction 对象

**验收标准：**
- [ ] 14 种指令: extend/trim/remove/insert/reorder/split/merge/transition/subtitle/speaker/hook/speed/broll/audio
- [ ] 每种指令有独立 schema (必须参数 + 可选参数)
- [ ] schema 校验通过 → 返回类型化对象
- [ ] 未知指令类型 → IntentRouterError
- [ ] UT: 每种指令至少 1 条测试

**依赖项：** R3
**已知约束：** 无

---

### R5: EditPlanner — 指令→EDITS diff 生成

**目标：** 将编辑指令应用到 EDITS 列表，生成 diff。

**涉及文件：**
- `modules/review_engine/edit_planner.py` — 新建
- `tests/unit/review_engine/test_edit_planner.py` — 新建

**输入：** `instructions: List[EditInstruction]`, `current_edits: List[Segment]`
**输出：** `EditPlan {new_edits[], diff: {added[], removed[], modified[]}, summary_text}`

**验收标准：**
- [ ] extend → 扩展 segment 的 start/end 时间
- [ ] remove → 从 EDITS 中移除 segment
- [ ] insert → 从原始视频插入新 segment
- [ ] reorder → 调整 segment 顺序
- [ ] diff 格式: `{added: [{idx, segment}], removed: [{idx, segment}], modified: [{idx, old, new}]}`
- [ ] summary_text: 自然语言描述变更 (如 "扩展了第3段 2.3s，删除了第7段")
- [ ] UT 5 条: extend / remove / insert / reorder / diff_format

**依赖项：** R3, R4
**已知约束：** 无

---

### R6: EditPlanner — 冲突检测 + 合并策略

**目标：** 检测多条评论指令之间的冲突，提供合并策略。

**涉及文件：**
- `modules/review_engine/edit_planner.py` — 扩展
- `tests/unit/review_engine/test_edit_planner.py` — 扩展

**输入：** `instructions[]` (来自多条评论)
**输出：** `{conflicts: [{comment_a, comment_b, reason}], resolved_instructions[]}`

**验收标准：**
- [ ] 同一 segment 的 remove + extend → 冲突
- [ ] 同一 segment 的 trim + speed → 可合并
- [ ] 冲突 → 抛出 ConflictingCommentsError (含冲突详情)
- [ ] 可合并 → 返回合并后的指令列表
- [ ] UT 3 条: conflict_detected / merge_compatible / no_conflict

**依赖项：** R5
**已知约束：** 无

---

### R7: NodeManager — DAG 定义 + 依赖追踪

**目标：** 定义 10 节点依赖图，追踪每个节点的状态。

**涉及文件：**
- `modules/review_engine/node_manager.py` — 新建
- `tests/unit/review_engine/test_node_manager.py` — 新建

**输入：** NODE_GRAPH 定义 (见总参考文档 §6.2)
**输出：** 节点状态管理 + 执行计划

**验收标准：**
- [ ] 10 节点: transcode, analyze, thumbnails, waveform, apply_edits, render_frames, merge_audio, enhance_audio, add_bgm, final_export
- [ ] 依赖关系正确 (DAG 无环)
- [ ] get_execution_order() → 拓扑排序
- [ ] get_affected_nodes(changed_node) → 下游节点列表
- [ ] 节点状态: pending/running/done/failed/skipped
- [ ] UT 4 条: topo_sort / affected_nodes / no_cycle / status_tracking

**依赖项：** 无
**已知约束：** 无

---

### R8: NodeManager — 选择性重跑 (auto/skip/force)

**目标：** 根据 mode 参数和 artifact 缓存决定哪些节点需要重跑。

**涉及文件：**
- `modules/review_engine/node_manager.py` — 扩展
- `tests/unit/review_engine/test_node_manager.py` — 扩展

**输入：** `changed_node`, `mode_overrides: Dict[str, str]`
**输出：** `{run: [node], skip: [node], reason: Dict[str, str]}`

**验收标准：**
- [ ] auto: 有 artifact 缓存 → skip，无 → run
- [ ] skip: 强制跳过 (即使无缓存)
- [ ] force: 强制重跑 (即使有缓存)
- [ ] 默认 auto: 只重跑 changed_node 及下游
- [ ] 智能重跑示例 (见总参考文档 §6.2 表格) 全部通过
- [ ] UT 4 条: auto_skip_cached / auto_run_missing / force_rerun / only_downstream

**依赖项：** R7, v0.14.0 R25 (artifact_store)
**已知约束：** 无

---

### R9: RenderPipeline — artifact 缓存 + 增量渲染

**目标：** 扩展 v0.14.0 的 render_pipeline，支持 artifact 缓存和增量渲染。

**涉及文件：**
- `modules/review_engine/render_pipeline.py` — 扩展
- `tests/unit/review_engine/test_render_pipeline.py` — 扩展

**输入：** `execution_plan (from NodeManager)`, `artifacts (from ArtifactStore)`
**输出：** 渲染结果 + 更新 artifacts

**验收标准：**
- [ ] 按 execution_plan 顺序执行节点
- [ ] skip 节点 → 从 artifact_store 加载缓存
- [ ] run 节点 → 执行 + 保存到 artifact_store
- [ ] 失败节点 → 中止 + 标记下游为 failed
- [ ] 进度回调 (node_name, status, progress_pct)
- [ ] UT 3 条: cached_skip / incremental / failure_cascade

**依赖项：** R7, R8
**已知约束：** 无

---

### R10: AI 重编辑 API — reedit + dry-run

**目标：** AI 重编辑的核心 API 端点。

**涉及文件：**
- `modules/app_api/routes/review_routes.py` — 扩展
- `tests/api/test_review_reedit_api.py` — 新建

**输入/输出：** 见总参考文档 §7.2

**验收标准：**
- [ ] POST /api/review/{id}/ai-reedit → 202 + job_id (后台任务)
- [ ] POST /api/review/{id}/ai-reedit/dry-run → 200 + diff 预览 (不渲染)
- [ ] reedit 完成 → 创建新 version + 更新 comments 状态
- [ ] 支持 idempotency_key
- [ ] 统一错误格式
- [ ] UT 4 条: reedit_creates_version / dry_run_no_render / idempotent / error_format

**依赖项：** R1-R9
**已知约束：** 后台 job，客户端轮询

---

### R11: AI 回复生成 — 每条评论处理解释

**目标：** 为每条被处理的评论生成 AI 回复，解释做了什么。

**涉及文件：**
- `modules/review_engine/intent_router.py` — 扩展
- `modules/review_engine/review_store.py` — 扩展 (ai_reply 字段)

**输入：** `comment`, `applied_instructions[]`, `diff`
**输出：** `ai_reply: str` (自然语言解释)

**验收标准：**
- [ ] "这里砍了" → "已将该段落从 15.3s 扩展至 18.1s，恢复了完整句子"
- [ ] "删掉这段" → "已删除 42.0s-46.5s 的重复片段"
- [ ] 回复写入 review_comments.ai_reply
- [ ] 回复简洁 (< 100 字)
- [ ] UT 2 条: generates_reply / reply_saved

**依赖项：** R3, R5
**已知约束：** 无

---

### R12: VersionDiff.vue — 版本 diff 高亮

**目标：** 视觉化展示两个版本之间的差异。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/VersionDiff.vue` — 新建

**输入：** diff 数据 (from API)
**输出：** 高亮显示变更

**验收标准：**
- [ ] 时间轴上: 新增片段绿色标记, 删除片段红色标记, 修改片段黄色标记
- [ ] 左右对比模式 (可选): v1 时间轴 | v2 时间轴
- [ ] 变更摘要文字 (summary_text from EditPlanner)
- [ ] 点击标记 → 跳转到变更位置

**依赖项：** v0.15.0 R9, R5
**已知约束：** 无

---

### R13: EnhancePanel.vue — 增强选项面板

**目标：** 增强功能的 UI 面板，提供音频/TTS/BGM/转场/reframe 选项。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/EnhancePanel.vue` — 新建

**输入：** 当前版本信息
**输出：** 增强配置 → 调用 API

**验收标准：**
- [ ] 音频增强: 降噪/均衡/压缩 开关 + 预设
- [ ] TTS 配音: 提供商选择 + 语音选择 + 预览
- [ ] BGM: 选曲 + 音量调节 + beat sync 开关
- [ ] 转场: 效果选择 + 应用位置
- [ ] Reframe: 平台选择 (抖音/Instagram/YouTube...)
- [ ] [应用增强] 按钮 → 后台 job

**依赖项：** v0.15.0 R11 (store)
**已知约束：** 无

---

### R14: AudioEnhancer — FFmpeg filter chain

**目标：** 音频增强处理（降噪 + 均衡 + 压缩 + 响度标准化）。

**涉及文件：**
- `modules/review_engine/audio_enhancer.py` — 新建
- `tests/unit/review_engine/test_audio_enhancer.py` — 新建

**输入：** `audio_path`, `config: AudioConfig`
**输出：** 增强后的音频文件路径

**验收标准：**
- [ ] FFmpeg filter chain: afftdn → equalizer → acompressor → loudnorm
- [ ] 必须加 `-ar 44100` (防止 loudnorm 采样率 bug)
- [ ] 各阶段可单独开关
- [ ] timeout 120s + stderr 捕获 + 重试 3 次
- [ ] 输出 LUFS 在 -16 ± 1 范围
- [ ] UT 3 条: full_chain / partial_config / loudnorm_sample_rate

**依赖项：** FFmpeg
**已知约束：** loudnorm 采样率 bug (已知，强制 44100)

---

### R15: TTSVoiceover — adapter 集成 + 时间对齐

**目标：** TTS 配音生成，通过 adapter 层调用 TTS 提供商。

**涉及文件：**
- `modules/review_engine/tts_voiceover.py` — 新建
- `modules/adapters/tts_adapter.py` — 实现
- `tests/unit/review_engine/test_tts_voiceover.py` — 新建

**输入：** `segments[]` (文字 + 时间), `voice`, `provider`
**输出：** 配音音频文件 + 时间对齐信息

**验收标准：**
- [ ] 通过 tts_adapter 调用 (不直接依赖提供商 SDK)
- [ ] 支持 edge-tts (默认, 免费)
- [ ] 配音对齐字幕时间 (每句 TTS 填充到 segment 时长)
- [ ] 无 API key 时 → 提示用户配置
- [ ] UT 2 条 (mock adapter): generates_audio / alignment_correct

**依赖项：** v0.14.0 R1 (adapter 骨架)
**已知约束：** CosyVoice/Fish Speech 需要 API key

---

### R16: BGMSelector — librosa beat 分析 + sync

**目标：** BGM 选择和节拍同步（调整切点对齐节拍）。

**涉及文件：**
- `modules/review_engine/bgm_selector.py` — 新建
- `tests/unit/review_engine/test_bgm_selector.py` — 新建

**输入：** `bgm_path`, `edits: List[Segment]`
**输出：** `beats: List[float]`, `synced_edits: List[Segment]`

**验收标准：**
- [ ] librosa beat 分析 → 节拍时间点列表
- [ ] beat_sync_edits: 微调 segment 切点 (±0.2s) 对齐节拍
- [ ] BGM 混合: 背景音量可调 (默认 -12dB)
- [ ] 淡入淡出: 开头 2s 淡入, 结尾 3s 淡出
- [ ] librosa 不可用 → 降级 (不 sync, 仅混合)
- [ ] UT 3 条: beat_detection / sync_adjusts_cuts / fallback_no_librosa

**依赖项：** librosa (可选)
**已知约束：** librosa 依赖较重，可选安装

---

### R17: TransitionEffects — 12 种转场效果

**目标：** 实现 12 种 FFmpeg 转场效果。

**涉及文件：**
- `modules/review_engine/transition_effects.py` — 新建
- `tests/unit/review_engine/test_transition_effects.py` — 新建

**输入：** `effect_name`, `segment_a`, `segment_b`, `duration`
**输出：** 渲染后的视频片段

**验收标准：**
- [ ] 12 种效果: cut/fade_black/fade_white/cross_dissolve/wipe_left/wipe_right/zoom_in/zoom_out/black_title/whoosh/glitch/flash
- [ ] FFmpeg xfade filter 实现 (支持的效果)
- [ ] black_title: PIL 生成黑底白字帧 → 拼接
- [ ] duration 参数: 0.15s-3.0s
- [ ] FFmpeg: timeout + stderr 捕获
- [ ] UT 3 条: fade_black / cross_dissolve / black_title

**依赖项：** FFmpeg
**已知约束：** 部分效果可能需要特定 FFmpeg 版本

---

### R18: StockMedia — Pexels adapter + 搜索/下载

**目标：** 通过 Pexels API 搜索和下载 stock 素材。

**涉及文件：**
- `modules/review_engine/stock_media.py` — 新建
- `modules/adapters/pexels_adapter.py` — 实现
- `tests/unit/review_engine/test_stock_media.py` — 新建

**输入：** `query`, `duration_range`, `orientation`
**输出：** `{results: [{id, url, preview_url, duration, photographer}], total}`

**验收标准：**
- [ ] 通过 pexels_adapter 调用 (不直接依赖 Pexels SDK)
- [ ] 搜索: 关键词 + 时长 + 横竖屏
- [ ] 下载: 选定素材 → 保存到 project_dir/stock/
- [ ] 无 API key → 抛出 StockMediaError (不静默失败)
- [ ] UT 2 条 (mock adapter): search_returns_results / no_key_raises

**依赖项：** v0.14.0 R1 (adapter 骨架)
**已知约束：** 需要 Pexels API key

---

### R19: SocialReframe — 多平台裁剪

**目标：** 自动裁剪视频到不同平台比例。

**涉及文件：**
- `modules/review_engine/social_reframe.py` — 新建
- `tests/unit/review_engine/test_social_reframe.py` — 新建

**输入：** `video_path`, `platform` (tiktok/instagram/youtube/shorts/wechat/xiaohongshu/square)
**输出：** 裁剪后的视频文件路径

**验收标准：**
- [ ] 7 个平台比例 (见总参考文档 §6.7)
- [ ] 智能裁剪: 居中裁剪 (无 face detection 时)
- [ ] max_duration 检查: shorts 60s, wechat 60s 等
- [ ] FFmpeg crop filter
- [ ] UT 2 条: crop_correct_ratio / max_duration_enforced

**依赖项：** FFmpeg
**已知约束：** 说话人位置追踪留到 v0.17+ (需 face detection)

---

### R20: StyleSkill — YAML 配置 + 自动提取

**目标：** 定义和保存风格配置，可在新项目中复用。

**涉及文件：**
- `modules/review_engine/style_skills.py` — 新建
- `tests/unit/review_engine/test_style_skills.py` — 新建

**输入：** 风格 YAML 或从项目自动提取
**输出：** StyleConfig 对象

**验收标准：**
- [ ] YAML 格式: color_grade, font, transition, audio_preset, pacing
- [ ] 保存到 `{project_dir}/styles/{name}.yaml`
- [ ] 加载: 读取 YAML → StyleConfig
- [ ] 自动提取: 从已完成项目中提取风格参数
- [ ] UT 2 条: save_load_roundtrip / auto_extract

**依赖项：** 无
**已知约束：** 无

---

### R21: ExportDialog.vue — 评论导出

**目标：** 将评论导出为 JSON / CSV / EDL 格式。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/ExportDialog.vue` — 新建
- `modules/review_engine/comment_exporter.py` — 新建
- `tests/unit/review_engine/test_comment_exporter.py` — 新建

**输入：** comments[], 导出格式
**输出：** 文件

**验收标准：**
- [ ] JSON: 完整评论数据
- [ ] CSV: timecode, type, text, status, ai_reply
- [ ] EDL: CMX 3600 格式 (可导入 Premiere/DaVinci)
- [ ] 文件保存到用户选择的路径
- [ ] UT 3 条: json / csv / edl

**依赖项：** 无
**已知约束：** EDL 格式复杂，先支持基本字段

---

### R22: 增强 API — audio/tts/bgm/transition/reframe

**目标：** 增强功能的 API 端点。

**涉及文件：**
- `modules/app_api/routes/enhance_routes.py` — 新建
- `modules/app_api/server.py` — 注册 blueprint
- `tests/api/test_enhance_api.py` — 新建

**输入/输出：** 见总参考文档 §7.3

**验收标准：**
- [ ] POST /api/review/enhance/audio → 202 + job_id
- [ ] POST /api/review/enhance/tts → 202 + job_id
- [ ] POST /api/review/enhance/bgm → 202 + job_id
- [ ] POST /api/review/enhance/transition → 202 + job_id
- [ ] POST /api/review/enhance/reframe → 202 + job_id
- [ ] 统一错误格式
- [ ] UT 5 条

**依赖项：** R14-R19
**已知约束：** 全部后台 job

---

### R23: Stock API — search + download

**目标：** Stock 素材搜索和下载 API。

**涉及文件：**
- `modules/app_api/routes/stock_routes.py` — 新建
- `modules/app_api/server.py` — 注册 blueprint
- `tests/api/test_stock_api.py` — 新建

**输入/输出：** 见总参考文档 §7.3

**验收标准：**
- [ ] GET /api/stock/search?q=xxx → 200 + results[]
- [ ] POST /api/stock/download → 202 + job_id
- [ ] 无 API key → 400 + 提示配置
- [ ] UT 2 条

**依赖项：** R18
**已知约束：** 无

---

### R24: Style API — list + save

**目标：** 风格配置的增删查 API。

**涉及文件：**
- `modules/app_api/routes/style_routes.py` — 新建
- `modules/app_api/server.py` — 注册 blueprint
- `tests/api/test_style_api.py` — 新建

**输入/输出：** 见总参考文档 §7.3

**验收标准：**
- [ ] GET /api/review/styles → 200 + styles[]
- [ ] POST /api/review/styles → 201 + style_id
- [ ] UT 2 条

**依赖项：** R20
**已知约束：** 无

---

### R25: 集成测试 + 端到端测试

**目标：** 端到端验证 AI 重编辑 + 增强完整闭环。

**涉及文件：**
- `tests/integration/test_ai_reedit_flow.py` — 新建
- `tests/integration/test_enhance_flow.py` — 新建
- `tests/smoke/test_smoke_full_pipeline.py` — 新建
- `tests/conftest.py` — 新增 fixtures

**输入：** 测试视频 + v0.15.0 生成的评审数据
**输出：** 测试报告

**验收标准：**
- [ ] IT: 添加评论 → AI 重编辑 → 新版本生成 → diff 正确
- [ ] IT: dry run → 返回 diff → 不创建新版本
- [ ] IT: 音频增强 → LUFS 在 -16 ± 1
- [ ] IT: 转场效果 → 视频无黑帧
- [ ] IT: 评论导出 JSON/CSV/EDL → 文件可读
- [ ] SMK: 完整闭环 (粗剪→评审→AI重编辑→增强→导出) < 120s
- [ ] REG: `pytest project/tests/ -v` 全量 0 失败
- [ ] 测试报告: `docs/test-reports/test-report-v0.16.0-release.md`

**依赖项：** R1-R24
**已知约束：** 需真实 LLM API (或 mock)

---

## 5. 完成状态追踪

| 任务 | 计划周期 | 实际完成 | 迭代 | 备注 |
|------|---------|---------|------|------|
| R1-R6 | 3 天 | — | 0 | 桥接层 |
| R7-R9 | 2 天 | — | 0 | DAG + 渲染 |
| R10-R12 | 1.5 天 | — | 0 | API + UI |
| R13-R17 | 3 天 | — | 0 | 增强核心 |
| R18-R21 | 2 天 | — | 0 | 附加能力 |
| R22-R24 | 1 天 | — | 0 | 增强 API |
| R25 | 1.5 天 | — | 0 | 测试 |
| **总计** | **14 天** | | | |

## 6. 决策和假设

| # | 内容 | 理由 |
|---|------|------|
| D1 | LLM 调用使用系统现有 AI 能力接口 | 不引入新 AI SDK |
| D2 | librosa 可选安装 | 避免强制依赖重包 |
| D3 | Pexels 是唯一 stock 提供商 | 免费 API，够用 |
| D4 | edge-tts 是默认 TTS | 免费，无需 API key |
| D5 | VLM 画笔分析推迟到 v0.17+ | 需要 VLM API，复杂度高 |
| A1 | LLM 可通过现有 API 调用 | 不引入新的 LLM 集成 |
| A2 | v0.15.0 评审 UI 和数据层可用 | 本版本依赖 |

## 7. 风险和缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LLM 意图解析不准 | 高 | 中 | retry + schema 校验 + 降级到关键词匹配 |
| DAG 重跑逻辑复杂 | 中 | 高 | 充分 UT + 简单用例先行 |
| librosa 安装问题 | 中 | 低 | 可选依赖，无 librosa 降级 |
| Pexels API 限流 | 低 | 低 | 缓存 + 限流提示 |
| FFmpeg 转场效果兼容性 | 中 | 中 | 回退到 fade_black |

## 8. 变更记录

| 版本 | 日期 | 变更 | 责任人 |
|------|------|------|--------|
| V1.0 | 2026-03-31 | 初版，25 个 R 任务 | Claude Code |

---

*文档结束*
