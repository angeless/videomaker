# R3 实施计划 — 视觉分析通道

**任务版本号**: v0.12.3
**所属功能项**: v0.12.0 — 视觉分析通道
**制定日期**: 2026-03-22
**基线 commit**: bbba374

---

## 1. 需求确认

**目标**: 创建视觉分析管道，将 CLIP 视觉嵌入（512 维）集成到 Library 的 VectorIndex 中，实现跨模态图文搜索。

**当前状态**:
- `step1_material_analysis/indexer/semantic.py` 有独立的 CLIP 索引（SemanticIndex），存 JSON 文件，与 Library 完全隔离
- Library 的 VectorIndex（R2 新增）用于 1536 维 OpenAI 文本嵌入
- 两个嵌入空间不兼容（512 vs 1536），不能共用同一个 VectorIndex

**关键架构决策**: 需要**第二个 VectorIndex 实例**（dim=512）专门用于 CLIP 视觉嵌入，与现有的文本嵌入 VectorIndex（dim=1536）并行存在。

**验收标准**:
- [ ] Library 初始化第二个 VectorIndex（dim=512，`cache/faiss_clip/`）
- [ ] 新增 `VisionMixin` 在 `modules/library/vision/` 下，封装 CLIP 编码和关键帧提取
- [ ] 素材入库时自动提取关键帧并生成 CLIP 嵌入存入视觉 VectorIndex
- [ ] `search_assets()` 支持 `retrieval_mode="visual"` — 用 CLIP 文本编码搜索视觉索引
- [ ] CLIP 不可用时（torch 未安装）降级为纯文本搜索，无报错
- [ ] 现有搜索行为零变更（hybrid/keyword/vector 模式不受影响）
- [ ] 全量回归测试通过
- [ ] 新增测试覆盖视觉索引 CRUD + CLIP 降级

## 2. 架构设计

### 2.1 模块布局

```
modules/library/vision/
├── __init__.py              # 公共接口导出
├── vision_mixin.py          # VisionMixin: CLIP 编码 + 关键帧提取 + 视觉搜索
└── clip_encoder.py          # CLIPEncoder 封装（从 semantic.py 提取，统一入口）
```

### 2.2 核心类设计

```python
# clip_encoder.py
class CLIPEncoder:
    """Lazy-loading CLIP encoder for image and text embedding."""

    DIMENSION = 512

    def encode_image(self, image) -> Optional[List[float]]:
        """Encode a PIL image or numpy BGR array → 512-dim vector."""

    def encode_text(self, text: str) -> Optional[List[float]]:
        """Encode text query → 512-dim vector (for cross-modal search)."""

    @staticmethod
    def is_available() -> bool:
        """Check if torch + transformers + CLIP are available."""
```

```python
# vision_mixin.py
class VisionMixin:
    """Mixin adding visual search capability to GlobalMediaLibrary."""

    def _extract_clip_embeddings(self, video_path: str, num_frames: int = 3) -> List[List[float]]:
        """Extract keyframes and encode with CLIP."""

    def _index_asset_visual(self, conn, uid: str, video_path: str) -> int:
        """Index a single asset's visual embeddings into _visual_index."""

    def _visual_search(self, query: str, top_k: int = 50) -> Dict[str, float]:
        """Search visual index using CLIP text encoding."""
```

### 2.3 与现有系统的集成

**双索引架构**:
```
GlobalMediaLibrary.__init__():
  self._vector_index = VectorIndex(dim=1536, index_dir=.../cache/faiss/)      # 文本嵌入（R2）
  self._visual_index = VectorIndex(dim=512,  index_dir=.../cache/faiss_clip/) # 视觉嵌入（R3）
  self._embedding_cache = EmbeddingCache()    # 查询嵌入缓存（R2）
  self._clip_encoder = None                    # lazy CLIPEncoder（R3）
```

**搜索路由扩展** (`search_assets`):
- `retrieval_mode="hybrid"` — 现有行为不变（FTS + 文本向量 + 标签）
- `retrieval_mode="visual"` — CLIP 文本编码 → 搜索 _visual_index → 返回视觉匹配
- `retrieval_mode="fusion"` — 未来 R6 实现，合并文本+视觉+标签

**UID 方案**: 视觉索引中的 UID = `{asset_uid}_f{frame_index}`（如 `abc123_f0`, `abc123_f1`），搜索结果按 asset_uid 聚合取最高分。

### 2.4 数据库扩展

新增表 `asset_visual_embeddings`:
```sql
CREATE TABLE IF NOT EXISTS asset_visual_embeddings (
    uid TEXT NOT NULL,
    frame_index INTEGER NOT NULL,
    model TEXT NOT NULL DEFAULT 'clip-vit-base-patch32',
    embedding_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (uid, frame_index)
);
```

## 3. 文件清单

| 文件路径 | 类型 | 操作 | 行数估计 |
|---------|------|------|---------|
| `modules/library/vision/__init__.py` | Python | 新增 | ~10 行 |
| `modules/library/vision/clip_encoder.py` | Python | 新增 | ~100 行 |
| `modules/library/vision/vision_mixin.py` | Python | 新增 | ~180 行 |
| `modules/library/global_media_library.py` | Python | 修改 | ~+15 行 |
| `modules/library/db/schema.py` | Python | 修改 | ~+15 行 |
| `modules/library/_constants.py` | Python | 修改 | ~+5 行 |
| `modules/library/core/core_mixin.py` | Python | 修改 | ~+20 行（搜索路由） |
| `tests/test_vision_mixin.py` | Python | 新增 | ~150 行 |
| **总计** | — | — | **~495 行** |

## 4. 实施步骤

### Step 1: 创建 `vision/` 子模块骨架 + CLIPEncoder
- 新建 `modules/library/vision/`
- 实现 `clip_encoder.py`：从 `semantic.py` 提取 CLIPEncoder，统一接口
- try/import 降级逻辑

### Step 2: 实现 VisionMixin
- 关键帧提取 → CLIP 编码 → VectorIndex add
- 视觉搜索：CLIP 文本编码 → VectorIndex search → 按 asset_uid 聚合

### Step 3: 数据库扩展
- `asset_visual_embeddings` 表
- SchemaMixin 中添加迁移

### Step 4: 集成到 Facade
- 第二个 VectorIndex 实例（dim=512）
- VisionMixin 加入 MRO
- `search_assets()` 增加 `visual` 路由

### Step 5: 编写测试
- CLIPEncoder mock 测试（不依赖真实 CLIP 模型）
- VisionMixin 索引 + 搜索测试
- 降级测试（无 CLIP 时不报错）
- 全量回归

## 5. 测试策略

**单元测试（mock CLIP）：**
- `test_clip_encoder_not_available`: 无 torch 时 `is_available()` 返回 False
- `test_visual_index_add_search`: mock CLIP 编码 → 添加到视觉索引 → 搜索匹配
- `test_visual_search_aggregation`: 多帧匹配同一资产，取最高分
- `test_visual_search_no_clip`: CLIP 不可用时返回空结果
- `test_visual_embeddings_persist`: 视觉嵌入存入 SQLite

**回归测试：**
- 运行全量 `ci_verify.sh`

## 6. 风险预判

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| CLIP 模型下载慢/不可用 | 中 | 中 | 延迟加载 + 降级为纯文本搜索 |
| 关键帧提取 cv2 资源泄漏 | 低 | 高 | try/finally cap.release() |
| 双索引内存压力 | 低 | 中 | 视觉索引独立持久化，按需加载 |
| MRO 冲突 | 低 | 高 | VisionMixin 不覆盖现有方法 |

## 7. 依赖和前置条件

- R2 已完成 ✅（VectorIndex 基础设施）
- torch + transformers 作为可选依赖（已在 requirements.txt）
- cv2 作为可选依赖（已存在）

## 8. 禁止修改文件核对

以上文件均不在 Tier 1 保护清单中。✅
