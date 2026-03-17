# VideoEditor v2.0 Roadmap

> 基于 2026-03-10 真实用户视角全面审视，按短期/中期/结构性三层分阶段推进。
> 原则：聚焦问题本身，不发散，不擅自重构，不破坏已通过验证的链路。

---

## 审视总结

| 维度 | 评分 | 核心发现 |
|------|------|---------|
| 面向人群清晰度 | 5/10 | UI 说"给创作者"，实际是"给技术人员"——定位模糊 |
| 功能设计 | 6/10 | 核心管线完整，但广度 > 深度，多数平台发布是空壳 |
| 架构质量 | 7.5/10 | Blueprint 工厂 + 优雅退化 + 幂等/审计——工程质量好，但 server.py 太胖 |
| 安全性 | 8/10 | 本地应用里罕见的安全意识：CSRF、审计、密钥脱敏、Keychain |
| 交互易用性 | 4.5/10 | 无时间线、无实时反馈、功能发现成本高、可访问性缺失 |
| 解决实际问题 | 5.5/10 | 素材→渲染自动化真实可用；多平台发布（核心卖点）名不副实 |

---

## 短期任务（S1-S4）

### S1: 退化行为显式通知

**问题**：渲染/磨皮/字幕模块在缺少可选依赖时静默退化，用户拿到降级成品却不知原因。

**目标**：
- 退化发生时写 Toast 通知用户
- 退化事件写入审计日志
- 不改变退化逻辑本身（退化是正确的设计）

**影响范围**：
- `auto_render.py` — libass 检测 + 字幕退化
- `beauty.py` — mediapipe 检测 + 磨皮退化
- `pipeline.py` — 阶段退化汇总
- 前端 Toast 组件

---

### S2: recovery_hint 前端消费

**问题**：P1 后端已返回 `recovery_hint`（含 `rerun_scope`, `error_classes`），但前端未消费这些信息，用户看到"失败"后无下一步指引。

**目标**：
- publish `/run` 失败时 UI 展示结构化错误摘要
- 根据 `rerun_scope` 展示对应的操作按钮（重试 / 修改配置后重试）
- 按 `error_classes` 展示中文错误分类

**影响范围**：
- Vue Capability 面板（publish 相关组件）
- Store（capabilities.js）
- 不改后端

---

### S3: Capability 导航加功能状态 badge

**问题**：16 个左侧导航项不区分"可用/开发中/规划中"，用户靠自己试探。

**目标**：
- Capability registry 增加 `maturity` 字段（`stable` / `beta` / `planned`）
- 前端导航项根据 maturity 显示 badge
- planned 项点击后显示"开发中"提示而非空白面板

**影响范围**：
- `modules/capabilities/registry.py` — 增加 maturity 字段
- `capability_*_routes.py` 或 registry API — 返回 maturity
- Vue 导航组件 — 渲染 badge

---

### S4: AI fallback 显式通知

**问题**：脚本生成 AI 返回非法 JSON 时静默 fallback 到模板脚本，用户以为拿到了 AI 结果。

**目标**：
- AI 调用失败/降级时返回 `degraded: true` 标记
- 前端展示 Toast："脚本生成已降级为模板模式（AI 调用失败）"
- 不改变 fallback 逻辑本身

**影响范围**：
- `ai_client.py` — 返回值增加 degraded 标记
- 调用 ai_client 的步骤模块 — 透传 degraded
- 前端对应面板 — 消费 degraded 标记

---

## 中期任务（M1-M2）

### M1: YouTube OAuth 完整授权流

**问题**：YouTube connector 有 API 骨架但需用户手动粘贴 access_token，无 OAuth 跳转流程。

**目标**：
- 实现 OAuth 2.0 authorization code flow
- Settings 页面"连接 YouTube"按钮 → 浏览器跳转 → 授权回调 → token 持久化
- 自动 refresh_token 刷新

**影响范围**：
- `content_publish.py` — token refresh 逻辑
- `capability_content_publish_routes.py` — OAuth callback 路由
- Settings 页面 — 连接/断开 UI
- `server.py` — 注册 OAuth 路由

---

### M2: Publish history API + UI 展示

**问题**：发布后无结果记录，用户无法回溯"发了什么、发到哪、是否成功"。

**目标**：
- `GET /api/capabilities/content_publish/history` — 历史记录查询
- 支持按平台、状态、error_class 过滤
- 前端展示发布历史列表

**影响范围**：
- 审计日志查询封装
- 新增 history API 路由
- 前端 publish 面板增加 history tab

---

## 结构性问题（L1）

### L1: server.py 渐进拆分

**问题**：server.py 7500+ 行，承担路由注册 + Job 管理 + 状态机 + 工具函数——职责过多。

**目标**：
- 渐进拆分为 `app_factory.py` + `job_manager.py` + `state_machine.py`
- 每次拆分一个独立模块，保持所有测试绿色
- 不改变对外 API 签名

**原则**：
- 只做 extract，不做重构
- 每拆一个文件，跑全量回归
- 分 3-5 个子 PR 完成

---

## 执行约束

1. **以阶段为单位推进**，不跨阶段大幅串改，不回头重做已完成内容
2. **最小闭环思路**，每个任务独立可验收
3. **每个任务必须包含**：
   - 修改文件清单（文件路径 + 新增/修改/删除 + 一句话职责说明）
   - 用户可感知能力（能做什么 / 从哪进入 / 看到什么变化）
   - 真实场景通测（至少 5 类验证点）
   - 遗留问题清单（高/中/低优先级）
   - 是否建议进入下一阶段
4. **不允许假完工**：功能可运行 + 前端或 API 可见 + 有真实场景测试 + 无明显回归
5. **强制补测试、跑回归、更新文档**

---

## 汇报格式（固定）

```
## [任务编号] 闭环汇报

### 1. 改动文件清单
| 文件路径 | 操作 | 职责变化 |
|---------|------|---------|

### 2. 用户可感知能力
- 用户现在能做什么
- 从哪里进入
- 操作后看到什么变化

### 3. 真实场景通测
| 场景 | 验证点 | 结果 |
|------|--------|------|

### 4. 遗留问题清单
| 优先级 | 问题 | 说明 |
|--------|------|------|

### 5. 是否建议进入下一阶段
建议 / 不建议，原因：...
```

---

## 变更记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-03-10 | v2.0 初版 | 基于用户视角审视，建立 S1-S4 + M1-M2 + L1 路线图 |
| 2026-03-10 | S1 完成 | 退化行为显式通知：beauty/pipeline/workflow 退化收集 + Toast + 审计日志 |
| 2026-03-10 | S2 完成 | recovery_hint 前端消费：Alpine.js + Vue 一键重试按钮、恢复状态展示、duplicate_risk 警告 |
| 2026-03-10 | S3 完成 | Capability 导航状态 badge：从 registry 读取 status，显示稳定/原型/开发中标签，planned 项拦截 |
| 2026-03-10 | S4 完成 | AI fallback 显式通知：step2/3 AI 退化时写 ai_degraded 到步骤状态，前端 Toast 告知用户 |
