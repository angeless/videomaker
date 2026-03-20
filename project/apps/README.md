# Apps index

应用入口层统一放在 `apps/`。

- `apps/desktop/launcher.py`：桌面 GUI 启动入口（pywebview + Flask）
- `apps/desktop/ui/*`：桌面端前端静态资源
- `apps/cli/run_toolkit.py`：素材分析 CLI 入口

旧入口路径 `.agents/skills/*` 保留 wrapper 兼容。
