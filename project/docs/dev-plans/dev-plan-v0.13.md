# VideoEditor v0.13.0 — 版本开发计划

> **文档版本**: V2.4（用户工作流研究整合：R11 已知约束补入 timeline_create / marker_add 两个高价值缺口工具的 Phase 1 评估项，引用 davinci-mcp 案例研究文档）
> **日期**: 2026-03-25
> **基线版本**: v0.12.12
> **核心主题**: MCP AI 原生层 · 时间线多轨编辑 · 向量基础设施升级 · 导出适配器 · 美颜 v2 · 语义词库正式入库

---

## 一、版本目标

**一句话**：为 VideoEditor 建立 MCP 接入层，升级时间线为多轨编辑器，修复降级可见性，完善向量基础设施，新增剪映/FCPXML 导出适配器，升级美颜模块，并将语义词库正式纳入仓库管理。

**明确排除**：W-004（真实平台发布 connector）本版本不做。

---

## 二、任务总览

| 任务 | 名称 | 对应版本 | 优先级 | 状态 |
|------|------|---------|--------|------|
| R1 | 种子词库验证 + 入库确认 | v0.13.1 | P0 | 🟡 待验证 |
| R2 | 退化行为显式通知（W-002） | v0.13.2 | P0 | ⬜ Planned |
| R3 | 素材入库自动触发视觉索引（W-010） | v0.13.3 | P1 | ⬜ Planned |
| R4 | VectorIndex compact 自动触发（W-006） | v0.13.4 | P1 | ⬜ Planned |
| R5 | recovery_hint 前端完整消费（W-003） | v0.13.5 | P1 | ⬜ Planned |
| R6a | FAISS IndexIVFFlat 升级路径（W-007） | v0.13.6 | P1 | ⬜ Planned |
| R6b | 向量索引增量 WAL 持久化（W-008） | v0.13.7 | P1 | ⬜ Planned |
| R6c | CLIP 模型热插拔（W-009） | v0.13.8 | P1 | ⬜ Planned |
| R7 | 可视化时间线编辑器 v1（W-001） | v0.13.9 | P1 | ⬜ Planned |
| R8 | 剪映草稿导出适配器（W-012） | v0.13.10 | P2 | ⬜ Planned |
| R9 | FCPXML 导出适配器（W-013） | v0.13.11 | P2 | ⬜ Planned |
| R10 | 美颜与审美增强 v2（W-005） | v0.13.12 | P2 | ⬜ Planned |
| R11 | MCP Server 模块（W-011） | v0.13.13 | P1 | ⬜ Planned |
| R12 | 集成测试 + 最终审计 | v0.13.14 | P0 | ⬜ Planned |

---

## 三、各任务详细定义

### R1：种子词库验证 + 入库确认

**目标**：确认重建的 2119 条种子 JSONL 存放于 `project/data/seeds/`，冷启动后 tag 库写入正常，不退化为 33 条最小集。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `project/data/seeds/semantic_keyword_library_flat.jsonl` | Verify（已预生成） |
| `modules/library/_constants.py` | Read-only（确认双路径逻辑） |
| `modules/library/db/schema.py` | Read-only（确认 seed 加载逻辑） |
| `.gitignore` | Modify（如有误排除） |

**输入**：已生成的 JSONL 文件（2119 行）

**输出**：应用冷启动后 tag 表记录数 ≥ 2100

**验收标准**：
- [ ] `wc -l project/data/seeds/semantic_keyword_library_flat.jsonl` ≥ 2100
- [ ] 每行合法 JSON，含 keyword/top_category/subcategory/kind/aliases 五字段
- [ ] 12 大类均有数据
- [ ] 清空 tag 表重启，tag 记录数 ≥ 2100（非 33 条）
- [ ] `.gitignore` 中无误排除 `project/data/seeds/`

**依赖项**：无
**已知约束**：`_constants.py` 已在 v0.12.12 确认正确，本 R 不修改

---

### R2：退化行为显式通知（W-002）

**目标**：所有 AI/渲染/处理能力发生降级时，前端展示 Toast 通知（含模块名+原因+降级路径），同时写结构化审计日志；消灭所有静默降级。

**涉及文件**：

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `modules/workflow_engine/workflow.py` | Modify | 3 处 `logger.warning` 退化点改为调用 `audit("degradation", ...)` 写入现有 SQLite |
| `modules/app_api/services/audit_log.py` | Read-only | 现有 `audit()` 基础设施已满足需求，不新增函数 |
| `modules/app_api/routes/system_routes.py` | Read-only | 现有 `GET /api/system/audit` 已可过滤降级记录，不新增端点 |
| `apps/desktop/ui-legacy/modules/runtime_mixin.js` | Modify | 新增 `showDegradationToast(event)` |
| `apps/desktop/ui-legacy/index.html` | Modify | 新增 Toast 组件（若现有不足展示结构化信息） |
| `tests/test_audit_log.py` | Modify | 新增降级日志测试 |

**输入**：降级事件 `{ module: str, reason: str, fallback_path: str, severity: "info"|"warning"|"error" }`

**输出**：
- 前端：3s 内 Toast（「[模块] 已降级：[原因] → 当前运行：[降级路径]」）
- 后端：调用 `audit("degradation", module, *, actor="workflow_engine", status="degraded", detail={"reason":..., "fallback_path":..., "severity":...})` 写入现有 SQLite
- API：`GET /api/system/audit?operation=degradation&limit=50` 返回最近 50 条（复用现有端点，不新增）

**验收标准**：
- [ ] 断开 API Key → Step 2 降级 → Toast 3s 内出现，展示模块名+原因
- [ ] 模拟 Step 3 解析失败 → Toast 可见
- [ ] CLIP 不可用 → Toast 可见
- [ ] 每次触发均写入日志，字段完整
- [ ] `GET /api/system/audit?operation=degradation` 返回 200，降级记录可见
- [ ] 正常路径无 Toast 干扰
- [ ] 新增测试通过

**依赖项**：无
**已知约束**：不改变降级本身的业务逻辑；Toast 复用现有 UI 组件；本 R 当前覆盖 `workflow.py` 中已确认的 3 处退化点（Step 2/Step 3/CLIP），目标"消灭所有静默降级"属于方向性表述，其他模块（如 `beauty.py`）若有退化点，待 R10 开发时按同一模式补充，不在本 R 范围内

---

### R3：素材入库自动触发视觉索引（W-010）

**目标**：`ingest_local_path` / `ingest_local_images` 完成后自动异步触发 CLIP 视觉索引；CLIP 不可用时静默跳过并触发 R2 降级通知。

**涉及文件**：

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `modules/library/core/core_mixin.py` | Modify | `ingest_local_path()` / `ingest_local_images()` 末尾异步调用 `_auto_visual_index()` |
| `modules/library/core/core_mixin.py` | Modify | 新增私有方法 `_auto_visual_index(uid_list: List[str])` |
| `modules/library/vision/vision_mixin.py` | Read→Modify | 确认 `index_asset_visual()` 签名；`_auto_visual_index` 调用它 |
| `modules/app_api/routes/library_routes.py` | Modify | 响应新增 `"visual_index_triggered": true/false` |
| `tests/test_capabilities.py` | Modify | 新增自动索引测试 |

**输入**：ingest 完成后的 uid_list

**输出**：
- 后台线程对每个 uid 调用 `index_asset_visual(uid)`
- CLIP 不可用时：写降级日志，不 crash
- API 响应新增字段 `visual_index_triggered`

**验收标准**：
- [ ] 导入 5 个视频 → 30s 内 CLIP 向量建立（`vector_index.count` 验证）
- [ ] 导入 10 张图片 → 同上
- [ ] CLIP 不可用：入库成功，降级 Toast 可见（R2 联动）
- [ ] 入库 API 响应含 `visual_index_triggered` 字段
- [ ] 异步不阻塞入库进度条
- [ ] 新增测试通过

**依赖项**：R2（降级通知须先就绪）
**已知约束**：大批量（>100 资产）时不加队列限流（v0.14 处理）

---

### R4：VectorIndex compact 自动触发（W-006）

**目标**：`VectorIndex._deleted` 比例 > 20% 时，下次缓存刷新自动调用 `rebuild()`，防止索引膨胀。

**涉及文件**：

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `modules/library/semantic/vector_index.py` | Modify | 新增 `compact_if_needed()`；在 `save()` 前或缓存刷新入口检查 `needs_compact` |
| `modules/library/global_media_library.py`（或调用方） | Modify | 缓存刷新处调用 `compact_if_needed()` |
| `tests/test_embedding_cache.py` | Modify | 新增 compact 触发测试 |

**输入**：`_deleted` 占 `_uid_to_pos` 总数 > 20% 时触发

**输出**：
- `compact_if_needed()` 满足条件时调用 `rebuild()`，清空 `_deleted`
- 日志：`logger.info("VectorIndex compact triggered: %d deleted / %d total")`

**验收标准**：
- [ ] 添加 10 向量，删 3（30%），刷新 → `_deleted` 变空集
- [ ] 添加 10 向量，删 1（10%），刷新 → `_deleted` 仍有 1（不触发）
- [ ] compact 后搜索结果与 compact 前一致
- [ ] 日志出现 `compact triggered`
- [ ] 新增测试通过

**依赖项**：无
**已知约束**：需确认 `rebuild()` 接口支持原地重建；`compact_if_needed()` 须在后台线程（`threading.Thread(daemon=True)`）中调用，不阻塞 `_refresh_cache()` 调用方；大索引 rebuild 预计 > 1s，compact 期间搜索仍使用旧索引；**Phase 1 须先确认挂载点**：`global_media_library.py` 当前无现成的 `_refresh_cache()` 或 compact hook 入口，实施前须先在 `vector_index.py` 的 `add_batch()` / `delete()` 末尾确认触发位置，再决定是直接在 `VectorIndex` 内部触发还是在 `global_media_library` 调用链中包装

---

### R5：recovery_hint 前端完整消费（W-003）

**目标**：publish 失败时展示结构化错误 Modal（含失败原因 + 对应「重新执行」按钮），消费后端已有的 `recovery_hint` 字段。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `modules/capabilities/content_publish.py` | Read-only（确认 recovery_hint 结构，lines 911-953） |
| `apps/desktop/ui-legacy/modules/semantic_publish_mixin.js` | Modify（publish 失败回调读取 recovery_hint） |
| `apps/desktop/ui-legacy/index.html` | Modify（新增「发布失败详情」Modal） |

**输入（后端响应示例）**：
```json
{
  "success": false,
  "recovery_hint": {
    "summary": "2/3 平台发布失败",
    "failed_step": "publish",
    "rerun_scope": "failed_only"
  }
}
```

**输出（按 rerun_scope 映射按钮）**：
- `"failed_only"` → 「重新发布失败平台」
- `"failed_and_blocked"` → 「重新发布所有失败项」
- `"fix_config_then_rerun"` → 「前往设置修复配置」
- `"none"` → 无重跑按钮

**验收标准**：
- [ ] `rerun_scope: "failed_only"` → Modal 展示，按钮文字正确
- [ ] `rerun_scope: "fix_config_then_rerun"` → 按钮点击跳转设置页
- [ ] `rerun_scope: "none"` → 无重跑按钮
- [ ] `success: true` → 不出现 Modal
- [ ] `recovery_hint` 字段缺失时 → 通用错误提示，不报 JS 错误

**依赖项**：无
**已知约束**：不新增后端端点；rerun 复用现有路由

---

### R6a：FAISS IndexIVFFlat 升级路径（W-007）

**目标**：向量数量 ≥ 10k 时自动切换 `IndexIVFFlat`（近似搜索）；< 10k 保持 `IndexFlatIP`（精确搜索）。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `modules/library/semantic/vector_index.py` | Modify（`_build_index()` 分支选择；新增 `_train_ivf()`） |
| `modules/library/_constants.py` | Modify（新增 `FAISS_IVF_THRESHOLD = 10000`，`FAISS_IVF_NLIST = 100`） |
| `tests/test_embedding_cache.py` | Modify |

**输入**：向量数量 N；训练集 = 随机采样 min(N, 39×nlist) 条

**输出**：
- N < 10k → `IndexFlatIP`，recall = 100%
- N ≥ 10k → `IndexIVFFlat`，recall ≥ 95%

**验收标准**：
- [ ] N = 100 → `type(index).__name__ == "IndexFlatIP"`
- [ ] Mock N = 15000 → `type(index).__name__ == "IndexIVFFlat"`
- [ ] IVF 模式 top-5，与 FlatIP 重合率 ≥ 4/5
- [ ] 训练样本不足时，fallback FlatIP + warning 日志
- [ ] 新增测试通过

**依赖项**：无
**已知约束**：IVF 需先 train 才能 add；rebuild 时若切换模式需重新 train

---

### R6b：向量索引增量 WAL 持久化（W-008）

**目标**：引入 WAL 记录增量 add，避免大索引每次全量 save；重启后 replay WAL 恢复未合并的向量。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `modules/library/semantic/vector_index.py` | Modify（新增 `_wal_path`；`add_batch()` 写 WAL；`load()` replay WAL；新增 `checkpoint()`） |
| `modules/library/_constants.py` | Modify（新增 `VECTOR_WAL_FILENAME = "vector_wal.jsonl"`） |
| `tests/test_embedding_cache.py` | Modify |

**输入**：`add_batch(uid_vec_pairs: List[Tuple[str, np.ndarray]])` 调用时，每个 `(uid, vec)` 对作为一条 WAL 记录；单条向量为 512 维 float32（约 3KB 编码后）

**WAL 行格式**：`{"op": "add", "uid": "xxx", "vec_b64": "..."}`

**输出**：
- `add_batch()` 后 WAL 文件追加写入，单条 < 10ms
- 重启后 replay WAL，索引可搜索到 WAL 中的向量
- `checkpoint()` 后 WAL 清空，主索引更新

**验收标准**：
- [ ] `add_batch([("uid1", vec)])` → WAL 新增 1 行含 uid
- [ ] 模拟重启（重新 `load()`）→ uid1 可搜索
- [ ] `checkpoint()` 后 WAL 为空，主索引已更新
- [ ] 单条 WAL 写入 < 10ms（10 次平均）
- [ ] 新增测试通过

**依赖项**：R6a
**已知约束**：向量 base64 编码，512 维 float32 约 3KB/行；不实现 WAL 压缩

---

### R6c：CLIP 模型热插拔 + 多模型支持（W-009）

**目标**：将硬编码 `clip-vit-base-patch32`（512 维）改为可配置；索引维度动态推断；支持模型切换后自动提示重建。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `modules/library/_constants.py` | Modify（新增 `DEFAULT_CLIP_MODEL = "openai/clip-vit-base-patch32"`；`DEFAULT_CLIP_DIM` 改动态） |
| `modules/library/vision/clip_encoder.py` | Modify（构造函数接受 `model_id`；暴露 `self.dim`） |
| `modules/library/semantic/vector_index.py` | Modify（dim 从 CLIPEncoder.dim 动态获取；存档 model_id） |
| `modules/app_api/routes/settings_routes.py` | Modify（新增 `GET/POST /api/settings/clip-model`） |
| `apps/desktop/ui-legacy/modules/settings_mixin.js` | Modify（模型选择 UI + 切换警告） |
| `tests/test_embedding_cache.py` | Modify |

**输入**：`POST /api/settings/clip-model { "model_id": "openai/clip-vit-large-patch14" }`；或直接修改配置文件中 `DEFAULT_CLIP_MODEL` 值后重启

**输出**：
- `GET /api/settings/clip-model` → `{ "model_id": "...", "dim": int }`
- `POST /api/settings/clip-model` → `{ "success": true }`（持久化到设置文件）
- 设置页：模型选择下拉 + 切换警告弹窗（"切换后需重建索引"）

**可用模型（2 个）**：`openai/clip-vit-base-patch32`（512），`openai/clip-vit-large-patch14`（768）

**验收标准**：
- [ ] `GET /api/settings/clip-model` 返回当前模型 ID + dim
- [ ] `POST /api/settings/clip-model` 持久化到设置文件
- [ ] 切换 large-patch14 重启后，dim 变 768，索引以 768 维创建
- [ ] 旧 512 维索引被自动弃用（warning 日志，不 crash）
- [ ] 设置页展示切换警告文案
- [ ] 新增测试通过

**依赖项**：R6a
**已知约束**：模型下载须联网；失败时保持原模型

---

### R7：可视化时间线编辑器 v1（W-001）

**目标**：Step 6 新增三轨视图（视频/字幕/音频），支持吸附（snap ±8px）、字幕联动视频移动、音频轨独立裁剪。（基于 v0.12 R7 单轨拖拽扩展，不重写）

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `apps/desktop/ui-legacy/modules/project_workflow_mixin.js` | Modify（`timelineState.tracks` 三轨数据结构；`initTimeline()` 三轨初始化） |
| `apps/desktop/ui-legacy/index.html` | Modify（Step 6 区块三轨 HTML 布局） |
| `apps/desktop/ui-legacy/styles.css` | Modify（三轨样式：轨道高度/标签/颜色） |
| `modules/app_api/routes/timeline_routes.py` | Modify（新增 `GET/PUT /api/timeline/{project_id}/tracks`；现有 `GET /api/timeline`、`POST /api/timeline/reorder` 等端点保持不变，新旧共存） |
| `modules/step6_rough_cut/rough_cut.py` | Read→轻度 Modify（确认输出含字幕段时间戳） |
| `tests/test_agent_api.py` | Modify |

**数据结构**：
```js
{
  video: [{ uid, start_ms, end_ms, label }],
  subtitle: [{ text, start_ms, end_ms }],
  audio: [{ label, start_ms, end_ms, volume }]
}
```

**轨道高度**：video 80px / subtitle 40px / audio 60px

**验收标准**：
- [ ] Step 6 展示三轨（含轨道标签 Video/Subtitle/Audio）
- [ ] 拖拽视频片段靠近边缘 8px 内 → 自动吸附，无缝隙
- [ ] 拖拽视频片段后字幕段位置联动更新
- [ ] 音频轨支持独立 trim（字幕不联动）
- [ ] `GET /api/timeline/{project_id}/tracks` 返回三轨 JSON
- [ ] `PUT` 保存后刷新页面状态恢复
- [ ] 新增测试通过

**依赖项**：无
**已知约束**：不实现 NLE 级多轨叠层；audio volume 字段仅存储，不做 UI 控制（留 v0.14）；⚠️ **风险提示**：新增 `GET/PUT /api/timeline/{project_id}/tracks` 引入了 `{project_id}` 路径参数，与现有 `GET /api/timeline`、`POST /api/timeline/reorder` 等无路径参数的端点风格不一致；Phase 1 须评估是否改用请求体传参风格，决策须在编码前确认，若决定变更接口须同步更新涉及文件表和验收标准

---

### R8：剪映草稿导出适配器（W-012）

**目标**：Step 6 完成后，新增「导出剪映草稿」入口，生成剪映专业版可打开的草稿包。

> 注：`step3/jianying_draft.py` 已有 `JianyingDraftBuilder`（用于脚本生成，定位不同），本 R 新建独立模块，不修改 step3 文件。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `modules/exporters/__init__.py` | Create |
| `modules/exporters/jianying/__init__.py` | Create |
| `modules/exporters/jianying/draft_builder.py` | Create（`JianyingExportBuilder`：timeline tracks → draft JSON） |
| `modules/exporters/jianying/schema.py` | Create（剪映 JSON Schema 常量，社区逆向 v5.x） |
| `modules/app_api/routes/capability_editing_routes.py` | Modify（新增 `POST /api/capabilities/jianying_export/run`） |
| `apps/desktop/ui-legacy/modules/editing_capabilities_mixin.js` | Modify（Step 6 导出按钮） |
| `tests/test_capabilities.py` | Modify |

**输入**：`POST /api/capabilities/jianying_export/run { "project_id": "xxx", "output_dir": "~/Desktop/VideoEditor-Drafts/" }`

**输出**：
- `~/Desktop/VideoEditor-Drafts/{name}/draft_content.json` + `draft_meta_info.json`
- API 响应：`{ "success": true, "data": { "draft_path": "..." }, "timestamp": "..." }`

**验收标准**：
- [ ] API 返回 200，`draft_path` 指向有效目录
- [ ] `draft_content.json` 可 `json.load()` 解析，含 tracks/materials/duration
- [ ] 草稿目录拷贝到剪映专业版 Projects 目录，可打开，时间线片段顺序正确
- [ ] 输出目录无写权限时，返回 4xx + 明确错误
- [ ] 前端按钮点击 → 成功提示 + 路径可见
- [ ] 新增测试通过

**依赖项**：R7（需三轨时间线数据）
**已知约束**：仅保证剪映专业版 Mac v5.x；素材用绝对路径（不内嵌）

---

### R9：FCPXML 导出适配器（W-013）

**目标**：Step 6 完成后，新增「导出 FCPXML」入口，生成 Final Cut Pro 1.9 格式 `.fcpxml`。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `modules/exporters/fcpxml/__init__.py` | Create |
| `modules/exporters/fcpxml/builder.py` | Create（`FCPXMLBuilder`：tracks → XML） |
| `modules/exporters/fcpxml/schema.py` | Create（FCPXML 1.9 结构常量） |
| `modules/app_api/routes/capability_editing_routes.py` | Modify（新增 `POST /api/capabilities/fcpxml_export/run`） |
| `apps/desktop/ui-legacy/modules/editing_capabilities_mixin.js` | Modify |
| `tests/test_capabilities.py` | Modify |

**输入**：`POST /api/capabilities/fcpxml_export/run { "project_id": "xxx", "output_path": "~/Desktop/xxx.fcpxml" }`

**输出**：
- FCPXML 1.9 文件：`<fcpxml version="1.9">` 根元素
- 每个视频片段 → `<asset-clip>`；字幕 → `<title>` clip
- API 响应：`{ "success": true, "data": { "fcpxml_path": "..." }, "timestamp": "..." }`

**验收标准**：
- [ ] API 返回 200，文件存在
- [ ] `xml.etree.ElementTree.parse()` 无报错
- [ ] 根元素 `<fcpxml version="1.9">`
- [ ] FCP 导入后，视频片段位置正确，字幕段出现
- [ ] 前端按钮点击 → 成功提示
- [ ] 新增测试通过

**依赖项**：R7
**已知约束**：单摄像机序列；不导出 LUT/效果；时间用 CMTime 格式（`s/d`）

---

### R10：美颜与审美增强 v2（W-005）

**目标**：在现有 `apply_beauty_filter()`（line 161，`beauty.py`）基础上新增：分级磨皮、肤色保护、5 组 LUT 预设、A/B 对比预览。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `modules/step7_final_render/beauty.py` | Modify（新增 `apply_regional_smooth()`, `apply_scene_lut()`, `skin_color_protect()`） |
| `modules/step7_final_render/luts/` | Create（5 个 `.cube` LUT 文件） |
| `modules/app_api/routes/capability_editing_routes.py` | Modify（新增 `POST /api/capabilities/beauty/preview`，`GET /api/capabilities/beauty/lut-presets`） |
| `apps/desktop/ui-legacy/modules/editing_capabilities_mixin.js` | Modify（A/B 预览 + LUT 选择） |
| `apps/desktop/ui-legacy/index.html` | Modify（美颜面板新增 LUT 下拉 + 分级强度 + A/B 区） |
| `tests/test_capabilities.py` | Modify |

**输入**：
- `POST /api/capabilities/beauty/preview { "frame_base64": "<base64>", "beauty_params": { "lut": "outdoor_natural" | null, "smooth_level": 0.0~1.0, "region_graded": true | false } }`
- `GET /api/capabilities/beauty/lut-presets`（无参数）

**输出**：
- `POST /api/capabilities/beauty/preview` → `{ "success": true, "data": { "result_base64": "...", "processing_ms": int }, "timestamp": "..." }`（500ms 内返回）
- `GET /api/capabilities/beauty/lut-presets` → `["outdoor_natural", "indoor_warm", "food", "night", "travel"]`
- `modules/step7_final_render/luts/*.cube` — 5 个新增 LUT 文件（Python 代码生成初版，可替换）

**LUT 预设**：`outdoor_natural`, `indoor_warm`, `food`, `night`, `travel`

**分级磨皮强度比**：额头 0.8× / 脸颊 1.0× / 下巴 0.6×（基于人脸检测区域）

**验收标准**：
- [ ] `POST /api/capabilities/beauty/preview` 在 500ms 内返回预览 base64
- [ ] A/B 预览：左原图/右效果，分界线可拖拽
- [ ] 分级磨皮：三区域强度差异可见，无锯齿边界
- [ ] 肤色保护：磨皮后肤色 HSV-S 通道变化 < 5%
- [ ] 5 个 LUT 可加载，产生可见色调差异
- [ ] `GET /api/capabilities/beauty/lut-presets` 返回 5 个名称
- [ ] 新增测试通过

**依赖项**：无
**已知约束**：人脸检测失败时 fallback 全图均匀磨皮；LUT `.cube` 文件来源：使用 Python 代码生成初版（`colour-science` 库或 numpy 手写线性映射 + 色调偏移），不满意可替换第三方免费 LUT（如 IWLTBAP、RocketStock 开源包），文件须在 R10 开发前就绪并提交仓库

---

### R11：MCP Server 模块（W-011）

**目标**：新建独立模块 `modules/mcp_server/`，FastMCP 封装现有 Agent API，暴露 12 个工具（7 工作流 + 5 能力）；安全边界：不暴露删除接口，路径写入限白名单。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `modules/mcp_server/__init__.py` | Create |
| `modules/mcp_server/server.py` | Create（FastMCP 主服务） |
| `modules/mcp_server/tools/workflow_tools.py` | Create（7 个工作流工具） |
| `modules/mcp_server/tools/capability_tools.py` | Create（5 个能力工具） |
| `modules/mcp_server/security.py` | Create（路径白名单；拒绝删除操作） |
| `modules/mcp_server/health.py` | Create（后端健康检查） |
| `modules/mcp_server/README.md` | Create（使用文档 + Claude Desktop 配置示例） |
| `requirements.txt` | Modify（新增 `fastmcp>=0.9`） |
| `tests/test_agent_api.py` | Modify |

**12 个工具**：

| 工具名 | 对应后端 API |
|--------|-------------|
| `video_step1_analyze` | `POST /api/agent/tasks/run` (analyze_materials) |
| `video_step2_plan` | `POST /api/agent/tasks/run` (topic_planning) |
| `video_step3_script` | `POST /api/agent/tasks/run` (script_generation) |
| `video_step4_match` | `POST /api/agent/tasks/run` (material_matching) |
| `video_step5_preview` | `POST /api/agent/tasks/run` (frame_preview) |
| `video_step6_cut` | `POST /api/agent/tasks/run` (rough_cut) |
| `video_step7_render` | `POST /api/agent/tasks/run` (final_render) |
| `library_search` | `POST /api/library/search` |
| `library_ingest` | `POST /api/library/ingest/local` |
| `project_list` | `GET /api/projects` |
| `project_create` | `POST /api/projects` |
| `workflow_run` | `POST /api/workflows/run` |

**安全规则**：写入路径仅允许 `~/Movies/VideoEditor/exports/`；`library_ingest` 的 source_path 禁止 `..` 穿越；不暴露任何 delete 接口。

**Lazy Connection**：每次工具调用时检查后端健康，离线返回可读错误（含启动指引），不 crash。

**验收标准**：
- [ ] `python -m modules.mcp_server.server` 启动无报错
- [ ] Claude Desktop 配置后，工具列表出现 12 个工具
- [ ] `video_step1_analyze` 调用成功，后端 API 被调用，返回 job_id
- [ ] `library_search` 返回 top-k 资产
- [ ] 删除类工具不在列表中
- [ ] `source_path` 含 `..` 时 `library_ingest` 返回权限错误
- [ ] 后端离线时，任意工具返回可读错误，不报 traceback
- [ ] 新增测试通过

**依赖项**：R2（降级通知须先就绪）
**已知约束**：FastMCP 需确认 Python 3.8 兼容性；若需 3.10+ 须另行评估；**⚠️ Phase 1 工具列表复审**：用户工作流研究（`docs/research/user-workflow-case-study-davinci-mcp.md`）发现 `timeline_create`（创建时间线）和 `marker_add`（时间点打标记）是粗剪阶段高频 MCP 操作，当前 12 工具未覆盖；两者均需新建后端端点（`POST /api/timeline/create`、`POST /api/timeline/markers`），目前不存在；Phase 1 须评估是否从 12 工具扩充至 14 工具，若扩充须同步新增后端端点并更新涉及文件表、验收标准和工具数量描述

---

### R12：集成测试 + 最终审计

**目标**：对 R1~R11 做完整集成验证，确认无 v0.12 核心路径回归，输出测试报告和审计记录。

**涉及文件**：

| 文件路径 | 操作 |
|---------|------|
| `tests/e2e/test_e2e_r1_seed.py` | Create |
| `tests/e2e/test_e2e_r2_degradation.py` | Create |
| `tests/e2e/test_e2e_r3_visual_index.py` | Create |
| `tests/e2e/test_e2e_r4_compact.py` | Create |
| `tests/e2e/test_e2e_r5_recovery.py` | Create |
| `tests/e2e/test_e2e_r6_vector.py` | Create |
| `tests/e2e/test_e2e_r7_timeline.py` | Create |
| `tests/e2e/test_e2e_r11_mcp.py` | Create |
| `project/docs/test-reports/2026-xx-xx-v0.13-test-report.md` | Create |
| `project/docs/audit/2026-xx-xx-v0.13-final-audit.md` | Create |
| `project/CHANGELOG.md` | Modify（[未发布] → [0.13.0]） |
| `project/VERSION` | Modify（0.13.0） |

**输入**：R1~R11 全部标记完成；执行 `bash scripts/ci_verify.sh` 触发集成验证流程

**输出**：
- `project/docs/test-reports/2026-xx-xx-v0.13-test-report.md`（Create）
- `project/docs/audit/2026-xx-xx-v0.13-final-audit.md`（Create）
- `project/CHANGELOG.md` — [未发布] → [0.13.0]
- `project/VERSION` → `0.13.0`

**验收矩阵**：

| 类别 | 测试点 | 通过标准 |
|------|--------|---------|
| R1 | 冷启动 tag 写入 | ≥ 2100 条 |
| R2 | 触发 3 类降级（Step2 / Step3 / CLIP） | 每次 Toast + 日志 |
| R3 | 导入 10 个文件 | 30s 内索引建立 |
| R4 | 删除 25% 再刷新 | `_deleted` 清空 |
| R5 | 模拟 publish 失败 | Modal + 按钮正确 |
| R6a | Mock 1.5w 向量 | IndexIVFFlat 生效 |
| R6b | add → 重启 → 搜索 | 向量可搜索 |
| R6c | 切换模型 → 重启 | dim 变更生效 |
| R7 | 拖拽 + 吸附 + 联动 | 3 项均可见 |
| R8 | 草稿 → FCP打开 | 时间线正确 |
| R9 | FCPXML → FCP导入 | 片段正确 |
| R10 | A/B + LUT + 分级 | 3 项均可用 |
| R11 | 12 工具 + 安全 | 全部通过 |
| 回归 | Step 1-7 全流程 | 无 v0.12 行为变化 |

**依赖项**：所有 R1~R11 完成

---

## 四、完成状态追踪

| 任务 | 计划周期 | 实际完成 | 备注 |
|------|---------|---------|------|
| R1 | 0.5 天 | — | 种子已预生成 |
| R2 | 3 天 | — | |
| R3 | 2 天 | — | |
| R4 | 1 天 | — | |
| R5 | 2 天 | — | |
| R6a | 2 天 | — | |
| R6b | 2 天 | — | |
| R6c | 2 天 | — | |
| R7 | 5 天 | — | 最复杂前端任务 |
| R8 | 3 天 | — | |
| R9 | 2 天 | — | |
| R10 | 3 天 | — | 含制作 5 个 LUT |
| R11 | 5 天 | — | 新建模块 |
| R12 | 2 天 | — | |
| **合计** | **~35 天** | — | |

---

## 五、风险登记

| 风险 | 等级 | 缓解策略 |
|------|------|---------|
| FastMCP Python 3.8 兼容性 | 高 | 先确认最低版本要求；若需 3.10+ 则评估升级代价 |
| 剪映草稿格式兼容性（非官方） | 中 | 注明版本限制；提供手动导入说明 |
| FAISS IVF 训练样本不足 | 中 | 保守阈值（10k）+ 不足自动 fallback FlatIP |
| 三轨时间线前端复杂度 | 中 | 严格限定 v1 范围，不做 NLE 级功能 |
| MCP 路径安全绕过 | 高 | R11 上线前独立安全测试（路径穿越/符号链接） |
| LUT 文件质量（自制） | 低 | 目视验收；不满意可用第三方免费 LUT 替换 |

---

## 六、变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| V1.0 | 2026-03-24 | 初版（版本目标 + 任务序列） |
| V2.0 | 2026-03-24 | 规范化重写：补全每 R 的涉及文件/输入/输出/验收标准/依赖/约束（§3.3） |
| V2.1 | 2026-03-25 | 评审修正：B1 R6b补输入 / B2 R6c补输入+输出 / B3 R10补输入+输出 / B4 R12补输入+输出；S1 R12 e2e文件具体化 / S2 R7端点共存说明 / S3 R10 LUT来源定义 / S4 R4异步约束明确 / S8 任务总览新增版本号列（v0.13.1~v0.13.14） |
| V2.2 | 2026-03-25 | 技术一致性修正：C1~C3 R2 删除 log_degradation/JSONL/新端点方案，改为复用 audit() + GET /api/system/audit；C4 R11 修正 4 条 API 路径（tasks/workflows/ingest/projects 复数/路径对齐）；C5 R8/R9 路由前缀改为 /api/capabilities/jianying_export(fcpxml_export)/run；C6 R10 路由前缀改为 /api/capabilities/beauty/...；C7 R7 补充 project_id 须通过请求体传入的约束；C8 R4 补充 Phase 1 须先确认挂载点的约束 |

| V2.3 | 2026-03-25 | 二次审查修正：R7 已知约束从强制改为风险提示（去除与涉及文件/验收标准的自相矛盾）；R8/R9/R10 响应格式补 data 包装 + timestamp（对齐 §4.3）；R12 验收矩阵 R2 行"4类"改"3类+明确类型"；R2 已知约束补充覆盖范围边界说明 |
| V2.4 | 2026-03-25 | 用户工作流研究整合：R11 已知约束补入 timeline_create / marker_add 两个高频缺口工具的 Phase 1 评估要求（来源：docs/research/user-workflow-case-study-davinci-mcp.md），标注对应后端端点尚不存在，须在扩充前新建 |
