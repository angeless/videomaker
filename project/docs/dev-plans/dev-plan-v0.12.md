# VideoEditor v0.12.0 — 开发计划

> **文档版本**: V2.0
> **日期**: 2026-03-21（V2.0修订）
> **制定者**: Angel（产品）+ Claude（方案设计）
> **基线版本**: v0.11.0（v0.11全部R任务完成后开始）
> **前置条件**: v0.11.0 审计通过，所有P0/P1/P2/P3问题已修复
> **核心主题**: 多模态语义分析（增量增强） · 向量搜索 · Prompt智能剪辑 · 订阅制商业化 · 产品体验修复

---

## 一、版本目标

### 1.1 一句话定义

**v0.12.0 = 在已有 CLIP/hybrid search 基础上增量增强多模态语义分析，在 Step 6 粗剪中集成拖拽时间线编辑，新增 Prompt 智能剪辑能力，修复产品体验断裂点，并引入订阅制开关。**

### 1.2 版本目标拆解

| 目标 | 优先级 | 来源 |
|------|--------|------|
| v0.11遗留问题审计修复 | P0 | 用户需求#1 |
| 多模态语义分析**增量增强**（在已有 CLIP+hybrid search 上扩展） | P0 | 竞品空白 + 用户需求#2 |
| 向量搜索增强（FAISS 替代 JSON 索引，片段级检索） | P0 | 痛点地图②②b |
| Step 6 粗剪集成拖拽时间线编辑 | P1 | WISHLIST W-001 + 用户需求#2 + 评测H4 |
| 片段级Prompt智能剪辑 | P1 | 核心差异化 |
| Library 与 Project 素材系统打通 | P1 | 评测H2 |
| AI 功能降级透明化 | P1 | 评测H3 |
| 产品体验修复（搜索/项目管理/Step 1预览/工作流状态等） | P1 | 评测M1-M5 |
| 订阅制商业化开关 | P2 | 用户需求#3 |
| 本地视觉推理硬件适配 | P1 | 用户需求#8 |

### 1.3 明确排除范围

- 多方言语音识别（用户确认先不做）
- 实时发布连接器（YouTube/TikTok等）——留在后续版本
- 多人协作功能
- 云端处理模式（本版本坚持本地优先）

---

## 二、v0.11 遗留问题审计与修复

### 2.1 审计策略

v0.12 启动前，必须先对 v0.11 完成验收审计：

```
Step 1: 重新运行 v0.10.0 审计报告中的 55 个问题 → 逐项确认修复状态
Step 2: 运行全量测试（pytest tests/ -v）→ 确认零回归
Step 3: 运行 E2E 测试（5 条核心用户路径）→ 确认功能闭环
Step 4: 检查 R11 Library 重构后的 API 兼容性 → 确认外部接口不变
Step 5: 输出审计报告 → 记录残留问题（如有）
```

### 2.2 预计遗留问题类型

| 类型 | 可能来源 | 修复归入 |
|------|---------|---------|
| R11 Library重构后的边界case | 13,245行拆分后可能漏洞 | R1（本版本） |
| R8 AI脚本生成的edge case | Step 3首次实现，可能有适配问题 | R1（本版本） |
| R9 外键启用后的数据迁移问题 | 已有数据可能违反外键约束 | R1（本版本） |
| 性能回归 | 重构后可能引入性能问题 | R1（本版本） |

---

## 三、多模态语义分析引擎设计（增量增强，非从零搭建）

> **重要前提**: 当前代码库已具备成熟的语义分析基础设施：
> - `modules/step1_material_analysis/indexer/semantic.py` — **CLIPEncoder** (openai/clip-vit-base-patch32, 512维)、SemanticIndex（JSON 索引、keyframe 抽取、image-text similarity）
> - `modules/library/global_media_library.py` — **25分类体系、62语义维度、16语义槽位**、混合搜索（tag 0.50 + FTS5 0.30 + vector 0.20 + custom 0.10）
> - `modules/capabilities/image_semantic.py` — 完整的图片语义分析+混合搜索（场景描述/mood/objects/keywords/质量评分）
>
> **v0.12 策略**: 在这些已有基础上**扩展**，而不是重建。核心增量点是：
> 1. JSON 向量索引 → FAISS 高性能索引（支持大规模检索）
> 2. 视频级分析 → 片段级分析（segment-level indexing）
> 3. 视觉单通道 → 视觉+语音双通道融合检索
> 4. 已有 CLIPEncoder 复用 → 新增语音 embedding 通道

### 3.1 整体架构（参考一刻相册 + 竞品分析，增量构建）

```
┌──────────────────────────────────────────────────────────────┐
│                    统一检索入口（一个搜索框）                    │
│            "海边日落 + 有人在说旅行的片段"                       │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│              Query Router（查询路由器）                        │
│    判断查询意图 → 拆分为视觉查询 + 语音查询 + 混合查询          │
└──────┬──────────────┬──────────────────┬─────────────────────┘
       │              │                  │
       ▼              ▼                  ▼
┌────────────┐ ┌─────────────┐ ┌───────────────────┐
│ 视觉语义   │ │ 语音语义    │ │ 融合排序引擎       │
│ 分析通道   │ │ 分析通道    │ │ (Score Fusion)     │
│            │ │             │ │                    │
│ • 关键帧   │ │ • Whisper   │ │ • 加权合并两通道   │
│   抽取     │ │   转录      │ │ • 去重             │
│ • CLIP/    │ │ • LLM语义   │ │ • 按相关度排序     │
│   SigLIP   │ │   摘要      │ │ • 返回TopK片段     │
│   Embedding│ │ • 语句级    │ │                    │
│ • 场景/    │ │   Embedding │ │                    │
│   物体/    │ │             │ │                    │
│   动作分类 │ │             │ │                    │
└─────┬──────┘ └──────┬──────┘ └─────────┬─────────┘
      │               │                  │
      ▼               ▼                  ▼
┌──────────────────────────────────────────────────────────────┐
│              向量数据库（本地 SQLite + FAISS）                  │
│                                                              │
│  visual_embeddings    audio_embeddings    fused_index         │
│  (CLIP 512/768d)      (sentence 384d)     (混合索引)          │
└──────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│              素材片段库（与现有 Library 模块集成）               │
│                                                              │
│  asset_id → segments[] → each segment has:                    │
│    { start_ms, end_ms, visual_embedding, audio_embedding,     │
│      scene_tags[], transcript_text, semantic_summary }        │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 三层分析方案（确保结果可靠）

按用户要求"多层方案确保结果可靠"，设计三层递进分析：

#### Layer 1: 快速索引层（导入时运行，<2秒/分钟素材）

| 分析项 | 技术 | 输出 | GPU需求 |
|--------|------|------|---------|
| 关键帧抽取 | FFmpeg scene detect + 固定间隔（每2秒1帧） | keyframes[] | ❌ CPU即可 |
| 视觉Embedding | CLIP ViT-B/32（本地推理） | 512维向量/帧 | ⚠️ 有GPU更快，CPU可用 |
| 场景粗分类 | CLIP zero-shot classification（20个预定义场景） | scene_tags[] | ⚠️ 同上 |
| 语音转录 | Whisper base/small（本地） | transcript_text | ⚠️ 有GPU更快，CPU可用 |
| 语音Embedding | sentence-transformers/all-MiniLM-L6-v2 | 384维向量/句 | ❌ CPU即可 |

**硬件要求**: 纯CPU可运行（i5+8GB RAM），有NVIDIA GPU（GTX 1060+/4GB VRAM）提速5-10x

#### Layer 2: 深度理解层（按需触发，用户搜索时细化）

| 分析项 | 技术 | 输出 | GPU需求 |
|--------|------|------|---------|
| 画面内容描述 | BLIP-2 / LLaVA（小型VLM，本地或可选API） | 每帧自然语言描述 | ✅ 推荐GPU |
| 物体检测 | YOLOv8-nano（本地） | objects[{label, bbox, confidence}] | ⚠️ GPU更快 |
| 动作识别 | CLIP + 动作提示词 zero-shot | action_tags[] | ⚠️ 同CLIP |
| 语音语义摘要 | LLM（本地小模型或API）对转录文本做段落级摘要 | semantic_summary | 可选 |

**触发条件**: 当 Layer 1 的 TopK 结果置信度 < 0.7 时自动触发 Layer 2 细化

#### Layer 3: 可选增强层（用户主动开启，或特定场景）

| 分析项 | 技术 | 输出 | 说明 |
|--------|------|------|------|
| 人脸聚类 | face_recognition库 / InsightFace | person_clusters[] | 隐私敏感，默认关闭 |
| OCR文字识别 | PaddleOCR / EasyOCR（本地） | on_screen_text[] | 识别画面中的文字 |
| 情感分析 | CLIP + 情感提示词 | emotion_tags[] | 辅助情绪维度检索 |
| 高级VLM分析 | 云端API（可选，如Qwen-VL/GPT-4o） | detailed_description | 付费增值功能 |

**开关**: 用户在设置中自主选择开启哪些Layer 3能力

### 3.3 向量搜索实现

#### 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 向量库 | **FAISS**（Facebook AI Similarity Search） | 本地运行、成熟稳定、支持GPU加速、支持IVF/HNSW索引 |
| 向量存储 | SQLite（元数据）+ FAISS索引文件（向量） | 与现有SQLite数据层一致；FAISS索引单独持久化 |
| Embedding模型 | CLIP ViT-B/32（视觉）+ all-MiniLM-L6-v2（文本） | 两者共享向量空间（CLIP天然对齐图文），MiniLM轻量高效 |
| 融合策略 | **加权Score Fusion** | visual_score × 0.5 + audio_score × 0.5（权重可调） |

#### 索引结构

```python
# 视觉索引：每个片段的关键帧embedding
visual_index = faiss.IndexFlatIP(512)     # Inner Product (cosine after L2 norm)

# 语音索引：每个片段的转录文本embedding
audio_index = faiss.IndexFlatIP(384)

# 当素材量 > 10万片段时，切换到 IVF 索引
# visual_index = faiss.IndexIVFFlat(quantizer, 512, nlist=256)
```

#### 搜索流程

```
用户输入: "海边日落有人在散步"
    │
    ├─→ CLIP text encoder → 512d query vector
    │     → FAISS visual_index.search(query, topK=50)
    │     → visual_candidates [{segment_id, score}]
    │
    ├─→ MiniLM text encoder → 384d query vector
    │     → FAISS audio_index.search(query, topK=50)
    │     → audio_candidates [{segment_id, score}]
    │
    └─→ Score Fusion
          → merge(visual_candidates, audio_candidates)
          → weighted_score = v_score × w_visual + a_score × w_audio
          → dedup by segment_id (take max score)
          → sort by weighted_score DESC
          → return top 20 results
```

### 3.4 与现有 Library 模块的集成策略

**关键原则**: 不重构 Library，在 R11 重构后的 Facade 上**扩展**。

```
modules/library/                      ← v0.11 R11 重构后的结构
├── global_media_library.py           ← Facade（新增语义搜索入口方法）
├── core/
│   ├── asset_ingestion.py            ← 修改：导入时触发 Layer 1 分析
│   ├── asset_search.py               ← 修改：新增 semantic_search() 方法
│   └── asset_analysis.py             ← 已有
├── semantic/                         ← 🆕 新增子模块（v0.12核心）
│   ├── __init__.py
│   ├── visual_analyzer.py            ← CLIP视觉embedding + 场景分类
│   ├── audio_analyzer.py             ← Whisper转录 + 语音embedding
│   ├── query_router.py               ← 查询路由（视觉/语音/融合）
│   ├── score_fusion.py               ← 多通道分数融合排序
│   ├── segment_extractor.py          ← 视频分段（场景切换检测+固定间隔）
│   └── embedding_models.py           ← 模型加载/推理管理（含GPU检测）
├── vector_store/                     ← 🆕 新增子模块
│   ├── __init__.py
│   ├── faiss_index.py                ← FAISS索引管理（创建/更新/搜索/持久化）
│   ├── embedding_store.py            ← embedding元数据存储（SQLite表）
│   └── index_builder.py              ← 批量索引构建（导入时/重建时）
├── deep_analysis/                    ← 🆕 新增子模块（Layer 2/3）
│   ├── __init__.py
│   ├── vlm_describer.py              ← VLM画面描述（可选）
│   ├── object_detector.py            ← YOLO物体检测（可选）
│   ├── face_clusterer.py             ← 人脸聚类（默认关闭）
│   └── ocr_reader.py                 ← OCR文字识别（可选）
├── maintenance/
├── tagging/
│   ├── tag_manager.py
│   └── auto_tagger.py                ← 修改：接入语义分析结果自动打标签
├── integrations/
└── db/
    ├── connection.py
    ├── migrations/                    ← 🆕 新增：向量表迁移脚本
    │   └── 001_add_semantic_tables.py
    └── seeds/
```

**Facade 扩展（非重写）**:

```python
# global_media_library.py 新增方法（不修改已有方法）

class GlobalMediaLibrary:
    # ... 所有已有方法保持不变 ...

    # 🆕 v0.12 新增
    def semantic_search(self, query: str, top_k: int = 20,
                        channels: str = "auto") -> List[SegmentResult]:
        """多模态语义搜索：按自然语言查找素材片段"""

    def analyze_asset_semantics(self, asset_id: str,
                                 layers: List[int] = [1]) -> SemanticAnalysis:
        """对指定素材执行语义分析"""

    def rebuild_semantic_index(self) -> IndexStats:
        """重建向量索引"""

    def get_segment_details(self, segment_id: str) -> SegmentDetail:
        """获取片段的语义详情"""
```

---

## 四、Step 6 粗剪集成拖拽时间线编辑

> **V2.0 修订**: 原计划设计了独立的"素材工作台"作为平行入口，经用户确认修正：
> - 拖拽编辑**属于粗剪阶段（Step 6）**，不是素材选择阶段
> - 素材选择保持**勾选模式**（Step 1），不改为拖拽
> - 删除独立的 Material Workbench 概念，改为增强 Step 6

### 4.1 设计目标

在 Step 6 粗剪阶段，将当前的"生成→预览→审批"单向流程升级为**可交互的拖拽时间线编辑器**：

1. 粗剪生成后，用户可以在时间线上**直接看到片段排列**
2. 拖拽 → 调整片段顺序
3. 裁切 → 修改单个片段的入出点
4. 删除 → 移除不想要的片段
5. Prompt → 对选中片段输入编辑指令

### 4.2 与现有产品结构的融合

**增强 Step 6，不新增独立入口**：

```
现有 Step 6 流程（v0.11）：
  "生成粗剪"按钮 → 后台算法 → rough_cut.mp4 → 预览播放 → 审批/重试

v0.12 增强后的 Step 6 流程：
  "生成粗剪"按钮 → 后台算法 → 片段计划
       ↓
  ┌──────────────────────────────────────────────────────┐
  │  Step 6 拖拽时间线编辑器（集成已有 TimelinePanel）     │
  │                                                      │
  │  ┌────────────────────────────────────────────────┐  │
  │  │ TimelineTrackClips  — 拖拽排序、裁切入出点      │  │
  │  │ TimelineTrackSubtitles — 字幕轨道              │  │
  │  │ TimelineTrackAudio — 音频轨道                   │  │
  │  │ TimelineRuler + Playhead — 时间刻度+播放头     │  │
  │  └────────────────────────────────────────────────┘  │
  │                                                      │
  │  ┌──────────┐    ┌──────────────────┐               │
  │  │ 片段列表  │    │ Prompt剪辑面板    │               │
  │  │（勾选增减）│    │（选中片段后输入） │               │
  │  └──────────┘    └──────────────────┘               │
  └──────────────────────────────────────────────────────┘
       ↓
  "确认粗剪" → 渲染 rough_cut.mp4 → 预览播放 → 审批 → Step 7
```

**关键设计决策**:
- **复用已有 TimelinePanel 组件体系**（TimelineTrackClips、TimelineRuler、TimelinePlayhead 等已存在）
- 不新增独立页面/入口，直接增强 Step6Rough.vue
- 素材选择（Step 1）保持勾选模式不变
- 粗剪生成后自动加载到时间线编辑器
- 用户调整完成后点"确认粗剪"再执行实际渲染

### 4.3 前端组件（Vue）

| 组件 | 职责 | 新增/修改 |
|------|------|----------|
| `Step6Rough.vue` | 粗剪步骤面板，集成时间线编辑器 | 🔧 修改 |
| `TimelinePanel.vue` | 时间线容器（已存在，增加拖拽交互） | 🔧 修改 |
| `TimelineTrackClips.vue` | 片段轨道（已存在，增加拖拽排序+裁切） | 🔧 修改 |
| `TimelineClipBlock.vue` | 单个片段块（已存在，增加拖拽手柄） | 🔧 修改 |
| `PromptPanel.vue` | 片段级Prompt输入面板 | 🆕 新增 |

---

## 五、片段级Prompt智能剪辑

### 5.1 功能定义

用户在时间线上选中一个片段后，可以输入自然语言指令来控制该片段的剪辑效果：

| Prompt示例 | 执行动作 |
|-----------|---------|
| "加速播放到2倍" | 调整 speed=2.0 |
| "加入柔和的背景音乐" | 从BGM库匹配 + 混音 |
| "调成暖色调" | 应用color grading preset |
| "添加淡入淡出效果" | 添加 fade_in + fade_out transition |
| "裁掉前3秒" | trim start_ms += 3000 |
| "添加字幕：这是一个美好的日落" | 在指定时间段插入字幕 |
| "画面稳定" | 应用 video stabilization |
| "静音" | audio volume = 0 |
| "慢动作播放这段" | speed = 0.5 |

### 5.2 技术实现

```
用户Prompt → LLM解析 → 结构化编辑指令 → FFmpeg/OpenCV执行 → 预览
```

#### Prompt解析器

```python
class PromptParser:
    """将用户自然语言指令解析为结构化编辑操作"""

    def parse(self, prompt: str, segment_context: dict) -> List[EditOperation]:
        """
        Input:  "加速播放到2倍，调成暖色调"
        Output: [
            EditOperation(type="speed", params={"factor": 2.0}),
            EditOperation(type="color_grade", params={"preset": "warm"})
        ]
        """
```

#### 支持的编辑操作（V1 最小集）

| 操作类型 | 参数 | 实现方式 |
|---------|------|---------|
| `speed` | factor: float | FFmpeg `-filter:v setpts` |
| `trim` | trim_start_ms, trim_end_ms | FFmpeg `-ss -to` |
| `volume` | level: float (0-2.0) | FFmpeg `-filter:a volume` |
| `fade` | fade_in_ms, fade_out_ms | FFmpeg `fade` filter |
| `color_grade` | preset: warm/cool/vintage/bw | FFmpeg `colorbalance` / LUT |
| `subtitle` | text, start_ms, end_ms | ASS字幕 + FFmpeg `subtitles` |
| `stabilize` | strength: low/medium/high | FFmpeg `vidstabdetect` + `vidstabtransform` |
| `crop` | x, y, w, h | FFmpeg `crop` filter |
| `rotate` | degrees: int | FFmpeg `transpose` |
| `mute` | — | FFmpeg `-an` |

#### LLM策略（已确认：三级混合，自动路由）

- **Level 1 关键词规则引擎**（零延迟）: 处理明确指令（"加速2倍""静音""裁掉前3秒"），关键词匹配，不依赖任何模型，保证离线可用
- **Level 2 本地小模型**（Qwen2-1.5B，~1.5GB）: 处理单步简单指令（"让画面更柔和""加个转场"），按需加载/用完可卸载，不常驻内存
- **Level 3 云端API**（复用已有AI Provider）: 处理复合/模糊/创意型指令（"调成电影感，加暖色调和慢动作，配轻柔钢琴"）
- **自动路由逻辑**: 指令含明确操作关键词→Level 1; 单步可解析→Level 2; 其余→Level 3; Level 2/3 不可用时降级到下一级

### 5.3 模块位置

```
modules/capabilities/prompt_edit/      ← 🆕 新增Capability模块
├── __init__.py
├── prompt_parser.py                   ← Prompt → EditOperation
├── edit_operations.py                 ← EditOperation定义 + FFmpeg映射
├── operation_executor.py              ← 执行编辑操作（调用FFmpeg/OpenCV）
├── preview_generator.py               ← 生成编辑预览（低分辨率快速预览）
└── templates/                         ← Prompt解析模板
    ├── speed_templates.json
    ├── color_templates.json
    └── ...
```

---

## 六、订阅制商业化开关

### 6.1 设计原则

- 本版本只做**开关基础设施**，不做完整的支付集成
- 所有功能默认可用（开发/测试期间）
- 通过 feature flag 控制哪些功能在免费/付费模式下可用
- 为后续接入支付系统预留接口

### 6.2 订阅层级设计

| 层级 | 名称 | 价格（建议） | 可用功能 |
|------|------|-------------|---------|
| Free | 免费版 | $0 | 基础剪辑（Step 1-7）、手动标签、基础搜索 |
| Pro | 专业版 | $19/月 | Layer 1语义分析、向量搜索、拖拽工作台、基础Prompt剪辑（10条/天） |
| Premium | 高级版 | $39/月 | Layer 2/3深度分析、无限Prompt剪辑、VLM画面描述、人脸聚类 |

### 6.3 技术实现

```
modules/subscription/                  ← 🆕 新增模块
├── __init__.py
├── feature_flags.py                   ← 功能开关定义
├── subscription_manager.py            ← 订阅状态管理
├── tier_config.py                     ← 层级配置（Free/Pro/Premium）
└── license_validator.py               ← 许可证验证（本地签名校验）
```

```python
# feature_flags.py
class FeatureFlags:
    SEMANTIC_SEARCH = "semantic_search"           # Pro+
    PROMPT_EDIT = "prompt_edit"                    # Pro+
    DEEP_ANALYSIS = "deep_analysis"               # Premium
    FACE_CLUSTERING = "face_clustering"            # Premium
    VLM_DESCRIPTION = "vlm_description"            # Premium
    UNLIMITED_PROMPT = "unlimited_prompt"           # Premium

    @classmethod
    def is_enabled(cls, feature: str, tier: str = "free") -> bool:
        """检查当前订阅层级是否可用该功能"""
```

### 6.4 前端集成

- 设置页面新增"订阅管理"面板
- 功能入口处增加 tier 检查 → 不可用时显示"升级提示"
- 开发模式下默认开放所有功能（`DEV_MODE=true` 跳过检查）

---

## 七、本地视觉推理硬件要求

### 7.1 最低硬件要求分析

| 配置层级 | CPU | RAM | GPU | 体验等级 |
|---------|-----|-----|-----|---------|
| **最低配置** | Intel i5 / AMD Ryzen 5 | 8GB | 无独显 | Layer 1 可用（慢速，~10秒/分钟素材） |
| **推荐配置** | Intel i7 / AMD Ryzen 7 | 16GB | NVIDIA GTX 1060 6GB | Layer 1+2 流畅（~2秒/分钟素材） |
| **高性能配置** | Intel i9 / AMD Ryzen 9 | 32GB | NVIDIA RTX 3060+ 8GB | 全部Layer，实时预览 |

### 7.2 自适应策略

```python
class HardwareDetector:
    """检测硬件并自动选择最优推理策略"""

    def detect(self) -> HardwareProfile:
        """返回: cpu_cores, ram_gb, gpu_name, vram_gb, cuda_available"""

    def recommend_config(self, profile: HardwareProfile) -> InferenceConfig:
        """
        根据硬件自动选择:
        - model_size: tiny/base/small/medium
        - device: cpu/cuda
        - batch_size: 1-32
        - precision: fp32/fp16/int8
        - layers_enabled: [1] / [1,2] / [1,2,3]
        """
```

### 7.3 模型大小预算

| 模型 | 用途 | 大小 | VRAM需求 |
|------|------|------|---------|
| CLIP ViT-B/32 | 视觉embedding | ~340MB | ~1GB |
| Whisper base | 语音转录 | ~142MB | ~1GB |
| all-MiniLM-L6-v2 | 文本embedding | ~80MB | ~0.5GB |
| YOLOv8-nano | 物体检测（可选） | ~6MB | ~0.5GB |
| BLIP-2 FlanT5-small | VLM描述（可选） | ~1.2GB | ~3GB |
| **Layer 1 合计** | — | **~562MB** | **~2.5GB** |
| **全部加载** | — | **~1.8GB** | **~6GB** |

---

## 八、R任务分解

### 执行顺序总览

```
R1（v0.11遗留修复 + Library/Project打通 + 项目清理 + 配置修复）
  → R2（语义分析基础设施 — 增量增强）
    → R3（视觉分析通道 — 复用已有CLIP）
      → R4（语音分析通道增强）
        → R5（向量搜索引擎 — JSON→FAISS升级）
          → R6（融合检索 + 搜索UI + AI降级透明化）
            → R7（Step 6 拖拽时间线编辑 — 复用已有 TimelinePanel）
              → R8（Prompt剪辑引擎）
                → R9（订阅制开关）
                  → R10（硬件自适应 + 性能优化）
                    → R11（产品体验修复批次 — 评测M1-M5/L1-L4）
                      → R12（集成测试 + 审计）
```

> **V2.0 变更**:
> - R2 标注为增量增强（复用已有 CLIPEncoder）
> - R7 从"独立工作台"改为"Step 6 拖拽时间线"
> - R6 新增 AI 降级透明化（评测H3）
> - 新增 R11（产品体验修复批次）
> - 原 R11 改为 R12

---

### R1: v0.11 遗留问题审计修复

| 属性 | 值 |
|------|-----|
| **优先级** | P0 |
| **依赖** | v0.11.0 完成 |
| **预计工作量** | Low-Med |

**任务内容**:
1. 运行 v0.11 全量审计（55项问题逐项验收）
2. 运行全量测试 + E2E测试
3. 修复发现的残留问题
4. 验证 R11 Library 重构后的 API 兼容性
5. **清理历史残留项目数据**（评测M3：`/api/projects` 返回12个 missing 状态的 audit_* 项目）
6. **修复 Library 与 Project 素材割裂问题**（评测H2：项目内 `materials.json` 与全局 `library.db` 无同步机制）
7. **修复渲染配置默认值不一致**（评测M5：默认竖屏 1080×1920 + 横屏预设 travel_story 冲突）
8. 输出审计报告到 `docs/audit/`

**验收标准**:
- [ ] v0.10 审计报告中的55个问题全部标记为"已修复"或"不适用"
- [ ] 全量测试通过率 100%（排除已知skip）
- [ ] E2E 5条路径全部通过
- [ ] Library Facade 所有公共方法签名不变
- [ ] `/api/projects` 不再返回 missing 状态的残留项目
- [ ] 项目内分析的素材自动写入全局 Library（或提供显式同步入口）
- [ ] 创建项目时默认渲染配置与美学预设一致

**涉及文件**: 取决于审计结果（预计修改<15个文件）

---

### R2: 语义分析基础设施（增量增强）

| 属性 | 值 |
|------|-----|
| **优先级** | P0 |
| **依赖** | R1 |
| **预计工作量** | Med |

> **增量策略**: 已有 `semantic.py` 中的 CLIPEncoder（512维）和 SemanticIndex **不拆不改**，
> 新增的 `modules/library/semantic/` 作为扩展层，通过 Facade 新方法调用，不替换原有逻辑。

**任务内容**:
1. 创建 `modules/library/semantic/` 子模块骨架（扩展层，不替代已有 `step1_material_analysis/indexer/semantic.py`）
2. 创建 `modules/library/vector_store/` 子模块骨架（FAISS 替代 JSON 索引用于大规模检索）
3. 实现 `HardwareDetector`（GPU检测+推理策略推荐）
4. 实现 `embedding_models.py`（模型加载管理器，**复用已有 CLIPEncoder 实例**，新增语音 embedding 模型）
5. 实现 `segment_extractor.py`（视频分段：基于已有 keyframe 抽取逻辑扩展为片段级索引）
6. 创建 SQLite 迁移脚本（`segments` / `embeddings` 表，扩展已有 library.db）
7. 添加依赖到 `requirements.txt`（faiss-cpu, sentence-transformers；CLIP 和 transformers 已在可选依赖中）
8. **迁移桥接**: 创建从已有 JSON 向量索引到 FAISS 的一次性迁移工具
9. **分析队列系统** — 后端实现异步分析队列管理器（入队/执行/断点续传/失败标记/重试/暂停），队列持久化到 SQLite（退出后下次启动自动恢复），适用所有模态（视觉/语音/embedding/深度分析）。API: `/api/analysis/queue`、`retry`、`pause`、`resume`
10. **分析队列前端侧边栏** — 新增 `AnalysisQueuePanel.vue`，独立侧边栏展示排队/进行中/已完成/失败的分析任务，支持单任务重启、全部暂停/继续，显示总进度（已分析 N/M），失败任务显示错误原因

**验收标准**:
- [ ] `HardwareDetector` 在无GPU机器上正确返回CPU配置
- [ ] `segment_extractor` 能将1分钟视频分为5-15个片段
- [ ] 模型加载管理器复用已有 CLIPEncoder，不重复加载
- [ ] SQLite迁移脚本可重复执行（幂等），且不影响已有 library.db 数据
- [ ] 已有的 `search_assets()` / `search_images()` 功能无回归
- [ ] 导入素材后自动入队分析，不阻塞用户操作
- [ ] 退出软件再启动后，未完成的分析队列自动恢复继续
- [ ] 单个素材分析失败时队列继续执行，失败项可手动重试
- [ ] 分析队列侧边栏正确显示任务状态和进度
- [ ] 全量旧测试无回归

**新增文件**:
- `modules/library/semantic/__init__.py`
- `modules/library/semantic/embedding_models.py`
- `modules/library/semantic/segment_extractor.py`
- `modules/library/semantic/analysis_queue.py`
- `modules/library/vector_store/__init__.py`
- `modules/library/vector_store/faiss_index.py`
- `modules/library/vector_store/embedding_store.py`
- `modules/library/db/migrations/001_add_semantic_tables.py`
- `modules/library/db/migrations/002_add_analysis_queue_table.py`
- `modules/app_api/routes/analysis_queue.py`
- `apps/desktop/ui-vue/src/components/library/AnalysisQueuePanel.vue`
- `tools/migrate_json_to_faiss.py`
- `tests/test_r2_semantic_infra.py`
- `tests/test_r2_analysis_queue.py`

---

### R3: 视觉分析通道

| 属性 | 值 |
|------|-----|
| **优先级** | P0 |
| **依赖** | R2 |
| **预计工作量** | Med-High（复用已有 CLIPEncoder，减少从零开发量） |

> **增量策略**: 复用 `semantic.py` 中已有的 CLIPEncoder (ViT-B/32, 512d)，
> `visual_analyzer.py` 作为调用层封装，不重复实现 CLIP 加载和推理逻辑。
> 已有 25 分类体系和 62 语义维度作为场景分类的基线。

**任务内容**:
1. 实现 `visual_analyzer.py`（封装已有 CLIPEncoder，新增场景零样本分类）
2. 将视觉分析集成到素材导入流程（`asset_ingestion.py` 扩展）
3. 实现关键帧→embedding的批量处理pipeline
4. 实现 FAISS 视觉索引的构建和搜索
5. 添加20个预定义场景标签（室内/室外/城市/自然/海边/山/美食/人物/动物/夜景/日落/雪景/水/建筑/交通/运动/舞蹈/表情/文字/屏幕）
6. 单元测试：视觉搜索准确率（人工标注的测试集）

**验收标准**:
- [ ] 导入一段5分钟视频后，自动生成关键帧+embedding
- [ ] `semantic_search("海边日落", channels="visual")` 返回相关片段
- [ ] 场景分类在测试集上 top-3 准确率 > 80%
- [ ] 纯CPU模式下可运行（速度可慢）
- [ ] GPU模式下处理速度 < 2秒/分钟素材

---

### R4: 语音分析通道增强

| 属性 | 值 |
|------|-----|
| **优先级** | P0 |
| **依赖** | R2 |
| **预计工作量** | Med |

**任务内容**:
1. 增强现有 Whisper 转录（如已有则复用，如无则新增）
2. 实现 `audio_analyzer.py`（转录文本→句子级embedding）
3. 将语音分析集成到素材导入流程
4. 实现 FAISS 语音索引的构建和搜索
5. 实现转录文本的段落级语义摘要（LLM调用，可选）

**验收标准**:
- [ ] 导入视频后自动转录并生成语音embedding
- [ ] `semantic_search("讨论旅行计划", channels="audio")` 返回含相关语音内容的片段
- [ ] 中文和英文转录均可工作
- [ ] 转录准确率（中文普通话）> 90%

**注意**: R3和R4可并行开发（共享R2基础设施）

---

### R5: 向量搜索引擎

| 属性 | 值 |
|------|-----|
| **优先级** | P0 |
| **依赖** | R3 + R4 |
| **预计工作量** | Med |

**任务内容**:
1. 实现 `query_router.py`（判断查询意图→分发到视觉/语音/混合通道）
2. 实现 `score_fusion.py`（加权分数融合+去重+排序）
3. 实现 `faiss_index.py` 的持久化（索引保存/加载/增量更新）
4. 实现索引重建功能（全量重建）
5. 性能优化：大素材库（>1000个片段）下搜索延迟 <500ms

**验收标准**:
- [ ] 混合搜索："海边有人讲旅行" → 同时匹配视觉（海边）+语音（讲旅行）
- [ ] 索引持久化后重启应用不丢失
- [ ] 增量更新：新导入素材自动加入索引
- [ ] 1000片段规模下搜索延迟 <500ms
- [ ] 搜索结果按相关度正确排序

---

### R6: 融合检索 + 搜索UI + AI降级透明化

| 属性 | 值 |
|------|-----|
| **优先级** | P1 |
| **依赖** | R5 |
| **预计工作量** | Med-High |

**任务内容**:
1. 实现 `/api/library/semantic_search` API端点
2. 在 Library Facade 新增 `semantic_search()` 公共方法
3. 前端：实现 `SearchBar` 组件（统一搜索框）
4. 前端：实现 `SegmentGrid` 组件（搜索结果展示：缩略图+标签+分数+时长）
5. 前端：搜索结果支持预览播放（点击缩略图播放片段）
6. 前端：空状态引导（"导入素材后可以用自然语言搜索"）
7. **AI 降级透明化**（评测H3）：
   - 在所有 AI 依赖步骤（Step 2脑暴、Step 3脚本、TopicCopy 等）的结果中加入降级标记
   - 工作流面板顶部常驻 AI 状态指示器（已连接/降级模式/未配置）
   - 激活 `DegradationBanner.vue`（已存在但未在关键流程中显示）
   - 降级模式下的结果明确标注"模板生成"而非让用户误以为是AI创作

**验收标准**:
- [ ] 用户在搜索框输入自然语言 → 看到匹配的片段列表
- [ ] 每个结果显示：缩略图、语义标签、匹配分数、时长
- [ ] 点击结果可预览播放该片段
- [ ] 搜索响应时间 <1秒（用户感知）
- [ ] 无搜索结果时显示友好提示
- [ ] 未配置 AI Key 时，工作流顶部显示降级提示
- [ ] Step 2/3 在降级模式下的输出明确标注"模板生成"

---

### R7: Step 6 拖拽时间线编辑

| 属性 | 值 |
|------|-----|
| **优先级** | P1 |
| **依赖** | R6 |
| **预计工作量** | Med-High |

> **V2.0 修订**: 不再创建独立的 Material Workbench。
> 拖拽时间线集成到 Step 6 粗剪阶段，复用已有 TimelinePanel 组件体系。
> 素材选择（Step 1）保持勾选模式不变。

**任务内容**:
1. 增强 `Step6Rough.vue` — 粗剪生成后自动加载片段到 TimelinePanel
2. 增强 `TimelineTrackClips.vue` — 支持拖拽排序（drag-and-drop reorder）
3. 增强 `TimelineClipBlock.vue` — 支持拖拽裁切入出点（左右边缘拖拽）
4. 新增"删除片段"操作（从时间线移除不需要的片段）
5. 新增"确认粗剪"按钮 — 将用户调整后的时间线排列提交渲染
6. 后端：新增 `/api/step6/timeline_edit` API — 接收用户调整后的片段计划
7. 后端：修改 `rough_cut.py` — 支持接收外部片段计划（而非仅算法生成）

**验收标准**:
- [ ] 粗剪生成后，片段在 TimelinePanel 中可视化展示
- [ ] 片段可拖拽排序（交换位置）
- [ ] 片段入出点可拖拽调整
- [ ] 不需要的片段可删除
- [ ] 用户调整后点"确认粗剪"→ 按新排列渲染 rough_cut.mp4
- [ ] 不修改 Step 1-5 和 Step 7 的任何逻辑

---

### R8: Prompt剪辑引擎

| 属性 | 值 |
|------|-----|
| **优先级** | P1 |
| **依赖** | R7 |
| **预计工作量** | High |

**任务内容**:
1. 创建 `capabilities/prompt_edit/` 模块
2. 实现 `prompt_parser.py`（Prompt→结构化EditOperation）
3. 实现 10 种基础编辑操作的 FFmpeg 映射
4. 实现 `operation_executor.py`（执行编辑操作）
5. 实现 `preview_generator.py`（快速低分辨率预览）
6. 前端：`PromptPanel` 组件（选中片段→输入Prompt→预览效果）
7. 兜底规则引擎（关键词匹配，不依赖LLM）

**验收标准**:
- [ ] 输入"加速到2倍" → 正确解析并执行
- [ ] 输入"调成暖色调" → 正确应用color grading
- [ ] 输入"裁掉前3秒" → 正确裁切
- [ ] 预览生成 <3秒
- [ ] 离线模式（无LLM）下关键词匹配可工作
- [ ] 复合指令（"加速2倍，加淡入效果"）能正确拆分和执行

---

### R9: 订阅制开关

| 属性 | 值 |
|------|-----|
| **优先级** | P2 |
| **依赖** | R6（需要知道哪些功能需要gate） |
| **预计工作量** | Low-Med |

**任务内容**:
1. 创建 `modules/subscription/` 模块
2. 实现 `feature_flags.py`（功能开关定义）
3. 实现 `subscription_manager.py`（订阅状态管理，本地存储）
4. 实现 `tier_config.py`（Free/Pro/Premium配置）
5. 在关键功能入口处添加 tier 检查
6. 前端：设置页面"订阅管理"面板
7. 开发模式开关（`DEV_MODE=true` 跳过所有限制）

**验收标准**:
- [ ] `DEV_MODE=true` 时所有功能无限制
- [ ] `tier=free` 时语义搜索和Prompt剪辑显示升级提示
- [ ] `tier=pro` 时基础语义搜索和Prompt可用
- [ ] 功能开关可通过配置文件修改（不需重编译）
- [ ] 设置页面正确显示当前订阅状态

---

### R10: 硬件自适应 + 性能优化

| 属性 | 值 |
|------|-----|
| **优先级** | P1 |
| **依赖** | R3 + R4（需要知道实际性能瓶颈） |
| **预计工作量** | Med |

**任务内容**:
1. 完善 `HardwareDetector`（实际设备测试+校准）
2. 实现模型精度自适应（fp32→fp16→int8，按VRAM自动选择）
3. 实现批处理优化（多帧并行embedding）
4. 实现索引分片（大素材库的分片加载）
5. 添加性能仪表盘（显示分析进度、GPU/CPU使用率、预估剩余时间）
6. 首次运行时自动性能测试（确定最优配置）
7. **模型按需下载与进度提示** — 首次触发语义分析时自动下载所需模型（CLIP ~340MB、Whisper ~142MB、MiniLM ~80MB），前端显示下载进度条+预估剩余时间+当前下载的模型名称，已下载模型缓存在本地不重复下载，下载失败可重试

**验收标准**:
- [ ] 无GPU机器可完成Layer 1分析（速度<15秒/分钟）
- [ ] GTX 1060可完成Layer 1+2分析（速度<3秒/分钟）
- [ ] RTX 3060可完成全部Layer（速度<1秒/分钟）
- [ ] 性能仪表盘正确显示进度
- [ ] 首次运行性能测试<30秒完成
- [ ] 首次触发语义分析时自动下载模型，显示下载进度条
- [ ] 模型下载失败可重试，不阻塞其他功能使用

---

### R11: 产品体验修复批次（评测发现）

| 属性 | 值 |
|------|-----|
| **优先级** | P1 |
| **依赖** | R10 |
| **预计工作量** | Med |

> **来源**: 2026-03-21 产品体验评测报告中发现的中低优先级问题。
> 高优先级问题（H2/H3/H4）已分别纳入 R1、R6、R7。

**任务内容**:

**中优先级 (M):**
1. **M1: Step 1 素材预览与筛选** — Step1Materials.vue 当前只有"分析素材"按钮，无素材列表/预览/筛选
   - 增加素材网格视图（缩略图+时长+质量评分）
   - 增加按时长/质量/场景类型筛选排序
   - 保持勾选模式（不改为拖拽）
2. **M2: 本地搜索数据管道补全** — keyword/FTS5 搜索需要素材入库到 Library 才能工作
   - 确保本地分析的标签/关键词写入 FTS5 索引
   - 不依赖外部 API 的情况下 keyword 搜索可命中本地分析结果
3. **M4: 工作流步骤状态可视化** — 步骤间缺乏上下文传递提示
   - WorkflowStepper 实时显示每步状态（进行中/等待审批/已完成）
   - 后台运行的 Job 在对应步骤上显示进度指示器
   - 步骤审批后自动滚动到下一步

**低优先级 (L):**
4. **L1: 前端国际化统一** — 部分文案硬编码中文，部分通过 labels.js
   - 将所有硬编码中文迁移到 `i18n/labels.js`
5. **L2: 暗色主题对比度** — `.text-muted` 文案对比度不足
   - 调整 CSS 变量，确保 WCAG AA 标准
6. **L3: Canvas 编排器入口优化** — 功能完整但入口不明显
   - 在导航中增加 Canvas 入口的可发现性
7. **L4: 社交导出连接器占位** — 14 平台规格齐全但只有 YouTube 有 OAuth
   - 为未连接的平台添加"手动复制"引导和"即将支持"标记

**验收标准**:
- [ ] Step 1 显示素材缩略图列表，支持筛选排序
- [ ] 未配置 API Key 时，keyword 搜索仍能命中本地分析的标签
- [ ] WorkflowStepper 每步显示实时状态，后台 Job 有进度指示
- [ ] 全部硬编码中文迁移到 labels.js
- [ ] `.text-muted` 对比度 ≥ 4.5:1（WCAG AA）

---

### R12: 集成测试 + 审计

| 属性 | 值 |
|------|-----|
| **优先级** | P0 |
| **依赖** | R1-R11全部完成 |
| **预计工作量** | Med |

**任务内容**:
1. 端到端测试：完整用户流程（导入→分析→搜索→Step 6拖拽编辑→Prompt→渲染）
2. 回归测试：全量旧测试确认无破坏
3. 性能测试：不同硬件配置下的基准测试
4. 安全审计：新增API端点的权限检查
5. 产品体验验证：以零基础用户视角走通全流程，检查降级提示、步骤引导、搜索效果
6. 生成审计报告
7. 生成测试报告
8. 更新 CHANGELOG、VERSION、TODO_NEXT

**验收标准**:
- [ ] 完整用户流程可走通（含 Step 6 拖拽编辑）
- [ ] 全量旧测试通过（零回归）
- [ ] 新增功能的单元测试覆盖率 >80%
- [ ] 审计报告无P0/P1问题
- [ ] 降级模式下全流程可走通（无 AI Key）
- [ ] CHANGELOG、VERSION已更新

---

## 九、文件变更总览

### 新增模块

| 路径 | 职责 |
|------|------|
| `modules/library/semantic/` | 多模态语义分析扩展层（视觉+语音+融合，增量增强已有能力） |
| `modules/library/vector_store/` | FAISS 向量存储（替代 JSON 索引用于大规模检索） |
| `modules/library/deep_analysis/` | 深度分析（VLM/YOLO/OCR/人脸，可选） |
| `modules/capabilities/prompt_edit/` | Prompt智能剪辑引擎 |
| `modules/subscription/` | 订阅制开关 |
| `tools/migrate_json_to_faiss.py` | JSON 向量索引到 FAISS 的一次性迁移工具 |

### 修改文件（最小改动）

| 路径 | 改动 |
|------|------|
| `modules/library/global_media_library.py` | Facade新增4个方法（不改已有方法） |
| `modules/library/core/asset_ingestion.py` | 导入流程新增语义分析触发 + 项目素材自动同步到Library |
| `modules/library/core/asset_search.py` | 新增 semantic_search 入口 |
| `modules/library/tagging/auto_tagger.py` | 接入语义分析结果 |
| `modules/step6_rough_cut/rough_cut.py` | 支持接收外部片段计划（用户拖拽调整后的） |
| `modules/app_api/routes/` | 新增API端点（semantic_search、step6_timeline_edit 等） |
| `apps/desktop/ui-vue/src/components/workflow/Step1Materials.vue` | 增加素材网格预览、筛选排序（R11-M1） |
| `apps/desktop/ui-vue/src/components/workflow/Step6Rough.vue` | 集成 TimelinePanel 拖拽编辑器（R7） |
| `apps/desktop/ui-vue/src/components/timeline/TimelinePanel.vue` | 增加拖拽排序和裁切交互（R7） |
| `apps/desktop/ui-vue/src/components/timeline/TimelineTrackClips.vue` | 增加 drag-and-drop reorder（R7） |
| `apps/desktop/ui-vue/src/components/timeline/TimelineClipBlock.vue` | 增加拖拽裁切手柄（R7） |
| `apps/desktop/ui-vue/src/components/common/DegradationBanner.vue` | 在关键工作流步骤中激活（R6-H3） |
| `apps/desktop/ui-vue/src/components/workflow/WorkflowStepper.vue` | 实时状态显示 + Job 进度指示（R11-M4） |
| `apps/desktop/ui-vue/src/i18n/labels.js` | 迁移所有硬编码中文（R11-L1） |
| `requirements.txt` | 新增依赖（faiss-cpu, sentence-transformers） |

### 新增前端组件

| 组件 | 职责 |
|------|------|
| `PromptPanel.vue` | 片段级Prompt输入面板（选中片段→输入指令→预览） |
| `SegmentGrid.vue` | 语义搜索结果展示（缩略图+标签+分数+时长） |

### 不修改的文件

- Step 1-5、Step 7 的核心业务逻辑（**零改动**，Step 6 仅扩展不重写）
- 已有 `step1_material_analysis/indexer/semantic.py`（CLIPEncoder 原样保留，通过扩展层复用）
- 已有 Capability 模块（12个，零改动）
- workflow_engine（零改动）
- contracts（零改动）
- 已有测试文件（零改动）

---

## 十、新增依赖

| 包名 | 版本 | 用途 | 大小 |
|------|------|------|------|
| `faiss-cpu` | ≥1.7.4 | 向量搜索 | ~30MB |
| `faiss-gpu` | ≥1.7.4 | 向量搜索GPU加速（可选） | ~100MB |
| `open-clip-torch` | ≥2.24.0 | CLIP视觉embedding | ~340MB（模型） |
| `sentence-transformers` | ≥2.3.0 | 文本embedding | ~80MB（模型） |
| `openai-whisper` | ≥20231117 | 语音转录（如尚未有） | ~142MB（base模型） |
| `ultralytics` | ≥8.1.0 | YOLOv8物体检测（可选） | ~6MB（nano模型） |

**总新增磁盘占用**: ~600MB（Layer 1必选）~ 2GB（全部模型）

---

## 十一、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| CLIP本地推理在无GPU机器上太慢 | 高 | 三层策略：CPU可用但标记为"慢速模式"；建议用户使用GPU；支持int8量化 |
| FAISS索引在大素材库下内存占用高 | 中 | IVF索引+分片加载；监控内存，超限提示用户 |
| Prompt解析准确率不够 | 中 | 三级兜底：LLM→小模型→关键词规则引擎 |
| 视觉语义搜索准确率不满足期望 | 高 | 多层分析确保可靠；用户可手动纠错/调整标签；置信度显示让用户知情 |
| 新增依赖导致安装复杂 | 中 | 可选依赖机制（核心依赖 vs 可选增强）；安装脚本自动检测 |
| 与v0.11 Library重构的兼容 | 低 | R1审计先验证；Facade扩展不改已有方法 |

---

## 十二、待确认问题（V2.0 更新）

1. **Prompt剪辑的LLM偏好** — **已确认：三级混合策略**
   - Level 1: 关键词规则引擎（零延迟，处理"加速2倍""静音""裁掉前3秒"等明确指令）
   - Level 2: 本地小模型（Qwen2-1.5B，~1.5GB，按需加载/用完可卸载，处理单步简单指令）
   - Level 3: 云端API（复用已有AI Provider，处理复合/模糊/创意型指令）
   - 自动判断：指令包含明确关键词→Level 1；单步简单指令→Level 2；其余→Level 3
   - 本地模型不常驻内存，不会让软件变重

2. **搜索结果排序** — **已确认：相关度为默认，支持多维排序**
   - 默认：相关度（semantic score）
   - 可选：素材评分（quality_score）、文件大小、导入时间
   - 前端搜索结果区域增加排序下拉选择

3. **导入时分析** — **已确认：导入时全量分析 + 异步队列 + 断点续传**
   - 导入后立即启动全量分析（所有模态：CLIP/Whisper/embedding 等）
   - 分析任务进入异步队列，不阻塞用户操作，分析完一个即可搜到一个
   - 队列支持断点续传：用户退出软件后，下次启动自动接上之前未完成的队列继续分析
   - 队列支持错误处理：个别视频分析失败/出错时在队列中标注，支持手动重启/暂停
   - 前端新增**分析队列侧边栏**：独立列表展示全部排队/进行中/已完成/失败的分析任务
   - 以上逻辑适用于所有模态的分析（视觉/语音/embedding/深度分析）

4. **深度分析层** — **已确认：v0.12 包含 Layer 2**
   - Layer 2（VLM 画面描述 + YOLO 物体检测 + 动作识别 + 语音语义摘要）在 v0.12 的 R3/R4 中实现
   - Layer 3（人脸聚类/OCR/高级VLM）留 v0.13

5. **模型下载** — **已确认：首次调用时按需下载**
   - 安装时不包含模型文件，保持安装包轻量
   - 用户首次触发语义分析功能时自动下载对应模型
   - 下载过程显示进度条和预估时间
   - 已下载的模型缓存在本地，不重复下载

---

## 附录A：用户痛点地图→v0.12映射

| 痛点 | 等级 | v0.12对应任务 |
|------|------|-------------|
| ① 手动剪切静音/口误耗时巨大 | 🔴极高频 | v0.11已有基础（R8 AI脚本）；v0.12 Prompt剪辑进一步增强 |
| ② 找不到"好的片段"——缺乏语义检索 | 🔴极高频 | **R3-R6 多模态语义搜索（核心解决方案）** |
| ②b 纯画面素材无法被检索 | 🔴极高频 | **R3 视觉分析通道（CLIP视觉embedding）** |
| ③ AI工具性能差——长视频卡顿崩溃 | 🔴极高频 | **R10 硬件自适应+性能优化** |
| ④ 所有AI工具都是云端 | 🔴极高频 | **本地优先架构（CLIP/Whisper/FAISS全部本地运行）** |
| ⑤ 文本编辑只能裁切不能智能变换 | 🟠高频 | **R8 Prompt剪辑（10种编辑操作）** |
| ⑤b 想按主题组织素材 | 🟠高频 | **R3+R4 语义标签自动打标 + R6 主题搜索** |

### V2.0 新增：产品体验评测发现 → v0.12 映射

| 评测问题 | 等级 | v0.12 对应任务 |
|---------|------|-------------|
| H2: Library 与 Project 素材系统割裂 | 高 | **R1（审计修复 — 素材同步机制）** |
| H3: AI 功能静默降级无提示 | 高 | **R6（AI降级透明化 — DegradationBanner激活）** |
| H4: Step 6 粗剪缺少可视化编辑 | 高 | **R7（Step 6拖拽时间线编辑）** |
| M1: Step 1 素材缺乏预览和筛选 | 中 | **R11（产品体验修复 — Step 1素材网格）** |
| M2: 搜索有架构但缺实际效果 | 中 | **R11（本地搜索数据管道补全）** |
| M3: 项目管理存在历史残留数据 | 中 | **R1（审计修复 — 项目清理）** |
| M4: 工作流步骤间缺乏状态提示 | 中 | **R11（WorkflowStepper实时状态）** |
| M5: 渲染配置默认值冲突 | 中 | **R1（审计修复 — 配置一致性）** |
| L1: 前端国际化不完整 | 低 | **R11（labels.js迁移）** |
| L2: 暗色主题对比度不足 | 低 | **R11（CSS变量调整）** |
| L3: Canvas编排器入口不明显 | 低 | **R11（导航优化）** |
| L4: 社交导出缺乏实际连接 | 低 | **R11（占位引导）** |

> 注: H1（Onboarding引导）经用户确认本版本暂不做。

---

## 附录B：竞品差异化对照

| 维度 | Descript | OpusClip | Premiere Pro | **VideoEditor v0.12** |
|------|---------|---------|-------------|----------------------|
| 语音语义 | ✅✅ 转录+文本编辑 | ✅ 高光检测 | ✅ 转录搜索 | ✅✅ 转录+embedding+语义搜索 |
| 视觉语义 | ❌ | ✅✅ ClipAnything | ✅ Media Intelligence | ✅✅ CLIP+场景分类+VLM |
| 融合检索 | ❌ | ✅ | ❌ | ✅✅ 语音+视觉加权融合 |
| Prompt剪辑 | ⚠️ | ❌ | ❌ | ✅✅ 10种操作 |
| 拖拽时间线 | ✅ | ⚠️ | ✅✅ | ✅ Step 6 集成时间线 |
| 本地运行 | ✅ | ❌ | ✅ | ✅ 完全本地 |
| 价格 | $16-65/月 | $15-29/月 | $23/月 | $0-39/月 |

---

| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-03-21 | 初版基于竞品调研V2.0加用户需求确认 |
| V2.0 | 2026-03-21 | 三项核心修订加评测问题。语义分析改增量增强；工作台删除拖拽移Step6；勾选保留。新增R11体验修复R12集成测试。R1扩展H2M3M5。R6扩展H3 |

---

*文档结束*
