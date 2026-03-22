# VideoEditor — Claude Code 项目指令

> 本文件是 Claude Code 在 project/ 目录下开发时的主入口指令。
> 每次启动开发前，必须先读取技术规范文档。

## 技术规范文档路由

开始任何开发任务前，必须按顺序读取以下文件：

1. `docs/tech-specs/architecture.md` — 架构与模块边界
2. `docs/tech-specs/dev-governance.md` — 开发治理流程
3. `docs/tech-specs/coding-standards.md` — 编码标准与质量要求
4. `docs/tech-specs/testing-strategy.md` — 测试策略与规范

## 状态文件路由

- `VERSION` — 当前版本号
- `CHANGELOG.md` — 变更日志
- `TODO_NEXT.md` — 待办进度（自动任务选择入口）
- `WISHLIST.md` — 衍生建议清单
- `docs/dev-plans/` — 开发计划（按版本）
- `docs/audit/` — 审计记录
- `docs/test-reports/` — 测试报告
- `docs/decisions/` — 架构决策记录

## 经验文件路由（编码实现时按需读取）

- `../docs/experience/common-errors.md` — 已知错误模式（Phase 2 门禁自查）

## 自动化开发循环

详见根目录 CLAUDE.md 中的「Claude Code 自动化开发指令」章节。
完整七阶段操作规范见 `docs/tech-specs/dev-governance.md`。
