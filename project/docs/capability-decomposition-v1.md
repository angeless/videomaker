# 能力拆分方案 v1（按产品功能，不按流水线步骤）

更新时间：2026-02-24
适用仓库：`/Users/angelwang/videoeditor`

## 1. 背景

当前实现是 Step1~Step7 的流水线结构，优点是流程完整，但问题是：

- 粗剪、快剪、精剪、导出、配乐配音都耦合在后半段，质量优化和功能迭代互相阻塞。
- “选题库（数据库）”和“选题+文案”没有形成稳定能力边界，不利于复用。
- 需要接外部编辑器或外部渲染 API 时，没有清晰的模块入口。

## 2. 新的能力边界（与你的拆分一一对应）

1. `topic_library`（选题库）
- 本质：数据库服务
- 输入：选题模板、标签、人群、风格
- 输出：可检索选题记录（供文案与脚本模块复用）

2. `topic_copy`（选题 + 文案）
- 本质：语义驱动的文案生成
- 输入：选题库记录 + 素材语义
- 输出：Hook、结构大纲、脚本骨架
- 参考：Lumen5 的“主题到脚本”体验

3. `text_rough_cut`（文字粗剪）
- 本质：基于转写文本的删改时间线
- 输入：ASR 文本时间戳、删除短语
- 输出：粗剪片段时间线
- 参考：Filmora / Descript 的 text-based editing

4. `short_clip`（短视频快剪）
- 本质：长视频高光提炼
- 输入：候选高光片段（分数、原因）
- 输出：时长受限的高光时间线
- 参考：Wisecut / Clipchamp

5. `refinement`（视频精剪）
- 本质：品质提升策略（转场、调色、磨皮、节奏）
- 输入：已匹配脚本、风格、编辑器目标
- 输出：精剪执行计划（内置 FFmpeg 或外部 NLE）
- 外接目标：DaVinci / Final Cut Pro / Premiere / 剪映

6. `social_export`（社媒导出）
- 本质：平台规格化导出
- 输入：母版视频 + 平台模板
- 输出：按平台规格的高质量成片
- 模板化方向：支持 FlexClip 风格的可配置模板

7. `audio_voice`（配乐和配音）
- 本质：声音层编排
- 输入：字幕/文案、情绪风格
- 输出：配音时间线 + 配乐方案
- 方向：兼容 ElevenLabs 类声音克隆接口

## 3. 已落地到代码的骨架

新增目录：`/Users/angelwang/videoeditor/modules/capabilities`

- `registry.py`：7 个能力注册表 + 旧流程映射
- `topic_library.py`：SQLite 选题库最小实现（init/upsert/search/list）
- `topic_copy.py`：选题+语义 => 文案草稿
- `text_rough_cut.py`：文本删改 => 粗剪时间线
- `short_clip.py`：高光候选 => 快剪时间线
- `refinement.py`：精剪策略和外部编辑器切换计划
- `social_export.py`：平台导出模板与 ffmpeg 命令构造器
- `audio_voice.py`：配音分段与配乐策略

## 4. 与现有 Step1~Step7 的迁移映射

过渡映射：

- Step1 -> `topic_library`（素材组织可继续在 library 中并行）
- Step2/3/4 -> `topic_copy`
- Step5 -> `text_rough_cut`
- Step6 -> `short_clip`
- Step7 -> `refinement`
- 新增 -> `social_export`（建议 Step8）
- 新增 -> `audio_voice`（建议 Step9）

说明：先保留旧工作流引擎，逐步把 UI/API 从 step 调度切到 capability 调度，避免一次性重构风险。

## 5. 三阶段落地建议

阶段 A（1 周）：结构拆分不改体验
- 接入 `topic_library` 到现有项目数据目录
- 在 Step2/3 前增加 “选题库检索 + 选题文案草案” 输入

阶段 B（1-2 周）：中段剪辑替换
- 用 `text_rough_cut` 替代当前固定粗剪规则
- 用 `short_clip` 取代单一 15s 拼接策略，支持目标时长可配

阶段 C（2 周）：质量与导出升级
- `refinement` 增加外部 NLE handoff（先 FCPXML/EDL）
- 增加 `social_export` 多平台导出任务
- 增加 `audio_voice` 的声音克隆/BGM 服务适配器

阶段 D（后续，当前功能稳定后启动）：Agent 易用性与双入口兼容
- 保留现有人用 UI 使用习惯，不做强制工作流改造。
- 新增 Agent 兼容 API 入口（同 capability 内核，新增上下文字段与幂等能力）。
- 新增 Agent 模板层（在系统模板/项目模板上可叠加自定义覆盖）。
- 新增 AI Skill 调用编排（串并行、重试、预算、审计）。
- 详细路线图见：`docs/agent-usability-roadmap-v1.md`。

## 6. 最小验证标准

- 能单独调用任一 capability，不依赖整个 Step1~7 完整运行。
- capability 输入输出是稳定 JSON，可被 API 和 UI 复用。
- 任一模块失败不影响其它模块数据（失败隔离）。

## 7. 当前接入进度（2026-02-24）

- 已接入 Step2：运行选题时自动同步 `data/topic_library.db`，并把选题库模板摘要拼到选题 prompt。
- 已接入 Step6：粗剪升级为 `text_rough_cut + short_clip` 组合策略，输出 `preview/rough_plan.json`。
- 已升级文字粗剪交互：支持按句号区间（如 `1,2,5-8`）保留/删除文本片段，并返回逐句保留决策。
- 已新增逐句勾选模式：Capability 工作台可直接勾选每句是否保留，并自动回填句号区间参数。
- 已新增逐句筛选与批量操作：支持关键词筛选句子、按筛选结果批量勾选、以及“一键全删口头词句”。
- 已新增文本与预览联动：点击任一句可直接跳转粗剪预览视频对应时间点。
- 已提供 capability 独立 API：见 `docs/capabilities-api.md`。
- 已接入桌面 UI：`制作视频` 页面新增 Capability 工作台，可独立触发 7 类能力并查看 JSON 结果。
- 已新增外部 NLE 交接包：支持输出 FCPXML/EDL（davinci/finalcut/premiere）。
- 已新增外部 NLE 一键启动：可在生成交接包后直接拉起目标编辑器（macOS）。
- 已新增外部 NLE 成片导回：支持把外部导出的成片回收至 `output/final.mp4`，直接衔接社媒导出。
- 已新增社媒导出任务：支持导出计划生成与后台执行。
- 已支持社媒自定义模板：可保存/删除项目级导出模板并与内置模板一起用于导出计划。
- 已新增配音执行接口：支持 ElevenLabs 配音合成（含 dry-run 预演）。
- 已新增旁白拼接与混音：支持把配音片段生成旁白轨并自动混音到母版视频（含 Ducking）。
- 已新增自动配乐能力：支持从项目 BGM 库按情绪自动匹配背景音乐，并接入混音与一键流水线。
- 已支持 BGM 自动循环与淡出：BGM 可自动铺满整段视频并在片尾淡出，减少长视频后半段无配乐问题。
- 已支持配乐 Provider 可插拔：本地曲库与 `elevencreative_compatible` 远端接口可切换。
- 已支持远端 BGM URL 直混：远端配乐可不落地直接参与混音（循环策略自动降级）。
- 已支持远端缓存与严格校验：同 URL 配乐可复用缓存，且可开启远端响应严格协议校验。
- 已支持缓存策略控制：可强制刷新远端配乐，或按缓存有效期（天）自动失效。
- 已新增一键音频流水线：后台串联“配音合成 -> 旁白轨 -> 自动配乐（可选）-> 混音”并返回进度。
- 已实现导出结果回流：社媒导出批次会写入 `workflow.json` 供 UI 历史回看。
- 已支持历史批次复跑：可按 `batch_id` 一键复用参数重新导出。
- 已新增导出前规格校验：支持按平台检查源视频是否需要截断、补边缩放、升采样或 FPS 转换，并在 UI 直接查看报告。
- 已支持 capability 统一请求上下文与幂等重放：`actor_type/actor_id/run_mode/idempotency_key/trace_id`，并将幂等缓存持久化到项目数据目录，支持 `GET/POST /api/capabilities/idempotency/cache*` 管理接口（TTL/清理）。
- 已接入桌面 UI 幂等缓存面板：支持在能力工作台内查询 `memory/persisted/merged` 缓存、按 `actor/endpoint/idempotency_key/project_path` 过滤、分页浏览、查看过期状态并执行清理（含 TTL、限量、清空内存/落盘、一键默认清理 7 天）。
- 已落地 Agent 入口骨架：`/api/agent/capabilities` 与 `/api/agent/tasks/plan`，并保持现有人用流程不变。
