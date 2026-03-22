# R10 实施计划：硬件自适应 + 性能优化

**版本：** v0.12.10
**日期：** 2026-03-22
**基线 Commit：** 377f1ee (upgrade: incremental spec upgrade v1.4 → v1.5)
**依赖：** R1-R9 已完成

---

## 1. 任务目标

为 VideoEditor 添加硬件自适应能力，使系统能根据运行环境（CPU/GPU/RAM）自动选择最优的编码方案和并发策略，提升渲染性能。

## 2. 范围与约束

### 做什么
1. **硬件探测模块** — 检测 CPU 核数、RAM、GPU 类型及可用加速器
2. **FFmpeg 加速适配** — macOS VideoToolbox / Linux NVENC / CPU fallback 三级策略
3. **自适应队列调度** — 根据系统负载动态调整 max_running
4. **Preflight 集成** — 将硬件信息注入 preflight 报告
5. **API 暴露** — `/api/system/hardware` 端点

### 不做什么
- 不引入新的 Python 依赖（用 subprocess + os 模块即可）
- 不修改现有渲染流程的核心逻辑，只在编码参数层适配
- 不做 GPU 渲染（仅 FFmpeg 硬件编码加速）

## 3. 实施步骤

### Step 1: 硬件探测模块 `modules/hardware/detector.py`

```python
# 功能：
# - detect_cpu(): cores, model, architecture
# - detect_memory(): total_gb, available_gb
# - detect_gpu(): vendor, model, has_videotoolbox/nvenc/vaapi
# - detect_ffmpeg_hwaccels(): 调用 ffmpeg -hwaccels 解析可用加速器
# - get_system_profile(): 综合硬件画像 → HardwareProfile dataclass
```

### Step 2: 编码策略选择器 `modules/hardware/encoding_strategy.py`

```python
# 功能：
# - choose_encoder(profile: HardwareProfile) → EncodingParams
# - macOS + Apple Silicon → h264_videotoolbox
# - NVIDIA GPU → h264_nvenc
# - 其他 → libx264 (CPU, 根据核数选 preset)
# - suggest_max_concurrent(profile) → int (1-4)
```

### Step 3: RenderConfig 集成

在 `auto_render.py` 的 `RenderConfig` 中增加 `encoder` 和 `hwaccel` 字段，
`FFmpegRenderer` 构建命令时使用硬件加速参数。

### Step 4: Preflight + API 集成

- `preflight_service.py` 新增 `_check_hardware()` 检测项
- `system_routes.py` 新增 `/api/system/hardware` 端点
- 队列 max_running 默认值由硬件画像决定

## 4. 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| AC-1 | `detect_cpu()` 返回核数 ≥ 1 | 单元测试 |
| AC-2 | `detect_memory()` 返回 total_gb > 0 | 单元测试 |
| AC-3 | `detect_ffmpeg_hwaccels()` 返回列表（可为空） | 单元测试 |
| AC-4 | `get_system_profile()` 返回完整 HardwareProfile | 单元测试 |
| AC-5 | macOS 环境下 `choose_encoder()` 推荐 videotoolbox | 单元测试 mock |
| AC-6 | CPU-only 环境下 fallback 到 libx264 | 单元测试 |
| AC-7 | `suggest_max_concurrent()` 基于 RAM 和 CPU 返回合理值 | 单元测试 |
| AC-8 | `/api/system/hardware` 返回 200 + 硬件信息 | API 测试 |
| AC-9 | RenderConfig 支持 encoder/hwaccel 参数 | 单元测试 |
| AC-10 | 现有测试不被破坏 | 回归测试 |

## 5. 风险

| 风险 | 缓解 |
|------|------|
| VideoToolbox 在 CI 环境不可用 | 所有硬件加速代码有 CPU fallback |
| subprocess 调用 ffmpeg 失败 | try/except + 默认空列表 |
| psutil 不是项目依赖 | 不使用 psutil，改用 os/platform/subprocess |

## 6. 文件变更清单

| 操作 | 文件 |
|------|------|
| 新增 | `modules/hardware/__init__.py` |
| 新增 | `modules/hardware/detector.py` |
| 新增 | `modules/hardware/encoding_strategy.py` |
| 修改 | `modules/step7_final_render/auto_render.py` — RenderConfig 增加字段 |
| 修改 | `modules/app_api/services/preflight_service.py` — 新增硬件检测项 |
| 修改 | `modules/app_api/routes/system_routes.py` — 新增 hardware 端点 |
| 新增 | `tests/test_hardware_detector.py` |
| 新增 | `tests/test_encoding_strategy.py` |
