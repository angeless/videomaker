# Modules index

核心业务与服务模块统一放在 `modules/`。

- `workflow_engine`：7步工作流运行时（状态机 + 步骤执行）
- `app_api`：Flask API 服务层
- `library`：全局素材库、入库、检索
- `adapters`：跨模块数据适配
- `step1_material_analysis` ~ `step7_final_render`：七个可独立演进的功能模块
- `legacy_lab`：历史 demo/test/learn 脚本隔离区

约束：
- 优先修改 `modules/*`，避免在 `.agents/skills/*` 里改业务实现。
- `.agents/skills/*` 仅保留兼容入口壳。
