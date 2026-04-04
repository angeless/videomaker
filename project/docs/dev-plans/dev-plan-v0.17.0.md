# VideoEditor 版本开发计划（v0.17.0）

**文档版本：** V1.0
**日期：** 2026-04-04
**基线 Commit：** 158a39f (Merge feat/v0.16.0-ai-reedit into main)
**基线 VERSION：** 0.16.0

---

## 1. 版本目标

VLM 画笔分析引擎：用户在评审画面上画笔标注 → VLM 识别标注区域内容 → 生成画面描述 → 增强 IntentRouter 多模态理解 → AI 主动画面诊断。让评审系统从"只懂文字"进化为"看得懂画面"。

## 2. 版本范围

### 包含的需求

**第 1 层：画笔区域智能识别（核心能力）**
- VLM 模型 adapter 层（本地 LLaVA / API GPT-4o / Claude Vision，走 adapter）
- 画笔区域裁剪器（DrawingOverlay 笔画 JSON → 裁剪区域图像）
- 区域画面描述（VLM 接收裁剪图像 → 返回自然语言描述）
- 评论框 AI 预填充（画笔完成后自动填充画面描述）

**第 2 层：多模态意图理解（增强 IntentRouter）**
- 多模态 IntentRouter 升级（文字 + 画面描述 → 更精确的编辑指令）
- 画笔→语义指令映射（圈住 logo → resize 指令，框选背景 → B-roll 搜索词）
- 指代消解（"这个太大了" + VLM 上下文 → 明确"logo 太大"）

**第 3 层：AI 主动画面诊断**
- 关键帧自动诊断（构图/曝光/色温/连续性 4 类检查）
- AI 评审员评论（诊断结果 → CommentPanel 中展示）
- 诊断面板 UI（DiagnosticsPanel.vue）

**API + UI**
- VLM 分析 API 端点
- 诊断 API 端点
- VLM 设置页（模型选择 / provider 配置）
- 集成测试 + 端到端测试

### 不包含的需求（Future）

| 需求 | 推迟原因 |
|------|---------|
| VLM 实时视频流分析 | 性能要求过高，需 GPU 优化 |
| 画面语义编辑（自动抠图/替换） | 需 SAM 模型，复杂度极高 |
| 多模型 ensemble | 单模型验证优先 |
| 视频理解（跨帧推理） | 单帧分析验证后再扩展 |
| GPU 加速渲染 | 与 VLM 独立，v0.18+ |

---

## 3. 技术设计

### 3.1 模块位置

```
modules/
├── review_engine/
│   ├── vlm_analyzer.py         ← VLM 分析核心（新建）
│   ├── region_extractor.py     ← 画笔区域裁剪（新建）
│   ├── frame_diagnostics.py    ← 主动画面诊断（新建）
│   ├── intent_router.py        ← 扩展：多模态输入
│   └── ...
├── adapters/
│   └── vlm_adapter.py          ← VLM provider adapter（新建）
└── app_api/routes/
    └── vlm_routes.py           ← VLM API 路由（新建）
```

### 3.2 VLM Adapter 抽象

```python
class VLMAdapter(Protocol):
    def describe_image(self, image: PIL.Image, prompt: str) -> str: ...
    def is_available(self) -> bool: ...

# 实现：
# - LocalLlavaAdapter  → 本地 LLaVA 7B (transformers)
# - OpenAIVisionAdapter → GPT-4o API
# - ClaudeVisionAdapter → Claude Vision API
# - StubAdapter         → 测试用 mock
```

### 3.3 数据流

```
DrawingOverlay (笔画 JSON)
  ↓
RegionExtractor.extract(frame, strokes) → PIL.Image (裁剪区域)
  ↓
VLMAnalyzer.describe_region(image) → "画面右下角有一个咖啡杯"
  ↓ (回填到评论 UI)
CommentInput 预填充 AI 描述
  ↓ (用户确认/修改后提交)
IntentRouter.route(comment_text, visual_context) → List[EditInstruction]
```

### 3.4 与现有系统的边界

| 现有系统 | 交互方式 | 改动程度 |
|---------|---------|---------|
| CLIPEncoder | 共存不冲突（CLIP 搜索 vs VLM 理解） | 无改动 |
| DrawingOverlay | 读取 serializeToStore() 输出的笔画 JSON | 扩展：新增 `onAnnotationComplete` 事件 |
| IntentRouter | 扩展输入：增加 `visual_context` 可选参数 | 向后兼容扩展 |
| ReviewStore | 扩展 comment 字段：增加 `visual_context` | DDL migration |
| CommentInput | 扩展：AI 描述预填充 | UI 扩展 |
| CommentPanel | 扩展：展示 AI 评审员诊断 | UI 扩展 |

---

## 4. 任务列表

| 任务ID | 任务名称 | 优先级 | 依赖 | 状态 |
|--------|---------|--------|------|------|
| R1 | VLMAdapter — provider 抽象层 | P0 | — | Planned |
| R2 | LocalLlavaAdapter — 本地 LLaVA 推理 | P0 | R1 | Planned |
| R3 | APIVisionAdapter — OpenAI/Claude Vision API | P1 | R1 | Planned |
| R4 | RegionExtractor — 画笔区域裁剪 | P0 | — | Planned |
| R5 | VLMAnalyzer — 区域画面描述 | P0 | R1, R4 | Planned |
| R6 | ReviewStore migration — visual_context 字段 | P0 | — | Planned |
| R7 | CommentInput 扩展 — AI 描述预填充 | P0 | R5 | Planned |
| R8 | DrawingOverlay 扩展 — onAnnotationComplete 事件 | P0 | — | Planned |
| R9 | IntentRouter 升级 — 多模态输入 | P0 | R5 | Planned |
| R10 | 指代消解 — "这个"→具体对象 | P1 | R9 | Planned |
| R11 | FrameDiagnostics — 构图检查 | P1 | R1 | Planned |
| R12 | FrameDiagnostics — 曝光/色温检查 | P1 | R11 | Planned |
| R13 | FrameDiagnostics — 连续性检查 | P1 | R11 | Planned |
| R14 | AI 评审员 — 诊断→评论自动生成 | P1 | R11-R13 | Planned |
| R15 | DiagnosticsPanel.vue — 诊断面板 UI | P1 | R14 | Planned |
| R16 | VLM API — describe + diagnose 端点 | P0 | R5, R14 | Planned |
| R17 | VLM 设置页 — provider 选择 + 测试连接 | P2 | R1 | Planned |
| R18 | 集成测试 + 端到端验证 | P0 | ALL | Planned |

---

## 5. 各任务详细定义

### R1: VLMAdapter — provider 抽象层

**目标：** 定义 VLM 模型调用的统一接口，支持多 provider 切换。

**涉及文件：**
- `modules/adapters/vlm_adapter.py` — 新建
- `tests/unit/adapters/test_vlm_adapter.py` — 新建

**输入：** `image: PIL.Image`, `prompt: str`, `max_tokens: int`
**输出：** `VLMResponse {text: str, model: str, latency_ms: int, tokens_used: int}`

**验收标准：**
- [ ] `VLMAdapter` Protocol 定义: `describe_image()`, `is_available()`, `get_model_info()`
- [ ] `VLMResponse` dataclass: text, model, latency_ms, tokens_used
- [ ] `StubVLMAdapter`: 返回固定文本，用于测试
- [ ] `get_vlm_adapter(provider: str)` 工厂函数: 根据 settings 返回对应 adapter
- [ ] provider 不可用时返回 None + 日志警告（优雅降级）
- [ ] UT 4 条: stub_works / factory_returns_correct / unavailable_graceful / response_format

**依赖项：** 无
**已知约束：** 遵循现有 adapter 模式（参考 tts_voiceover.py 的 edge-tts adapter）

---

### R2: LocalLlavaAdapter — 本地 LLaVA 推理

**目标：** 封装本地 LLaVA-v1.5-7B 模型，实现离线画面描述。

**涉及文件：**
- `modules/adapters/vlm_adapter.py` — 扩展
- `tests/unit/adapters/test_vlm_local_llava.py` — 新建

**输入：** `image: PIL.Image`, `prompt: str`
**输出：** `VLMResponse` (本地推理结果)

**验收标准：**
- [ ] 延迟加载 LLaVA 模型（首次调用时加载，约 4GB VRAM / 8GB RAM）
- [ ] `is_available()`: 检查 transformers + torch + 模型权重
- [ ] `describe_image()`: image + prompt → text (中文 prompt 支持)
- [ ] 无 GPU 时自动 CPU 推理（慢但可用）
- [ ] 模型不存在时 `is_available()=False`，不崩溃
- [ ] UT 3 条 (mock model): inference_returns_text / unavailable_check / lazy_loading

**依赖项：** R1
**已知约束：**
- LLaVA 需要 `transformers>=4.36`，与现有 CLIP 共存（同一 transformers 包）
- 首次加载约 30-60 秒，需要 loading 状态反馈
- requirements.txt 中 llava 相关依赖标注为可选

---

### R3: APIVisionAdapter — OpenAI/Claude Vision API

**目标：** 封装云端 VLM API（GPT-4o, Claude Vision），作为本地模型的高质量替代。

**涉及文件：**
- `modules/adapters/vlm_adapter.py` — 扩展
- `tests/unit/adapters/test_vlm_api_adapter.py` — 新建

**输入：** `image: PIL.Image`, `prompt: str`
**输出：** `VLMResponse`

**验收标准：**
- [ ] `OpenAIVisionAdapter`: base64 编码图像 → GPT-4o API
- [ ] `ClaudeVisionAdapter`: base64 编码图像 → Claude API
- [ ] API key 从 settings 读取（复用现有 AI settings 架构）
- [ ] 超时 30s + 重试 1 次
- [ ] API 失败 → 降级到本地 LLaVA（如可用）
- [ ] 图像预处理：超过 2048px 缩放、大于 5MB 压缩
- [ ] UT 4 条 (mock HTTP): openai_success / claude_success / timeout_retry / fallback_local

**依赖项：** R1, R2
**已知约束：** 需要联网 + API key，符合"数据不上云"定位需用户主动选择

---

### R4: RegionExtractor — 画笔区域裁剪

**目标：** 从视频帧中裁剪出用户画笔标注的区域。

**涉及文件：**
- `modules/review_engine/region_extractor.py` — 新建
- `tests/unit/review_engine/test_region_extractor.py` — 新建

**输入：** `frame: PIL.Image (视频帧)`, `strokes: List[Dict] (DrawingOverlay 输出的笔画 JSON)`
**输出：** `ExtractionResult {region_image: PIL.Image, bbox: Tuple[x,y,w,h], tool_type: str, confidence: float}`

**验收标准：**
- [ ] 矩形工具 (rect) → 直接裁剪矩形区域
- [ ] 椭圆工具 (circle) → 裁剪外接矩形
- [ ] 画笔工具 (pen) → 计算笔画包围盒 (bounding box) + 10% padding
- [ ] 箭头工具 (arrow) → 箭头指向点为中心，裁剪 200×200 区域（可配置）
- [ ] spotlight → 使用高亮区域
- [ ] 无标注笔画 → 返回整帧图像
- [ ] 多个笔画 → 合并包围盒
- [ ] 坐标归一化：DrawingOverlay 坐标 (canvas px) → 视频帧坐标 (video px)
- [ ] UT 6 条: rect / circle / pen_bbox / arrow_center / multi_stroke / no_stroke_full_frame

**依赖项：** 无
**已知约束：** DrawingOverlay 输出格式固定（参考 `serializeToStore()` 方法）

---

### R5: VLMAnalyzer — 区域画面描述

**目标：** VLM 分析核心，接收裁剪区域图像，返回结构化画面描述。

**涉及文件：**
- `modules/review_engine/vlm_analyzer.py` — 新建
- `tests/unit/review_engine/test_vlm_analyzer.py` — 新建

**输入：** `region_image: PIL.Image`, `context: AnalysisContext (video_type, timestamp_ms, surrounding_text)`
**输出：** `RegionDescription {summary: str, objects: List[str], scene_type: str, visual_issues: List[str]}`

**验收标准：**
- [ ] `describe_region(image, context)` → 自然语言描述 + 结构化字段
- [ ] prompt 工程：引导 VLM 输出 JSON 格式（对象列表 / 场景类型 / 视觉问题）
- [ ] VLM 返回纯文本时 → regex 解析为结构化输出
- [ ] VLM 不可用 → 降级返回 `RegionDescription(summary="[画面区域]", objects=[])`
- [ ] 中文 prompt + 中文输出
- [ ] 缓存：同一帧+同一区域 5 分钟内不重复调用
- [ ] UT 5 条: structured_output / text_fallback_parse / degradation / cache_hit / chinese_prompt

**依赖项：** R1 (adapter), R4 (region_extractor)
**已知约束：** VLM 输出格式不稳定，需要 robust parsing

---

### R6: ReviewStore migration — visual_context 字段

**目标：** 扩展评论数据库表，存储 VLM 分析的视觉上下文。

**涉及文件：**
- `modules/review_engine/review_store.py` — 扩展
- `tests/unit/review_engine/test_review_store.py` — 扩展

**DDL 变更：**
```sql
ALTER TABLE review_comments ADD COLUMN visual_context TEXT;
-- JSON: {"summary": "...", "objects": [...], "bbox": [x,y,w,h]}
ALTER TABLE review_comments ADD COLUMN ai_generated INTEGER DEFAULT 0;
-- 0=用户评论, 1=AI诊断评论
```

**验收标准：**
- [ ] 自动 migration：表已存在时 ALTER TABLE 添加新列
- [ ] `add_comment()` 接受 `visual_context` 可选参数
- [ ] `add_comment()` 接受 `ai_generated` 标志
- [ ] `list_comments()` 返回结果包含 visual_context
- [ ] `list_comments(filter_ai=True/False)` 过滤 AI 评论
- [ ] 向后兼容：旧数据 visual_context=NULL 正常工作
- [ ] UT 4 条: migration / add_with_context / list_with_filter / backward_compat

**依赖项：** 无
**已知约束：** SQLite ALTER TABLE 只支持 ADD COLUMN（不支持改类型/删列）

---

### R7: CommentInput 扩展 — AI 描述预填充

**目标：** 画笔标注完成后，自动调用 VLM 分析并预填充评论输入框。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/CommentInput.vue` — 扩展
- `apps/desktop/ui-vue/src/stores/review.js` — 扩展

**交互流程：**
1. 用户在 DrawingOverlay 画完标注 → 触发 `onAnnotationComplete`
2. 前端调用 `POST /api/review/{id}/vlm/describe` (带帧截图 + 笔画 JSON)
3. 返回 AI 描述 → 显示在 CommentInput 输入框上方作为上下文提示
4. 用户可以编辑/删除 AI 描述，或在此基础上补充评论

**验收标准：**
- [ ] AI 描述显示为灰色提示文本（区别于用户输入）
- [ ] 显示 loading spinner（VLM 分析中）
- [ ] VLM 不可用 → 不显示提示（静默降级）
- [ ] 用户可以点击"×"关闭 AI 提示
- [ ] 提交评论时 visual_context 随评论一起提交
- [ ] UT 2 条: shows_ai_hint / hides_on_dismiss

**依赖项：** R5 (VLMAnalyzer), R8 (onAnnotationComplete)
**已知约束：** VLM 延迟 1-5s，需要 loading 状态

---

### R8: DrawingOverlay 扩展 — onAnnotationComplete 事件

**目标：** DrawingOverlay 完成标注后发射事件，携带帧截图和笔画数据。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/DrawingOverlay.vue` — 扩展
- `apps/desktop/ui-vue/src/components/review/ReviewView.vue` — 扩展

**验收标准：**
- [ ] 新增 `annotationComplete` emit 事件
- [ ] 触发时机：用户松开鼠标（mouseup）后 500ms 无新笔画 → 视为标注完成
- [ ] 事件 payload: `{strokes: [...], frameDataUrl: "data:image/jpeg;...", timestamp_ms: N}`
- [ ] `frameDataUrl`: 从 video 元素截取当前帧（canvas.toDataURL）
- [ ] ReviewView 监听事件，调用 VLM API
- [ ] 用户继续画 → 取消上一次请求 (debounce)
- [ ] UT 2 条: event_fires / debounce_cancels

**依赖项：** 无
**已知约束：** canvas.toDataURL 在跨域视频上可能失败（tainted canvas），需 catch

---

### R9: IntentRouter 升级 — 多模态输入

**目标：** 扩展 IntentRouter，接受 visual_context 作为额外上下文，生成更精确的指令。

**涉及文件：**
- `modules/review_engine/intent_router.py` — 扩展
- `tests/unit/review_engine/test_intent_router.py` — 扩展

**输入变更：**
```python
# 之前
def route_comment_to_instruction(comment_text, resolved_comment, context) -> List[EditInstruction]

# 之后（向后兼容）
def route_comment_to_instruction(comment_text, resolved_comment, context, visual_context=None) -> List[EditInstruction]
```

**验收标准：**
- [ ] visual_context=None → 行为不变（向后兼容）
- [ ] visual_context 存在 → 注入 SYSTEM_PROMPT 的上下文部分
- [ ] 示例："这个太大了" + visual_context.objects=["logo"] → `resize(target="logo")`
- [ ] 示例："换个背景" + visual_context.scene_type="outdoor_sky" → `broll(query="天空替换")`
- [ ] LLM prompt 模板更新：增加 `[画面上下文]` 区块
- [ ] UT 4 条: backward_compat / logo_resize / broll_with_context / no_context_fallback

**依赖项：** R5
**已知约束：** LLM prompt 变长可能影响延迟

---

### R10: 指代消解 — "这个"→具体对象

**目标：** 利用 VLM 视觉上下文消解评论中的模糊指代。

**涉及文件：**
- `modules/review_engine/vlm_analyzer.py` — 扩展 `resolve_reference()`
- `tests/unit/review_engine/test_reference_resolution.py` — 新建

**输入：** `comment_text: str`, `visual_context: RegionDescription`
**输出：** `resolved_text: str` (指代替换后的文本)

**验收标准：**
- [ ] "这个太大了" + objects=["logo"] → "logo 太大了"
- [ ] "把这删了" + objects=["water_bottle", "cup"] → "把 water_bottle 和 cup 删了"（多对象）
- [ ] "颜色不对" + visual_issues=["色温偏冷"] → "颜色不对（色温偏冷）"
- [ ] 无指代词 → 返回原文不变
- [ ] 多指代 → 依次消解
- [ ] UT 5 条: single_ref / multi_object / color_issue / no_ref_passthrough / multi_ref

**依赖项：** R5, R9
**已知约束：** 中文指代词列表需覆盖：这个/那个/它/这里/那里/这边/那边

---

### R11: FrameDiagnostics — 构图检查

**目标：** AI 自动分析关键帧的构图质量。

**涉及文件：**
- `modules/review_engine/frame_diagnostics.py` — 新建
- `tests/unit/review_engine/test_frame_diagnostics.py` — 新建

**输入：** `frame: PIL.Image`, `video_metadata: Dict (resolution, aspect_ratio)`
**输出：** `List[DiagnosticIssue] {type: str, severity: str, description: str, region: bbox, suggestion: str}`

**检查项：**
- 三分法偏移：主体是否在三分线附近
- 头顶空间：人物头顶是否留白过多/过少
- 水平线：是否明显倾斜
- 画面边缘：主体是否被裁切

**验收标准：**
- [ ] VLM prompt 专门设计：要求输出构图问题 JSON 列表
- [ ] 每个问题包含：type, severity (info/warning/error), description, suggestion
- [ ] 无问题 → 返回空列表
- [ ] VLM 不可用 → 静默跳过（不阻塞）
- [ ] UT 3 条: finds_composition_issue / no_issue_empty / degradation

**依赖项：** R1
**已知约束：** 构图判断高度主观，severity 保守设为 info/warning

---

### R12: FrameDiagnostics — 曝光/色温检查

**目标：** 检测关键帧的曝光和色温问题。

**涉及文件：**
- `modules/review_engine/frame_diagnostics.py` — 扩展
- `tests/unit/review_engine/test_frame_diagnostics.py` — 扩展

**检查项：**
- 过曝区域：高光溢出比例 > 5%
- 欠曝区域：阴影死黑比例 > 10%
- 色温偏移：整体偏蓝/偏黄

**实现方式：** 混合方案——直方图分析（纯算法，不依赖 VLM）+ VLM 确认

**验收标准：**
- [ ] 直方图分析：高光 (>240) 像素占比 → 过曝判定
- [ ] 直方图分析：阴影 (<15) 像素占比 → 欠曝判定
- [ ] 色温：HSV H 通道均值偏移 → 冷暖判定
- [ ] VLM 可用时：补充自然语言描述
- [ ] VLM 不可用时：仅使用直方图算法结果
- [ ] UT 4 条: overexposed / underexposed / color_temp / histogram_only

**依赖项：** R11
**已知约束：** 直方图阈值需要可配置（不同风格容忍度不同）

---

### R13: FrameDiagnostics — 连续性检查

**目标：** 检测相邻场景之间的视觉连续性问题。

**涉及文件：**
- `modules/review_engine/frame_diagnostics.py` — 扩展
- `tests/unit/review_engine/test_frame_diagnostics.py` — 扩展

**输入：** `frames: List[PIL.Image]` (每个场景的代表帧), `scenes: List[SceneInfo]`
**输出：** `List[ContinuityIssue] {scene_a_idx, scene_b_idx, issue_type, description}`

**检查项：**
- 色温跳变：相邻帧色温差 > 阈值
- 亮度跳变：相邻帧平均亮度差 > 30%
- 主体位置突变：VLM 分析主体位置不连贯

**验收标准：**
- [ ] 色温跳变：帧间 HSV-H 均值差 > 15 → warning
- [ ] 亮度跳变：帧间亮度均值差 > 30% → warning
- [ ] VLM 辅助：可用时分析主体位置连贯性
- [ ] 单场景视频 → 跳过连续性检查
- [ ] UT 3 条: color_jump / brightness_jump / single_scene_skip

**依赖项：** R11
**已知约束：** 需要 SceneInfo 列表（来自 v0.14.0 scene_segmenter）

---

### R14: AI 评审员 — 诊断→评论自动生成

**目标：** 将诊断结果转化为 ReviewStore 中的 AI 评论。

**涉及文件：**
- `modules/review_engine/vlm_analyzer.py` — 扩展 `generate_ai_review()`
- `tests/unit/review_engine/test_ai_reviewer.py` — 新建

**输入：** `session_id`, `diagnostics: List[DiagnosticIssue]`
**输出：** 在 ReviewStore 中创建 `ai_generated=1` 的评论

**验收标准：**
- [ ] 每个 DiagnosticIssue → 一条 AI 评论 (comment_type="ai_diagnostic")
- [ ] AI 评论的 time_start_ms/time_end_ms 对应场景时间范围
- [ ] AI 评论文本格式："[构图] 主体偏右，建议使用三分构图 — AI 诊断"
- [ ] severity=info → comment status="info", warning → "open", error → "flagged"
- [ ] 不覆盖已有 AI 评论（幂等性：同 session+同 issue type → 跳过）
- [ ] UT 4 条: creates_comment / correct_time_range / idempotent / severity_mapping

**依赖项：** R6 (migration), R11-R13 (diagnostics)
**已知约束：** 无

---

### R15: DiagnosticsPanel.vue — 诊断面板 UI

**目标：** 评审页面新增诊断面板，展示 AI 画面诊断结果。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/DiagnosticsPanel.vue` — 新建
- `apps/desktop/ui-vue/src/views/ReviewView.vue` — 扩展（集成新面板）
- `apps/desktop/ui-vue/src/stores/review.js` — 扩展（诊断状态）

**UI 设计：**
- 位于 CommentPanel 下方或作为新 Tab
- 按场景分组显示诊断
- severity 色彩编码：info=蓝, warning=黄, error=红
- 点击诊断项 → 跳转到对应时间码
- "运行诊断"按钮 → 调用 API
- loading 状态 + 进度指示

**验收标准：**
- [ ] 诊断列表渲染：type 图标 + description + severity 色彩
- [ ] 点击跳转：播放器跳到对应时间
- [ ] 运行诊断按钮 → loading → 结果
- [ ] 空诊断 → "AI 未发现画面问题" 提示
- [ ] VLM 不可用 → 按钮禁用 + 提示配置 VLM
- [ ] UT 2 条: renders_list / click_seeks

**依赖项：** R14, R16
**已知约束：** 遵循现有 Vue 组件风格（Alpine.js 混合模式）

---

### R16: VLM API — describe + diagnose 端点

**目标：** 暴露 VLM 分析和画面诊断的 HTTP 端点。

**涉及文件：**
- `modules/app_api/routes/vlm_routes.py` — 新建
- `tests/api/test_vlm_api.py` — 新建

**端点列表：**

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/review/{id}/vlm/describe` | 分析画笔区域 |
| POST | `/api/review/{id}/vlm/diagnose` | 运行全帧诊断 |
| GET | `/api/review/{id}/vlm/diagnostics` | 获取诊断结果 |
| GET | `/api/vlm/status` | VLM 可用性状态 |

**验收标准：**
- [ ] POST describe: 接收 base64 帧 + strokes JSON → 返回 RegionDescription
- [ ] POST diagnose: 触发异步诊断 → 202 + job_id
- [ ] GET diagnostics: 返回诊断结果列表
- [ ] GET status: 返回 {available: bool, provider: str, model: str}
- [ ] 统一错误格式 + 参数校验
- [ ] base64 图像大小限制 10MB
- [ ] UT 5 条: describe_success / diagnose_async / diagnostics_list / status_check / oversized_reject

**依赖项：** R5, R14
**已知约束：** describe 请求较大（含 base64 图像），设置 Content-Length 上限

---

### R17: VLM 设置页 — provider 选择 + 测试连接

**目标：** 设置页面增加 VLM 模型配置选项。

**涉及文件：**
- `apps/desktop/ui-vue/src/views/SettingsView.vue` — 扩展
- `modules/app_api/routes/system_routes.py` — 扩展 settings

**设置项：**
- VLM Provider: 本地 LLaVA / OpenAI GPT-4o / Anthropic Claude（三选一）
- API Key（OpenAI / Claude 时显示）
- 模型名（可选覆盖）
- 测试连接按钮

**验收标准：**
- [ ] Provider 下拉选择（默认"本地 LLaVA"）
- [ ] 选择 API provider 时显示 API Key 输入框
- [ ] 测试连接：发送测试图像 → 显示返回描述
- [ ] 设置持久化到 settings.json
- [ ] UT 2 条: settings_persist / test_connection

**依赖项：** R1
**已知约束：** 复用现有 settings 架构（`/api/settings` 端点）

---

### R18: 集成测试 + 端到端验证

**目标：** 验证完整链路：画笔→裁剪→VLM→描述→IntentRouter→指令。

**涉及文件：**
- `tests/integration/test_vlm_pipeline.py` — 新建
- `tests/smoke/test_vlm_smoke.py` — 新建

**验收标准：**
- [ ] 端到端: 模拟画笔 JSON → RegionExtractor → VLMAnalyzer(stub) → IntentRouter → EditInstruction
- [ ] 降级路径: VLM 不可用 → 所有功能静默降级，不影响现有评审流程
- [ ] API 集成: POST describe → 返回结构化描述
- [ ] 诊断集成: POST diagnose → AI 评论写入 → GET diagnostics 可查
- [ ] 全量回归: 现有 1330+ 测试无新增失败
- [ ] UT 6 条: e2e_pipeline / degradation_path / api_describe / api_diagnose / full_regression / backward_compat

**依赖项：** ALL
**已知约束：** 集成测试使用 StubVLMAdapter

---

## 6. 依赖关系图

```
R1 (VLMAdapter)
├── R2 (LocalLlava) ─────────┐
├── R3 (APIVision) ──────────┤
├── R11 (构图) ──┐            │
├── R12 (曝光) ──┤            │
├── R13 (连续性)─┤            │
│                └── R14 (AI评审) ── R15 (DiagnosticsPanel)
├── R17 (设置页)              │
│                             │
R4 (RegionExtractor) ────────┤
                              │
R5 (VLMAnalyzer) ◄───────────┘
├── R7 (CommentInput 预填充)
├── R9 (IntentRouter 多模态)
│   └── R10 (指代消解)
│
R6 (DB migration) ◄── R14
R8 (DrawingOverlay 事件) ◄── R7

R18 (集成测试) ◄── ALL
```

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 本地 LLaVA 内存占用大 (8GB+) | 低配设备无法运行 | 三级降级：LLaVA → API → 无 VLM |
| VLM 输出格式不稳定 | 结构化解析失败 | robust regex parsing + fallback to raw text |
| 画笔坐标系不匹配 | 裁剪区域偏移 | R4 严格测试坐标转换 |
| API 延迟高 (2-5s) | UX 卡顿 | 异步请求 + loading 状态 + debounce |
| 构图诊断过于主观 | 误报率高 | severity 保守（默认 info），用户可关闭 |

## 8. 版本验收标准

- [ ] 18 个 R 任务全部完成
- [ ] 新增测试全部通过
- [ ] 全量回归 1330+ 无新增失败
- [ ] VLM 不可用时所有现有功能不受影响
- [ ] 画笔→描述→指令端到端链路可演示
- [ ] AI 诊断可在评审页触发并展示结果
