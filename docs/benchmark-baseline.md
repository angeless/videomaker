# 渲染/发布链路 Benchmark 基线

更新时间：2026-03-01

## 1. 目标

本基线用于验证以下能力在本地桌面环境下的性能稳定性：

- `social_export` 的导出计划构建延迟
- `content_publish` 的 dry-run 计划与执行延迟
- （可选）`content_publish` 的 Blog 真实落盘发布延迟

脚本入口：`tools/benchmark_render_publish.py`

## 2. 运行方式

```bash
python tools/benchmark_render_publish.py --iterations 20 --include-live-blog
```

常用参数：

- `--iterations`: 每个场景迭代次数（建议 >=20）
- `--platforms`: 社媒导出平台列表（逗号分隔）
- `--output`: 报告输出路径
- `--include-live-blog`: 是否追加 blog 非 dry-run 发布测试

## 3. 验收阈值

默认阈值（见脚本 `acceptance.thresholds`）：

- `export_plan_p95_ms <= 250`
- `publish_dry_plan_p95_ms <= 120`
- `publish_dry_run_p95_ms <= 80`
- `publish_live_blog_p95_ms <= 220`（仅在开启 `--include-live-blog` 时校验）

说明：

- 该阈值基于“本地单机、无外部网络发布”的可重复测试口径。
- 如果 CI 或低配机器波动较大，优先看 `p95` 与 `max` 的相对变化趋势，而不是单次绝对值。

## 4. 报告结构

脚本会输出 JSON，关键字段：

- `benchmarks.social_export_plan.latency_ms`
- `benchmarks.content_publish_dry.plan_latency_ms`
- `benchmarks.content_publish_dry.run_latency_ms`
- `benchmarks.content_publish_live_blog.run_latency_ms`（可选）
- `acceptance.pass`
- `acceptance.checks`
- `acceptance.measured`

## 5. 建议门禁

建议在合并前至少满足：

- `acceptance.pass == true`
- 每个关键指标的 `p95` 相比主分支回退不超过 20%
- 若未通过，需在 PR 描述里标注退化原因与修复计划
