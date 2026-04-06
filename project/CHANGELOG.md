# 变更日志

所有重要变更都将被记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 规范。

## [0.18.0] - (Unreleased)

### 新增 (Added)
- X0: 异步 Job 管理器 — job_system/job_manager.py (submit/progress/cancel/cleanup，线程安全)
- A1: MCP 评审操作工具组 — 6 工具 (init/comment/resolve/reedit/dry-run/export)
- A2: MCP VLM 工具组 — 3 工具 (describe_region/diagnose_frame/status)
- A3: MCP 增强工具组 — 4 工具 (audio/tts/bgm/transition)
- B1: FrameSampler 关键帧采样策略 — 三种采样模式 (scene_boundary/uniform/hybrid) + max_frames 限制
- contracts.py 扩展: SampledFrame, StreamIssue, StreamAnalysis, SceneSummary, Clip, TimelineTrack, Timeline 数据类
- C1: TimelineStore — 多轨时间线 SQLite 持久化 (WAL 模式, track/clip CRUD)
- D1: 硬件检测扩展 — FFmpeg 解码器探测 + HEVC 硬解检测 + choose_decoder() 解码策略
- A4: MCP 只读查询工具组 — 4 工具 (query_state/comments/diagnostics/versions)
- A5: MCP 安全升级 — 工具权限分级 (READ/WRITE/DANGEROUS) + JSONL 审计日志 + 路径白名单扩展
- C2: TimelineOps 轨道操作 — 增删/重排/锁定/静音/音量 + 类型限制
- C3: TimelineOps 片段操作 — 移动/裁剪/分割/跨轨移动/重叠检测 + LockedTrackError
- D2: render_pipeline 硬件加速 — 自适应编码器选择 + HEVC 硬解 + CRF→码率自动切换
- B2: VideoStreamAnalyzer — 跨帧时序分析 (委托 check_continuity + VLM 增强转场/叙事)
- C5: track_builder 动态多轨输出 — extra_audio_tracks + extra_video_tracks 扩展
- A6: MCP 集成测试 — 端到端验证 (review chain/VLM chain/security/tool discovery) + README 更新 (12→29 工具)
- B3: SceneSummarizer — 场景级描述聚合 (多帧去重合并/代表帧选择/VLM 摘要/降级策略)
- C4: Timeline API — 9 个多轨端点 (create/get/track CRUD/clip CRUD/split) + 统一错误格式 + 锁定轨道 403
- D3: RenderManager — 分段并行渲染 (Clip→Segment 适配/ThreadPoolExecutor/FFmpeg concat/重试/清理)

## [0.17.0] - 2026-04-04

### 新增 (Added)
- VLM 画笔分析引擎
  - R1: VLMAdapter 抽象层 — Protocol + StubAdapter + factory (stub/local_llava/openai/claude)
  - R2: LocalLlavaAdapter — 本地 LLaVA-7B 推理 (延迟加载, 优雅降级)
  - R3: APIVisionAdapter — OpenAI GPT-4o + Claude Vision 双 adapter
  - R4: RegionExtractor — 画笔笔画→裁剪区域 (rect/circle/pen/arrow/spotlight + 归一化坐标自动检测)
  - R5: VLMAnalyzer — 结构化画面描述 (JSON 解析 + 文本回退 + 缓存)
  - R6: ReviewStore migration — visual_context + ai_generated 列 (向后兼容)
- 多模态评审增强
  - R9: IntentRouter 多模态升级 — visual_context 注入 LLM prompt
  - R10: 指代消解 — "这个/那个/它" → VLM 识别的具体对象
- AI 画面诊断
  - R11: 构图检查 (VLM 辅助: 三分法/头顶空间/水平线/边缘裁切)
  - R12: 曝光/色温检查 (直方图算法: 高光溢出/阴影死黑/B-R 色温偏移)
  - R13: 连续性检查 (相邻场景: 亮度跳变/色温跳变)
  - R14: AI 评审员 — 诊断结果→自动生成 AI 评论 (幂等)
- 前端集成
  - R7: CommentInput AI 描述预填充 (loading/提示/关闭)
  - R8: DrawingOverlay annotationComplete 事件 (500ms debounce + 帧截图)
  - R15: DiagnosticsPanel.vue — 诊断面板 (severity 色彩编码 + 点击跳转)
  - R17: VLM 设置页 (provider 选择 + API Key + 测试连接)
- API
  - R16: VLM API — POST describe / POST diagnose / GET diagnostics / GET status

### 修复 (Fixed)
- PIL.Image.convert("HSV") 不支持 → 改用 RGB B-R 通道差值分析色温
- DrawingOverlay 笔画格式 (type/start/end) 与 RegionExtractor (tool/points) 不匹配 → 自动格式归一化
- generate_ai_review N+1 查询 → 使用 add_comment 返回的 comment_id
- 关键词回退模式对未识别文本错误生成 'remove' 指令 → 返回空列表
- VLM 缓存键只采样 1 像素 → 5 像素采样减少误命中

### 测试 (Tests)
- 新增 86 个测试 (75 unit + 7 API + 5 integration)
- 全量回归 1504 passed, 1 skipped, 0 failures

## [0.16.0] - 2026-04-03

### 新增 (Added)
- AI 重编辑引擎
  - R1-R2: CommentResolver — 时间→segment 二分搜索映射 + gap 检测
  - R3-R4: IntentRouter — 自然语言→14 类结构化编辑指令 (LLM + 关键词回退)
  - R5-R6: EditPlanner — 指令应用 + 冲突检测 + diff 生成
  - R7-R8: NodeManager — 10 节点 DAG 拓扑排序 + 选择性重跑 (auto/skip/force)
  - R9: render_incremental() — 增量渲染 + artifact 缓存
  - R10: AI Reedit API — POST /api/review/<id>/ai-reedit (202 async) + dry-run
  - R11: AI Reply API — GET /api/review/<id>/comments/<cid>/ai-reply
  - R12: VersionDiff.vue — 时间轴 diff 标记 (绿/红/黄)
- 增强能力
  - R14: AudioEnhancer — FFmpeg afftdn+eq+compressor+loudnorm (-ar 44100)
  - R15: TTSVoiceover — edge-tts adapter + 4 语音预设
  - R16: BGMSelector — librosa 节拍分析 + beat sync ±200ms 微调
  - R17: TransitionEffects — 12 种效果 (xfade + 自定义)
  - R18: StockMedia — Pexels API adapter (搜索 + 下载)
  - R19: SocialReframe — 7 平台预设 (tiktok/ig/yt/shorts/wechat/xhs/square)
  - R20: StyleSkill — YAML 风格配置 (保存/加载/自动提取)
  - R21: CommentExporter — JSON/CSV/EDL (CMX 3600) 导出
  - R13: EnhancePanel.vue — 5-tab 增强面板
  - R21: ExportDialog.vue — 格式选择 + 预览 + 复制
- API 路由
  - R22: enhance_routes — 5 个增强端点 (audio/tts/bgm/transition/reframe)
  - R23: stock_routes — 搜索 + 下载
  - R24: style_routes — 风格 CRUD

### 修复 (Fixed)
- review_routes.py 调用不存在的 store.get_comments() → 修正为 list_comments()
- comment_exporter.py EDL 导出 _ms_to_smpte(None) 崩溃
- security.py Python 3.9 不兼容 `dict | None` → Optional[dict]
- style_skills.py 硬依赖 yaml → 可选依赖 + 优雅降级
- bgm_selector.py librosa+scipy 版本不兼容 → try/except 降级

### 测试 (Tests)
- 新增 148 个测试 (118 unit + 30 integration/smoke)
- 全量回归 1289 passed, 54 skipped, 0 new failures

## [0.15.0] - 2026-04-01

### 新增 (Added)
- 核心评审 UI (14 Vue 组件)
  - R1: ReviewPlayer — HTML5 视频播放器 + 缩放/平移/全屏
  - R2-R4: PlayerControls — 进度条、SMPTE 时间码、速度/音量/IO 控制
  - R5: CommentInput — 评审类型选择器 (7 类) + 文本输入 + 时间范围
  - R6: CommentCard — 单条评审显示 (类型徽章/时间码/状态)
  - R7: CommentPanel — 评审侧边栏 (筛选/排序/计数)
  - R8: TrackComments — 时间轴评审标记 + tooltip
  - R9: ReviewTimeline — 时间尺/轨道容器/缩放控制
  - R12-R15: DrawingOverlay — Canvas 标注 (画笔/箭头/矩形/椭圆)
  - R13: AnnotationToolbar — 工具/颜色/线宽选择
  - R17: ThumbnailStrip — 精灵图时间轴缩略图
  - R19: WaveformTrack — Canvas 音频波形可视化
  - R20: SubtitleEditor — 时间轴字幕块
  - R21: SafeZoneOverlay — 宽高比安全区参考线
  - R22: VersionSwitcher — 版本导航 + 下拉列表
- 评审基础设施
  - R10: useKeyboardShortcuts — 模式感知键盘快捷键 (40+ 绑定)
  - R11: review.js Pinia store — 完整评审状态管理
  - ReviewView.vue — 主评审页面布局 (3 面板)
  - /review 路由注册
- 后端生成器 (FFmpeg)
  - R16: thumbnail_generator.py — 精灵图缩略图生成
  - R18: waveform_generator.py — 音频峰值提取
  - 升级 review_routes.py 中的 thumbnails/waveform 端点 (stub → 实际实现)

### 变更 (Changed)
- review API thumbnails/waveform 端点从 stub (202) 升级为真实 FFmpeg 处理 (200/500)

### 测试 (Tests)
- 新增 13 个测试 (thumbnail_generator 6 + waveform_generator 7)
- 更新 4 个测试适配非 stub 行为
- 全量回归: 1184 passed, 0 failed

## [0.14.0] - 2026-03-31

### 新增 (Added)
- 智能粗剪引擎 (review_engine 模块)
  - R2: 视频类型检测 (VAD) — speech/scenic/mixed 三路分类
  - R3: Whisper 词级转录 — faster-whisper/openai-whisper 双引擎
  - R4: 说话人分离 — pyannote.audio 可选 + 单说话人 fallback
  - R5: 语气词 + 静音检测 — 中英文语气词集 + dead air 标记
  - R6-R8: 废话句/重复片段/false start 检测
  - R14: FFmpeg 场景分割
  - R17: 混合路径 (speech+B-roll) 分离合并
  - R18: FFmpeg 粗剪渲染 — concat + loudnorm + retry
- 评审数据层
  - R23: ReviewStore — SQLite 持久化 (sessions/comments/versions)
  - R24: 版本 CRUD + diff + 非破坏性 rollback
  - R25: ArtifactStore — 原子写入 + 大文件 symlink (>50MB)
- 粗剪 API (10 endpoints)
  - R20: POST /api/roughcut/init + GET /detect-type + GET /stats
  - R21: GET /transcript + GET /fillers + POST /fillers/batch + POST /transcript/edit
  - R22: GET /scenes + POST /scenes/select + POST /generate
- 评审 API (12 endpoints)
  - R26: POST /api/review/init + GET /state + comments CRUD
  - R27: versions list + diff + rollback
  - R28: thumbnails + waveform stubs (202)
- 前端粗剪 UI
  - R9-R13: TranscriptEditor — 段落展示/标记高亮/点击跳转/编辑操作/Hook+统计
  - R16: SceneSelector — 网格布局/选择/全选
  - R19: roughcut.js Pinia store + RoughCutView 主视图
  - /roughcut 路由注册
- 125 个新测试 (75 unit + 23 API + 5 integration + 16 smoke)

### 变更 (Changed)
- server.py: 注册 review + roughcut blueprints
- legacy_project_routes.py: 新增 choose_files_multiple 参数 + 多选文件对话框

## [0.13.1] - 2026-03-26

### 修复 (Fixed)
- R1: 消除 Step 1「分析素材」静默失败 — Toast + 创建项目按钮
- R2: 修复前后端项目状态脱节 — ready:false 时清除 localStorage
- R3: 能力工具状态准确标注 — 区分「可用」与「需先打开项目」
- R4: Step 1 新增素材选择 UI — 空态/有素材/loading 三状态
- R5: 素材导入进度反馈 — 显示当前文件名 + 已处理/总数
- R6: 工作流步骤命名去技术化 — 创作者语言（挑选素材/找选题/写脚本...）
- R7: 设置页「测试连接」按钮 — 验证 API Key 有效性
- R8: 集成测试通过，917 全量回归无破坏

## [0.13.0] - 2026-03-28

### 新增 (Added)
- R10: 美颜与审美增强 v2（W-005）
  - 分级磨皮：额头 0.8× / 脸颊 1.0× / 下巴 0.6×，feathered zone blending
  - 肤色保护：HSV-S 通道变化 < 5%
  - 5 个 LUT 预设：outdoor_natural / indoor_warm / food / night / travel
  - `POST /api/capabilities/beauty/preview` + `GET /api/capabilities/beauty/lut-presets`
  - 前端 A/B 对比预览面板
- R11: MCP Server 模块（W-011）
  - FastMCP 封装 12 工具（7 工作流 + 5 能力）
  - 安全：路径白名单、穿越拒绝、无删除接口、lazy connection
- R12: 集成测试 + 最终审计
  - 全量回归 1039 passed / 0 failures

### 修复 (Fixed)
- Phase 8 安全审计：top_k 上界 / mode 白名单 / base64 大小限制

### 变更 (Changed)
- 开发治理规范 v1.5→v1.18

## [0.13.11] - 2026-03-27

### 新增 (Added)
- R9: FCPXML 导出适配器（W-013）
  - `modules/exporters/fcpxml/` 新模块：`FCPXMLBuilder` + `schema.py`
  - FCPXML 1.9 格式：`<asset-clip>` 视频 + `<title>` 字幕
  - `POST /api/capabilities/fcpxml_export/run` API 端点
  - CMTime 时间格式（ms/1000s）
  - 新增 7 个测试

## [0.13.10] - 2026-03-27

### 新增 (Added)
- R8: 剪映草稿导出适配器（W-012）
  - `modules/exporters/jianying/` 新模块：`JianyingExportBuilder` + `schema.py`
  - `POST /api/capabilities/jianying_export/run` API 端点
  - 生成 `draft_content.json` + `draft_meta_info.json`（剪映专业版 v5.x 格式）
  - 输出目录无写权限时返回 400 + 明确错误
  - 新增 7 个测试

## [0.13.9] - 2026-03-27

### 新增 (Added)
- R7: 可视化时间线编辑器 v1（W-001）
  - `GET/PUT /api/timeline/tracks` — 三轨（video/subtitle/audio）读写 API
  - 前端三轨视图：Video 80px / Subtitle 40px / Audio 60px，颜色区分
  - `timelineSnap()` 吸附算法（8px 阈值）
  - `timelineMoveVideoClip()` 视频拖拽 + 字幕联动
  - `timelineTrimAudio()` 音频独立裁剪
  - 新增 9 个 API 测试

## [0.13.8] - 2026-03-27

### 新增 (Added)
- R6: 向量索引基础设施升级（W-007+W-008+W-009）
  - R6a: `_build_faiss_index()` 自动选择 IndexIVFFlat（N >= 10k）或 IndexFlatIP
  - R6b: WAL 持久化 — `add()` 追加 JSONL WAL；`load()` replay；`save()` 清空
  - R6b: `add_batch()` + `checkpoint()` 接口
  - R6c: CLIPEncoder `dim` / `model_id` 动态暴露；CLIP 设置 API
  - 新增 12 个测试

## [0.13.5] - 2026-03-27

### 新增 (Added)
- R5: recovery_hint 前端完整消费（W-003）
  - `runContentPublish()` 检测 `recovery_hint.can_rerun`，自动弹出失败详情 Modal
  - Modal 按 `rerun_scope` 映射按钮文字（重新发布 / 前往设置 / 无按钮）
  - `fix_config_then_rerun` 点击跳转发布连接器设置页
  - `recovery_hint` 缺失时安全降级为通用提示，无 JS 错误
  - 新增 Alpine 状态变量 `publishRecoveryHint` / `showPublishFailureModal`

## [0.13.4] - 2026-03-27

### 新增 (Added)
- R4: VectorIndex compact 自动触发（W-006）
  - `compact_if_needed()` 方法：`_deleted` 比例 > 20% 时自动 rebuild 清理
  - `_extract_vector(pos)` 辅助方法：从 FAISS / NumPy 后端提取原始向量
  - `save()` 前自动检查并触发 compact，防止索引膨胀
  - 新增 6 个测试（覆盖触发/不触发/搜索一致性/日志/save 联动/NumPy 后端）

## [0.13.3] - 2026-03-27

### 新增 (Added)
- R3: 素材入库自动触发视觉索引（W-010）
  - `_auto_visual_index(assets)` 私有方法：入库后异步后台线程 CLIP 索引
  - `ingest_local_path()` / `ingest_local_images()` 末尾自动调用
  - CLIP 不可用时：静默跳过 + R2 降级通知（`_log_degradation`）
  - API 响应含 `visual_index_triggered: true/false` 字段
  - 异步 daemon 线程，不阻塞入库进度条
  - 新增 9 个测试（覆盖触发/降级/非阻塞 3 类场景）

## [0.13.2] - 2026-03-27

### 新增 (Added)
- R2: 退化行为显式通知（W-002）
  - `_log_degradation()` 辅助函数：结构化记录降级事件到审计日志
  - workflow.py 3 处退化点（Step 1 CLIP / Step 2 选题 / Step 3 脚本）写入 `audit("degradation", ...)`
  - 前端 `_fetchDegradationAudit()`：轮询审计 API，60s 内新事件自动 Toast
  - Toast 格式：`[模块] 已降级：原因 → 降级路径`
  - 新增 4 个降级审计测试（含 API 端点过滤测试）
  - 全量测试 928 passed / 0 failed

## [0.13.1] - 2026-03-27

### 新增 (Added)
- R1: 种子词库验证 + 入库确认
  - 语义种子词库 JSONL（2119 条，12 分类）正式纳入仓库管理
  - `_constants.py` 双路径逻辑验证通过（项目内优先，旧路径兜底）
  - 冷启动验证：空 DB 启动后 tag 记录 ≥ 2100（非 33 条最小集）
  - 新增测试 `test_r1_seed_library.py`（7 用例，覆盖文件完整性 + 冷启动加载）

## [0.12.12] - 2026-03-22

### 新增 (Added)
- R12: 集成测试 + 最终审计
  - 917 全量测试通过
  - 8 项跨模块集成验证全部通过
  - R1-R11 任务完成度确认
  - 最终审计报告 `docs/audit/2026-03-22-r12-final-audit.md`

## [0.12.11] - 2026-03-22

### 修复 (Fixed)
- R11: 产品体验修复批次
  - API 错误响应标准化：5 处 `str(exc)` 裸露异常替换为 `safe_error_response()` 用户友好消息
  - 前端 IngestPanel 文件夹选择添加 try/catch 错误反馈
  - 隐藏未实现功能入口：云端导入 tab + ContentPublish 设置 tab
  - 关键 JSON 解析（script/materials）静默失败改为返回明确错误
  - API 参数验证加固：target_duration_s 范围限制、timeline fps/resolution/transition 边界检查
  - 新增 `safe_error_response()` 工具函数到 param_utils.py

## [0.12.10] - 2026-03-22

### 新增 (Added)
- R10: 硬件自适应 + 性能优化
  - `modules/hardware/` 新模块：硬件探测 + 自适应编码策略
  - CPU/RAM/GPU 自动检测（macOS/Linux）
  - FFmpeg 硬件加速三级策略：VideoToolbox → NVENC → libx264 CPU
  - 渲染并发数基于系统资源智能推荐（1-4）
  - RenderConfig 支持 `video_encoder` / `hwaccel` / `encoder_extra_args`
  - auto_render.py 全部硬编码 libx264 替换为可配置编码器
  - Preflight 集成硬件画像检测项
  - API：`/api/system/hardware` 端点
  - 22 个新增测试，917 全量通过

## [0.12.9] - 2026-03-22

### 新增 (Added)
- R9: 订阅制开关
  - `modules/subscription/` 新模块：FeatureGate + Tier 枚举
  - Free/Pro 双层功能控制（8 个免费功能 + 11 个 Pro 功能）
  - API：`/api/subscription/status` + `/api/subscription/gate` + `/api/subscription/upgrade`
  - 持久化到 settings.json
  - 11 个新增测试

## [0.12.8] - 2026-03-22

### 新增 (Added)
- R8: Prompt 剪辑引擎 — 自然语言时间线编辑
  - `modules/prompt_editing/` 新模块：规则引擎解析器 + 执行器
  - 支持 5 种编辑指令：删除/移动/裁剪/倒序/变速
  - 中英文双语指令支持（"删除第2个片段" / "remove clip 3"）
  - `POST /api/timeline/edit-by-prompt` API 端点
  - 17 个新增测试覆盖解析器 + 执行器

## [0.12.7] - 2026-03-22

### 新增 (Added)
- R7: Step 6 拖拽时间线编辑
  - `POST /api/timeline/reorder` — 片段重排序，持久化到 script_matched.json
  - `POST /api/timeline/trim` — 片段裁剪（source_start/source_end 调整）
  - TimelineClipBlock.vue 支持 HTML5 拖拽重排序（dragstart/drop/dragover）
  - Pinia store 新增 `reorderClips()` action（乐观更新 + 后端持久化）
  - 拖拽悬停视觉反馈（黄色虚线边框）
  - 7 个新增测试覆盖 reorder/trim API

## [0.12.6] - 2026-03-22

### 新增 (Added)
- R6: 融合检索模式（`retrieval_mode="fusion"`）— 通过 RRF 加权合并文本向量 + 视觉向量搜索结果
- R6: 搜索 UI 新增"视觉"和"融合"检索模式按钮
- R6: 视觉搜索状态徽章（显示 CLIP 可用性和视觉嵌入数量）
- R6: `check_ai_status()` 新增 `clip_available` 字段
- R6: API 响应新增 `visual_search_enabled` / `visual_embeddings_count`
- R6: `retrievalModeZh()` 支持"视觉检索"和"融合检索"中文标签
- 11 个新增测试，全量回归 860 passed / 50 skipped

## [0.12.5] - 2026-03-22

### 改进 (Changed)
- R5: 向量搜索引擎 API 完整暴露
  - `/api/library/search?mode=visual` 支持 CLIP 跨模态图文搜索
  - `count_matching_assets()` 支持 visual 模式
  - `stats()` 新增 `visual_search_enabled` 和 `visual_embeddings_count`
  - 6 个新增测试覆盖 API 模式验证和 stats 字段

## [0.12.4] - 2026-03-22

### 改进 (Changed)
- R4: `_build_embedding_source()` 纳入 ASR 转录文本，语音内容可通过向量搜索发现
  - 支持 `analysis_json.asr_text` 和 `analysis_json.transcription.text` 双路径提取
  - 转录文本截断 2000 字符，保留语义元数据空间
  - `_upsert_embedding_for_asset` / `_refresh_embeddings_incremental` 管道适配
  - 7 个新增测试覆盖 ASR 纳入、截断、降级

## [0.12.3] - 2026-03-22

### 新增 (Added)
- R3: `modules/library/vision/` 子模块 — CLIP 视觉分析通道
  - `CLIPEncoder`: 延迟加载 CLIP 模型，支持图像/文本编码（512 维）
  - `VisionMixin`: 关键帧提取 → CLIP 编码 → 视觉索引
  - 双 VectorIndex 架构：文本嵌入（1536 维）+ 视觉嵌入（512 维）并行
  - `search_assets(retrieval_mode="visual")` 跨模态图文搜索
  - `asset_visual_embeddings` 数据库表
  - 11 个新增测试（mock CLIP）
  - 全量回归 836 passed / 50 skipped

## [0.12.2] - 2026-03-22

### 新增 (Added)
- R2: `modules/library/semantic/` 子模块 — 独立的向量索引引擎和查询嵌入缓存
  - `VectorIndex`: FAISS IndexFlatIP 优先，NumPy 暴力搜索降级
  - `EmbeddingCache`: LRU 查询嵌入缓存（128 条，3600s TTL）
  - FAISS 索引持久化到磁盘（`cache/faiss/`），支持增量 add/remove
  - OMP 冲突防护（torch + FAISS 共存）
  - 29 个新增测试覆盖 VectorIndex + EmbeddingCache

### 重构 (Refactored)
- `core_mixin.py` 向量搜索逻辑委托给 `VectorIndex`，减少约 80 行内联代码
- `_get_query_embedding()` 支持 `EmbeddingCache` 新后端，保留 legacy dict fallback
- `GlobalMediaLibrary.__init__()` 初始化语义基础设施实例

## [0.12.1] - 2026-03-22

### 修复 (Fixed)
- M3: `/api/projects` 不再返回已删除的残留项目，新增 `/api/projects/cleanup` 清理端点
- H2: Library Facade 新增 `sync_project_materials()` 方法，支持项目分析结果回写全局库
- M5: `RenderConfig.from_aesthetic_preset()` 根据美学预设自动适配横竖屏方向

### 新增 (Added)
- `PRESET_ORIENTATIONS` 常量（refinement.py），定义每个美学预设的推荐方向
- 9 个新测试覆盖 M3/H2/M5 三项修复

## [0.11.0] - 2026-03-22

### 修复 (Fixed)
- R1: P0 两处 Segfault（null 参数 /api/init + step=99 越界 /api/run_step）(BUG-001, BUG-002)
- R2: P0 安全修复（CSRF 双开关逻辑 + provider 枚举校验 + 搜索长度限制）(SEC-001, BUG-004, SEC-002)
- R3: P1 接口补全（health/projects/workflow-status/settings 路由 + UnicodeDecodeError + run_step 防御）(BUG-006/007/008)
- R8: P1 Step 3 AI 脚本生成实现，清除残留 TODO (BUG-003)
- R10: P3 视觉一致性（图标统一 + 空状态文案 + ESC 关弹窗 + 标题统一 + Canvas 说明）(UX-P3-001~005)

### 新增 (Added)
- R4: 预检路由守卫 + 向导断点补救引导 (UX-P1-001, UX-P1-002)
- R5: 项目弹窗优化（路径 readonly + 目录说明 + 项目名生效）(UX-P2-001, UX-P2-007)
- R6: 破坏性操作二次确认 + AI 设置测试连接 (UX-P2-003, UX-P2-004)
- R7: Job 进度可视化 + 无项目新建引导 + 标签种子数据 (UX-P2-005/006, DATA-001)
- R9: SQLite 外键约束启用 + requirements.txt 依赖分层 (DATA-002, DEP-001)

### 重构 (Refactored)
- R11: Library 单体拆分 — global_media_library.py 从 13,282 行精简为 269 行 Facade (ARCH-001)
  - 提取 8 个 Mixin：FingerprintMixin, GDriveMixin, DuplicateDetectionMixin, PathRelinkMixin, TagManagerMixin, AutoTaggerMixin, CoreMixin, SchemaMixin
  - 提取 _constants.py 共享常量（避免循环导入）
  - 所有公共接口零变更，全量回归测试 787 passed / 50 skipped

## [0.10.0] - 2026-03-20

### 修改 (Changed)
- 项目目录重组：开发代码（modules/, apps/, tests/, tools/, .agents/）迁入 project/ 子目录
- 技术文档（docs/tech-specs/）迁入 project/docs/tech-specs/
- 开发报告和计划文档迁入 project/docs/
- 版本文件（VERSION, CHANGELOG.md, requirements.txt, LICENSE）迁入 project/
- CLAUDE.md 所有路径引用更新为 project/ 前缀

### 新增 (Added)
- project/.claude/CLAUDE.md — Claude Code 开发工作区入口指令
- .gitignore 追加 project/ 工作区忽略规则

### 技术说明
- 零 Python 代码变更：内部相对路径（parents[N]）自动适配新目录层级
- 全量回归测试通过：764 passed, 50 skipped, 0 failures, 0 errors

## [0.9.1] - 2026-03-20

### 修复 (Fixed)
- 修复 386 个 PermissionError 测试错误：macOS TCC 安全机制下 `~/Downloads` 文件 `exists()` 返回 True 但 `open()` 被拒绝（BF-001）
- 语义系统 seed 数据导入增加 PermissionError 防护，不可读时静默跳过
- `test_semantic_system.py` / `test_tag_recall.py` skipif 条件改为实际文件可读性检查

## [0.9.0] - 2026-03-20

### 新增 (Added)
- Playwright E2E 测试框架 + 15 个测试覆盖 5 条核心用户路径（T-0902）
- 发布链路 OpenAPI 3.0 规范文档（29 个端点）+ `/api/docs/publish` 路由（T-0903）
- 安全事件审计日志（Origin/CSRF/Token 失败记录）+ 暴力破解检测（T-0904）

### 修改 (Changed)
- server.py 从 7,643 行拆分至 1,936 行，提取 workflow_runner / publish_orchestrator / settings_service / template_service / governance_service 等 services 层（T-0901）
- system_routes.py 补全 `parse_str_param` / `parse_int_param` 输入校验（T-0904）

## [0.8.0] - 2026-03-19

### 新增 (Added)
- YouTube OAuth 2.0 完整授权流程（浏览器授权 + Keychain 存储 + 自动刷新）（T-0801）
- 平台就绪状态标识（connector_ready / connector_kind / setup_hint）+ 前端三色芯片（T-0802）
- 发布历史结构化展示（三标签页 + 可展开详情 + 分页加载）（T-0803）
- 队列恢复 UI（中断任务检测 + 批量重试/忽略 + 启动横幅）（T-0804）
- Webhook 连接器配置向导 + CRUD 4 端点 + 连接测试（T-0805）

## [0.7.0] - 2026-03-19

### 新增 (Added)
- 发布面板术语人性化 + 平台 checkbox picker，移除 input_mode / session_id 等开发术语（T-0601）
- 导出面板 toggle 卡片多选 + 结构化计划/结果展示（T-0602）
- 发布面板错误恢复引导（recovery_hint 消费 + 错误分类 + 重试按钮）（T-0603）
- 项目名可读化 + inline 重命名能力（project_meta.json）（T-0604）
- 引导流程增强（交互式 3 步向导 + 文件夹导入）（T-0605）
- 12 个能力面板表单默认值 + 占位符文案集中管理（T-0606）

## [0.6.0] - 2026-03-19

### 新增 (Added)
- 审计日志系统
- 队列恢复 UX 改进
- YouTube 发布 connector 骨架

### 修复 (Fixed)
- 修复 23/26 UX 问题
