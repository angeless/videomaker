# VideoEditor 版本开发计划（v0.18.0）

**文档版本：** V1.4（原子性拆分版）
**日期：** 2026-04-06
**基线 Commit：** 0a35f22 (fix(vlm): wire VLM into production app)
**基线 VERSION：** 0.17.0

---

## 1. 版本目标

四大基础设施升级：MCP Server 扩展（让 AI Agent 完整操控 VideoEditor）+ VLM 视频流分析（从单帧进化到连续场景理解）+ 多轨时间线（视频/音频/字幕独立编辑）+ GPU 渲染管线（硬件加速落地到实际渲染路径）。

**一句话定位：** 让 VideoEditor 从"能用"进化为"能被 AI Agent 操控 + 能理解视频流 + 能多轨编辑 + 能快速渲染"。

> ⚠️ **Python 版本约束**（审计修正 H7）：`mcp_server/server.py` 使用 Python 3.10+ 语法
> (`dict | None`)，而项目声明支持 Python 3.8+。MCP 模块的 `requirements.txt` / 文档中
> 需明确标注 **Python ≥ 3.10** 约束。其余模块保持 3.8+ 兼容（`Optional[X]` 语法）。

## 2. 版本范围

### 包含的需求

**Feature A：MCP Server 扩展（W-011 升级）**
- 评审工具组：session init / 评论 CRUD / AI reedit / 诊断
- VLM 工具组：区域描述 / 帧诊断
- 增强工具组：音频增强 / TTS / BGM / 转场
- 只读查询工具组：session 状态、诊断结果作为 MCP Tool（FastMCP 0.9 不支持 Resource）
- 安全：工具权限分级 + 输出路径白名单扩展

**Feature B：VLM 视频流分析**
- 关键帧采样器：场景边界 + 均匀采样（可配置密度）
- 时序分析器：跨帧一致性、场景转场质量、视觉叙事弧线
- 场景级描述聚合：多帧 → 单场景自然语言摘要
- 视频摘要生成：全视频视觉摘要报告
- API + 评审面板集成

**Feature C：多轨时间线**
- 时间线数据模型：Track[] 结构（video / audio / subtitle / effects）
- 轨道操作：增删、重排序、锁定/静音
- 片段操作：移动、裁剪、分割、跨轨拖拽
- 时间线存储：ReviewStore 扩展或独立 timeline_store
- 时间线 API 端点
- 多轨时间线 UI（扩展 components/timeline/ 体系）

**Feature D：GPU 渲染管线**
- 硬件检测→编码策略→渲染路径 全链路贯通
- 硬件加速解码（VideoToolbox/CUDA 输入端）
- 硬件加速编码（已有 encoding_strategy.py，落地到 render_pipeline；auto_render 已 wired）
- 分段并行渲染：多片段同时编码 → concat
- 渲染进度 API + 前端进度条
- 渲染设置 UI（质量/速度/编码器选择）

### 不包含的需求（Future）

| 需求 | 推迟原因 |
|------|---------|
| 画面语义编辑（自动抠图/替换） | 需 SAM 模型，v0.19+ |
| HEVC/AV1 输出格式 | 兼容性风险高，验证 H.264 管线后再扩展 |
| MCP SSE 实时推送 | FastMCP 0.9 不支持 streaming，等 1.0 |
| 多用户协作编辑 | 超出桌面单用户定位 |
| 实时预览渲染 | 需 WebCodecs / GPU 直出，架构变动大 |

---

## 3. 技术设计

### 3.1 模块位置

```
modules/
├── mcp_server/
│   ├── server.py                    ← 扩展：注册新工具组
│   ├── tools/
│   │   ├── workflow_tools.py        ← 已有 7 个
│   │   ├── capability_tools.py      ← 已有 5 个
│   │   ├── review_tools.py          ← 新建：评审工具组
│   │   ├── vlm_tools.py             ← 新建：VLM 工具组
│   │   ├── enhance_tools.py         ← 新建：增强工具组
│   │   └── review_query_tools.py    ← 新建：只读查询工具组（替代 Resource）
│   └── security.py                  ← 扩展：工具权限分级
│
├── review_engine/
│   ├── contracts.py                 ← 扩展：SampledFrame / StreamAnalysis / SceneSummary 数据类
│   ├── exceptions.py                ← 扩展：LockedTrackError
│   ├── video_stream_analyzer.py     ← 新建：视频流分析核心
│   ├── frame_sampler.py             ← 新建：关键帧采样策略
│   ├── scene_summarizer.py          ← 新建：场景级描述聚合
│   ├── timeline_store.py            ← 新建：多轨时间线存储
│   ├── timeline_ops.py              ← 新建：轨道/片段操作
│   ├── render_pipeline.py           ← 扩展：接入硬件加速（D2）
│   └── frame_diagnostics.py         ← 已有：B2 委托 check_continuity()
│
├── hardware/
│   ├── detector.py                  ← 已有，扩展解码能力检测
│   └── encoding_strategy.py         ← 已有，扩展解码策略
│
├── job_system/                       ← 新建目录（X0 异步 Job 管理器，避免与 architecture.md "基础设施层"概念冲突）
│   └── job_manager.py               ← 新建：异步任务注册/进度/取消
│
├── render_engine/                   ← 新建目录（审计修正 H3：Business 层）
│   └── render_manager.py            ← 新建：并行渲染调度
│
├── step7_final_render/
│   └── auto_render.py               ← 已有（已 wired，D2 不改动）
│
├── exporters/
│   └── track_builder.py             ← 扩展：动态 Track[] 输出（C5）
│
└── app_api/routes/
    ├── timeline_routes.py           ← 扩展：多轨 API
    ├── vlm_routes.py                ← 扩展：视频流分析端点（B4）
    ├── settings_routes.py           ← 扩展：渲染设置（D5）
    └── render_routes.py             ← 新建：渲染管线 API
```

### 3.2 Feature A 数据流 — MCP Agent 操控链路

```
AI Agent (Claude Desktop / Cursor / etc.)
  ↓ MCP Tool Call
FastMCP Server (modules/mcp_server/server.py)
  ↓ HTTP → Flask Backend
VideoEditor API (26+ route files)
  ↓
业务层 (review_engine / capabilities / step pipeline)
  ↓ MCP Read-only Tool Call
AI Agent 读取 session state / diagnostics / render progress（只读查询工具）
```

### 3.3 Feature B 数据流 — 视频流分析

```
video_path
  ↓ FrameSampler
[keyframe_0, keyframe_1, ..., keyframe_N]  (PIL.Image[])
  ↓ VLMAnalyzer.describe_region() × N (batch)
[description_0, ..., description_N]
  ↓ SceneSummarizer.aggregate()
{scene_id: "镜头1: 海边日落，人物背影",  ...}
  ↓ VideoStreamAnalyzer.generate_summary()
"全片叙事弧线: 开场→发展→高潮→结尾; 主要场景: 海边(3), 室内(2), 特写(1)"
```

### 3.4 Feature C 数据架构 — 多轨时间线

```python
@dataclass
class TimelineTrack:
    track_id: str
    track_type: str      # "video" | "audio" | "subtitle" | "effect"
    label: str
    clips: List[Clip]
    muted: bool = False
    locked: bool = False
    volume: float = 1.0  # audio tracks only

@dataclass
class Clip:
    clip_id: str
    track_id: str
    start_ms: int        # position on timeline
    end_ms: int
    source_path: str
    source_in_ms: int    # source trim in point
    source_out_ms: int   # source trim out point
    label: str = ""

@dataclass
class Timeline:
    timeline_id: str
    session_id: str
    tracks: List[TimelineTrack]
    duration_ms: int
    version: int = 1
```

### 3.5 Feature D 架构 — 渲染管线

```
HardwareProfile (detector.py)
  ↓
EncodingParams (encoding_strategy.py) — 选择编码器
  ↓
RenderManager.render_timeline(timeline, config)
  ├── 分段：每个 Clip → 独立 FFmpeg job
  ├── 并行：max_concurrent 个 job 同时运行
  ├── 硬件加速：-hwaccel videotoolbox -c:v h264_videotoolbox
  ├── 进度回调：per-segment progress → SSE/WebSocket → 前端
  └── concat：所有分段 → 最终输出
```

### 3.6 与现有系统的边界

| 现有系统 | Feature | 交互方式 | 改动程度 |
|---------|---------|---------|---------|
| 无（新建 job_system/） | X0 | 新模块：job_manager.py | 新建 |
| MCP server (12 tools) | A | 新增 4 个工具文件（17 工具：6+3+4+4） | 扩展，不改现有 |
| VLMAnalyzer (v0.17) | B | 批量调用 describe_region | 无改动 |
| VLM adapters | B | 复用 get_vlm_adapter() | 无改动 |
| scene_segmenter | B | 复用场景边界数据 | 无改动 |
| track_builder.py | C | 从 3 固定轨道 → 动态 Track[] | 重构 |
| ReviewStore | C | 扩展：timeline 表 | DDL migration |
| components/timeline/ | C | 扩展多轨数据绑定 + 轨道头 | 扩展 |
| auto_render.py | D | 已 wired（D2 不改动） | 无改动 |
| render_pipeline.py | D | 接入硬件加速 + 并行 | 扩展 |
| encoding_strategy.py | D | 新增 decode 策略 | 扩展 |
| review_engine/contracts.py | B, C | 新增数据类（SampledFrame 等）+ Timeline 类型 | 扩展 |
| review_engine/exceptions.py | C | 新增 LockedTrackError | 扩展 |
| app_api/routes/vlm_routes.py | B | 新增视频流分析端点 | 扩展 |
| app_api/routes/settings_routes.py | D | 新增渲染设置 | 扩展 |
| stores/review.js | B, C | 新增 timeline + stream 状态 | 扩展 |

---

## 4. 任务列表

### Feature A: MCP Server 扩展

| 任务ID | 任务名称 | 优先级 | 依赖 | 状态 |
|--------|---------|--------|------|------|
| A1 | MCP 评审操作工具组 — init + comment + reedit（6 工具） | P0 | — | Planned |
| A2 | MCP VLM 工具组 — describe + diagnose + status（3 工具） | P1 | — | Planned |
| A3 | MCP 增强工具组 — audio/tts/bgm/transition（4 工具） | P1 | — | Planned |
| A4 | MCP 只读查询工具组 — session state + diagnostics | P1 | A1 | Planned |
| A5 | MCP 安全升级 — 工具权限分级 + 审计日志 | P0 | A1-A3 | Planned |
| A6 | MCP 集成测试 + Claude Desktop 验证 | P0 | ALL-A | Planned |

### Feature B: VLM 视频流分析

| 任务ID | 任务名称 | 优先级 | 依赖 | 状态 |
|--------|---------|--------|------|------|
| B1 | FrameSampler — 关键帧采样策略 | P0 | — | Planned |
| B2 | VideoStreamAnalyzer — 跨帧时序分析 | P0 | B1 | Planned |
| B3 | SceneSummarizer — 场景级描述聚合 | P0 | B2 | Planned |
| B4a | 视频流分析 API — 3 个后端端点 | P1 | B1-B3, X0 | Planned |
| B4b | 视频流分析 UI — DiagnosticsPanel + Store 扩展 | P1 | B4a | Planned |
| B5 | 视频流分析集成测试 | P0 | B1-B4b | Planned |

### Feature C: 多轨时间线

| 任务ID | 任务名称 | 优先级 | 依赖 | 状态 |
|--------|---------|--------|------|------|
| C1 | Timeline 数据模型 + TimelineStore | P0 | — | Planned |
| C2 | TimelineOps — 轨道操作（增删/重排/锁定/静音） | P0 | C1 | Planned |
| C3 | TimelineOps — 片段操作（移动/裁剪/分割/跨轨） | P0 | C1 | Planned |
| C4 | Timeline API 端点 | P0 | C1-C3 | Planned |
| C5 | track_builder 升级 — 动态 Track[] 输出 | P1 | C1 | Planned |
| C6 | 多轨 UI — 扩展 components/timeline/ 体系 | P1 | C4 | Planned |
| C7 | 多轨时间线集成测试 | P0 | C1-C6 | Planned |

### Feature D: GPU 渲染管线

| 任务ID | 任务名称 | 优先级 | 依赖 | 状态 |
|--------|---------|--------|------|------|
| D1 | 硬件检测扩展 — 解码能力探测 + HEVC 支持 | P0 | — | Planned |
| D2 | render_pipeline 接入硬件加速（auto_render 已 wired） | P0 | D1 | Planned |
| D3 | RenderManager — 分段并行渲染调度 | P0 | D2 | Planned |
| D4a | 渲染进度 API — 3 个后端端点 | P1 | D3, X0 | Planned |
| D4b | 渲染进度 UI — RenderProgress.vue 前端进度条 | P1 | D4a | Planned |
| D5 | 渲染设置 UI — 编码器选择 + 质量/速度 | P2 | D2 | Planned |
| D6 | GPU 渲染集成测试 + 性能基准 | P0 | D1-D4b | Planned |

### 共享基础设施

| 任务ID | 任务名称 | 优先级 | 依赖 | 状态 |
|--------|---------|--------|------|------|
| X0 | 异步任务管理器 — Job 注册/进度/取消 | P0 | — | Planned |

> ⚠️ 审计新增（H1）：B4a 和 D4a 都需要 `202 + job_id` 异步模式，但项目中当前
> 无任何异步 Job 基础设施。X0 作为共享前置任务，提供统一的 Job 注册/进度查询/取消机制。

**总计：27 个任务（X0×1 + A×6 + B×6 + C×7 + D×7）**

---

## 5. 各任务详细定义

### X0: 异步任务管理器 — Job 注册/进度/取消

> ⚠️ 审计新增（H1）：B4 (`POST analyze-stream → 202 + job_id`) 和 D4 (`POST render → 202 + job_id`)
> 都需要异步 Job 模式，但项目中无此基础设施。X0 提供统一的 Job 管理层。

**目标：** 提供异步任务的注册、进度查询、取消机制，供 B4 和 D4 复用。

**涉及文件：**
- `modules/job_system/job_manager.py` — 新建
- `tests/unit/job_system/test_job_manager.py` — 新建

**核心接口：**
```python
class JobManager:
    def submit(self, job_type: str, fn: Callable, *args) -> str:
        """提交异步任务，返回 job_id。内部用 ThreadPoolExecutor。"""
    def get_status(self, job_id: str) -> Dict[str, Any]:
        """返回 {status, progress_pct, result, error}。"""
    def cancel(self, job_id: str) -> bool:
        """请求取消（设置 cancel flag，任务自行检查）。"""
    def cleanup_expired(self, max_age_s: int = 3600) -> int:
        """清理超过 max_age_s 的已完成 Job。"""
```

**验收标准：**
- [ ] submit → 返回 job_id（UUID）
- [ ] get_status → pending / running / done / failed / cancelled
- [ ] progress 更新：任务内调用 `job_manager.update_progress(job_id, pct)`
- [ ] cancel：设置标志位，不强制 kill 线程
- [ ] 线程安全：Lock 保护 job registry
- [ ] **architecture.md 同步更新**：将 `job_system/` 模块注册到架构文档模块清单
- [ ] UT 5 条: submit_returns_id / status_lifecycle / progress_update / cancel / cleanup
- [ ] CHANGELOG.md 更新

**依赖项：** 无

---

### A1: MCP 评审工具组 — review session + comments + reedit

**目标：** 让 AI Agent 通过 MCP 完整操控评审流程：创建 session、添加/查看评论、触发 AI reedit。

**涉及文件：**
- `modules/mcp_server/tools/review_tools.py` — 新建
- `modules/mcp_server/server.py` — 扩展注册
- `tests/unit/mcp_server/test_review_tools.py` — 新建

**工具列表：**

| Tool | 说明 | 对应 API |
|------|------|---------|
| `review_init` | 创建评审 session | POST /api/review/init |
| `review_add_comment` | 添加评论 | POST /api/review/{id}/comments |
| `review_resolve_comment` | 标记评论已解决 | PATCH /api/review/comments/{id} |
| `review_ai_reedit` | 触发 AI 重编辑 | POST /api/review/{id}/ai-reedit |
| `review_ai_reedit_dry_run` | AI 重编辑预览（dry-run） | POST /api/review/{id}/ai-reedit/dry-run |
| `review_export_comments` | 导出评论 | GET /api/review/{id}/comments/export |

> ⚠️ 审计修正 V1.2：`review_get_state` 和 `review_list_comments` 移入 A4 只读查询工具组，
> 消除与 `review_query_state` / `review_query_comments` 的端点重叠。

**验收标准：**
- [ ] 6 个评审操作工具全部注册到 FastMCP
- [ ] 工具参数类型正确（project_dir: str, session_id: str 等）
- [ ] 复用 `_call_backend()` / `_post()` 模式
- [ ] review_init 返回 session_id
- [ ] review_add_comment 支持 visual_context 可选参数
- [ ] 错误响应传递后端错误信息（不吞异常）
- [ ] UT 5 条: init / add_comment / resolve / reedit / export
- [ ] CHANGELOG.md 更新

**依赖项：** 无
**已知约束：** 复用现有 `_call_backend` 模式，通过 HTTP 调用 Flask 后端

---

### A2: MCP VLM 工具组 — describe + diagnose

**目标：** 让 AI Agent 通过 MCP 调用 VLM 画面分析和诊断。

**涉及文件：**
- `modules/mcp_server/tools/vlm_tools.py` — 新建
- `tests/unit/mcp_server/test_vlm_tools.py` — 新建

**工具列表：**

| Tool | 说明 | 对应 API |
|------|------|---------|
| `vlm_describe_region` | 分析画笔区域 | POST /api/review/{id}/vlm/describe |
| `vlm_diagnose_frame` | 运行帧诊断（同步） | POST /api/review/{id}/vlm/diagnose |
| `vlm_status` | VLM 可用性 | GET /api/vlm/status |

> ⚠️ 审计修正 V1.2：`vlm_get_diagnostics` 移入 A4（`review_query_diagnostics`），消除端点重叠。
> `vlm_diagnose_frame` 实际端点为同步返回（非异步 job_id），修正描述。

**验收标准：**
- [ ] vlm_describe_region 接受 base64 帧 + strokes JSON
- [ ] vlm_diagnose_frame 为**同步**调用（直接返回诊断结果，无 job_id）
- [ ] vlm_status 返回 provider + available 状态
- [ ] 图像大小验证（10MB 限制传递到 MCP 工具层）
- [ ] UT 3 条: describe / diagnose / status
- [ ] CHANGELOG.md 更新

**依赖项：** 无（VLM API 端点已存在）

---

### A3: MCP 增强工具组 — audio/tts/bgm/transition

**目标：** 让 AI Agent 通过 MCP 调用 v0.16 增强能力。

**涉及文件：**
- `modules/mcp_server/tools/enhance_tools.py` — 新建
- `tests/unit/mcp_server/test_enhance_tools.py` — 新建

**工具列表：**

| Tool | 说明 | 对应 API |
|------|------|---------|
| `enhance_audio` | 音频增强（降噪/EQ/压缩/响度） | POST /api/review/enhance/audio（session_id 在 JSON body 中） |
| `enhance_tts` | 文字转语音 | POST /api/review/enhance/tts（session_id 在 JSON body 中） |
| `enhance_bgm` | BGM 选择 + 节拍对齐 | POST /api/review/enhance/bgm（session_id 在 JSON body 中） |
| `enhance_transition` | 添加转场效果 | POST /api/review/enhance/transition（单数，session_id 在 JSON body 中） |

> ⚠️ 审计修正：移除 `enhance_style`（`POST /api/review/{id}/style/apply` 端点不存在）。
> ⚠️ 审计修正：enhance 路由的 session_id 在 JSON body 中传递，非 URL path。端点路径为 `/api/review/enhance/*`，不含 `{id}`。

**验收标准：**
- [ ] 4 个增强工具全部注册
- [ ] enhance_audio 传递 session_id + denoise/eq/compressor 参数
- [ ] enhance_tts 支持 session_id + voice/text/language 参数
- [ ] enhance_transition 用单数（匹配实际路由 `/enhance/transition`）
- [ ] 输出路径白名单保护（security.py 扩展）
- [ ] UT 4 条: audio / tts / bgm / transition
- [ ] CHANGELOG.md 更新

**依赖项：** 无（增强 API 端点已存在）

---

### A4: MCP 只读查询工具组 — session state + diagnostics

> ⚠️ 审计修正（X1）：FastMCP 0.9 不支持 `@mcp.resource()` 装饰器（需 2.x+）。
> 改为以只读 Tool 形式暴露相同数据，复用 `_get()` 模式。

**目标：** 以 MCP 只读 Tool 形式暴露评审 session 状态和诊断结果，供 Agent 读取上下文。

**涉及文件：**
- `modules/mcp_server/tools/review_query_tools.py` — 新建
- `modules/mcp_server/server.py` — 注册只读工具
- `tests/unit/mcp_server/test_review_query_tools.py` — 新建

**工具列表：**

| Tool | 说明 | 对应 API |
|------|------|---------|
| `review_query_state` | 获取 Session 元数据 + 当前版本 | GET /api/review/{id}/state |
| `review_query_comments` | 获取评论列表 | GET /api/review/{id}/comments |
| `review_query_diagnostics` | 获取 VLM 诊断结果 | GET /api/review/{id}/vlm/diagnostics |
| `review_query_versions` | 获取版本历史 | GET /api/review/{id}/versions |

**验收标准：**
- [ ] 4 个只读查询工具注册到 FastMCP（普通 `@mcp.tool()` 装饰器）
- [ ] 复用 `_get()` 调用模式（同 capability_tools.py）
- [ ] 返回 JSON dict，统一 error/success 格式
- [ ] session_id 不存在 → 错误信息传递（不吞异常）
- [ ] 安全等级标记为 READ（A5 权限分级）
- [ ] UT 4 条: state / comments / diagnostics / versions
- [ ] CHANGELOG.md 更新

**依赖项：** A1（评审工具需先可用）

---

### A5: MCP 安全升级 — 工具权限分级 + 审计日志

**目标：** 对 MCP 工具按读/写/危险操作分级，记录审计日志。

**涉及文件：**
- `modules/mcp_server/security.py` — 扩展
- `tests/unit/mcp_server/test_security.py` — 扩展

**安全等级：**

| 等级 | 工具类型 | 示例 |
|------|---------|------|
| READ | 查询/列出/状态 | review_list_comments, vlm_status |
| WRITE | 创建/修改 | review_add_comment, enhance_audio |
| DANGEROUS | 删除/覆盖 | 无（MCP 不暴露删除操作） |

**验收标准：**
- [ ] 工具元数据增加 `permission_level` 字段
- [ ] 审计日志：每次工具调用记录 timestamp + tool_name + args_hash + result_status
- [ ] 审计日志写入 `data/mcp_audit.jsonl`
- [ ] 路径白名单扩展：覆盖 review session 输出目录
- [ ] UT 4 条: permission_tag / audit_logged / path_whitelist / no_delete_exposed
- [ ] CHANGELOG.md 更新

**依赖项：** A1-A3

---

### A6: MCP 集成测试 + Claude Desktop 验证

**目标：** 端到端验证：FastMCP Server 启动 → 工具发现 → 调用 → 结果。

**涉及文件：**
- `tests/integration/test_mcp_server_flow.py` — 新建（审计修正 M1：集成测试命名规范 `*_flow.py`）
- `modules/mcp_server/README.md` — 更新 Claude Desktop 配置指南

**验收标准：**
- [ ] FastMCP server 可启动（`python -m modules.mcp_server.server`）
- [ ] 工具发现：验证 tool_list 包含全部 29 个工具（12 旧 + 17 新：A1×6 + A2×3 + A3×4 + A4×4）
- [ ] 评审链路：review_init → review_add_comment → review_list_comments
- [ ] VLM 链路：vlm_status → vlm_describe_region（mock 后端）
- [ ] 安全验证：路径白名单拦截 `..` 遍历
- [ ] README 更新：新增工具列表 + 配置示例
- [ ] UT 5 条: server_starts / tool_discovery / review_chain / vlm_chain / security
- [ ] CHANGELOG.md 更新

**依赖项：** A1-A5

---

### B1: FrameSampler — 关键帧采样策略

**目标：** 从视频中智能提取关键帧，平衡分析质量和性能。

**涉及文件：**
- `modules/review_engine/frame_sampler.py` — 新建
- `modules/review_engine/contracts.py` — 扩展：添加 SampledFrame / StreamAnalysis / SceneSummary 数据类（审计修正 M6）
- `tests/unit/review_engine/test_frame_sampler.py` — 新建

> ⚠️ 审计修正（M7，V1.2 更正归属）：项目中已有 3 处重复的帧提取逻辑：
> `scene_segmenter.py:_extract_thumbnail` (L177)、`scene_selector.py:_extract_frame` (L155)、
> `thumbnail_generator.py` (L114+，sprite sheet 模式)。
> B1 的 `frame_sampler.py` 应提供统一的 `extract_frame(video_path, timestamp_ms) -> PIL.Image` 函数，
> 并在后续版本中让其他模块统一调用。

**采样策略：**
1. **场景边界采样**：复用 scene_segmenter 的边界点，每个场景取首帧
2. **均匀采样**：按时间间隔均匀采样（默认每 5s 一帧，可配置）
3. **混合模式**（默认）：场景边界 + 场景内每 10s 补充采样
4. **密度控制**：`max_frames` 上限（默认 50），超出时自动降低密度

**输入：** `video_path: str`, `strategy: str`, `max_frames: int`, `scene_boundaries: Optional[List[int]]`
**输出：** `List[SampledFrame]` where `SampledFrame = {frame: PIL.Image, timestamp_ms: int, scene_idx: int, source: str}`

**验收标准：**
- [ ] 三种采样策略：scene_boundary / uniform / hybrid
- [ ] FFmpeg 帧提取：`ffmpeg -ss {ts} -i {path} -vframes 1 -f image2pipe`
- [ ] max_frames 限制（超出时均匀抽稀）
- [ ] 空视频 / 无法读取 → 返回空列表 + 日志
- [ ] 帧缓存：同一视频同一时间戳不重复提取
- [ ] UT 5 条: scene_boundary / uniform / hybrid / max_cap / empty_video
- [ ] CHANGELOG.md 更新

**依赖项：** 无
**已知约束：** FFmpeg 帧提取约 50-200ms/帧，50 帧视频约 5-10s

---

### B2: VideoStreamAnalyzer — 跨帧时序分析

**目标：** 分析相邻帧之间的视觉关系，检测时序问题。

> ⚠️ 审计修正（X6）：`frame_diagnostics.py:check_continuity()` (L187-246) 已实现亮度跳变
> (BRIGHTNESS_JUMP_RATIO=0.30) 和色温跳变 (COLOR_TEMP_SHIFT_H=15) 检测。
> B2 必须委托调用 `check_continuity()`，**不得重新实现**这两个算法。

**涉及文件：**
- `modules/review_engine/video_stream_analyzer.py` — 新建
- `tests/unit/review_engine/test_video_stream_analyzer.py` — 新建

**分析维度：**

| 维度 | 方法 | VLM 依赖 |
|------|------|---------|
| 色温一致性 | **委托 `check_continuity()`**（已有 COLOR_TEMP_SHIFT_H=15） | 否 |
| 亮度一致性 | **委托 `check_continuity()`**（已有 BRIGHTNESS_JUMP_RATIO=0.30） | 否 |
| 场景转场质量 | 相邻帧差异 + VLM 评价 | 可选 |
| 视觉叙事弧线 | 帧描述序列 → 叙事分析 | 是 |

**输入：** `frames: List[SampledFrame]`, `vlm_adapter: Optional`
**输出：** `StreamAnalysis {issues: List[StreamIssue], narrative_arc: str, scene_descriptions: Dict[int, str]}`

**实现要点：**
```python
from modules.review_engine.frame_diagnostics import FrameDiagnostics

# check_continuity 是 FrameDiagnostics 的实例方法，非模块函数
diag = FrameDiagnostics(vlm_adapter=None)  # 连续性检测不需要 VLM
# 签名: check_continuity(self, frames: List[Any], scene_indices: Optional[List[int]]) -> List[ContinuityIssue]
continuity_issues = diag.check_continuity(frames_as_images, scene_indices=scene_idx_list)
# ContinuityIssue → StreamIssue 类型映射（B2 需实现适配）
# 仅新增：跨场景转场质量 + 叙事弧线（check_continuity 不覆盖的部分）
```

**验收标准：**
- [ ] 色温/亮度一致性：**委托 `check_continuity()`**，不重复实现
- [ ] 场景转场质量：VLM 可用时增强，不可用时仅用算法
- [ ] 叙事弧线：VLM 可用时生成自然语言摘要，不可用时返回 "VLM 不可用"
- [ ] 批量 VLM 调用：串行 + 超时控制（每帧 10s 上限）
- [ ] UT 5 条: delegates_to_check_continuity / transition_quality / narrative_with_vlm / narrative_without_vlm / timeout
- [ ] CHANGELOG.md 更新

**依赖项：** B1

---

### B3: SceneSummarizer — 场景级描述聚合

**目标：** 将同一场景的多帧描述聚合为一段连贯的场景摘要。

**涉及文件：**
- `modules/review_engine/scene_summarizer.py` — 新建
- `tests/unit/review_engine/test_scene_summarizer.py` — 新建

**聚合策略：**
1. 同场景多帧描述 → 去重 + 合并关键对象
2. 选取"最具代表性"描述（objects 最多的帧）
3. VLM 可用时：多帧描述 → LLM 生成一句话摘要
4. VLM 不可用时：取首帧描述作为场景摘要

**输入：** `analysis: StreamAnalysis`, `vlm_adapter: Optional`
**输出：** `Dict[int, SceneSummary]` where `SceneSummary = {scene_idx, summary, key_objects, duration_ms, representative_frame_ms}`

**验收标准：**
- [ ] 多帧描述去重合并
- [ ] 代表帧选择：对象数最多的帧
- [ ] VLM 摘要：多描述 → 一句话
- [ ] VLM 降级：取首帧描述
- [ ] 空场景 → 跳过
- [ ] UT 4 条: merge_descriptions / representative_frame / vlm_summary / degradation
- [ ] CHANGELOG.md 更新

**依赖项：** B2

---

### B4a: 视频流分析 API — 3 个后端端点

> ⚠️ 审计修正（F-1）：原 B4 拆分为 B4a(API) + B4b(UI)，降低单任务跨层复杂度。

**目标：** 暴露视频流分析的 HTTP 端点，复用 X0 JobManager 提供异步模式。

**涉及文件：**
- `modules/app_api/routes/vlm_routes.py` — 扩展
- `tests/api/test_vlm_stream_api.py` — 新建

**新增端点：**

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/review/{id}/vlm/analyze-stream` | 触发视频流分析（异步） |
| GET | `/api/review/{id}/vlm/stream-analysis` | 获取流分析结果 |
| GET | `/api/review/{id}/vlm/scene-summaries` | 获取场景摘要 |

**验收标准：**
- [ ] POST analyze-stream 返回 202 + job_id（**复用 X0 JobManager**）
- [ ] GET stream-analysis 返回 StreamAnalysis JSON
- [ ] GET scene-summaries 返回 Dict[scene_idx, SceneSummary]
- [ ] **错误响应包含 timestamp + trace_id**（coding-standards.md 要求）
- [ ] 分析进度反馈（N/M 帧已分析）通过 JobManager.update_progress
- [ ] UT 3 条: api_trigger / api_result / api_progress
- [ ] CHANGELOG.md 更新

**依赖项：** B1-B3, X0（异步 Job 基础设施）

---

### B4b: 视频流分析 UI — DiagnosticsPanel + Store 扩展

**目标：** 在评审面板中集成视频流分析的前端展示。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/DiagnosticsPanel.vue` — 扩展
- `apps/desktop/ui-vue/src/stores/review.js` — 扩展

**验收标准：**
- [ ] DiagnosticsPanel 新增"视频流分析"Tab
- [ ] Tab 内容：场景摘要列表 + 叙事弧线文字 + 问题标记
- [ ] review.js 新增 `streamAnalysis` / `sceneSummaries` 状态字段
- [ ] 从 B4a API 加载数据（GET stream-analysis + GET scene-summaries）
- [ ] 分析中状态：显示进度（N/M 帧）
- [ ] UT 2 条: panel_tab / store_state
- [ ] CHANGELOG.md 更新

**依赖项：** B4a

---

### B5: 视频流分析集成测试

**目标：** 端到端验证：video_path → 采样 → 分析 → 聚合 → API 返回。

**涉及文件：**
- `tests/integration/test_video_stream_flow.py` — 新建（审计修正 M1）

**验收标准：**
- [ ] 完整链路：mock 视频 → FrameSampler → VideoStreamAnalyzer(stub VLM) → SceneSummarizer
- [ ] 降级路径：VLM 不可用 → 纯算法分析仍有结果
- [ ] API 集成：POST analyze-stream → GET stream-analysis
- [ ] 性能：50 帧分析 < 30s（stub VLM）
- [ ] 全量回归：现有测试无新增失败
- [ ] UT 5 条: e2e_pipeline / degradation / api_chain / performance / regression
- [ ] CHANGELOG.md 更新

**依赖项：** B1-B4b

---

### C1: Timeline 数据模型 + TimelineStore

**目标：** 定义多轨时间线数据模型，并实现 SQLite 持久化。

**涉及文件：**
- `modules/review_engine/timeline_store.py` — 新建
- `modules/review_engine/contracts.py` — 扩展数据类
- `tests/unit/review_engine/test_timeline_store.py` — 新建

**数据模型：**
```python
# Timeline → 1:N → Track → 1:N → Clip
# 存储为两张 SQLite 表：timeline_tracks + timeline_clips
```

**DDL：**
```sql
CREATE TABLE IF NOT EXISTS timeline_tracks (
    track_id TEXT PRIMARY KEY,
    timeline_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    track_type TEXT NOT NULL,  -- video/audio/subtitle/effect
    label TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    muted INTEGER DEFAULT 0,
    locked INTEGER DEFAULT 0,
    volume REAL DEFAULT 1.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_clips (
    clip_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    source_path TEXT DEFAULT '',
    source_in_ms INTEGER DEFAULT 0,
    source_out_ms INTEGER DEFAULT 0,
    label TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',  -- JSON for effect params etc.
    FOREIGN KEY (track_id) REFERENCES timeline_tracks(track_id)
);
```

**验收标准：**
- [ ] Timeline / TimelineTrack / Clip dataclass 定义
- [ ] TimelineStore: create_timeline, get_timeline, delete_timeline
- [ ] TimelineStore: add_track, get_tracks, update_track, remove_track
- [ ] TimelineStore: add_clip, get_clips, update_clip, remove_clip
- [ ] 从 ReviewStore 复用 DB 连接（同一 SQLite 文件）
- [ ] **`PRAGMA journal_mode=WAL` 在连接初始化时设置**（审计修正 H2：防止并发写入时 `database is locked`）
- [ ] 自动 migration：表不存在时创建
- [ ] UT 6 条: create_timeline / add_track / add_clip / update_clip / remove / migration
- [ ] CHANGELOG.md 更新

**依赖项：** 无

---

### C2: TimelineOps — 轨道操作（增删/重排/锁定/静音）

**目标：** 封装轨道级别的业务操作。

**涉及文件：**
- `modules/review_engine/timeline_ops.py` — 新建
- `modules/review_engine/exceptions.py` — 扩展：添加 LockedTrackError（继承 VideoEditorError）
- `tests/unit/review_engine/test_timeline_ops.py` — 新建

**操作列表：**

| 操作 | 方法 | 约束 |
|------|------|------|
| 添加轨道 | `add_track(timeline_id, track_type, label)` | 同类型轨道最多 4 条 |
| 删除轨道 | `remove_track(track_id)` | 锁定轨道不可删除 |
| 重排序 | `reorder_tracks(timeline_id, track_ids)` | 更新 sort_order |
| 锁定/解锁 | `toggle_lock(track_id)` | 锁定后片段不可编辑 |
| 静音/取消静音 | `toggle_mute(track_id)` | 仅 audio 轨道有效 |
| 设置音量 | `set_volume(track_id, volume)` | 仅 audio 轨道，0.0-2.0 |

**验收标准：**
- [ ] 6 个操作全部实现
- [ ] 轨道类型限制：video ≤ 4, audio ≤ 4, subtitle ≤ 2, effect ≤ 2
- [ ] 锁定轨道保护：删除/编辑 → raise LockedTrackError
- [ ] **LockedTrackError 定义在 `review_engine/exceptions.py`**（审计修正 H5：继承 VideoEditorError，符合 coding-standards.md）
- [ ] 静音仅限 audio 轨道
- [ ] UT 6 条: add / remove / reorder / lock / mute / volume
- [ ] CHANGELOG.md 更新

**依赖项：** C1

---

### C3: TimelineOps — 片段操作（移动/裁剪/分割/跨轨）

**目标：** 封装片段级别的编辑操作。

**涉及文件：**
- `modules/review_engine/timeline_ops.py` — 扩展
- `tests/unit/review_engine/test_timeline_clip_ops.py` — 新建

**操作列表：**

| 操作 | 方法 | 约束 |
|------|------|------|
| 移动片段 | `move_clip(clip_id, new_start_ms)` | 不可超出轨道范围 |
| 裁剪片段 | `trim_clip(clip_id, in_ms, out_ms)` | 修改 source_in/out |
| 分割片段 | `split_clip(clip_id, at_ms)` | 返回两个新 clip_id |
| 删除片段 | `remove_clip(clip_id)` | 锁定轨道上的片段不可删 |
| 跨轨移动 | `move_clip_to_track(clip_id, target_track_id)` | 同类型轨道间 |
| 重叠检测 | `check_overlap(track_id)` | video 轨不允许重叠 |

**验收标准：**
- [ ] 6 个操作全部实现
- [ ] 分割：at_ms 必须在 clip 的 start_ms ~ end_ms 之间
- [ ] 跨轨移动：仅同类型轨道（video↔video, audio↔audio）
- [ ] video 轨重叠检测：重叠 → 自动推移后续片段（ripple edit）
- [ ] audio 轨允许重叠（混音）
- [ ] 锁定轨道保护
- [ ] UT 7 条: move / trim / split / remove / cross_track / overlap_ripple / locked_protection
- [ ] CHANGELOG.md 更新

**依赖项：** C1

---

### C4: Timeline API 端点

**目标：** 暴露多轨时间线的 HTTP CRUD 端点。

**涉及文件：**
- `modules/app_api/routes/timeline_routes.py` — 扩展
- `tests/api/test_timeline_api.py` — 新建

**端点列表：**

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/review/{id}/timeline` | 创建多轨时间线 |
| GET | `/api/review/{id}/timeline` | 获取完整时间线 |
| POST | `/api/review/{id}/timeline/tracks` | 添加轨道 |
| PATCH | `/api/review/{id}/timeline/tracks/{track_id}` | 更新轨道属性 |
| DELETE | `/api/review/{id}/timeline/tracks/{track_id}` | 删除轨道 |
| POST | `/api/review/{id}/timeline/clips` | 添加片段 |
| PATCH | `/api/review/{id}/timeline/clips/{clip_id}` | 更新片段 |
| DELETE | `/api/review/{id}/timeline/clips/{clip_id}` | 删除片段 |
| POST | `/api/review/{id}/timeline/clips/{clip_id}/split` | 分割片段 |

**验收标准：**
- [ ] 9 个端点全部实现
- [ ] 统一错误格式（复用 _error_response），**错误响应包含 timestamp + trace_id**（审计修正 M4：coding-standards.md 要求）
- [ ] 锁定轨道操作 → 403
- [ ] 分割返回两个新 clip 的 ID
- [ ] 全时间线 GET 返回嵌套结构 {tracks: [{clips: [...]}]}
- [ ] **双 API 共存迁移**（审计修正 H6）：旧 `GET /api/timeline`（project 由 project_dir_getter 提供）保留但标注 deprecated，新多轨 API 在 `/api/review/{id}/timeline` 下
- [ ] UT 7 条: create / get / add_track / update_track / add_clip / split / locked_reject
- [ ] CHANGELOG.md 更新

**依赖项：** C1-C3

---

### C5: track_builder 升级 — 动态 Track[] 输出

**目标：** 将 track_builder.py 从 3 固定轨道升级为动态 Track[] 输出，兼容多轨模型。

**涉及文件：**
- `modules/exporters/track_builder.py` — 重构
- `tests/unit/exporters/test_track_builder.py` — 新建

**变更：**
```python
# 之前：返回 {"video": [...], "subtitle": [...], "audio": [...]}
# 之后：返回 List[TimelineTrack] 或保持 dict 但支持多轨
def build_tracks_from_script(script, config) -> Dict[str, List[Dict]]:
    # 保持向后兼容，但支持 config["extra_audio_tracks"] 等扩展
```

**验收标准：**
- [ ] 向后兼容：无 config 时输出格式不变
- [ ] 支持 config.extra_audio_tracks → 多音频轨
- [ ] 支持 config.extra_video_tracks → 画中画轨
- [ ] 输出可直接喂给 TimelineStore.import_tracks()
- [ ] UT 4 条: backward_compat / extra_audio / extra_video / import_to_store
- [ ] CHANGELOG.md 更新

**依赖项：** C1

---

### C6: 多轨时间线 UI — 扩展 components/timeline/ 体系

> ⚠️ 审计修正（X5）：`ReviewTimeline.vue` 是一个带 4 个 named slot 的 Shell 组件，不是轨道渲染器。
> 多轨 UI 组件已存在于 `components/timeline/` 目录树下（TimelinePanel.vue、TimelineTrackClips.vue 等）。
> C6 应扩展现有 `components/timeline/` 体系，而非重写 ReviewTimeline.vue。

**目标：** 扩展现有 `components/timeline/` 组件体系，支持多轨显示和操作。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/timeline/TimelinePanel.vue` — 扩展：多轨数据绑定
- `apps/desktop/ui-vue/src/components/timeline/TimelineTrackClips.vue` — 扩展：多轨道渲染
- `apps/desktop/ui-vue/src/components/timeline/TimelineTrackHeader.vue` — 新建：轨道头（锁定/静音/音量）
- `apps/desktop/ui-vue/src/stores/review.js` — 扩展 timeline 状态

**UI 设计：**
```
┌─ Track Header ─┬─ Clip Lane ──────────────────────┐
│ 🎬 V1  🔒 👁   │ [clip1] [clip2]   [clip3]        │
│ 🎬 V2          │      [pip-overlay]                │
│ 🔊 A1  🔇      │ ████████████████████████████████ │
│ 🔊 A2          │ ░░░░░░ BGM ░░░░░░░░░░░░░░░░░░░  │
│ 🅃 Sub          │ "Hello"  "World"   "Bye"          │
└─────────────────┴──────────────────────────────────┘
```

**验收标准：**
- [ ] 多轨道渲染：每个 track 独立行，带 header + clip lane
- [ ] Track header：类型图标 + label + 锁定/静音按钮
- [ ] Clip 渲染：按 start_ms/end_ms 定位在时间轴上
- [ ] 点击片段 → 选中高亮 + 属性面板
- [ ] 拖拽移动：片段可在同轨内拖拽
- [ ] 从 API 加载时间线数据
- [ ] UT 2 条: renders_tracks / click_selects
- [ ] CHANGELOG.md 更新

**依赖项：** C4

---

### C7: 多轨时间线集成测试

**目标：** 端到端验证：创建时间线 → 添加轨道/片段 → 操作 → 导出。

**涉及文件：**
- `tests/integration/test_timeline_flow.py` — 新建（审计修正 M1）

**验收标准：**
- [ ] 创建时间线 → 添加 2 video + 2 audio + 1 subtitle 轨道
- [ ] 每轨添加片段 → 移动/裁剪/分割操作
- [ ] 锁定轨道 → 操作被拒绝
- [ ] API 链路：POST create → POST add_track → POST add_clip → POST split → GET timeline
- [ ] track_builder 输出导入到 TimelineStore
- [ ] 全量回归：现有测试无新增失败
- [ ] UT 5 条: full_workflow / lock_protection / api_chain / import / regression
- [ ] CHANGELOG.md 更新

**依赖项：** C1-C6

---

### D1: 硬件检测扩展 — 解码能力探测 + HEVC 支持

**目标：** 扩展 detector.py，探测 FFmpeg 解码器列表（特别是 HEVC 硬解能力）。

**涉及文件：**
- `modules/hardware/detector.py` — 扩展
- `modules/hardware/encoding_strategy.py` — 扩展：新增 `choose_decoder()` 解码策略
- `tests/unit/hardware/test_detector.py` — 扩展

**新增检测项：**

| 检测项 | 方法 | 输出 |
|--------|------|------|
| FFmpeg 解码器列表 | `ffmpeg -decoders` | List[str] |
| HEVC 硬解可用 | 检查 `hevc_videotoolbox` / `hevc_cuvid` | bool |
| 可用 hwaccel 列表 | `ffmpeg -hwaccels` | 已有，确认完整 |

**HardwareProfile 扩展：**
```python
@dataclass(frozen=True)
class HardwareProfile:
    # ... 已有字段 ...
    ffmpeg_decoders: List[str] = field(default_factory=list)  # 新增
    has_hevc_hw_decode: bool = False                          # 新增
```

**验收标准：**
- [ ] `detect_decoders()` → 解码器名称列表
- [ ] HEVC 硬解检测：`hevc_videotoolbox` (macOS) / `hevc_cuvid` (NVIDIA)
- [ ] `encoding_strategy.py` 新增 `choose_decoder(profile, input_codec)` → 返回 hwaccel + decoder 参数
- [ ] 向后兼容：旧代码不受影响
- [ ] **architecture.md 同步更新**（D-009）：将 `hardware/` 模块注册到架构文档模块清单
- [ ] 检测失败 → 安全默认值（空列表，False）
- [ ] UT 4 条: decoders_detected / hevc_hw / fallback_empty / backward_compat
- [ ] CHANGELOG.md 更新

**依赖项：** 无

---

### D2: render_pipeline 接入硬件加速

> ⚠️ 审计修正（X4）：`auto_render.py` 已有完整的硬件加速链路 —
> `apply_hardware_profile()` → `get_system_profile()` → `choose_encoder()` → `_encoder_args()` 已 wired。
> D2 的实际缺口仅在 `render_pipeline.py`，其 `_transcode_segment()` 硬编码 `libx264 -preset fast -crf 23`。
> auto_render.py 从 D2 范围中移除。

**目标：** 将 encoding_strategy.py 的输出接入 render_pipeline.py 的渲染命令（auto_render.py 已完成，不在范围内）。

**涉及文件：**
- `modules/review_engine/render_pipeline.py` — 扩展：接入 HardwareProfile + EncodingParams
- `tests/unit/review_engine/test_render_pipeline_hwaccel.py` — 新建

**改动要点：**
1. ~~auto_render.py~~（已 wired，无需改动）
2. render_pipeline.py `_transcode_segment()` 前置：检测 HardwareProfile → choose_encoder → 注入参数
3. HEVC 输入自动检测：输入为 HEVC → 加 `-hwaccel videotoolbox` 解码
4. 非 CRF 模式：硬件编码器不支持 CRF → 切换为 `-b:v` 码率模式

**验收标准：**
- [ ] render_pipeline `_transcode_segment()` 不再硬编码 libx264
- [ ] render_pipeline 构建的 FFmpeg 命令包含 `-hwaccel` 参数（当硬件可用时）
- [ ] HEVC 输入自动使用硬件解码（如可用）
- [ ] 硬件编码器不支持 CRF → 自动切换码率模式
- [ ] CPU fallback：硬件不可用 → 回退 libx264 + CRF（保持现有行为）
- [ ] UT 5 条: pipeline_cmd_has_hwaccel / hevc_input_decode / crf_to_bitrate / cpu_fallback / encoder_label
- [ ] CHANGELOG.md 更新

**依赖项：** D1

---

### D3: RenderManager — 分段并行渲染调度

**目标：** 将时间线片段分配到多个并行 FFmpeg 进程，提升渲染速度。

> ⚠️ 审计修正（H3）：按 architecture.md 四层架构，`hardware/` 属于 Infrastructure 层（检测+策略），
> 而 RenderManager 是 Business 层逻辑（调度渲染任务）。应放在 `modules/render_engine/` 新目录下。
>
> ⚠️ 审计修正（H4）：RenderManager 接收 `List[Clip]`（C1 定义），但 render_pipeline 使用
> `Segment`（contracts.py 已有定义，含 source_path/start_ms/end_ms）。需提供 `Clip→Segment` 适配器。

**涉及文件：**
- `modules/render_engine/__init__.py` — 新建目录
- `modules/render_engine/render_manager.py` — 新建（不在 hardware/ 下）
- `tests/unit/render_engine/__init__.py` — 新建
- `tests/unit/render_engine/test_render_manager.py` — 新建

**架构：**
```python
from modules.review_engine.contracts import Segment

class RenderManager:
    def __init__(self, profile: HardwareProfile): ...

    @staticmethod
    def clip_to_segment(clip: Clip) -> Segment:
        """Clip (timeline model) → Segment (render contract) 适配器。"""
        return Segment(
            source_path=clip.source_path,
            start_ms=clip.source_in_ms,
            end_ms=clip.source_out_ms,
        )

    def render_timeline(
        self,
        clips: List[Clip],
        config: RenderConfig,
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """渲染完整时间线 → 输出文件路径。"""
        segments = [self.clip_to_segment(c) for c in clips]
        # 1. 分段：每个 Segment → 独立渲染任务
        # 2. 并行：ThreadPoolExecutor(max_workers=suggest_max_concurrent())
        # 3. 每段完成 → progress_callback(segment_idx, total)
        # 4. concat：所有分段 → 最终输出（FFmpeg concat demuxer）
```

**验收标准：**
- [ ] RenderManager 位于 `modules/render_engine/`（非 hardware/）
- [ ] **architecture.md 同步更新**（D-009）：将 `render_engine/` 模块注册到架构文档模块清单（Business 层）
- [ ] Clip→Segment 适配器：`clip_to_segment()` 方法
- [ ] 分段渲染：每个 Segment 独立 FFmpeg 进程
- [ ] 并行度：由 `suggest_max_concurrent()` 控制
- [ ] 进度回调：每段完成时调用
- [ ] 错误处理：单段失败 → 重试 1 次 → 仍失败 → 整体失败 + 清理临时文件
- [ ] concat 合并：使用 FFmpeg concat demuxer
- [ ] UT 6 条: clip_to_segment / parallel_render / progress_callback / segment_failure / concat / cleanup
- [ ] CHANGELOG.md 更新

**依赖项：** D2

---

### D4a: 渲染进度 API — 3 个后端端点

> ⚠️ 审计修正（F-2）：原 D4 拆分为 D4a(API) + D4b(UI)，降低单任务跨层复杂度。

**目标：** 暴露渲染进度的实时查询端点，复用 X0 JobManager 提供异步模式。

**涉及文件：**
- `modules/app_api/routes/render_routes.py` — 新建
- `tests/api/test_render_api.py` — 新建

**端点列表：**

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/review/{id}/render` | 触发渲染（异步） |
| GET | `/api/review/{id}/render/progress` | 查询渲染进度 |
| POST | `/api/review/{id}/render/cancel` | 取消渲染 |

**进度格式：**
```json
{
  "status": "rendering",
  "segments_total": 8,
  "segments_done": 3,
  "percent": 37.5,
  "encoder": "Apple VideoToolbox (hardware)",
  "elapsed_s": 12.3,
  "eta_s": 20.1
}
```

**验收标准：**
- [ ] POST render 返回 202 + job_id（**复用 X0 JobManager**）
- [ ] GET progress 返回实时进度 JSON
- [ ] POST cancel 终止渲染进程
- [ ] 渲染完成 → status="done" + output_path
- [ ] **错误响应包含 timestamp + trace_id**（审计修正 M4：coding-standards.md 要求）
- [ ] UT 4 条: trigger / progress / cancel / complete
- [ ] CHANGELOG.md 更新

**依赖项：** D3, X0（异步 Job 基础设施）

---

### D4b: 渲染进度 UI — RenderProgress.vue 前端进度条

**目标：** 前端渲染进度展示组件。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/RenderProgress.vue` — 新建

**验收标准：**
- [ ] 进度条组件：百分比 + 分段计数 + 编码器名 + ETA
- [ ] 从 D4a API 轮询进度（GET render/progress，可配置间隔）
- [ ] 取消按钮：调用 POST render/cancel
- [ ] 渲染完成 → 显示输出路径 + 打开按钮
- [ ] 渲染失败 → 显示错误信息
- [ ] UT 2 条: progress_display / cancel_button
- [ ] CHANGELOG.md 更新

**依赖项：** D4a

---

### D5: 渲染设置 UI — 编码器选择 + 质量/速度

**目标：** 设置页增加渲染配置项。

**涉及文件：**
- `apps/desktop/ui-vue/src/views/SettingsView.vue` — 扩展
- `modules/app_api/routes/settings_routes.py` — 扩展

**设置项：**

| 设置 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| 视频编码器 | 下拉 | 自动（跟随硬件检测） | 手动覆盖：libx264 / h264_videotoolbox / h264_nvenc |
| 质量预设 | 滑块 | 平衡 | 高质量(CRF 15) / 平衡(CRF 18) / 快速(CRF 23) |
| 分辨率 | 下拉 | 1080×1920 | 竖屏/横屏预设 |
| 并行渲染 | 开关 | 开 | 关闭=单线程顺序渲染 |
| 硬件信息 | 只读 | — | 显示检测到的 GPU + 编码器 |

**验收标准：**
- [ ] 编码器下拉：仅显示当前硬件支持的选项
- [ ] 质量滑块 → 映射到 CRF / 码率
- [ ] 硬件信息只读显示（调用 /api/system/hardware）
- [ ] 设置持久化到 settings
- [ ] UT 3 条: encoder_options / quality_mapping / persist
- [ ] CHANGELOG.md 更新

**依赖项：** D2

---

### D6: GPU 渲染集成测试 + 性能基准

**目标：** 端到端验证硬件加速渲染 + 性能对比基准。

**涉及文件：**
- `tests/integration/test_gpu_render_flow.py` — 新建（审计修正 M1）
- `tests/benchmark/test_render_benchmark.py` — 新建

**验收标准：**
- [ ] 检测 → 策略 → 渲染 全链路：HardwareProfile → EncodingParams → render_pipeline
- [ ] CPU fallback 路径：模拟无 GPU → libx264 正常渲染
- [ ] 硬件加速路径：有 VideoToolbox → h264_videotoolbox 渲染
- [ ] 并行渲染：4 段视频 → 2 并行 → concat → 成品
- [ ] 性能基准（仅记录，不 assert）：CPU vs GPU 渲染时间对比
- [ ] 全量回归：现有测试无新增失败
- [ ] UT 5 条: full_pipeline / cpu_fallback / hw_accel / parallel_concat / regression
- [ ] CHANGELOG.md 更新

**依赖项：** D1-D4

---

## 6. 依赖关系图

```
共享基础设施:
  X0 (异步 Job 管理器) ──→ B4a, D4a

Feature A: MCP Server 扩展
  A1 (评审操作) ──┐
  A2 (VLM 工具) ──┼── A5 (安全) ── A6 (集成测试)
  A3 (增强工具) ──┘
  A4 (只读查询) ◄── A1（依赖 A1 的 review session 端点）

Feature B: VLM 视频流
  B1 (采样器) → B2 (时序分析) → B3 (场景聚合) → B4a (API, ←X0) → B4b (UI) → B5 (集成测试)

Feature C: 多轨时间线
  C1 (数据模型) ──┬── C2 (轨道操作) ──┐
                  ├── C3 (片段操作) ──┼── C4 (API) → C6 (UI) → C7 (集成测试)
                  └── C5 (track_builder)    （C5 独立于 C4，仅依赖 C1）

Feature D: GPU 渲染
  D1 (检测扩展) → D2 (render_pipeline) → D3 (并行调度) → D4a (进度API, ←X0) → D4b (进度UI) → D6 (集成测试)
                                  └───→ D5 (设置UI)    （D5 依赖 D2，非 D3）

跨 Feature 依赖：仅 X0（B4a 和 D4a 共享异步 Job 基础设施）
```

## 7. 建议实施顺序

四个 Feature 可以完全并行开发。X0 是 B4/D4 的前置依赖，建议第 1 波完成。

| 波次 | 任务 | 说明 |
|------|------|------|
| 第 0 波 | X0 | 异步 Job 基础设施（B4a/D4a 的前置依赖） |
| 第 1 波 | A1, A2, A3, B1, C1, D1 | 各 Feature 的无依赖基础任务 |
| 第 2 波 | A4, A5, B2, C2, C3, C5, D2 | 依赖第 1 波的核心逻辑 |
| 第 3 波 | A6, B3→B4a, C4, D3→D4a, D5 | 后端 API 端点（B3/B4a、D3/D4a 波内有序） |
| 第 4 波 | B4b, B5, C6→C7, D4b, D6 | 前端 UI + 集成测试（C6/C7 波内有序） |

> ⚠️ 审计修正（M5）：每个波次完成后，运行 SMK（Smoke）测试确保核心路径不退化。
> 集成测试任务（A6/B5/C7/D6）中需包含回归验证。

单线程执行时的推荐路径：**X0 → A1→A2→A3→A4→A5→A6 → B1→B2→B3→B4a→B4b→B5 → C1→C2→C3→C4→C5→C6→C7 → D1→D2→D3→D4a→D4b→D5→D6**

> ⚠️ 审计修正（M8）：新建测试目录（`tests/unit/mcp_server/`、`tests/unit/job_system/`、
> `tests/unit/render_engine/`、`tests/api/`、`tests/benchmark/`）时必须创建 `__init__.py`，
> 否则 pytest 无法发现测试。每个任务创建新测试文件时需检查目标目录是否已有 `__init__.py`。

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| FastMCP API 变更（0.9→1.0） | MCP 工具注册方式变化 | 锁定 fastmcp>=0.9,<1.0；不使用 @mcp.resource（需 2.x） |
| MCP 模块 Python 3.10+ 约束 | 与项目 3.8+ 声明冲突 | MCP 模块独立标注 Python ≥ 3.10 约束 |
| VLM 批量调用性能（50 帧×5s/帧 = 250s） | 流分析时间过长 | max_frames 限制 + 并行 VLM 调用 |
| 多轨时间线 UI 复杂度高 | 前端开发周期长 | 先实现数据层+API，UI 分阶段 |
| 硬件编码器 CRF 不兼容 | 画质控制方式不同 | 自动切换码率模式 |
| FFmpeg 版本差异（hwaccel 参数） | 部分机器不兼容 | 运行时探测 + CPU 自动回退 |
| SQLite 并发写入（timeline + review 同库） | 锁等待 | WAL 模式（C1 验收标准）+ 短事务 |

## 9. 版本验收标准

- [ ] 27 个任务全部完成（X0×1 + A×6 + B×6 + C×7 + D×7）
- [ ] MCP Server 工具数 ≥ 29（12 旧 + 17 新：A1×6 操作 + A2×3 VLM + A3×4 增强 + A4×4 只读查询）
- [ ] 视频流分析端到端链路可演示
- [ ] 多轨时间线 CRUD 完整可用
- [ ] GPU 硬件加速渲染可用（macOS VideoToolbox 验证）
- [ ] CPU fallback 路径全部正常
- [ ] 新增测试全部通过
- [ ] 全量回归无新增失败（SMK 测试每波次通过）
- [ ] 性能基准记录（GPU vs CPU 渲染时间）
- [ ] CHANGELOG.md 全部更新

---

## 10. 完成状态跟踪（Completion Status Tracking）

> 审计修正（M2）：dev-governance.md 要求计划文档包含此章节。

| 任务ID | 任务名称 | 状态 | 完成日期 | 备注 |
|--------|---------|------|---------|------|
| X0 | 异步任务管理器 | Done | 2026-04-06 | 5 UT passed |
| A1 | MCP 评审操作工具组（6 工具） | Done | 2026-04-06 | 5 UT passed |
| A2 | MCP VLM 工具组（3 工具） | Done | 2026-04-06 | 3 UT passed |
| A3 | MCP 增强工具组 | Done | 2026-04-06 | 4 UT passed |
| A4 | MCP 只读查询工具组 | Planned | — | — |
| A5 | MCP 安全升级 | Planned | — | — |
| A6 | MCP 集成测试 | Planned | — | — |
| B1 | FrameSampler | Done | 2026-04-06 | 5 UT passed |
| B2 | VideoStreamAnalyzer | Planned | — | — |
| B3 | SceneSummarizer | Planned | — | — |
| B4a | 视频流分析 API（3 端点） | Planned | — | — |
| B4b | 视频流分析 UI（DiagnosticsPanel） | Planned | — | — |
| B5 | 视频流集成测试 | Planned | — | — |
| C1 | Timeline 数据模型 | Done | 2026-04-06 | 7 UT passed |
| C2 | 轨道操作 | Planned | — | — |
| C3 | 片段操作 | Planned | — | — |
| C4 | Timeline API | Planned | — | — |
| C5 | track_builder 升级 | Planned | — | — |
| C6 | 多轨 UI（components/timeline/） | Planned | — | — |
| C7 | 多轨集成测试 | Planned | — | — |
| D1 | 硬件检测扩展 | Done | 2026-04-06 | 6 UT passed |
| D2 | render_pipeline 硬件加速（auto_render 已 wired） | Planned | — | — |
| D3 | RenderManager | Planned | — | — |
| D4a | 渲染进度 API（3 端点） | Planned | — | — |
| D4b | 渲染进度 UI（RenderProgress.vue） | Planned | — | — |
| D5 | 渲染设置 UI | Planned | — | — |
| D6 | GPU 渲染集成测试 | Planned | — | — |

## 11. 变更日志（Change Log）

| 日期 | 变更内容 | 影响范围 |
|------|---------|---------|
| 2026-04-04 | V1.0 初版 | 全部 |
| 2026-04-04 | V1.1 审计修正 — 6 Critical + 7 High + 8 Medium 修复 | A3/A4/B1/B2/C1/C2/C4/C6/D2/D3/D4 + 新增 X0 |
| 2026-04-04 | V1.2 二次审计 — A1/A2/A4 工具去重 + 依赖图修正 + 8 处小修 | A1(8→6)/A2(4→3)/工具数 29/依赖图/C6 名称/D6/M7 归属 |
| 2026-04-04 | V1.3 三次审计终版 — B2 示例修正 + encoding_strategy→D1 + 波次有序化 + X0→job_system + §3.1/3.6 补全 + arch.md 同步 | B2/D1/D3/X0/C2/§3.1/§3.6/tree 格式 |
| 2026-04-06 | V1.4 原子性拆分 — B4→B4a(API)+B4b(UI)、D4→D4a(API)+D4b(UI)；任务总数 25→27；波次/依赖图/跟踪表同步更新 | B4/D4/§6/§7/§9/§10 |

## 12. 架构决策记录（Decisions）

| 编号 | 决策 | 原因 | 替代方案 |
|------|------|------|---------|
| D-001 | A4 用只读 Tool 替代 MCP Resource | FastMCP 0.9 不支持 @mcp.resource()，需 2.x+ | 升级到 FastMCP 2.x（风险高，API 不稳定） |
| D-002 | D2 仅改 render_pipeline.py，不改 auto_render.py | auto_render.py 已有完整硬件加速链路 | 重复 wire（浪费） |
| D-003 | RenderManager 放在 render_engine/ 而非 hardware/ | architecture.md 四层架构：hardware/ 是 Infrastructure 层 | 放在 hardware/（违反架构边界） |
| D-004 | B2 委托 check_continuity() 而非重新实现 | frame_diagnostics.py L187-246 已有亮度/色温检测 | 重写（代码重复） |
| D-005 | C6 扩展 components/timeline/ 而非重写 ReviewTimeline.vue | ReviewTimeline.vue 是 shell，多轨 UI 已在 timeline/ 下 | 重写 shell（破坏现有布局） |
| D-006 | 新增 X0 异步 Job 管理器 | B4/D4 都需要 202+job_id，项目无此基础设施 | 各自实现（代码重复） |
| D-007 | 移除 enhance_style 工具 | POST /api/review/{id}/style/apply 端点不存在 | 先创建端点（超出 v0.18 范围） |
| D-008 | X0 用 `job_system/` 而非 `infrastructure/` | `infrastructure` 与 architecture.md "基础设施层"概念冲突 | 放在 infrastructure/（名称歧义） |
| D-009 | `render_engine/` 和 `hardware/` 需补入 architecture.md | 两个模块目前未出现在架构文档模块清单中 | 编码阶段 D1/D3 任务中同步更新 |
