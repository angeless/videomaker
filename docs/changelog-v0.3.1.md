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

## 下一步计划

参见 `docs/next_dev_plan.md` 中的 Phase 1-4 计划。当前优先项：
1. 真实发布引擎（官方平台 connector）
2. 安全基线增强（细粒度权限 + 审计日志）
3. 队列恢复体验（中断任务批量重试）
