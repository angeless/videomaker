# VideoEditor 版本开发计划（v0.19.0）

**文档版本：** V1.0
**日期：** 2026-04-15
**基线 Commit：** 95199fd (fix: tenth-pass cross-audit findings)
**基线 VERSION：** 0.18.0
**基线测试：** 1648 passed, 5 skipped

---

## 1. 版本目标

**生产化 + 遗留债务清理 + 开发者体验 + 用户报告核心修复**。

v0.18.0 通过 10 轮独立交叉审计修复了 92 个问题，包括 13 CRITICAL + 27 HIGH。
但审计过程中也暴露了几类**不能在审计-修复循环里解决**的遗留问题：
- 约 8 个 dead-stub 端点（前端 UI 存在，后端不做实事）
- 前端 0 单元测试（Vue 组件从未被自动化验证过）
- Python 模块里有 ~555 个 bare `except Exception`（无法逐个审完）
- 旧 API envelope 不一致（`{ok/error}` vs `{success,...}`）
- VLM 错误静默化（429/timeout/auth 失败用户看不到）

**2026-05-08 用户报告补充**（产品功能测试发现，已根因锁定）：
- **素材标签器从未调用 LLM**：`_llm_tagging_enabled` 仅检查 `OPENAI_API_KEY`，未配置时静默走 `_heuristic_structured_tags`（颜色规则）。Settings UI 暴露的 Anthropic key 不被 library 标签器读取（适配器层断裂）。→ Feature L + M
- **顶层导航混乱**：7 个一级入口 + `/create/workflow` 与 `/workflows` 命名碰撞 + 编辑动作散落 3 处。→ Feature N

**v0.19.0 一句话定位：** 把 v0.18.0 的能力从"功能完备"推进到"用户可感知地可靠、可调试、可生产"，**同时补齐素材 AI 能力的真实性与导航清晰度**。

---

## 2. 版本范围

### Feature E：Dead-Stub 清理（优先级 P0）

> 这批是审计发现的"看起来能用但实际无效"的功能。要么真正接通，要么从 UI 删除。产品上必须做选择。

| E# | 位置 | 现状 | 决策选项 |
|----|------|------|--------|
| E1 | `enhance_routes.py` audio/tts/bgm/transition/reframe 5 端点 | POST 返回 202 但无 worker 调度，job 永远 queued | A. 接通 run_in_bg；B. 删除 UI tab |
| E2 | `stock_routes.py` download | 同 E1 | 同 E1 |
| E3 | `system_routes.py` /api/settings/render GET/PUT | 写入 render_settings.json 但无消费者读取 | 接通到 RenderManager |
| E4 | `EnhancePanel.vue` | 调用 E1 的空端点 | 配合 E1 决策 |

**验收：** 所有前端可触发的后端操作要么真实执行，要么在 UI 中显式隐藏/灰掉。

---

### Feature F：前端可观测性 + 错误显现（优先级 P0）

> 审计多轮发现 VLM / Render 失败时"静默 degrade"，用户看不到为什么没结果。

| F# | 需求 | 验收 |
|----|------|------|
| F1 | VLM 失败分级显现（auth/429/timeout/network）→ 用户可见 toast + 指引 | 测试：触发 401/429/timeout 场景，UI 显示具体错误码 |
| F2 | DiagnosticsPanel 流分析失败时显示原因（不只是"分析失败"） | 测试：mock 不同错误，断言错误文案 |
| F3 | Render 失败时前端显示 FFmpeg stderr 末尾 N 字符 | 测试：触发 ffmpeg 失败，断言 stderr 片段可见 |
| F4 | 全局 apiStore 错误归因：保留 `raw_error` + 友好 message | 审计：所有 `apiStore.api()` 调用不丢诊断信息 |
| F5 | 前端测试基础设施（Vitest + @vue/test-utils）+ ≥ 10 个组件测试 | 验收：前端 CI 运行，通过率 100% |

---

### Feature G：API envelope 统一 + 契约测试（优先级 P1）

> 审计发现旧路由返回 `{ok: bool}`，新路由返回 `{success: bool, error, code, ...}`。前端两套判断逻辑。

| G# | 需求 | 验收 |
|----|------|------|
| G1 | 所有路由统一输出 envelope: `{success, error, message, code, trace_id, ...data}` | grep 剩余 `{"ok": True` 为 0 |
| G2 | 前端 apiStore 只信任统一 envelope | test: 旧 envelope 返回时有迁移告警日志 |
| G3 | 契约测试：每个端点的 2XX / 4XX / 5XX 响应结构快照 | `tests/contracts/` 新增 ≥30 个快照 |
| G4 | OpenAPI / JSON Schema 自动生成 | 生成 `docs/api-schema.json` |

---

### Feature H：VLM + Render 完备性（优先级 P1）

> 审计发现 VLM/Render 的几个"能跑通但不完美"的遗留。

| H# | 需求 | 验收 |
|----|------|------|
| H1 | RenderManager._concat_segments 异构源 stream normalization — 不同分辨率/fps/编解码的源不再崩 | 测试用例：3 个异构源 clip → render 成功 |
| H2 | VLM transition 支持多图片 prompt（side-by-side 双帧） | `_check_transitions` 真正分析两帧 |
| H3 | VLM settings → adapter env var 桥接完善（v0.17 遗留） | 在 UI 设置 key 后立即可用，无需重启 |
| H4 | `/vlm/diagnose` 同步改异步（与 analyze-stream 统一） | GET/POST 两端都有 job_id 模式 |
| H5 | `add_track` TOCTOU 竞争（SQLite 事务化计数 + 插入） | 并发测试 5 个 POST 不产生超限轨道 |

---

### Feature I：安全加固收尾（优先级 P1）

| I# | 需求 | 验收 |
|----|------|------|
| I1 | 审计剩余 `except Exception: pass/return None` 总计 ~555 处 — 分优先级修 top 50 | 至少 50 个 bare except 被明确分类：log-and-raise / 预期降级 / 需修 |
| I2 | libraryGovernance 等剩余裸 fetch 全部走 apiStore | grep `fetch(` 不含 apiStore 为 0 |
| I3 | 所有返回 HTML 的路由审查 escape 情况 | 测试：XSS payload 注入不成功 |
| I4 | CSP header 在 HTML 响应上全面启用 | curl -I 所有 HTML 端点包含 CSP |
| I5 | MCP permission level 真正生效（DANGEROUS 工具需显式确认） | 测试：DANGEROUS 工具在默认模式下 403 |

---

### Feature J：开发者体验（优先级 P2）

| J# | 需求 | 验收 |
|----|------|------|
| J1 | 修复 test_fingerprint_relink.py 3 个 pre-existing failures | 1651 passed, 5 skipped（0 failed） |
| J2 | Frontend CI pipeline（lint + test + build） | GitHub Actions 或等价物工作 |
| J3 | 开发者文档：adapter 协议、envelope 规范、测试 fixture 目录 | `docs/tech-specs/` 新增 3 篇 |
| J4 | 新增 "arch decision records"（ADR）记录 v0.18 的 10 轮审计教训 | `docs/decisions/` 新增 ADR-010 至 ADR-013 |
| J5 | pre-commit hook: sanitize_ffmpeg_bin / is_safe_outbound_url 新代码自动调用 | 提交时自动检查 |

---

### Feature K：UX 细节（优先级 P2，时间允许才做）

| K# | 需求 |
|----|------|
| K1 | TimelineTrackHeader aria-label / focus 样式（round-4 遗留） |
| K2 | 下载进度条（当前只显示 "下载中…"，缺具体百分比） |
| K3 | render 出错时一键"导出诊断包"（日志 + 配置 + clip 列表） |
| K4 | 全局快捷键 cheatsheet（"?" 打开） |

---

### Feature L：Library 标签器 LLM 接入 + 适配器统一（优先级 **P0** — 用户报告核心）

> **缺口分析**：当前 `modules/library/core/core_mixin.py:1461` 的 `_llm_structured_tags` 只走 OpenAI（line 199-202 `_llm_tagging_enabled` 仅检查 `OPENAI_API_KEY`），且通过 `_call_openai_json` (line 877) 直接调 OpenAI SDK，**完全绕过 v0.17 引入的 `vlm_adapter`**。Settings UI 的 Anthropic key 字段 hint 写"备用 AI 服务商"但实际不被 library 标签器读取。
>
> **现状证据**：未配 `OPENAI_API_KEY` 时运行时 `LLM tagging enabled: False`，所有素材静默降级到 `_heuristic_structured_tags`（颜色/边缘/运动规则）。

| L# | 需求 | 验收 |
|----|------|------|
| L1 | `_llm_tagging_enabled` 接受 OpenAI **或** Anthropic key（任一即 enabled） | 单测：仅 `ANTHROPIC_API_KEY` 时返回 True；都没有时返回 False |
| L2 | 抽象 `_call_openai_json` → `_call_vlm_json`（路由 `vlm_adapter.get_vlm_adapter(provider)`） | 单测：mock OpenAI/Claude/Llava adapter 各跑一次，返回 schema 一致 |
| L3 | `_call_openai_text` 同上抽象为 `_call_vlm_text` | 调用点全部切换；grep `_call_openai_` 在 library/ 下 = 0 |
| L4 | 异常吞噬修复：`except Exception: return {}` 改为分类错误（auth/rate_limit/network/parse）+ 日志 + UI 可见 | 单测：注入 4 类异常，断言 logger 调用与返回错误码 |
| L5 | settings UI hint 修订：Anthropic 字段说"用于素材 AI 标签 + 评审 VLM"，与代码一致 | 操作：仅设 Anthropic key 后导入素材，`_meta.model_version` ≠ `heuristic_only` |
| L6 | `_meta.model_version` 反映真实 provider（`gpt-4o-mini` / `claude-sonnet-4-5` / `local_llava` / `heuristic_only`） | 集成测试：3 种 provider 路径下 `model_version` 字段不同 |
| L7 | LLM 失败不再静默：`/api/library/health` 返回 `{llm_status: ok|missing_key|auth_failed|rate_limited|...}` | curl 端点，断言字段存在；模拟 401 时 status = `auth_failed` |
| **L8** | **env var 桥接修复**（plan-audit C-Critical-2）：settings_service 写 `ANTHROPIC_API_KEY` 时同步写 `VIDEOEDITOR_CLAUDE_API_KEY`；或反向，让 `_vlm_claude.py:19` 优先读 `ANTHROPIC_API_KEY`（兼容旧名）。**必须与 L1 同 Wave**，否则 L1 形同虚设 | 操作：UI 设 Anthropic key → 重启服务 → ClaudeVisionAdapter `is_available() == True`；单测 |
| **L9** | `_vision_enrich_tags` (line 352, 用于图片素材) 走 vlm_adapter | 测试：仅 Anthropic key 时图片素材入库 `method=image_vision_enrich` 而非 `image_heuristic` |
| **L10** | `_call_openai_embedding` (line 1024, 3 处调用) 接通 vlm_adapter（或 Voyage SDK 作 Anthropic 推荐 embedding） | 测试：仅 Anthropic key 时语义搜索可用；hybrid/vector 模式不静默回退 keyword |

**不做边界**：本次不改 prompt 工程；不改 `structured_tags` schema；不动 review_engine 的 vlm_adapter 用法本身（但 L 系列共享的错误枚举 `VLMProviderError` 也供 F1 用 — 与 F1 同步定义）。

**审计修订**（2026-05-08）：
- 因 plan-audit C-Critical-2 暴露 env var 命名断裂，新增 **L8**（必须修，否则 L1-L7 全部不工作）
- 因 plan-audit C/U6 暴露 `_vision_enrich_tags` 同样 OpenAI-only，新增 **L9**
- 因 plan-audit C/U5 暴露 embedding OpenAI-only，新增 **L10**
- L4 错误枚举与 F1 共用 `VLMProviderError`（plan-audit A-H3）

---

### Feature M：素材分析能力诚实化（优先级 **P0** — 用户信任修复）

> **缺口分析**：`scene_description_simulation` / `object_detection_simulation`（`video_asset_toolkit.py:532, 641`）函数名诚实但 UI 文案声称"AI 描述"。`AssetDetailPanel.vue:149` 显示标签时不区分 heuristic / LLM 来源，用户无法察觉降级。`OnboardingModal.vue` 328 行**完全不提 API Key**。
>
> **与 Feature F 的区分**：F1-F4 是 review/render 错误显现；M 是 library 模块的并行修复。

| M# | 需求 | 验收 |
|----|------|------|
| M1 | `AssetDetailPanel.vue` 显示标签来源徽章（`heuristic` / `llm:gpt-*` / `llm:claude-*`） | 组件测试：mock 3 种 `_meta.model_version`，断言 badge 正确 |
| M2 | Library 顶部"AI 标签未启用"横幅（参照 `DiagnosticsPanel.vue:31` 模式），含 Settings 链接 | 操作：未设 key 时进 Library 看到横幅；设 key 后横幅消失 |
| M3 | `OnboardingModal.vue` 新增 step：API Key 配置引导（含跳过选项） | 操作：首次启动看到 step；跳过后进入 Library 仍见 M2 横幅 |
| M4 | `scene_description_simulation` → `_describe_scene_heuristic`；调用点同步 | grep `_simulation` 函数定义在 `video_asset_toolkit.py` = 0 |
| M5 | `object_detection_simulation` → `_detect_objects_heuristic`；调用点同步 | 同 M4 |
| M6 | UI 文案审查：删除/修改所有声称"AI 场景描述"但实际走 heuristic 的文案 | grep `AI 场景|AI 描述|AI 标签` 在未限定 LLM 的上下文 = 0 |
| M7 | E2E playwright：3 种状态（无 key / 有 OpenAI key / 有 Anthropic key）下 Library 横幅与徽章正确 | 测试通过 |
| **M8** | **指纹 vs 标签概念区分**（plan-audit C-Critical-1）：LibraryHealthPanel 拆分两块统计（"已建指纹（pHash 去重）" vs "已生成 AI 标签"）+ 各自 hover hint 解释技术差别 | 操作：进 LibraryHealthPanel 看到两块独立卡片；hint 文案审查 |
| **M9** | **老用户配置入口**（plan-audit H-7）：M3 onboarding 仅首次启动可见；老用户从 M2 横幅点 "立即配置" 直达 Settings AI section（带 anchor `#ai-config`） | 操作：未配 key 老用户从 Library 一键到 Settings AI 卡片 |

**不做边界**：不改 heuristic 算法本身（蓝车=water 是已知接受的降级行为）；不重写 onboarding 步骤数（仅在已有结构里**加**一步）。M2 横幅复用 `MissingKeyBanner.vue` 新组件，**不复制 DiagnosticsPanel 样式**（plan-audit A-H4）。

**审计修订**（2026-05-08）：
- 因 plan-audit C-Critical-1 用户口语"指纹"与代码概念错配，新增 **M8**
- 因 plan-audit H-7 老用户看不到 M3 onboarding，新增 **M9**
- M4/M5 验收升级：grep 函数定义 + grep 全工作区调用点（plan-audit B-H5）

---

### Feature N：顶层导航重构（优先级 **P1** — Issue B 完整修复）

> **缺口分析**：当前 `router/index.js` 顶级路径 7 个（library / create / roughcut / review / workflows / tools / settings），其中 `/create/workflow`（创作工作流面板）与 `/workflows`（工作流管理）**同名不同物**；`/roughcut`、`/review` 与 `/create/refine` 等都是"加工剪辑"动作但拆三层；`/production` 重定向已无活引用。

| N# | 需求 | 验收 |
|----|------|------|
| N1 | 顶级 path 压到 4 个：`library / create / tools / settings` | `router/index.js` 顶层 routes ≤ 4（不算 redirect） |
| N2 | `/workflows` 合并为 `/tools/workflows`，旧路径 redirect | 旧 URL 仍可达；菜单栏只有 4 项 |
| N3 | `/roughcut` 收编为 `/create/roughcut` 子路由 | 旧 URL redirect；面包屑显示"创作 → 智能粗剪" |
| N4 | `/review` 收编为 `/create/review` 子路由 | 同 N3 |
| N5 | **`/create/workflow` 重命名为 `/create/guide`**（消除与 `/workflows` 命名冲突）—— **plan-audit B-Critical-1 升级**：影响面包含 14 个 .vue/.js 文件 + 20+ 处硬编码 | **多步验收**：① `grep -rn "/create/workflow" apps/desktop/ui-vue/src/` 在改完后 = 0（除 redirect 配置）② i18n labels.js 同步 ③ Vue 组件硬编码扫描 ④ 旧路径 301 redirect 测试 ⑤ E2E 通过 |
| N6 | **修订**（plan-audit risk-N）：删除孤儿 `ProductionView.vue` + redirect 保留 6 版本周期至 v0.24 | `find apps/desktop/ui-vue/src/views/ -name 'ProductionView*'` = 0；router redirect 保留 + 添加注释说明删除时机 |
| N7 | i18n labels.js 同步 + NavBar 组件重构 | 操作：所有原入口仍可达，导航栏 ≤ 4 项 |
| N8 | E2E playwright 覆盖新路径 + 旧路径 redirect | 测试通过 |

**不做边界**：不改任何 view 内部布局；不重画图标；不改键盘快捷键。

**审计修订**（2026-05-08）：
- 因 plan-audit C-Critical-3（用户先报布局），把 **N5 + N6 提前到 Wave 1**（与 M 同期）；N1-N4 + N7-N8 留 Wave 4 主体重构
- N5 验收文档化为 5 步多重验收（plan-audit B-Critical-1）
- N1 验收文字修订："顶级 path ≤ 4（不算 startup `/` 与 redirect）"（plan-audit A-H8）

---

## 3. 出版本流程

> 2026-05-08 第二次修订：吸收 plan-audit 5 Critical 修正——优先级反转修复（N 部分前移）+ env var 桥接 + L6 提前 + 概念错配澄清。详见 [`plan-audit-report-v0.19.0.md`](../audit/2026-05-08-plan-audit-report-v0.19.0.md)。

### Wave 1（两周半）：Dead-Stub 清理 + 信任修复地基 + 用户报告头牌问题
E1 + E2 + E3 + E4 + F1 + F2 + F3 + **M1 + M2 + M3 + M8 + M9 + L6 + N5 + N6** — 用户可感知的"修能用"质变 + 标签来源透明化 + 用户头牌问题（布局命名碰撞 + 指纹/标签概念）即时缓解。

> Wave 1 关键依赖：M1 用 L6 提供的 `_meta.model_version`（plan-audit B-Critical-2 修正）

### Wave 2（三周）：契约 + 测试基础设施 + LLM 接入主体
F5（前端测试）+ G1 + G2 + G3 + G4 + J1 + **L1 + L2 + L3 + L4 + L5 + L7 + L8 + L9 + L10**（LLM 接入 + 适配器统一 + env var 桥接 + vision_enrich + embedding）+ **H3**（VLM settings → adapter env var bridge，与 L8 同源）。

> Wave 2 关键依赖：L1 ↔ L8 必须同 PR 完成（env var 修复，plan-audit C-Critical-2）

### Wave 3（三周）：功能完备性 + 命名诚实化
H1 + H2 + H4 + H5 + I1（前 50 bare except）+ **M4 + M5 + M6 + M7**（Heuristic 函数 + UI 文案诚实化 + E2E）。

### Wave 4（两周）：安全加固 + 开发者体验 + 导航主体重构
I2-I5 + J2-J5 + **N1 + N2 + N3 + N4 + N7 + N8**（导航主体重构）+ K（时间允许）。

**总计 ~10.5 周**（原 8 周 + L/M/N 含 audit 修正约 2.5 周），实测可能 9-13 周。

---

## 4. 非目标（v0.19 明确不做）

- **重大架构重构**（如拆成前后端分离服务）— 留到 v1.0
- **新产品功能**（如 AI 写脚本、云端渲染）— 不属于"生产化"
- **i18n / 多语言** — 用户基数不足以支撑
- **Windows 完整支持** — macOS-first，PyWebView 在 Windows 上有已知问题

---

## 5. 审计持续集成

v0.18.0 的 10 轮交叉审计教会我们：**审计必须嵌入日常流程，而不是版本末尾一次性做**。

v0.19.0 引入：
- 每次 merge 前 1 轮 agent review（`pr-review-toolkit` 插件）
- 每 2 周跑 1 次 scope-expanded audit（目标：漂移检测）
- 新增「审计过的文件」清单 `docs/audit/audited-files.md`，后续只审未列出的

---

## 6. 成功标准

**硬性指标：**
- 1651+ passed, 0 failed（现 1648 passed, 5 skipped, 3 pre-existing failures）
- 0 dead-stub 端点（E1-E4 全解决）
- 前端 ≥ 10 个组件测试
- API envelope 统一率 100%
- 新增交叉审计轮次 ≥ 2 的情况下 CRITICAL = 0
- **L 系列：** 仅设 `ANTHROPIC_API_KEY` 时素材入库后 `_meta.model_version` 含 `claude` 字样（非 `heuristic_only`）
- **M 系列：** 未配 key 时 Library 显示警告横幅；UI 文案 grep "AI 场景描述" 在 heuristic 路径 = 0
- **N 系列：** `router/index.js` 顶层 routes ≤ 4；旧路径 100% 可用 redirect

**软性指标：**
- 用户反馈渠道上"为什么没反应"类投诉 → 0
- 开发者新 feature 到 merge 的 TTL 缩短（契约 + 测试基础设施的红利）

---

## 7. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| Dead-stub 删除 vs 实现的产品决策拖延 | 高 | 高 | Wave 1 前先开 product review，2 天内必须拍板 |
| 前端测试基础设施引入导致 build 变慢 | 中 | 中 | 使用 Vitest（比 Jest 快 10x），浅集成 |
| API envelope 统一引入后端兼容性问题 | 中 | 高 | 保留兼容层 6 周，旧 envelope 同时返回 `ok` 和 `success` |
| 审计团队资源不足 | 高 | 低 | 自动化尽量多：scope-expanded audit 可由 agent 夜间跑 |
| **L 系列：Claude vision prompt schema 与 OpenAI 不兼容** | 中 | 高 | 在 vlm_adapter 层做 provider-specific 适配；保留 OpenAI 原路径作 fallback |
| **L 系列：Anthropic vision token 成本高于 OpenAI** | 中 | 中 | 默认 keyframes 数从 3 降到 2；增加 cache 层防重复调用 |
| **N 系列：路由重构导致用户深链失效** | 高 | 中 | 全部旧路径都做 301 redirect（保留 6 个版本周期） |
| **L+M 同时改 Settings UI 引发表单冲突** | 中 | 低 | M3 onboarding 与 L5 settings hint 由同一人/同一 PR 完成 |

---

## 8. 版本号候选

推荐：**v0.19.0** — 因为包含"可观测性 + 契约 + 安全"这些**用户不可见但开发者/安全团队重度依赖**的改动，属于 minor bump。

如果 Wave 1-4 全部按时完成且新功能占比 > 30%，可升级到 **v0.20.0**；否则保持 v0.19.0。

---

## 9. 附录：10 轮审计回顾

v0.18.0 发布后的 10 轮交叉审计（2026-04-14 至 2026-04-15）总共修复 **92 个问题**：

| Round | Commit | 问题数 | CRITICAL | HIGH |
|-------|--------|:---:|:---:|:---:|
| 1 | `1d46bdf` | 10 | 10 | 0 |
| 2 | `7ab433c` | 10 | 0 | 4 |
| 3 | `2986b51` | 12 | 0 | 3 |
| 4 | `93e1aa8` | 6 | 0 | 0 |
| 5 | `291cce5` | 10 | 0 | 5 |
| 6 | `39d5728` | 11 | 0 | 4 |
| 7 | `4106ced` | 10 | 3 | 0 |
| 8 | `e174bd1` | 5 | 0 | 0 |
| 9 | `c04f109` | 6 | 0 | 2 |
| 10 | `022a430` | 7 | 0 | 4 |
| 11 | `95199fd` | 3 | 0 | 2 |

**核心教训：**
1. 测试全绿 ≠ 代码正确（6 轮后才发现 v0.15 起 Comment Export 就是死代码）
2. MagicMock 会伪造不存在的接口（`describe_region` 在 9 轮里都是假的）
3. 扩大审计范围比重复审同一文件收益大 10x
4. 后期加的"孤岛 feature"bug 密度通常比核心 pipeline 高 5-10x（OAuth flow 一个文件 3 个 HIGH）
5. "越审越多"不是审计有毛病，是在逐步暴露代码真实质量

---

**文档结束**
