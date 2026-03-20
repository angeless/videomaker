# project_relink 模块维护与交接手册 v1.0

## 1. 文档定位

本文档用于指导开发、测试、后续接手同学长期维护 `project_relink` 模块。  
目标不是重新讲一遍需求，而是把当前已经落地的行为、边界、优先级、状态流转、数据口径固定下来，避免后续继续开发时出现“看起来能跑，但把旧规则改坏了”的情况。

本文覆盖范围：

- Phase A/B：素材库底座能力
- C-1 ~ C-2：工程 relink 基础链路
- D-1 ~ D-2：任务化、人工绑定、长期同步、交接闭环

本文不覆盖：

- 语义系统实现细节
- 第二种 NLE 格式
- 指纹算法研究性改造
- 与外部工作流系统的自动集成细节

---

## 2. 当前模块目标

`project_relink` 的核心目标已经不是“分析一次工程”，而是：

1. 读取 Jianying 工程中的素材引用
2. 将引用映射到素材库中的 `assets.uid`
3. 基于素材库路径能力输出 relink map
4. 支持人工绑定修复 missing / unmatched 项
5. 支持 apply 到工程副本
6. 支持 reanalyze 继承前序人工绑定
7. 支持 verify / handover / export
8. 形成长期同步与工作交接闭环

一句话概括：

**让工程修复从一次性操作，升级为可追溯、可继承、可交接的长期工作流。**

---

## 3. 模块边界

### 3.1 做什么

`project_relink` 负责：

- 解析 Jianying 工程素材引用
- 构建 relink job 与 item
- 生成修复建议
- 执行人工绑定
- 批量绑定
- 预览 apply 差异
- 输出修复副本
- 继承历史绑定
- 验证当前路径有效性
- 生成交接报告

### 3.2 不做什么

`project_relink` 不负责：

- 重新分析语义标签
- 修改 `asset_tag_result`
- 修改 `evidence`
- 修改 `learning_candidate`
- 重新设计素材指纹算法
- 支持多种 NLE 格式并存的复杂兼容逻辑
- 覆盖原始工程文件
- 自动决定“删除哪个重复素材”

---

## 4. 与其他模块的关系

### 4.1 与素材库底座的关系

`project_relink` 依赖但不重构以下底座能力：

- `_best_existing_path(...)`
- `relink_report(...)`
- `path_change_log`
- `known_media_roots`
- `duplicate_group`
- `asset_locations`
- `assets.primary_path`
- `assets.uid`

### 4.2 与语义系统的关系

唯一耦合点是：**都共享 `assets.uid`**。

严格要求：

- `project_relink` 不写 `asset_tag_result`
- `project_relink` 不写 `evidence`
- `project_relink` 不写 `learning_candidate`
- `project_relink` 不触发语义重分析

这是一条硬边界。

---

## 5. 核心数据模型

### 5.1 job 层：`project_relink_job`

用于描述一次工程级分析任务。

关键字段：

- `job_id`
- `project_path`
- `project_type`
- `status`
- `total_refs`
- `stable_refs`
- `changed_refs`
- `missing_refs`
- `unmatched_refs`
- `result_json`
- `retry_of`
- `retry_count`
- `last_error_at`
- `predecessor_job_id`
- `handover_at`
- `handover_snapshot`
- `version_info`
- `apply_count`
- `applied_at`

#### job.status 固定枚举

只有这四个值：

- `pending`
- `running`
- `done`
- `failed`

禁止新增 `applied`、`closed`、`verified` 等平行状态。

#### 为什么没有 `applied`

因为 apply 是 job 的一个动作结果，不是 job 生命周期状态。  
是否 apply 通过下列字段判断：

- `apply_count`
- `applied_at`
- 输出记录表 / 输出列表
- action log

### 5.2 item 层：`project_relink_item`

用于描述工程中单条素材引用的修复状态。

关键字段分成三类：

#### A. 系统匹配字段

这些字段是系统扫描结论，**人工绑定不能覆盖**：

- `uid`
- `new_path`
- `status`
- `fingerprint_match_type`
- `match_confidence`
- `reason`

#### B. 人工绑定字段

这些字段是 D-2 起新增的用户决策层：

- `manual_uid`
- `manual_new_path`
- `manual_decision_source`
- `manual_bound_at`

#### C. 长期同步 / 交接字段

- `inherited_from_item_id`
- `verified_at`
- `applied`

---

## 6. item 状态机

### 6.1 初始扫描状态机

由 `build_project_relink_map()` 产生：

- `stable`
- `relinked`
- `missing`
- `unmatched`

判定规则：

#### stable
工程里的 `old_path` 当前仍然存在。

#### relinked
系统匹配到了素材库中的 `uid`，并且 `_best_existing_path()` 找到了新的有效路径。

#### missing
匹配到了 `uid`，但当前没有可用路径。

#### unmatched
完全无法匹配到素材库中的任何素材。

### 6.2 D-2 完整状态机

#### 人工绑定 `bind_project_relink_item`

允许：

- `missing -> relinked`
- `missing -> missing`
- `unmatched -> relinked`
- `unmatched -> missing`

禁止：

- `stable -> bind()`，必须报错
- 直接覆盖系统匹配字段

#### 解绑 `unbind_project_relink_item`

只对 `manual_uid` 非空项有效。

解绑后：

- 清空所有 `manual_*` 字段
- 基于原始系统匹配重算状态
- 若原始 `uid` 可找到路径，回到 `relinked`
- 若原始 `uid` 不可找到路径，回到 `missing`
- 若原始 `uid` 本来为空，回到 `unmatched`

#### 刷新 `refresh_project_relink_items`

只刷新路径可用性，不重解析工程。

规则：

- `stable` 不参与刷新重算
- 对非 `stable` 项：
  - `effective_uid = manual_uid or uid`
  - 找到路径则 `relinked`
  - 找不到路径则 `missing`
  - 若没有任何 uid，保留 `unmatched`

### 6.3 D-4 补充状态机：长期同步

#### reanalyze

同一工程重新分析时：

- 生成一个新 job
- `predecessor_job_id` 指向前序 job
- 自动继承前序人工绑定
- 继承后重新用 `_best_existing_path(manual_uid)` 校验
- 有路径则 `relinked`
- 无路径则 `missing`

#### verify

`verify_project_relink_state()` 只检查路径，不改 item.status。

- 会设置 `verified_at`
- 会输出 stale 列表
- 不会把 `relinked` 自动改为 `missing`
- 状态与验证是两条维度

#### handover

`generate_handover_report()` 只聚合快照并冻结，不自动重新推导 job 状态。

---

## 7. 字段优先级规则

这是最容易被改坏的地方。

### 7.1 effective_uid 规则

```text
effective_uid = manual_uid or uid
```

### 7.2 effective_new_path 规则

```text
effective_new_path = manual_new_path or new_path
```

解释：

- apply 与 preview 都必须优先使用人工绑定路径
- 这是 D-2 的核心规则之一
- 禁止反过来写

### 7.3 binding_mode 口径

后端返回给前端时，必须明确区分：

- `manual`
- `system`
- `none`

前端不能靠猜字段是否为空去拼业务语义。

---

## 8. 继承规则（D-4）

reanalyze 时，人工绑定继承优先级固定为三级：

1. `source_ref`
2. `old_path`
3. `asset_name + media_type`

### 为什么要这样

因为同一工程重复分析时：

- `source_ref` 最稳定
- `old_path` 次稳定
- 文件名最不稳定，必须最后兜底

### 继承后不允许做的事

- 不覆盖系统匹配字段
- 不直接判定为 stable
- 不跳过 `_best_existing_path` 校验
- 不写入语义系统相关表

---

## 9. apply 规则

### 9.1 apply 输入来源

`apply_project_relink(job_id, output_path=None)` 使用：

- 仅 `status='relinked'` 的 item
- 每个 item 的路径优先级：
  - `manual_new_path`
  - `new_path`

### 9.2 apply 安全规则

硬规则：

1. **绝不覆盖原始工程文件**
2. 输出文件默认按命名规则生成副本
3. `output_path` 不允许与原文件相同
4. 只替换明确可修复的 relinked 项
5. `stable / missing / unmatched` 不允许被 apply 修改
6. preview 与 apply 使用同一套 effective path 规则

### 9.3 apply 是幂等动作

D-3 / C-2 后要求：

- 已 apply 的 job 再次 apply 时要有保护
- 默认不重复覆盖同一输出
- 需要 `force` 才允许重新生成
- 要有 `apply_count` 与 `applied_at`

---

## 10. preview 规则

`preview_project_relink_apply(job_id)` 是只读预览。

必须做到：

- 不改 DB 中 item 状态
- 不改原工程
- 检查 `effective_new_path` 是否仍存在
- 返回：
  - `will_apply`
  - `will_skip`
  - `already_applied`
  - `warnings`
  - `output_path_preview`

preview 不是 apply 的简化版，而是 apply 的前置安全门。

---

## 11. action log 规则

所有关键修复动作必须写审计日志。

至少包括：

- bind
- batch_bind
- unbind
- undo_bind
- apply
- reanalyze
- verify
- handover

### 11.1 为什么重要

因为 `project_relink` 已经不是单次工具，而是多人协作链路。  
没有 action log，就没有交接，也没有回溯。

### 11.2 action log 的作用

用于：

- UI 历史抽屉
- 交接报告时间线
- 回滚判断
- 问题追查
- 团队协作记录

---

## 12. 交接闭环规则（handover）

### 12.1 handover 何时可做

推荐在以下条件下执行：

- job.status = `done`
- 已完成人工绑定或确认无需绑定
- 已完成 verify
- 已有明确输出副本或确认无需 apply

### 12.2 推荐交接版本规则

推荐把满足以下条件的 job 视为“可交接版本”：

1. `status='done'`
2. `handover_at` 非空
3. `handover_snapshot.closure_status='complete'`

若 closure 不是 complete，也可以交接，但必须明确写清剩余风险。

### 12.3 handover_snapshot 是冻结快照

原则：

- 一旦生成，不自动更新
- 后续环境变化不会反写旧 snapshot
- 想拿新快照，必须显式再次调用 handover

这保证了交接文档的“当时真实”。

---

## 13. 推荐交接文档内容

Markdown 导出的交接报告应稳定包含以下章节：

1. 工程信息
2. 解决汇总
3. 人工绑定明细
4. 输出副本
5. 验证结果
6. 操作时间线
7. 前序任务链
8. closure_status

这是给人看的版本。  
JSON 是给系统或后续脚本消费的版本。

---

## 14. API 口径总表

### 14.1 基础分析与导出

- `POST /api/library/project-relink`
- `GET /api/library/project-relink/<job_id>`
- `GET /api/library/project-relink/<job_id>/export`
- `POST /api/library/project-relink/<job_id>/apply`

### 14.2 生命周期与问题处理

- `POST /api/library/project-relink/<job_id>/retry`
- `GET /api/library/project-relink/<job_id>/preview-apply`
- `GET /api/library/project-relink/<job_id>/export-missing`
- `GET /api/library/project-relink/<job_id>/suggest-candidates`
- `GET /api/library/project-relink/missing-stats`

### 14.3 人工绑定

- `POST /api/library/project-relink/item/<item_id>/bind`
- `POST /api/library/project-relink/item/<item_id>/unbind`
- `POST /api/library/project-relink/<job_id>/refresh-items`

### 14.4 工作台与历史

- `POST /api/library/project-relink/batch-bind`
- `GET /api/library/project-relink/item/<id>/history`
- `POST /api/library/project-relink/item/<id>/undo-bind`
- `GET /api/library/project-relink/<job_id>/outputs`
- `GET /api/library/project-relink/<job_id>/workbench`

### 14.5 长期同步与交接

- `POST /api/library/project-relink/reanalyze`
- `GET /api/library/project-relink/job-chain`
- `POST /api/library/project-relink/<job_id>/verify`
- `POST /api/library/project-relink/<job_id>/handover`
- `GET /api/library/project-relink/<job_id>/export-handover`

---

## 15. 前端工作台原则

`ProjectRelinkPanel.vue` 目前已经不是单纯结果展示页，而是工作台。

### 15.1 前端不能自己发明状态

所有分组、badge、工作台 tab，都必须来自后端真实字段，不允许前端重新推导一套并与后端脱节。

### 15.2 前端允许做的事情

- 展示 effective 字段
- 展示 binding_mode
- 展示继承标记
- 展示验证结果
- 展示 handover 结果
- 发起 bind/unbind/batch-bind/apply/verify/handover/reanalyze

### 15.3 前端不允许做的事情

- 修改系统匹配字段
- 自行伪造 relinked / missing 状态
- 在本地缓存中偷偷改 job 结果但不回源
- 跳过 preview 直接 apply
- 自动把素材库搜索结果写回 item

---

## 16. 禁止改坏的硬规则

### 规则 1
**manual 字段永远不能覆盖 system 字段。**

### 规则 2
**候选建议永远只读。真正写入只能走 bind / batch-bind。**

### 规则 3
**stable 项禁止绑定。**

### 规则 4
**apply 绝不覆盖原始工程文件。**

### 规则 5
**refresh-items 只刷新路径，不重解析工程。**

### 规则 6
**verify 是只读检查，不改状态。**

### 规则 7
**handover_snapshot 是冻结快照，不自动更新。**

### 规则 8
**reanalyze 继承人工绑定时，不能跳过 `_best_existing_path` 校验。**

### 规则 9
**所有关键动作必须写 action log。**

### 规则 10
**project_relink 不得写语义系统表。**

---

## 17. 推荐排查顺序（线上/验收出问题时）

如果用户反馈“工程修复不对”，按以下顺序排查：

### 1）先看 job
- job.status
- predecessor_job_id
- retry_of
- apply_count
- handover_at

### 2）再看 item
- status
- uid
- manual_uid
- new_path
- manual_new_path
- binding_mode
- inherited_from_item_id
- verified_at

### 3）再看 action log
- 有没有 bind
- 有没有 unbind
- 有没有 apply
- 有没有 reanalyze
- 有没有 verify
- 有没有 handover

### 4）再看底座路径能力
- `_best_existing_path` 是否找到路径
- `asset_locations` 是否最新
- `path_change_log` 是否完整
- root 扫描是否做过

### 5）最后看工程文件本身
- Jianying JSON 是否结构异常
- materials path 是否缺失
- source_ref 是否变化
- 输出副本是否正确写入

---

## 18. 未来扩展建议

### 18.1 可做
- 第二种 NLE adapter
- 更丰富的 handover report 模板
- 项目级批量 verify
- 自动提醒 stale output
- 团队协作权限
- 交接版本 pin / release

### 18.2 暂不建议立刻做
- 重构 item 状态枚举
- 把 verify 混进 status
- 让前端本地持久化一套平行状态
- 让 apply 直接改原工程
- 让素材库搜索直接自动绑定
- 在没有真实样本回归集前重写 adapter contract

---

## 19. 推荐的下一个维护阶段

建议下一阶段不是继续“加更多修复动作”，而是做稳态运维能力：

1. 建真实工程样本回归集  
2. 做大工程性能压测  
3. 做 action log / handover report 的真实团队试运行  
4. 做 job 归档与保留策略  
5. 明确“推荐交接版本”的 UI 标识  

---

## 20. 结语

到 D-4 为止，`project_relink` 已经不是一个单点功能，而是一条完整的工程修复与交接链路。

后续维护的核心原则只有一句：

**永远优先保证“可追溯、可继承、可交接”，再考虑“更聪明、更自动化”。**
