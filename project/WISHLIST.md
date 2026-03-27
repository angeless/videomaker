# VideoEditor — 衍生建议与改进愿望清单

> 本文件收集开发过程中发现的计划外改进机会。
> 仅记录，不执行。纳入正式开发计划后方可执行。
> Phase 7 衍生建议检查时追加到本文件。

## 格式说明

每条建议包含：
- **ID**: W-NNN（自增编号）
- **来源**: 发现于哪个版本/任务
- **描述**: 改进内容
- **优先级**: 高 / 中 / 低
- **状态**: 待评估 / 已纳入计划(vX.Y) / 已拒绝(原因)

---

## 建议列表

### W-001: 可视化时间线编辑器 v1
- **来源**: roadmap_v2.0.md Phase 3
- **描述**: 轨道视图（视频/字幕/音频）+ 拖拽裁剪 + 吸附
- **优先级**: 高
- **状态**: 待评估

### W-002: 退化行为显式通知
- **来源**: roadmap_v2.0.md S1
- **描述**: 渲染/磨皮/字幕模块退化时写 Toast 通知 + 审计日志
- **优先级**: 高
- **状态**: 待评估

### W-003: recovery_hint 前端完整消费
- **来源**: roadmap_v2.0.md S2
- **描述**: publish 失败时展示结构化错误摘要 + rerun_scope 操作按钮
- **优先级**: 中
- **状态**: 待评估

### W-004: 真实平台发布 connector
- **来源**: next_dev_plan.md Phase 1.1
- **描述**: YouTube/小红书/抖音/微信视频号官方适配器
- **优先级**: 高
- **状态**: 待评估

### W-005: 美颜与审美增强 v2
- **来源**: roadmap_v2.0.md Phase 3
- **描述**: 人脸区域分级磨皮、肤色保护、场景 LUT 预设、A/B 对比预览
- **优先级**: 中
- **状态**: 待评估

### W-006: VectorIndex compact 自动触发
- **来源**: v0.12.2 R2
- **描述**: VectorIndex.remove() 使用 lazy deletion，deleted 集合超过 20% 时 `needs_compact` 为 True，但目前无自动 compact 触发机制。建议在 `_refresh_vector_cache` 中检测并自动 rebuild。
- **优先级**: 低
- **状态**: 待评估

### W-007: FAISS IndexIVFFlat 大规模升级路径
- **来源**: v0.12.2 R2
- **描述**: 当前使用 IndexFlatIP（精确搜索），资产超过 100k 时性能下降。未来可增加 IndexIVFFlat 自动切换策略：<10k 用 Flat，>10k 自动训练 IVF。
- **优先级**: 低
- **状态**: 待评估

### W-008: 向量索引增量持久化优化
- **来源**: v0.12.2 R2
- **描述**: 当前每次 rebuild 后全量 save。对于增量 add 场景，可考虑 WAL-style 增量日志，减少大索引的写入开销。
- **优先级**: 低
- **状态**: 待评估

### W-009: CLIP 模型热插拔 + 多模型支持
- **来源**: v0.12.3 R3
- **描述**: 当前硬编码 clip-vit-base-patch32。未来可支持 clip-vit-large-patch14 等更大模型（768 维），需要索引维度自适应。
- **优先级**: 低
- **状态**: 待评估

### W-010: 素材入库时自动触发视觉索引
- **来源**: v0.12.3 R3
- **描述**: 当前 `index_asset_visual()` 需要显式调用。应在 `ingest_local_images` 流程中自动触发 CLIP 索引（如果可用）。
- **优先级**: 中
- **状态**: 待评估

### W-011: MCP Server 模块
- **来源**: 竞品研究 davinci-resolve-mcp (2026-03-24)
- **描述**: 新增 `modules/mcp_server/` 模块，用 FastMCP 封装现有 Agent API（agent_capability_routes、agent_skill_routes、agent_task_run_routes、workflow_routes 等），将 VideoEditor 暴露为标准 MCP Server。上线前需对写/输出类工具加路径白名单保护，禁止 MCP 工具触发任何删除操作。
- **优先级**: 高
- **状态**: 待评估

### W-012: 剪映草稿导出适配器
- **来源**: 竞品研究 davinci-resolve-mcp (2026-03-24)
- **描述**: Step 6（粗剪）完成后，可选输出剪映草稿格式（draft_content.json + 草稿文件夹），用户拖入剪映专业版直接打开，时间线、字幕、分段全部就位，只需做最后精调。草稿格式基于社区逆向工程的 JSON 结构，需关注剪映版本兼容性。
- **优先级**: 中
- **状态**: 待评估

### W-013: Final Cut Pro FCPXML 导出适配器
- **来源**: 竞品研究 davinci-resolve-mcp (2026-03-24)
- **描述**: Step 6（粗剪）完成后，可选输出 FCPXML 格式，用户在 Final Cut Pro 中直接打开，时间线完整呈现。FCPXML 为 Apple 官方文档化的项目交换格式，稳定性优于剪映草稿，且 Premiere Pro 等工具也可导入，具备一定通用性。
- **优先级**: 低
- **状态**: 待评估
