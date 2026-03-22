# R11 实施计划：产品体验修复批次

**版本：** v0.12.11
**日期：** 2026-03-22
**基线 Commit：** d5c6e09

---

## 1. 修复范围（6 项高价值修复）

### Fix-1: API 错误响应标准化
将 `str(exc)` 裸露异常替换为用户友好消息，统一错误格式。

### Fix-2: 前端 API 调用错误处理
`IngestPanel.vue` 等组件调用 API 无错误反馈 → 添加 toast 通知。

### Fix-3: 隐藏未实现功能入口
云端导入 tab "即将支持" 按钮 + 空设置 tab → 隐藏或标记 beta。

### Fix-4: API 参数验证加固
`target_duration_s`、`offset`、`limit` 等关键参数加范围验证。

### Fix-5: 关键 JSON 解析静默失败修复
`legacy_project_routes.py` 中 script/materials 解析失败静默返回空 → 返回错误。

### Fix-6: friendlyErrorMessage 在前端真正消费
`api.js` 已有错误转换但调用方未使用 → 确保 catch 显示 toast。

## 2. 不做什么
- 不改架构
- 不改业务逻辑
- 不增加新功能
- 不重构代码结构

## 3. 验收标准

| # | 标准 |
|---|------|
| AC-1 | API 错误响应不暴露 Python traceback |
| AC-2 | 前端 API 失败时显示 toast 通知 |
| AC-3 | 未实现功能不在 UI 中显示 |
| AC-4 | 参数越界返回 400 而非 500 |
| AC-5 | JSON 解析失败返回明确错误 |
| AC-6 | 现有测试不被破坏 |
