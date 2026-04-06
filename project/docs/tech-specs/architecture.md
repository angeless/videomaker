# VideoEditor 系统架构规范

**文档版本**：v1.0
**发布日期**：2026-03-19
**维护责任人**：产品 & 架构组
**最后更新**：2026-03-19

---

## 0. 文档定位与适用范围

### 0.1 文档目的

本文档定义 VideoEditor（桌面版短视频生产系统）的整体技术架构、模块边界、数据流、接入层和运行原则。

**文档作用**：
- 为新模块开发提供架构基线
- 明确模块间的依赖关系与通信方式
- 防止跨越模块边界造成的耦合污染
- 建立可扩展的模块化单体架构
- 为性能、安全、可维护性奠定基础

### 0.2 适用范围

- 所有核心业务模块开发与迭代
- 新功能模块设计与集成
- 接入层（API、CLI、GUI）扩展
- 数据层（存储、缓存）演进
- 工作流编排与调度

### 0.3 非适用范围

- 具体功能特性设计（见各模块 PRD）
- UI/UX 设计细节（见设计文档）
- 个别算法实现细节（见模块内部代码）
- 第三方依赖管理（见 requirements.txt）

---

## 1. 架构设计原则

### 1.1 模块化单体

- **物理隔离**：每个模块独占目录，独立 `__init__.py`
- **接口隔离**：模块间仅通过公开 API 调用，不直接访问私有实现
- **权限隔离**：核心模块（contracts、adapters、app_api）受开发规范保护

**执行机制**：
- 所有跨模块调用必须通过 adapters 层
- 不允许直接 import 其他模块的私有模块
- 破坏隔离的改动需经过 architecture review

### 1.2 可配置优先

- 任何硬编码行为都应抽象为配置项
- 默认配置应提供基线可用的初始值
- 配置变更不需重启（支持 hot reload）

**配置来源**（优先级从高到低）：
1. 环境变量（`VIDEOEDITOR_*`）
2. 项目配置文件（`project_config.json`）
3. 用户设置数据库（`settings.db`）
4. 系统默认配置（模块级常量）

### 1.3 可扩展优先

- 架构应支持在不破坏现有功能的前提下添加新能力
- 新增能力应尽可能通过能力模块（capabilities）而非修改步骤（steps）
- 新增适配器（adapters）不应触发现有模块代码改动

**扩展方式**：
- **纵向扩展**：增加新的 Step（step8、step9 等）
- **横向扩展**：增加新的 Capability（新能力模块）
- **适配器扩展**：增加新的输入/输出适配器

### 1.4 审计优先

所有关键操作必须可追踪、可重现、可回滚：

- 状态变更必须记录时间戳、操作者、变更原因
- 关键业务逻辑必须生成审计日志
- 任务执行必须支持重跑与幂等性
- 数据修改必须支持版本管理与冲突解决

---

## 2. 系统总体架构

### 2.1 四层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     接入层（Ingress Layer）                  │
│         Flask API + pywebview GUI + Agent API + CLI          │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   业务层（Business Layer）                   │
│  Step Pipeline + Capability Modules + Workflow Engine       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                 支撑层（Infrastructure Layer）               │
│  Adapters + Contracts + Registry + Library + NLE Handlers   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  数据层（Data Layer）                        │
│         SQLite + File System + Cache + External APIs        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心职责划分

| 层级 | 职责 | 包含模块 | 变动频率 |
|------|------|--------|--------|
| 接入层 | 路由、认证、会话、UI 协议 | app_api/server.py, launcher.py, routes/* | 中 |
| 业务层 | 核心工作流、能力组件、编排 | step1~7, capabilities/*, workflow_engine | 高 |
| 支撑层 | 模块间通信、数据定义、库管理、异步任务 | adapters, contracts, library, registry, job_system | 低 |
| 数据层 | 存储、缓存、外部服务 | SQLite, FileSystem, Redis (Future) | 低 |

---

## 3. 模块职责说明

### 3.1 Step Pipeline（步骤流水线）

Step Pipeline 是核心业务执行流。包含 7 个顺序步骤，每个步骤都是**可独立可视化、可单独运行、可独立审批的单元**。

#### 3.1.1 Step 1：素材分析（step1_material_analysis）

**[已实现]**

**职责**：
- 解析输入素材（视频文件），提取元数据
- 语音识别与转录
- 音频质量评估
- 视频资产分析（时长、分辨率、fps、codec）
- 语义指纹生成

**对外 API**：
```python
def analyze_videos(video_paths: List[str], config: Dict) -> Dict:
    """
    返回结构:
    {
        "videos": [
            {
                "path": str,
                "duration_s": float,
                "resolution": [int, int],
                "fps": float,
                "audio_languages": List[str],
                "transcript": {
                    "language": str,
                    "text": str,
                    "segments": List[Dict]
                },
                "audio_quality": {
                    "snr": float,
                    "noise_level": float,
                    "clarity_score": float
                },
                "semantic_fingerprint": str
            }
        ],
        "combined_duration_s": float,
        "total_materials_count": int
    }
    """
```

**关键子模块**：
- `transcribe.py`：语音识别（支持多语言）
- `audio_quality.py`：音频质量评估
- `video_asset_toolkit.py`：视频元数据提取
- `indexer/semantic.py`：语义指纹生成
- `indexer/fingerprint.py`：音频指纹

**输入**：视频文件目录路径
**输出**：`data/materials.json`（元数据集合）

**边界说明**：
- 不负责素材存储与库管理（库由 library 模块负责）
- 不负责素材关联与版本管理
- 不参与后续步骤的选题、脚本生成

---

#### 3.1.2 Step 2：选题规划（step2_topic_planning）

**[已实现]**

**职责**：
- 基于 Step1 的素材元数据与用户输入，生成多个备选选题（topic）
- 每个选题应包含：标题、描述、选题理由、目标受众、核心关键词
- 支持选题审核与反馈迭代

**对外 API**：
```python
def generate_topics(materials: Dict, config: Dict, context: Optional[Dict] = None) -> Dict:
    """
    返回结构:
    {
        "topics": [
            {
                "slug": str,           # 唯一标识
                "title": str,
                "description": str,
                "rationale": str,      # 选题理由
                "target_audience": str,
                "keywords": List[str],
                "tone": str,           # 语气风格
                "estimated_duration_s": float
            }
        ],
        "reasoning": str  # 选题策略说明
    }
    """
```

**输入**：Step1 输出的 materials.json + 用户选择
**输出**：`data/topics.json`（备选选题集合）

**审批流程**：用户在 UI 中选择满意的选题，调用 approve_step(2)

---

#### 3.1.3 Step 3：脚本生成（step3_script_generation）

**[已实现]**

**职责**：
- 基于选定选题生成完整脚本（narrative script）
- 脚本应包含：分镜头、配音文字、转场建议、字幕清单
- 支持脚本编辑与反馈调整

**对外 API**：
```python
def generate_script(topic: Dict, materials: Dict, config: Dict, context: Optional[Dict] = None) -> Dict:
    """
    返回结构:
    {
        "script": {
            "title": str,
            "sections": [
                {
                    "index": int,
                    "duration_s": float,
                    "voiceover": str,
                    "visual_description": str,
                    "transitions": str
                }
            ],
            "total_duration_s": float
        },
        "subtitles": [
            {
                "index": int,
                "start_s": float,
                "end_s": float,
                "text": str,
                "language": str
            }
        ],
        "keywords_timeline": Dict[float, List[str]],  # 时间轴关键词
        "metadata": {
            "generated_at": str,
            "model": str,
            "temperature": float
        }
    }
    """
```

**输入**：Step2 选定的 topic + Step1 的 materials
**输出**：`data/script.json`（完整脚本）

**关键子模块**：
- JSON 解析与兜底机制（处理 AI 模型返回的不规范 JSON）

---

#### 3.1.4 Step 4：素材匹配（step4_material_matching）

**[已实现]**

**职责**：
- 将脚本中的视觉描述与可用素材匹配
- 优先级匹配（精确 > 语义 > 备选）
- 脚本自适应改写（如果素材不足，改写脚本以适配现有素材）
- 生成素材覆盖率报告

**对外 API**：
```python
def match_materials(script: Dict, materials: Dict, matching_config: Dict, context: Optional[Dict] = None) -> Dict:
    """
    返回结构:
    {
        "matched_segments": [
            {
                "script_index": int,
                "script_description": str,
                "matched_material": {
                    "path": str,
                    "material_id": str,
                    "confidence": float,
                    "match_type": str  # "exact" | "semantic" | "fallback"
                },
                "trim": {
                    "start_s": float,
                    "end_s": float,
                    "duration_s": float
                },
                "fallback": Optional[Dict]
            }
        ],
        "coverage_analysis": {
            "total_segments": int,
            "exact_matches": int,
            "semantic_matches": int,
            "fallback_matches": int,
            "coverage_percentage": float,
            "gaps": List[Dict]
        },
        "adaptive_script": Optional[Dict],  # 如果脚本被改写
        "warnings": List[str]
    }
    """
```

**输入**：Step3 的 script.json + Step1 的 materials
**输出**：`data/matched_plan.json`（素材匹配方案）

**关键子模块**：
- 语义匹配引擎
- 脚本自适应改写（当素材不足时）

---

#### 3.1.5 Step 5：帧预览（step5_frame_preview）

**[已实现]**

**职责**：
- 根据脚本与素材匹配方案，提取关键帧作为视觉预览
- 帧预览用于在粗剪前验证素材与脚本的视觉对应关系

**对外 API**：
```python
def generate_frame_previews(matched_plan: Dict, materials: Dict, output_dir: str) -> Dict:
    """
    返回结构:
    {
        "frames": [
            {
                "segment_index": int,
                "frame_path": str,
                "timestamp_s": float,
                "material_id": str
            }
        ],
        "preview_dir": str,
        "total_frames": int
    }
    """
```

**输入**：Step4 的 matched_plan.json + 原始素材文件
**输出**：帧预览图片集合 + `data/frames_manifest.json`

---

#### 3.1.6 Step 6：粗剪预览（step6_rough_cut）

**[已实现]**

**职责**：
- 基于素材匹配方案，快速渲染低质量粗剪视频（30 秒～2 分钟）
- 粗剪用于验证节奏、转场、配音与素材的整体协调
- 粗剪应快速完成（< 2 分钟），供用户快速反馈

**对外 API**：
```python
def build_rough_cut(matched_plan: Dict, script: Dict, materials: Dict, output_path: str, config: Dict) -> Dict:
    """
    返回结构:
    {
        "video_path": str,
        "duration_s": float,
        "bitrate_kbps": int,
        "resolution": [int, int],
        "generated_at": str,
        "processing_time_s": float
    }
    """
```

**输入**：Step4 的 matched_plan + Step3 的 script
**输出**：`output/rough_cut.mp4`（低质量粗剪）

---

#### 3.1.7 Step 7：终剪渲染（step7_final_render）

**[已实现]**

**职责**：
- 按多个"阶段"（stage）渐进式渲染最终成品
- 支持多种输出格式与质量档位
- 支持分阶段精渲染（基础视频 → 添加字幕 → 添加音乐 → 最终输出）

**阶段定义**：
1. **Base**：无字幕、无 BGM 的基础视频
2. **Subtitled**：添加字幕后的版本
3. **AudioMixed**：添加背景音乐与配音混音
4. **Final**：最终成品

**对外 API**：
```python
def render_final_video(stage: str, matched_plan: Dict, script: Dict, materials: Dict,
                      audio_config: Optional[Dict] = None, subtitle_config: Optional[Dict] = None,
                      output_path: str = "output/final.mp4") -> Dict:
    """
    返回结构:
    {
        "stage": str,
        "video_path": str,
        "duration_s": float,
        "bitrate_kbps": int,
        "resolution": [int, int],
        "subtitle_count": int,
        "audio_tracks": int,
        "processing_time_s": float,
        "file_size_mb": float
    }
    """
```

**输入**：Step4 的 matched_plan + Step3 的 script + 音频/字幕配置
**输出**：`output/final.mp4`（最终视频）+ `output/stages/` 下的各阶段输出

---

### 3.2 Capability 模块（能力组件）

Capabilities 是**独立于 Step Pipeline 的功能模块**，可被灵活调用、组合、跳过。每个 Capability 都对应一项独立的产品能力。

**[已实现]** 的 Capability 模块：

| 模块 | 职责 | API 端点 | 输入来源 |
|------|------|--------|--------|
| `topic_library` | 选题库管理、检索 | `/api/capabilities/topic_library` | 项目/内联 |
| `topic_copy` | 选题文案生成 | `/api/capabilities/topic_copy/draft` | 项目/内联 |
| `text_rough_cut` | 逐句文本粗剪 | `/api/capabilities/text_rough_cut/plan` | 脚本 |
| `short_clip` | 高光短视频提炼 | `/api/capabilities/short_clip/plan` | 脚本/素材 |
| `refinement` | 精剪策略与 NLE 交接 | `/api/capabilities/refinement/*` | 脚本/素材 |
| `subtitle_calibration` | 字幕校准与时间轴调整 | `/api/capabilities/subtitle_calibration/*` | 字幕 |
| `image_semantic` | 图片语义分析 | `/api/capabilities/image_semantic/*` | 图片文件 |
| `article_expand` | 微信公众号文章扩写 | `/api/capabilities/article_expand/generate` | 脚本 |
| `social_export` | 社媒导出配置 | `/api/capabilities/social_export/*` | 脚本/视频 |
| `audio_voice` | 配音与背景音乐混音 | `/api/capabilities/audio_voice/*` | 脚本/音频库 |
| `content_publish` | 内容发布（抖音/B站/YouTube） | `/api/capabilities/content_publish/*` | 视频/文案 |
| `publish_prep` | 发布文案准备 | `/api/capabilities/publish_prep/generate` | 脚本 |

**关键特性**：

1. **独立调用**：每个 capability 都可不依赖 Step Pipeline 独立运行
2. **上下文支持**：统一支持 `actor_type/actor_id/run_mode/idempotency_key/trace_id`
3. **幂等性**：所有 POST 请求支持幂等重放（通过 idempotency_key）
4. **模式灵活**：支持 `input_mode=project|inline`
   - `project`：从当前项目目录读取数据
   - `inline`：直接传入数据（用于 Agent 调用、无项目上下文）

**Capability 模块注册表**：见 `modules/capabilities/registry.py`

---

### 3.3 Workflow Engine（工作流引擎）

**[已实现]**

**职责**：
- 编排 Step1~7 的执行顺序
- 管理步骤间的状态转移
- 支持步骤审批与反馈迭代
- 管理后台异步任务

**核心概念**：

```
WorkflowState:
  version: int
  project_dir: str
  current_step: int (1-7)
  steps: Dict[int, StepState]
    ├─ status: "not_started" | "pending" | "running" | "waiting_review" | "done" | "error"
    ├─ review_status: None | "approved" | "rejected"
    ├─ error_message: Optional[str]
    └─ output_files: List[str]
```

**主要方法**：

```python
class WorkflowState:
    def create(project_dir: Path, videos_dir: str, config: Dict) -> WorkflowState
    def load() -> WorkflowState
    def save()
    def get_step(n: int) -> Dict
    def set_step_status(n: int, status: str, **kwargs)
    def approve_review(n: int, parsed_data: Dict)
    def can_advance_to(n: int) -> bool  # 检查依赖
```

**文件位置**：
- 工作流状态：`<project>/workflow.json`
- 各步骤输出：`<project>/data/` 下的对应文件

---

### 3.4 Library 模块（素材库管理）

**[已实现]**

**职责**：
- 全局素材库的存储与检索
- 素材的入库、去重、版本管理
- 素材的语义索引与快速查找
- 项目工程恢复时的素材路径重链（project_relink_adapter）

**对外 API**：
```python
# 库操作
def ingest_materials(video_paths: List[str], project_id: str) -> Dict
def search_materials(query: str, limit: int = 20) -> List[Dict]
def get_material(material_id: str) -> Dict
def list_materials(filters: Dict) -> List[Dict]

# 项目重链
def relink_project(project_path: str, materials_db_path: str) -> Dict
```

**存储结构**：
- SQLite 库：`global_media_library.db`
- 项目库：`<project>/library.db`
- 缓存：`<project>/library_cache.json`

**关键子模块**：
- `global_media_library.py`：全局库操作
- `project_relink_adapter.py`：工程恢复与路径重链

---

### 3.5 Adapters 层（适配器与胶水代码）

**[已实现]**

**职责**：
- 跨模块通信的唯一通道
- 禁止任何模块直接 import 其他模块的私有实现
- 数据转换与协议适配

**禁止项**：
- 不允许直接 `from step2_topic_planning.impl import xxx`
- 不允许跨模块访问 `_private_function()`
- 不允许绕开 adapters 的直接函数调用

**推荐交互方式**：
```python
# ❌ 错误方式
from step4_material_matching.adaptive_rewriter import _rewrite_script

# ✅ 正确方式
from adapters.materials_mapper import rewrite_script_for_available_materials
```

**核心适配器**：
- `materials_mapper`：Step1 → Step4 的素材映射
- `project_relink_adapter`：工程恢复与路径重链（见 library 模块）

---

### 3.6 Contracts 层（数据契约）

**[已实现]**

**职责**：
- 统一定义跨模块数据结构
- 防止模块间数据格式冲突
- 支持版本化与向后兼容

**主要契约**：

| 契约 | 职责 | 版本 |
|------|------|------|
| `materials_contract.json` | 素材元数据定义 | v1.0 |
| `script_contract.json` | 脚本结构定义 | v1.0 |
| `workflow_contract.json` | 工作流状态定义 | v1.0 |
| `render_contract.json` | 渲染输出定义 | v1.0 |

**契约强制机制**：
- 所有跨模块数据必须通过 JSON Schema 验证
- 数据版本变更必须更新契约文档
- 向后兼容性由 migration 模块保证

---

### 3.7 App API 模块（应用接口与路由）

**[已实现]**

**职责**：
- Flask HTTP API 服务
- 路由定义与请求处理
- 身份认证与会话管理
- 后台任务调度与状态跟踪
- 文件提供与安全校验

**核心子模块**：

| 子模块 | 职责 | 路由前缀 |
|--------|------|--------|
| `server.py` | 主应用与路由挂载 | - |
| `secure_store.py` | 本地加密存储（密钥、token） | - |
| `job_store.py` | 后台任务队列与进度跟踪 | - |
| `param_utils.py` | 请求参数解析与验证 | - |
| `migrations.py` | 数据库迁移 | - |
| `publish_prep_api.py` | 发布文案准备 API | - |
| `routes/ui_routes.py` | UI 路由 | `/api/ui/` |
| `routes/settings_routes.py` | 设置管理 | `/api/settings/` |
| `routes/job_routes.py` | 后台任务 | `/api/job/` |
| `routes/workflow_routes.py` | 工作流 | `/api/workflows/` |
| `routes/capability_*_routes.py` | 能力模块路由 | `/api/capabilities/` |
| `routes/agent_*.py` | Agent API 路由 | `/api/agent/` |
| `routes/library_routes.py` | 素材库 | `/api/library/` |
| `routes/timeline_routes.py` | 时间线相关 | `/api/timeline/` |

**关键特性**：

1. **幂等性支持**：所有 POST 请求可通过 `idempotency_key` 实现幂等
2. **上下文传播**：自动捕获 `actor_type/actor_id/trace_id/run_mode`
3. **异步调度**：后台任务返回 job_id，支持长轮询
4. **错误处理**：统一错误格式 `{error: str, code: str, details: Dict}`

**错误码体系**：
- `invalid_request`：请求参数错误
- `auth_failed`：认证失败
- `not_found`：资源不存在
- `conflict`：状态冲突（如 step 已 done）
- `internal_error`：服务器错误
- `not_implemented`：功能未实现

---

### 3.8 Desktop Launcher（桌面应用入口）

**[已实现]**

**职责**：
- 启动 Flask 后端服务
- 初始化 pywebview（macOS WKWebView）
- 管理应用窗口与生命周期
- 依赖检测与自动安装

**主要功能**：
1. 依赖自动检测（Flask、pywebview）
2. 端口自动选择（避免冲突）
3. 项目选择对话框
4. 应用窗口管理（最小化、全屏、退出）

**启动方式**：
```bash
# 默认：打开项目选择器
python apps/desktop/launcher.py

# 直接打开已有项目
python apps/desktop/launcher.py --project /path/to/project

# 调试模式
python apps/desktop/launcher.py --debug
```

---

### 3.9 CLI 入口（命令行工具）

**[已实现]**

**职责**：
- 提供命令行访问 workflow 功能
- 支持脚本化与自动化
- 支持 headless 模式（无 GUI）

**主要命令**：
```bash
# 初始化项目
python apps/cli/run_toolkit.py init --videos /path/to/videos --project ./my_project

# 运行工作流
python apps/cli/run_toolkit.py run --project ./my_project [--step N]

# 查询状态
python apps/cli/run_toolkit.py status --project ./my_project

# 导出成品
python apps/cli/run_toolkit.py export --project ./my_project --format mp4
```

---

## 4. 模块边界要求

### 4.1 核心边界规则

#### 规则 1：接口隔离

**原则**：模块间仅通过公开 API 调用，禁止直接访问私有实现。

**实现方式**：
- 每个模块提供 `__init__.py` 明确公开 API
- 私有代码以 `_` 前缀标记
- 跨模块调用必须经过 adapters 层

**红线示例**：
```python
# ❌ 禁止
from modules.step3_script_generation.impl.parser import _parse_json_strict
from modules.step4_material_matching.internal import _fuzzy_match

# ✅ 推荐
from adapters.script_adapters import parse_and_validate_script
from adapters.materials_mapper import fuzzy_match_by_keywords
```

#### 规则 2：数据流向

所有数据流都应遵循"单向无环"原则：

```
Step1 → Step2 → Step3 → Step4 → Step5 → Step6 → Step7
  ↓       ↓       ↓       ↓       ↓       ↓       ↓
Library (单向：Step → Library，不反向依赖)
```

**禁止项**：
- 后续步骤不允许修改前置步骤的输出
- 步骤间不允许循环调用
- Capability 不允许直接修改 Step 输出

#### 规则 3：共享资源访问

**共享资源**（Global Media Library、Settings DB、Project Relink）必须通过指定的"资源网关"访问：

| 资源 | 网关 | 规则 |
|------|------|------|
| Global Media Library | `library.global_media_library` | 读：多线程安全；写：排他锁 |
| Settings DB | `app_api.secure_store` | 读写都经过加密存储 |
| Project Relink | `library.project_relink_adapter` | 读：快照模式；写：事务 |
| File System | `adapters.fs_utils` | 读写都通过原子操作 |

---

### 4.2 推荐交互方式

#### 模式 1：步骤间的"数据文件"流动

Step N 完成后，生成 `data/step<N>_output.json`，Step N+1 读取该文件：

```python
# Step 1 完成后
with atomic_write(project_dir / "data" / "materials.json") as f:
    json.dump(materials_data, f)

# Step 2 开始时
materials = json.load(open(project_dir / "data" / "materials.json"))
```

**优点**：
- 天然支持暂停/恢复
- 易于调试（可检查中间文件）
- 支持并行回溯

#### 模式 2：Capability 的"内联"调用

Capability 优先支持 `input_mode=inline`，接收输入数据而非项目路径：

```python
# 好的调用方式
result = topic_copy.draft(
    input_mode="inline",
    topic={...},
    materials=[...],
    actor_type="agent"
)

# 而非
result = topic_copy.draft(
    input_mode="project",
    project_path="...",  # 强制依赖项目目录
)
```

**优点**：
- 解耦 Capability 与项目目录结构
- 支持 Agent/API 无项目上下文调用
- 便于单元测试

#### 模式 3：工作流与异步任务

长时间操作（> 5 秒）必须异步化，返回 job_id，由客户端轮询：

```python
# API 层
@app.post("/api/run_step")
def run_step(request: Request) -> Dict:
    job = job_store.create_job(
        task="run_step",
        step_num=request.step,
        params={...}
    )
    # 立即返回 job_id，后台执行
    return {"job_id": job.id, "status": "pending"}

# 客户端轮询
GET /api/job/{job_id}  # 返回 {"status": "running", "progress": 0.5}
```

---

### 4.3 禁止项清单

| 禁止项 | 原因 | 替代方案 |
|--------|------|--------|
| 直接 import 其他模块的 `impl/internal` | 破坏接口隔离 | 经过 adapters 或 __init__ 公开 API |
| Step 间循环依赖 | 破坏单向流动 | 数据通过文件而非函数调用 |
| Capability 直接修改 Step 输出 | 破坏审计追踪 | 生成新的输出文件，记录版本 |
| 绕开 secure_store 访问敏感数据 | 安全风险 | 所有敏感数据都通过 secure_store |
| 全局可变状态（除 job_store） | 难以追踪与测试 | 所有状态都持久化到文件或数据库 |
| 跨模块的硬编码路径 | 难以移植 | 配置化路径，允许通过环境变量覆盖 |
| 直接访问数据库（bypass ORM） | 破坏一致性 | 通过 adapters 提供的 ORM 方法 |

---

## 5. 步骤管线（Step Pipeline）架构

### 5.1 管线模型

```
User Input
    ↓
┌─────────────────────────────────┐
│ Step 1: Material Analysis       │ → materials.json
├─────────────────────────────────┤
│ Step 2: Topic Planning          │ → topics.json (选题备选集)
├─────────────────────────────────┤
│ Step 3: Script Generation       │ → script.json (完整脚本)
├─────────────────────────────────┤
│ Step 4: Material Matching       │ → matched_plan.json
├─────────────────────────────────┤
│ Step 5: Frame Preview           │ → frames/ (帧图片集)
├─────────────────────────────────┤
│ Step 6: Rough Cut Preview       │ → rough_cut.mp4 (低质)
├─────────────────────────────────┤
│ Step 7: Final Render            │ → final.mp4 (成品)
└─────────────────────────────────┘
    ↓
Output / Publish
```

### 5.2 步骤状态机

每个步骤都有一个独立的状态机：

```
    ┌──────────────────┐
    │  not_started     │ (初始态)
    └────────┬─────────┘
             │ (用户点击"运行")
    ┌────────▼─────────┐
    │     pending      │ (等待运行)
    └────────┬─────────┘
             │ (后台任务开始)
    ┌────────▼─────────┐
    │     running      │ (运行中)
    └────────┬─────────┘
             │ (完成)
    ┌────────▼──────────────┐
    │  waiting_review       │ (等待用户审批)
    ├───┬──────────────┬────┤
    │   │              │    │
    │ (拒) (编辑) (批准) │
    │   ▼              ▼    │
    │┌──────────┐ ┌────────┐│
    ││ rejected │ │  done  ││
    │└──────────┘ └────────┘│
    └───────────────────────┘
```

**状态转移规则**：
- `not_started` → `pending`：用户点击"开始"
- `pending` → `running`：后台任务队列调度
- `running` → `waiting_review`：任务完成，等待审批
- `waiting_review` → `done`：用户批准
- `waiting_review` → `pending`：用户编辑后重新运行
- 任何态 → `error`：异常发生

---

### 5.3 管线编排规则

**顺序执行**：
- Step N 必须在 Step N-1 成功完成后才能开始
- Step N-1 处于 `waiting_review` 时，Step N 不能执行

**跳过逻辑**：
- 用户可显式跳过 Step 2（使用默认选题）
- 用户可跳过 Step 5（直接进入粗剪）
- 不允许跳过 Step 1、3、4、6、7（核心链路）

**重跑逻辑**：
- Step N 重跑会清除 Step N+1 的所有输出（级联清除）
- Step N 重跑后，后续 Step 状态重置为 `not_started`

---

## 6. 能力模块（Capability）架构

### 6.1 能力模块的定义

**Capability** 是一个**功能独立、可被灵活调用、可跳过、可组合的功能单元**。

与 Step 的区别：

| 特性 | Step | Capability |
|------|------|-----------|
| 执行顺序 | 严格顺序（1→2→...→7） | 灵活调用，可跳过 |
| 输入来源 | 上一步的输出 | 项目文件 / 内联数据 |
| 依赖管理 | 强依赖 | 弱依赖 |
| 调用方式 | workflow 引擎驱动 | API 直接调用 |
| 使用场景 | 完整工作流 | 特定功能增强、微调 |

### 6.2 Capability 的标准接口

所有 Capability 都应实现统一的接口签名：

```python
def capability_operation(
    # 核心业务参数
    input_data: Dict,
    config: Dict,

    # 通用上下文（可选）
    actor_type: Optional[str] = None,      # "human" | "agent"
    actor_id: Optional[str] = None,        # 用户/Agent ID
    run_mode: Optional[str] = None,        # "interactive" | "headless"
    idempotency_key: Optional[str] = None, # 幂等重放 key
    trace_id: Optional[str] = None,        # 追踪 ID

    # 输入模式
    input_mode: str = "project"            # "project" | "inline"
) -> Dict:
    """
    返回结构:
    {
        "result": Dict,                    # 业务结果
        "request_context": {               # 原样回传
            "actor_type": str,
            "actor_id": str,
            "run_mode": str,
            "trace_id": str
        },
        "plan_summary": str,               # 执行过程说明
        "artifacts": List[Dict],           # 生成的中间产物
        "warnings": List[str],             # 警告信息
        "idempotency": {                   # 幂等性信息
            "key": Optional[str],
            "replayed": bool,              # 是否从缓存重放
            "cached_at": Optional[str]
        }
    }
    """
```

### 6.3 能力模块注册与发现

所有 Capability 都必须向 `capabilities/registry.py` 注册：

```python
# modules/capabilities/registry.py

CAPABILITY_REGISTRY = {
    "topic_library": {
        "module": "topic_library",
        "class": "TopicLibrary",
        "operations": ["query", "create", "bootstrap"],
        "input_mode_support": ["project", "inline"],
        "related_steps": [2],
        "description": "选题库管理与检索"
    },
    "topic_copy": {
        "module": "topic_copy",
        "class": "TopicCopy",
        "operations": ["draft"],
        "input_mode_support": ["project", "inline"],
        "related_steps": [2, 3],
        "description": "选题文案生成"
    },
    # ... 更多模块
}
```

**发现 API**：
```python
GET /api/capabilities
# 返回所有注册的 capability 定义及其元信息
```

---

### 6.4 幂等性缓存机制

所有 POST 请求都支持幂等重放。缓存由两部分组成：

**内存缓存**（进程内）：
- TTL：当前会话（进程退出后清除）
- 存储位置：Python 内存

**持久缓存**（磁盘）：
- TTL：7 天（可配置）
- 存储位置：`data/capability_idempotency_cache.json`
- 清理策略：后台清理任务

**幂等重放流程**：

```
POST /api/capabilities/xxx
{
    "input": {...},
    "idempotency_key": "abc123"
}
    ↓
1. 检查内存缓存 → 命中 → 直接返回（idempotency.replayed=true）
    ↓ 未命中
2. 检查持久缓存 → 命中 && 未过期 → 返回（idempotency.replayed=true）
    ↓ 未命中或已过期
3. 执行业务逻辑 → 生成结果
    ↓
4. 写入内存缓存 + 持久缓存（带时间戳）
    ↓
5. 返回结果（idempotency.replayed=false）
```

---

## 7. 工作流引擎（Workflow Engine）架构

### 7.1 工作流生命周期

```
Project Created
    ↓
┌──────────────────────────────────────┐
│ Workflow Initialized                 │
│ (workflow.json 创建，Step 1 = pending)│
└──────────────────────────────────────┘
    ↓
┌─ Step Loop (i=1 to 7) ───────────────┐
│                                      │
│  1. 用户审阅 Step i-1 的输出          │
│  2. 点击"下一步"或"运行 Step i"       │
│  3. API 调用 POST /api/run_step      │
│  4. 返回 job_id，进入后台执行         │
│  5. 轮询 GET /api/job/{job_id}       │
│  6. 完成后进入 waiting_review         │
│  7. 用户点击"批准"→ Step 完成         │
│                                      │
│  如果用户修改数据：                    │
│  - 修改 UI 中的参数                   │
│  - 点击"重新运行"                     │
│  - Step 重新进入 pending              │
│                                      │
└──────────────────────────────────────┘
    ↓
Workflow Done
    ↓
Export / Publish
```

### 7.2 后台任务队列

所有长时间操作都进入异步队列：

**Job 状态**：

```
pending → running → done/failed
  ↑                    ↓
  └─────── retry ──────┘
```

**Job 结构**：
```python
class Job(BaseModel):
    id: str                          # UUID
    task: str                        # "run_step", "render_final", etc.
    status: str                      # "pending" | "running" | "done" | "failed"
    step_num: Optional[int]          # 如果是 step 任务
    params: Dict                     # 任务参数
    result: Optional[Dict]           # 完成后的结果
    error: Optional[str]             # 错误信息
    progress: float                  # 0.0 ~ 1.0
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    retry_count: int = 0
    max_retries: int = 3
```

**存储位置**：`data/jobs.db`（SQLite）

---

## 8. 数据层设计

### 8.1 存储方案

#### SQLite 主库

**核心数据库文件**：

| 文件 | 位置 | 用途 | 范围 |
|------|------|------|------|
| `global_media_library.db` | `~/.videoeditor/library/` | 全局素材库 | 跨项目 |
| `settings.db` | `~/.videoeditor/config/` | 用户设置、密钥 | 跨项目 |
| `library.db` | `<project>/` | 项目库索引 | 单项目 |
| `jobs.db` | `<project>/` | 后台任务队列 | 单项目 |

**schema 管理**：
- 所有 schema 变更通过 `migrations.py` 执行
- 支持版本回滚
- 每个 migration 必须包含 up & down 脚本

#### 文件系统

**目录结构**（单个项目）：

```
<project_dir>/
├── workflow.json              # 工作流状态
├── data/
│   ├── materials.json         # Step 1 输出
│   ├── topics.json            # Step 2 输出
│   ├── script.json            # Step 3 输出
│   ├── matched_plan.json      # Step 4 输出
│   ├── frames_manifest.json   # Step 5 输出
│   ├── capability_idempotency_cache.json  # Capability 幂等缓存
│   └── ... (其他临时文件)
├── frames/                    # Step 5 帧预览
│   └── *.jpg
├── output/
│   ├── rough_cut.mp4          # Step 6 输出
│   ├── final.mp4              # Step 7 输出
│   ├── stages/
│   │   ├── base.mp4
│   │   ├── subtitled.mp4
│   │   ├── audio_mixed.mp4
│   │   └── final.mp4
│   └── ... (其他格式导出)
├── cache/                     # 临时缓存
│   └── ... (可在任何时间清除)
└── logs/
    └── *.log
```

**文件操作原则**：
- 所有写操作使用原子操作（write-to-temp + os.replace）
- 所有读操作使用共享锁（防止并发修改）
- 清理策略：cache 目录 7 天自动过期

#### 缓存层

**内存缓存**（当前不使用，规划中）：
- Redis（可选）：用于分布式缓存
- 本地 LRU：用于频繁访问的元数据

---

### 8.2 数据一致性

**乐观锁**：
```python
# 更新 workflow.json 时
current_version = load_version()
update_data()
if not check_version(current_version):
    raise ConflictError("Workflow 已被修改，请刷新后重试")
```

**事务保证**：
- SQLite 所有更新操作都在事务内
- 异常发生自动 rollback

---

## 9. 接入层设计

### 9.1 Flask API 层

**核心职责**：
- HTTP 请求处理与参数验证
- 身份认证与会话管理
- 错误格式统一化
- 请求日志与审计

**中间件栈**：
```python
app = Flask(__name__)
app.wsgi_app = [
    RequestLoggingMiddleware,      # 请求日志
    AuthenticationMiddleware,      # 认证检查
    RequestValidationMiddleware,   # 参数验证
    ErrorHandlingMiddleware,       # 错误统一处理
]
```

**路由层次**：
```
/api/
├── /ui/                          # UI 相关（项目、设置、文件）
├── /status                       # 系统状态
├── /system/                      # 系统诊断、加载情况
├── /settings/                    # 配置管理
├── /session/                     # 会话与认证
├── /library/                     # 素材库
├── /approve/<step>               # Step 审批
├── /run_step                     # Step 执行
├── /job/<job_id>                 # 任务状态
├── /files/<path>                 # 文件提供
├── /capabilities/                # 能力模块 API
├── /agent/                       # Agent API
├── /workflows/                   # 自定义工作流
└── /dialog/                      # 系统对话框（文件夹选择）
```

### 9.2 pywebview GUI 层

**职责**：
- 渲染 UI（Alpine.js + HTML/CSS）
- 与 Flask API 通信（Fetch API）
- 本地事件与消息（WebSocket）

**通信模式**：
```
┌──────────────┐                  ┌─────────────┐
│  pywebview   │ ◄─ HTTP/REST ──► │  Flask API  │
│   (GUI)      │                  │  (Backend)  │
└──────────────┘                  └─────────────┘
       │                                 │
       ▼                                 ▼
  Alpine.js                        Python Modules
    Events                              Logic
```

**前后端数据合约**：
- 所有 API 响应都返回 JSON（UTF-8）
- 所有 API 都支持 CORS（本地环回）
- 长时间操作都异步化，返回 job_id

---

### 9.3 Agent API 层

**[规划中]**

**目标**：支持外部 AI Agent（如 Claude Agent）调用 VideoEditor 的能力。

**主要端点**：
```
POST /api/agent/tasks/plan         # 规划 Agent 任务
POST /api/agent/tasks/run          # 执行 Agent 任务
GET  /api/agent/tasks/<job_id>     # 查询任务状态
GET  /api/agent/capabilities       # 发现可调用的 Capability
```

**特点**：
- 所有 Capability 都可被 Agent 调用
- 支持完整的上下文传播（trace_id、actor_id）
- 支持长时间任务与流式结果

---

### 9.4 CLI 入口

**[已实现]**

**命令语言**：
```bash
# 初始化
python -m apps.cli.run_toolkit init \
  --videos <视频目录> \
  --project <项目路径> \
  [--ai anthropic|openai]

# 运行
python -m apps.cli.run_toolkit run \
  --project <项目路径> \
  [--step <1-7|all>] \
  [--force] \
  [--headless]

# 查询状态
python -m apps.cli.run_toolkit status --project <项目路径>

# 导出
python -m apps.cli.run_toolkit export \
  --project <项目路径> \
  --format <mp4|mov|webm> \
  --quality <low|medium|high>
```

---

## 10. 安全基线

### 10.1 认证与授权

**当前状态**：[规划中]

- 本地项目：无认证（信任本地文件系统）
- 远程 API：支持 API Key 认证
- Agent 调用：支持 OAuth/Bearer Token

**路线图**：
1. 本地加密存储（已实现：secure_store.py）
2. 项目级访问控制（规划中）
3. 远程 API Key 管理（规划中）

### 10.2 敏感数据保护

**敏感数据包括**：
- AI API 密钥（OpenAI、Anthropic）
- 发布平台 Token（YouTube、抖音）
- 用户项目文件

**保护措施**：
- 所有密钥存储在 `secure_store`（加密）
- 不允许在日志中输出密钥
- API 响应中不返回密钥（仅返回 key_id）

**实现**：
```python
from modules.app_api.secure_store import SecureStore

store = SecureStore()
store.set("openai_key", "sk-...", encrypt=True)
key = store.get("openai_key", decrypt=True)  # 自动解密
```

### 10.3 输入验证

所有外部输入（API、文件上传、用户输入）都必须验证：

```python
# 参数验证
request_model = ProjectInitRequest.parse_obj(request.json)

# 文件路径校验
def safe_path(project_dir: Path, rel_path: str) -> Path:
    abs_path = (project_dir / rel_path).resolve()
    if not str(abs_path).startswith(str(project_dir.resolve())):
        raise SecurityError("Path traversal detected")
    return abs_path
```

### 10.4 审计日志

所有关键操作都记录审计日志：

```python
# 审计日志格式
{
    "timestamp": "2026-03-19T10:30:00Z",
    "actor": {
        "type": "human|agent|system",
        "id": "user_id|agent_id"
    },
    "action": "run_step|approve_step|export_video",
    "resource": "project:abc123:step:2",
    "result": "success|failed",
    "details": {...}
}
```

**存储位置**：`<project>/logs/audit.jsonl`

---

## 11. 与其他文档的关系

### 11.1 文档树

```
docs/
├── tech-specs/
│   ├── architecture.md (本文档) ⬅ 架构总览
│   ├── database-schema.md (规划中) ⬅ 数据库结构
│   ├── api-reference.md (规划中) ⬅ API 完整参考
│   └── deployment-guide.md (规划中) ⬅ 部署指南
├── module-index.md ⬅ 旧版模块索引（已过期，本文档取代）
├── capabilities-api.md ⬅ Capability API 详细说明
├── project_relink_freeze_rules_and_guardrails_v1.md ⬅ 工程恢复冻结规则
├── next_dev_plan.md ⬅ 下一阶段开发计划
└── ... (功能设计、测试、复盘等)
```

### 11.2 参考关系

| 文档 | 目的 | 参考本文档的部分 |
|------|------|-----------------|
| capabilities-api.md | Capability API 详细说明 | 6. Capability 架构 |
| next_dev_plan.md | 下一阶段开发计划 | 所有已规划的模块 |
| project_relink_*.md | 工程恢复规范 | 3.4 Library 模块 |
| 各模块 PRD | 功能需求 | 该模块的职责与 API |

---

## 12. 修订说明

### 12.1 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|--------|
| v1.0 | 2026-03-19 | 初始版本：定义四层架构、模块边界、工作流、Capability 系统、数据层、接入层、安全基线 |

### 12.2 已实现 vs 规划中

**已实现** [✓]：
- Step1~7 流水线 + WorkflowEngine
- Capability 模块注册表与通用接口
- Flask API + pywebview GUI + CLI
- 幂等缓存机制
- secure_store（敏感数据存储）
- 原子文件操作

**规划中** [○]：
- Agent API（完整支持）
- Redis 分布式缓存
- 项目级访问控制
- 完整的 API Reference 文档
- 数据库 Schema 文档
- 部署指南

---

## 13. 遵循指南

### 13.1 架构审查清单

新增模块或修改现有模块时，检查以下项：

- [ ] **隔离性**：模块是否有清晰的边界与公开 API？
- [ ] **依赖性**：是否只依赖于 contracts、adapters 和其他公开 API？
- [ ] **数据流**：是否遵循单向无环的数据流向？
- [ ] **错误处理**：是否所有异常都被捕获并转换为标准格式？
- [ ] **幂等性**：关键操作是否支持重跑与幂等？
- [ ] **审计**：关键操作是否记录审计日志？
- [ ] **文档**：是否更新了模块的 README 与接口说明？
- [ ] **测试**：是否有单元测试与集成测试？

### 13.2 代码审查重点

- 禁止跨越模块边界的直接 import
- 禁止硬编码路径（所有路径都应配置化）
- 禁止全局可变状态（除 job_store）
- 强制使用 adapters 进行跨模块通信
- 强制使用原子文件操作
- 强制异常处理与日志记录

---

## 14. 常见问题

### Q1：能否在 Step 2 中直接调用 Step 4 的功能？

**A**：不推荐。应该：
1. 在 Step 2 完成后，通过工作流状态转移到 Step 3
2. 或者，如果是临时需求，通过 Capability 模块提供新的 API
3. 避免打破 Step 的顺序依赖关系

### Q2：Capability 和 Step 应该如何选择？

**A**：
- **Step**：核心工作流的一部分，有严格的顺序依赖
- **Capability**：可选的功能增强，可被灵活调用、跳过、重复执行

示例：
- "音频质量评估"是 Step1 的内容 ✓
- "图片语义分析"是独立 Capability ✓

### Q3：如何在 Agent 中调用 Capability？

**A**：使用 Agent API 的 `inline` 模式：
```python
result = agent_api.call(
    endpoint="/api/capabilities/topic_copy/draft",
    method="POST",
    payload={
        "input_mode": "inline",
        "topic": {...},
        "materials": [...],
        "actor_type": "agent"
    }
)
```

### Q4：项目配置应该存在哪里？

**A**：
1. **全局默认**：代码中的常量
2. **用户覆盖**：`~/.videoeditor/config.json`
3. **项目覆盖**：`<project>/config.json`
4. **运行时覆盖**：环境变量 `VIDEOEDITOR_*`

优先级从低到高。

---

**文档完成日期**：2026-03-19
**维护状态**：Active
**下次审查日期**：2026-06-19
