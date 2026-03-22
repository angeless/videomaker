# 测试报告 v0.12.10 — R10 硬件自适应 + 性能优化

**日期：** 2026-03-22
**测试环境：** macOS Darwin 23.6.0, Python 3.13.1, pytest 8.3.4

## 测试结果摘要

| 类别 | 数量 |
|------|------|
| 新增测试 | 22 |
| 全量测试通过 | 917 |
| 全量测试跳过 | 50 |
| 全量测试失败 | 0 |
| 耗时 | 54.79s |

## 新增测试详情

### test_hardware_detector.py (10 tests)
- TestDetectCPU: 返回值结构、logical ≥ physical
- TestDetectMemory: 返回值结构、available ≤ total
- TestDetectGPU: 返回值结构、macOS VideoToolbox 检测
- TestDetectFFmpegHwaccels: 返回类型、缺失 ffmpeg 降级、macOS videotoolbox
- TestGetSystemProfile: 完整 profile 聚合

### test_encoding_strategy.py (12 tests)
- TestChooseEncoder: VideoToolbox/NVENC/VAAPI/CPU 四路选择、优先级
- TestCPUPreset: 核数与 preset 映射
- TestSuggestMaxConcurrent: 范围限制、低 RAM 限制、硬件加速增益、最小值保证

## 回归测试

全量 917 个测试通过，无回归。
