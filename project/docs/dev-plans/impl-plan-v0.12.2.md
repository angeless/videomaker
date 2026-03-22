# R2 实施计划 — 语义分析基础设施（增量增强）

**任务版本号**: v0.12.2
**所属功能项**: v0.12.0 — 语义分析基础设施
**制定日期**: 2026-03-22
**基线 commit**: 8f97812

---

## 1. 需求确认

**目标**: 将当前分散在 `core_mixin.py`（5970 行）中的向量搜索基础设施提取到独立的 `modules/library/semantic/` 子模块，并将 NumPy 暴力搜索替换为 FAISS 索引，提升搜索性能和可维护性。

**输入**:
- 现有 `core_mixin.py` 中的向量缓存/搜索相关代码（约 120 行）
- 现有 `asset_embeddings` 表中的 1536 维 OpenAI 嵌入向量
- 现有的查询嵌入缓存机制

**输出**:
- `modules/library/semantic/` 子模块，包含独立的向量索引引擎
- FAISS 索引文件（持久化到磁盘），替代内存 NumPy 矩阵
- `core_mixin.py` 中搜索相关方法委托给新模块
- 全部现有搜索行为零变更（接口兼容）

**验收标准**:
- [ ] `modules/library/semantic/` 目录结构完整，含 `__init__.py`、`vector_index.py`、`embedding_cache.py`
- [ ] FAISS 索引支持增量 add/remove，不需要全量重建
- [ ] 当 FAISS 不可用时（未安装），自动降级为 NumPy 暴力搜索（现有逻辑）
- [ ] `_vector_search()` 接口签名不变，返回值格式不变
- [ ] `_refresh_vector_cache()` 替换为 FAISS 索引刷新
- [ ] 查询嵌入缓存从 `core_mixin.py` 迁移到 `embedding_cache.py`
- [ ] 全量回归测试通过率 100%（排除已知 skip）
- [ ] FAISS 索引文件持久化到 `{library_dir}/cache/faiss/` 目录
- [ ] 新增单元测试覆盖 FAISS 索引的 CRUD、降级、持久化

## 2. 架构设计

### 2.1 模块布局

```
modules/library/semantic/
├── __init__.py              # 公共接口导出
├── vector_index.py          # VectorIndex 类：FAISS 索引管理（增量更新、持久化、搜索）
└── embedding_cache.py       # EmbeddingCache 类：查询嵌入 LRU 缓存
```

### 2.2 核心类设计

```python
# vector_index.py
class VectorIndex:
    """向量索引引擎，FAISS 优先，NumPy 降级。"""

    def __init__(self, dimension: int = 1536, index_dir: Optional[Path] = None):
        """初始化索引，尝试加载已有 FAISS 索引文件。"""

    def add(self, uid: str, vector: List[float]) -> None:
        """增量添加单条向量。"""

    def remove(self, uid: str) -> None:
        """移除单条向量。"""

    def search(self, query_vector: List[float], top_k: int = 1200,
               threshold: float = 0.08) -> Dict[str, float]:
        """搜索最近邻，返回 {uid: similarity_score}。"""

    def rebuild(self, uids: List[str], vectors: np.ndarray) -> None:
        """全量重建索引（首次加载或数据不一致时）。"""

    def save(self) -> None:
        """持久化索引到磁盘。"""

    def load(self) -> bool:
        """从磁盘加载索引，返回是否成功。"""

    @property
    def count(self) -> int:
        """当前索引中的向量数量。"""
```

```python
# embedding_cache.py
class EmbeddingCache:
    """查询嵌入 LRU 缓存。"""

    def __init__(self, max_size: int = 128, ttl_seconds: int = 3600):
        """初始化缓存。"""

    def get(self, query: str) -> Optional[List[float]]:
        """获取缓存的查询嵌入。"""

    def put(self, query: str, embedding: List[float]) -> None:
        """缓存查询嵌入。"""

    def clear(self) -> None:
        """清空缓存。"""
```

### 2.3 与现有系统的集成

- `core_mixin.py` 中 `_vector_search()` 内部委托给 `VectorIndex.search()`
- `_refresh_vector_cache()` 替换为 `VectorIndex.rebuild()` 或增量同步
- `_invalidate_vector_cache()` 调用 `VectorIndex` 清理
- `_get_query_embedding()` 中的缓存逻辑迁移到 `EmbeddingCache`
- `GlobalMediaLibrary.__init__()` 中初始化 `VectorIndex` 和 `EmbeddingCache` 实例

### 2.4 FAISS 索引策略

- **索引类型**: `IndexFlatIP`（内积，对归一化向量等价于余弦相似度）
- **UID 映射**: 维护 `uid_to_idx: Dict[str, int]` + `idx_to_uid: List[str]` 双向映射
- **增量更新**: add 直接追加；remove 标记为删除，定期 compact（或 rebuild 时清理）
- **持久化**: `faiss.write_index()` / `faiss.read_index()` + JSON 映射文件
- **降级**: `try: import faiss` 失败时使用 NumPy 实现（保持现有行为）

## 3. 文件清单

| 文件路径 | 类型 | 操作 | 行数估计 |
|---------|------|------|---------|
| `modules/library/semantic/__init__.py` | Python | 新增 | ~15 行 |
| `modules/library/semantic/vector_index.py` | Python | 新增 | ~200 行 |
| `modules/library/semantic/embedding_cache.py` | Python | 新增 | ~60 行 |
| `modules/library/core/core_mixin.py` | Python | 修改 | ~-80/+30 行（提取+委托） |
| `modules/library/global_media_library.py` | Python | 修改 | ~+10 行（初始化语义模块） |
| `modules/library/_constants.py` | Python | 修改 | ~+5 行（FAISS 相关常量） |
| `tests/test_vector_index.py` | Python | 新增 | ~150 行 |
| `tests/test_embedding_cache.py` | Python | 新增 | ~80 行 |
| **总计** | — | — | **~550 行** |

## 4. 实施步骤

### Step 1: 创建 `semantic/` 子模块骨架
- 新建 `modules/library/semantic/__init__.py`
- 新建 `embedding_cache.py`，从 `core_mixin.py` 提取查询缓存逻辑

### Step 2: 实现 `VectorIndex` 核心类
- FAISS 索引管理（IndexFlatIP）
- UID 双向映射
- 增量 add/remove
- 降级到 NumPy 暴力搜索

### Step 3: 实现持久化与加载
- `save()` / `load()` 方法
- 索引文件路径管理
- 自动恢复（加载失败时 rebuild）

### Step 4: 集成到 `core_mixin.py`
- `_vector_search()` 委托给 `VectorIndex.search()`
- `_refresh_vector_cache()` 替换为索引同步逻辑
- `_invalidate_vector_cache()` 更新
- `_get_query_embedding()` 使用 `EmbeddingCache`

### Step 5: 更新 `GlobalMediaLibrary` Facade
- `__init__()` 中初始化 `VectorIndex` 和 `EmbeddingCache`
- 确保实例变量在 Mixin 间可访问

### Step 6: 编写测试
- `test_vector_index.py`: FAISS add/remove/search/persist/降级
- `test_embedding_cache.py`: LRU 淘汰、TTL 过期、命中/未命中
- 运行全量回归确保无破坏

## 5. 测试策略

**单元测试：**
- `test_vector_index_add_search`: 添加向量后搜索返回正确结果
- `test_vector_index_remove`: 移除后不再出现在搜索结果
- `test_vector_index_persist_load`: 持久化后重新加载，搜索结果一致
- `test_vector_index_numpy_fallback`: 无 FAISS 时降级为 NumPy 搜索
- `test_vector_index_rebuild`: 全量重建后搜索正确
- `test_vector_index_empty`: 空索引搜索返回空字典
- `test_embedding_cache_hit_miss`: 缓存命中返回向量，未命中返回 None
- `test_embedding_cache_ttl`: TTL 过期后返回 None
- `test_embedding_cache_lru`: 超过 max_size 时淘汰最旧条目

**回归测试：**
- 运行全量 `ci_verify.sh`，确认搜索行为零变更

## 6. 风险预判

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| FAISS 未安装在用户环境 | 高 | 中 | 降级为 NumPy（保持现有行为），FAISS 作为可选依赖 |
| `core_mixin.py` 提取时引入回归 | 中 | 高 | 保持接口签名不变，全量回归测试 |
| FAISS 索引文件损坏 | 低 | 中 | 加载失败时自动 rebuild from DB |
| 增量 remove 导致索引碎片化 | 低 | 低 | remove 使用标记删除，rebuild 时清理 |

## 7. 依赖和前置条件

- R1 已完成 ✅
- `faiss-cpu` 作为可选依赖添加到 `requirements.txt`
- 不依赖任何外部 API（FAISS 纯本地运算）

## 8. 禁止修改文件核对

以上文件均不在 Tier 1 保护清单中。✅
