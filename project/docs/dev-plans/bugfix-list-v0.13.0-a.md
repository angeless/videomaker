# Bug 修复清单 v0.13.0-a

> 来源：UX 运行时测试报告（2026-03-25）§0.11 空闲循环扫描
> 创建时间：2026-03-28

## P0 Bug

### BF-001 前后端状态脱节（NEW-2）
- **表现**：UI 标题显示项目名，但后端 `GET /api/status → ready:false`，操作均会静默失败
- **根因**：`fetchStatus()` 中 `if (data.ready) this._applyState(data)` — ready=false 时跳过状态同步
- **修复方案**：当 `data.ready === false && data.project_dir` 存在时，清除前端的 projectDir 并展示警告 Toast；或在 poll 循环中检测 ready 状态变化
- **文件**：`project/apps/desktop/ui-legacy/modules/runtime_mixin.js`
- **状态**：🔴 待修复

### BF-002 工具箱误导性"可用"标识（NEW-3）
- **表现**：14 个工具全部显示"稳定"或 hybrid 可用标识，但 project-mode 工具在无项目时点击即报错
- **根因**：capability badge 只反映注册表状态（稳定/原型/开发中），未区分运行时可用性
- **修复方案**：在 `openCapabilityTab()` 中检测 project-mode capability + 无 projectDir，展示提示 Toast 而非直接打开
- **文件**：`project/apps/desktop/ui-legacy/modules/capability_admin_mixin.js`
- **状态**：🔴 待修复

## P1 Bug

### BF-003 纯 Web 模式选择文件夹无响应（NEW-4）
- **表现**：`openFolderDialog()` 依赖 pywebview 桥，纯浏览器模式下静默无响应
- **根因**：pywebview bridge 调用无 fallback
- **修复方案**：检测 `window.pywebview` 是否存在，不存在时展示"桌面版功能，需通过桌面应用访问"提示
- **文件**：`project/apps/desktop/ui-legacy/modules/project_workflow_mixin.js`
- **状态**：🟡 待修复

## P1 Bug（用户实测发现）

### BF-004 素材导入 405 Method Not Allowed
- **表现**：Vue 前端导入素材面板调用 `POST /api/library/ingest/local/preview` 等 4 个端点报 405
- **根因**：Vue 前端期望 preview/start 两段式流程（4 个新端点），但后端只有旧版单步端点（`/api/library/preview/local`、`/api/library/ingest/local`）；Flask catch-all `GET /<path:filename>` 路径匹配但方法不符 → 405
- **修复方案**：在 `library_routes.py` 中新增 4 个端点：`ingest/local/preview`、`ingest/local/start`、`ingest/image/preview`、`ingest/image/start`；preview 响应字段与 Vue 组件期望一致（顶层 `sample_videos` / `sample_images`，无嵌套）
- **文件**：`project/modules/app_api/routes/library_routes.py`
- **状态**：✅ 已修复

## 执行记录
- [x] BF-001 — fetchStatus() 加 `ready:false` 清空逻辑 + Toast 提示 (runtime_mixin.js)
- [x] BF-002 — openCapabilityTab() project-mode 无项目时改 showToast；capabilityModeText 改中文友好标签 (capability_admin_mixin.js)
- [x] BF-003 — 已确认 pickFolder() 后端走 osascript fallback + 有 showToast 兜底，非 Bug，关闭
- [x] BF-004 — 新增 4 个 Vue 前端素材导入端点，修复 405 (library_routes.py)
