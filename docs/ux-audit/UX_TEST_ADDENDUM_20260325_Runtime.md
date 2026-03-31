# VideoEditor v0.12.12 — 实际运行测试附录

> **关联报告**: `UX_TEST_REPORT_20260325_Creator_Simulation.md`
> **补充日期**: 2026-03-25
> **测试方式**: Flask 无头模式启动（port 9527）+ Chromium 浏览器 + preview 工具链（截图/快照/网络/控制台）

---

## 一、测试环境

```
服务器模式: Flask headless (VIDEOEDITOR_REQUIRE_LOCAL_TOKEN=0)
Python: 3.13.1
FFmpeg: /opt/homebrew/bin/ffmpeg
AI 状态: 未配置 API Key（OpenAI + Anthropic 均未设置）
素材库: 空库（0 个素材）
项目: 无加载项目
```

---

## 二、实测发现（按测试顺序）

### RT-1：启动与加载

**实测网络请求序列**（浏览器 DevTools 抓包）:
```
GET /api/session/bootstrap      → 200 OK
GET /api/settings/ui            → 200 OK
GET /api/system/preflight       → 200 OK
GET /api/settings/ai            → 200 OK
GET /api/status                 → 200 OK
GET /api/tasks/queue            → 200 OK
```

**RT-1-A ✅ 亮点**: 6 步启动序列全部 200，Vue 资源懒加载，冷启动流畅。StartupView、WorkflowPanel 等按需分块加载，性能良好。

**RT-1-B 🔴 Bug**: `GET /api/status → {"ready": false}`，但 UI 标题栏仍显示 `project_canada_vlog`（来自前端 localStorage 缓存）。**前后端状态不同步**，用户看到项目名以为已打开，实际后端空载。

---

### RT-2：系统预检结果（实测 API 数据）

```
检查项              状态        实测详情
Python              ✅ ok       3.13.1
Flask               ✅ ok       已安装
pywebview           ✅ ok       已安装
FFmpeg              ✅ ok       /opt/homebrew/bin/ffmpeg
向量检索            ⚠️ warning  缺少 OpenAI API Key，text-embedding-3-small 不可用
本地 Token 保护     ⚠️ warning  VIDEOEDITOR_REQUIRE_LOCAL_TOKEN 未启用
CSRF 保护           ⚠️ warning  CSRF 校验未启用
DaVinci Resolve     ⚠️ warning  未检测到（仍可生成交接文件）
阻断项              0 个        系统可正常运行
```

**RT-2-A ✅ 好的设计**: 向量检索缺 API Key 时降级为关键词搜索，系统不崩溃。preflight 区分 blocker/warning，"了解风险继续"按钮设计得当。

**RT-2-B ⚠️ 文案问题**: DaVinci 提示"仍可生成交接文件"——自媒体人看不懂。建议改为"没有剪辑软件，使用内置渲染器输出"。

---

### RT-3：Step 1 — 点击"分析素材"（实测点击）

**操作**: 点击 `button.btn.btn-primary`（分析素材）

**实测结果**:
```
POST /api/run_step → 400 BAD REQUEST
Response: {"error": "项目未加载"}
```

**UI 反应**: 按钮被点击，请求失败，页面**无任何变化**——无 toast、无错误弹窗、无按钮状态变化。

**RT-3-A 🔴 静默失败**: 经典反模式。用户点击无效果，会反复点击或以为软件卡住。

**RT-3-B 🔴 证实 P0-1**: Step 1 内容截图证实——只有说明文字 + "分析素材"按钮，**零素材选择 UI**。

---

### RT-4：素材库页面（实测截图）

截图显示素材库的实际视觉效果：
- 搜索栏 placeholder: `"请先导入素材后再搜索"` ← ✅ 良好空态文案
- `素材总数：0` 蓝色徽章
- 3 tab 切换：`导入与浏览` / `维护` / `工程修复`
- 导入面板：`本地视频` / `本地图片` / `云端导入` 三个子选项卡
- 输入框 + "选择文件夹"按钮 + "预览扫描" + "开始入库"
- 折叠面板：标签浏览 / 搜索分析 / 自定义标签

**RT-4-A ✅ 超预期**: 空库状态视觉整洁，引导文字清晰，比代码走查预判好。

**RT-4-B ⚠️ 致命依赖**: "选择文件夹"按钮依赖 pywebview 原生桥接，**纯浏览器访问时静默无效**。对于 Web 模式需提供 `<input type="file" webkitdirectory>` 降级方案。

**RT-4-C — API 数据**:
```json
GET /api/library/stats
{
  "total_assets": 0,
  "hybrid_search_enabled": true,       ← 关键词搜索可用
  "embedding_status": "missing_api_key",
  "visual_search_enabled": false,
  "semantic_dimensions_supported": 62   ← 高维度语义系统
}
```
`semantic_dimensions_supported: 62` 是竞争优势，远超同类产品（通常 10-20 维）。

---

### RT-5：设置页面（实测截图）

截图显示实际设置界面：
- 当前 AI 服务商：`OpenAI`，模型：`gpt-4o-mini`
- OpenAI 密钥右侧：黄色 **"未配置"** 徽章
- Anthropic 密钥右侧：黄色 **"未配置"** 徽章

**实测 AI 服务商 API 支持**:
```
OpenAI    → gpt-4o-mini / gpt-4o / gpt-4.1-mini / o4-mini / o3-mini
Anthropic → claude-sonnet-4-6 / claude-3-7-sonnet-latest / claude-3-5-haiku-latest
Moonshot  → moonshot-v1-8k / 32k / 128k
Qwen      → qwen-plus / turbo / max
Gemini    → gemini-2.0-flash / 1.5-pro / 1.5-flash
MiniMax   → abab6.5s/t/g-chat
```

密钥存储后端：`macOS Keychain`（`"backend": "macos_keychain"`）

**RT-5-A ✅ 亮点**: 6 家服务商支持国内主流（Kimi/通义/MiniMax），密钥用 macOS Keychain 管理安全性好。

**RT-5-B ⚠️ 问题**: 无"测试连接"按钮，用户无法验证 API Key 是否有效。

---

### RT-6：工具箱（实测截图 + 快照）

**左侧 14 个工具**，全部标注 `可用`：

| 组别 | 工具列表 |
|------|---------|
| 内容策划 | 选题库、选题文案、公众号扩写 |
| 剪辑制作 | 文字粗剪、短视频快剪、视频精剪 |
| 后期增强 | 配乐配音、字幕校准、图片语义 |
| 发布分发 | 发布文案、社媒导出、内容发布 |
| 自动化 | 自定义工作流、任务缓存、Agent模板、Agent观测 |

**右侧内容区顶部**：🔴 红色横幅 `"选题库读取失败：项目未加载"`

**RT-6-A 🔴 误导性状态**: 所有工具显示 `可用`，点进去立即报错。**应区分"工具可用"（有功能代码）和"现在能用"（依赖满足）**——需要项目数据的工具在无项目时应显示"需先创建项目"。

**RT-6-B ✅ 文案设计**: 工具箱顶部 hint 文字 `"独立使用单个工具，不走工作流"` 是有效的概念区分，但位置过高容易被忽视。

---

### RT-7：工作流管理器（实测截图）

**截图显示**：
- 标题：`自定义工作流管理`  右上角：`← 返回创作`
- 可用模板卡片：**"素材先行视频制作（10步）"** `10 个阶段`
- 描述：适合 vlog/纪录片/UGC 等先有素材再找故事的制作流程
- 标签：`视频` `Vlog` `素材先行` `模板`
- **10 步完整流程**（截图中清晰可见）：
  ```
  1 素材入库与深度理解   2 叙事发现(选题)   3 纸面粗剪
  4 第一次粗剪           5 脚本细化+旁白设计 6 第二次粗剪
  7 精剪                 8 声音设计          9 字幕+导出V1
  10 审片+精调
  ```
- `从模板创建` 按钮
- 我的工作流区域：`暂无自定义工作流，可从上方模板创建`

**RT-7-A ✅ 超预期惊喜**: 这个 10 步 vlog 模板**完美契合"有乱素材→爆火 vlog"的测试场景**。步骤命名（"叙事发现""纸面粗剪""审片+精调"）远比 7 步工作流的技术化命名更直觉。这个模板本身就是对主报告 P1-1 命名问题的隐性修正。

**RT-7-B ⚠️ 孤立问题**: 工作流管理器（10步模板）和 7 步工作流是两套系统，UI 上没有任何互相引导。

---

### RT-8：API 健康全览

| 端点 | 状态码 | 关键数据 |
|------|--------|---------|
| `GET /api/status` | 200 | `{"ready": false}` |
| `GET /api/project/list` | 200 | `{"projects": []}` |
| `GET /api/system/preflight` | 200 | `ok: true, blockers: []` |
| `GET /api/library/stats` | 200 | `total_assets: 0` |
| `GET /api/library/search` | 200 | `total_matches: 0`（库空，正常） |
| `GET /api/workflows` | 200 | `workflows: []` |
| `GET /api/job/interrupted` | 200 | `jobs: []` |
| `POST /api/run_step` | **400** | `{"error": "项目未加载"}` |
| `GET /api/settings/ai` | 200 | 6 providers, keys unset |

---

## 三、实测新增发现（代码走查未能发现）

| 编号 | 发现 | 级别 |
|------|------|------|
| NEW-1 | Step 1 点击"分析素材"后**完全静默失败**（400 但无任何 UI 反馈） | 🔴 P0 |
| NEW-2 | UI 标题显示项目名但后端 `ready: false`，**前后端状态脱节** | 🔴 P0 |
| NEW-3 | 工具箱 14 个工具全标"可用"，点进去即报错，**误导性状态标识** | 🔴 P0 |
| NEW-4 | "选择文件夹"按钮依赖 pywebview 桥，纯 Web 模式**静默无响应** | ⚠️ P1 |
| NEW-5 | 设置页无"测试连接"按钮，API Key 配置无法即时验证 | ⚠️ P1 |
| NEW-6 | 10步 vlog 工作流模板（工作流管理器）与 7步引导流程孤立，无互相引导 | ⚠️ P1 |
| NEW-7 | `semantic_dimensions_supported: 62`，语义标签系统维度极高，是隐藏竞争优势 | ✅ 亮点 |
| NEW-8 | 支持 6 家 AI 服务商含国内主流，密钥存 macOS Keychain，安全架构完善 | ✅ 亮点 |

---

## 四、实测后评分修正

| 维度 | 代码走查 | 实测修正 | 变化 | 理由 |
|------|---------|---------|------|------|
| 上手难度 | ⭐⭐⭐ | ⭐⭐ | ↓ | 工具"可用"但不可用，误导新用户 |
| 核心任务完成率 | ⭐⭐⭐ | ⭐⭐ | ↓ | Step 1 静默失败，工作流完全无法启动 |
| 认知负担 | ⭐⭐ | ⭐⭐ | = | 10步模板好但两套系统孤立加重负担 |
| 惊喜感 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ↑ | 10步 vlog 模板超预期，完美契合场景 |
| 发布就绪度 | ⭐⭐ | ⭐⭐ | = | 无变化 |
| 错误恢复 | ⭐⭐⭐⭐ | ⭐⭐ | ↓↓ | 关键路径静默失败，无任何错误恢复引导 |
| 国际化 | ⭐⭐ | ⭐⭐ | = | 无变化 |

**综合评分修正: 2.9 → 2.6 / 5.0**

---

## 五、关键截图记录

| 截图 | 内容 | 关键发现 |
|------|------|---------|
| 截图1 | 创作页·Step 1（缩略版） | Step 1 没有素材选择 UI，只有一个按钮 |
| 截图2 | 创作页·Step 1（全尺寸） | 整个工作区空白，7步步骤条正常渲染 |
| 截图3 | 素材库页 | 空态引导清晰，三 tab 分组合理 |
| 截图4 | 设置页 | 双 API Key"未配置"黄色徽章醒目 |
| 截图5 | 工具箱 | 14工具全"可用"但右侧显示"项目未加载"错误 |
| 截图6 | 工作流管理器 | 10步 vlog 模板，超预期的产品设计亮点 |

---

*实测附录: 2026-03-25*
*测试工具: Flask headless + Claude Preview (Chromium) + curl API 测试*
