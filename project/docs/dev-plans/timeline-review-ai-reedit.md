# AI 智能剪辑 + 时间轴评审 — 总参考文档

> 日期: 2026-03-31 | 状态: 定稿 V1.0
> 覆盖版本: v0.14.0 (粗剪+数据层) → v0.15.0 (评审UI) → v0.16.0 (AI重编辑+增强)
> 对标: 粗剪 > Descript+Gling, 评审 > Clapshot+Frame.io, AI重编辑 > OpenStoryline+VideoAgent
>
> **本文档是功能设计总参考，不是开发计划。各版本的 R 任务详见:**
> - `dev-plan-v0.14.0.md` — Phase 0 + 1 (智能粗剪 + 数据层)
> - `dev-plan-v0.15.0.md` — Phase 2 + 3 (核心评审 UI + 高级标注)
> - `dev-plan-v0.16.0.md` — Phase 4 + 5 (AI 重编辑 + 增强能力)

---

## 1. 产品目标

**一句话**: 导入视频 → AI 智能粗剪 → 时间轴评审 → AI 重编辑 → 成品，全程一体化。

**完整流程**:
```
原始视频导入 → 自动检测视频类型 (VAD)
     │
     ├─ 🎤 口播路径 (speech_ratio > 0.6)
     │   ├─ Whisper 转录 (词级时间戳)
     │   ├─ AI 预标记: 语气词 + 废话 + 重复片段 + bad takes
     │   ├─ 用户编辑文字稿 (删=删视频, 拖=调序, ⭐=hook)
     │   ├─ 多说话人颜色区分
     │   └─ 确认 → 生成 EDITS → 粗剪
     │
     ├─ 🎬 情景路径 (speech_ratio < 0.15)
     │   ├─ 场景分割 + VLM 镜头分析
     │   ├─ 用户选主题/风格/时长
     │   ├─ AI 选镜头 + 排序 + 节奏控制
     │   └─ 可搜索 stock 素材补充 (Pexels API)
     │
     ├─ 🎤🎬 混合路径 (中间值)
     │   ├─ VAD 分离口播段 + B-roll 段
     │   ├─ 口播 → 文案编辑, B-roll → AI 自动插入
     │   └─ 合并 → 粗剪
     │
     ▼
 📋 时间轴评审 (评论 + 画笔 + 形状标注 + 逐帧 + 缩略图 + 波形)
     │
     ▼
 🤖 AI 重编辑 (评论→指令 + DAG智能重跑 + 版本diff)
     │   可选增强: 音频增强 / TTS配音 / BGM / 转场效果 / 自动reframe
     │
     ▼
 🔄 循环直到满意 → 多平台导出
```

---

## 2. 技术规范合规性

> 以下确保计划符合 `tech-specs/` 下四份规范文档的所有要求。

### 2.1 模块边界 (architecture.md)

```
project/modules/review_engine/          ← 新模块，独立目录
├── __init__.py                         ← 公共 API 入口 (MUST)
├── contracts.py                        ← 数据合约定义
├── exceptions.py                       ← 模块专属异常
├── video_detector.py                   ← 视频类型检测
├── transcript_editor.py                ← 口播文案编辑
├── scene_selector.py                   ← 情景镜头选择
├── mixed_editor.py                     ← 混合路径
├── review_store.py                     ← 评审状态 CRUD
├── artifact_store.py                   ← 版本化 artifact
├── comment_resolver.py                 ← 评论定位
├── intent_router.py                    ← LLM 意图路由
├── edit_planner.py                     ← 编辑方案生成
├── node_manager.py                     ← 节点 DAG
├── render_pipeline.py                  ← 渲染管线
├── audio_enhancer.py                   ← 音频增强
├── tts_voiceover.py                    ← TTS 配音
├── bgm_selector.py                     ← BGM 选择
├── transition_effects.py               ← 转场效果
├── style_skills.py                     ← 风格技能
├── stock_media.py                      ← Stock 素材搜索
└── social_reframe.py                   ← 多平台自动 reframe
```

**模块隔离规则:**
- 外部模块通过 `__init__.py` 公共 API 访问，不直接 import 内部文件
- 跨模块数据通过 `contracts.py` 定义的数据合约传递
- 使用 `adapters.fs_utils` 进行文件系统操作
- 使用 `app_api.secure_store` 存储 API keys (Pexels, TTS 等)

### 2.2 异常处理 (coding-standards.md)

```python
# modules/review_engine/exceptions.py

class ReviewEngineError(VideoEditorError):
    """Base exception for review engine module."""

class VideoDetectionError(ReviewEngineError):
    """Video type detection failed."""

class TranscriptError(ReviewEngineError):
    """Transcription or transcript editing failed."""

class RenderError(ReviewEngineError):
    """Video rendering failed."""

class IntentRouterError(ReviewEngineError):
    """LLM intent routing failed (bad response, schema violation)."""

class ArtifactNotFoundError(ReviewEngineError):
    """Required artifact from previous version/node not found."""

class ConflictingCommentsError(ReviewEngineError):
    """Multiple comments on same segment have contradicting instructions."""

class StockMediaError(ReviewEngineError):
    """Stock media search/download failed."""
```

### 2.3 API 合规 (coding-standards.md §4.3)

所有 API 端点遵循统一错误格式:
```json
{
  "success": false,
  "error": "error_code",
  "message": "用户可读的错误描述",
  "code": 400,
  "timestamp": "2026-03-31T10:30:00Z",
  "trace_id": "uuid-for-tracking"
}
```
- 标准错误码: `invalid_request` (400), `not_found` (404), `conflict` (409), `internal_error` (500)
- POST 请求支持 `idempotency_key` header
- 长操作 >5s 返回 `job_id`，客户端轮询 `GET /api/job/{job_id}`

### 2.x 模块与 Step Pipeline 关系

- review_engine 是 **独立于 step1-7 pipeline 的并行路径**
- step1 的转录输出可复用（通过 `contracts.MaterialAnalysisResult` 接口）
- step5/step6 保持不变，review_engine 的粗剪是新的独立入口
- 用户在 UI 中选择"工作流模式"(step pipeline) 或"智能剪辑模式"(review_engine)

### 2.x 外部 API 走 Adapter 层 (architecture.md §1.1)

```
project/modules/adapters/
├── pexels_adapter.py         ← Pexels Stock 素材 API
└── tts_adapter.py            ← TTS 提供商适配 (edge-tts/CosyVoice/Fish Speech)
```
- review_engine 不直接调用外部 API，通过 adapters/ 封装
- 环境变量: `VIDEOEDITOR_PEXELS_API_KEY`, `VIDEOEDITOR_TTS_PROVIDER`, `VIDEOEDITOR_TTS_API_KEY`

### 2.x 数据库 Schema

```sql
CREATE TABLE review_sessions (
    session_id TEXT PRIMARY KEY,
    project_path TEXT NOT NULL,
    video_path TEXT NOT NULL,
    video_type TEXT NOT NULL,        -- speech|scenic|mixed
    speech_ratio REAL,
    current_version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',    -- active|completed|archived
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE review_comments (
    comment_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES review_sessions(session_id),
    version INTEGER NOT NULL,
    time_start_ms INTEGER NOT NULL,
    time_end_ms INTEGER,
    comment_type TEXT NOT NULL,      -- cut|keep|modify|transition|audio|subtitle|general
    text TEXT NOT NULL,
    drawing_data TEXT,
    drawing_thumbnail TEXT,
    status TEXT DEFAULT 'pending',   -- pending|resolved|rejected
    ai_reply TEXT,
    resolved_in_version INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE review_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES review_sessions(session_id),
    version_number INTEGER NOT NULL,
    edits_json TEXT NOT NULL,
    video_path TEXT,
    render_status TEXT DEFAULT 'pending',
    render_job_id TEXT,
    parent_version INTEGER,
    change_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, version_number)
);

CREATE TABLE review_artifacts (
    artifact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES review_sessions(session_id),
    version_number INTEGER NOT NULL,
    node_name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    checksum TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, version_number, node_name)
);
```

### 2.x 不包含的需求 (Future)

| 需求 | 推迟原因 |
|------|---------|
| 多人协作 / @提及 | 桌面单用户产品 |
| GPU 加速渲染 | CPU 满足 <5min 视频需求，v0.17+ |
| 实时协作 (WebRTC) | 需 Server 架构重构 |
| 语音克隆 | 法律风险 + 额外模型 |
| 动态字幕样式 | 复杂度高，v0.17+ |

### 2.4 测试策略 (testing-strategy.md)

每个 Phase 交付时必须包含:

| Phase | 必须的测试 |
|-------|-----------|
| 0 (粗剪) | UT: video_detector, transcript_editor, scene_selector / IT: 完整粗剪流程 / API: roughcut endpoints |
| 1 (数据层) | UT: review_store, artifact_store / IT: 版本创建+回退 / API: review endpoints |
| 2 (评审UI) | UI: ReviewPlayer 交互 / E2E: 添加评论→显示在时间轴 |
| 3 (高级评审) | UT: 画笔数据序列化 / IT: sprite sheet 生成 / UI: 画笔标注交互 |
| 4 (AI引擎) | UT: comment_resolver, intent_router (mock LLM), edit_planner / IT: 评论→重编辑完整流程 |
| 5 (增强) | UT: audio_enhancer, tts, bgm, transitions / IT: 带增强的完整渲染 |

**测试命名 (MUST):**
```python
def test_video_detector_speech_heavy_returns_speech():
def test_transcript_editor_delete_paragraph_removes_segment():
def test_comment_resolver_gap_detection_finds_cut_content():
def test_intent_router_invalid_schema_raises_error():
def test_render_pipeline_skip_mode_uses_cached_artifact():
```

### 2.5 编码标准 (coding-standards.md)

- 所有公共函数: 完整 type annotations + Google-style docstring
- 常量使用 UPPER_SNAKE_CASE，环境变量前缀 `VIDEOEDITOR_`
- FFmpeg 调用: 设置 timeout + 捕获 stderr + 最多重试 3 次
- 文件操作: atomic write (write-to-temp + os.replace)
- 数据库: 使用 Store 类封装，参数化查询防 SQL 注入

---

## 3. Layer 0: 智能粗剪 — 全面超越 Descript + Gling

### 3.1 对标功能清单

| 功能 | Descript | Gling | ChatCut | 我们 | Phase |
|------|---------|-------|---------|------|-------|
| 文字即视频 (编辑文字=编辑视频) | ✅ | ❌ | ❌ | ✅ | 0 |
| AI 语气词预标记 | ✅ | ✅ | ❌ | ✅ | 0 |
| Bad take / 重复片段检测 | ✅ | ✅ | ✅ | ✅ | 0 |
| 多说话人区分 (diarization) | ✅ | ❌ | ✅ | ✅ | 0 |
| 文字光标跟随播放 | ✅ | ❌ | ❌ | ✅ | 0 |
| 预计时长实时统计 | ✅ | ❌ | ❌ | ✅ | 0 |
| 静音/空白段自动检测删除 | ✅ | ✅ | ❌ | ✅ | 0 |
| 非口播视频支持 | ❌ | ❌ | ❌ | ✅ 情景路径 | 0 |
| 混合视频支持 (口播+B-roll) | ❌ | ❌ | ❌ | ✅ 混合路径 | 0 |
| 精彩片段标记→hook | ❌ | ❌ | ❌ | ✅ | 0 |
| AI 预标记一键全部接受 | ❌ | ✅ | ❌ | ✅ | 0 |
| Stock 素材搜索 (Pexels) | ❌ | ❌ | ❌ | ✅ | 5 |
| 本地运行免费 | ❌($24/月) | ❌($15/月) | ❌ | ✅ | 0 |

### 3.2 Bad Take 检测 (Descript + Gling 核心功能)

```python
class BadTakeDetector:
    """检测废话、重复片段、false starts"""

    def detect_retakes(self, paragraphs: List[Paragraph]) -> List[RetakeMark]:
        """检测重新开始说的片段 (false starts)"""
        # 模式1: 连续两句语义高度相似 (cosine > 0.85) → 保留后一句
        # 模式2: 句子被打断后重新开始 ("所以...所以说我觉得")
        # 模式3: 明显的犹豫+重启 ("呃...不对...就是说")

    def detect_dead_air(self, audio_path: str, threshold_sec: float = 1.5) -> List[Tuple]:
        """检测长静音段 (>1.5s)"""
        # FFmpeg silencedetect filter
        # 返回 [(start, end, duration), ...]

    def detect_filler_sentences(self, paragraphs: List[Paragraph]) -> List[int]:
        """检测整句废话 (不含有效信息)"""
        # LLM 判断: "这句话是否包含实质性内容?"
        # 例: "对对对" "嗯嗯" "就是那个" → 标记为废话

    def auto_mark_all(self, transcript_doc) -> TranscriptDoc:
        """综合标记: 语气词 + 重复 + 废话 + 静音"""
        # 1. 规则标记: 呃/嗯/就是/对/然后/所以说/反正
        # 2. 静音检测: >1.5s 空白
        # 3. 重复检测: 语义相似句
        # 4. 废话检测: LLM 判断
        # 每种标记不同颜色:
        #   灰色删除线 = 语气词
        #   红色删除线 = 重复/bad take
        #   橙色删除线 = 废话
        #   蓝色虚线 = 长静音
```

### 3.3 口播文案编辑器 (超越 Descript)

```
┌──────────────────────────────────────────────────────┐
│ 📹 视频预览 (左, 跟随光标播放)     📊 统计栏 (右上)   │
│                                    原始: 228s        │
│                                    删除: -57s        │
│                                    预计: 171s        │
│                                    语气词: 12处 4.1s  │
│                                    重复: 3处 8.2s     │
│                                    静音: 5处 7.5s     │
├──────────────────────────────────────────────────────┤
│ 📝 文字稿编辑器                                       │
│                                                      │
│ 工具栏: [全部接受] [全部拒绝] [只接受语气词]           │
│         [搜索替换] [导出SRT]                           │
│                                                      │
│  🔵[说话人A] 0:09 ─────────────────────────────────   │
│  兴奋感在于说我意识到我所有的无论是生活                  │
│  ̶就̶是̶  ← 灰色(语气词)                                │
│  生活方式都需要升级了有一个机会升级                      │
│                                                      │
│  🔵[说话人A] 0:28                                     │
│  因为我用AI的方式就像我妈用AI                          │
│  我妈在把AI当百度用                                    │
│  ̶呃̶  ← 灰色                                          │
│  我再把AI当一个三倍的放大器用                           │
│                                                      │
│  🟢[说话人B] 0:38                                     │
│  你反思就是你觉得你也可以升维对不对                      │
│                                                      │
│  🔴[说话人A] 0:42  ← 红色(重复/bad take)               │
│  ̶我̶在̶把̶它̶当̶一̶个̶我̶的̶三̶倍̶放̶大̶器̶用̶  ← 与上方重复      │
│                                                      │
│  🔵[说话人A] 0:46                                     │
│  但是我可以，它是十倍，甚至可以变成百倍                  │
│                                                      │
│  ⭐🔵[说话人A] 3:01  ← 用户标记精彩(做hook)            │
│  我应该像培养一个天才小孩一样                           │
│  我知道这个小孩的能力比我强...                          │
│                                                      │
│  ───── 🔇 静音 2.3s ─────  ← 蓝色虚线(可删)          │
│                                                      │
│  ──────────────────────────────────────────           │
│  [✓ 生成粗剪]  [预览时间轴]  [重置全部]                │
└──────────────────────────────────────────────────────┘
```

**交互:**
1. 点击文字 → 视频跳转到对应时间，当前词高亮
2. 播放时 → 自动滚动文字稿，当前播放词高亮
3. 选中文字 → 右键: 删除/恢复/标记hook/修改说话人
4. 拖拽段落 → 调整视频顺序
5. 点击删除线标记 → 恢复原文（取消 AI 建议）
6. 双击段落 → 修改字幕文字（不影响视频，只改字幕）
7. Cmd+F → 搜索文字稿，高亮匹配

### 3.4 情景路径 (独有)

```
┌──────────────────────────────────────────────────────┐
│ 🎬 镜头网格 (可切换: 网格/列表/时间轴视图)             │
│                                                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │  2.3s   │ │  4.1s   │ │  1.8s   │ │  5.5s   │   │
│  │ [缩略图]│ │ [缩略图]│ │ [缩略图]│ │ [缩略图]│    │
│  │ 城市夜景│ │ 街道慢移│ │ 食物特写│ │ 人物对话│    │
│  │ ⭐⭐⭐   │ │ ⭐⭐     │ │ ⭐       │ │ ⭐⭐⭐   │   │
│  │ 🏙️ 风景│ │ 🚶 动作 │ │ 🍜 静物 │ │ 👤 人物 │   │
│  │ ✅ 已选 │ │ ✅ 已选 │ │         │ │ ✅ 已选 │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
│                                                      │
│  筛选: [全部▾] [风景] [人物] [动作] [静物] [特写]     │
│  排序: [AI推荐▾] [时间] [时长] [质量评分]             │
│                                                      │
│  设定:                                               │
│  主题: [_________________]                            │
│  风格: [快节奏▾] [电影感▾] [vlog▾] [叙事▾]           │
│  时长: [30s] [60s] [90s] [自定义___]                  │
│  配乐: [轻快▾] (可稍后在评审阶段调整)                  │
│                                                      │
│  [AI 自动选择]  [清除选择]  [✓ 生成粗剪]              │
└──────────────────────────────────────────────────────┘
```

---

## 4. Layer 1: 评审层 — 全面超越 Clapshot + Frame.io

### 4.1 对标功能清单

| 功能 | Clapshot | Frame.io | 我们 | Phase |
|------|----------|----------|------|-------|
| 时间戳评论 (毫秒精度) | ✅ | ✅ | ✅ | 2 |
| 画笔标注 (自由绘制) | ✅ 7色 | ✅ | ✅ 7色+3粗细 | 3 |
| 形状标注 (矩形/圆/箭头) | ❌ | ✅ | ✅ | 3 |
| 文字标注 (在画面上写字) | ❌ | ✅ | ✅ | 3 |
| 聚光灯/模糊标注 | ❌ | ✅ | ✅ 高亮+模糊 | 3 |
| 逐帧导航 (← →) | ✅ | ✅ | ✅ | 2 |
| 缩略图时间条 (sprite sheet) | ✅ | ✅ | ✅ | 3 |
| 音频波形可视化 | ✅ | ✅ | ✅ | 3 |
| SMPTE timecode 显示 | ✅ | ✅ | ✅ | 2 |
| Loop 区间 (I/O 键) | ✅ | ✅ | ✅ | 2 |
| 评论线程 (嵌套回复) | ✅ | ✅ | ✅ 单层 + AI回复 | 4 |
| 字幕轨道 (SRT/VTT) | ✅ | ❌ | ✅ 可编辑 | 3 |
| 播放倍速 (0.25x-2x) | ✅ | ✅ | ✅ 0.25x-4x | 2 |
| 拖拽 seek | ✅ | ✅ | ✅ | 2 |
| 评论时间区间 (范围选择) | ❌ | ✅ | ✅ | 2 |
| 评论 @提及 | ❌ | ✅ | ❌ 单用户不需要 | - |
| 版本对比 | ❌ | ✅ A/B | ✅ 版本diff+回退 | 4 |
| 审批工作流 (Approve/Reject) | ❌ | ✅ | ✅ | 4 |
| 评论导出 (JSON/CSV/EDL) | ✅ JSON | ✅ | ✅ JSON+CSV+EDL | 5 |
| 画面缩放/平移 (检查细节) | ❌ | ✅ | ✅ Cmd+滚轮 | 3 |
| 安全帧标记 (Safe zone) | ❌ | ✅ | ✅ 9:16/16:9/1:1 叠加 | 5 |
| 评论类型 (7种颜色) | ❌ | ❌ | ✅ 独有 | 2 |
| AI 自动重编辑 | ❌ | ❌ | ✅ 独有核心功能 | 4 |
| AI 回复 (解释修改) | ❌ | ❌ | ✅ 独有 | 4 |

### 4.2 高级标注工具 (超越 Clapshot，对标 Frame.io)

```python
class AnnotationTool:
    """标注工具类型"""
    FREEHAND = "freehand"      # 自由画笔 (Clapshot 有)
    RECTANGLE = "rectangle"     # 矩形框 (Frame.io 有)
    ELLIPSE = "ellipse"         # 椭圆 (Frame.io 有)
    ARROW = "arrow"             # 箭头 (Frame.io 有)
    LINE = "line"               # 直线
    TEXT = "text"               # 文字标注 (Frame.io 有)
    SPOTLIGHT = "spotlight"     # 聚光灯 (高亮区域，其余变暗)
    BLUR = "blur"               # 模糊标注 (遮挡敏感区域)

# 存储格式
annotation = {
    "tool": "rectangle",
    "color": "#FF0000",
    "width": 3,
    "points": [{"x": 100, "y": 200}, {"x": 400, "y": 500}],
    "text": "这里构图有问题",   # 仅 text 类型
    "opacity": 0.8,
}
# 整个标注组存为 composite data-URI (WebP)
# 同时保留 vector 数据用于 VLM 分析
```

**前端实现:**
- `components/review/DrawingOverlay.vue` — Canvas 叠加层
- `components/review/AnnotationToolbar.vue` — 工具栏
  - 8 种工具按钮 + 7 色调色板 + 3 级粗细 + 透明度滑块
  - 橡皮擦 (逐笔删除 or 区域擦除)
  - 撤销/重做栈 (Cmd+Z / Cmd+Shift+Z)
  - Shift 键约束: 画矩形→正方形, 画椭圆→正圆, 画线→水平/垂直/45°

### 4.3 视频播放器 (专业级)

```
控制栏:
┌────────────────────────────────────────────────────┐
│ ◀◀  ◀  ▶/⏸  ▶  ▶▶  │ 00:15:23:12  │ 🔊━━━━━━  │
│ -5s -1帧 播放 +1帧 +5s│ SMPTE码     │ 音量      │
├────────────────────────────────────────────────────┤
│ [0.25x] [0.5x] [1x] [1.5x] [2x] [4x]            │
│ [I 入点] [O 出点] [⟲ 循环]                         │
│ [🔍+ 放大] [🔍- 缩小] [↕ 适应] [⛶ 全屏]           │
│ [📐 安全帧: 无▾ | 9:16 | 16:9 | 1:1 | 4:5]       │
└────────────────────────────────────────────────────┘

快捷键:
Space     = 播放/暂停
J/K/L     = 倒放/暂停/正放 (连按L加速: 1x→2x→4x)
←/→       = 逐帧 (-1/+1 帧)
Shift+←/→ = 跳 5 秒
I/O       = 设置入点/出点
Cmd+L     = 循环入出点区间
C         = 添加评论 (自动填入当前 timecode)
D         = 进入画笔模式
1-7       = 选择评论类型
Cmd+Enter = 提交评论
R         = 触发 AI 重编辑
[/]       = 跳到上/下一条评论
Cmd+[/]   = 切换上/下一个版本
Cmd+Z     = 撤销 (画笔/评论)
Cmd++/-   = 时间轴缩放
F         = 全屏
Esc       = 退出画笔模式/全屏
```

### 4.4 评论面板 (右侧)

```
┌──────────────────────────────────┐
│ 评论 (12)  [筛选▾] [排序: 时间▾] │
│ ┌──────────────────────────────┐ │
│ │ 🔴 00:15:23 - 00:18:05       │ │
│ │ "这里被砍掉了"               │ │
│ │ ✅ resolved in v2            │ │
│ │ 🤖 AI: 已扩展至完整句子      │ │
│ │ [回复] [编辑] [删除]         │ │
│ └──────────────────────────────┘ │
│ ┌──────────────────────────────┐ │
│ │ 🔵 00:00:00 - 00:03:00       │ │
│ │ "加转场，黑屏写标题"         │ │
│ │ [画笔缩略图]                 │ │
│ │ ⏳ pending                   │ │
│ │ [回复] [编辑] [删除]         │ │
│ └──────────────────────────────┘ │
│ ┌──────────────────────────────┐ │
│ │ 🟡 02:00:15                   │ │
│ │ "这段啰嗦了删掉"             │ │
│ │ ⏳ pending                   │ │
│ └──────────────────────────────┘ │
│                                  │
│ ─── 版本 ──────────────────────  │
│ [v1 粗剪▾] → [v2 AI修改] → v3   │
│ [查看 diff] [回退到 v1]         │
│                                  │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│ [🤖 AI 重编辑]  [预览变更]      │
│ ■■■■■■■■░░ 80% 渲染中...        │
└──────────────────────────────────┘
```

---

## 5. Layer 2: 桥接层 — 独创 + 超越 ChatCut

### 5.1 对标功能清单

| 功能 | ChatCut | 我们 | Phase |
|------|---------|------|-------|
| 自然语言→编辑指令 | ✅ (对话式) | ✅ (时间轴精确定位) | 4 |
| 多步骤 agentic 指令 | ❌ | ✅ (一条评论→多个指令) | 4 |
| 编辑预览 (dry run) | ❌ | ✅ (生成diff不渲染) | 4 |
| 冲突检测 | ❌ | ✅ (矛盾评论标记) | 5 |
| 画笔→VLM 理解 | ❌ | ✅ (截帧+标注→VLM描述) | 5 |
| 变更摘要 | ❌ | ✅ (自然语言描述修改) | 4 |
| 指令验证 | ❌ | ✅ (schema校验+范围检查) | 4 |

### 5.2 评论定位引擎 (独创)

```python
class CommentResolver:
    """将时间戳评论映射到 EDITS 列表中的具体操作"""

    def resolve(self, comment: Comment, edits: List[Segment],
                transcript: List[Word]) -> ResolvedComment:
        """
        Args:
            comment: 用户评论 (time, end_time, text, type, drawing)
            edits: 当前剪辑方案
            transcript: Whisper 词级转录

        Returns:
            ResolvedComment with:
            - matched_segments: 匹配到的 segment 索引列表
            - gap_info: 如果评论指向被砍内容, 返回 gap 信息
            - drawing_description: VLM 对画笔标注的描述 (if any)
            - suggested_action: 初步建议的操作类型
        """
        # 1. 二分查找: time → 找到包含/最近的 segment
        # 2. Gap 检测: 如果 time 落在两个 segment 之间
        #    → 查找原始转录中被砍掉的内容
        #    → 返回 gap 内的完整文本和时间范围
        # 3. 区间匹配: 如果 end_time 存在
        #    → 找出区间内所有 segments
        # 4. VLM 分析 (如果有画笔):
        #    → 截取该帧 + 叠加画笔 → 发送给 VLM
        #    → "用户用红色圆圈标记了画面右侧人物的脸部"
```

### 5.3 编辑指令集 (全面)

```python
# 11种指令类型，覆盖所有剪辑操作
INSTRUCTION_TYPES = {
    "extend":      "扩展 segment 时间范围",
    "trim":        "缩短 segment 时间范围",
    "remove":      "删除 segment",
    "insert":      "从原始视频插入新片段",
    "reorder":     "调整 segment 顺序",
    "split":       "拆分一个 segment 为两个",
    "merge":       "合并相邻 segments",
    "transition":  "插入转场效果",
    "subtitle":    "修改字幕文本",
    "speaker":     "修改说话人标记 (影响镜头跟踪)",
    "hook":        "复制 segment 到开头做 hook",
    "speed":       "变速 (慢动作/加速)",
    "broll":       "插入 B-roll / stock 素材",
    "audio":       "音频操作 (增强/降噪/配音/BGM)",
}
```

---

## 6. Layer 3: AI 重编辑引擎 — 全面超越 OpenStoryline + VideoAgent

### 6.1 对标功能清单

| 功能 | OpenStoryline | VideoAgent | 我们 | Phase |
|------|--------------|------------|------|-------|
| 节点 DAG | ✅ 16节点 | ✅ 30+ agent | ✅ 10节点 | 4 |
| Artifact Store | ✅ | ❌ | ✅ 版本化目录 | 4 |
| Mode 参数 | ✅ auto/skip | ❌ | ✅ auto/skip/force | 4 |
| 选择性重跑 | ✅ | ❌ | ✅ 依赖图追踪 | 4 |
| Style Skill | ✅ 3种类型 | ❌ | ✅ YAML + 自动提取 | 5 |
| 音频增强 | ❌ | ❌ | ✅ FFmpeg filter chain | 5 |
| TTS 配音 | ✅ 302.ai/ByteDance | ✅ | ✅ edge-tts/CosyVoice | 5 |
| BGM 选择 + beat sync | ✅ librosa | ❌ | ✅ librosa beat 分析 | 5 |
| 转场效果库 | ✅ fade | ❌ | ✅ fade/dissolve/wipe/黑屏标题 | 5 |
| Stock 素材搜索 | ✅ Pexels | ❌ | ✅ Pexels API | 5 |
| 多平台 reframe | ❌ | ❌ | ✅ 9:16/16:9/1:1/4:5 | 5 |
| 时间轴精确定位 | ❌ (对话式) | ❌ | ✅ 独有 | 2-4 |
| 画笔标注反馈 | ❌ | ❌ | ✅ 独有 | 3-5 |
| 版本 diff + 回退 | ❌ | ❌ | ✅ 独有 | 4 |
| Clip 变速/倒放 | ❌ | ✅ | ✅ | 5 |

### 6.2 节点 DAG (10 节点)

```python
NODE_GRAPH = {
    # Phase 0 节点 (粗剪阶段生成, 评审阶段复用)
    "transcode":     {"deps": [],              "desc": "转码为处理友好格式"},
    "analyze":       {"deps": ["transcode"],   "desc": "Whisper转录+VAD+场景分割"},
    "thumbnails":    {"deps": ["transcode"],   "desc": "FFmpeg sprite sheet"},
    "waveform":      {"deps": ["transcode"],   "desc": "音频波形数据"},

    # Phase 4 节点 (AI 重编辑)
    "apply_edits":   {"deps": ["analyze"],     "desc": "应用编辑指令到EDITS列表"},
    "render_frames": {"deps": ["apply_edits", "thumbnails"], "desc": "cv2+PIL逐帧渲染"},
    "merge_audio":   {"deps": ["render_frames", "transcode"], "desc": "FFmpeg合并音频"},

    # Phase 5 节点 (增强, 可选)
    "enhance_audio": {"deps": ["merge_audio"], "desc": "音频增强(降噪/均衡/响度)"},
    "add_bgm":       {"deps": ["enhance_audio"], "desc": "BGM混合+beat sync"},
    "final_export":  {"deps": ["add_bgm"],    "desc": "最终编码+多平台reframe"},
}
```

**智能重跑示例:**
| 用户操作 | 触发节点 | 重跑链 | 跳过的节点 |
|---------|---------|--------|-----------|
| 修改评论→改 EDITS | apply_edits | apply→render→merge→enhance→bgm→export | transcode, analyze, thumbnails, waveform |
| 只改字幕文字 | render_frames | render→merge→enhance→bgm→export | transcode, analyze, thumbnails, waveform, apply_edits |
| 换 BGM | add_bgm | bgm→export | 前面全部跳过 |
| 换音频增强参数 | enhance_audio | enhance→bgm→export | 前面全部跳过 |

### 6.3 音频增强 (Descript Studio Sound 级别)

```python
class AudioEnhancer:
    """音频增强 — 对标 Descript Studio Sound"""

    def enhance(self, audio_path: str, config: AudioConfig) -> str:
        """
        FFmpeg filter chain:
        1. 降噪: afftdn (FFmpeg 自带降噪, 或 RNNoise)
        2. 均衡: equalizer (提升人声频段 300-3000Hz)
        3. 压缩: acompressor (缩小动态范围, 防爆音)
        4. 响度标准化: loudnorm (LUFS -16, 符合平台标准)
        5. 采样率: -ar 44100 (防止 loudnorm 改变采样率 bug)
        """
        filter_chain = (
            "afftdn=nf=-25,"               # 降噪
            "equalizer=f=1000:t=q:w=1:g=3," # 提升人声
            "acompressor=threshold=-20dB:ratio=4:attack=5:release=50," # 压缩
            "loudnorm=I=-16:LRA=11:TP=-1.5," # 响度标准化
        )
```

### 6.4 TTS 配音

```python
class TTSVoiceover:
    """TTS 配音生成"""

    PROVIDERS = {
        "edge_tts": {"desc": "微软 Edge TTS (免费)", "quality": "中"},
        "cosy_voice": {"desc": "CosyVoice (阿里, 高质量)", "quality": "高"},
        "fish_speech": {"desc": "Fish Speech (开源)", "quality": "高"},
    }

    def generate(self, text: str, voice: str, provider: str = "edge_tts") -> str:
        """生成配音音频, 返回文件路径"""

    def generate_with_timing(self, segments: List[dict]) -> str:
        """按 EDITS 列表的时间节奏生成配音, 对齐字幕"""
```

### 6.5 BGM 选择 + Beat Sync

```python
class BGMSelector:
    """BGM 选择与节拍同步"""

    def analyze_beats(self, bgm_path: str) -> List[float]:
        """librosa beat 分析, 返回节拍时间点列表"""

    def select_from_library(self, mood: str, duration: float) -> str:
        """从本地 BGM 库中选择合适的曲目"""
        # mood: upbeat, calm, dramatic, cinematic, playful...

    def beat_sync_edits(self, edits: List[Segment], beats: List[float]) -> List[Segment]:
        """调整 segment 切点对齐 BGM 节拍"""
        # 微调每个 segment 的 end 时间 (±0.2s) 使切点落在节拍上
```

### 6.6 转场效果库

```python
TRANSITION_EFFECTS = {
    "cut":           {"desc": "硬切 (默认)", "duration": 0},
    "fade_black":    {"desc": "淡入淡出黑屏", "duration": 0.5},
    "fade_white":    {"desc": "淡入淡出白屏", "duration": 0.5},
    "cross_dissolve":{"desc": "交叉溶解", "duration": 0.5},
    "wipe_left":     {"desc": "左擦", "duration": 0.5},
    "wipe_right":    {"desc": "右擦", "duration": 0.5},
    "zoom_in":       {"desc": "推进 (假zoom)", "duration": 0.3},
    "zoom_out":      {"desc": "拉远 (假zoom)", "duration": 0.3},
    "black_title":   {"desc": "黑屏+标题文字", "duration": 3.0},
    "whoosh":        {"desc": "音效whoosh过渡", "duration": 0.8},
    "glitch":        {"desc": "故障风转场", "duration": 0.3},
    "flash":         {"desc": "闪白转场", "duration": 0.15},
}
```

### 6.7 多平台自动 Reframe

```python
class SocialReframe:
    """自动裁剪到不同平台比例"""

    PLATFORMS = {
        "tiktok":    {"ratio": (9, 16),  "max_duration": 180},
        "instagram": {"ratio": (4, 5),   "max_duration": 90},
        "youtube":   {"ratio": (16, 9),  "max_duration": None},
        "shorts":    {"ratio": (9, 16),  "max_duration": 60},
        "wechat":    {"ratio": (9, 16),  "max_duration": 60},
        "xiaohongshu":{"ratio": (3, 4),  "max_duration": 300},
        "square":    {"ratio": (1, 1),   "max_duration": None},
    }

    def reframe(self, video_path: str, platform: str,
                speaker_positions: dict) -> str:
        """智能裁剪: 跟踪说话人位置, 保持主体居中"""
```

---

## 7. API 设计 (完整)

### 7.1 Phase 0: 粗剪 API

```
POST   /api/roughcut/init              — 初始化 (传入视频路径)
GET    /api/roughcut/detect-type        — 视频类型检测结果
GET    /api/roughcut/transcript         — 转录文案 (词级, 含说话人)
GET    /api/roughcut/fillers            — AI 预标记列表
POST   /api/roughcut/fillers/batch      — 批量接受/拒绝标记
POST   /api/roughcut/transcript/edit    — 提交文案编辑
GET    /api/roughcut/scenes             — 场景分割结果 (情景路径)
POST   /api/roughcut/scenes/select      — 提交镜头选择
POST   /api/roughcut/generate           — 生成粗剪 (后台 job)
GET    /api/roughcut/preview-stats      — 预计时长等统计
```

### 7.2 Phase 1-4: 评审 + AI 重编辑 API

```
POST   /api/review/init                 — 初始化评审会话
GET    /api/review/state                — 当前评审状态
POST   /api/review/comments             — 添加评论
PATCH  /api/review/comments/:id         — 修改评论
DELETE /api/review/comments/:id         — 删除评论
GET    /api/review/versions             — 版本列表
GET    /api/review/versions/:v          — 版本详情
GET    /api/review/diff/:v1/:v2         — 版本 diff
POST   /api/review/ai-reedit            — AI 重编辑 (后台 job)
POST   /api/review/ai-reedit/dry-run    — 预览变更
POST   /api/review/rollback/:v          — 回退到指定版本
POST   /api/review/thumbnails           — 生成缩略图 (后台)
POST   /api/review/waveform             — 生成波形 (后台)
POST   /api/review/export/comments      — 导出评论 (JSON/CSV/EDL)
```

### 7.3 Phase 5: 增强 API

```
POST   /api/review/enhance/audio        — 音频增强
POST   /api/review/enhance/tts          — TTS 配音
POST   /api/review/enhance/bgm          — BGM 添加
POST   /api/review/enhance/transition   — 转场效果
POST   /api/review/enhance/reframe      — 多平台裁剪
GET    /api/review/styles               — 风格列表
POST   /api/review/styles               — 保存风格
GET    /api/stock/search                — Stock 素材搜索 (Pexels)
POST   /api/stock/download              — 下载 stock 素材
```

---

## 8. 前端组件清单

```
components/roughcut/                    ← Phase 0
├── VideoTypeSelector.vue               — 类型选择 (自动+手动)
├── TranscriptEditor.vue                — 口播文案编辑器
├── TranscriptParagraph.vue             — 单段落组件
├── FillerMarkup.vue                    — 语气词标记
├── SceneSelector.vue                   — 情景镜头选择器
├── SceneCard.vue                       — 单镜头卡片
└── RoughCutStats.vue                   — 统计栏

components/review/                      ← Phase 2-5
├── ReviewPlayer.vue                    — 视频播放器
├── PlayerControls.vue                  — 播放控制栏
├── ReviewTimeline.vue                  — 时间轴整合
├── ThumbnailStrip.vue                  — 缩略图条
├── WaveformTrack.vue                   — 音频波形
├── TrackComments.vue                   — 评论标记轨道
├── CommentInput.vue                    — 评论输入
├── CommentPanel.vue                    — 评论列表面板
├── CommentCard.vue                     — 单条评论卡片
├── DrawingOverlay.vue                  — 画笔+形状 Canvas
├── AnnotationToolbar.vue               — 标注工具栏
├── SubtitleEditor.vue                  — 字幕编辑
├── VersionSwitcher.vue                 — 版本切换
├── VersionDiff.vue                     — 版本 diff 高亮
├── SafeZoneOverlay.vue                 — 安全帧叠加
├── EnhancePanel.vue                    — 增强选项面板
└── ExportDialog.vue                    — 导出对话框

stores/
├── roughcut.js                         — 粗剪状态
└── review.js                           — 评审状态

views/
├── RoughCutView.vue                    — 粗剪页面
└── ReviewView.vue                      — 评审页面
```

---

## 9. 里程碑

| Phase | 交付物 | 工作量 | 累计 |
|-------|--------|--------|------|
| 0 | 智能粗剪 (口播文案编辑+bad take检测+情景镜头选择+混合路径) | 4 天 | 4 天 |
| 1 | 评审数据层 (review_store + artifact_store + API) | 1.5 天 | 5.5 天 |
| 2 | 核心评审 UI (播放器+时间轴+评论+逐帧+loop+倍速+快捷键) | 2.5 天 | 8 天 |
| 3 | 高级评审 (画笔+形状+缩略图+波形+字幕编辑+安全帧+画面缩放) | 3 天 | 11 天 |
| 4 | AI 重编辑引擎 (桥接层+DAG+智能重跑+版本diff+dry run+AI回复) | 3 天 | 14 天 |
| 5 | 增强能力 (音频增强+TTS+BGM+转场库+stock搜索+reframe+style skill+评论导出) | 4 天 | **18 天** |

---

## 10. 验证标准

### Phase 0 (粗剪):
- [ ] 1870_raw.MP4 自动检测为 "speech"
- [ ] 转录文案显示, 12+ 处语气词被 AI 预标记
- [ ] 3+ 处重复片段 (bad takes) 被检测
- [ ] 删除段落→对应视频被删, 时长统计更新
- [ ] 标记精彩片段→hook 自动生成
- [ ] 一键接受全部语气词标记
- [ ] 生成粗剪 ≈ v4 效果

### Phase 2-3 (评审):
- [ ] 逐帧导航精确到 1/30s
- [ ] J/K/L 快捷键正常, 连按加速
- [ ] 缩略图条鼠标悬停预览
- [ ] 音频波形对齐
- [ ] 7 种评论类型颜色正确
- [ ] 画笔自由绘制 + 矩形 + 箭头 + 文字标注
- [ ] 撤销/重做正常
- [ ] 安全帧叠加 (9:16)
- [ ] 评论导出 JSON/CSV

### Phase 4 (AI 重编辑):
- [ ] "15.3s: 培养被砍了" → 正确定位 segment + 扩展
- [ ] Dry run 返回 diff 预览
- [ ] AI 重编辑只重跑受影响节点
- [ ] 版本 diff 高亮变更片段
- [ ] 回退到任意历史版本
- [ ] AI 回复解释每条评论的处理

### Phase 5 (增强):
- [ ] 音频增强: 降噪+均衡+压缩+响度标准化
- [ ] TTS 配音对齐字幕时间
- [ ] BGM beat sync 切点对齐节拍
- [ ] 3+ 种转场效果可用
- [ ] Pexels stock 搜索返回结果
- [ ] 一键导出 9:16 + 16:9 + 1:1
- [ ] Style Skill 保存后可在新项目加载

---

## 11. 借鉴与超越总结

| 竞品 | 我们借鉴了什么 | 我们超越了什么 |
|------|--------------|--------------|
| **Descript** | 文字即视频理念, 语气词预标记 | +bad take检测, +非口播支持, +免费本地 |
| **Gling** | 静音/废话自动检测 | +文案编辑(vs只删废话), +情景路径 |
| **Clapshot** | 画笔7色, sprite sheet, SMPTE码 | +形状/箭头/文字标注, +评论类型, +AI重编辑 |
| **Frame.io** | 形状标注, 安全帧, 版本对比 | +AI自动重编辑, +版本diff, +画笔→VLM |
| **OpenStoryline** | artifact store, mode参数, style skill, TTS, BGM | +时间轴精确定位, +画笔标注, +版本回退 |
| **VideoAgent** | 多agent协作理念 | +一体化UI (vs纯API), +评审闭环 |
| **ChatCut** | 自然语言编辑指令 | +时间轴定位(vs对话), +dry run预览 |
