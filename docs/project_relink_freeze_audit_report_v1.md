# project_relink 冻结审计报告 v1.0

**审计日期**：2026-03-09
**审计范围**：`modules/library/global_media_library.py`, `modules/library/project_relink_adapter.py`, `modules/app_api/routes/library_routes.py`, `apps/desktop/ui-vue/src/stores/library.js`, `apps/desktop/ui-vue/src/components/library/ProjectRelinkPanel.vue`
**参照文件**：`docs/project_relink_freeze_rules_and_guardrails_v1.md`, `docs/project_relink_maintenance_handover_v1.md`
**测试基线**：572 passed, 2 skipped（含 26 真实样本回归测试）

---

## 1. 审计结论

| 审计项 | 条数 | 结果 |
|---|---|---|
| 冻结规则逐条审计 | 13 | ✅ 12 match / 🔧 1 drift（已修复）|
| 维护手册字段比对 | 全量 | ✅ match |
| API 口径验证 | 25 路由 | ✅ match |
| 硬规则测试覆盖 | 10 条 | ✅ 全覆盖 |

**总结：全部冻结规则与代码一致，唯一漂移已在审计中修复。**

---

## 2. 冻结规则逐条审计

### §2.1 job.status 模型（pending/running/done/failed）

**结果：✅ MATCH**

代码中 job status 赋值点：
- `create_project_relink_job` → `running` → `done` / `failed`
- `retry_project_relink_job` → `running` → `done` / `failed`
- `reanalyze_project_relink` → `running` → `done` / `failed`

全代码搜索 `status='applied'`、`status='closed'`、`status='verified'` → 零匹配。

**测试覆盖**：`TestD4Constraints::test_no_applied_status`, `TestFreezeRuleCompliance::test_job_status_only_four_values`

---

### §2.2 item.status 模型（stable/relinked/missing/unmatched）

**结果：✅ MATCH**

所有 item status 赋值只使用这四个值。`_recalc_project_relink_job_summary` 精确统计这四种。

搜索 `manual_relinked`、`system_relinked`、`verified`、`applied` 作为 item status → 零匹配。

**测试覆盖**：`TestFreezeRuleCompliance::test_item_status_only_four_values`

---

### §2.3 数据事实源（project_relink_item 为唯一事实源）

**结果：✅ MATCH**

所有工作台分组（`get_project_relink_workbench`）、导出（`export_project_relink_map`）、apply（`apply_project_relink`）、交接（`generate_handover_report`）均从 `project_relink_item` 表读取。`result_json` 仅在 create 时写入一次，后续不作为主数据源。

---

### §2.4 系统匹配字段（bind 不覆盖 uid/fingerprint_match_type/match_confidence/reason/new_path）

**结果：🔧 DRIFT → 已修复**

**发现**：`bind_project_relink_item` 原代码在 UPDATE 语句中包含 `new_path=?`，将 `best_path` 同时写入 `manual_new_path` 和 `new_path`，导致系统原始 `new_path` 被覆盖。

**修复**：移除 bind UPDATE 中的 `new_path=?`。现在 bind 只写入 `manual_uid`, `manual_new_path`, `manual_decision_source`, `manual_bound_at`，系统 `new_path` 保持不变。

**修复行**：`global_media_library.py` 第 11870-11878 行
**修复内容**：
```diff
- SET manual_uid=?, manual_new_path=?,
-     manual_decision_source=?, manual_bound_at=?,
-     status='relinked', new_path=?
+ SET manual_uid=?, manual_new_path=?,
+     manual_decision_source=?, manual_bound_at=?,
+     status='relinked'
```

**注释补充**：`# Freeze rule §2.4: bind must NOT overwrite system new_path.`

**验证**：151 relink 测试全通过，`apply_project_relink` 不受影响（使用 `manual_new_path or new_path` 优先级）。

**测试覆盖**：`TestFreezeRuleCompliance::test_bind_preserves_system_new_path`（回归集）

---

### §2.5 人工绑定层（manual_uid/manual_new_path/manual_decision_source/manual_bound_at）

**结果：✅ MATCH**

bind 写入且仅写入这四个字段。unbind 清空且仅清空这四个字段。无第二套绑定表，无前端旁路存储。

---

### §2.6 Apply 行为（不覆盖原始工程、只处理 relinked、路径优先级 manual > system）

**结果：✅ MATCH**

- 第 11159-11161 行：`output_path` 与原始路径相同时报错
- 第 11122 行：只查询 `status = 'relinked'`
- 第 11176 行：`manual_new_path or new_path`
- 第 11180 行：on-disk 验证 `Path(new).exists()`

**测试覆盖**：`TestFreezeRuleCompliance::test_apply_never_overwrites_original`

---

### §2.7 Preview 行为（只读）

**结果：✅ MATCH**

`preview_project_relink_apply` 只执行 SELECT 和计算，唯一写操作是审计日志（`preview_apply` action，第 11477 行），符合冻结规则允许列表。

---

### §2.8 Retry vs Reanalyze（完全分离）

**结果：✅ MATCH**

- `retry_project_relink_job`：使用 `retry_of` 字段，前提 `status='failed'`
- `reanalyze_project_relink`：使用 `predecessor_job_id` 字段，前提前序 `status='done'`
- 两个字段分属不同 schema migration（D-1 vs D-4），互不干扰

---

### §2.9 继承逻辑（source_ref → old_path → asset_name+media_type）

**结果：✅ MATCH**

`reanalyze_project_relink` 第 12396-12408 行精确实现三级优先级：
```python
if sr and sr in predecessor_bindings_by_source_ref:
    ...
elif op and op in predecessor_bindings_by_old_path:
    ...
elif aname and (aname, mtype) in predecessor_bindings_by_name_type:
    ...
```

继承后调用 `_best_existing_path()` 重新校验。写入 `inherited_from_item_id` 指向实际匹配的前序 item。

**测试覆盖**：`TestD4Constraints::test_source_ref_priority`, `TestManualBindingInheritance::test_three_tier_priority`

---

### §2.10 Verify 语义（只读，不改 status）

**结果：✅ MATCH**

`verify_project_relink_state` 唯一写操作：`UPDATE project_relink_item SET verified_at = ?`。代码注释明确：`# D-4 rule #3: do NOT change status`。不修改 `status`, `uid`, `new_path`, `manual_uid` 等任何其他字段。

**测试覆盖**：`TestD4Constraints::test_verify_no_status_change`, `TestFreezeRuleCompliance::test_verify_never_changes_status`

---

### §2.11 Handover 快照冻结

**结果：✅ MATCH**

- `generate_handover_report` 写入 `handover_snapshot` JSON blob，一次性冻结
- 无后台任务或触发器自动更新 snapshot
- `export_handover_report` 读取已有 snapshot，不存在时才调用 `generate` 新建
- 重新调用 `generate_handover_report` 会覆盖旧 snapshot（需显式操作）

**测试覆盖**：`TestD4Constraints::test_snapshot_frozen`, `TestFreezeRuleCompliance::test_handover_snapshot_frozen`

---

### §2.12 候选建议只读

**结果：✅ MATCH**

`suggest_candidates_for_missing` 仅执行 SELECT，零 UPDATE/INSERT（除非在底座层做可用性检查）。注释：`# D-1 hard rule #5: read-only, never auto-write to new_path or change status.`

---

### §2.13 搜索跳转单向规则

**结果：✅ MATCH（架构层面）**

后端无任何"搜索结果自动回填 item"的方法。bind/batch-bind 需要明确的 `uid` + `item_id` 参数。搜索跳转是纯前端导航行为。

---

## 3. 审计日志覆盖率

| 动作 | action_type | 代码行 | 审计 |
|---|---|---|---|
| bind | `"bind"` | 11896 | ✅ |
| unbind | `"unbind"` | 11970 | ✅ |
| batch_bind | `"batch_bind"` | 12137 | ✅ |
| undo_bind | `"undo_bind"` | 12193 | ✅ |
| apply | `"apply"` | 11241 | ✅ |
| preview_apply | `"preview_apply"` | 11477 | ✅ |
| retry | `"retry"` | 11369 | ✅ |
| refresh_items | `"refresh_items"` | 12066 | ✅（额外） |
| export_missing | `"export_missing"` | 11536 | ✅（额外） |
| reanalyze | `"reanalyze"` | 12479 | ✅ |
| verify | `"verify"` | 12607 | ✅ |
| handover | `"handover"` | 12771 | ✅ |

§3.3 要求的 10 种动作全部有审计日志。额外还有 `refresh_items` 和 `export_missing`。

**测试覆盖**：`TestFreezeRuleCompliance::test_action_log_completeness`

---

## 4. API 口径验证

### 维护手册 §14 列出 25 个路由，全部实现：

| 分组 | 路由 | 实现 |
|---|---|---|
| 基础 | POST /project-relink | ✅ |
| 基础 | GET /project-relink/\<job_id\> | ✅ |
| 基础 | GET /project-relink/\<job_id\>/export | ✅ |
| 基础 | POST /project-relink/\<job_id\>/apply | ✅ |
| 生命周期 | POST /project-relink/\<job_id\>/retry | ✅ |
| 生命周期 | GET /project-relink/\<job_id\>/preview-apply | ✅ |
| 生命周期 | GET /project-relink/\<job_id\>/export-missing | ✅ |
| 生命周期 | GET /project-relink/\<job_id\>/suggest-candidates | ✅ |
| 生命周期 | GET /project-relink/missing-stats | ✅ |
| 绑定 | POST /project-relink/item/\<id\>/bind | ✅ |
| 绑定 | POST /project-relink/item/\<id\>/unbind | ✅ |
| 绑定 | POST /project-relink/\<job_id\>/refresh-items | ✅ |
| 工作台 | POST /project-relink/batch-bind | ✅ |
| 工作台 | GET /project-relink/item/\<id\>/history | ✅ |
| 工作台 | POST /project-relink/item/\<id\>/undo-bind | ✅ |
| 工作台 | GET /project-relink/\<job_id\>/outputs | ✅ |
| 工作台 | GET /project-relink/\<job_id\>/workbench | ✅ |
| D-4 | POST /project-relink/reanalyze | ✅ |
| D-4 | GET /project-relink/job-chain | ✅ |
| D-4 | POST /project-relink/\<job_id\>/verify | ✅ |
| D-4 | POST /project-relink/\<job_id\>/handover | ✅ |
| D-4 | GET /project-relink/\<job_id\>/export-handover | ✅ |
| 列表 | GET /project-relink/list | ✅ |
| 比较 | GET /project-relink/compare | ✅ |
| 验证 | POST /project-relink/validate | ✅ |

---

## 5. 维护手册数据模型比对

### §5.1 job 字段

| 手册列出字段 | 代码存在 | 说明 |
|---|---|---|
| job_id | ✅ | PK |
| project_path | ✅ | |
| project_type | ✅ | |
| status | ✅ | pending/running/done/failed |
| total_refs | ✅ | |
| stable_refs | ✅ | |
| changed_refs | ✅ | |
| missing_refs | ✅ | |
| unmatched_refs | ✅ | |
| result_json | ✅ | |
| retry_of | ✅ | D-1 |
| retry_count | ✅ | D-1 |
| last_error_at | ✅ | D-1 |
| predecessor_job_id | ✅ | D-4 |
| handover_at | ✅ | D-4 |
| handover_snapshot | ✅ | D-4 |
| version_info | ✅ | C-2 |
| apply_count | ✅ | C-2 |
| applied_at | ✅ | C-2 |

### §5.2 item 字段

| 手册列出字段 | 代码存在 | 分层 |
|---|---|---|
| uid | ✅ | 系统匹配 |
| new_path | ✅ | 系统匹配 |
| status | ✅ | 系统匹配 |
| fingerprint_match_type | ✅ | 系统匹配 |
| match_confidence | ✅ | 系统匹配 |
| reason | ✅ | 系统匹配 |
| manual_uid | ✅ | 人工绑定 |
| manual_new_path | ✅ | 人工绑定 |
| manual_decision_source | ✅ | 人工绑定 |
| manual_bound_at | ✅ | 人工绑定 |
| inherited_from_item_id | ✅ | D-4 长期同步 |
| verified_at | ✅ | D-4 交接 |
| applied | ✅ | C-1 |

---

## 6. 硬规则（维护手册 §16）测试覆盖表

| 硬规则 | 测试 |
|---|---|
| #1 manual 不覆盖 system | `test_bind_preserves_system_new_path` |
| #2 候选建议只读 | 代码审查（零写操作）|
| #3 stable 禁止绑定 | `TestBind::test_bind_stable_rejected` |
| #4 apply 不覆盖原始工程 | `test_apply_never_overwrites_original` |
| #5 refresh 只刷新路径 | `TestRefresh::test_refresh_basic` |
| #6 verify 不改状态 | `test_verify_never_changes_status` |
| #7 handover_snapshot 冻结 | `test_handover_snapshot_frozen` |
| #8 reanalyze 不跳过 _best_existing_path | `test_bind_and_reanalyze_inherits` |
| #9 关键动作写 action log | `test_action_log_completeness` |
| #10 不写语义系统表 | 代码搜索（零匹配 asset_tag_result/evidence/learning_candidate 写操作）|

---

## 7. 回归测试体系

| 测试文件 | 测试数 | 覆盖 |
|---|---|---|
| `test_project_relink.py` | 117 | C-1 ~ D-4 单元测试 |
| `test_project_relink_api.py` | 34 | C-1 ~ D-4 API 测试 |
| `test_relink_regression.py` | 26 | 真实剪映工程回归 |
| **合计** | **177** | |

### 真实样本回归集

| 样本 | 来源 | 视频数 | 音频数 |
|---|---|---|---|
| sample_small | 潮州婚礼 | 56 | 0 |
| sample_medium | 莫斯科 | 105 | 0 |
| sample_large | 摩尔曼斯克 | 104 | 40 |
| sample_mixed | 粉色捷琳别尔卡 | 93 | 63 |

回归测试覆盖：全链路 parse → bind → inherit → apply → verify → handover → export + 性能 + 冻结规则合规。

---

## 8. 审计结论

1. **冻结规则 13 条全部合规**（1 条 drift 已修复）
2. **维护手册全量字段与代码一致**
3. **API 口径 25 个路由全部实现**
4. **硬规则 10 条全部有测试或代码审查覆盖**
5. **真实样本回归集已建立**，覆盖 4 个真实剪映工程

当前代码库状态可以作为 **project_relink v1.0 冻结基线**。
