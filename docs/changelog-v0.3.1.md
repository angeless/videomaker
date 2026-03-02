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

## v0.3.6 SQLite 连接泄漏修复（2026-03-02）

**问题**：Python 的 `with sqlite3.connect(...) as conn:` 语义是 commit/rollback，**不会**关闭连接。这导致测试中出现大量 `ResourceWarning: unclosed database` 警告，生产环境下也存在连接泄漏风险（文件描述符与内存不释放）。

**修复**：

| 文件 | 修复方式 |
|------|---------|
| `modules/app_api/job_store.py` | `_connect()` 改为 `@contextmanager`，`try/yield/commit + except/rollback + finally/close` |
| `modules/app_api/migrations.py` | `with sqlite3.connect()` 改为 `conn = sqlite3.connect(); try/commit/except rollback/finally close` |
| `modules/capabilities/topic_library.py` | 新增 `_connect()` 上下文管理器，5 个函数全部替换 |
| `tests/test_ai_settings_and_queue.py` | 2 处测试验证查询改为 `try/finally conn.close()` |

**验证**：`pytest -q -W all` → **146 passed, 0 warnings**（修复前有多个 ResourceWarning）。

## v0.3.7 资源泄漏防护 + 错误处理增强（2026-03-02）

### cv2.VideoCapture/VideoWriter 异常安全

视频处理函数的 `cap.release()` / `writer.release()` 全部包裹 `try/finally`，防止中间异常导致文件描述符泄漏。

| 文件 | 修复内容 |
|------|---------|
| `modules/step7_final_render/beauty.py` | `process_video()` 加 `try/finally` 嵌套释放 cap+out |
| `modules/step7_final_render/pipeline.py` | `_apply_subtitles_cv2()` 加 `try/finally`，移除取消路径的冗余 release |
| `modules/step7_final_render/auto_render.py` | `_burn_subtitles_python()` 加 `try/finally` 嵌套释放 cap+writer |
| `modules/step1_material_analysis/video_asset_toolkit.py` | `isOpened()` 失败早期退出前补 `cap.release()` |

### 裸 except 子句修复

| 文件 | 行 | 修复 |
|------|-----|------|
| `video_asset_toolkit.py` L71 | `except:` → `except Exception:` | 配置解析失败 |
| `video_asset_toolkit.py` L112 | `except:` → `except Exception:` | 哈希生成降级 |
| `video_asset_toolkit.py` L243 | `except:` → `except (TypeError, ValueError):` | 码率解析 |

### 静默异常改为日志输出

| 文件 | 位置 | 修复 |
|------|------|------|
| `job_runtime.py` L24 | `ManagedJobLog._notify()` | `pass` → `traceback.print_exc()` |
| `job_runtime.py` L91 | `ManagedJob._notify()` | `pass` → `traceback.print_exc()` |
| `job_runtime.py` L143 | `_persist()` | `pass` → `traceback.print_exc()` |

回归验证：**146/146 测试通过，0 warnings**。

## v0.3.8 子进程超时 + 裸 except 修复（2026-03-02）

### subprocess 超时防护

为所有核心模块的 `subprocess.run()` / `check_output()` 添加 `timeout` 参数，防止损坏文件或网络文件导致 FFmpeg/FFprobe 无限挂起。

| 文件 | 调用数 | 超时值 |
|------|--------|--------|
| `auto_render.py` | 8 处 | 15s（filter检测）/ 30s（ffprobe）/ 300s（裁剪/合并）/ 600s（音频混合）/ 3600s（完整渲染） |
| `pipeline.py` | 2 处 | 600s（片段编码/字幕 re-encode） |
| `rough_cut.py` | 2 处 | 600s（片段编码/concat） |
| `video_asset_toolkit.py` | 1 处 | 30s（ffprobe 元数据提取） |

### 裸 except 修复（第二批）

| 文件 | 修复 |
|------|------|
| `search_videos.py` L150/184 | `except:` → `except Exception:` |
| `search_videos.py` L253 | `except:` → `except Exception:` |
| `materials_mapper.py` L192 | `except:` → `except (TypeError, ValueError):` |

回归验证：**146/146 测试通过，0 warnings**。

## v0.3.9 进程管理 + 临时目录清理（2026-03-02）

### Popen 替换为 subprocess.run

macOS `open` 命令的 `Popen` 改为 `subprocess.run(timeout=5, check=False)`，消除潜在的僵尸进程。

| 文件 | 位置数 |
|------|--------|
| `workflow.py` | 3 处（帧预览/粗剪/最终视频） |
| `legacy_project_routes.py` | 2 处（Finder 打开文件/目录） |

### 临时目录清理保护

`workflow.py:_run_render()` 的 `shutil.rmtree(tmp)` 包裹 `try/finally`，确保渲染异常时临时文件也被清理。

### 裸 except 修复（第三批）

`jianying_draft.py` L435: `except:` → `except (TypeError, ValueError):`

回归验证：**146/146 测试通过，0 warnings**。

## v0.3.10 参数解析工具 + POST 端点测试覆盖（2026-03-02）

### 新增 `param_utils.py` 共享工具

新增 `modules/app_api/param_utils.py`，提供 `parse_int_param()` 和 `parse_float_param()` 两个通用参数解析函数，后续路由可逐步替换重复的 try/except 解析逻辑。

### 新增 4 个测试

| 测试 | 覆盖内容 |
|------|---------|
| `test_v0310_parse_int_param` | 8 个边界场景：正常值/None/空字符串/非数字/下限/上限/浮点字符串/int直传 |
| `test_v0310_parse_float_param` | 6 个边界场景：正常/None/非数字/下限/上限/float直传 |
| `test_v0310_editing_post_endpoints_require_project` | 5 个 POST + 1 个 GET 端点无项目时返回 400；refinement/plan 自动降级验证 |
| `test_v0310_topic_library_list_inline_returns_200` | inline 模式下 topic_library GET 返回 200；project 模式无项目返回 400 |

回归验证：**150/150 测试通过，0 warnings**。

## v0.3.11 参数解析统一 + subprocess 超时补全 + 裸 except 修复（2026-03-02）

### 路由参数解析统一

将 7 个路由文件中 24 处重复的 `try/except int()/float() + max(min(...))` 解析模式替换为共享工具 `parse_int_param()` / `parse_float_param()`，消除代码重复。

| 文件 | 替换数 |
|------|--------|
| `routes/capability_editing_routes.py` | 7 处（limit/target_duration_s/max_clips/fps×2/timeout_seconds） |
| `routes/capability_social_export_routes.py` | 3 处（limit/timeout_seconds×2） |
| `routes/idempotency_routes.py` | 2 处（limit/offset） |
| `routes/agent_task_run_routes.py` | 2 处（max_parallel×2） |
| `routes/agent_task_query_routes.py` | 2 处（limit/offset） |
| `routes/agent_observability_routes.py` | 4 处（limit×2/top_n×2） |
| `routes/workflow_routes.py` | 2 处（limit/offset） |

### subprocess 超时补全

| 文件 | 修复内容 | 超时值 |
|------|---------|--------|
| `modules/app_api/server.py` | `osascript` 文件/目录对话框 | 120s |
| `modules/step5_frame_preview/frame_preview.py` | FFmpeg 帧提取 | 30s |

### 裸 except 修复（第四批）

| 文件 | 修复 |
|------|------|
| `legacy_lab/manage_videos/improved_fingerprint.py` L131 | `except:` → `except Exception:` |
| `legacy_lab/manage_videos/fingerprint_system.py` L154 | `except:` → `except Exception:` |
| `legacy_lab/manage_videos/tests/test_search_function.py` L170 | `except:` → `except Exception:` |
| `legacy_lab/manage_videos/learn/learn_ai_analysis_part2.py` L128,L184 | `except:` → `except Exception:` (×2) |

回归验证：**150/150 测试通过，0 warnings**。

---

## v0.3.12（2026-03-02）— 参数解析统一（第三批）+ library 端点测试

### 路由参数解析统一

将 `library_routes.py` 和 `capability_audio_voice_routes.py` 中剩余的手写
`try/except int()/float() + max(min())` 模式替换为共享工具函数。

| 文件 | 替换数 | 参数 |
|------|--------|------|
| `library_routes.py` | 15 处 | limit, offset, max_results, max_videos, max_images, max_scan_folders |
| `capability_audio_voice_routes.py` | 8 处 | origin_volume, narration_volume, bgm_volume, bgm_fade_out_s, ducking_* |

净减代码约 55 行，行为完全保持一致。

### 新增测试（+5）

| 测试 | 端点 | 验证内容 |
|------|------|---------|
| `test_v0312_library_search_default_params` | GET /api/library/search | 默认参数、browse 模式 |
| `test_v0312_library_search_with_query_and_bounds` | GET /api/library/search | 无效/超大 limit/offset 安全降级 |
| `test_v0312_library_assets_post` | POST /api/library/assets | UID 批量查询 |
| `test_v0312_library_preview_local_missing_path` | POST /api/library/preview/local | 缺少 path 返回 400 |
| `test_v0312_library_preview_local_invalid_max_results` | POST /api/library/preview/local | 无效数值安全降级 |

回归验证：**152/152 测试通过，0 warnings**。

## 下一步计划

参见 `docs/next_dev_plan.md` 中的 Phase 1-4 计划。当前优先项：
1. 真实发布引擎（官方平台 connector）
2. 安全基线增强（细粒度权限 + 审计日志）
3. 队列恢复体验（中断任务批量重试）
