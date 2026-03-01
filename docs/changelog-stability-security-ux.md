# 稳定性 / 安全性 / UX 优化记录

**版本**：v0.3.0-stability
**日期**：2026-03-01
**分支**：claude/serene-shamir
**执行者**：Claude Opus 4.6（serene-shamir worktree）
**触发**：第二轮真实用户全功能走查测试 → 发现问题 → 实施修复
**基线**：b4e70fc（chore: print local UI URL when launcher starts）

---

## 一、变更概览

本轮共修改 **11 个文件**，新增 **2 个 API endpoint**，覆盖三大维度：

| 维度 | 数量 | 说明 |
|------|------|------|
| P0 稳定性 | 3 项 | subprocess timeout / input() 隔离 / _jobs 线程锁 |
| P1 安全 | 3 项 | chmod 600 / SSRF 防护 / 符号链接穿越 |
| P2 功能 UX | 7 项 | 渲染取消 / 步骤导航 / FFmpeg 自检 / AI 测试 / Step4 编辑 / 美颜参数 / preflight UI |

---

## 二、P0 — 稳定性修复（Codex 卡死根因）

### P0.1 subprocess timeout
**问题**：16+ 个 `subprocess.run / Popen.wait` 调用无 timeout，FFmpeg 进程挂起时 Python 线程永久阻塞。
**修复**：所有调用加 `timeout` + `try/except subprocess.TimeoutExpired` 优雅降级。

| 文件 | 调用数 | timeout |
|------|--------|---------|
| `modules/step7_final_render/pipeline.py` | 3 | 3600s |
| `modules/step7_final_render/auto_render.py` | 10 | 30s（probe）/ 3600s（render） |
| `modules/step6_rough_cut/rough_cut.py` | 2 | 3600s |
| `modules/step5_frame_preview/frame_preview.py` | 1 | 60s |
| `modules/app_api/server.py` | 1（osascript） | 120s |

### P0.2 legacy input() 隔离
**问题**：`chinese_search_ui.py` / `video_search_ui.py` / `fingerprint_scanner.py` 中的 `while True + input()` 在 headless 环境永久阻塞。
**修复**：入口函数加 `if not sys.stdin.isatty(): return` 守卫。

| 文件 | 修改 |
|------|------|
| `modules/legacy_lab/manage_videos/chinese_search_ui.py` | +`import sys` + isatty 守卫 |
| `modules/legacy_lab/manage_videos/video_search_ui.py` | +`import sys` + isatty 守卫 |
| `.agents/skills/manage-videos/fingerprint_scanner.py` | isatty 守卫（sys 已 import） |

### P0.3 _jobs 线程锁
**问题**：`_jobs` 字典在 Flask 请求线程和后台 worker 线程间无同步保护，竞态条件可导致 job 状态永远卡在 "running"。
**修复**：`server.py` 新增 `_jobs_lock = threading.Lock()`，保护 init / done / error / cancel / read 5 个关键路径。

---

## 三、P1 — 安全修复

### P1.1 设置文件权限
**位置**：`server.py` `_write_settings()`
**修复**：写入后追加 `p.chmod(0o600)`，防止其他用户读取 API Key。

### P1.2 SSRF 防护
**位置**：`modules/capabilities/audio_voice.py`
**修复**：新增 `_validate_remote_endpoint()` 函数，阻止 `endpoint` URL 指向 localhost / 10.x / 172.16-31.x / 192.168.x / 169.254.169.254 等内网地址。
**覆盖**：`_http_json_post()` 和 `_http_download_binary()` 两个 HTTP 出口。

### P1.3 符号链接路径穿越
**位置**：`server.py` `api_files()` + `serve_static()`
**修复**：
- `startswith` 检查改为 `str(project_root) + os.sep` 前缀匹配（防止 `/project2` 匹配 `/project`）
- 新增 `target.is_symlink()` 检查，拒绝指向项目外的符号链接

---

## 四、P2 — 功能与 UX 改进

### P2.1 渲染取消 UI 按钮
**位置**：`index.html` Step 7 面板
**改动**：渲染进行中时在日志框标题栏显示「⏹ 取消渲染」按钮，调用已有 `cancelWorkflowJob()`。新增"已取消"提示卡片。

### P2.2 步骤导航（上一步/下一步）
**位置**：`index.html` 内容区底部
**改动**：在工作流视图底部添加"← 上一步"/"下一步 →"按钮，复用已有 `navToStep(n)`。未完成的步骤不可跳转。

### P2.3 FFmpeg 安装引导 — `/api/system/preflight`
**位置**：`server.py` 新增 endpoint
**改动**：轻量级环境自检，检测 FFmpeg / ffprobe / Python 版本 / AI Key 状态，每项附带安装提示（hint）。
**双入口**：GET `/api/system/preflight`（人类 UI + Agent 均可调用）

### P2.4 AI 连接测试 — `/api/settings/ai/test`
**位置**：`server.py` 新增 endpoint + `index.html` + `app.js`
**改动**：POST 请求，用保存的 AI 配置发送轻量请求验证 Key 有效性。支持 OpenAI / Anthropic 双 provider。UI 显示成功/失败提示。
**双入口**：POST `/api/settings/ai/test`

### P2.5 Step 4 应用内素材编辑
**位置**：`index.html` Step 4 面板 + `app.js`
**改动**：
- 匹配表中"分配素材"列改为 `<select>` 下拉，列出所有可用素材（带文件名+时长）
- 新增 `reassignClipMaterial(clipIndex, newVideoId)` 方法
- 确认时自动保存 scriptClips 到后端
- 删除"请手动编辑 JSON"提示

### P2.6 美颜参数暴露
**位置**：`index.html` Step 6 面板 + `app.js`
**改动**：
- 磨皮强度改为 `<input type="range">` 滑块（原为 number 输入）
- 新增"毛孔弱化"滑块（`pore_reduction`, 0-1）
- 两个滑块均显示当前值
- `renderOpts` 默认值新增 `pore_reduction: 0.6`

### P2.7 环境自检 UI 面板
**位置**：`index.html` Hub 页面 + `app.js`
**改动**：在 AI 配置卡片下方新增「环境自检」卡片，显示 FFmpeg / ffprobe / Python / AI Key 四项检测结果。附「刷新」按钮重新检测。

---

## 五、修改文件清单

| 文件 | 改动类型 |
|------|----------|
| `modules/step7_final_render/pipeline.py` | P0.1 timeout |
| `modules/step7_final_render/auto_render.py` | P0.1 timeout |
| `modules/step6_rough_cut/rough_cut.py` | P0.1 timeout |
| `modules/step5_frame_preview/frame_preview.py` | P0.1 timeout |
| `modules/app_api/server.py` | P0.1 + P0.3 + P1.1 + P1.3 + P2.3 + P2.4 |
| `modules/legacy_lab/manage_videos/chinese_search_ui.py` | P0.2 isatty |
| `modules/legacy_lab/manage_videos/video_search_ui.py` | P0.2 isatty |
| `.agents/skills/manage-videos/fingerprint_scanner.py` | P0.2 isatty |
| `modules/capabilities/audio_voice.py` | P1.2 SSRF |
| `apps/desktop/ui/index.html` | P2.1 + P2.2 + P2.5 + P2.6 + P2.7 |
| `apps/desktop/ui/app.js` | P2.4 + P2.5 + P2.6 + P2.7 |

---

## 六、验证结果

- `py_compile`：9/9 文件通过
- `pytest tests/`：112/112 测试通过（无回归）
- 前端 JS：无语法错误（Alpine.js reactive 数据绑定完整）

---

## 七、下一步计划（待实施）

### 高优先
1. **content_publish 真实实现**：当前 100% 模拟，至少应支持 Blog 平台的真实 Markdown/HTML 本地导出（已有基础代码）
2. **OpenCV 帧读取安全**：`pipeline.py:480-496` 的 `while True` 循环需加最大迭代限制
3. **README.md 更新**：当前 README 仍描述旧 "Kimi Skill" 架构

### 中优先
4. **Step 3 脚本时间线拖拽**：当前只是文本列表，无可视化时间线
5. **Step 5 帧预览灯箱**：点击帧缩略图应弹出大图查看
6. **美颜预览**：单帧前后对比预览（需前端 canvas 渲染）
7. **项目模板**：新建项目时选择旅行/美食/风景等预设配置

### 低优先
8. **index.html 组件化拆分**：当前 3673 行单文件
9. **`.app` 打包**：pyinstaller 或 py2app 双击启动
10. **CSRF 条件完善**：当前需 `_REQUIRE_CSRF_PROTECTION` + `_REQUIRE_LOCAL_API_TOKEN` 同时为真

---

## 八、注意事项（接手须知）

1. **不要删除 `.agents/skills/` 下的文件**：它们是兼容壳，旧入口仍依赖
2. **不要移除 `legacy_lab/` 下的 input() 守卫**：已加的 `isatty()` 守卫是防止 Codex/Agent 环境卡死的关键
3. **server.py 的 `_jobs_lock`**：所有对 `_jobs` 字典的读写必须在 `with _jobs_lock:` 内，否则会引发竞态
4. **新增 API endpoint 均需保持双入口设计**：人类 UI 和 Agent 都应能调用
5. **`audio_voice.py` 的 SSRF 验证**：任何新增的 HTTP 出口都应经过 `_validate_remote_endpoint()`
