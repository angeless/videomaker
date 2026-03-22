# R1 实施计划 - 两处 Segfault 修复

**日期：** 2026-03-21
**任务ID：** R1
**任务名称：** P0 稳定性修复（BUG-001 + BUG-002）
**优先级：** P0
**预计变更量：** ~60 行

---

## 1. 需求确认

- **目标**：消除 `/api/init` null 参数和 `/api/run_step` 越界 step 值导致的进程级崩溃
- **根因**：Tee 对象在异常清理阶段引用已失效的 `_real` 属性，触发 C 层 Segfault
- **验收标准**：非法输入返回 HTTP 400，进程不崩溃；正常输入行为不变

## 2. 架构设计

### 2.1 修复策略

三层防御：
1. **入口校验层**：路由 handler 入口处拦截非法参数，提前返回 400
2. **Tee 防御层**：write/flush 方法加 hasattr + try/except 防护
3. **cleanup 防御层**：添加安全的 __del__ 方法

### 2.2 不变约束
- 正常日志写入逻辑和输出不受影响
- step 合法范围 1-7，硬编码与 step_method_map 一致
- 不改变 Tee 在 _worker 中的设置/恢复流程

## 3. 文件清单

| 文件路径 | 操作 | 变更说明 |
|---------|------|---------|
| modules/app_api/routes/legacy_project_routes.py | Modify | /api/init 入口 null 检查；/api/run_step 添加 step 必填+范围校验 |
| modules/app_api/services/job_runtime.py | Modify | Tee.write/flush 加防御；添加 __del__ |
| tests/test_r1_segfault_fix.py | New | 8 个验收用例 |

## 4. 实施步骤

1. legacy_project_routes.py — /api/init handler 入口添加 project_dir null 检查
2. legacy_project_routes.py — /api/run_step handler 添加 step 必填和范围校验
3. job_runtime.py — Tee 类 write/flush 加防御性 try/except
4. tests/test_r1_segfault_fix.py — 编写 8 个验收测试

## 5. 风险预判

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|-----|------|--------|
| Tee 防御代码影响正常日志 | 低 | 高 | 仅在 _real 失效时生效，正常路径无额外开销 |
| step 范围硬编码 | 低 | 低 | 记录到 WISHLIST.md |

## 6. 完成标志

- [ ] null project_dir → 400，不崩溃
- [ ] step=99/0/-1 → 400，不崩溃
- [ ] 正常 /api/init 和 /api/run_step 行为不变
- [ ] 全量回归测试通过
