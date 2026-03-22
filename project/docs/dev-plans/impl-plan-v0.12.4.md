# R4 实施计划 — 语音分析通道增强

**任务版本号**: v0.12.4
**所属功能项**: v0.12.0 — 语音分析通道增强
**制定日期**: 2026-03-22
**基线 commit**: 0aee2fc

---

## 1. 需求确认

**目标**: 将 ASR 转录文本纳入嵌入源，使语音内容可通过向量搜索被发现。

**当前缺口**:
- `analysis_json.asr_text` 存储了转录文本，但 `_build_embedding_source()` 不读取它
- 搜索无法匹配"视频中说了什么"

**验收标准**:
- [ ] `_build_embedding_source()` 接受 `analysis_json` 参数并提取 `asr_text`
- [ ] `_upsert_embedding_for_asset()` 传递 `analysis_json`
- [ ] `_refresh_embeddings_incremental()` SQL 查询包含 `analysis_json`
- [ ] 转录文本截断到 2000 字符，避免挤占其他语义信号
- [ ] 全量回归测试通过
- [ ] 新增测试验证转录文本被纳入嵌入源

## 2. 文件清单

| 文件 | 操作 | 变更说明 |
|------|------|---------|
| `modules/library/core/core_mixin.py` | 修改 | 3 个方法增强 |
| `tests/test_embedding_source.py` | 新增 | 转录纳入嵌入源测试 |

## 3. 禁止修改文件核对

以上文件均不在 Tier 1 保护清单中。✅
