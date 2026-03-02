# Changelog v0.3.1（2026-03-01）

基于 main 分支，等价移植 serene-shamir 分支 v0.3.1 的改进。

## 本轮变更

| 编号 | 改进 | 涉及文件 | 状态 |
|------|------|---------|------|
| P0.4 | OpenCV 帧读取安全上限 | `modules/step7_final_render/beauty.py`, `modules/step7_final_render/pipeline.py`, `modules/step7_final_render/auto_render.py` | **已完成** |
| P2.8 | README.md 全面重写 | `README.md` | **main 已有**（无需移植） |
| P2.9 | Blog 平台本地真实导出 | `modules/capabilities/content_publish.py`, `tests/test_content_publish.py` | **main 已有**（无需移植） |

## P0.4 详细说明

**问题**：`beauty.py`、`pipeline.py`、`auto_render.py` 中的 cv2 帧读取使用 `while True` 循环。如果遇到损坏的视频文件，`cap.read()` 可能在某些边界情况下持续返回空帧但不返回 `False`，导致无限循环。

**修复**：将 `while True` 改为 `while frame_idx < max_frames`，其中：
```python
max_frames = max(total_frames * 2, int(fps * 600))
```
- `total_frames * 2`：报告帧数的 2 倍（容忍帧数报告不准确）
- `int(fps * 600)`：10 分钟等效帧数（兜底上限）
- 取两者较大值，确保正常视频不会被误截断

**影响范围**：
- `beauty.py:process_video()` — 磨皮逐帧处理循环
- `pipeline.py:_apply_subtitles_cv2()` — PIL 字幕渲染逐帧循环
- `auto_render.py:_burn_subtitles_python()` — 独立渲染器的 PIL 字幕循环

## 回归验证

- `python -m py_compile` 三个文件全部通过
- `pytest -q`：**136 passed**（无回归）
- 测试数量从之前的 125 增至 136（main 分支此前已有新增测试）

## 分支说明

- 工作分支：`main`
- serene-shamir 分支的 v0.3.0 含有架构差异（回退了模块化路由拆分），不适合直接合并
- 本次仅移植了 v0.3.1 中 main 尚未覆盖的改进（P0.4）

## v0.3.2 安全测试补充（2026-03-01）

新增 3 个安全边界测试，验证现有安全守卫的完备性：

| 编号 | 测试 | 涉及文件 | 结论 |
|------|------|---------|------|
| S1 | 伪造/空 CSRF token 被拒绝（403） | `tests/test_ai_settings_and_queue.py` | **守卫完备** |
| S2 | 不存在的 job_id 返回 404 | `tests/test_ai_settings_and_queue.py` | **守卫完备** |
| S3 | POST 缺失/错误 API token 被拒绝（401） | `tests/test_ai_settings_and_queue.py` | **守卫完备** |

**详细覆盖**：
- S1：伪造 CSRF → 403 `csrf_required`；空 CSRF → 403 `csrf_required`；正确 CSRF → 200
- S2：GET `/api/job/<不存在>` → 404；POST `/api/job/<不存在>/cancel` → 404
- S3：POST 无 token → 401 `local_auth_required`；错误 token → 401；GET 无 token → 401；正确 token+CSRF → 200

**结论**：`server.py` 的 `_guard_local_api_token()` 和 `job_routes.py` 的参数验证已正确覆盖所有边界情况，无需修补代码。

回归验证：**139/139 测试通过**。

## v0.3.3 输入验证增强（2026-03-01）

为 API 路由层的数值参数添加边界检查（try/except + `max(lo, min(val, hi))`），防止非法输入导致意外行为或资源浪费。

| 文件 | 参数 | 边界 |
|------|------|------|
| `routes/capability_editing_routes.py` | `target_duration_s` | 1–600 |
| `routes/capability_editing_routes.py` | `max_clips` | 1–50 |
| `routes/capability_editing_routes.py` | `fps` (×2) | 1–120 |
| `routes/capability_editing_routes.py` | `timeout_seconds` | 1–300 |
| `routes/idempotency_routes.py` | `limit` | 1–1000 |
| `routes/idempotency_routes.py` | `offset` | ≥0 |
| `routes/capability_social_export_routes.py` | `timeout_seconds` (×2) | 10–7200 |
| `routes/capability_social_export_routes.py` | `quality` (×3) | 枚举 `low/medium/high/lossless` |

**新增测试**：
- `test_v033_idempotency_limit_offset_bounds`：负值/超大/非数字 limit/offset 不崩溃
- `test_v033_social_export_quality_enum_fallback`：非法 quality 值静默回退为 `high`

**注意**：已有正确边界的参数未改动（如 `topic_library.limit` 已有 `max(1, min(limit, 300))`，`agent_task_run.max_parallel` 已有 `max(1, min(…, 8))`，`observability.limit/top_n` 已有完整边界）。

回归验证：**141/141 测试通过**。

## v0.3.4 测试覆盖 + 残余验证（2026-03-02）

### 新增 GET 端点覆盖测试

| 端点 | 涉及蓝图 | 测试 |
|------|---------|------|
| `GET /api/status` | `system_routes` | `test_v033_system_get_endpoints` |
| `GET /api/system/load` | `system_routes` | 同上 |
| `GET /api/tasks/queue` | `system_routes` | 同上 |
| `GET /api/library/stats` | `library_routes` | `test_v033_library_stats_endpoint` |
| `GET /api/workflows/catalog` | `workflow_routes` | `test_v033_workflows_catalog_endpoint` |

### 残余输入验证补全

| 文件 | 参数 | 边界 |
|------|------|------|
| `routes/capability_audio_voice_routes.py` | `origin/narration/bgm_volume` | 0.0–3.0 |
| `routes/capability_audio_voice_routes.py` | `bgm_fade_out_s` | 0.0–30.0 |
| `routes/capability_audio_voice_routes.py` | `ducking_threshold` | 0.0–1.0 |
| `routes/capability_audio_voice_routes.py` | `ducking_ratio` | 1.0–50.0 |
| `routes/capability_audio_voice_routes.py` | `ducking_attack/release_ms` | 0–500 / 0–2000 |
| `routes/capability_content_publish_routes.py` | `expires_in_minutes` | 1–43200 |

### 已确认完备的路由（无需修改）

- `agent_task_query_routes.py`：`limit`/`offset` 已有完整边界
- `agent_task_run_routes.py`：`max_parallel` 已有 `max(1, min(…, 8))`
- `agent_observability_routes.py`：`limit`/`top_n` 已有完整边界
- `library_routes.py`：`limit`/`offset`/`media_type`/`retrieval_mode` 已有完整验证

回归验证：**144/144 测试通过**。

## v0.3.5 JSON 错误响应标准化（2026-03-02）

**问题**：Flask 默认对 404（未知路由）和 405（方法不允许）返回 HTML 页面，不符合 JSON API 规范，前端/Agent 客户端需额外处理。

**修复**：在 `server.py` 新增：
- `@app.errorhandler(404)` → `{"error": "路由不存在", "code": "not_found"}`
- `@app.errorhandler(405)` → `{"error": "HTTP 方法不允许", "code": "method_not_allowed"}`
- 通用 `HTTPException` 处理改为返回 JSON（`{"error": desc, "code": name}`），而非直接 `return exc`

**新增测试**：
- `test_v035_unknown_route_returns_json_404`：验证未知路由返回 JSON 404
- `test_v035_wrong_method_returns_json_405`：验证 DELETE /api/status 返回 JSON 405

回归验证：**146/146 测试通过**。

## 下一步计划

参见 `docs/next_dev_plan.md` 中的 Phase 1-4 计划。当前优先项：
1. 真实发布引擎（官方平台 connector）
2. 安全基线增强（细粒度权限 + 审计日志）
3. 队列恢复体验（中断任务批量重试）
