# 第六部分：版本交叉审计流程（§6.1–§6.2）

> **导航**: [← 返回索引](dev-governance.md) | [子 agent 审计 Prompt →](dev-governance-part6-audit-prompts.md) | [整合 agent 规范 →](dev-governance-part6-audit-integrator.md)
>
> 本文件定义版本级交叉审计的流程总览和发起器规范。
> 审计子 agent 的 Prompt 模板和检测标准拆分在 `dev-governance-part6-audit-prompts.md`。
> 整合 agent 的规范拆分在 `dev-governance-part6-audit-integrator.md`。
>
> **TL;DR（上下文受限时仅读此块）**:
> 版本内所有任务的 Phase 1-7 循环完成后，进入 Phase 8（版本交叉审计）。发起器收集版本上下文，按 Stage 1→2→3 串行 dispatch 独立子 agent 审计，最后由整合 agent 生成版本审计报告。三阶段顺序：Stage 1 规格合规 → Stage 2 质量工程 → Stage 3 完整性与 UX（前一阶段通过后一阶段才启动）。审计报告归档到 `docs/audits/v{X.Y.Z}/`。只有 Critical 级发现阻断版本发布。

---

## §6.1 审计流程概述

### 触发条件

Phase 8 在以下任一条件满足时触发：

1. **自动触发**：版本内所有 Planned 任务均已完成 Phase 1-7 循环（即 TODO_NEXT.md 中本版本无剩余 Planned 任务）
2. **手动触发**：用户输入"发起审计""版本审计""开始审计"等指令

### 三阶段审计模型

```
Phase 8 启动
    │
    ▼
Stage 1: Spec Review（规格合规审计）
    │ 通过
    ▼
Stage 2: Quality Review（质量工程审计）
    │ 通过
    ▼
Stage 3: Completeness & UX Review（完整性与体验审计）
    │ 通过
    ▼
整合 Agent：合并三份报告 → 生成版本审计报告
    │
    ▼
归档到 docs/audits/v{X.Y.Z}/
    │
    ▼
Phase 8 ③ 门禁检查
```

### 顺序约束

- Stage 1 必须先通过，Stage 2 才能启动（规格不对，质量审计无意义）
- Stage 2 必须先通过，Stage 3 才能启动（质量不达标，审计完整性和体验无意义）
- Stage 3 仅在项目有前端时完整执行；纯后端项目仅检查"端到端可用性"和"新用户/老用户兼容"两项
- 如果项目没有 PRD 或 `product-standards.md`，Stage 3 跳过"文案一致性"检测项，其余项基于代码和实际行为审计
- 如果 Stage 1 或 Stage 2 发现 Critical 级问题，暂停审计流程，先修复后重新 dispatch 该 Stage 验证
- **重审上限**：每个 Stage 最多重新 dispatch 3 次。第 3 次仍有 Critical → 停止审计流程，升级为人工审查

### "通过"的判定标准

- **Stage 通过** = 该 Stage 无 Critical 级发现
- 存在 Important/Minor/Observation 级发现不阻断下一 Stage
- Critical 发现修复后需重新 dispatch 该 Stage 的子 agent 验证

### 子 agent 上下文约束

> 以下两条硬约束在审计流程中始终生效：

1. **上下文精简原则**：每个子 agent 只拿到该 Stage 所需的最小上下文包（见 §6.2 上下文分配表）。不继承父对话的全部历史。由发起器负责组装。
2. **隔离原则**：审计子 agent 是只读审计，不修改任何文件。如需修复，由审计流程结束后的用户决策驱动。

### 与现有 Phase 体系的位置关系

```
任务 1: Phase 1→2→3→4→4.5→5→6→7 → 下一个任务
任务 2: Phase 1→2→3→4→4.5→5→6→7 → 下一个任务
...
任务 N: Phase 1→2→3→4→4.5→5→6→7 → 版本任务全部完成
                                         │
                                         ▼
                                   Phase 8: 版本交叉审计
                                         │
                                         ▼
                                   Idle Loop（§0.11 Gap 扫描）
                                         │
                                         ▼
                                   版本封板 / 发布
```

> **注意**：Phase 8 是版本级审计，不替代任务级的 Phase 4 审计。Phase 4 关注单个任务的实施合规，Phase 8 关注整个版本的系统性质量。

---

## §6.2 审计发起器规范

### 发起器职责

审计发起器在主对话中执行，负责：

1. 收集版本上下文信息
2. 为每个 Stage 组装精简上下文包
3. 按顺序 dispatch 子 agent（Stage 1 → 2 → 3）
4. 每个 Stage 子 agent 返回后，检查是否有 Critical 发现
5. 三个 Stage 全部完成后，dispatch 整合 agent
6. 验证审计报告完整性（Phase 8 ③ 门禁）
7. 归档审计报告到 `docs/audits/v{X.Y.Z}/`

### 版本上下文收集清单

发起器在启动审计前，必须收集以下信息并写入"共享上下文块"：

```markdown
## 审计共享上下文

### 版本信息
- 版本号：v{X.Y.Z}（读取 VERSION 文件）
- 版本分支：test-v-{X}-{Y}（读取当前分支或 dev-plan）
- 审计日期：{YYYY-MM-DD}

### 变更范围
- 变更文件列表：（git diff --name-status {版本起始commit}..HEAD）
- 每个文件的变更类型：A（新增）/ M（修改）/ D（删除）
- 变更文件总数：N 个

### 版本开发摘要
- 本版本 CHANGELOG 条目（从 CHANGELOG.md 提取本版本部分）
- 开发计划中本版本的任务清单及完成状态（从 dev-plan 提取）
- 本版本任务总数：N 个，已完成：N 个
```

### 上下文分配表

> **核心原则**：每个子 agent 只拿到该 Stage 审计所需的最小上下文。不给多余信息。

| 内容 | Stage 1 (规格合规) | Stage 2 (质量工程) | Stage 3 (完整性+UX) | 整合 Agent |
|------|:--:|:--:|:--:|:--:|
| 审计共享上下文 | ✅ | ✅ | ✅ | ✅ |
| dev-plan（本版本任务定义） | ✅ | — | — | — |
| Phase 1 各任务的允许修改文件列表 | ✅ | — | — | — |
| git diff summary（变更内容摘要） | ✅ | ✅ | ✅ | — |
| architecture.md | ✅ | — | — | — |
| coding-standards-core.md | — | ✅ | — | — |
| coding-standards 相关子文件（按变更涉及领域选取） | — | ✅ 按需 | — | — |
| 变更文件源码（完整内容） | — | ✅ | ✅ 仅前端 | — |
| UI 设计规范 | — | — | ✅ | — |
| product-standards.md | — | — | ✅ | — |
| Stage 1 审计报告 | — | — | — | ✅ |
| Stage 2 审计报告 | — | — | — | ✅ |
| Stage 3 审计报告 | — | — | — | ✅ |
| 上一版本 audit-report.md | — | — | — | ✅ 如存在 |
| CHANGELOG.md（近期） | — | — | — | ✅ |
| memory（.auto-memory/） | — | — | — | ✅ |

### 发起器 Prompt 模板

发起器在 dispatch 每个子 agent 时，使用以下结构：

```
你是 {{项目名称}} v{{X.Y.Z}} 的独立审计 Agent。

## 你的审计角色
{{从 dev-governance-part6-audit-prompts.md 读取该 Stage 的角色描述}}

## 审计上下文
{{粘贴审计共享上下文块}}

## 你需要审计的材料
{{粘贴该 Stage 专属的上下文材料（按上方分配表选取）}}

## 检测标准
{{从 dev-governance-part6-audit-prompts.md 读取该 Stage 的检测标准表}}

## 输出要求
{{从 dev-governance-part6-audit-prompts.md 读取该 Stage 的输出格式}}

## 约束
- 你是只读审计角色，不修改任何文件
- 每条发现必须附上具体证据（文件路径 + 行号 + 代码片段或 diff 引用）
- 不确定的发现标记为"存疑"，不要假装确定
- 不要虚假赞美（"代码写得很好"），只报告事实和发现
- 使用统一编号格式：[C/I/M/O]-NNN（C=Critical, I=Important, M=Minor, O=Observation）
```

### Phase 8 门禁（③ 阶段门禁）

Phase 8 完成后，检查以下门禁条件：

- [ ] 三个 Stage 的审计报告均已生成
- [ ] 整合报告已生成且包含：审计概要、发现统计、分级发现详情
- [ ] 所有 Critical 级发现都有具体修复建议
- [ ] 整合报告中每条"通过"判定都附有证据引用（非空 ✓）
- [ ] 审计报告已归档到 `docs/audits/v{X.Y.Z}/`
- [ ] `docs/audits/audit-index.md` 已更新

**门禁失败处理**：
- 报告不完整 → 重新 dispatch 缺失 Stage 的子 agent
- Critical 发现无修复建议 → 要求整合 agent 补充
- 归档未完成 → 发起器执行归档

---

*文件结束 — 子 agent 审计详细标准见 [dev-governance-part6-audit-prompts.md](dev-governance-part6-audit-prompts.md)*
