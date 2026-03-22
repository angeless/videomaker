# R1 实施计划 — v0.11 遗留问题审计修复

**任务版本号**: v0.12.1
**所属功能项**: v0.12.0 — 遗留审计修复
**制定日期**: 2026-03-22
**基线 commit**: 618ddf2

---

## 1. 任务目标

验证 v0.11 的 11 个 R 任务是否完整修复了 v0.10 审计报告中的 55 个问题，同时修复评测发现的 3 个新问题（M3/H2/M5）。

## 2. 验收标准

- [ ] v0.10 审计报告中的问题全部标记为"已修复"或"不适用"
- [ ] 全量测试通过率 100%（排除已知 skip）
- [ ] Library Facade 所有公共方法签名不变
- [ ] `/api/projects` 不再返回 missing 状态的残留项目
- [ ] 项目内分析的素材提供显式同步入口写入全局 Library
- [ ] 创建项目时默认渲染配置与美学预设一致

## 3. 代码现状

| 文件路径 | 当前职责 |
|---------|---------|
| `modules/app_api/services/settings_service.py` | 项目列表管理，`_get_recent_projects()` 返回所有项目含 missing |
| `modules/library/global_media_library.py` | Library Facade（269 行），无项目→全局素材同步方法 |
| `modules/step7_final_render/auto_render.py` | `RenderConfig` 默认 1080x1920 |
| `modules/capabilities/refinement.py` | 美学预设定义（travel_story/cinematic/clean_vlog） |

## 4. 预计修改文件清单

| 文件路径 | 操作 | 变更说明 |
|---------|------|---------|
| `modules/app_api/services/settings_service.py` | 修改 | M3：过滤 missing 状态项目 + 清理入口 |
| `modules/library/global_media_library.py` | 修改 | H2：新增 `sync_project_materials()` 方法 |
| `modules/step7_final_render/auto_render.py` | 修改 | M5：`RenderConfig` 增加 preset 感知 |
| `modules/capabilities/refinement.py` | 修改 | M5：preset 增加推荐方向元数据 |
| `tests/test_settings_service.py` | 新增/修改 | M3 的测试用例 |
| `tests/test_library_sync.py` | 新增 | H2 同步功能测试 |
| `tests/test_render_config.py` | 新增/修改 | M5 preset 匹配测试 |
| `docs/audit/2026-03-22-r1-audit.md` | 新增 | 审计报告 |

## 5. 实施步骤

### Step 1: 审计验收（非编码）
- 逐项验证 v0.10 审计报告 55 项问题在 v0.11 的修复状态
- 输出验收矩阵

### Step 2: M3 修复 — 过滤残留项目
- 在 `_get_recent_projects()` 中过滤 `status="missing"` 的项目
- 可选：新增 `/api/projects/cleanup` 端点清理 missing 项目

### Step 3: H2 修复 — 素材同步入口
- 在 Library Facade 新增 `sync_project_materials(project_dir)` 方法
- 从 `materials.json` 读取分析结果写入 `library.db`

### Step 4: M5 修复 — 渲染配置适配
- 为 aesthetic preset 添加推荐方向元数据
- `RenderConfig` 支持从 preset 推导默认方向

### Step 5: 测试
- 编写对应测试用例
- 运行全量测试确认无回归

## 6. 风险预判

| 风险 | 概率 | 缓解 |
|------|------|------|
| H2 同步时数据冲突 | 中 | 采用 "project 覆盖 library" 策略 |
| M5 改动影响已有渲染 | 低 | 仅改默认值，不改渲染逻辑 |

## 7. 禁止修改文件核对

以上文件均不在 Tier 1 保护清单中。✅
