# 测试报告 — R1 两处 Segfault 修复

**日期：** 2026-03-21
**任务：** R1（BUG-001 + BUG-002）
**版本：** v0.11.0

---

## 测试结果

| 测试类型 | 用例数 | 通过 | 失败 | 跳过 |
|---------|--------|------|------|------|
| R1 验收测试 | 8 | 8 | 0 | 0 |
| 全量回归 | 822 | 772 | 0 | 50 |

## R1 验收用例明细

| # | 用例 | 结果 |
|---|------|------|
| 1 | POST /api/init {"project_dir": null} → 不崩溃 | ✅ PASS |
| 2 | POST /api/init {"project_dir": null, "videos_dir": null} → 不崩溃 | ✅ PASS |
| 3 | POST /api/init {"project_dir": ""} → 原有 400 逻辑 | ✅ PASS |
| 4 | POST /api/run_step {"step": 99} → 400 | ✅ PASS |
| 5 | POST /api/run_step {"step": 0} → 400 | ✅ PASS |
| 6 | POST /api/run_step {"step": -1} → 400 | ✅ PASS |
| 7 | POST /api/run_step {"step": "abc"} → 400 | ✅ PASS |
| 8 | Tee._real=None 时 write/flush 不崩溃 | ✅ PASS |

## 环境

- Python 3.13.1, pytest 8.3.4
- macOS Darwin 23.6.0
- 运行耗时：16.84s
