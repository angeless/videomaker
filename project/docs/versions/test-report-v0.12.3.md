# 测试报告 — R3 视觉分析通道

**日期：** 2026-03-22
**任务：** R3
**版本：** v0.12.3

---

## 测试结果

| 测试类型 | 用例数 | 通过 | 失败 | 跳过 |
|---------|--------|------|------|------|
| R3 VisionMixin 测试 | 11 | 11 | 0 | 0 |
| 全量回归 | 886 | 836 | 0 | 50 |

## R3 测试明细

| # | 用例 | 结果 |
|---|------|------|
| 1 | test_is_available_returns_bool | ✅ |
| 2 | test_encode_text_returns_none_when_unavailable | ✅ |
| 3 | test_encode_image_returns_none_when_unavailable | ✅ |
| 4 | test_index_asset_visual_adds_to_index | ✅ |
| 5 | test_index_stores_in_db | ✅ |
| 6 | test_index_no_clip_returns_zero | ✅ |
| 7 | test_visual_search_returns_matches | ✅ |
| 8 | test_visual_search_aggregates_frames | ✅ |
| 9 | test_visual_search_no_clip_returns_empty | ✅ |
| 10 | test_visual_search_empty_query_returns_empty | ✅ |
| 11 | test_refresh_loads_from_db | ✅ |

## 环境

- Python 3.13.1, pytest 8.3.4
- macOS Darwin 23.6.0
- 运行耗时: 18.78s
