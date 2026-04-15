# VideoEditor 版本开发计划（v0.19.0）

**文档版本：** V1.0
**日期：** 2026-04-15
**基线 Commit：** 95199fd (fix: tenth-pass cross-audit findings)
**基线 VERSION：** 0.18.0
**基线测试：** 1648 passed, 5 skipped

---

## 1. 版本目标

**生产化 + 遗留债务清理 + 开发者体验**。

v0.18.0 通过 10 轮独立交叉审计修复了 92 个问题，包括 13 CRITICAL + 27 HIGH。
但审计过程中也暴露了几类**不能在审计-修复循环里解决**的遗留问题：
- 约 8 个 dead-stub 端点（前端 UI 存在，后端不做实事）
- 前端 0 单元测试（Vue 组件从未被自动化验证过）
- Python 模块里有 ~555 个 bare `except Exception`（无法逐个审完）
- 旧 API envelope 不一致（`{ok/error}` vs `{success,...}`）
- VLM 错误静默化（429/timeout/auth 失败用户看不到）

**v0.19.0 一句话定位：** 把 v0.18.0 的能力从"功能完备"推进到"用户可感知地可靠、可调试、可生产"。

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

## 3. 出版本流程

### Wave 1（两周）：Dead-Stub 清理 + 错误显现
E1 + E2 + E3 + E4 + F1 + F2 + F3 — 用户可感知的"修能用"质变。

### Wave 2（两周）：契约 + 测试基础设施
F5（前端测试）+ G1 + G2 + G3 + G4 + J1（pre-existing failures）。

### Wave 3（三周）：功能完备性
H1 + H2 + H3 + H4 + H5 + I1（前 50 bare except）。

### Wave 4（一周）：安全加固 + 开发者体验
I2-I5 + J2-J5 + K（时间允许）。

**总计 8 周**，实测可能 6-10 周。

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
