# 测试报告 — v0.17.0 VLM 画笔分析引擎

**版本：** v0.17.0
**日期：** 2026-04-04
**分支：** feat/v0.17.0-vlm-analysis

## 测试结果摘要

| 指标 | 结果 |
|------|------|
| 新增测试 | 86 (44 unit + 12 diagnostics + 14 router/ref + 9 API + 7 integration/smoke) |
| 全量回归 | **1504 passed, 1 skipped, 0 failures** |
| 新增失败 | 0 |
| 审计修复后回归 | 1504 passed, 0 failures |

## 新增测试明细

### 单元测试 (75)

| 测试文件 | 测试数 | 覆盖 |
|---------|--------|------|
| test_vlm_adapter.py | 10 | VLMResponse, StubAdapter, factory |
| test_vlm_local_llava.py | 6 | LocalLlava availability, mock inference, lazy loading |
| test_vlm_api_adapter.py | 9 | OpenAI/Claude adapters, API key, mock HTTP |
| test_region_extractor.py | 6 | rect/circle/pen/arrow/multi-stroke/no-stroke |
| test_vlm_analyzer.py | 7 | structured output, text fallback, degradation, cache, Chinese prompt |
| test_review_store_vlm.py | 6 | migration, visual_context, ai_generated, filter, backward compat |
| test_intent_router_vlm.py | 5 | backward compat, visual context injection |
| test_reference_resolution.py | 9 | single ref, multi object, color issue, passthrough |
| test_frame_diagnostics.py | 12 | composition VLM, exposure, color temp, continuity |
| test_ai_reviewer.py | 4 | comment creation, time range, idempotent, severity |

### API 测试 (7)
| test_vlm_api.py | 7 | describe, diagnose, diagnostics list, status, error cases |

### 集成测试 (5)
| test_vlm_pipeline.py | 5 | e2e pipeline, degradation, API describe/diagnose, backward compat |

## 审计修复验证

| 审计项 | 修复 | 回归 |
|--------|------|------|
| #1 PIL HSV crash | RGB B-R ratio | PASS |
| #6 stroke key mismatch | _normalize_stroke() | PASS |
| #5 N+1 query | use returned comment_id | PASS |
| #7 destructive fallback | return [] | PASS |
| #2 weak cache key | 5-pixel sampling | PASS |

## 降级路径验证

| 场景 | 结果 |
|------|------|
| VLM adapter=None | 所有功能静默降级，不影响现有评审 |
| LLaVA 未安装 | factory 返回 None，不崩溃 |
| API key 未配置 | adapter.is_available()=False |
| 画笔无标注 | 返回整帧图像 |
| VLM 返回非 JSON | fallback 到 raw text 作为 summary |
