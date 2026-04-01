# VideoEditor 版本开发计划（v0.14.0）

**文档版本：** V1.0
**日期：** 2026-03-31
**基线 Commit：** `5a48ef9` (merge: integrate origin/claude/recursing-wu into main)
**基线 VERSION：** 0.13.1

---

## 1. 版本目标

智能粗剪（三条路径：口播/情景/混合）+ 评审数据层（SQLite + artifact store + API），为 v0.15.0 评审 UI 打基础。

## 2. 版本范围

### 包含的需求

- 视频类型自动检测（VAD 分类）
- 口播路径：Whisper 词级转录 + 说话人分离 + AI 预标记 + bad take 检测 + 文案编辑器 UI
- 情景路径：场景分割 + VLM 分析 + 镜头选择器 UI
- 混合路径：VAD 分离 + 口播/B-roll 合并
- 粗剪渲染引擎（FFmpeg concat）
- 评审数据层（review_store + artifact_store + SQLite schema）
- 粗剪 + 评审 API 端点

### 不包含的需求（Future）

| 需求 | 推迟到 |
|------|--------|
| 评审 UI（播放器/评论/时间轴） | v0.15.0 |
| 画笔标注 / 缩略图 / 波形 | v0.15.0 |
| AI 重编辑引擎 | v0.16.0 |
| 音频增强 / TTS / BGM / 转场 / reframe | v0.16.0 |

---

## 3. 任务列表

| 任务ID | 任务名称 | 优先级 | 状态 |
|--------|---------|--------|------|
| R1 | review_engine 模块脚手架 | P0 | ✅ Complete |
| R2 | 视频类型检测 (VAD) | P0 | ✅ Complete |
| R3 | Whisper 词级转录集成 | P0 | ✅ Complete |
| R4 | 说话人分离 (diarization) | P1 | ✅ Complete |
| R5 | 语气词 + 静音检测 (规则标记) | P0 | ✅ Complete |
| R6 | 废话句检测 (LLM 标记) | P1 | ✅ Complete |
| R7 | Bad take 检测 — 重复片段 | P0 | ✅ Complete |
| R8 | Bad take 检测 — false starts | P1 | ✅ Complete |
| R9 | TranscriptEditor.vue — 段落展示 + 说话人标签 | P0 | ✅ Complete |
| R10 | TranscriptEditor.vue — 标记展示 (颜色删除线) | P0 | ✅ Complete |
| R11 | TranscriptEditor.vue — 点击跳转 + 播放跟随滚动 | P0 | ✅ Complete |
| R12 | TranscriptEditor.vue — 编辑操作 (删除/恢复/拖拽排序) | P0 | ✅ Complete |
| R13 | TranscriptEditor.vue — Hook 标记 + 统计栏 + 全部接受 | P0 | ✅ Complete |
| R14 | 场景分割 (FFmpeg scene detection) | P1 | ✅ Complete |
| R15 | VLM 镜头分析 (可选) | P2 | Deferred (v0.15.0) |
| R16 | SceneSelector.vue — 网格展示 + 筛选/排序 | P1 | ✅ Complete |
| R17 | 混合路径逻辑 (VAD 分离 + 合并) | P1 | ✅ Complete |
| R18 | 粗剪渲染引擎 (FFmpeg concat) | P0 | ✅ Complete |
| R19 | roughcut.js Store + RoughCutView.vue 页面 | P0 | ✅ Complete |
| R20 | 粗剪 API — init + detect-type + stats | P0 | ✅ Complete |
| R21 | 粗剪 API — transcript + fillers + batch | P0 | ✅ Complete |
| R22 | 粗剪 API — scenes + select + generate | P1 | ✅ Complete |
| R23 | review_sessions + review_comments 表 CRUD | P0 | ✅ Complete |
| R24 | review_versions 表 CRUD | P0 | ✅ Complete |
| R25 | review_artifacts 表 + 文件管理 | P0 | ✅ Complete |
| R26 | 评审 API — init + state + comments CRUD | P0 | ✅ Complete |
| R27 | 评审 API — versions + diff + rollback | P0 | ✅ Complete |
| R28 | 评审 API — thumbnails + waveform (生成 stub) | P1 | ✅ Complete |
| R29 | 集成测试 + 冒烟测试 | P0 | ✅ Complete |

---

## 4. 各任务详细定义

### R1: review_engine 模块脚手架

**目标：** 创建 review_engine 模块目录结构、公共 API 入口、异常体系、数据合约。

**涉及文件：**
- `modules/review_engine/__init__.py` — 公共 API 入口
- `modules/review_engine/exceptions.py` — 异常体系 (继承 VideoEditorError)
- `modules/review_engine/contracts.py` — VideoType enum, DetectionResult, TranscriptDoc, Paragraph, Word 等合约
- `modules/adapters/pexels_adapter.py` — Pexels adapter 骨架
- `modules/adapters/tts_adapter.py` — TTS adapter 骨架

**输入：** 无
**输出：** 可 import 的模块骨架

**验收标准：**
- [ ] `from modules.review_engine import ...` 不报错
- [ ] `from modules.review_engine.exceptions import ReviewEngineError` 继承自 VideoEditorError
- [ ] contracts.py 定义了 VideoType, DetectionResult, TranscriptDoc, Paragraph, Word
- [ ] adapter 骨架可 import
- [ ] `python3 -m py_compile` 全部通过

**依赖项：** 无
**已知约束：** 无

---

### R2: 视频类型检测 (VAD)

**目标：** 对输入视频进行 Voice Activity Detection，返回口播/情景/混合分类。

**涉及文件：**
- `modules/review_engine/video_detector.py` — 核心逻辑
- `tests/unit/review_engine/test_video_detector.py` — UT

**输入：** `video_path: str`, `config: Optional[Dict]`
**输出：** `DetectionResult {video_type, speech_ratio, duration_s, has_audio, method}`

**验收标准：**
- [ ] 口播视频 → `video_type="speech"`, `speech_ratio > 0.6`
- [ ] 无人声视频 → `video_type="scenic"`, `speech_ratio < 0.15`
- [ ] 混合视频 → `video_type="mixed"`, `0.15 ≤ ratio ≤ 0.6`
- [ ] 无音轨 → `video_type="scenic"`, `has_audio=false`
- [ ] 不存在的路径 → 抛出 VideoDetectionError
- [ ] 处理 < 5s
- [ ] UT 3 条: speech / scenic / invalid_path

**依赖项：** R1, FFmpeg, webrtcvad 或 silero-vad (try/import)
**已知约束：** webrtcvad 需 16-bit PCM; silero-vad 需 torch

---

### R3: Whisper 词级转录集成

**目标：** 复用 step1 的 transcribe.py，返回词级时间戳的 TranscriptDoc。

**涉及文件：**
- `modules/review_engine/transcript_editor.py` — TranscriptDoc 构建逻辑
- `tests/unit/review_engine/test_transcript_editor.py` — UT

**输入：** `video_path: str`, `language: Optional[str]`
**输出：** `TranscriptDoc {paragraphs[], speakers[], language, total_duration_s, word_count}`

**验收标准：**
- [ ] 输入视频 → 返回带词级时间戳的 TranscriptDoc
- [ ] 每个 word 有 start_s/end_s/confidence
- [ ] 中文转录准确率 > 90%
- [ ] UT 2 条: valid_doc / empty_audio

**依赖项：** R1, faster-whisper 或 openai-whisper (复用 transcribe.py)
**已知约束：** 词级时间戳精度 ±0.1s

---

### R4: 说话人分离

**目标：** 对多人对话视频区分不同说话人。

**涉及文件：**
- `modules/review_engine/transcript_editor.py` — 新增 diarization 逻辑
- `tests/unit/review_engine/test_transcript_editor.py` — 新增 UT

**输入：** `audio_path: str`, `transcript_doc: TranscriptDoc`
**输出：** 更新后的 TranscriptDoc（每个 paragraph 标注 speaker）

**验收标准：**
- [ ] 两人对话 → speaker_0 / speaker_1 正确区分
- [ ] 无 pyannote-audio → 降级为单说话人
- [ ] UT 2 条: multi_speaker / fallback_single

**依赖项：** R3, pyannote-audio (可选, try/import)
**已知约束：** pyannote 需 GPU，无 GPU 降级

---

### R5: 语气词 + 静音检测

**目标：** 规则标记常见语气词，FFmpeg 检测长静音段。

**涉及文件：**
- `modules/review_engine/transcript_editor.py` — 新增标记方法
- `tests/unit/review_engine/test_transcript_editor.py` — 新增 UT

**输入：** `transcript_doc: TranscriptDoc`, `audio_path: str`
**输出：** `{filler_words: [{paragraph_id, word_index, text}], dead_air: [{start_s, end_s, duration_s}]}`

**验收标准：**
- [ ] 标记: 呃/嗯/就是/对/然后/所以说/反正/那个/这个
- [ ] 静音 > 1.5s → dead_air 列表
- [ ] 不切句中连接词（保留自然语音，参考 1870_viral 经验）
- [ ] UT 2 条: filler_words / dead_air

**依赖项：** R3, FFmpeg (silencedetect)
**已知约束：** 无

---

### R6: 废话句检测 (LLM)

**目标：** 使用 LLM 判断整句是否为无实质内容的废话。

**涉及文件：**
- `modules/review_engine/transcript_editor.py` — 新增废话检测
- `tests/unit/review_engine/test_transcript_editor.py` — 新增 UT

**输入：** `paragraphs: List[Paragraph]`
**输出：** `{filler_sentences: [{paragraph_id, reason}]}`

**验收标准：**
- [ ] "对对对"、"嗯嗯" → 标记为废话
- [ ] 有实质内容的肯定句 → 不标记
- [ ] 无 LLM → 跳过此步（返回空列表）
- [ ] UT 2 条: detects_filler / no_llm_skips

**依赖项：** R3, LLM (可选)
**已知约束：** 准确率 ~70%，允许假阳性

---

### R7: Bad take 检测 — 重复片段

**目标：** 检测语义相似的连续段落对（retakes），建议保留后一段。

**涉及文件：**
- `modules/review_engine/bad_take_detector.py` — 新建
- `tests/unit/review_engine/test_bad_take_detector.py` — 新建

**输入：** `paragraphs: List[Paragraph]`
**输出：** `{retakes: [{original_id, retake_id, similarity, recommendation}]}`

**验收标准：**
- [ ] 连续两段 cosine similarity > 0.85 → retake
- [ ] 推荐保留后一段
- [ ] 无 sentence-transformers → 降级为 Jaccard 文字重叠
- [ ] UT 2 条: finds_retakes / no_model_degrades

**依赖项：** R3, sentence-transformers (可选, try/import)
**已知约束：** 降级模式精度较低

---

### R8: Bad take 检测 — false starts

**目标：** 检测句子被打断后重新开始的模式。

**涉及文件：**
- `modules/review_engine/bad_take_detector.py` — 新增
- `tests/unit/review_engine/test_bad_take_detector.py` — 新增

**输入：** `paragraphs: List[Paragraph]`
**输出：** `{false_starts: [{paragraph_id, pattern}]}`

**验收标准：**
- [ ] "所以...所以说我觉得" → false_start (interrupted_restart)
- [ ] "呃...不对...就是说" → false_start (hesitation_restart)
- [ ] UT 2 条: interrupted / hesitation

**依赖项：** R3
**已知约束：** 正则模式匹配，中文语境

---

### R9: TranscriptEditor.vue — 段落展示 + 说话人标签

**目标：** 前端组件：按段落显示转录文字，每段标注说话人和时间戳。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/roughcut/TranscriptEditor.vue` — 新建
- `apps/desktop/ui-vue/src/components/roughcut/TranscriptParagraph.vue` — 新建

**输入：** TranscriptDoc (from store)
**输出：** 渲染的段落列表

**验收标准：**
- [ ] 每段显示说话人标签（颜色区分）+ 时间戳
- [ ] 文字按词渲染（后续标记/高亮需要词级粒度）
- [ ] 长文本自动折行

**依赖项：** R19 (store)
**已知约束：** 无

---

### R10: TranscriptEditor.vue — 标记展示

**目标：** 在文字稿上显示 AI 预标记（语气词/静音/废话/bad take），用不同颜色删除线区分。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/roughcut/FillerMarkup.vue` — 新建
- `apps/desktop/ui-vue/src/components/roughcut/TranscriptParagraph.vue` — 修改

**输入：** filler_words, dead_air, filler_sentences, retakes, false_starts
**输出：** 带颜色标记的文字渲染

**验收标准：**
- [ ] 灰色删除线 = 语气词
- [ ] 红色删除线 = retake / bad take
- [ ] 橙色删除线 = 废话句
- [ ] 蓝色虚线 = 长静音段
- [ ] 点击标记 → 可恢复（取消 AI 建议）

**依赖项：** R9
**已知约束：** 无

---

### R11: TranscriptEditor.vue — 点击跳转 + 播放跟随

**目标：** 点击文字跳转到视频对应时间；播放时文字自动滚动并高亮当前词。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/roughcut/TranscriptEditor.vue` — 修改

**输入：** 当前播放时间 (from video element)
**输出：** 视频 seek + 文字高亮

**验收标准：**
- [ ] 点击任意词 → 视频跳到该词的 start_s
- [ ] 播放中 → 当前播放词高亮，文字稿自动滚动到可视区域
- [ ] 暂停时高亮停留

**依赖项：** R9
**已知约束：** 词级时间戳精度 ±0.1s

---

### R12: TranscriptEditor.vue — 编辑操作

**目标：** 支持删除段落、恢复已删段落、拖拽排序。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/roughcut/TranscriptEditor.vue` — 修改

**输入：** 用户操作 (右键菜单 / 拖拽)
**输出：** 更新的 EDITS 列表

**验收标准：**
- [ ] 选中段落 → 右键 → 删除：该段从 EDITS 中移除
- [ ] 已删段落 → 右键 → 恢复：还原到 EDITS
- [ ] 拖拽段落 → 调整视频顺序：EDITS 重新排列
- [ ] 每次编辑 → 预计时长实时更新

**依赖项：** R9, R19 (store)
**已知约束：** 拖拽使用 SortableJS

---

### R13: TranscriptEditor.vue — Hook 标记 + 统计栏 + 全部接受

**目标：** 精彩片段标记为 hook，统计栏显示时长信息，一键接受全部 AI 建议。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/roughcut/RoughCutStats.vue` — 新建
- `apps/desktop/ui-vue/src/components/roughcut/TranscriptEditor.vue` — 修改

**输入：** 用户操作
**输出：** hook 标记 + 统计数据

**验收标准：**
- [ ] 选中段落 → 右键 → 标记 hook：该段被复制到开头
- [ ] 统计栏显示: 原始时长 / 已删时长 / 预计时长 / 语气词数 / 重复数 / 静音数
- [ ] [全部接受] 按钮：一键接受所有 AI 预标记
- [ ] [全部拒绝] 按钮：还原所有标记
- [ ] [只接受语气词] 按钮

**依赖项：** R10, R12
**已知约束：** 无

---

### R14: 场景分割

**目标：** 对情景路径视频进行镜头切割。

**涉及文件：**
- `modules/review_engine/scene_selector.py` — 新建
- `tests/unit/review_engine/test_scene_selector.py` — 新建

**输入：** `video_path: str`
**输出：** `{scenes: [{scene_id, start_s, end_s, duration_s, thumbnail_path}], total_scenes}`

**验收标准：**
- [ ] FFmpeg scene detection 正确识别切换点 (误差 < 0.5s)
- [ ] 每个场景提取中间帧作为缩略图
- [ ] UT 2 条: splits_scenes / single_scene_video

**依赖项：** R1, FFmpeg
**已知约束：** 无

---

### R15: VLM 镜头分析 (可选)

**目标：** 使用 VLM 对每个场景生成描述、类型标签、质量评分。

**涉及文件：**
- `modules/review_engine/scene_selector.py` — 新增 VLM 分析
- `tests/unit/review_engine/test_scene_selector.py` — 新增 UT

**输入：** `scenes: List[Scene]` (from R14)
**输出：** 更新后的 scenes（每个场景增加 category, description, quality_score, tags）

**验收标准：**
- [ ] VLM 返回 category (landscape/portrait/action/still/closeup/wide)
- [ ] 无 VLM → 降级为仅 thumbnail + 基础分类 (duration-based)
- [ ] UT 2 条: vlm_analysis / no_vlm_degrades

**依赖项：** R14, LLM with vision (可选)
**已知约束：** 每帧分析 ~1-2s，采样关键帧

---

### R16: SceneSelector.vue — 网格展示 + 筛选/排序

**目标：** 网格视图展示分割后的镜头，支持筛选、排序、AI 自动选择。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/roughcut/SceneSelector.vue` — 新建
- `apps/desktop/ui-vue/src/components/roughcut/SceneCard.vue` — 新建
- `apps/desktop/ui-vue/src/components/roughcut/VideoTypeSelector.vue` — 新建

**输入：** scenes[] (from store)
**输出：** 选中的 scene_ids + 配置

**验收标准：**
- [ ] 网格显示缩略图 + 时长 + 类型标签
- [ ] 筛选: 全部/风景/人物/动作/静物/特写
- [ ] 排序: AI推荐/时间/时长/质量
- [ ] 风格选择: 快节奏/电影感/vlog/叙事
- [ ] 目标时长: 30s/60s/90s/自定义
- [ ] [AI 自动选择] + [清除选择] + [生成粗剪]

**依赖项：** R14, R19 (store)
**已知约束：** 无

---

### R17: 混合路径逻辑

**目标：** 对混合视频自动分离口播段和 B-roll 段，分别处理后合并。

**涉及文件：**
- `modules/review_engine/mixed_editor.py` — 新建
- `tests/unit/review_engine/test_mixed_editor.py` — 新建

**输入：** `video_path`, `transcript_doc`, `vad_result`
**输出：** `{speech_segments[], broll_segments[], merged_edits[]}`

**验收标准：**
- [ ] 正确分离口播段和 B-roll 段
- [ ] 合并后 EDITS 保持时间顺序
- [ ] UT 2 条: separates_segments / merge_order

**依赖项：** R2, R3, R14
**已知约束：** 无

---

### R18: 粗剪渲染引擎

**目标：** 将 EDITS 列表渲染为视频文件。

**涉及文件：**
- `modules/review_engine/render_pipeline.py` — 新建
- `tests/unit/review_engine/test_render_pipeline.py` — 新建

**输入：** `edits: List[Segment]`, `output_path`, `config`
**输出：** `{video_path, duration_s, file_size_bytes, processing_time_s}`

**验收标准：**
- [ ] 60 段 EDITS → 连贯视频，无黑帧
- [ ] 音视频同步 < 50ms
- [ ] 3min 视频渲染 < 60s
- [ ] FFmpeg: timeout 300s + stderr 捕获 + 重试 3 次
- [ ] loudnorm 加 `-ar 44100`
- [ ] iPhone HEVC MOV 先转码
- [ ] UT 2 条: basic_concat / timeout_retries
- [ ] IT: 完整渲染与 v4 效果一致

**依赖项：** R1, FFmpeg
**已知约束：** loudnorm 采样率 bug (已知)

---

### R19: roughcut.js Store + RoughCutView.vue

**目标：** 前端状态管理 + 粗剪页面布局。

**涉及文件：**
- `apps/desktop/ui-vue/src/stores/roughcut.js` — 新建
- `apps/desktop/ui-vue/src/views/RoughCutView.vue` — 新建

**输入：** API 响应
**输出：** 响应式状态 + 页面

**验收标准：**
- [ ] store: session, transcript, fillers, edits, stats 状态
- [ ] API 调用封装: loading/error 状态
- [ ] RoughCutView 布局: 左侧视频 + 右上统计 + 下方编辑器
- [ ] 口播路径 → 显示文案编辑器; 情景路径 → 显示镜头选择器

**依赖项：** R20-R22 (API)
**已知约束：** 使用现有前端架构 (Alpine.js 或 Vue)

---

### R20: 粗剪 API — init + detect-type + stats

**目标：** 实现粗剪核心 API: 初始化会话、视频类型检测、统计信息。

**涉及文件：**
- `modules/app_api/routes/roughcut_routes.py` — 新建
- `modules/app_api/server.py` — 注册 blueprint
- `tests/api/test_roughcut_api.py` — 新建

**输入/输出：** 见总参考文档 §7.1

**验收标准：**
- [ ] POST /api/roughcut/init → 201 + session_id + job_id
- [ ] GET /api/roughcut/{id}/detect-type → 200 + video_type + speech_ratio
- [ ] GET /api/roughcut/{id}/stats → 200 + 统计数据
- [ ] 参数缺失 → 400 + `{"success": false, "error": "invalid_request", ...}`
- [ ] session 不存在 → 404
- [ ] UT 3 条

**依赖项：** R1, R2
**已知约束：** 无

---

### R21: 粗剪 API — transcript + fillers + batch

**目标：** 转录、预标记、批量操作 API。

**涉及文件：**
- `modules/app_api/routes/roughcut_routes.py` — 扩展
- `tests/api/test_roughcut_api.py` — 扩展

**输入/输出：** 见总参考文档 §7.1

**验收标准：**
- [ ] GET /api/roughcut/{id}/transcript → 200 + TranscriptDoc
- [ ] GET /api/roughcut/{id}/fillers → 200 + 预标记列表
- [ ] POST /api/roughcut/{id}/fillers/batch → 200 + updated_count
- [ ] POST /api/roughcut/{id}/transcript/edit → 200 + 新 EDITS + 预计时长
- [ ] UT 4 条

**依赖项：** R3, R5-R8
**已知约束：** 无

---

### R22: 粗剪 API — scenes + select + generate

**目标：** 场景、选择、生成粗剪 API。

**涉及文件：**
- `modules/app_api/routes/roughcut_routes.py` — 扩展
- `tests/api/test_roughcut_api.py` — 扩展

**输入/输出：** 见总参考文档 §7.1

**验收标准：**
- [ ] GET /api/roughcut/{id}/scenes → 200 + scenes[]
- [ ] POST /api/roughcut/{id}/scenes/select → 200 + edits_list
- [ ] POST /api/roughcut/{id}/generate → 202 + job_id (后台任务)
- [ ] generate 支持 idempotency_key
- [ ] UT 3 条

**依赖项：** R14, R18
**已知约束：** generate 是后台 job

---

### R23: review_sessions + review_comments 表 CRUD

**目标：** 评审会话和评论的 SQLite 持久化。

**涉及文件：**
- `modules/review_engine/review_store.py` — 新建
- `tests/unit/review_engine/test_review_store.py` — 新建

**输入：** CRUD 参数
**输出：** 数据库操作结果

**验收标准：**
- [ ] 建表语句与总参考文档 §2.x Schema 一致
- [ ] create_session → session_id
- [ ] add_comment → comment_id, 时间毫秒精度
- [ ] update_comment / delete_comment
- [ ] list_comments(session_id, version?) → 支持版本筛选
- [ ] 参数化查询，无 SQL 注入
- [ ] tmp_path 测试数据库
- [ ] UT 5 条: create / add / update / delete / filter

**依赖项：** R1
**已知约束：** SQLite 单线程写入，Store 类内部加锁

---

### R24: review_versions 表 CRUD

**目标：** 版本管理的持久化。

**涉及文件：**
- `modules/review_engine/review_store.py` — 扩展
- `tests/unit/review_engine/test_review_store.py` — 扩展

**输入：** CRUD 参数
**输出：** 数据库操作结果

**验收标准：**
- [ ] create_version → version_id, version_number 自增
- [ ] get_version(session_id, version_number) → 完整版本数据
- [ ] diff_versions(v1, v2) → added/removed/modified segments
- [ ] rollback_to(version) → 创建新版本 (不删历史)
- [ ] UT 4 条: create / get / diff / rollback

**依赖项：** R23
**已知约束：** 无

---

### R25: review_artifacts 表 + 文件管理

**目标：** Artifact 索引 + 版本化文件存储。

**涉及文件：**
- `modules/review_engine/artifact_store.py` — 新建
- `tests/unit/review_engine/test_artifact_store.py` — 新建

**输入：** session_id, version_number, node_name, file_path
**输出：** artifact_id / 文件路径

**验收标准：**
- [ ] save → 文件复制到 `{project}/artifacts/v{N}/{node}/` + DB 记录
- [ ] get → 返回文件路径
- [ ] rollback → 复制历史 artifacts 到新版本
- [ ] atomic write (write-to-temp + os.replace)
- [ ] 大文件使用符号链接
- [ ] UT 3 条: save_get / rollback / atomic_write

**依赖项：** R1
**已知约束：** 无

---

### R26: 评审 API — init + state + comments CRUD

**目标：** 评审会话初始化 + 状态查询 + 评论增删改。

**涉及文件：**
- `modules/app_api/routes/review_routes.py` — 新建
- `modules/app_api/server.py` — 注册 blueprint
- `tests/api/test_review_api.py` — 新建

**输入/输出：** 见总参考文档 §7.2

**验收标准：**
- [ ] POST /api/review/init → 201
- [ ] GET /api/review/{id}/state → 200
- [ ] POST /api/review/{id}/comments → 201 + comment_id
- [ ] PATCH /api/review/comments/{id} → 200
- [ ] DELETE /api/review/comments/{id} → 200
- [ ] 统一错误格式 (success/error/message/code/timestamp/trace_id)
- [ ] UT 5 条

**依赖项：** R23
**已知约束：** 无

---

### R27: 评审 API — versions + diff + rollback

**目标：** 版本查询、diff、回退 API。

**涉及文件：**
- `modules/app_api/routes/review_routes.py` — 扩展
- `tests/api/test_review_api.py` — 扩展

**输入/输出：** 见总参考文档 §7.2

**验收标准：**
- [ ] GET /api/review/{id}/versions → 200 + versions[]
- [ ] GET /api/review/{id}/versions/{v} → 200 + version detail
- [ ] GET /api/review/{id}/diff/{v1}/{v2} → 200 + diff
- [ ] POST /api/review/{id}/rollback/{v} → 200
- [ ] UT 4 条

**依赖项：** R24
**已知约束：** 无

---

### R28: 评审 API — thumbnails + waveform (stub)

**目标：** 缩略图和波形生成的后台 job API (stub，实际生成逻辑在 v0.15.0)。

**涉及文件：**
- `modules/app_api/routes/review_routes.py` — 扩展
- `tests/api/test_review_api.py` — 扩展

**输入/输出：** 见总参考文档 §7.2

**验收标准：**
- [ ] POST /api/review/{id}/thumbnails → 202 + job_id (stub: 直接标记 done)
- [ ] POST /api/review/{id}/waveform → 202 + job_id (stub)
- [ ] UT 2 条

**依赖项：** R23
**已知约束：** 实际生成逻辑在 v0.15.0 实现

---

### R29: 集成测试 + 冒烟测试

**目标：** 端到端验证完整粗剪流程 + 评审数据层。

**涉及文件：**
- `tests/integration/test_roughcut_flow.py` — 新建
- `tests/smoke/test_smoke_review.py` — 新建
- `tests/conftest.py` — 新增 fixtures

**输入：** 测试视频
**输出：** 测试报告

**验收标准：**
- [ ] IT: init → detect → transcript → fillers → edit → generate → 完整流程
- [ ] IT: review init → add comment → create version → diff → rollback
- [ ] SMK: 核心路径 < 30s
- [ ] REG: `pytest project/tests/ -v` 全量 0 失败
- [ ] 测试报告: `docs/test-reports/test-report-v0.14.0-release.md`

**依赖项：** R1-R28
**已知约束：** 部分 IT 需真实视频 (@pytest.mark.slow)

---

## 5. 完成状态追踪

| 任务 | 计划周期 | 实际完成 | 迭代 | 备注 |
|------|---------|---------|------|------|
| R1-R8 | 2.5 天 | 2026-03-31 | 1 | ✅ 后端逻辑 — 全部完成 |
| R9-R13 | 2 天 | 2026-03-31 | 1 | ✅ 编辑器 UI — 全部完成 |
| R14-R17 | 1.5 天 | 2026-03-31 | 1 | ✅ 情景+混合 — R15 VLM 推迟 |
| R18-R22 | 2 天 | 2026-03-31 | 1 | ✅ 渲染+API — 全部完成 |
| R23-R28 | 2 天 | 2026-03-31 | 1 | ✅ 数据层 — 全部完成 |
| R29 | 1 天 | 2026-03-31 | 1 | ✅ 测试 — 125 tests passed |
| **总计** | **11 天** | **2026-03-31** | **1** | **28/29 完成 (R15 Deferred)** |

## 6. 决策和假设

| # | 内容 | 理由 |
|---|------|------|
| D1 | review_engine 独立于 step pipeline | 用户场景不同：step pipeline 是内容生产，review_engine 是剪辑修改 |
| D2 | VLM 分析可选 | 用户可能无 GPU/VLM API |
| A1 | 用户有 FFmpeg ≥ 5.0 | afftdn/loudnorm 需要 |
| A2 | 用户有 faster-whisper 或 openai-whisper | 口播路径核心依赖 |

## 7. 风险和缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Whisper 中文精度不足 | 中 | 中 | 允许用户手动修改转录文字 |
| 说话人分离不准 | 中 | 低 | 用户可手动改标签 |
| 长视频渲染超时 | 中 | 中 | timeout 300s + 分段渲染 |

## 8. 变更记录

| 版本 | 日期 | 变更 | 责任人 |
|------|------|------|--------|
| V1.0 | 2026-03-31 | 初版，29 个 R 任务 | Claude Code |

---

*文档结束*
