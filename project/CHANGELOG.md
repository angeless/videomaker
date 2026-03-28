# 变更日志

所有重要变更都将被记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 规范。

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
