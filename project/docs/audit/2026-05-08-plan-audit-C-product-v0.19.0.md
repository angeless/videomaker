# dev-plan-v0.19.0 计划审计 — 维度 C（产品对齐）

> **审计对象**: `project/docs/dev-plans/dev-plan-v0.19.0.md` V1.0（新增 Feature L/M/N，共 22 个任务）
> **审计日期**: 2026-05-08
> **审计维度**: C — 产品对齐（用户报告覆盖率 / 需求理解 / 优先级 / 用户价值完整性 / 非功能需求）
> **审计依据**:
> - 用户原始报告（2026-05-08，"全面产品功能测试"）
> - `project/docs/tech-specs/product-standards.md`（§3、§4、§7、§9、§11）
> - `videoeditor/CLAUDE.md`（产品定位）
> - 实际代码核查（`core_mixin.py` / `vlm_adapter.py` / `_vlm_claude.py` / `settings_service.py` / `router/index.js` / `AppNav.vue` / `AssetDetailPanel.vue` / `OnboardingModal.vue` / `LocationHealthPanel2.vue`）
> **审计人**: 独立子 Agent（plan-audit 维度 C）
> **结论**: **条件通过 — 需修正后方可进入 Wave 1**
>
> 共发现 **3 项 Critical（必修）**、**6 项 High（应修）**、**5 项 Medium（建议修）**、**3 项 Low（记录）**

---

## 一、总体评价

L/M/N 三个 Feature 在**产品意图诊断**上是准确的（标签器适配器断裂、UI 文案过度承诺、导航命名碰撞），且 P0/P1 总体分配合理。然而审计发现：

1. **覆盖完整性问题（C1）**：用户报告中的"指纹"概念错配（pHash 去重 vs LLM 标签）被 L/M/N **完全回避**，Library 健康面板仍然显示"有指纹"统计卡（`LocationHealthPanel2.vue:18`），用户的认知错配在 v0.19.0 后**仍然存在**。
2. **跨 Feature 职责重叠 + 实现链路断裂（C2）**：H3（VLM settings → adapter env var bridge）与 L1-L7（library 标签器接 Anthropic）**共用同一份 settings_service 桥接逻辑**，但当前 settings_service.py:604 写的是 `os.environ["ANTHROPIC_API_KEY"]`，而 Claude vision adapter 读的是 `VIDEOEDITOR_CLAUDE_API_KEY`（`_vlm_claude.py:19`）。**L 系列做完后 library 标签器能跑（因为它读 ANTHROPIC_API_KEY），但 review_engine 的 Claude VLM 仍然读不到 key**，需要 H3 才完整。计划没有把这件事讲清楚，存在"L 完成 ≠ 用户感知到 AI 工作"的风险。
3. **优先级倒置（C3）**：用户报告时第一句是"产品的功能布局混乱"，L/M（标签问题）反而被列为 P0、N（导航重构）被列为 P1。从用户感受顺序看应当**反过来**或**至少 N 也是 P0**。
4. **M3 onboarding 引导对当前活跃用户无效（CX3）**：M3 假设"首次启动"才看到，但用户已经在使用产品（不是第一次）。M3 对当前提报问题的用户**完全不可见**，他们只能看到 M2 横幅。
5. **VLMResponse schema 与 L2 验收条件不兼容（H1）**：L2 要求"mock 三种 adapter 返回 schema 一致"，但当前 `VLMResponse` 只有 `text: str` 单字段，没有结构化 JSON 输出能力，需新增一层 `_call_vlm_json` 把 text → 解析为 dict，且每家 provider 的 prompt 工程不同。L 边界声明"本次不改 prompt 工程"与此矛盾。

---

## 二、发现汇总表

| # | 检测项 | 严重度 | 类型 | 描述 |
|---|---|---|---|---|
| **C1** | CX5（用户期望未盖到） | 🔴 Critical | 概念错配 | 用户提到"指纹"，UI 仍存在"有指纹"统计；L/M/N 不回应、不解释 pHash vs LLM tag 区别 |
| **C2** | CX4 + 跨 Feature 完整性 | 🔴 Critical | 实现链路断裂 | L 系列依赖 settings 桥接，但当前 H3 才修桥接；L 完成而 H3 未完成时，review_engine VLM 仍读不到 key |
| **C3** | CX2 | 🔴 Critical | 优先级倒置 | 用户感知顺序：先布局混乱（N）后标签错（L/M）。计划反而 N=P1 / L,M=P0 |
| H1 | C2（需求理解） | 🟠 High | 验收不可达 | L2 要求"adapter schema 一致"，但 VLMResponse 只有 text 字段；JSON 解析层、prompt 适配未设计 |
| H2 | CX3 | 🟠 High | 用户价值缺失 | M3 onboarding 对已激活用户不可见；提报用户无法被 M3 触达 |
| H3 | C4（前后端衔接） | 🟠 High | 完整性 | L7 加 `llm_status` 字段后，前端没有任何任务消费这个字段（M2 横幅只判定"未启用"，不区分 auth_failed / rate_limited） |
| H4 | C5（非功能） | 🟠 High | 非功能漏点 | 横幅 a11y（aria-live）/ Anthropic key 安全存储升级（当前明文存 settings.json）/ Claude 视觉成本风险 — 对策段未谈用户层面 |
| H5 | C1（覆盖率） | 🟠 High | 衍生发现遗漏 | 用户提到"全部修"，但**embedding/语义搜索**（`_call_openai_embedding` line 1024、1055、1067、1212）在 Anthropic-only 环境下也无法工作 — L1-L7 范围未含 embedding |
| H6 | CX1（80/20） | 🟠 High | 范围不全 | `_vision_enrich_tags`（line 352）也只读 OPENAI_API_KEY；不在 L 范围内 → "AI 标签未启用"横幅会判定为"已启用"但 vision_enrich 仍走死路径 |
| M1 | C2 | 🟡 Medium | 文案不一致 | M2 横幅文案"AI 标签未启用"vs M6 要求 grep "AI 场景\|AI 描述\|AI 标签" = 0 — 横幅自身就出现"AI 标签"字眼，逻辑环 |
| M2 | C5 | 🟡 Medium | 性能未谈 | CLIP 模型加载是冷启动 5-15s，Library 横幅依赖 `/api/library/health` — 没说明此端点是否触发模型加载 |
| M3 | C3 | 🟡 Medium | 优先级判据 | M3 加 onboarding step 是 P0；M2 加横幅也是 P0；二者粒度差距大（M3 跨多步、M2 单组件），需明确分离优先级 |
| M4 | C5 | 🟡 Medium | 隐私通知缺失 | 用户从"未启用"切到"启用"时，会发送本地素材 keyframe 到 OpenAI/Anthropic 云端 — 没要求用 L5 hint 或 M3 step 给出**数据外发**告知 |
| M5 | CX5 | 🟡 Medium | 概念错配延伸 | M1 标签来源徽章用 `heuristic` / `llm:gpt-*` / `llm:claude-*` 字面值 — 终端用户不懂 "heuristic"；需要中文显示如"启发式（无 AI）" |
| L1 | C4 | 🟢 Low | 验收宽松 | L5 验收"`_meta.model_version` ≠ `heuristic_only`"过弱，未含"用户在 UI 上看到这个变化"的端到端 |
| L2 | CX1 | 🟢 Low | 范围说明 | "不做边界"未列入 v0.20 / WISHLIST 后续；用户期望可能漂到下版本 |
| L3 | C5 | 🟢 Low | 错误码本地化 | L4 分类错误（auth/rate_limit/network/parse）— 这些英文错误码到 UI 后是否有中文文案，未在任何任务中定义 |

---

## 三、Critical 详情

### C1 — 概念错配未被 L/M/N 解决（CX5）

**用户原话**：
> "素材指纹和标签打的还是不对，可能没有实际调用 LLM？"

**用户的心智模型**：用户把"指纹"和"标签"并列，**实际是把**"看到的两件事"放在一起——
- "指纹"= UI 上看到的"有指纹"统计卡（`LocationHealthPanel2.vue:18` "有指纹" / `:17` `with_content_fingerprint`）
- "标签"= AssetDetailPanel 的"语义标签"区块（`AssetDetailPanel.vue:68`）

**实际后端语义**：
- `content_fingerprint`：`fingerprint.py:99-117` SimHash + DCT pHash，**纯视觉去重**，与 LLM 完全无关
- `structured_tags`：`core_mixin.py:1461` `_llm_structured_tags`，**LLM 文本生成**，与去重无关

**L/M/N 对此问题的处理**：**完全回避**。
- L 系列只动 LLM 标签链路
- M 系列加横幅、徽章、文案修订 — **没有触及"指纹"二字**
- N 系列只重构路由

**后果**：
- 用户在 v0.19.0 完成后看到 Library 仍然写"有指纹 X / 总素材 Y"，且没有任何说明此"指纹"≠ LLM 标签
- 用户下次再提"指纹打的不对" — 但这是 pHash 算法，与 v0.19.0 修的所有内容无关
- 对话本质：**用户看到的两个独立功能（去重 + 标签）被他归并为同一个问题，计划把这两件事拆分修了，但没有告知用户它们是两件事**

**修正建议**：
1. **新增 M8（P0）**：在 `LocationHealthPanel2.vue` 把"有指纹"改为"已计算去重码"或"重复检测就绪"；hover tooltip 明确说"用于检测重复素材，与 AI 标签无关"
2. **新增 M9（P1）**：在 LibraryView 导览/帮助里加一段"什么是去重指纹 vs AI 标签"说明（< 100 字）
3. 在计划文档"M 边界"段加一行：**承认用户口语中"指纹"被误用，本计划假定用户实际指 LLM 标签链路**

### C2 — L 与 H3 链路断裂（CX4）

**实证**：
- `settings_service.py:604`：UI 设置 anthropic_api_key 后，写 `os.environ["ANTHROPIC_API_KEY"]`
- `_vlm_claude.py:19`：`API_KEY_ENV = "VIDEOEDITOR_CLAUDE_API_KEY"`
- `_vlm_claude.py:33`：`is_available()` 只查 `VIDEOEDITOR_CLAUDE_API_KEY`

**结论**：当前 settings UI 设的 anthropic key **完全不能驱动** review_engine 的 Claude vision adapter。这是 v0.17 遗留的桥接断裂。

**L 系列做完后**：
- ✅ Library 标签器（直接读 `os.environ["ANTHROPIC_API_KEY"]`）能用
- ❌ Review engine（通过 `vlm_adapter.get_vlm_adapter("claude")`）仍不能用 — 因为读的是 `VIDEOEDITOR_CLAUDE_API_KEY`

**H3 描述**："VLM settings → adapter env var 桥接完善（v0.17 遗留）"——这才是修桥接的任务。

**问题**：
- L1-L7 在 Wave 2，H3 在 Wave 3 — **L 和 H3 之间存在隐式依赖**，但计划里没有标注
- 如果只发布 Wave 2 截止时的版本，会出现"library 标签真在用 LLM 了，但 VLM review 还是没反应" — 用户感知会**自相矛盾**
- L7 的 `llm_status` 字段是 library health，没有覆盖 review_engine VLM 健康，无法暴露这个矛盾

**修正建议**：
1. **将 H3 提到 Wave 2，与 L1-L7 同 Wave 完成**（L 边界写"不动 review_engine vlm_adapter 用法"，但桥接是基础设施层，必须同步）
2. 在 Risk 表加一条："L 完成而 H3 未完成时，用户体验自相矛盾（library 用 LLM、review 不用）→ Wave 2 必须把 H3 一并发"
3. 把 settings_service.py:604 的写法改为**同时写两个 env**：`ANTHROPIC_API_KEY` + `VIDEOEDITOR_CLAUDE_API_KEY`（H3 主体）

### C3 — 优先级与用户感受顺序倒置（CX2）

**用户原话顺序**：
> "我目前看到的两个大的问题：
> 1. **产品的功能布局混乱**
> 2. 素材指纹和标签打的还是不对"

**用户列了两件事，第一件是布局，第二件是标签**。从产品规范 §3.1 "用户场景到功能"看，**用户感受到的痛点强弱顺序就是优先级顺序**。

**计划当前安排**：
- L（标签）= P0
- M（标签 UI）= P0
- N（导航）= P1

**矛盾**：
- 用户先列"布局" → 应当 P0
- 用户后列"标签" → 应当 P1（或与布局并列 P0）
- 计划相反

**反方论据**（值得权衡）：
- L+M 解决信任问题（用户怀疑"AI 没在工作"）— 这是品牌信任层，损耗最深
- N 是结构问题，用户能"绕过去"（找到入口就行）
- 从修复成本看，N 改路由 + redirect 是低成本，可推迟

**取舍建议**：
- **方案 A（保守）**：维持 L/M=P0，但把 N 升至 P0 — Wave 1 同时启动**3 个 P0**
- **方案 B（激进）**：把 N 至少部分前置到 Wave 1（仅 N1-N5 即 4 项核心 path 改造，无 i18n / E2E 部分）
- **方案 C（明确告知）**：维持现状，但在文档里**明确告知用户**"我们识别到您的两个痛点，因为信任问题修复路径长，先做 L/M；N 在 Wave 4。如果你更介意布局，我们可以反过来" — 让用户拍板

**任一方案都比"默认 N=P1 不解释"更符合 product-standards §9.2「可以建议，不能替用户拍板」**

---

## 四、High 详情

### H1 — L2 验收"adapter schema 一致"在当前 VLM 接口下不可达

**实证**：
- `vlm_adapter.py:22-29`：`VLMResponse` 只有 `text: str` / `model` / `latency_ms` / `tokens_used`
- 没有 JSON schema 输出能力
- L2 要求 `_call_vlm_json()` 抽象层 — 这意味着需要：
  - 新增 prompt 强制 JSON 输出
  - 添加 JSON 解析层 + 容错（OpenAI 支持 `response_format`，Claude 不支持，需 prompt 强约束 + 后处理）
  - 各 provider 的 JSON 失败率不同 → 解析降级路径

**矛盾**：L 边界写"本次不改 prompt 工程"，但 `_call_openai_json` 现在的 prompt 是为 OpenAI tuned 的（line 1502-1525），换 Claude 必须改 prompt（用 `<json>` 标签或额外 system message）。

**建议**：
- 修订 L 边界："prompt 适配（per-provider）属于 L2 范围内的 minimal change，但**结构化标签 schema 不变**"
- 增加 L8（P0）：定义 `_call_vlm_json` 接口契约（输入 messages、images、要求 JSON schema；输出 dict + provider/model 信息）— 否则 L2 无法启动

### H2 — M3 onboarding 对当前活跃用户不可见（CX3）

**实证**：
- `OnboardingModal.vue:1-100`：组件挂载条件 `appStore.showOnboardingWizard`
- `app.js:138`：`if (!prefsStore.uiSettings.onboarding_completed) prefsStore.showOnboardingWizard = true`
- 已激活用户 `onboarding_completed = true`，**永远看不到 M3**

**当前提报问题的用户**（已经在用产品）：
- 不会看到 M3 的"API Key 配置引导"step
- 只会看到 M2 横幅 — M2 才是真入口
- M3 对当前用户群体**价值为 0**，是给未来新用户准备的

**判断**：M3 是"未来用户友好"的优化，不是修复当前用户痛点。**M3 不该 P0**，应降为 P1 或 P2。

**修正建议**：
- M3 优先级降为 P1
- 同时新增 M3.5（P0）：在已激活用户的 Library 横幅 click 后，弹出**和 onboarding step 同样内容**的弹窗（不依赖 onboarding_completed 状态）— 这才是当前用户能感知的入口
- 或者：在 SettingsView 顶部加"如何配置 AI" tooltip（永久可见）

### H3 — L7 字段没有前端消费者

**实证**：
- L7 加 `/api/library/health` 字段 `{llm_status: ok|missing_key|auth_failed|rate_limited|...}`
- M2 验收："未设 key 时进 Library 看到横幅；设 key 后横幅消失"
- M2 没有要求"auth_failed 时显示『密钥无效』、rate_limited 时显示『超出额度』"

**结果**：L7 后端做了细致分类，前端只用粗判定（有 key/无 key），细分类**白做**。

**修正建议**：
- 修订 M2 验收：横幅根据 `llm_status` 显示不同文案：
  - `missing_key` → "未配置 AI 服务密钥"
  - `auth_failed` → "AI 密钥无效或已过期"
  - `rate_limited` → "AI 调用超出额度"
  - `network_error` → "AI 服务暂时不可达"
- 或新增 M2.5（P0）：apiStore 错误归因层把 L7 字段映射到具体 toast

### H4 — 非功能需求缺位（C5）

| 维度 | 当前覆盖 | 缺失 |
|---|---|---|
| 性能 | 无 | CLIP 模型加载 5-15s 冷启动；library health 是否触发？需声明"health 调用不加载模型" |
| 安全 | 无 | Anthropic key 当前明文存 settings.json — 升级到 keychain 不在范围 |
| 可访问性 | 无 | M2 横幅没有 aria-live / role=alert；M1 徽章没有 aria-label |
| 隐私 | 无 | 启用 LLM 后会**外发本地素材 keyframe** — 没有要求做"数据外发提醒" |
| 成本 | Risk 表提到（限 keyframes 数从 3→2） | 用户层面没有"本次扫描预计花费 X 美元"提示 |

**修正建议**：在 L4（错误分类）+ L5（hint 修订）+ M2（横幅）/ M3（step）任务里**显式加非功能要求**，至少：
- M2 横幅含 `role="status" aria-live="polite"`
- L5 hint 加"本服务会上传素材关键帧到 [provider]，请知悉"
- L7 health 端点加 `cold_start_estimated_seconds` 字段

### H5 — Embedding/语义搜索未在 L 范围（C1）

**实证**：
- `core_mixin.py:1024` `_call_openai_embedding`
- `core_mixin.py:1055/1067/1212` 是 embedding 调用点，仅 OPENAI_API_KEY
- L 系列 7 个任务**完全没提 embedding**

**用户感受**：
- 用户搜素材（如"日落"）依赖 embedding；Anthropic-only 环境下搜索功能仍然失效
- 但 L 系列只修标签，搜索框还是"搜不到"

**判断**：用户说"全部修"，embedding 也是"AI 没在工作"的一部分。

**修正建议**：
- 新增 L9（P0 / P1）：embedding 也支持 Anthropic（Claude 没有 embedding API → 需要 fallback 到本地 sentence-transformers，或明确告知"语义搜索需 OpenAI"）
- 或在 M 系列加文案："语义搜索仅 OpenAI 支持"

### H6 — `_vision_enrich_tags` 也是 OpenAI-only（CX1 80/20）

**实证**：
- `core_mixin.py:352-394` `_vision_enrich_tags`：硬编码 `import openai` + `OPENAI_API_KEY`
- 这是另一条 vision tag 路径，与 `_llm_structured_tags` 平行
- L 系列没有提到这条

**结果**：L1 让 `_llm_tagging_enabled` 接受 Anthropic key 后，`_vision_enrich_enabled`（line 192）**依然只看 OPENAI_API_KEY**。Anthropic-only 用户：
- ✅ structured_tags 走 Claude 工作
- ❌ vision_enrich tags 仍 fallback 为 {}

**修正建议**：把 `_vision_enrich_*` 也纳入 L2 抽象层，或在 L 边界明确"vision_enrich 暂不支持 Anthropic，下版本（v0.20）补"

---

## 五、Medium 详情

### M1 — M2 横幅文案与 M6 grep 互冲

**矛盾**：
- M2："Library 顶部'AI 标签未启用'横幅"
- M6："grep `AI 场景|AI 描述|AI 标签` 在未限定 LLM 的上下文 = 0"

横幅本身就含"AI 标签"四字 — M6 grep 会命中横幅文案。

**修正建议**：M6 加白名单："横幅、徽章、settings hint 例外"，或修订 M2 文案为"智能标签未启用"（避开 "AI 标签"）

### M2 — `/api/library/health` 性能行为未声明

CLIP 模型加载是 5-15s，Library 页面挂载时调 health 是否触发模型预热？计划没有要求"health 是 lazy-only check"。

**修正建议**：L7 加验收"health 端点 99% 响应 < 200ms，不触发模型加载"

### M3 — M3 vs M2 粒度差距

M2 = 单组件加横幅（0.5-1 天）
M3 = onboarding 加 step（涉及 modal 步骤数变化、preferences 状态、E2E 测试，2-3 天）

二者同列 P0 / Wave 1，量级不一致。**修正建议**：M3 拆为 M3a（添加 step 静态 UI / 0.5 天）+ M3b（联动 ingest / 1 天）+ M3c（E2E / 0.5 天），或整体降到 Wave 2。

### M4 — 隐私告知缺失

用户首次启用 LLM 时，会把本地素材关键帧（base64 data URL）发到云端。**当前没有任何 step / hint / banner 告知此事**。

**修正建议**：
- L5 hint 加："本服务会上传素材关键帧到 OpenAI/Anthropic，请知悉"
- M3 onboarding step 显式确认"我了解上传素材"（隐私 checkbox）
- M2 横幅 click 时显式告知

### M5 — 标签来源徽章文案不友好

M1 用 `heuristic` / `llm:gpt-4o-mini` / `llm:claude-sonnet-4-5` 作字面 badge — 终端用户看不懂 "heuristic"。

**修正建议**：
- `heuristic` → "启发式（无 AI）"
- `llm:gpt-4o-mini` → "GPT-4o"
- `llm:claude-sonnet-4-5` → "Claude Sonnet 4.5"
- `heuristic_only`（空 LLM）→ "未启用 AI 标签"

---

## 六、Low 详情

### L1 — L5 验收过于技术性

L5：操作"`_meta.model_version` ≠ `heuristic_only`"是开发者视角，用户视角应当是"在 AssetDetailPanel 看到 Claude 徽章"——验收应是端到端可见。

### L2 — 范围外项目去向

L 边界、M 边界、N 边界都写"不做 X" — 但没说"X 进入 v0.20 / 移到 WISHLIST"。建议每条不做边界都标记后续 owner。

### L3 — 错误码英文/中文双轨

L4 分类英文错误码（auth / rate_limit / network / parse），到 UI 后展示中文。计划没在 L 或 M 系列定义这层 i18n 映射。

---

## 七、用户期望但 L/M/N 未盖到的清单（CX1 应答）

按用户报告"全部修"的隐含期望：

| 编号 | 用户感知 | L/M/N 覆盖？ | 缺口建议 |
|---|---|---|---|
| U1 | 标签错（structured_tags） | ✅ L1-L7 直接修 | — |
| U2 | UI 文案承诺 AI 但不给 AI | ✅ M1, M2, M6 | — |
| U3 | 顶层导航混乱 | ✅ N1-N8 | — |
| U4 | "指纹"打的不对 | ❌ **完全未覆盖** | C1 修正建议（M8/M9） |
| U5 | Embedding / 语义搜索（间接） | ❌ **完全未覆盖** | H5 修正建议（L9） |
| U6 | `_vision_enrich_tags` 路径 | ❌ **完全未覆盖** | H6 修正建议 |
| U7 | Review engine VLM（Claude 桥接） | ⚠️ 依赖 H3，但 H3 在 Wave 3 延后 | C2 修正建议 |
| U8 | 已激活用户配置 API Key 入口 | ⚠️ M3 对老用户不可见 | H2 修正建议 |
| U9 | 启用 LLM 后的隐私 / 成本告知 | ❌ **完全未覆盖** | H4/M4 修正建议 |
| U10 | 错误状态可读性（auth_failed 等） | ⚠️ 后端做了 L7，前端没消费 | H3 修正建议 |

**覆盖率估算**：
- 完全覆盖：3/10（U1, U2, U3）= 30%
- 部分覆盖：3/10（U7, U8, U10）= 30%
- 完全遗漏：4/10（U4, U5, U6, U9）= 40%

**用户期望"全部修"**，当前 L/M/N 只覆盖 60%（其中 30% 还不完整）。

---

## 八、修正方案总览（按 Wave 重排建议）

### Wave 1（修订）
保留 E1-E4 + F1-F3 + M1 + M2（修订为 H3 联动）+ **新增 M8/M9（"指纹"概念修复）** + **新增 N1-N5（导航核心 path 改造，对应 CX2 用户感受顺序）**

### Wave 2（修订）
F5 + G1-G4 + J1 + L1-L8（含 L8 接口契约）+ **H3 提到此 Wave**（与 L 同步） + L9（embedding 路径决策）+ M3 拆分（M3a 静态 UI）

### Wave 3（修订）
H1 + H2 + H4 + H5 + I1 + M3b + M3c + M4-M7 + **H6（vision_enrich 处理）**

### Wave 4（修订）
I2-I5 + J2-J5 + N6-N8（i18n + E2E）+ K（时间允许）

---

## 九、产品规范一致性核查（product-standards.md）

| 规范条款 | 计划合规情况 |
|---|---|
| §3.1 用户场景到功能路径 | ⚠️ 部分缺失：L/M/N 任务都从"代码缺陷"出发，未明确写"用户场景 → 痛点 → 验证"链路 |
| §3.2 问题定义清楚 | ✅ L 序前置"缺口分析"段做得好；M、N 也合规 |
| §4.1 PRD 必需要素 | ⚠️ "用户故事"形式缺失；任务表只到验收，未写 user story |
| §4.2 禁止模糊 | ✅ 各任务验收都是 grep / 测试 / 操作，可执行 |
| §6.1 业务规则可执行 | ⚠️ L4 分类错误"auth/rate_limit/network/parse" — 没写每类的处理步骤、错误码、后续重试 |
| §7.1 自检 | ⚠️ M3 没考虑"已激活用户看不到"（H2）；L 没考虑 vision_enrich 路径（H6）→ 表明自检未做满 |
| §10.3 文档命名 | ✅ 计划文件名 `dev-plan-v0.19.0.md` 合规 |
| §11.2 审计整合 | ✅ Wave 重排时 L/M/N 与历史审计 E-K 整合 |

**关键违反点**：§7.1 / §3.1 — 计划是"代码视角"而非"用户视角"组织的，导致 H2/H6 这类"用户实际看不见的修复"发生。

---

## 十、修订建议清单（按优先级）

**必须修（P0，进 Wave 1 前完成）**：
1. C1 — 加 M8/M9 解决"指纹"概念错配
2. C2 — H3 提到 Wave 2 并与 L 联动；同时双写 env var
3. C3 — N 优先级判断给用户决策 / 或部分 N 提前

**应当修（P1）**：
4. H1 — 加 L8 接口契约
5. H2 — M3 拆分，老用户路径用 M3.5 或 SettingsView 入口
6. H3 — M2 横幅 / toast 消费 L7 细分类
7. H4 — 加 a11y / 隐私 / 成本要求
8. H5 — 决策 embedding 是否在 v0.19 / v0.20

**建议修（P2）**：
9. M1-M5 全部修订
10. H6 — vision_enrich 路径明确标注

**记录（不阻塞 Wave 1）**：
11. L1-L3 — 改进验收和命名

---

## 十一、修订记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-05-08 | 初版 — 维度 C 产品对齐审计；3 Critical / 6 High / 5 Medium / 3 Low |

---

**审计结论**：

L/M/N 三个 Feature 是必要且方向正确的，但当前版本在以下三个方面**未达到 product-standards §3.1 / §7.1 / §11.4 的要求**：

1. **用户视角覆盖不足**：U4（指纹）、U5（embedding）、U6（vision_enrich）、U9（隐私）共 4 项用户期望未盖到
2. **跨 Feature 链路断裂**：L 与 H3 必须同 Wave 才能让用户感知一致
3. **优先级与用户感受不匹配**：N（用户首先列出的痛点）反而被排到 P1

**建议**：吸收上述 3 Critical 修正后再进入 Wave 1。如果时间紧，至少要在 TODO_NEXT.md 和 dev-plan 文档里**明确告知用户**当前未盖到的 4 项 + L/H3 链路依赖。

---

*文档结束*
