# project_relink 版本冻结规则 + 后续开发红线清单

## 0. 文档定位

本文档是 `project_relink` 模块的**冻结规则文档**，不是功能说明书，也不是需求草案。

它的作用只有一个：

> 明确 `project_relink` 当前哪些规则已经定型，哪些行为不能被后续开发随意改写，防止模块在继续迭代时失去一致性、可追溯性和可交接性。

适用范围：
- 后续所有 `project_relink` 相关开发
- 包括后端、前端、任务链、apply、handover、历史追踪、人工绑定、工作台相关改动
- 包括支持第二种 NLE 前的架构延展

执行原则：
- 先遵守，后扩展
- 先补文档，再改规则
- 先保证兼容，再增加能力

---

## 1. 当前版本冻结结论

截至当前版本，`project_relink` 已经不是“实验功能”，而是一个已形成闭环的工程恢复子系统。

已经冻结的核心闭环包括：

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

因此后续开发的默认前提是：

> 不是重做 `project_relink`，而是在冻结基线之上做增量扩展。

---

## 2. 冻结对象

以下内容全部视为**冻结对象**，后续不得随意改变其语义：

### 2.1 job 状态模型冻结

`project_relink_job.status` 只允许以下四个值：

- `pending`
- `running`
- `done`
- `failed`

红线：
- 不得再引入 `applied` 作为 job 状态
- 不得引入新的临时状态去替代现有四态
- apply 的执行结果属于 job 的附加属性，不属于 job 状态本身

原因：
- job 状态描述的是任务执行生命周期
- apply、handover、verify 是 job 的后续动作，不是独立状态分支
- 混入额外状态会破坏时间线、重试逻辑和版本链判断

---

### 2.2 item 状态模型冻结

`project_relink_item.status` 只允许以下四个值：

- `stable`
- `relinked`
- `missing`
- `unmatched`

红线：
- 不得增加 `manual_relinked`、`system_relinked`、`verified`、`applied` 这类新状态
- 不得让前端自行推导出新的“伪状态”替代后端状态
- 不得把验证结果、绑定方式、应用结果混入 status 字段

原因：
- `status` 表示“当前引用是否能被恢复”这一件事
- 绑定来源、验证结果、是否交接，是额外维度，不应污染主状态机

---

### 2.3 数据事实源冻结

`project_relink_item` 是 relink 结果的唯一事实源。

红线：
- 不得把 `result_json` 当成主数据源
- 不得让前端基于缓存对象长期持有“真实状态”
- 不得在 UI 层拼装一个与 `project_relink_item` 平行的状态模型

正确原则：
- `project_relink_item` 是 source of truth
- `project_relink_job.result_json` 只能视为快照/备用结果
- 所有工作台分组、导出、apply、交接都必须回到 item 表读取真实数据

---

### 2.4 系统匹配字段冻结

以下字段属于**系统匹配层**，后续不得被人工绑定逻辑覆盖：

- `uid`
- `fingerprint_match_type`
- `match_confidence`
- `reason`
- `new_path`

补充说明：
- `new_path` 可以被“优先级使用”覆盖，但不能被人工绑定写坏系统来源语义
- 人工绑定必须写入 `manual_*` 字段，不得回写系统字段来伪装系统匹配成功

红线：
- 不得在 bind 时把 `manual_uid` 写回 `uid`
- 不得在 bind 时重写 `fingerprint_match_type`
- 不得在 bind 时把 `reason` 改成“人工绑定”覆盖系统 reason

原因：
- 系统匹配与人工决策必须分层
- 否则历史不可解释，撤销不可恢复，继承不可追溯

---

### 2.5 人工绑定层冻结

人工绑定层只允许通过以下字段表达：

- `manual_uid`
- `manual_new_path`
- `manual_decision_source`
- `manual_bound_at`

红线：
- 不得新起第二套人工绑定结果表
- 不得把人工绑定写进 action log 再由日志反推状态
- 不得把人工绑定结果只存在前端，不落库

原因：
- 手工修复劳动必须可继承、可导出、可交接
- 只存在前端或日志中的绑定无法进入长期同步闭环

---

### 2.6 Apply 行为冻结

`apply_project_relink()` 的固定规则如下：

1. 只生成修复副本
2. 永远不覆盖原始工程文件
3. 只处理 `status='relinked'` 的项
4. 路径优先级：`manual_new_path > new_path`
5. 输出文件名必须具备可追踪规则

红线：
- 不得默认覆盖原始工程
- 不得让 missing/unmatched/stable 被当成 apply 目标
- 不得绕开 preview-apply 直接偷偷写回

原因：
- apply 是修复输出，不是原项目破坏性更新
- 一旦允许覆盖原始工程，交接和审计价值会大幅下降

---

### 2.7 Preview 行为冻结

`preview_project_relink_apply()` 是只读预览，不写状态，不改文件。

红线：
- 不得在 preview 时做隐式 apply
- 不得在 preview 时顺手刷新绑定、变更 item、补写路径
- 不得在 preview 时写入影响后续判断的业务字段

允许：
- 写审计日志
- 计算 will_apply / will_skip
- 输出 warnings

---

### 2.8 Retry 与 Reanalyze 语义冻结

`retry` 与 `reanalyze` 是两个完全不同的动作。

#### retry
用于：失败任务重跑
字段：`retry_of`
前提：原 job 必须是 `failed`

#### reanalyze
用于：同一工程的长期同步再分析
字段：`predecessor_job_id`
前提：前序 job 通常为 `done`

红线：
- 不得把 retry 当 reanalyze 用
- 不得把 predecessor 链和 retry 链混在一起
- 不得让“重新分析”覆盖旧 job 本身

原因：
- 两条链分别代表“失败恢复”和“正常迭代”
- 混用后会导致时间线、继承、交接全部失真

---

### 2.9 继承逻辑冻结

重分析时允许继承前序 job 的人工绑定，但必须遵守以下优先级：

1. `source_ref`
2. `old_path`
3. `asset_name + media_type`

红线：
- 不得只按文件名粗暴继承
- 不得跳过 `media_type` 校验
- 不得把继承结果直接写成系统匹配结果

继承结果要求：
- 写入 `manual_uid`
- 写入 `inherited_from_item_id`
- 重新调用 `_best_existing_path()` 校验当前路径是否仍可用

原因：
- 继承的本质不是复制旧结果，而是复用人的选择再做当前验证

---

### 2.10 Verify 语义冻结

`verify_project_relink_state()` 是只读检查动作。

它负责：
- 检查当前有效路径是否仍存在
- 更新 `verified_at`
- 生成 stale 报告

它不负责：
- 修改 item 状态
- 重新匹配 uid
- 自动修复路径
- 触发 reanalyze

红线：
- 不得把 verify 做成隐式修复
- 不得让 verify 修改主状态机

原因：
- 状态与验证是两个维度
- 否则“路径失效”与“状态变化”会相互污染，无法判断问题来源

---

### 2.11 Handover 快照冻结

`handover_snapshot` 是交接冻结快照，不是动态实时视图。

红线：
- 不得在 job 数据变化后自动改写已有 handover_snapshot
- 不得把 handover_snapshot 当实时计算面板
- 不得省略显式生成交接报告这一步

正确原则：
- handover 是一次明确动作
- snapshot 一经生成，表示当时的冻结交付状态
- 之后若要更新，必须再次显式生成新的 handover

---

### 2.12 候选建议只读规则冻结

`suggest_candidates_for_missing()` 及其前端展示始终只读。

红线：
- 候选建议不允许直接写入 item
- 候选建议不允许偷偷把推荐路径塞进 `manual_new_path`
- 所有真正写入动作必须通过 bind/batch-bind API

原因：
- 建议与决策必须分离
- 否则会破坏审计、撤销、人工确认闭环

---

### 2.13 搜索跳转单向规则冻结

从 `project_relink` 跳转到素材库搜索，只允许单向触发。

允许：
- 把 `asset_name` 带到素材库搜索框
- 用户再手动选择绑定对象

红线：
- 不得搜索后自动回填绑定
- 不得把搜索结果默认视为人工确认
- 不得跨页面静默改写 relink item

原因：
- 搜索只是辅助定位，不是确认动作
- 确认动作必须显式发生

---

## 3. 前后端协作红线

### 3.1 前端不得创造后端没有定义的新状态

前端只能展示：
- 后端提供的 `status`
- 后端提供的 `binding_mode`
- 后端提供的 `effective_uid / effective_new_path`
- 后端提供的 `verified_at / handover_at`

红线：
- 不得在前端构造“半修复”“可疑成功”“待确认继承”等额外业务状态

---

### 3.2 工作台分组规则必须以后端字段为准

工作台可以分组显示，但分组只是视图，不是新状态。

例如：
- 待处理 = missing + unmatched
- 已解决 = stable + relinked
- 手工修复 = `manual_uid is not null`
- 继承绑定 = `inherited_from_item_id is not null`

红线：
- 前端分组逻辑不能反向写回后端状态
- 不得因 UI 需求新增数据库状态枚举

---

### 3.3 所有关键动作都必须可审计

以下动作必须写审计日志：
- bind
- unbind
- batch-bind
- undo-bind
- preview-apply
- apply
- retry
- reanalyze
- verify
- handover

红线：
- 不得新增会改变工程结果的动作而不记日志
- 不得只在前端 toast，不在后端留痕

---

## 4. 数据兼容红线

### 4.1 不允许破坏旧 job 可读性

新增字段必须通过安全迁移方式追加，不能要求旧数据重建才能读取。

红线：
- 不得强制重建 `project_relink_job` / `project_relink_item`
- 不得让老 job 因字段缺失而无法展示

---

### 4.2 不允许让导出结构频繁漂移

以下导出结构需要保持稳定：
- relink map JSON
- export missing JSON / CSV
- handover JSON / Markdown

红线：
- 不得随意改字段名
- 不得今天导出一套，明天导出另一套而不做版本标识

建议：
- 任何导出结构变更都应加版本号或兼容字段

---

## 5. 架构扩展红线

### 5.1 支持第二种 NLE 前，不得破坏 adapter 抽象

当前已有 adapter 抽象层，且 Jianying 已接入。

红线：
- 不得为了 Jianying 的局部便利，直接把工程解析/写回逻辑散落回 `global_media_library.py`
- 不得在新增 NLE 之前先把 adapter 体系绕掉

正确方向：
- 第二种 NLE 必须基于 adapter contract 接入
- 先满足 contract，再谈格式差异

---

### 5.2 不允许为新需求再起平行模型

后续如需：
- 更复杂的交接
- 更多验证维度
- 更多输出类型
- 更多工作台视图

都必须基于现有：
- `project_relink_job`
- `project_relink_item`
- `path_change_log`
- action log
- output record

红线：
- 不得新起第二套“project_relink_v2_result”之类的表
- 不得让一次性功能走旁路数据结构

---

## 6. 推荐后续开发顺序

后续开发优先级固定如下：

### 第一优先
《project_relink 维护与交接手册》、
《project_relink 版本冻结规则 + 后续开发红线清单》

目标：
- 把现有模块的边界、规则、版本基线固化下来
- 确保以后不是“谁接手谁重解释”

### 第二优先
做真实项目样本回归集

目标：
- 用真实剪映工程样本形成长期回归集
- 覆盖 stable / relinked / missing / unmatched / manual binding / inherited binding / apply / handover 等关键场景
- 让后续改动都能对真实工程回归，而不是只靠合成测试

### 第三优先
再考虑支持第二种 NLE

目标：
- 在不破坏 adapter contract 的前提下扩展新格式
- 先有样本、先有 contract、再做接入

---

## 7. 给后续开发的执行要求

后续任何涉及 `project_relink` 的开发，默认执行以下要求：

1. 先阅读维护手册
2. 再阅读本冻结规则
3. 确认本次改动是否触及红线
4. 若触及红线，先更新文档并说明原因
5. 再进行代码改动
6. 改动后补充对应测试与回归样本

凡涉及以下内容，必须先确认后再改：
- 状态机
- 字段优先级
- 继承规则
- apply 行为
- verify 行为
- handover 快照语义
- adapter contract
- 导出结构

---

## 8. 一句话版本基线

> `project_relink` 当前已完成从“工程解析”到“长期同步与交接”的完整闭环；后续开发只能在既有 job/item/manual/apply/handover 体系上增量扩展，不允许另起平行模型，不允许覆盖系统匹配层，不允许破坏状态机和交接快照语义。

---

## 9. 后续开发总口令

请按以下优先级继续推进：

> 第一优先：先固化《project_relink 维护与交接手册》与《project_relink 版本冻结规则 + 后续开发红线清单》；
> 第二优先：建立真实项目样本回归集，把当前闭环变成长期可回归能力；
> 第三优先：在不破坏 adapter 抽象和冻结规则的前提下，再考虑支持第二种 NLE。

