# 测试报告 — R2 语义分析基础设施（增量增强）

**日期：** 2026-03-22
**任务：** R2
**版本：** v0.12.2

---

## 测试结果

| 测试类型 | 用例数 | 通过 | 失败 | 跳过 |
|---------|--------|------|------|------|
| R2 VectorIndex 测试 | 18 | 18 | 0 | 0 |
| R2 EmbeddingCache 测试 | 11 | 11 | 0 | 0 |
| 全量回归 | 875 | 825 | 0 | 50 |

## R2 VectorIndex 测试明细

| # | 用例 | 结果 |
|---|------|------|
| 1 | test_add_and_search_returns_match | ✅ PASS |
| 2 | test_search_empty_index_returns_empty | ✅ PASS |
| 3 | test_search_respects_threshold | ✅ PASS |
| 4 | test_search_top_k_limits_results | ✅ PASS |
| 5 | test_add_replaces_existing | ✅ PASS |
| 6 | test_remove_excludes_from_search | ✅ PASS |
| 7 | test_remove_nonexistent_is_noop | ✅ PASS |
| 8 | test_rebuild_replaces_index | ✅ PASS |
| 9 | test_rebuild_invalid_shape_is_noop | ✅ PASS |
| 10 | test_save_and_load | ✅ PASS |
| 11 | test_load_nonexistent_dir | ✅ PASS |
| 12 | test_load_corrupted_meta | ✅ PASS |
| 13 | test_fallback_search_works (NumPy) | ✅ PASS |
| 14 | test_fallback_remove_works (NumPy) | ✅ PASS |
| 15 | test_empty_vector_rejected | ✅ PASS |
| 16 | test_wrong_dimension_rejected | ✅ PASS |
| 17 | test_zero_vector_rejected | ✅ PASS |
| 18 | test_needs_compact | ✅ PASS |

## R2 EmbeddingCache 测试明细

| # | 用例 | 结果 |
|---|------|------|
| 1 | test_put_and_get_returns_vector | ✅ PASS |
| 2 | test_get_miss_returns_none | ✅ PASS |
| 3 | test_normalizes_query | ✅ PASS |
| 4 | test_empty_query_returns_none | ✅ PASS |
| 5 | test_empty_embedding_not_stored | ✅ PASS |
| 6 | test_expired_entry_returns_none | ✅ PASS |
| 7 | test_fresh_entry_returns_vector | ✅ PASS |
| 8 | test_evicts_oldest_when_full | ✅ PASS |
| 9 | test_eviction_keeps_recent | ✅ PASS |
| 10 | test_clear_empties_cache | ✅ PASS |
| 11 | test_size_tracks_entries | ✅ PASS |

## 环境

- Python 3.13.1, pytest 8.3.4
- macOS Darwin 23.6.0
- FAISS: faiss-cpu (IndexFlatIP backend)
- 运行耗时: 19.60s
