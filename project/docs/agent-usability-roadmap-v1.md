# Agent 易用性路线图 v1（在当前功能完成后启动）

更新时间：2026-02-25  
适用仓库：`/Users/angelwang/videoeditor`

## 1. 目标

- 保留现有人用操作习惯（桌面 UI、步骤流、能力工作台）不变。
- 在同一能力内核上，新增对 Agent 友好的 API 调用形态。
- 让 Agent 可自定义模板、参数和 AI Skill 调用策略，而不是只能走固定流程。

## 2. 约束

- 启动时机：**当前能力拆分功能全部稳定后**再投入该方向开发。
- 兼容优先：不破坏已有 `/api/capabilities/*` 行为；新增能力以可选字段/新路由方式提供。
- 可回放：Agent 任务必须可审计、可复现、可重跑。
- 说明：仓库内已存在部分 Agent 基础接口（Beta），本路线图用于定义“默认落地标准与后续增强顺序”。

## 3. 核心原则

1. 单一能力内核  
人和 Agent 都调用同一套 capability 实现，不做双实现分叉。

2. 人机双入口  
UI 继续面向人；新增 Agent API 仅作为额外入口，不替代人用入口。

3. 声明式任务  
Agent 提交“目标 + 约束 + 模板 + 技能策略”，系统生成可执行计划并返回结构化结果。

4. 幂等与可追踪  
关键写操作支持 `idempotency_key`；所有执行有 `job_id`、日志、产物清单、失败原因。

5. 安全边界  
Agent 只能在策略允许的模板、技能和资源范围内执行。

## 4. 分阶段路线图（Phase D）

当前状态（2026-02-25）：
- 已落地 D1 的最小骨架：`/api/agent/capabilities`、`/api/agent/tasks/plan`、`/api/agent/tasks/run`、`/api/agent/tasks/<job_id>`。
- 已落地 D2 的首批能力：`GET/POST/DELETE /api/agent/templates`（`system/project/agent` 分层、`system` 只读保护）。
- 已落地 D3 的最小调用链：`POST /api/agent/skills/invoke`（单 Skill 异步执行 + 重试策略 + 任务轮询复用）。
- `/api/capabilities/*` 已支持统一 `request_context` 回传。
- `POST /api/capabilities/*` 已支持基于 `idempotency_key` 的幂等回放（进程内 + 项目级落盘缓存）。
- 已支持幂等缓存管理：`GET /api/capabilities/idempotency/cache`、`POST /api/capabilities/idempotency/cache/prune`（TTL/清理）。
- 未改变现有人用 UI 与工作流行为。

### D1：Agent-Compatible API 外壳（1 周）

- 给现有 capability 路由统一增加可选上下文字段：
  - `actor_type`: `human | agent`
  - `actor_id`: 调用方标识
  - `run_mode`: `interactive | headless`
  - `idempotency_key`: 幂等键
  - `trace_id`: 链路追踪
- 输出统一补充：
  - `request_context`
  - `plan_summary`
  - `artifacts`
  - `warnings`

验收：
- 不传上述字段时，行为与当前版本一致。
- 传入 `actor_type=agent` 时，返回结构仍可被当前 UI 正常消费。

### D2：模板系统 Agent 自定义（1-2 周，进行中）

- 模板分层：
  - `system`（内置只读）
  - `project`（项目级）
  - `agent`（Agent 私有覆盖层）
- 支持变量槽位和约束：
  - 例如 `target_duration_s`、`platforms`、`quality`、`style`、`mood`
- 支持模板继承与覆盖：`base_template + overrides`

验收：
- 人用模板管理界面保持现状。
- Agent 可通过 API 创建/更新/删除 `agent` 层模板，不影响系统模板。

当前进度：
- 已实现 `GET/POST/DELETE /api/agent/templates`。
- 已实现内置 `system` 模板与只读保护。
- 已实现 `project` 与 `agent(actor_id)` 两层持久化。
- 已实现模板继承/覆盖（`base_template + overrides`）解析与 `effective_content` 输出。
- 已实现变量槽位 schema 约束（写入校验 + 解析告警）。
- 已补：模板继承策略可视化与批量变量回填工具（桌面端“能力工作台 -> Agent模板”）。
  - 模板继承链可视化：`template_chain`、`resolve_warnings` 展示。
  - 批量回填：支持对已勾选可写模板批量写入 `content/overrides` 变量。
  - 编辑器：支持单模板新建/编辑/删除与 JSON 字段校验。

### D3：AI Skill 调用编排（1-2 周，进行中）

- 建立 Skill 调用声明：
  - `skill_id`
  - `input`
  - `timeout_seconds`
  - `retry_policy`
  - `budget_limit`
- 支持串并行策略：
  - `sequential`
  - `parallel`
  - `conditional`
- 每次 Skill 调用回写结构化执行记录。

验收：
- Agent 可以在一次任务中声明“模板选择 + Skill 调用 + capability 执行”。
- 失败可定位到具体 Skill 调用节点。

当前进度：
- 已实现 `POST /api/agent/skills/invoke` 最小版（单 Skill 调用）。
- 已实现 `timeout_seconds` 与 `retry_policy(max_retries/backoff_ms/retry_on_http)`。
- 已输出结构化执行结果并复用 `/api/agent/tasks/<job_id>` 轮询。
- 已实现任务重放：`POST /api/agent/tasks/<job_id>/replay`（支持覆盖 payload/context，默认清理 `idempotency_key`，支持历史记录回放）。
- 已实现 `POST /api/agent/tasks/run` 的 `mode=skill_sequence` 串行编排（支持 `continue_on_error`）。
- 已实现 `POST /api/agent/tasks/run` 的 `mode=skill_sequence` 并行编排（`strategy=parallel`, `max_parallel`）。
- 已实现 `POST /api/agent/tasks/run` 的 `mode=skill_sequence` 条件编排（`strategy=conditional`）。
- 已实现 `budget_limit` 基础约束（`max_steps`, `max_failures`, `max_duration_seconds`）。
- 已实现预算与治理策略联动（`data/agent_governance.json`，按 actor/能力动态收紧额度与禁用清单）。
- 已实现运行统计与动态额度自动回写（`data/agent_governance_usage.json`）。
- 已实现基础成本核算（步骤级 token 统计 + 时长估算成本）并纳入动态额度建议。
- 已实现成本模型配置化（`data/agent_cost_model.json`，按 `default -> provider -> model` 精细计费）。
- 已实现自动调优策略（基于 `recent_runs` 窗口按失败率/成本/时长趋势动态收放建议额度）。
- 已实现 `GET /api/agent/tasks/<job_id>` 链路聚合视图（`chain_view`，跨能力节点摘要）。
- 已实现 `GET /api/agent/tasks/history`（按 actor/status/mode/capability/skill/replay_supported/time 窗口过滤 + 分页）。
- 已实现 `POST /api/agent/tasks/<job_id>/export`（单任务审计快照导出，支持内存/历史回退）。
- 已实现历史链路回放增强：history 记录 `step_summaries`，详情回退可重建 `chain_view.nodes/edges`（含条件依赖边）。
- 已实现观测聚合与导出：`GET /api/agent/observability`、`POST /api/agent/observability/export`（支持与 history 一致的筛选参数，输出成功率/重试率/模板命中率/失败 TopN）。

### D4：治理与观测（1 周）

- 策略控制：
  - 能力白名单
  - 模板读写权限
  - 最大并发/时长/成本限制
- 可观测：
  - 任务成功率、平均时长、重试率、模板命中率、Skill 失败 TopN

验收：
- 可以按 `actor_id` 回溯任务链路和产物。
- 超策略调用被拒绝并返回明确错误码。

## 5. API 状态（已实现 + Roadmap）

已实现：
- `GET /api/agent/capabilities`：返回 Agent 可用能力与参数 schema。
- `POST /api/agent/tasks/plan`：输入任务意图，输出执行计划（不执行）。
- `POST /api/agent/tasks/run`：按计划异步执行，返回 `job_id`（含 `mode=skill_sequence` 串行编排）。
  当前支持 `strategy=sequential|parallel|conditional`。
- `GET /api/agent/tasks/<job_id>`：查询任务状态、日志、产物。
- `GET /api/agent/tasks/history`：按过滤条件分页查询历史任务。
- `POST /api/agent/tasks/<job_id>/export`：导出单任务审计快照（json/csv）。
- `GET/POST/DELETE /api/agent/templates`：Agent 模板管理。
- `POST /api/agent/skills/invoke`：显式触发单 Skill（受策略限制）。

Roadmap（未实现）：
- 暂无（v1 范围内已完成）。

已补齐：
- 前端看板可视化已落地到“能力工作台 -> Agent观测”：
  - 条件筛选：`actor_id`、窗口大小 `limit`、`top_n`
  - 指标看板：成功率/错误率/重试率/模板命中率/平均时长/平均成本
  - Top 视图：模板命中 TopN、失败节点 TopN、模式分布
  - 任务明细：最近任务列表（状态、模式、能力/Skill、重试、tokens、成本、模板命中）
  - 一键导出：JSON/CSV（调用 `/api/agent/observability/export`）

## 6. 与当前能力的映射要求

- `topic_library`：Agent 可按标签策略检索并生成候选主题集合。
- `topic_copy`：Agent 可基于模板参数自动改写文案骨架。
- `text_rough_cut`：Agent 可用句子索引策略自动删除停顿和冗余句。
- `short_clip`：Agent 可按平台目标时长自动分配片段预算。
- `refinement`：Agent 可按编辑器能力选择内部/外部执行路径。
- `social_export`：Agent 可批量套模板导出并做规格校验闭环。
- `audio_voice`：Agent 可按情绪和人声策略自动配音/配乐。

## 7. 完成定义（DoD）

- 人用流程无回归（UI 手动操作路径保持稳定）。
- Agent API 至少覆盖 7 个 capability 的“plan + run + history”。
- 模板和 Skill 调用具备权限控制、审计日志、可重跑能力。
- 文档提供最小可用示例（curl + JSON 样例 + 错误码说明）。
