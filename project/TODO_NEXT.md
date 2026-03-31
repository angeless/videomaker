# VideoEditor — 待办进度

> 更新于 2026-03-31

## 当前版本：v0.13.1
## 当前状态：v0.14.0 开发中

## 三版本规划

| 版本 | 内容 | R 任务数 | 计划文档 |
|------|------|---------|---------|
| v0.14.0 | 智能粗剪 + 评审数据层 | 29 | `docs/dev-plans/dev-plan-v0.14.0.md` |
| v0.15.0 | 核心评审 UI + 高级标注 | 23 | `docs/dev-plans/dev-plan-v0.15.0.md` |
| v0.16.0 | AI 重编辑引擎 + 增强能力 | 25 | `docs/dev-plans/dev-plan-v0.16.0.md` |

总参考文档: `docs/dev-plans/timeline-review-ai-reedit.md`

## v0.14.0 任务进度

| 任务 | 描述 | 优先级 | 状态 |
|------|------|--------|------|
| R1 | review_engine 模块脚手架 | P0 | ✅ Done |
| R2 | 视频类型检测 (VAD) | P0 | ✅ Done |
| R3 | Whisper 词级转录集成 | P0 | ✅ Done |
| R4 | 说话人分离 (diarization) | P1 | ✅ Done |
| R5 | 语气词 + 静音检测 | P0 | ✅ Done |
| R6 | 废话句检测 (LLM) | P1 | ✅ Done |
| R7 | Bad take — 重复片段 | P0 | ✅ Done |
| R8 | Bad take — false starts | P1 | ✅ Done |
| R9 | TranscriptEditor — 段落展示 | P0 | Planned |
| R10 | TranscriptEditor — 标记展示 | P0 | Planned |
| R11 | TranscriptEditor — 点击跳转 | P0 | Planned |
| R12 | TranscriptEditor — 编辑操作 | P0 | Planned |
| R13 | TranscriptEditor — Hook+统计 | P0 | Planned |
| R14 | 场景分割 (FFmpeg) | P1 | ✅ Done |
| R15 | VLM 镜头分析 | P2 | Deferred |
| R16 | SceneSelector UI | P1 | Planned |
| R17 | 混合路径逻辑 | P1 | ✅ Done |
| R18 | 粗剪渲染引擎 | P0 | ✅ Done |
| R19 | roughcut.js Store + View | P0 | Planned |
| R20 | 粗剪 API — init/detect/stats | P0 | ✅ Done |
| R21 | 粗剪 API — transcript/fillers | P0 | ✅ Done |
| R22 | 粗剪 API — scenes/generate | P1 | ✅ Done |
| R23 | review_sessions + comments CRUD | P0 | ✅ Done |
| R24 | review_versions CRUD | P0 | ✅ Done |
| R25 | review_artifacts + 文件管理 | P0 | ✅ Done |
| R26 | 评审 API — init/state/comments | P0 | ✅ Done |
| R27 | 评审 API — versions/diff/rollback | P0 | ✅ Done |
| R28 | 评审 API — thumbnails/waveform stub | P1 | ✅ Done |
| R29 | 集成测试 + 冒烟测试 | P0 | Planned |

## 测试状态

- 104 tests passing (75 unit + 13 review API + 10 roughcut API + 6 artifact)
- 测试覆盖: video_detector, transcript_editor, speaker_diarizer, filler_detector, bad_take_detector, scene_segmenter, mixed_editor, render_pipeline, review_store, artifact_store, review_routes, roughcut_routes

## 下一步

1. R9-R13: TranscriptEditor Vue UI 组件
2. R16: SceneSelector Vue UI
3. R19: roughcut.js Store + RoughCutView.vue
4. R29: 集成测试 + 冒烟测试
5. 版本收尾: Phase 4 审计 + Phase 5 测试报告

## 已完成的文件清单

### review_engine 模块 (modules/review_engine/)
- `__init__.py` — 公共 API 入口
- `contracts.py` — 数据契约 (dataclass)
- `exceptions.py` — 异常层级
- `video_detector.py` — R2: VAD 视频类型检测
- `transcript_editor.py` — R3: Whisper 词级转录
- `speaker_diarizer.py` — R4: 说话人分离
- `filler_detector.py` — R5: 语气词 + 静音检测
- `bad_take_detector.py` — R6-R8: 废话句/重复/false start
- `scene_segmenter.py` — R14: FFmpeg 场景分割
- `mixed_editor.py` — R17: 混合路径分离合并
- `render_pipeline.py` — R18: FFmpeg 粗剪渲染
- `review_store.py` — R23-R24: SQLite 持久化
- `artifact_store.py` — R25: 版本化文件管理

### API 路由 (modules/app_api/routes/)
- `review_routes.py` — R26-R28: 评审 API
- `roughcut_routes.py` — R20-R22: 粗剪 API

### 适配器 (modules/adapters/)
- `pexels_adapter.py` — stub, deferred to v0.16.0
- `tts_adapter.py` — stub, deferred to v0.16.0

## 注意事项

- 基线 commit: `5a48ef9`
- review_engine 独立于 step pipeline (并行路径)
- 异常继承自 VideoEditorError (modules/exceptions.py)
- 外部 API (Pexels/TTS) 走 adapters/ 层
- loudnorm 必须加 `-ar 44100`
- 大文件 (>50MB) artifact 使用 symlink
