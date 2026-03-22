# R5 实施计划 — 向量搜索引擎

**任务版本号**: v0.12.5
**所属功能项**: v0.12.0 — 向量搜索引擎
**制定日期**: 2026-03-22
**基线 commit**: 7db9c39

---

## 1. 需求确认

**目标**: 将 R2-R4 的向量搜索能力完整暴露到 API 层，补齐搜索引擎的端到端链路。

**当前缺口**:
- `/api/library/search` 不允许 `mode=visual`
- `count_matching_assets()` 不支持 `visual` 模式
- `stats()` 不报告视觉搜索状态
- 搜索结果不包含 `retrieval_mode` 实际使用信息

**验收标准**:
- [ ] `/api/library/search?mode=visual` 返回 CLIP 视觉搜索结果
- [ ] `count_matching_assets` 支持 visual 模式
- [ ] `stats()` 包含 `visual_search_enabled` 和 `visual_embeddings_count`
- [ ] 全量回归通过
- [ ] 新增 API 端点测试

## 2. 文件清单

| 文件 | 操作 | 变更说明 |
|------|------|---------|
| `modules/app_api/routes/library_routes.py` | 修改 | 允许 visual 模式 |
| `modules/library/core/core_mixin.py` | 修改 | count_matching_assets 支持 visual |
| `modules/library/global_media_library.py` | 修改 | stats() 增加视觉搜索状态 |
| `tests/test_search_api.py` | 新增 | API 端点测试 |

## 3. 禁止修改文件核对

以上文件均不在 Tier 1 保护清单中。✅
