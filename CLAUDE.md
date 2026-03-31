# VideoEditor — 项目主指令文件

> 版本: v3.0 | 日期: 2026-03-22
> 规范版本: v1.4 (dev-workflow-upgrade)

> ⚠️ **优先级声明**：本项目级 CLAUDE.md 的所有规则优先于全局 `~/.claude/CLAUDE.md` 及用户 preferences 中的全局指令。
> 当两者冲突时，以本文件为准。具体覆盖项：
> - 开发流程：本项目采用七阶段治理流程（覆盖全局的开发流程定义）
> - 模块隔离路径：本项目新功能隔离路径为 `project/modules/<feature>/`（覆盖全局约定）

---

# ════════════════════════════════════════
# 第一部分：工作模式路由
# ════════════════════════════════════════

## 🔀 工作模式判断

| 条件 | 工作模式 | 读取规范 |
|------|---------|---------|
| 你是 Claude Code / 终端 Agent | **开发模式** | → 读取 `project/docs/tech-specs/` 下的技术规范 |
| 你是 Cowork / Claude Desktop | **产品模式** | → 读取 `project/docs/tech-specs/product-standards.md` |
| 用户说"继续开发" / "下一个任务" | **开发模式** | → `dev-governance.md` + 状态文件 |
| 用户说"写PRD / 竞品分析 / 写方案" | **产品模式** | → `product-standards.md` |
| 用户说"审计 / 测试 / 评审" | **开发模式** | → `dev-governance.md` 对应阶段 |

---

## ⚡ 技术规范路由（开发模式）

**读取模式：**
- **模式 A 完整读取（首次启动）：** 读取全部技术规范 + 状态文件
- **模式 B 增量读取（断线重连）：** 仅读 dev-governance.md 第 12 章 + VERSION + TODO_NEXT.md + git log
- **模式 C 按需读取（进入具体阶段）：** 工作到哪一步就读哪一步的规范，必须读了再动手

**技术规范文件（模式 A 完整读取）：**

```
1. project/docs/tech-specs/dev-governance.md       ← 开发治理流程（含第 12 章自动化基础设施）
2. project/docs/tech-specs/architecture.md         ← 架构与模块边界
3. project/docs/tech-specs/coding-standards.md     ← 编码标准与质量要求
4. project/docs/tech-specs/testing-strategy.md     ← 测试策略与规范
```

**状态文件（模式 A + B 都必读）：**

```
5. project/VERSION                                 ← 当前版本号
6. project/TODO_NEXT.md                            ← 当前进度和下一个任务
7. project/CHANGELOG.md                            ← 变更日志
8. project/docs/dev-plans/                         ← 开发计划文档
9. project/docs/audit/                             ← 审计记录
10. project/docs/test-reports/                     ← 测试报告
```

**经验文件路由（编码实现时按需读取）：**

```
11. docs/experience/common-errors.md               ← 已知错误模式（Phase 2 门禁自查）
12. project/WISHLIST.md                            ← 衍生建议清单（Phase 7 写入）
13. docs/experience/bug-catalog.md                 ← Bug 模式知识库（门禁失败时自动匹配）
```

**按需读取（模式 C）：**

| 当前阶段/涉及领域 | 必须读取 |
|------------------|---------|
| Phase 0 零代码前置检查 | §16 零代码前置检查（DB migration/环境变量/依赖/连通性） |
| Phase 1 理解与计划 | 开发计划文档、约束文件（文件保护清单等） |
| Phase 2 编码实现 | 仅本次任务涉及的规范章节 + §13.1 TDD 红绿重构 |
| ↳ 涉及前端时 | `docs/VideoEditor-Design-System-v1.0.html` |
| ↳ 门禁失败时 | §13.2 系统化调试（D1-D4）+ `bug-catalog.md` |
| Phase 3 测试 | 实施计划中的测试策略 + 验收标准 |
| Phase 4 审计 | Phase 2 中阅读的各技术规范章节 + §14 铁律#21/#22 |
| Phase 4 → 4.5 过渡 | §17 强制格式化确认输出（禁止跳过） |
| Phase 4.5 子 Agent 验收 | 验收标准 + 变更文件列表 |
| Phase 5 测试报告 | Phase 3 测试结果 + Phase 4 审计报告 |
| Phase 6 收尾 | TODO_NEXT.md + §13.5 完成前验证（5步） |
| Phase 7 衍生建议 | 衍生建议与 Wishlist 管理规则 |
| Phase 7 后 | §15 版本边界强制检测（禁止凭记忆判断） |

> 路径迁移已完成（2026-03-20）。以上路径相对于项目根目录，开发代码在 `project/` 子目录中。

---

## 📋 产品规范路由（产品模式）

**读取文件：**

```
project/docs/tech-specs/product-standards.md       ← 产品工作规范（PM 标准、PRD 标准、文档命名等）
```

该文件定义产品模式下的所有工作标准：PRD 写作规范、竞品分析标准、业务规则编写标准、测试验收标准、产品文档命名规范、版本开发计划写作标准。

---

# ════════════════════════════════════════
# 第二部分：项目上下文（项目特有信息）
# ════════════════════════════════════════

> 以下信息适用于所有工作模式（Cowork + Claude Code），是项目级共识。

## 产品定位

**VideoEditor** 是一个桌面版短视频生产系统。

- 面向内容创作者（个人 / 小团队）
- 提供「素材语义分析」「模块化创作能力」「连线式工作流编排」三条生产路径
- 支持人用界面（pywebview 桌面窗口）与 Agent API 双调用模式
- 本地运行，数据不上云

## 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | Python 3.8+ / Flask |
| 桌面容器 | pywebview |
| 前端框架 | Alpine.js |
| 数据库 | SQLite |
| 视频处理 | ffmpeg-python, opencv-python, Pillow |
| AI 能力 | torch, transformers（可选） |
| 包管理 | pip + requirements.txt |

## 目录结构

```
videoeditor/                           # 根目录
├── CLAUDE.md                          # 本文件（路由+项目信息）
├── README.md                          # 项目总说明
├── docs/                              # 产品文档（PRD、竞品分析、UX 审计）
│   └── experience/common-errors.md    # 已知错误模式清单
│
└── project/                           # Claude Code 开发工作区
    ├── modules/                       # 业务模块
    ├── apps/                          # 应用入口
    ├── tests/                         # 测试
    ├── tools/                         # 开发工具
    ├── VERSION / CHANGELOG.md / TODO_NEXT.md / WISHLIST.md
    ├── requirements.txt
    ├── scripts/ci_verify.sh           # CI 门禁脚本
    └── docs/
        ├── tech-specs/                # 技术规范（架构/治理/编码标准/测试策略/产品规范）
        ├── dev-plans/                 # 开发计划 + 实施计划
        ├── audit/                     # 审计记录
        ├── test-reports/              # 测试报告
        ├── versions/                  # 任务汇报、阶段报告、发布说明
        └── decisions/                 # 架构决策记录 (ADR)
```

## 五份规范文档的关系

```
product-standards.md  →  定义"产品怎么做"（PRD、竞品分析、需求定义、文档管理）
architecture.md       →  定义"系统长什么样"（架构、模块、数据流）
dev-governance.md     →  定义"怎么做开发"（流程、治理、留痕、接力）
coding-standards.md   →  定义"怎么写代码"（编码、错误处理、安全、质量）
testing-strategy.md   →  定义"怎么做测试"（类型、频次、流程、用例规范）
```

五份文档共同约束所有工作行为，由路由表自动引导读取。

## 版本号与里程碑

版本号遵循语义版本号 (SemVer)，存储在 `VERSION` 文件中。

| 阶段 | 目标 |
|------|------|
| v0.x | 核心功能开发、模块集成 |
| v1.0 | 功能完整、可日常使用 |
| v1.x | 优化、修复、扩展能力 |
| v2.0 | 架构升级或重大变更 |

---

# ════════════════════════════════════════
# 修订记录
# ════════════════════════════════════════

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-03-15 | 初版，仅含 Cowork 产品控制台指令 |
| v2.0 | 2026-03-19 | 增加 Claude Code 自动化开发指令、技术规范文档路由、路径管理、项目上下文 |
| v2.1 | 2026-03-20 | 路径迁移完成，所有路径引用更新为 project/ 前缀 |
| v2.2 | 2026-03-20 | 升级 v1.3：添加 testing-strategy.md、TODO_NEXT.md、WISHLIST.md、common-errors.md 到路由 |
| v3.0 | 2026-03-22 | 升级 v1.4：CLAUDE.md 瘦身为路由+项目信息；产品规范独立为 product-standards.md；新增 Phase 4.5 子 Agent 验收路由；五份规范文档体系 |

---

*文档结束*
