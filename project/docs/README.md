# 模块化拆分文档索引

本目录用于指导阶段2模块化重构与后续并行开发。

- `changelog-v0.3.1.md`：v0.3.1 变更记录（P0.4 帧读取安全上限）
- `module-index.md`：模块职责、目录草案、受保护区/可改区
- `module-dependency-matrix.md`：允许/禁止依赖规则与边界约束
- `file-migration-map.md`：文件迁移路径与回滚映射
- `stage2-completion.md`：阶段2已落地的最终目录、映射、验证与回滚
- `capability-decomposition-v1.md`：按产品能力拆分（选题库/文案/粗剪/快剪/精剪/导出/配音）
- `capabilities-api.md`：能力模块 API（可独立调用各能力）
- `agent-usability-roadmap-v1.md`：Agent 易用性路线图（在人用流程不变前提下扩展 Agent API / 模板 / Skill 编排）
- `changelog-stability-security-ux.md`：2026-03-01 稳定性/安全性/UX 优化记录（P0 subprocess timeout + P1 安全 + P2 功能，共修改11个文件）

执行建议：
1. 先读 `module-index.md`
2. 再按 `module-dependency-matrix.md` 设置开发边界
3. 最后按 `file-migration-map.md` 分步迁移并逐步验证
