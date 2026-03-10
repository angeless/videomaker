# project_relink 开发政策与执行令 v1.0

**生效日期**：2026-03-09
**适用范围**：所有后续 `project_relink` 相关开发
**前置文件**：冻结规则、维护手册、adapter 契约、冻结审计报告

---

## 一、当前阶段认定

project_relink 当前阶段已完成从一次性修复链路到长期同步与交接闭环的建设，现进入冻结维护阶段。

已冻结的完整闭环：

1. 工程解析
2. 系统匹配
3. 候选建议
4. 人工绑定
5. 批量绑定
6. 预览 diff
7. apply 修复副本
8. 工作台分组
9. 历史/撤销/审计
10. 重分析继承
11. 路径验证
12. 交接快照与导出

---

## 二、执行顺序（不得跳序）

1. 任何后续改动，先对照：
   - `docs/project_relink_freeze_rules_and_guardrails_v1.md`
   - `docs/project_relink_maintenance_handover_v1.md`
   - `docs/project_relink_adapter_contract_v1.md`

2. 任何改动提交前，必须跑真实样本回归集：
   - `tests/fixtures/jianying_samples/`
   - `tests/test_relink_regression.py`

3. 未通过冻结规则审查或真实样本回归，不得合并。

4. 在未出现明确业务优先级前，不继续扩语义、不重构指纹、不改坏 adapter 抽象。

5. 下一阶段如要推进，只允许两类工作：
   - 维护性修复与稳定性增强
   - 在 adapter 契约不破坏前提下评估第二种 NLE 接入

---

## 三、语义冻结清单

### 1. 状态机冻结

**job.status**：`pending` / `running` / `done` / `failed` — 不得新增。

**item.status**：`stable` / `relinked` / `missing` / `unmatched` — 不得新增。

不得把 apply 重新做成"直接改原项目"的危险模式。

### 2. 字段分层冻结

系统匹配层（`uid`, `new_path`, `fingerprint_match_type`, `match_confidence`, `reason`）与人工绑定层（`manual_uid`, `manual_new_path`, `manual_decision_source`, `manual_bound_at`）**永远不混写**。

### 3. 字段优先级冻结

```
effective_uid      = manual_uid      or uid
effective_new_path = manual_new_path or new_path
```

### 4. 长期同步语义冻结

`reanalyze_project_relink()` 的职责已冻结为：

- 对同一 `project_path` 重新分析
- 自动寻找前序 job
- 自动继承前序人工绑定
- 继承后重新调用 `_best_existing_path()` 验证是否仍有效
- 用 `predecessor_job_id` 和 `inherited_from_item_id` 建立溯源关系

不得把 reanalyze 改成"简单重跑分析且丢失人工修复历史"。

### 5. 交接闭环语义冻结

handover 不是普通导出，而是冻结快照。

当前规则：
- `generate_handover_report()` 生成快照
- `handover_snapshot` 是冻结结果
- `handover_at` 表示交接时点
- 若要更新交接结果，必须显式重新生成，不自动覆盖旧快照

这条规则不能改成"随界面变化自动刷新报告"。

### 6. Adapter 抽象冻结

当前只支持 Jianying，但接入方式已经抽象到 adapter 层。

冻结要求：
- 不允许把 Jianying 逻辑重新散落写回主流程
- 不允许为了支持第二种 NLE 破坏现有 adapter contract
- 新 NLE 的接入必须以 adapter 为边界实现

---

## 四、对当前代码状态的判断

当前 project_relink 不再处于"快速试错期"，而是进入"冻结维护期"。

这意味着后续开发重点不应该再是随意加功能，而应该转为：

1. 维护性修复
2. 稳定性增强
3. 真实项目回归补齐
4. 在不破坏冻结规则的前提下，准备第二种 NLE 的适配条件

---

## 五、后续开发执行顺序

从现在开始，project_relink 后续工作按以下顺序执行，不得跳序。

### 第一优先：维护冻结文档与基线

必须持续维护：
- `project_relink_freeze_rules_and_guardrails_v1.md`
- `project_relink_maintenance_handover_v1.md`
- `project_relink_adapter_contract_v1.md`

若实现已变更但文档未更新，视为未完成交付。

### 第二优先：真实项目样本回归集持续扩充

后续如发现边界问题，应优先新增真实样本或回归 case，而不是直接改逻辑后不留验证资产。

优先补充方向：
- 更复杂的多层目录项目
- 多音频轨道项目
- 特殊字符 / 更复杂命名
- 更长的 job 链继承场景
- 路径失效后再次恢复的循环场景

### 第三优先：评估第二种 NLE

只有在前两项稳定后，才允许推进第二种 NLE。

推进前提：
- 不破坏 adapter 抽象
- 不污染 Jianying 现有逻辑
- 不改动冻结状态机语义
- 必须先出契约对照表，再开始编码

---

## 六、后续开发红线

以下红线未经明确审批，不允许突破。

**红线 1**：不得重构 project_relink 状态机语义。

**红线 2**：不得让人工绑定覆盖系统匹配字段。

**红线 3**：不得让 apply 直接覆盖原始工程文件。

**红线 4**：不得把候选建议改成自动写入。

**红线 5**：不得绕开 adapter contract 直接把 NLE 特例写死进主流程。

**红线 6**：不得在未跑真实样本回归集的情况下提交 project_relink 相关改动。

**红线 7**：不得为了支持新格式而破坏 Jianying 已有链路。

**红线 8**：不得把交接快照改成自动变化的"动态视图"。

---

## 七、开发前置检查要求

后续任何涉及 project_relink 的开发，必须先完成以下检查：

### 代码前

1. 先阅读：
   - 冻结规则文档
   - 维护交接手册
   - adapter 契约文档

2. 明确本次改动属于哪一类：
   - 维护修复
   - 稳定性增强
   - 回归补齐
   - 新 NLE 适配准备

### 提交前

必须至少执行：

```bash
pytest tests/test_project_relink.py tests/test_project_relink_api.py -q
pytest tests/test_relink_regression.py -q
pytest tests/ -q
cd apps/desktop/ui-vue && npx vite build
```

若有失败，必须先解释原因，再谈合并。

---

## 八、推荐的后续工作方式

### A. 小步迭代

每次只解决一个清晰问题，不要大面积同时改状态机、adapter、UI、apply。

### B. 先补测试再改逻辑

真实项目回归优先于"感觉上应该能工作"。

### C. 先更新文档再冻结变更

凡是影响边界语义的改动，先更新文档，再改代码。

### D. 对外扩展必须先过契约层

支持第二种 NLE 时，先过 adapter contract，再进入实现。

---

## 九、当前阶段结论

project_relink 当前已具备：

- 一次性修复能力
- 持续跟踪能力
- 人工修复继承能力
- 工程交接能力
- 维护与扩展基线

因此，当前阶段可以正式认定为：

> **project_relink 第一阶段产品化建设完成，进入冻结维护与受控扩展阶段。**

---

## 十、执行令

从本文件生效开始，后续 project_relink 开发一律遵循以下口令：

> 第一优先，先固化并遵守《project_relink 维护与交接手册》和《project_relink 版本冻结规则 + 后续开发红线清单》；
> 第二优先，持续维护真实项目样本回归集，把真实工程回归作为合并前必过条件；
> 第三优先，在不破坏 adapter 抽象和冻结规则的前提下，再评估支持第二种 NLE。

任何突破上述顺序和红线的开发，必须先审批，再实施。

---

## 附：文件清单

| 文件 | 路径 | 用途 |
|---|---|---|
| 冻结规则 | `docs/project_relink_freeze_rules_and_guardrails_v1.md` | 13 条冻结规则 + 红线 |
| 维护手册 | `docs/project_relink_maintenance_handover_v1.md` | 数据模型 + 状态机 + API + 排查指南 |
| Adapter 契约 | `docs/project_relink_adapter_contract_v1.md` | NLE 接入接口规范 + 检查清单 |
| 冻结审计报告 | `docs/project_relink_freeze_audit_report_v1.md` | 代码与规则逐条比对结果 |
| 开发政策 | `docs/project_relink_dev_policy_v1.md` | 本文件 |
| 真实样本 | `tests/fixtures/jianying_samples/*.json` | 4 个真实剪映工程样本 |
| 回归测试 | `tests/test_relink_regression.py` | 26 个真实样本回归测试 |
