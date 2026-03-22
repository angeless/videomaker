# 变更日志

所有重要变更都将被记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 规范。

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
