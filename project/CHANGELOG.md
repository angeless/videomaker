# 变更日志

所有重要变更都将被记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 规范。

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
