# VideoEditor v0.13.0 — Release Notes

**发布日期**: 2026-03-28
**基线版本**: v0.12.12
**任务数量**: 12 (R1-R12 全部完成)

---

## 核心主题

MCP AI 原生层 · 时间线多轨编辑 · 向量基础设施升级 · 导出适配器 · 美颜 v2 · 语义词库正式入库

## 新增功能

### 语义基础设施 (R1-R4)
- **种子词库正式入库** (R1): 2119 条语义种子词，12 大分类
- **退化行为显式通知** (R2): 3 类降级均有 Toast + 日志 + recovery_hint
- **素材入库自动视觉索引** (R3): 导入时自动触发 CLIP 索引
- **VectorIndex compact 自动触发** (R4): 删除 25% 后自动清理

### 前端体验 (R5, R7)
- **recovery_hint 前端消费** (R5): Modal + 操作按钮
- **可视化时间线 v1** (R7): 三轨视图、拖拽吸附、字幕联动

### 向量基础设施 (R6)
- **FAISS IndexIVFFlat** (R6a) / **WAL 持久化** (R6b) / **CLIP 热插拔** (R6c)

### 导出适配器 (R8-R9)
- **剪映草稿** (R8) + **FCPXML** (R9)

### 美颜 v2 (R10)
- 分级磨皮 + 肤色保护 + 5 LUT + A/B 预览

### MCP Server (R11)
- 12 工具 + 安全边界 + Claude Desktop 即插即用

## 质量数据

| 指标 | 数据 |
|------|------|
| 测试 | 1039 passed / 0 failures |
| CI 门禁 | 8/8 PASS |
| Phase 8 审计 | 3 CRITICAL 修复 / 架构合规 |

## 已知限制

- MCP Server 需 FastMCP (Python 3.10+)
- 美颜人脸检测依赖 mediapipe（可选，降级为中心区域）
- LUT 为 Python 生成，可替换专业 LUT
