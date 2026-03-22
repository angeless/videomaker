# 任务汇报 — v0.12.1 R1 v0.11 遗留问题审计修复

**版本**: v0.12.1
**任务**: R1 — v0.11 遗留问题审计修复
**日期**: 2026-03-22
**基线 commit**: 618ddf2
**完成 commit**: e163dc7

---

## 1. 任务目标

验证 v0.11 的 11 个 R 任务是否完整修复了 v0.10 审计报告中的 55 个问题，同时修复评测发现的 3 个新问题（M3/H2/M5）。

## 2. 验收标准完成情况

| # | 验收标准 | 状态 |
|---|---------|------|
| 1 | v0.10 审计报告中的问题全部标记为"已修复"或"不适用" | ✅ 通过 |
| 2 | 全量测试通过率 100%（排除已知 skip） | ✅ 通过 |
| 3 | Library Facade 所有公共方法签名不变 | ✅ 通过 |
| 4 | `/api/projects` 不再返回 missing 状态的残留项目 | ✅ 通过 |
| 5 | 项目内分析的素材提供显式同步入口写入全局 Library | ✅ 通过 |
| 6 | 创建项目时默认渲染配置与美学预设一致 | ✅ 通过 |

## 3. 变更文件清单

| 文件 | 操作 | 变更说明 |
|------|------|---------|
| `modules/app_api/routes/legacy_project_routes.py` | 修改 | M3：增加 `/api/projects/cleanup` 端点 |
| `modules/app_api/services/settings_service.py` | 修改 | M3：`_get_recent_projects()` 过滤 missing 状态项目 |
| `modules/library/global_media_library.py` | 修改 | H2：新增 `sync_project_materials()` 方法 |
| `modules/step7_final_render/auto_render.py` | 修改 | M5：`RenderConfig.from_aesthetic_preset()` 适配方向 |
| `modules/capabilities/refinement.py` | 修改 | M5：`PRESET_ORIENTATIONS` 常量 |
| `tests/test_r1_fixes.py` | 新增 | 9 个测试覆盖 M3/H2/M5 |
| `docs/dev-plans/impl-plan-v0.12.1.md` | 新增 | R1 实施计划 |

## 4. 测试结果

- R1 验收测试：9 passed / 0 failed
- 全量回归：通过（排除已知 skip）

## 5. 风险与遗留

无遗留问题。

## 6. 下一步

R2：语义分析基础设施（增量增强）

## 7. 耗时

单 session 完成

## 8. 关键决策

- M3：采用过滤 + 清理端点双策略，兼顾即时显示和后台清理
- H2：`sync_project_materials()` 采用 project 覆盖 library 策略
- M5：`PRESET_ORIENTATIONS` 以常量形式定义推荐方向，`RenderConfig` 按需读取

## 9. commit hash

e163dc7
