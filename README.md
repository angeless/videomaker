# VideoEditor（桌面版短视频生产系统）

本项目是本地桌面应用（`pywebview + Flask + Alpine`），提供「素材语义分析」「模块化创作能力」「连线式工作流编排」三条生产路径，支持人用界面与 Agent API 双调用。

## 快速启动（无需命令行）

1. 在 Finder 中双击项目根目录的 `start.command`。
2. 首次启动会自动：
   - 创建 `.venv`
   - 安装 `requirements.txt`
   - 启动桌面窗口
3. 后续启动只需再次双击 `start.command`。

说明：`apps/desktop/launcher.py` 内置依赖自检，缺依赖时会自动补装。

## 运行方式（命令行可选）

```bash
cd /Users/angelwang/videoeditor
source .venv/bin/activate
python apps/desktop/launcher.py
```

## 当前核心能力

- 素材语义库：本地/云端素材入库、语义标签、向量检索
- 创作能力模块（Capability）：
  - `topic_library` 选题库
  - `topic_copy` 选题+文案
  - `text_rough_cut` 文字粗剪
  - `short_clip` 短视频快剪
  - `refinement` 精剪/NLE 交接
  - `social_export` 社媒导出
  - `audio_voice` 配乐配音（含 TTS）
  - `subtitle_calibration` 中英字幕校准
  - `image_semantic` 图片语义分析/检索
  - `article_expand` 公众号文章扩写
  - `publish_prep` 发布文案生成（多平台）
  - `content_publish` 发布执行（支持 webhook 网关与 YouTube 直连 connector）
- 工作流画布（n8n 风格）：节点拖拽、连线、节点配置、运行历史、重跑
- Agent 接口：`/api/agent/tasks/plan`、`/api/agent/tasks/run`
- 系统自检：`GET /api/system/preflight`（前端“启动前自检/系统诊断”卡片）
- NLE 连接器检测：`GET /api/capabilities/refinement/connectors`

## 常用目录

- 桌面入口：`apps/desktop/launcher.py`
- 前端：`apps/desktop/ui/index.html`, `apps/desktop/ui/app.js`, `apps/desktop/ui/styles.css`
- 后端 API：`modules/app_api/server.py`
- 能力实现：`modules/capabilities/*.py`
- 文档：`docs/`

## 配置方式

优先使用应用内设置（无需手工改环境变量）：

- AI 设置：Provider / Model / Base URL / API Key
- UI 设置：首次引导、字体缩放、创作者术语模式、默认目录、自动恢复上次项目

配置落盘文件：`.video_library/app_settings.json`

密钥存储说明：
- macOS 下 AI Key 默认写入系统 Keychain，设置文件仅保存引用字段。
- 非 macOS 或系统凭据不可用时，会自动降级到本地设置文件（后续会补多平台凭据后端）。

## 开发与测试

```bash
cd /Users/angelwang/videoeditor
source .venv/bin/activate
pytest -q
```

性能基准（渲染/发布链路）：

```bash
python tools/benchmark_render_publish.py --iterations 20 --include-live-blog
```

## 说明

- 本地 API 默认监听 `127.0.0.1`。
- UI 已改为本地 Alpine 资源（离线可用）。
- 若你只看到了旧界面，请完全退出旧进程后重启 `start.command`。
