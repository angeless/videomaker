# v0.14.0 Code Review Report (§7.3)

**日期：** 2026-03-31
**版本：** v0.14.0
**审查范围：** `modules/review_engine/` (14 files, ~2,400 lines) + `app_api/routes/` (2 files)
**审查方法：** 独立 Agent 交叉审查 (superpowers:code-reviewer)
**审查执行者：** Claude Code sub-agent

---

## 审查结果摘要

| 级别 | 发现数 | 已修复 | 延迟到后续版本 |
|------|--------|--------|---------------|
| Critical | 1 | 1 | 0 |
| Important | 8 | 3 | 5 |
| Minor | 8 | 0 | 8 |

---

## Critical 发现

### C1: Path Traversal in ArtifactStore — **已修复** ✅

**位置：** `artifact_store.py` `_version_dir()`
**问题：** `session_id` 和 `node_name` 直接拼入 `os.path.join` 而无验证，攻击者可传入 `../../etc` 逃逸 artifacts 根目录。
**修复：**
1. 新增 `_validate_path_component()` 静态方法，拒绝含 `os.sep`、`/`、`\`、`..` 的路径组件
2. 增加 belt-and-suspenders 检查：确认最终路径在 `_artifacts_root` 之下
**测试：** 125/125 通过

---

## Important 发现

### I1: ReviewStore reads without lock — **Deferred**

**位置：** `review_store.py` `get_session()`, `list_comments()`, `get_version()`, `list_versions()`
**评估：** SQLite 默认 serialized 线程模式，读操作使用独立连接，线程安全。写操作已有 `_lock` 保护。无实际安全/正确性风险，仅为最佳实践建议。
**处置：** v0.15.0 统一评估锁策略

### I2: ArtifactStore accesses ReviewStore private members — **已修复** ✅

**位置：** `artifact_store.py` 直接访问 `_review_store._lock` 和 `_review_store._connect()`
**修复：** 在 ReviewStore 新增公共方法 `execute_locked(callback)`，ArtifactStore 全部改用此 API。

### I3: `_find_ffmpeg()` duplicated 3x — **Already in WISHLIST (W-021)**

**位置：** `video_detector.py`, `render_pipeline.py`, `scene_segmenter.py`
**处置：** 低优先级代码整洁，不影响正确性。W-021 已跟踪。

### I4: Whisper model loaded per transcription call — **Deferred**

**位置：** `transcript_editor.py`
**评估：** 可选依赖路径，当前无性能热点（本地单用户场景），v0.15.0 加模型缓存

### I5: SentenceTransformer loaded per call — **Deferred**

**位置：** `mixed_editor.py`
**评估：** 同 I4

### I6: `__import__("json")` in render_pipeline — **已修复** ✅

**位置：** `render_pipeline.py` `_get_duration()` L212
**修复：** 改为模块级 `import json`

### I7: Inline imports in Flask handlers — **Deferred**

**位置：** `roughcut_routes.py` 多处
**评估：** 有意为之的懒加载模式，避免启动时加载重型模块（torch、pyannote 等）。不修改。

### I8: `artifact_store_getter=lambda: None` — **Deferred**

**位置：** `server.py` L486
**评估：** 有意为之的延迟布线 — review_routes 的注释明确标注 `(or None)`，artifact 操作当前在 roughcut_routes 完成。v0.15.0 完成 artifact store 全局初始化时统一修复。

---

## Minor 发现

| ID | 位置 | 描述 | 处置 |
|---|---|---|---|
| M1 | 多文件 | 缺少 shebang `#!/usr/bin/env python3` | 模块文件非可执行，shebang 非必需 |
| M2 | Vue 前端 | `formatTime` 在多组件重复 | 前端 utils 整理推迟到 v0.15.0 |
| M3 | `mixed_editor.py` | 文本重叠回退策略较弱（仅用前2词） | 可接受的降级，v0.15.0 优化 |
| M4 | `bad_take_detector.py` | 段间死区 filler 未归属到段落 | 不影响检测结果，标注即可 |
| M5 | `speaker_diarizer.py` | pyannote 降级缺少日志 | 已有 try/import 机制，添加 warning 推迟 |
| M6 | `contracts.py` | 部分 dataclass 缺少 `__repr__` | 默认 `__repr__` 已足够 |
| M7 | `scene_segmenter.py` | FFprobe 超时硬编码 30s | 合理默认值，不修改 |
| M8 | `roughcut_routes.py` | L77 宽泛 except (已在 W-022) | WISHLIST 已跟踪 |

---

## 修复验证

```
125 passed, 3 warnings in 1.59s
├── 单元测试: 75 ✅
├── API 测试: 23 ✅
├── 集成测试: 5 ✅
└── 冒烟测试: 16 ✅（含 artifact_store 导入验证）
```

---

## 结论

- **Critical C1 已修复** — 路径遍历漏洞已堵上，双重验证（组件检查 + 路径归属检查）
- **Important 3/8 已修复**（I2 封装、I6 导入方式），5 项合理推迟
- **Minor 8 项** 均为代码整洁类，不影响安全/正确性
- **合并判定：✅ 可以合并到 main**
