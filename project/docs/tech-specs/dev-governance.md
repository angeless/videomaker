# VideoEditor 开发治理流程 (Development Governance)

**文档类型：** 技术规范 - 开发治理流程
**版本：** v2.0
**日期：** 2026-03-20
**作者/责任人：** Claude Code 自动化开发体系
**范围：** VideoEditor 桌面版（v0.7.0 及以后）

---

## 1. 文档目的

本文件定义了 VideoEditor 项目中所有开发活动的标准化流程、文件管理规范、质量控制方法，约束 AI 开发者（Claude Code）和人类开发者在代码交付全周期中的行为。

目标：
- 确保每次迭代都有完整的计划、执行、验证、记录闭环
- 最小化认知负担和协作摩擦
- 让任意新加入的开发者都能快速理解当前状态和下一步动作
- 保证代码质量、可维护性、可追溯性
- 支持自动化开发 Agent 在没有人类实时指导下自主完成迭代

---

## 2. 开发版本管理

### 2.1 语义化版本规则

版本号格式：**MAJOR.MINOR.PATCH**

- **MAJOR**：重大功能变更或架构调整（例：v0.7.0 → v1.0.0）
- **MINOR**：功能增强、新能力模块、向后兼容改动（例：v0.6.0 → v0.7.0）
- **PATCH**：Bug 修复、性能优化、文档更新（例：v0.6.0 → v0.6.1）

规则：
- 每个版本一经 tag 就不再修改
- MAJOR 或 MINOR 变更时，PATCH 重置为 0
- 同一工作线程内只能开发一个目标版本（例：不能在开发 v0.8.0 时跳转到 v0.9.0）

### 2.2 VERSION 文件管理

位置：`/项目根目录/VERSION`

格式（单行纯文本，无额外字符）：
```
0.6.0
```

更新规则：
- VERSION 文件由开发者在完成整个版本迭代后手动更新
- 更新时机：在 CHANGELOG.md 中记录所有本版本改动后，新建 git tag 前
- 更新方式：`echo "x.y.z" > VERSION`
- 每个 git tag 对应一个 VERSION 内容快照

### 2.3 CHANGELOG.md 格式

位置：`/项目根目录/CHANGELOG.md`

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 规范：

```markdown
# 变更日志

所有重要变更都将被记录在此文件中。

## [未发布]

### 新增 (Added)
- 新功能描述

### 修改 (Changed)
- 现有功能的改进

### 修复 (Fixed)
- Bug 修复描述

### 移除 (Removed)
- 删除的功能

### 安全 (Security)
- 安全补丁

## [0.6.0] - 2026-03-19

### 新增
- 审计日志系统（P0-1）
- 队列恢复 UX 改进（P0-2）
- YouTube 发布 connector 骨架（P1）

### 修复
- 修复 23/26 UX 问题

---

## 规则

1. 每个 R（Release 任务）完成后立即更新 CHANGELOG.md 中的"未发布"章节
2. 新增、修改、修复、移除、安全分类各占一行或多行
3. 每条记录简洁清晰，面向最终用户理解
4. 一个版本 release 前，将"未发布"章节改为"[x.y.z] - YYYY-MM-DD"
5. 严禁倒序；最新的版本始终在顶部
```

### 2.4 Git Commit Message 规范

格式遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 列表：**
- `feat`：新功能（MINOR 版本升级）
- `fix`：Bug 修复（PATCH 版本升级）
- `docs`：文档更新（无版本升级）
- `style`：代码风格调整、格式化（无版本升级）
- `refactor`：代码重构、无功能变更（PATCH 或 MINOR 取决于范围）
- `perf`：性能优化（PATCH）
- `test`：测试相关改动（无版本升级）
- `chore`：构建脚本、依赖更新等（无版本升级）

**Scope 规范：**
- 按模块或功能区域命名，例：`(app_api)`, `(publish_prep)`, `(vue_ui)`, `(job_runtime)`
- Scope 内如果涉及多个子模块，用 `-` 分隔，例：`(L1-1)` 表示 server.py 的第 1 次大提取
- Scope 可选但强烈建议

**Subject 规范：**
- 以命令式动词开头（"add", "fix", "improve"，而非 "added", "fixed"）
- 首字母小写
- 长度 ≤ 50 个字符
- 末尾无句号

**Body：**
- 可选，但 MINOR 或 MAJOR 变更建议包含
- 解释做了什么以及为什么做
- 每行 ≤ 72 个字符
- 与 Subject 间隔一空行

**Footer：**
- 记录 Breaking Changes: `BREAKING CHANGE: ...`
- 记录关联的 issue: `Closes #123`
- 与 Body 间隔一空行

**示例：**
```
feat(publish_prep): add webhook notification template for TikTok

- Extend PublishPrepEngine to support webhook notification payloads
- Add template support for TikTok webhook content
- Maintain backward compatibility with existing 10+ platform templates

Closes #145
```

```
fix(job_runtime): prevent duplicate job dispatch on rapid retry

Improved idempotency check to handle concurrent retry calls within 100ms window.

BREAKING CHANGE: job retry API now requires explicit idempotency_key param
```

### 2.5 分支策略

**主分支：**
- `main`：生产分支，始终保持可发布状态，对应 VERSION 中的版本号
- 任何人都不能直接 push 到 main；必须通过合并流程

**开发分支命名规则：**

| 分支类型 | 命名规则 | 场景 | 生命周期 |
|---------|---------|------|---------|
| 功能 | `feature/<功能名>` | 新增能力、新模块、新功能 | 完成后合并，删除 |
| 修复 | `fix/<问题描述>` | Bug 修复 | 完成后合并，删除 |
| 发布 | `release/v<版本号>` | 版本发布前的最后调整 | Release 后合并到 main，删除 |
| 实验 | `experiment/<实验名>` | 探索性、原型级工作 | 决定采纳后转为 feature，或删除 |

**规则：**
- 分支源始终来自 main
- 分支名称全小写，单词间用 `-` 分隔，不使用大写字母、下划线或 `/` 嵌套
- 一个分支对应一个独立的、完整的工作单元（不跨越多个版本迭代）
- 长期未提交的分支（> 14 天无新 commit）应予以清理

**示例：**
```bash
# 新增发布 connector
git checkout -b feature/publish-connector-tiktok

# Bug 修复
git checkout -b fix/job-dispatch-race-condition

# 版本发布
git checkout -b release/v0.7.0

# 实验性工作
git checkout -b experiment/llm-title-generation-v2
```

### 2.6 Git Tag 规则

Tag 格式：`v<MAJOR>.<MINOR>.<PATCH>`

**创建时机：**
- 版本完全通过验证后（所有测试通过、审计通过、无已知高风险项）
- 在 main 分支上，对应 VERSION 文件更新的 commit

**创建命令：**
```bash
git tag -a v0.7.0 -m "Release v0.7.0: feature X, feature Y, fix Z"
git push origin v0.7.0
```

**查询：**
```bash
git tag -l                  # 列出所有 tag
git show v0.7.0             # 查看特定 tag
git log --oneline v0.6.0..v0.7.0  # 查看版本间的 commit 差异
```

**规则：**
- Tag 一经创建就不删除（除非极端误操作需要强制修复）
- 不允许 tag 指向非 main 分支的 commit
- Annotated tag（带注解）优于 lightweight tag（轻量级）

---

## 3. 开发计划管理

### 3.1 开发计划文档命名和位置

位置：`/docs/dev-plans/`

命名格式：`dev-plan-v{版本号}.md`

示例：
- `dev-plan-v0.7.0.md` — v0.7.0 版本开发计划
- `dev-plan-v0.8.0.md` — v0.8.0 版本开发计划

### 3.2 开发计划文档结构

```markdown
# VideoEditor 版本开发计划（v{版本号}）

**文档版本：** V1.0
**日期：** YYYY-MM-DD
**基线 Commit：** <commit hash> (<commit message>)
**基线 VERSION：** x.y.z

---

## 1. 版本目标

（一句话总结此版本核心目标）

例：支持 TikTok 多账户发布，完善发布前准备流程。

## 2. 版本范围

### 包含的需求
- 需求 A：描述
- 需求 B：描述
- 需求 C：描述

### 不包含的需求（Future）
- 需求 D：为什么推后
- 需求 E：为什么推后

## 3. 任务列表

| 任务ID | 任务名称 | 所属模块 | 目标版本 | 状态 | 优先级 |
|------|--------|--------|--------|------|------|
| R1 | 新增 TikTok connector | content_publish | v0.7.0 | Planned | P0 |
| R2 | 优化发布前检查逻辑 | publish_prep | v0.7.0 | Planned | P0 |
| R3 | 修复字幕校准延迟问题 | subtitle_calibration | v0.7.0 | Planned | P1 |

## 4. 各任务详细定义

### R1: 新增 TikTok connector

**目标：**
新增 TikTok 平台作为 content_publish 模块的一个新 connector，支持视频发布、基础元数据设置。

**涉及文件：**
- `modules/capabilities/content_publish.py` — 新增 TiktokConnector 类
- `modules/app_api/routes/publish_api.py` — 新增 /api/publish/tiktok 端点
- `apps/desktop/ui-vue/src/views/PublishView.vue` — 新增 TikTok 平台选项
- `apps/desktop/ui-vue/src/i18n/labels.js` — 新增 TikTok 相关文案
- `tests/test_content_publish.py` — 新增 TikTok connector 测试用例

**输入：**
- 视频文件路径 (string)
- 视频元数据 (title, description, tags, thumbnail) (dict)
- TikTok 登录状态 (验证用户是否已授权 TikTok API)

**输出：**
- 发布成功：{ success: true, video_id: "...", url: "..." }
- 发布失败：{ success: false, error_code: "...", error_message: "..." }

**验收标准：**
- [ ] TikTok connector 类实现，包含 authenticate(), validate(), publish() 三个核心方法
- [ ] /api/publish/tiktok 路由实现，接收 POST 请求，返回 200 或 4xx/5xx
- [ ] Vue UI 中显示 TikTok 平台选项，与其他平台保持视觉一致
- [ ] 所有新增代码通过 pylint / black 检查
- [ ] 单元测试通过率 100%（5 个测试用例）
- [ ] 集成测试通过：模拟端到端的视频发布流程
- [ ] 无 Breaking Change；现有平台功能不被影响
- [ ] 代码注释完整，函数签名清晰
- [ ] CHANGELOG.md 已更新

**依赖项：**
- 需要 TikTok API 文档和开发者账号（用户自备）
- 不依赖其他 R 任务

**已知约束：**
- 不支持 TikTok 草稿功能（仅支持直接发布）
- 单次发布 ≤ 10 分钟的视频（TikTok 限制）

---

### R2: 优化发布前检查逻辑

（类似结构）

---

### R3: 修复字幕校准延迟问题

（类似结构）

---

## 5. 完成状态追踪

| 任务 | 计划周期 | 实际完成日期 | 迭代次数 | 备注 |
|-----|--------|----------|--------|------|
| R1 | 3 天 | — | 0 | 未开始 |
| R2 | 2 天 | — | 0 | 未开始 |
| R3 | 1 天 | — | 0 | 未开始 |

## 6. 变更记录

| 日期 | 变更内容 | 责任人 |
|-----|--------|------|
| 2026-03-19 | 初始版本，定义 R1/R2/R3 | Claude Code |

---

## 7. 决策和假设

- 假设：用户已在系统外完成 TikTok API 授权
- 假设：TikTok API 稳定性与 YouTube API 相当
- 决策：优先支持单账户发布，多账户在 v0.8.0 支持

## 8. 风险和缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|-----|------|--------|
| TikTok API 变更 | 中 | 高 | 保留 webhook fallback |
| 视频格式兼容性 | 中 | 中 | 添加预检查逻辑 |
```

### 3.3 任务（R）的完整定义规范

每个任务必须包含以下字段，确保后续开发者能独立完成而无歧义：

| 字段 | 类型 | 必填 | 说明 |
|-----|------|------|------|
| 目标 (Objective) | String | Yes | 一句话总结任务做什么，为什么做 |
| 涉及文件 (Affected Files) | List[String] | Yes | 列出所有将被创建、修改的文件的绝对路径 |
| 输入 (Input) | Dict | Yes | 定义该任务接受的所有输入参数、数据结构、来源 |
| 输出 (Output) | Dict | Yes | 定义该任务产生的所有输出、返回值、副作用 |
| 验收标准 (Acceptance Criteria) | List[String] | Yes | Checklist 形式，每一项必须是可测试的陈述 |
| 依赖项 (Dependencies) | List[String] | Yes | 此任务依赖的其他 R 任务、外部库、工具 |
| 已知约束 (Known Constraints) | List[String] | No | 列出该任务的所有已知限制、边界情况 |

### 3.4 计划变更记录

计划初版发布后，如需变更任务范围、需求、验收标准：

1. 在计划文档中新增"变更记录"章节
2. 每次变更记录：日期、变更内容、变更原因、责任人
3. 不允许通过口头讨论修改计划；所有变更必须文档化
4. 版本号规则：初版 V1.0，每次变更升级为 V1.1 / V1.2 / V2.0 等

示例：
```markdown
## 变更记录

| 版本 | 日期 | 变更内容 | 原因 | 责任人 |
|-----|-----|--------|------|------|
| V1.0 | 2026-03-19 | 初版发布 | — | Claude Code |
| V1.1 | 2026-03-20 | R1 中移除多账户支持（推迟到 v0.8.0） | API 超期，无法在本迭代完成 | Human PM |
| V1.2 | 2026-03-21 | R3 验收标准新增"字幕延迟 < 50ms" | 用户反馈 | Claude Code |
```

---

## 4. 迭代开发流程（核心章节）

**核心原则：** 每个 R（Release）任务必须走完整的 7 个阶段的治理循环，输出完整的过程记录和文件产物。任何阶段失败或无法通过都必须报告，不允许跳过。

### 4.1 Phase 1: 理解与计划

**目标：** 深入理解任务需求，制定实施方案，识别风险。

**操作步骤：**

1. **读取技术规范**
   - 阅读 `docs/tech-specs/architecture.md` 了解系统整体设计
   - 阅读 `docs/tech-specs/coding-standards.md` 了解代码规范
   - 阅读本文件（dev-governance.md）理解开发流程

2. **读取当前状态**
   - 读取 `VERSION` 文件，获知当前版本号
   - 阅读 `CHANGELOG.md`，了解最近 3-5 个版本的变更历史
   - 运行 `git log --oneline -20` 查看最近 20 条 commit，理解最近的改动趋势

3. **读取开发计划**
   - 定位当前版本对应的计划文件，例如 `docs/dev-plans/dev-plan-v0.7.0.md`
   - 逐条阅读所有 R 任务定义
   - 找出当前要处理的 R 任务（通常是"状态 = Planned"的第一个）

4. **检查前置条件**
   - 检查上一个 R 任务是否已完成（查看计划文件中的状态）
   - 如果当前 R 有"依赖项"，逐一验证依赖项是否已完成
   - 验证 git 本地状态：`git status` 应该是 clean（无未提交改动）

5. **输出实施计划**

   新建文件：`docs/dev-plans/{日期}-r{N}-implementation-plan.md`

   例：`docs/dev-plans/2026-03-19-r1-implementation-plan.md`

   内容结构：
   ```markdown
   # R{N} 实施计划 - {任务名称}

   **日期：** 2026-03-19
   **任务ID：** R1
   **任务名称：** 新增 TikTok connector
   **规划时间：** 3 天

   ---

   ## 1. 需求确认

   （从开发计划中复制）
   - 目标：...
   - 输入：...
   - 输出：...
   - 验收标准：... (Checklist)

   ## 2. 架构设计

   ### 2.1 模块布局
   - TiktokConnector 类：在 `modules/capabilities/content_publish.py` 中实现
   - 基于已有的 YoutubeConnector / WeiboConnector 参考模式
   - 继承基类 BasePublishConnector

   ### 2.2 接口签名
   ```python
   class TiktokConnector(BasePublishConnector):
       def __init__(self, api_key: str, api_secret: str):
           ...

       def authenticate(self) -> Dict[str, Any]:
           ...

       def validate(self, video_path: str, metadata: Dict) -> Tuple[bool, str]:
           ...

       def publish(self, video_path: str, metadata: Dict) -> Dict[str, Any]:
           ...
   ```

   ### 2.3 与现有系统的集成
   - content_publish.py 中的 `PublishEngine.register_connector('tiktok', TiktokConnector)`
   - /api/publish/tiktok 路由文件新建或在 publish_api.py 中新增
   - Vue UI 在 PublishView.vue 中新增平台选项

   ## 3. 文件清单

   | 文件路径 | 类型 | 操作 | 行数估计 |
   |--------|------|------|--------|
   | modules/capabilities/content_publish.py | Python | Modify | +250 行 |
   | modules/app_api/routes/publish_api.py | Python | Modify | +80 行 |
   | apps/desktop/ui-vue/src/views/PublishView.vue | Vue | Modify | +30 行 |
   | apps/desktop/ui-vue/src/i18n/labels.js | JS | Modify | +15 行 |
   | tests/test_content_publish.py | Python | Modify | +120 行 |
   | **总计** | — | — | **~495 行** |

   ## 4. 实施步骤

   1. Step 1: 在 content_publish.py 中实现 TiktokConnector 基类 (100 行)
   2. Step 2: 实现 TiktokConnector 的 authenticate/validate/publish 三个方法 (150 行)
   3. Step 3: 在 content_publish.py 中注册 TiktokConnector (5 行)
   4. Step 4: 在 publish_api.py 中新增 /api/publish/tiktok 端点 (80 行)
   5. Step 5: 在 Vue UI 中新增 TikTok 平台卡片 (30 行)
   6. Step 6: 新增文案标签到 labels.js (15 行)
   7. Step 7: 编写单元测试 (60 行)
   8. Step 8: 集成测试、手工验证 (—)

   每个 Step 完成后立即自检并验证语法。

   ## 5. 测试策略

   **单元测试：**
   - test_tiktok_authenticate: 模拟 API 成功 / 失败
   - test_tiktok_validate: 验证视频时长、格式
   - test_tiktok_publish: 验证发布逻辑
   - test_tiktok_error_handling: 验证异常处理
   - test_tiktok_integration: 完整流程测试

   **集成测试：**
   - 端到端流程：用户选择 TikTok → 上传视频 → 设置文案 → 点击发布 → 验证返回结果
   - 回归测试：运行全量已有测试，确保 YouTube/Weibo 等现有平台不被破坏

   **手工验证：**
   - 启动应用，进入发布页面，验证 TikTok 选项可见
   - 尝试发布（需要真实 TikTok 账号）
   - 验证错误提示文案清晰准确

   ## 6. 风险预判

   | 风险 | 概率 | 影响 | 缓解措施 |
   |-----|-----|------|--------|
   | TikTok API 文档过期 | 中 | 高 | 实时查证，预留 fallback |
   | 与现有发布流程冲突 | 低 | 高 | 与 BasePublishConnector 保持 interface 一致 |
   | Vue 组件兼容性 | 低 | 中 | 基于已有组件复用代码 |

   ## 7. 依赖和前置条件

   - 无其他 R 任务依赖
   - 需要 TikTok API 开发者文档
   - 需要模拟 TikTok API responses（用于测试）

   ## 8. 完成标志

   本阶段完成的标志：
   - [ ] 架构设计已评审通过（人类确认）
   - [ ] 文件清单明确，无遗漏
   - [ ] 实施步骤清晰，每步都可独立执行
   - [ ] 测试策略定义完整
   - [ ] 风险已识别并有缓解方案
   ```

**输出物：** 实施计划文档，包含架构设计、文件清单、步骤、风险预判。

**检查清单：**
- [ ] 理解了任务的完整需求
- [ ] 理解了与现有系统的接口关系
- [ ] 列出了所有涉及的文件
- [ ] 设计了整体架构，避免 Breaking Change
- [ ] 风险已识别
- [ ] 实施计划已确认（人类审批或 AI 自检通过）

---

### 4.2 Phase 2: 执行（增量开发）

**目标：** 按照实施计划逐步编写代码，确保每一步都完整、可验证。

**核心原则：**
- **增量编写**：每次只完成一个小步骤，立即验证
- **及时验证**：不积累修改；每个文件完成后立即检查语法
- **避免幻觉**：严禁想象或猜测某个库、函数、接口的存在；必须通过代码扫描确认
- **清晰注释**：关键逻辑添加注释；函数签名明确

**操作步骤：**

1. **开始前检查**
   ```bash
   git status              # 确保 clean
   git branch              # 确认在正确分支（feature/xxx）
   cat VERSION             # 确认当前版本号
   ```

2. **按照实施计划逐步执行**

   对于每一个 Step（例如 Step 1: 在 content_publish.py 中实现 TiktokConnector 基类）：

   a. **打开相关文件，阅读已有代码**
      - 运行 `grep -n "class.*Connector" modules/capabilities/content_publish.py` 找到已有 connector 实现
      - 阅读 YouTube/Weibo connector 的完整实现（100-200 行），作为参考
      - 理解基类 BasePublishConnector 的接口要求

   b. **添加新代码**
      - 在 content_publish.py 中的适当位置插入 TiktokConnector 类
      - 每个方法上添加 docstring，说明参数、返回值、异常
      - 使用 TODO 标记未完成的部分（例如 `# TODO: implement error retry logic`）

   c. **验证语法**
      ```bash
      python3 -m py_compile modules/capabilities/content_publish.py
      ```
      如果出错，根据错误信息修复。

   d. **运行相关单元测试**（如果已有）
      ```bash
      pytest tests/test_content_publish.py::test_tiktok_authenticate -v
      ```
      如果失败或无法运行，记录失败原因，继续下一步。

   e. **生成简要的 Step 完成笔记**
      在开发计划中的实施步骤旁添加完成时间和摘要：
      ```
      Step 1: 在 content_publish.py 中实现 TiktokConnector 基类
              — [DONE 2026-03-19 10:30] Added 100 lines of TiktokConnector.__init__ and docstring
      ```

3. **处理集成依赖**

   当完成单个文件的修改后，如果该文件被其他模块导入，需要验证不会破坏现有引用：

   ```bash
   # 搜索该文件被谁 import
   grep -r "from modules.capabilities.content_publish import" --include="*.py"
   grep -r "import.*content_publish" --include="*.py"

   # 对于每个引用文件，确认新增的内容不会影响既有导入
   ```

4. **定期 commit（每个 Step 或每日）**

   不允许积累超过 4-5 个 Step 的改动后再 commit。推荐每个 Step 完成后就 commit：

   ```bash
   git add modules/capabilities/content_publish.py
   git commit -m "feat(content_publish): add TiktokConnector base class

   - Implement TiktokConnector inheriting BasePublishConnector
   - Define authenticate(), validate(), publish() method stubs
   - Add comprehensive docstrings following Google style guide"
   ```

5. **避免常见陷阱**

   - **幻觉导入：** 不要假设 `from external_lib import something` 存在；通过 `pip show` 或阅读 requirements.txt 确认
   - **模糊假设：** 不要假设某个配置项存在；通过 grep 搜索 settings.py 或 config.py 确认
   - **跨文件不一致：** 当在多个文件中定义相同的常量或配置时，使用中央集中定义（例如 `constants.py`），而非重复定义

**输出物：** 编写完成的源代码文件，每个文件通过语法检查，每个 commit 满足 Conventional Commits 规范。

**检查清单：**
- [ ] 所有新文件都通过 `python3 -m py_compile` 或等效的语法检查
- [ ] 每个 commit message 满足规范
- [ ] 没有幻觉导入或假设
- [ ] 代码注释清晰（特别是复杂逻辑）
- [ ] 没有遗漏涉及文件

---

### 4.3 Phase 3: 测试

**目标：** 验证新增代码的正确性、完整性、与既有代码的兼容性。

**分为三个级别：单元测试、集成测试、手工验证**

#### 4.3.1 单元测试

**操作步骤：**

1. **确认测试文件存在**
   - 对于新模块，创建 `tests/test_{模块名}.py`
   - 对于既有模块的扩展，在 `tests/test_{模块名}.py` 中新增测试类/函数

2. **编写测试用例**

   遵循 Arrange-Act-Assert (AAA) 模式：

   ```python
   def test_tiktok_authenticate_success():
       """Test TiktokConnector.authenticate() with valid credentials."""
       # Arrange: set up test data and mock
       connector = TiktokConnector(
           api_key='test_key',
           api_secret='test_secret'
       )
       mock_response = {
           'access_token': 'token_xyz',
           'expires_in': 3600
       }
       with patch('requests.post', return_value=mock_response):
           # Act: call the method
           result = connector.authenticate()

           # Assert: verify the result
           assert result['success'] is True
           assert result['access_token'] == 'token_xyz'

   def test_tiktok_authenticate_failure():
       """Test TiktokConnector.authenticate() with invalid credentials."""
       # Arrange
       connector = TiktokConnector(api_key='invalid', api_secret='invalid')

       # Act & Assert
       with pytest.raises(AuthenticationError):
           connector.authenticate()
   ```

3. **运行测试并收集结果**
   ```bash
   pytest tests/test_content_publish.py::TestTiktokConnector -v --tb=short
   ```

4. **记录测试结果**

   创建临时测试日志：
   ```
   ✓ test_tiktok_authenticate_success — PASSED
   ✓ test_tiktok_authenticate_failure — PASSED
   ✗ test_tiktok_publish_oversized_video — FAILED

   Failure reason: Expected ValidationError but got RuntimeError
   Next step: Adjust error handling in TiktokConnector.validate()
   ```

5. **迭代修复**

   如果测试失败，返回 Phase 2 修复代码，然后重新运行测试。禁止跳过失败的测试。

**测试覆盖率要求：**
- 新增功能的测试覆盖率 ≥ 80%
- 至少包含 Happy Path（正常场景）和 Sad Path（错误场景）各一个测试

#### 4.3.2 集成测试

**操作步骤：**

1. **确认依赖的模块都已完成**

   例如：如果 R1 依赖 "content_publish.py 模块已完成"，确认该模块所有新增方法都通过单元测试。

2. **编写跨模块测试用例**

   ```python
   def test_publish_api_tiktok_end_to_end():
       """Integration test: full flow from API call to platform publish."""
       # Arrange: set up test app, database, mock TikTok API
       client = app.test_client()

       video_path = 'tests/fixtures/sample_video.mp4'
       metadata = {
           'title': 'Test Video',
           'description': 'This is a test',
           'tags': ['test', 'video']
       }

       # Act: call the API endpoint
       response = client.post(
           '/api/publish/tiktok',
           json={'video_path': video_path, 'metadata': metadata},
           headers={'Authorization': 'Bearer test_token'}
       )

       # Assert: verify the API response and side effects
       assert response.status_code == 200
       result = response.get_json()
       assert result['success'] is True
       assert 'video_id' in result
       assert result['url'].startswith('https://www.tiktok.com/')
   ```

3. **运行集成测试**
   ```bash
   pytest tests/test_publish_api.py -v --tb=short
   ```

4. **回归测试：运行全量既有测试**

   确保新增代码没有破坏既有功能：
   ```bash
   pytest tests/ -v --tb=short
   ```

   输出示例：
   ```
   ===== test session starts =====
   collected 173 items

   test_app_api.py::test_auth_bootstrap PASSED
   test_content_publish.py::test_youtube_connector_publish PASSED
   test_content_publish.py::test_weibo_connector_publish PASSED
   test_content_publish.py::test_tiktok_connector_authenticate PASSED
   ... (共 173 项)

   ===== 173 passed in 2.34s =====
   ```

   如果出现失败（如 172 passed, 1 failed），必须：
   - 分析失败原因
   - 如果是由新代码引起的回归，修复代码
   - 如果是既有测试的不稳定性，记录在案并通知维护者

**集成测试覆盖率要求：**
- 至少覆盖一个完整的端到端用户流程
- 包含至少一个异常场景（网络超时、API 错误等）

#### 4.3.3 手工验证

**操作步骤：**

1. **启动应用**
   ```bash
   python apps/desktop/server.py
   # 或
   npm run dev  (for Vue UI)
   ```

2. **按照实施计划中的"手工验证"清单逐一测试**

   例如：
   - 进入发布页面
   - 验证 TikTok 平台选项可见
   - 上传一个视频
   - 填写文案信息
   - 点击发布
   - 验证发布成功/失败的提示

3. **记录观察到的问题**

   如果遇到 UI 错误、文案不清晰、按钮状态异常等，记录：
   ```
   Issue: 发布成功后没有显示"返回列表"按钮
   Severity: Medium
   步骤: 1. 进入发布页 2. 填写视频 3. 点击发布 4. 发布成功后（预期：显示成功提示和返回按钮，实际：只有成功提示，无返回按钮）
   影响范围: TikTok 平台（其他平台正常）
   ```

4. **处理发现的问题**

   - 高优先级问题：立即修复，重新测试
   - 低优先级问题：记录到开发计划的"待办"或"下一个版本"

**手工验证的对象：**
- 新用户流程：第一次使用该功能的用户能否理解？
- 正常流程：核心路径是否可用？
- 异常处理：错误时是否有清晰的提示？
- 一致性：新功能与既有功能的视觉和交互是否一致？

**输出物：** 测试日志、手工验证记录、发现的问题清单

**检查清单：**
- [ ] 单元测试覆盖率 ≥ 80%，所有测试通过
- [ ] 集成测试通过，覆盖至少一个完整流程
- [ ] 全量回归测试通过（173 tests passed, 0 failed）
- [ ] 手工验证完成，关键路径可用
- [ ] 发现的问题已评估优先级
- [ ] 高优先级问题已修复并重测

---

### 4.4 Phase 4: 审计

**目标：** 对新增代码进行全面的技术审查，确保代码质量、规范性、安全性。

**输出文件：** `docs/audit/{日期}-r{N}-audit.md`

例：`docs/audit/2026-03-19-r1-audit.md`

**审计报告结构：**

```markdown
# R{N} 代码审计报告 - {任务名称}

**日期：** 2026-03-19
**任务ID：** R1
**审计者：** Claude Code
**审计时间：** 2 小时

---

## 1. 审计范围

审查以下新增或修改文件：
- modules/capabilities/content_publish.py (TiktokConnector 类，+250 行)
- modules/app_api/routes/publish_api.py (+80 行)
- apps/desktop/ui-vue/src/views/PublishView.vue (+30 行)
- tests/test_content_publish.py (+120 行)

总计：+480 行代码

---

## 2. 代码自检

### 2.1 语法和语言规范

| 检查项 | 结果 | 备注 |
|------|------|------|
| Python 语法正确（py_compile） | ✓ PASS | 无错误 |
| 遵循 PEP 8（通过 pylint） | ✓ PASS | 0 错误，3 警告（见下） |
| 代码缩进一致 | ✓ PASS | 使用 4 空格 |
| 导入语句排列正确 | ✓ PASS | 标准库 → 第三方库 → 本地模块 |
| Vue 语法正确 | ✓ PASS | 无 Vue 编译错误 |

**PEP 8 警告：**
1. Line 45: Line too long (93 > 88 characters) — 已接受（注释很重要，无法缩短）
2. Line 102: Function is too complex (C901) — 已优化，复杂度从 12 降至 8
3. Line 156: Too many arguments (6 > 5) — 已计划，暂时保留（后续重构）

### 2.2 命名和可读性

| 检查项 | 结果 | 备注 |
|------|------|------|
| 类/函数名清晰准确 | ✓ PASS | TiktokConnector, publish(), validate() 等命名清晰 |
| 变量名避免单字符 | ✓ PASS | 未发现单字母变量 |
| 常量使用全大写 | ✓ PASS | TIKTOK_API_TIMEOUT, MAX_VIDEO_SIZE 等 |
| 函数 docstring 完整 | ✓ PASS | 所有公开方法都有 docstring，包含参数和返回值说明 |
| 注释清晰且避免过度 | ✓ PASS | 注释用于解释复杂逻辑，未出现自明的注释 |

### 2.3 结构和设计

| 检查项 | 结果 | 详情 |
|------|------|------|
| 遵循既有架构模式 | ✓ PASS | TiktokConnector 继承 BasePublishConnector，与 YoutubeConnector/WeiboConnector 结构一致 |
| 不违反单一职责原则 | ✓ PASS | TiktokConnector 只负责 TikTok 发布，未混杂其他逻辑 |
| 接口设计合理 | ✓ PASS | authenticate/validate/publish 三个公开方法，职责清晰 |
| 未引入循环依赖 | ✓ PASS | 依赖关系：TiktokConnector → BasePublishConnector → (无反向依赖) |
| 避免硬编码 | ✓ PASS | API 密钥来自参数，timeout 值定义为常量 |
| 异常处理合理 | ✗ FAIL | 见 Issue #1 |

### 2.4 错误处理

**Issue #1: 异常捕获不够细化**

代码：
```python
def publish(self, video_path: str, metadata: dict) -> dict:
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        return {'success': False, 'error': str(e)}
```

问题：捕获过于宽泛（Exception），无法区分网络错误、API 错误、本地文件错误。

影响：用户无法得到有针对性的错误提示。

建议：
```python
except requests.ConnectionError:
    return {'success': False, 'error_code': 'NETWORK_ERROR', 'message': '网络连接失败'}
except requests.Timeout:
    return {'success': False, 'error_code': 'TIMEOUT', 'message': '请求超时，请重试'}
except FileNotFoundError:
    return {'success': False, 'error_code': 'FILE_NOT_FOUND', 'message': '视频文件不存在'}
```

**状态：** 已修复（commit abc123）

---

## 3. 接口一致性检查

### 3.1 API 端点规范

新增端点：`POST /api/publish/tiktok`

| 项目 | 要求 | 实现 | 状态 |
|-----|------|------|------|
| 请求格式 | JSON body: {video_path, metadata} | ✓ 已实现 | PASS |
| 响应格式 | JSON: {success, video_id?, error_code?, error_message?} | ✓ 已实现 | PASS |
| 状态码 | 成功 200，参数错误 400，认证失败 401，服务错误 500 | ✓ 已实现 | PASS |
| 认证机制 | Bearer token in Authorization header | ✓ 已实现 | PASS |
| 幂等性 | 支持 idempotency_key 参数 | ✗ 未实现 | FAIL |

**Issue #2: 缺少幂等性支持**

原文：开发计划中要求"单次发布 ≤ 10 分钟的视频"，未明确幂等性需求。

实际：其他发布 API（YouTube, Weibo）都支持 idempotency_key，防止重复发布。

建议：在 /api/publish/tiktok 中添加 idempotency_key 参数支持，与既有 API 保持一致。

**状态：** 已修复（commit def456）

### 3.2 前端组件一致性

Vue 组件 PublishView.vue 中新增 TikTok 平台选项。

检查与既有 YouTube/Weibo 选项的一致性：
- [ ] 卡片尺寸一致（300px × 200px）
- [ ] 文案排版一致（platform name, description, action button）
- [ ] 颜色方案一致（platform brand color, button color）
- [ ] 交互一致（hover effect, loading state, success/error state）

结果：✓ 全部一致

---

## 4. 测试覆盖率分析

### 4.1 单元测试覆盖

```
modules/capabilities/content_publish.py (TiktokConnector)

  Line Coverage:
    - __init__: 100% (2/2)
    - authenticate: 100% (12/12)
    - validate: 95% (19/20) — 1 行 edge case 未覆盖（文件权限异常）
    - publish: 80% (24/30) — 6 行异常处理未覆盖
    - _check_video_format: 100% (8/8)

  总体覆盖率: 87%
```

### 4.2 未覆盖的代码

| 代码片段 | 原因 | 优先级 | 计划 |
|--------|------|------|------|
| validate() L19-20 (FilePermissionError) | 环境难以模拟 | LOW | 下个版本补充 |
| publish() 中的 retry logic | 需要持久化支持 | MEDIUM | 当前版本补充 |

**结论：** 单元测试覆盖率 87%，达到 80% 目标。未覆盖的代码多为异常边界，可接受。

---

## 5. 已知风险与依赖

### 5.1 业务风险

| 风险 | 概率 | 影响 | 状态 |
|-----|-----|------|------|
| TikTok API 变更或下线 | Medium | High | 已建立 webhook fallback |
| 单次上传 > 10 分钟视频 | Low | Medium | 已添加 validate() 检查 |
| 用户多账户切换 | High | Medium | 当前版本仅支持单账户，v0.8.0 规划 |

### 5.2 技术依赖

- tiktok-api-python: ^1.2.0 (已在 requirements.txt 中，无新依赖)
- requests: ^2.28.0 (既有依赖，已经验证兼容)

### 5.3 系统依赖

- 无新系统依赖（macOS/Windows/Linux 都已支持）

---

## 6. 安全审查

### 6.1 认证和授权

- [ ] API 端点受 token 认证保护
- [ ] 用户不能发布其他用户的视频
- [ ] API key/secret 存储在 macOS Keychain（不硬编码）

结果：✓ 全部通过

### 6.2 输入验证

| 输入项 | 验证方法 | 状态 |
|------|--------|------|
| video_path | 文件存在性、格式、大小 | ✓ |
| metadata.title | 长度限制 (1-150 chars)、特殊字符过滤 | ✓ |
| metadata.tags | 数组长度、每项长度、类型检查 | ✓ |

结果：✓ 全部通过

### 6.3 数据保护

- [ ] 无敏感数据（密码、token）被记录到日志
- [ ] 发布结果不包含 raw API 响应
- [ ] 错误消息不暴露系统细节

结果：✓ 全部通过

---

## 7. 性能和可伸缩性

### 7.1 代码性能

| 方法 | 复杂度 | 耗时 | 瓶颈 |
|-----|------|------|------|
| authenticate | O(1) | 200ms (API call) | TikTok API 响应时间 |
| validate | O(n) | 100ms (文件扫描) | 本地磁盘 I/O |
| publish | O(1) | 2000ms (视频上传) | 网络带宽 |

结果：✓ 无性能问题

### 7.2 并发和资源

- 单个用户同时发布多个视频：支持（异步任务队列处理）
- 多个用户同时发布：支持（无全局锁，仅用户级锁）
- 内存占用：< 50MB （视频元数据缓存）

结果：✓ 可接受

---

## 8. 文档和可维护性

### 8.1 代码文档

| 项目 | 要求 | 实现 | 状态 |
|-----|------|------|------|
| 模块级 docstring | 说明模块职责 | ✓ | PASS |
| 类级 docstring | 说明类职责和依赖 | ✓ | PASS |
| 方法级 docstring | 说明参数、返回值、异常 | ✓ | PASS |
| 复杂逻辑注释 | 解释为什么，不是做什么 | ✓ | PASS |

### 8.2 外部文档

- [ ] CHANGELOG.md 已更新
- [ ] README.md 涉及部分已更新
- [ ] API 文档（如有）已更新

结果：✓ 全部已更新

---

## 9. 审计结论

### 总体评分

| 维度 | 评分 | 备注 |
|-----|------|------|
| 代码质量 | A | 清晰、规范，minor issues 已全部修复 |
| 功能完整性 | A | 满足所有验收标准 |
| 测试覆盖率 | A | 87%，超过 80% 目标 |
| 文档完整性 | A | 代码注释、提交说明、外部文档完整 |
| 安全性 | A | 无安全问题 |
| 兼容性 | A | 无破坏既有接口 |

**综合评级：A（优秀）**

### 主要发现

**优点：**
1. 代码结构清晰，继承既有架构模式
2. 错误处理完善（已修复 Issue #1）
3. 测试覆盖率高，用例完整
4. 文档齐全，易于维护

**需要改进的地方：**
1. 幂等性支持（已修复 Issue #2）
2. 复杂逻辑复杂度（已优化）

**建议：**
1. 后续考虑在 v0.8.0 中支持多账户发布
2. 在队列持久化完成后，补充发布中断恢复功能

---

## 10. 审计签名

**审计者：** Claude Code
**审计日期：** 2026-03-19
**审计结论：** ✓ APPROVED FOR MERGE

此代码可以合并到 main 分支。
```

**审计内容最少应包括：**

1. **代码自检**（参考 coding-standards.md 中的自检清单）
   - 语法正确性
   - 命名规范
   - 注释清晰性
   - 代码结构

2. **接口一致性**
   - API 端点与既有端点是否一致
   - 返回格式、状态码是否标准
   - 前端组件与既有组件是否一致

3. **错误处理覆盖**
   - 异常是否充分处理
   - 错误提示是否清晰
   - 异常流程是否可恢复

4. **测试覆盖**
   - 单元测试行覆盖率（目标 ≥ 80%）
   - 关键路径是否有测试
   - 异常路径是否有测试

5. **已知风险**
   - 列出审查过程中发现的潜在问题
   - 评估风险级别和影响范围
   - 给出缓解建议

**输出物：** 审计报告 Markdown 文件

**检查清单：**
- [ ] 代码通过了 pylint/black/flake8 等工具检查（仅 warnings，无 errors）
- [ ] 没有发现 Breaking Change
- [ ] 测试覆盖率 ≥ 80%
- [ ] 错误处理完善
- [ ] 无已知高优先级风险
- [ ] 文档完整（代码注释、CHANGELOG、README 等）
- [ ] 审计报告已生成

---

### 4.5 Phase 5: 测试报告

**目标：** 记录所有测试活动的结果，包括测试用例、执行结果、统计数据。

**输出文件：** `docs/test-reports/{日期}-r{N}-test-report.md`

例：`docs/test-reports/2026-03-19-r1-test-report.md`

**测试报告结构：**

```markdown
# R{N} 测试报告 - {任务名称}

**日期：** 2026-03-19
**任务ID：** R1
**执行者：** Claude Code
**执行时间：** 2026-03-19 10:00 - 16:00

---

## 1. 测试范围

- 单元测试：modules/capabilities/content_publish.py (TiktokConnector)
- 集成测试：/api/publish/tiktok 端点
- 回归测试：所有既有单元测试（test suite）
- 手工验证：发布流程 UI 测试

---

## 2. 测试用例和结果

### 2.1 单元测试

| 用例ID | 用例描述 | 前置条件 | 操作步骤 | 预期结果 | 实际结果 | 状态 |
|------|--------|--------|--------|--------|--------|------|
| UT-1 | authenticate() 成功 | TiktokConnector 实例化 | 调用 authenticate() 无参数 | 返回 {success: true, access_token: ...} | ✓ 符合预期 | PASS |
| UT-2 | authenticate() 失败（无效凭证） | TiktokConnector 实例化，api_key 无效 | 调用 authenticate() | 抛出 AuthenticationError | ✓ 符合预期 | PASS |
| UT-3 | validate() 合法视频 | TiktokConnector 实例化，视频文件存在 | 调用 validate(video_path) | 返回 (True, '') | ✓ 符合预期 | PASS |
| UT-4 | validate() 超长视频 | 视频时长 11 分钟 | 调用 validate() | 返回 (False, 'VIDEO_TOO_LONG') | ✓ 符合预期 | PASS |
| UT-5 | validate() 文件不存在 | video_path 指向不存在的文件 | 调用 validate() | 返回 (False, 'FILE_NOT_FOUND') | ✓ 符合预期 | PASS |
| UT-6 | publish() 成功 | TiktokConnector 已认证，视频有效 | 调用 publish(video_path, metadata) | 返回 {success: true, video_id: '...', url: '...'} | ✓ 符合预期 | PASS |
| UT-7 | publish() API 错误 | TikTok API 返回 5xx 错误 | 调用 publish() | 返回 {success: false, error_code: 'API_ERROR', ...} | ✓ 符合预期 | PASS |
| UT-8 | publish() 网络超时 | 模拟请求超时 (3秒后) | 调用 publish() | 返回 {success: false, error_code: 'TIMEOUT', ...} | ✓ 符合预期 | PASS |

**统计：**
- 总计：8 个测试用例
- 通过：8 个（100%）
- 失败：0 个
- 跳过：0 个

### 2.2 集成测试

| 用例ID | 场景 | 操作步骤 | 预期结果 | 实际结果 | 状态 |
|------|------|--------|--------|--------|------|
| IT-1 | POST /api/publish/tiktok 成功 | 1. 发送 POST /api/publish/tiktok，携带合法 video_path 和 metadata<br>2. 验证请求头包含 Authorization token | 返回 200，body 包含 {success: true, video_id, url} | ✓ 符合预期 | PASS |
| IT-2 | POST /api/publish/tiktok 未认证 | 发送 POST 请求但不含 Authorization header | 返回 401 Unauthorized | ✓ 符合预期 | PASS |
| IT-3 | POST /api/publish/tiktok 参数缺失 | 发送 POST 请求，缺少 video_path 字段 | 返回 400 Bad Request，error_message: "Missing required field: video_path" | ✓ 符合预期 | PASS |
| IT-4 | 重复发送（幂等性） | 发送两个相同的 POST 请求，idempotency_key 相同 | 第一个返回 200 with result，第二个返回 200 with 缓存结果（不重复上传） | ✓ 符合预期 | PASS |
| IT-5 | 与既有平台并存 | 先发送 YouTube 发布请求，再发送 TikTok 请求 | 两个请求都成功，互不干扰 | ✓ 符合预期 | PASS |

**统计：**
- 总计：5 个测试用例
- 通过：5 个（100%）
- 失败：0 个
- 跳过：0 个

### 2.3 回归测试（全量测试套件）

执行命令：`pytest tests/ -v`

```
collected 173 items

test_app_api.py::test_auth_bootstrap PASSED
test_app_api.py::test_auth_invalid_token PASSED
... (169 个既有测试)
test_content_publish.py::test_tiktok_authenticate PASSED
test_content_publish.py::test_tiktok_validate PASSED
test_content_publish.py::test_tiktok_publish PASSED
test_publish_api.py::test_api_publish_tiktok PASSED

===== 173 passed in 3.42s =====
```

**统计：**
- 总计：173 个测试
- 通过：173 个（100%）
- 失败：0 个
- 跳过：0 个
- **回归测试结论：✓ PASS，无破坏**

### 2.4 手工验证

| 项目 | 操作 | 观察结果 | 状态 |
|-----|------|--------|------|
| UI 可见性 | 启动应用，进入发布页面 | TikTok 平台卡片正常显示，与 YouTube/Weibo 并列 | PASS |
| 文案清晰性 | 查看 TikTok 卡片文案 | "发布到 TikTok" 清晰，描述准确 | PASS |
| 交互流程 | 上传视频 → 填写文案 → 点击发布 | 流程顺畅，各步反馈清晰 | PASS |
| 成功反馈 | 发布成功后 | 显示"发布成功"提示，包含 TikTok 链接 | PASS |
| 错误处理 | 故意上传无效格式文件 | 显示"视频格式不支持"错误信息，建议用户转码 | PASS |
| 一致性 | 与 YouTube 平台的 UI/交互对比 | 整体风格、按钮、文案风格一致 | PASS |

**统计：**
- 总计：6 个手工验证项
- 通过：6 个（100%）
- 失败：0 个

---

## 3. 缺陷统计

### 3.1 发现的缺陷

| 缺陷ID | 描述 | 严重程度 | 状态 | 修复方式 |
|------|------|--------|------|--------|
| BUG-1 | 发布成功后无"返回"按钮 | Medium | FIXED | 在 PublishView.vue 中添加 back navigation 逻辑 |
| BUG-2 | 错误提示文案使用了 error_code | High | FIXED | 改为使用人类可读的错误消息 |

### 3.2 已修复的问题

所有发现的问题已在修复后重测并通过。

---

## 4. 测试覆盖率

### 4.1 代码行覆盖率

```
modules/capabilities/content_publish.py:
  TiktokConnector 类: 87% (covered: 137/157 lines)

modules/app_api/routes/publish_api.py:
  publish_tiktok 函数: 100% (covered: 45/45 lines)

apps/desktop/ui-vue/src/views/PublishView.vue:
  TikTok 相关逻辑: 92% (covered: 23/25 lines)

总体覆盖率: 90%
```

### 4.2 测试类型分布

- 单元测试：8 个（占 53%）
- 集成测试：5 个（占 33%）
- 手工验证：6 个（占 14%）
- 回归测试：173 个（确保无破坏）

---

## 5. 测试执行时间

| 测试类型 | 执行时间 | 机器配置 |
|--------|--------|--------|
| 单元测试 | 1.2 s | MacBook Pro M1 |
| 集成测试 | 2.1 s | 同上 |
| 回归测试 | 3.4 s | 同上 |
| 手工验证 | 15 min | 同上 |
| **总计** | **18.7 min** | — |

---

## 6. 测试环境

- OS: macOS 12.6
- Python: 3.9.13
- pytest: 7.1.2
- Node.js: 16.14.0

---

## 7. 已知局限

| 项目 | 说明 | 影响 |
|-----|------|------|
| TikTok 账户 | 测试使用 mock API 而非真实 TikTok 账户 | 无法完全验证真实发布流程 |
| 多用户并发 | 当前测试仅单用户，未模拟多用户并发 | 无法验证并发场景 |
| 网络延迟 | 未完整模拟各种网络延迟场景 | 可能存在极端网络环境下的问题 |

---

## 8. 测试结论

### 总体评价

✓ **所有测试通过**（173/173）
✓ 代码覆盖率 90%
✓ 未发现 critical/high 级缺陷
✓ 用户流程可用

### 建议

1. 后续生产部署前，建议用真实 TikTok 账户进行端到端测试
2. 考虑添加并发发布的压力测试（v0.8.0）

### 签名

**测试者：** Claude Code
**测试日期：** 2026-03-19
**测试结论：** ✓ APPROVED FOR RELEASE
```

**测试报告最少应包括：**

1. **测试用例清单** —— 每个用例都应该能被复现
2. **执行结果统计** —— 通过/失败/跳过的数量
3. **缺陷清单** —— 发现的 bug、已修复状态
4. **覆盖率数据** —— 代码行覆盖率、分支覆盖率
5. **测试结论** —— 是否可以发布

**输出物：** 测试报告 Markdown 文件

**检查清单：**
- [ ] 所有测试用例执行完毕
- [ ] 通过率 ≥ 95%（允许跳过低优先级）
- [ ] 发现的 critical/high bug 都已修复并重测
- [ ] 回归测试通过（无破坏既有功能）
- [ ] 代码覆盖率 ≥ 80%
- [ ] 测试报告已生成

---

### 4.6 Phase 6: 收尾

**目标：** 更新所有相关文档，记录本迭代的成果，准备合并。

**操作步骤：**

1. **更新 CHANGELOG.md**

   在"未发布"章节中添加本次 R 任务的改动记录：
   ```markdown
   ## [未发布]

   ### 新增 (Added)
   - TikTok 平台发布支持（单账户，≤10分钟视频）
   - TikTok 发布 API 端点 /api/publish/tiktok
   - TikTok 发布前验证规则（格式、时长、文件大小）

   ### 修复 (Fixed)
   - （如有）发布流程中的错误处理不够细致

   ---

   ## [0.6.0] - 2026-03-19
   ...
   ```

2. **更新 VERSION（如需）**

   如果本次迭代涉及 MINOR 或 MAJOR 功能更新，需要决定是否升级版本号：
   - 如果只是补丁式修复：PATCH 升级（v0.6.0 → v0.6.1）
   - 如果是功能新增：MINOR 升级（v0.6.0 → v0.7.0）
   - 如果是架构大改：MAJOR 升级（v0.x.0 → v1.0.0）

   ```bash
   echo "0.7.0" > VERSION
   git add VERSION
   ```

3. **更新开发计划文档**

   在 `docs/dev-plans/dev-plan-v{版本号}.md` 中：
   - 标记本 R 任务状态为"Complete"
   - 更新"完成状态追踪"表格中的"实际完成日期"和"迭代次数"
   - 如有遗留的改进建议，转移到下一个版本的任务列表或"Future Work"章节

   例：
   ```markdown
   | 任务 | 计划周期 | 实际完成日期 | 迭代次数 | 备注 |
   |-----|--------|----------|--------|------|
   | R1 | 3 天 | 2026-03-19 | 2 | COMPLETE - TikTok connector 实现，Bug#1、#2 已修复 |
   | R2 | 2 天 | — | 0 | Planned |
   | R3 | 1 天 | — | 0 | Planned |
   ```

4. **最终 git commit**

   将所有文档更新、CHANGELOG、VERSION 变更提交为一个 commit：

   ```bash
   git add CHANGELOG.md VERSION docs/dev-plans/dev-plan-v0.7.0.md
   git commit -m "chore: finalize R1 — TikTok connector + documentation update

   - Add TikTok platform support to content_publish module
   - Implement /api/publish/tiktok API endpoint
   - Update CHANGELOG.md and VERSION for v0.7.0
   - Update development plan: R1 marked as complete
   - Test coverage: 173 tests passed, 90% code coverage

   Closes #R1"
   ```

   （注：`#R1` 是可选的；如果使用 GitHub Issues 跟踪 R 任务，可以填写对应 issue 号）

5. **创建 git tag（仅在版本发布时）**

   如果本次迭代完成了整个版本（所有 R 任务都完成），创建版本 tag：

   ```bash
   git tag -a v0.7.0 -m "Release v0.7.0: TikTok support, publish prep enhancement, subtitle calibration fix"
   git push origin v0.7.0
   ```

**输出物：** 更新后的 CHANGELOG.md、VERSION、开发计划文档、git commit

**检查清单：**
- [ ] CHANGELOG.md 已更新，本次改动记录清晰
- [ ] VERSION 已根据需要更新
- [ ] 开发计划文档已标记该 R 任务为完成
- [ ] 最终 commit 已提交
- [ ] 如果是完整版本发布，tag 已创建

---

### 4.7 Phase 7: 衍生建议

**目标：** 记录开发过程中发现的改进机会、技术债务、未来工作方向。

**操作步骤：**

1. **汇总开发过程中的观察**

   在开发、测试、审计过程中可能发现：
   - 代码可以优化的地方（但当前任务范围外）
   - 用户体验可以改进的地方
   - 架构可以改善的地方
   - 测试可以加强的地方

   例：
   - "TiktokConnector 的 retry logic 可以在 v0.8.0 中强化"
   - "Vue UI 中的平台卡片可以提取为通用组件"
   - "发布前检查逻辑可以统一到一个中央模块"

2. **分类和优先级评估**

   | 建议 | 类型 | 优先级 | 预期收益 | 计划 |
   |-----|------|------|--------|------|
   | 支持多账户发布 | Feature | P1 | 高 | v0.8.0 |
   | 提取平台卡片公共组件 | Refactor | P2 | 中 | v0.8.0 或未来 |
   | 完善发布中断恢复 | Enhancement | P2 | 中 | v0.8.0+ |
   | 添加发布队列持久化 | Technical Debt | P3 | 低 | Future |

3. **记录到指定位置**

   选择适当的存储位置：

   **Option A：** 如果建议较多且重要，新建文档
   ```
   docs/decisions/2026-03-19-r1-follow-up-recommendations.md
   ```

   **Option B：** 直接更新开发计划文档的"Future Work"或"后续建议"章节
   ```markdown
   ## 9. 后续建议（基于 R1 完成）

   ### v0.8.0 计划
   - R4: 支持多账户 TikTok 发布
   - R5: 提取平台卡片为通用组件
   - R6: ...

   ### Technical Debt
   - 发布队列持久化（当前使用内存队列，应改为 SQLite）
   - ...
   ```

4. **不在当前任务中执行**

   重要：建议只是记录，不应该在当前任务范围内实现。任何超出当前 R 任务的改动都被禁止，除非得到人类的明确授权。

**输出物：** 建议文档或开发计划中的"后续建议"章节

**检查清单：**
- [ ] 开发过程中的有价值观察都被记录
- [ ] 建议都被分类和优先级评估
- [ ] 建议不会被自动执行（仅记录）
- [ ] 建议文档清晰易于后续参考

---

## 5. 过程文件管理

所有过程文件必须规范存放、命名清晰、可追溯：

### 5.1 审计记录

**位置：** `docs/audit/`

**命名规则：** `YYYY-MM-DD-r{N}-audit.md`

**示例：**
- `docs/audit/2026-03-19-r1-audit.md`
- `docs/audit/2026-03-20-r2-audit.md`

**保留期：** 永久保留（项目生命周期内）

### 5.2 测试报告

**位置：** `docs/test-reports/`

**命名规则：** `YYYY-MM-DD-r{N}-test-report.md`

**示例：**
- `docs/test-reports/2026-03-19-r1-test-report.md`
- `docs/test-reports/2026-03-20-r2-test-report.md`

**保留期：** 永久保留

### 5.3 开发计划

**位置：** `docs/dev-plans/`

**命名规则：** `dev-plan-v{版本号}.md`

**示例：**
- `docs/dev-plans/dev-plan-v0.7.0.md`
- `docs/dev-plans/dev-plan-v0.8.0.md`

**变更版本：** 计划发布后，每次变更更新版本号（V1.0 → V1.1 → V1.2 等）

**保留期：** 永久保留

### 5.4 实施计划

**位置：** `docs/dev-plans/`

**命名规则：** `{YYYY-MM-DD}-r{N}-implementation-plan.md`

**示例：**
- `docs/dev-plans/2026-03-19-r1-implementation-plan.md`
- `docs/dev-plans/2026-03-20-r2-implementation-plan.md`

**保留期：** 可选；如果对后续参考有价值则保留，否则可删除

### 5.5 决策记录（ADR）

**位置：** `docs/decisions/`

**命名规则：** `ADR-{序号}-{主题}.md`

**示例：**
- `docs/decisions/ADR-001-tiktok-single-account-priority.md`
- `docs/decisions/ADR-002-webhook-fallback-strategy.md`

**何时创建：** 当做出可能影响后续决策的技术选择时

**内容结构：**
```markdown
# ADR-{序号} - {决策标题}

## 状态
Accepted / Proposed / Superseded by ADR-XXX

## 背景
为什么要做这个决策？

## 决策
我们决定：...

## 后果
正面结果：...
负面结果：...

## 替代方案（可选）
- 方案 A：...
- 方案 B：...
```

**保留期：** 永久保留

---

## 6. AI 开发者专项规则

本章节针对由 Claude Code 等 AI Agent 执行自动化开发时的额外约束。

### 6.1 开始工作前的强制检查

在开始任何编码前，AI 必须执行以下检查列表（记录在日志中）：

**检查 1：确认 git 环境**
```bash
git status                  # 结果：On branch feature/xxx, clean
git branch                  # 结果：feature/xxx
```

如果不在正确分支，**停止并报告**。

**检查 2：读取当前状态文件**
```bash
cat VERSION                 # 当前版本 → v0.6.0
grep "^##" CHANGELOG.md | head -1    # 最近发布版本
git log --oneline -1        # 最新 commit
```

**检查 3：读取相关技术规范**
- [ ] 阅读 `docs/tech-specs/architecture.md`（10分钟）
- [ ] 阅读 `docs/tech-specs/coding-standards.md`（10分钟）
- [ ] 阅读 `docs/tech-specs/dev-governance.md` 本文件（当前任务相关部分）

**检查 4：读取当前开发计划**
- [ ] 定位 `docs/dev-plans/dev-plan-v{当前版本}.md`
- [ ] 找出当前要处理的 R 任务（状态 = "Planned"，无未完成的依赖项）
- [ ] 复制该 R 任务的完整定义

**检查 5：检查前置任务**
- [ ] 如果当前 R 有依赖项，确认所有依赖项都已完成
- [ ] 查看上一个 R 任务的审计报告和测试报告，确保无 blocking issue

**检查 6：验证工作目录**
```bash
pwd                         # 结果：/sessions/.../mnt/videoeditor 或等效路径
ls -la docs/                # 结果：有 architecture.md, coding-standards.md, dev-governance.md
```

**完成标志：** 输出一份检查清单，所有项都打 ✓

示例：
```
=== Phase 1 Pre-Work Checklist ===
✓ Git status: clean, on feature/tiktok-connector
✓ VERSION: 0.6.0
✓ Latest commit: 9aa11ec (refactor: extract settings_helpers)
✓ architecture.md read ✓
✓ coding-standards.md read ✓
✓ dev-governance.md read ✓
✓ Development plan read: dev-plan-v0.7.0.md
✓ Current task: R1 (TikTok connector)
✓ No blocking dependencies
✓ Working directory verified: /sessions/.../mnt/videoeditor

Ready to proceed with Phase 1 Implementation Plan
```

### 6.2 禁止幻觉导入（No Hallucination）

AI 严禁假设某个库、函数、模块的存在。每个导入都必须通过验证：

**错误示例：**
```python
# 错误：假设 tiktok_api 库存在且包含 Client 类
from tiktok_api import Client
client = Client(api_key='...')
```

**正确做法：**
```bash
# 先验证库存在
grep "tiktok" requirements.txt
# 或
pip show tiktok-api

# 然后查看该库的文档和已有使用示例
grep -r "from tiktok" --include="*.py" modules/
grep -r "import tiktok" --include="*.py" modules/
```

**规则：**
- 如果库不在 `requirements.txt` 中，不能导入
- 如果函数 / 类未在已有代码中出现过，不能使用（除非已通过 help() 或官方文档验证）
- 如果配置项 / 常量未在 `settings.py`、`config.py` 等地方定义，不能假设其存在

**如果发现缺失的库 / 函数：**
1. 停止编码
2. 报告缺失项
3. 等待人类决定是否添加该依赖
4. 重新开始

### 6.3 禁止假设性编码（No Assumption）

AI 不能假设某个类、方法、字段已存在或有某种行为。必须通过代码扫描确认：

**错误示例：**
```python
# 假设 BasePublishConnector 中已有 _validate_video() 方法
self._validate_video(video_path)  # 可能不存在！
```

**正确做法：**
```bash
# 先查找该方法是否已存在
grep -n "_validate_video" modules/capabilities/content_publish.py

# 如果不存在，要么自己实现，要么调用已知存在的方法
grep -n "def.*validate" modules/capabilities/content_publish.py
```

**规则：**
- 在调用任何方法前，用 grep 搜索其定义位置
- 在访问任何字段前，确认该字段在 __init__ 或类定义中出现过
- 在做出任何业务逻辑假设前，在注释中明确说明假设，并等待人类确认

### 6.4 增量编写、每步验证（Incremental Coding）

代码必须分步骤编写，每步完成后立即验证：

**禁止：** 一次性写出 500 行代码，最后才运行测试

**必须：**
1. Step 1: 写 30-50 行（例如一个类的 __init__ 方法）
2. 立即运行语法检查
3. Step 2: 写下一个方法
4. 再次验证
5. ... 重复

**验证方法：**
```bash
# Python 语法检查
python3 -m py_compile path/to/file.py

# 如果有单元测试，立即运行相关测试
pytest tests/test_xxx.py::test_specific_case -v
```

### 6.5 环境一致性检查（Environment Consistency）

每次做出跨文件的改动（例如修改共享常量、改变接口签名），必须检查不会破坏其他文件：

**示例：** 在 `content_publish.py` 中添加了新的 Connector 基类方法

```bash
# 搜索该类在哪些地方被继承
grep -r "BasePublishConnector" --include="*.py" modules/

# 搜索该方法在哪些地方被调用
grep -r "\.methodname" --include="*.py" modules/

# 对每个出现的地方，确认不会因新改动而断裂
```

### 6.6 回归保护（No Regression）

任何新代码都可能破坏既有功能。必须：

1. **在添加任何新代码前，运行全量测试作为基线：**
   ```bash
   pytest tests/ -v > /tmp/baseline_test_results.txt
   # 记录当前通过数（例如 173 passed）
   ```

2. **编写并修改代码**

3. **编码完成后，再次运行全量测试：**
   ```bash
   pytest tests/ -v > /tmp/new_test_results.txt
   # 确认通过数没有减少
   ```

4. **对比测试结果：**
   ```bash
   diff /tmp/baseline_test_results.txt /tmp/new_test_results.txt
   # 应该只有新增的测试，无既有测试失败
   ```

**如果发现回归（既有测试失败）：**
1. 停止继续开发新功能
2. 定位导致失败的改动
3. 修复该改动
4. 重新运行测试直到通过
5. 继续新功能开发

---

## 7. 多 Agent 接力规则

在开发过程中可能有多个 AI Agent 或人类开发者接力完成不同阶段的工作。为了确保平稳交接，定义以下规则：

### 7.1 工作交接的信息来源

**禁止：** 通过对话内容、chat 历史、Agent 之间的消息传递交接信息

**必须：** 通过本地文件（git 仓库中的文件）交接信息

**规则：**
- 每个 Agent 开始工作前，必须从文件读取当前状态，而非询问前一个 Agent
- 每个 Agent 结束工作后，必须将所有重要信息写入文件，而非依赖对话记录
- 任何决策都必须有文档记录，不依赖"前一个 Agent 说过什么"

### 7.2 Agent 开始工作的标准流程

当一个新 Agent 接手项目时，必须依次执行：

**Step 1: 读取 VERSION**
```bash
cat VERSION  # 获知当前版本号
```

**Step 2: 阅读 CHANGELOG.md**
```bash
head -50 CHANGELOG.md  # 了解最近的改动
```

**Step 3: 查看 git log**
```bash
git log --oneline -10  # 了解最近的 commit 历史
```

**Step 4: 读取开发计划**
```bash
ls docs/dev-plans/dev-plan-v*.md  # 找到当前版本的计划
cat docs/dev-plans/dev-plan-v{当前版本}.md  # 阅读完整计划
```

**Step 5: 检查已完成的 R 任务**
```bash
ls docs/audit/  # 查看已有的审计报告
ls docs/test-reports/  # 查看已有的测试报告
```

**Step 6: 输出当前状态总结**

新 Agent 应输出一份总结文档：
```markdown
# Agent 交接状态报告

**日期：** 2026-03-20
**接手 Agent：** Claude Code (Session 2)
**前一个 Agent：** Claude Code (Session 1)

## 当前状态

- 版本：v0.6.0
- 最新 commit：abc123 (feat: add TikTok connector)
- 上一个完成的 R 任务：R1 (TikTok connector)
  - 审计报告：docs/audit/2026-03-19-r1-audit.md ✓
  - 测试报告：docs/test-reports/2026-03-19-r1-test-report.md ✓
- 当前未完成的 R 任务：R2 (发布前检查优化)

## 下一步

1. 读取 R2 的完整定义（docs/dev-plans/dev-plan-v0.7.0.md）
2. 生成 R2 的实施计划
3. 执行 Phase 2-7
```

### 7.3 Agent 结束工作的标准流程

当一个 Agent 完成一个 R 任务或迭代周期后，必须：

1. **确保所有文件都已 commit**
   ```bash
   git status  # 结果应该是 clean
   ```

2. **更新 CHANGELOG.md**
   ```bash
   cat CHANGELOG.md | head -20  # 确认本次改动已记录
   ```

3. **更新开发计划文档**
   ```bash
   grep -A 2 "R[0-9]" docs/dev-plans/dev-plan-v*.md | grep "状态"
   # 确认已完成的 R 任务状态已更新为 "Complete"
   ```

4. **生成交接总结**

   创建文件 `docs/dev-plans/{日期}-agent-handoff-summary.md`：
   ```markdown
   # Agent 交接总结

   **交接者：** Claude Code (Session 1)
   **日期：** 2026-03-19
   **完成的 R 任务：** R1

   ## 已完成

   - [x] R1 需求理解和计划
   - [x] R1 代码实现（TiktokConnector 等）
   - [x] R1 单元测试
   - [x] R1 集成测试
   - [x] R1 审计（docs/audit/2026-03-19-r1-audit.md）
   - [x] R1 测试报告（docs/test-reports/2026-03-19-r1-test-report.md）
   - [x] CHANGELOG.md 更新
   - [x] 开发计划更新

   ## 已知问题

   （如有）

   ## 下一个 Agent 应做

   1. 阅读本总结和相关文档
   2. 从 R2 开始工作
   ```

### 7.4 禁止的跨 Agent 假设

- 禁止：假设前一个 Agent 已做过某个检查
- 禁止：依赖对话中的口头约定
- 禁止：跳过标准的 Phase 1-7 流程
- 禁止：自作主张改变任务定义或范围

---

## 8. 自动化开发循环指令

当用户执行"继续开发"命令时，Claude Code 应自动执行以下循环（不需要人类的每一步都确认）：

### 8.1 循环的 13 个步骤

```
1. 读取技术规范 (architecture.md, coding-standards.md, dev-governance.md)
   ↓
2. 检查当前状态 (VERSION, CHANGELOG.md, git log)
   ↓
3. 读取开发计划 (docs/dev-plans/dev-plan-v{版本}.md)
   ↓
4. 自动领取下一个待完成任务 (状态 = "Planned", 无未完成依赖)
   ↓
5. 输出实施计划 (docs/dev-plans/{日期}-r{N}-implementation-plan.md)
   ↓
6. 等待人类确认 (继续执行 / 修改计划 / 停止)
   ↓
7. 执行 Phase 2: 代码实现 (增量编写、每步验证)
   ↓
8. 执行 Phase 3: 测试 (单元 / 集成 / 回归 / 手工)
   ↓
9. 执行 Phase 4: 审计 (生成审计报告)
   ↓
10. 执行 Phase 5: 测试报告 (生成测试报告)
    ↓
11. 执行 Phase 6: 收尾 (更新文档, commit)
    ↓
12. 执行 Phase 7: 衍生建议 (记录改进建议)
    ↓
13. 自动进入下一个任务? (检查计划中是否有未完成的 R)
    │
    ├─ YES: 返回 Step 4，开始下一个 R 任务的 Phase 1
    │
    └─ NO: 输出完成总结，等待用户下一步指令
```

### 8.2 循环的退出条件

自动循环应在以下任何情况下停止，并报告给用户：

1. **测试失败且无法自修复**
   - 症状：Phase 3 中出现 ≥ 1 个 critical/high bug，修复后仍未通过
   - 动作：报告问题详情，请求人类协助

2. **需要人类决策**
   - 架构选择（例：应该新建类还是扩展既有类）
   - 需求澄清（例：API 返回格式应该是什么）
   - 优先级调整（例：R3 应该放到下个版本吗）
   - 动作：输出决策问题，等待人类反馈

3. **所有任务已完成**
   - 症状：开发计划中所有 R 任务状态都是"Complete"
   - 动作：输出版本完成总结，建议人类审查并决定是否发布

4. **发现严重风险**
   - 症状：审计或测试中发现无法接受的问题（安全漏洞、性能风险等）
   - 动作：报告风险，暂停循环，等待人类确认下一步

5. **连续两个任务的审计结果有「高风险」项**
   - 症状：R{N} 和 R{N+1} 的审计报告中均包含高风险或不通过评级
   - 动作：报告两次审计的问题清单，请求人类 review 后再决定是否继续

6. **需要新增外部依赖**
   - 症状：当前任务需要引入 requirements.txt 中不存在的第三方库
   - 动作：报告依赖名称、用途、版本、许可证，等待人类确认后再安装

### 8.3 循环执行中的日志

每个循环的执行应产生一份详细的日志（追加到 `docs/.development-log.md`）：

```markdown
## 2026-03-19 Session 1

### R1: TikTok Connector
- Phase 1 ✓ (14:00-14:20)
- Phase 2 ✓ (14:20-15:30)  [implemented 480 lines]
- Phase 3 ✓ (15:30-16:00)  [173/173 tests passed]
- Phase 4 ✓ (16:00-16:30)  [audit passed, A rating]
- Phase 5 ✓ (16:30-16:45)  [test report generated]
- Phase 6 ✓ (16:45-16:50)  [commit + CHANGELOG]
- Phase 7 ✓ (16:50-17:00)  [recommendations documented]

### R2: Publish Prep Enhancement
- Phase 1 ✓ (17:00-17:30)  [implementation plan generated, awaiting confirmation]
- 暂停：等待人类确认是否继续 R2
```

---

## 9. 与其他文档的关系

本项目的技术规范分为三个核心文档，相互关联但职责清晰：

| 文档 | 位置 | 职责 | 内容 |
|-----|------|------|------|
| **architecture.md** | `docs/tech-specs/` | "系统长什么样" | 模块划分、依赖关系、数据流、公开接口 |
| **coding-standards.md** | `docs/tech-specs/` | "代码怎么写" | 命名规范、注释规范、异常处理、自检清单 |
| **dev-governance.md**（本文件） | `docs/tech-specs/` | "开发怎么走" | 版本管理、计划管理、迭代流程、文件管理、AI 规则 |

**使用场景：**

- 需要理解系统架构？→ 读 architecture.md
- 需要知道代码应该怎么写？→ 读 coding-standards.md
- 需要了解开发流程和规范？→ 读 dev-governance.md
- 需要执行一个迭代周期？→ 按照 dev-governance.md 第 4 章的 7 个 Phase 执行
- 需要审查别人的代码？→ 参考 coding-standards.md 中的自检清单
- 新开发者入职？→ 按顺序读这三个文档

---

## 10. 修订说明

**文档版本：** v1.0
**创建日期：** 2026-03-19
**作者：** Claude Code
**状态：** Active

**修订历史：**

| 版本 | 日期 | 变更 | 作者 |
|-----|------|------|------|
| v1.0 | 2026-03-19 | 初版发布 | Claude Code |

**下一次修订计划：**
- 在 v0.7.0 或 v0.8.0 完成后评估流程是否需要调整
- 收集开发者反馈，优化 Phase 流程

---

## 11. 附录：常用命令速查

### 11.1 版本和状态检查

```bash
# 查看当前版本
cat VERSION

# 查看最近的改动
head -30 CHANGELOG.md
git log --oneline -10

# 查看当前分支和状态
git status
git branch -v
```

### 11.2 开发计划管理

```bash
# 列出所有开发计划
ls docs/dev-plans/dev-plan-v*.md

# 查看当前版本计划
cat docs/dev-plans/dev-plan-v0.7.0.md | grep -A 20 "^## 3. 任务列表"

# 查看特定 R 任务的定义
grep -A 30 "^### R1:" docs/dev-plans/dev-plan-v0.7.0.md
```

### 11.3 测试和验证

```bash
# 运行全量测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_content_publish.py::TestTiktokConnector -v

# 运行语法检查
python3 -m py_compile modules/capabilities/content_publish.py

# 查看测试覆盖率
pytest tests/ --cov=modules/ --cov-report=html
```

### 11.4 提交和 Tag 管理

```bash
# 查看最近的 commit
git log --oneline -5

# 创建 commit
git add .
git commit -m "feat(scope): description"

# 创建 tag
git tag -a v0.7.0 -m "Release v0.7.0"
git push origin v0.7.0

# 查看所有 tag
git tag -l
git show v0.7.0
```

### 11.5 文件管理

```bash
# 查看审计报告
ls docs/audit/

# 查看测试报告
ls docs/test-reports/

# 查看决策记录
ls docs/decisions/

# 全文搜索
grep -r "pattern" --include="*.py" --include="*.md" modules/ docs/
```

---

## 12. 自动化开发基础设施（Automation Infrastructure）

> 本章定义 AI 自动化开发的扩展基础设施，补充第 4 章的七阶段流程。
> v2.0 升级新增，覆盖：智能启动、阶段门禁体系、门禁失败追踪、阶段回滚、无任务空闲循环、S 型分支简化、文件保护层级、TODO_NEXT.md 管理。

### 12.1 快速启动命令（Smart Start）

**触发词：** "开始开发" / "继续开发" / "继续" / "自动开发"

收到此命令后，执行以下自动检测流程：

```
步骤 1: 读取 VERSION 文件，获取当前版本号
步骤 2: 读取 TODO_NEXT.md，扫描任务完成状态
        └── 不存在 → 降级：扫描 docs/dev-plans/ 定位计划文件
步骤 3: 读取 git log --oneline -20
步骤 4: 自动判定当前应该做什么：
        ├── 有未完成任务 → 从最小未完成版本号的第一个 Planned 任务开始
        ├── 版本未发布 → 执行版本收尾
        ├── 有下一个版本计划 → 开始下一版本
        └── 全部完成 → 等待用户指示
步骤 5: 读取 docs/.gate-failures.json（如存在），检查遗留失败记录
步骤 6: 轻量合规快检（四文件存在性、ci_verify.sh 可执行、VERSION 与 CHANGELOG 一致）
步骤 7: 输出检测结果摘要（不超过 10 行）
步骤 8: 进入自动连续开发模式
```

**查询命令：** "查看当前进度" → 仅输出检测摘要，不进入开发模式

### 12.2 阶段门禁体系（Gate System）

> 每个 Phase 都遵循统一的三段式结构：**① 规范输入（读什么）→ ② 执行（做什么）→ ③ 阶段门禁（检查什么）**。
> 只有当前阶段的门禁通过后，才能自动进入下一阶段。

#### 12.2.1 Phase 3 ③ — Part A：自动化门禁

在第 4.3 节测试完成后，必须通过以下自动化检查：

```bash
# 实际可运行的命令（不允许占位符）
pytest tests/ -v --tb=short              # 全量测试
python3 -m py_compile modules/**/*.py    # 语法检查（按需）
bash scripts/ci_verify.sh               # 整合脚本（阶段 5 构建后可用）
```

**门禁阈值：**

| 检查项 | 通过标准 | 已知豁免 |
|--------|---------|---------|
| pytest | 不允许引入新的测试失败 | 无 |
| py_compile | 0 errors | 无 |
| ci_verify.sh | 退出码 0 | 脚本不存在时跳过 |

Part A 全部通过 → 自动进入 Phase 4。
Part A 失败 → 记录到 `docs/.gate-failures.json`（§12.3）→ 修复 → 重跑。

#### 12.2.2 Phase 4 ③ — Part B/C/D 门禁

在第 4.4 节审计完成后，必须通过以下三部分门禁：

**Part B：技术规范合规审计**

对照 coding-standards.md 逐项自检（仅检查本次变更涉及的条目）：

| 检查项 | 检查内容 |
|--------|---------|
| 分层边界 | 是否违反了分层架构的依赖规则？ |
| 目录结构 | 新文件是否放在正确目录下？ |
| 命名规范 | 表名、API 路径、模块名是否符合命名规则？ |
| 安全规范 | 机密是否硬编码？SQL 是否参数化？ |
| 测试规范 | 新功能是否有对应测试？ |

每项标注：✅ 合规 / ❌ 违规 / ➖ 不涉及

> **对抗性审计原则**：审计时从"找到至少 1 个违规点"的视角出发。如果结果为"0 违规"，额外输出最可能违规的 3 个点及其合规原因。
> **自审标注**：如果 Phase 2 和 Phase 4 在同一 session 完成，标注为 `审计模式: 自审（同 session）`。

**Part C：验收标准逐条核对**

1. 重新读取开发计划中的验收标准
2. 逐条检查，标注：✅ 已满足 / ❌ 未满足 / ⚠️ 部分满足
3. 存在 ❌ 必须先修复

**Part D：实施一致性检查**

1. 文件一致性：计划 vs 实际修改的文件
2. 范围一致性：是否超出或遗漏了任务范围？
3. 禁止文件事后验证：`git diff --name-only` 与 §12.7 文件保护层级比对

**审计门禁结论：**
- ✅ 通过 — Part B/C/D 全部通过
- ⚠️ 有条件通过 — 存在合理偏差
- ❌ 未通过 — 任何一个 Part 存在未解决的 ❌

### 12.3 门禁失败追踪（Gate Failure Tracking）

**文件：** `docs/.gate-failures.json`

**格式：**
```json
{
  "task_version": "v0.11.1",
  "failures": [
    {
      "phase": "Phase 3",
      "gate": "Part A",
      "count": 2,
      "last_failure": "2026-03-20T15:30:00",
      "last_error": "test_workflow_init_project FAILED - AssertionError",
      "attempts": [
        {"timestamp": "2026-03-20T15:00:00", "error_summary": "..."},
        {"timestamp": "2026-03-20T15:30:00", "error_summary": "..."}
      ]
    }
  ]
}
```

**规则：**
- 每次门禁失败时写入记录
- 连续 3 次相似失败 → 触发失败模式分析，调整修复策略
- **累计 10 次失败 → 停止等待用户介入**
- 门禁通过后清除对应记录
- 跨 session 时从文件读取，不依赖上下文记忆

### 12.4 阶段回滚流程（Phase Rollback）

当后续阶段门禁揭示前序阶段问题时，允许回退：

| 当前阶段 | 触发条件 | 回退目标 | 回退后动作 |
|---------|---------|---------|-----------|
| Phase 3 | Part A 累计 10 次失败 | Phase 2 | 分析根因，修复代码，从 Phase 3 重走 |
| Phase 4 | Part B/C 发现代码缺陷 | Phase 2 | 修复代码，从 Phase 3 重走 |
| Phase 4 | Part D 发现计划偏差过大 | Phase 1 | 修订实施计划，从 Phase 2 重走 |
| Phase 5 | 测试数据与审计不一致 | Phase 3 | 重新运行测试 |
| Phase 6 | 版本号一致性失败 | Phase 6 ② | 修正版本号，重新执行收尾 |

**回滚限制：**
- 单次任务累计回退上限：10 次
- 回退时 commit 当前状态：`rollback(vX.Y.Z): Phase N → Phase M - <原因>`
- 回退计数在 Phase 6 汇报中记录

### 12.5 无任务空闲循环（Idle Scan-Test-Fix Cycle）

当所有 Planned 任务完成后，不直接停止，而是进入循环：

```
Step 1: PRD/开发计划 Gap 扫描
  ↓ 有 Gap → 生成任务，回到七阶段流程
  ↓ 无 Gap → 进入 Step 2
Step 2: 全量测试（按 testing-strategy.md 执行）
  ↓ 生成测试报告: docs/versions/idle-test-report-vX.Y.Z-{a}.md
Step 3: 问题分类
  ↓ 计划内 Bug → Bug 修复清单: docs/dev-plans/bugfix-list-vX.Y.Z-{a}.md
  ↓ 计划外建议 → WISHLIST.md（执行去重检测）
Step 4: 判定
  ↓ Bug 修复清单有条目 → 执行修复，回到 Step 2
  ↓ Bug 修复清单为空 → 停止，等待用户介入
```

**问题分类标准：**
- 能在当前 PRD/dev-plan 中找到对应需求 → 计划内修复
- 超出当前范围 → 计划外建议（写入 WISHLIST.md）
- 边界模糊时 → 优先归入计划内修复

### 12.6 S 型项目简化分支体系（三层分支）

> 本项目当前采用此简化分支体系（项目规模 L 但无线上用户、单 Agent 开发）。

**三层分支总览：**

```
main                          ← 主干版本（受保护，禁止直接提交）
  └── test                    ← 测试/集成分支（从 main 创建）
        └── dev-{a}           ← 开发分支（a = 开发者/Agent 标识）
```

**各分支规则：**

| 分支 | 命名 | 职责 | 谁可写入 |
|------|------|------|---------|
| main | `main` | 主干稳定版本 | 仅从 test 合入 |
| test | `test` | 测试与集成 | 仅从 dev-{a} 合入 |
| dev-{a} | `dev-agent1` | 实际开发 | 对应开发者/Agent |

**硬性规则：**
1. 禁止在 main 上直接开发
2. 禁止在 test 上直接开发
3. 合并前仍需产出简化版合并报告（变更摘要+测试状态）
4. **升级条件**：项目对外发布 / 引入多 Agent 并行 / 规模增长时，必须升级到五层分支体系

**初始化命令：**
```bash
git checkout main
git checkout -b test && git push -u origin test
git checkout -b dev-agent1 && git push -u origin dev-agent1
```

### 12.7 文件保护层级（File Protection Tiers）

#### Tier 1：绝对禁止

以下文件在任何情况下都**不允许 AI 开发者修改**：

| 文件/路径 | 说明 |
|-----------|------|
| `docs/tech-specs/dev-governance.md` | 开发治理流程（本文件） |
| `docs/tech-specs/coding-standards.md` | 编码标准规范 |
| `docs/tech-specs/architecture.md` | 系统架构规范 |
| `docs/tech-specs/testing-strategy.md` | 测试策略规范 |

**理由：** 这些文件是"规则本身"。执行者不可修改规则。

> **升级流程豁免**：执行 dev-workflow-upgrade 升级流程期间，Tier 1 保护暂不生效。升级完成后正式启用。

#### Tier 2：封板后禁止

| 文件/路径模式 | 封板条件 |
|--------------|---------|
| `docs/dev-plans/dev-plan-vX.Y.md` | 所有任务状态为 Sealed |
| `docs/versions/task-report-vX.Y.Z.md` | 文件创建即封板 |
| `docs/versions/audit-report-vX.Y.Z.md` | 文件创建即封板 |
| `docs/versions/test-report-vX.Y.Z.md` | 文件创建即封板 |

#### Tier 3：条件保护

以下文件仅当任务定义中**明确列出**时才允许修改：

| 文件/路径模式 | 说明 |
|--------------|------|
| `scripts/ci_verify.sh` | 整合检查脚本 |
| `requirements.txt` | Python 依赖 |
| `.env.example` | 环境变量模板 |

**违规处理：**
- Phase 1 门禁预检：预计修改文件 vs 保护清单比对
- Phase 4 Part D 事后验证：实际修改文件 vs 保护清单比对
- 命中 Tier 1/2 → 立即停止

### 12.8 TODO_NEXT.md 管理规范

**定位：** 开发计划的轻量状态视图，Smart Start（§12.1）首先读取此文件定位进度。

**格式：**
```markdown
# TODO_NEXT — 开发进度快照

> 自动生成于 YYYY-MM-DD HH:MM，数据来源：docs/dev-plans/dev-plan-vX.Y.md

## 当前版本：vX.Y

## 下一个待执行任务

- **任务版本号：** vX.Y.Z
- **任务名称：** {任务名称}
- **所属功能项：** vX.Y.0 — {功能项名称}
- **开发计划位置：** `docs/dev-plans/dev-plan-vX.Y.md` → 任务 vX.Y.Z

## 任务状态总览

| 任务版本号 | 任务名称 | 状态 | 完成日期 |
|----------|--------|------|---------|
| vX.Y.1 | 任务1 | ✅ Completed | 2026-03-20 |
| vX.Y.2 | 任务2 | 🔲 Planned | — |

## 版本进度

- 已完成：N / 总数 任务
- VERSION 文件当前值：X.Y.Z
```

**更新规则：**
- 每完成一个任务的 Phase 6 收尾时，整体覆写更新
- 数据来源：从 `docs/dev-plans/dev-plan-vX.Y.md` 提取
- 与开发计划不一致时，以 dev-plan 为准

### 12.9 自动连续判定（Phase 7 后触发）

Phase 7 完成后自动判定是否继续下一个任务：

**自动继续条件（全部满足）：**
1. Phase 4 审计门禁为 ✅ 或 ⚠️
2. Phase 6 汇报第 9 项为"建议继续"
3. 当前任务不是功能项的最后一个
4. 未触发任何停止条件（第 4 章停止条件）

**边界处理：**
- 功能项完成 → 全量回归 → 更新 VERSION → 自动进入下一功能项
- 版本完成 → 先执行 §12.5 空闲循环 → 大版本封板检查 → 停止等待确认

---

## 13. 修订记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-03-19 | 初版，七阶段开发流程、分支策略、文件管理、多 Agent 协议 |
| v2.0 | 2026-03-20 | 新增第 12 章自动化基础设施：智能启动、Part A/B/C/D 门禁、门禁追踪、阶段回滚、空闲循环、S 型三层分支、文件保护层级、TODO_NEXT 管理、自动连续判定 |

---

**文档结束**
