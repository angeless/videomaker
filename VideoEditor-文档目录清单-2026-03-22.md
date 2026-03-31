# VideoEditor 项目文档完整目录清单

> 盘点日期: 2026-03-22 | 共计 ~100+ 文档 | 总量约 1.0 MB

---

## 一、根目录核心文件

| 文件 | 大小 | 最后修改 | 内容概要 |
|------|------|---------|---------|
| `CLAUDE.md` | 8.4 KB | 03-22 | 项目级工作路由+上下文（v3.0），定义开发/产品模式、技术规范路由、五文档体系 |
| `README.md` | 2.9 KB | 03-10 | 快速启动指南，核心能力（12 模块）、工作流画布、Agent API |
| `VideoEditor-v0.12.1-Audit-Report.md` | 23 KB | 03-22 | v0.12.1 全面深度审计（架构/189端点/安全/边界/数据库/测试/UX，综合 7.1/10） |

---

## 二、产品文档 `/docs/`

### 审计与评测

| 文件 | 大小 | 内容概要 |
|------|------|---------|
| `2026-03-19_全面审计报告_V1.0.md` | 23 KB | 早期版本综合审计 |
| `2026-03-21_产品体验评测报告_v0.11_V1.0.md` | 11 KB | v0.11 用户测试，痛点 M1-M5，体验缺口 H2-H4 |
| `audit/全面审计报告_v0.10.0.md` | 34 KB | v0.10.0 完整系统审计 |
| `audit/全面审计报告_v0.10.0_R2.md` | 33 KB | v0.10.0 修复后复审 |

### 竞品与市场

| 文件 | 大小 | 内容概要 |
|------|------|---------|
| `2026-03-21_竞品调研报告_V2.0.md` | 47 KB | 竞品工具分析、市场定位、功能差异、差异化机会 |
| `AI_Video_Editing_Competitive_Analysis_2026.md` | 40 KB | 2026 AI 视频编辑工具市场调研 |

### 产品设计与需求

| 文件 | 大小 | 内容概要 |
|------|------|---------|
| `prd/product_design.md` | 35 KB | 产品系统设计 v1.0，12 个能力模块、复制原则、审计追踪、API 规格 |
| `ux-audit/UX_REPORT_20260315.md` | 23 KB | UX 评测报告，痛点与可用性建议 |
| `VideoEditor-Design-System-v1.0.html` | 78 KB | UI/UX 设计系统完整规范（HTML 格式） |

### 素材质量评分体系（4 篇，共 147 KB）

| 文件 | 大小 | 内容概要 |
|------|------|---------|
| `素材质量评分_开发指令_完整版_v1.md` | 63 KB | 完整开发指令，算法、边界、API 合约 |
| `素材质量评分体系_详细设计_v2.md` | 35 KB | v2 详细设计，框架/指标/评分模型 |
| `素材质量评分_实现规格_v2_appendix.md` | 36 KB | v2 实现附录 |
| `素材质量评分_边界安全分析_v1.md` | 13 KB | 边界安全分析 |

### 其他产品文档

| 文件 | 大小 | 内容概要 |
|------|------|---------|
| `2026-03-19_版本开发任务计划_v0.7-v0.9_V1.0.md` | 62 KB | v0.7-v0.9 任务分解与里程碑 |
| `素材处理优化方案_Keywords_and_Quality.md` | 15 KB | 关键词提取与质量优化 |
| `PATH-MIGRATION-INSTRUCTIONS.md` | 9.5 KB | 目录迁移指南 |
| `queue_recovery_rules.md` | 3.9 KB | 任务队列恢复规则 |
| `statement_v0.3_20260302.md` | 16 KB | v0.3 产品状态声明 |

---

## 三、技术规范 `/project/docs/tech-specs/`（五文档体系，共 247 KB）

| 文件 | 大小 | 职责 |
|------|------|------|
| `dev-governance.md` | 87 KB | "怎么做开发"：12 阶段治理、门禁、自动化基础设施 |
| `architecture.md` | 48 KB | "系统长什么样"：模块边界、数据流、API 层、扩展原则 |
| `coding-standards.md` | 68 KB | "怎么写代码"：Python/Flask 约定、错误处理、安全、日志 |
| `testing-strategy.md` | 12 KB | "怎么做测试"：测试类型、覆盖目标(90%+)、审批门禁 |
| `product-standards.md` | 12 KB | "产品怎么做"：PRD 标准、竞品分析格式、验收标准 |
| `phase8-audit.md` | 8.2 KB | Phase 4.5 子 Agent 验收规范 |
| `phase8-audit-prompts.md` | 11 KB | 审计验证结构化 Prompt |
| `phase8-audit-integrator.md` | 8.7 KB | 多流审计结果合并规则 |

---

## 四、开发计划 `/project/docs/dev-plans/`（10 篇，共 120 KB）

### 版本级计划

| 文件 | 大小 | 内容概要 |
|------|------|---------|
| `dev-plan-v0.11.md` | 40 KB | v0.11 计划：R1-R8 共 8 个任务 |
| `dev-plan-v0.12.md` | 52 KB | v0.12 计划：R1-R12 共 12 个任务（多模态分析/时间线/Prompt 剪辑） |

### 实施计划（per-release）

| 文件 | 版本 | 内容概要 |
|------|------|---------|
| `2026-03-21-r1-implementation-plan.md` | v0.11 R1 | 遗留问题审计与修复 |
| `impl-plan-v0.12.1.md` | v0.12.1 | 语义分析基础设施增强 |
| `impl-plan-v0.12.2.md` | v0.12.2 | 视觉分析管线（CLIP） |
| `impl-plan-v0.12.3.md` | v0.12.3 | 音频分析通道增强 |
| `impl-plan-v0.12.4.md` | v0.12.4 | 向量搜索引擎（FAISS） |
| `impl-plan-v0.12.5.md` | v0.12.5 | 融合检索 + 搜索 UI |
| `impl-plan-v0.12.10.md` | v0.12.10 | 硬件适配与性能优化 |
| `impl-plan-v0.12.11.md` | v0.12.11 | 产品体验修复 |

---

## 五、审计记录 `/project/docs/audit/`

| 文件 | 内容 |
|------|------|
| `2026-03-22-r2-audit.md` | R2（视觉分析）审计 |
| `2026-03-22-r3-audit.md` | R3（音频分析）审计 |
| `2026-03-22-r10-audit.md` | R10（硬件适配）审计 |
| `2026-03-22-r12-final-audit.md` | R12（最终集成）审计 |

---

## 六、版本交付报告 `/project/docs/versions/`

| 文件 | 类型 |
|------|------|
| `task-report-v0.12.1.md` | v0.12.1 任务完成报告 |
| `task-report-v0.12.2.md` / `test-report-v0.12.2.md` | v0.12.2 任务+测试 |
| `task-report-v0.12.3.md` / `test-report-v0.12.3.md` | v0.12.3 任务+测试 |
| `test-report-v0.12.10.md` | v0.12.10 测试报告 |
| `audit-report-v0.11.0-r1.md` / `test-report-v0.11.0-r1.md` | v0.11.0 R1 审计+测试 |

---

## 七、历史完成报告 `/project/docs/`（14 篇，v0.7-v0.10）

| 版本 | 文件 |
|------|------|
| v0.7.0 | `v0.7.0_completion_report.md` |
| v0.8.0 | `v0.8.0_completion_report.md` |
| v0.9.0 | `v0.9.0_completion_report.md` + T0901-T0904 各 completion + implementation |
| v0.9.1 | `v0.9.1_BF001_completion_report.md` + implementation |
| v0.10.0 | `v0.10.0_PATH_MIGRATION_completion_report.md` + implementation |

---

## 八、项目状态文件 `/project/`

| 文件 | 大小 | 内容概要 |
|------|------|---------|
| `VERSION` | 7 B | 当前版本号（0.12.1 或 0.12.12） |
| `CHANGELOG.md` | ~10 KB | 正式变更日志，v0.7.0 到 v0.12.12 |
| `TODO_NEXT.md` | ~3 KB | 当前进度：v0.12.12，R1-R12 全部 ✅ |
| `WISHLIST.md` | ~1.5 KB | 衍生建议 W-001 到 W-010+ |

---

## 九、其他参考文档

| 文件 | 大小 | 内容概要 |
|------|------|---------|
| `project/docs/capabilities-api.md` | 26 KB | 12 个能力模块 API 规格 |
| `project/docs/api/openapi-publish.yaml` | 41 KB | OpenAPI 3.0 发布能力定义 |
| `project/docs/module-index.md` | 3.9 KB | 模块索引 |
| `project/docs/module-dependency-matrix.md` | 2.9 KB | 模块依赖矩阵 |
| `project/docs/roadmap_v2.0.md` | 6.5 KB | v2.0 路线图 |
| `project/docs/next_dev_plan.md` | 20 KB | 后续开发计划 |
| `project/docs/benchmark-baseline.md` | 1.8 KB | 性能基准 |
| `project/docs/copy-placeholders.md` | 7.9 KB | UI 文案占位符 |
| `docs/experience/common-errors.md` | 1.6 KB | 已知错误模式清单 |

### Relink 冻结文档（5 篇，共 51 KB）

| 文件 | 内容概要 |
|------|---------|
| `project_relink_freeze_audit_report_v1.md` | 冻结前审计 |
| `project_relink_freeze_rules_and_guardrails_v1.md` | 冻结规则 |
| `project_relink_maintenance_handover_v1.md` | 维护交接 |
| `project_relink_adapter_contract_v1.md` | 适配器合约 |
| `project_relink_dev_policy_v1.md` | 开发策略 |

---

## 文档体系总结

| 类别 | 数量 | 总量 | 用途 |
|------|------|------|------|
| 产品文档 | ~19 篇 | 468 KB | 产品规格、审计、竞品、UX、设计系统 |
| 技术规范 | 8 篇 | 247 KB | 治理、架构、编码标准、测试策略、产品标准 |
| 开发计划 | 10 篇 | 120 KB | v0.11-v0.12 版本级与任务级计划 |
| 审计记录 | 4 篇 | 9 KB | R2/R3/R10/R12 审计 |
| 版本报告 | 8 篇 | 14 KB | 任务完成+测试报告 |
| 历史报告 | 14 篇 | 45 KB | v0.7-v0.10 完成报告 |
| 参考文档 | 20+ 篇 | 100+ KB | API、路线图、模块索引、交接等 |
| 状态文件 | 4 个 | 15 KB | VERSION/CHANGELOG/TODO_NEXT/WISHLIST |
| **合计** | **~100+** | **~1.0 MB** | |

---

*清单结束*
