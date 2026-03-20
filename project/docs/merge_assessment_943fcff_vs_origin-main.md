# 合并评估报告（仅评估，不在本线程执行合并）

更新时间：2026-02-23  
对比范围：`origin/main (94839dc)` -> `main (943fcff)`  
未并入远端主线提交：`943fcff refactor: finalize modular isolation with compatibility wrappers`

---

## 1) 合并风险报告

### 变更规模
- 提交数：1
- 文件变更：100
- 代码量：`+23501 / -6031`
- 主要特征：**重构 + 新功能混合在同一提交**

### 风险分级

#### 高风险
1. **提交粒度过大，且“架构迁移”和“新能力引入”混合**
- 迁移：`.agents/skills/*` -> `modules/*` + `apps/*`
- 新增：`modules/app_api/server.py`、`modules/library/global_media_library.py`、`apps/desktop/ui/*` 等完整能力
- 风险：冲突定位和回归定位成本高，回滚易“一刀切”

2. **运行时入口路径重定向（wrapper）依赖 `sys.path` 注入**
- 兼容壳大量使用 `runpy` + `sys.path.insert`
- 风险：特殊启动方式（不同 cwd / 打包环境）下可能出现导入边界问题

3. **新增全局持久化库（SQLite + cache）引入状态耦合**
- 新增 `.video_library/library.db` 与 `cache/gdrive`
- 风险：代码可回滚，但运行期数据状态（库结构/缓存）可能残留，影响回滚后行为一致性

#### 中风险
1. **接口面新增较多（HTTP API + UI）**
- 新增 `api/settings/ai`、`api/library/*`、`api/job/*/cancel` 等
- 风险：前后端版本不一致时可能出现字段期望差异

2. **依赖与性能负载模型变化**
- 引入重任务并发控制、系统负载拦截、异步任务取消
- 风险：边界场景（高负载、长任务取消、I/O 慢）需专项验证

#### 低风险
1. **历史脚本入口可用性**
- 已验证以下兼容入口可运行：
  - `/Users/angelwang/videoeditor/.agents/skills/manage-videos/run_toolkit.py --help`
  - `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/workflow.py --help`
  - `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/app.py --help`

### 合并前最低验证清单（建议）
1. 启动 GUI + API 全流程冒烟（初始化、分析、选素材、run_step、approve、cancel）。
2. 本地与 Google Drive 入库各跑一轮（含中途取消）。
3. 回归旧入口命令（至少 5 个常用脚本）。
4. 验证 `.video_library` 清库后重建行为。

---

## 2) 影响模块列表

### 顶层目录影响
- `modules/`：49 文件（新增为主）
- `.agents/`：35 文件（兼容壳/入口调整）
- `apps/`：8 文件（新增桌面启动与 UI）
- `docs/`：5 文件（重构文档）
- `requirements.txt`、`README.md`、`.gitignore` 变更

### 关键模块（按影响面）
1. `modules/app_api`
- 新增 Flask API 与任务调度、负载保护、取消机制

2. `modules/library`
- 新增全局素材库（sha256 + phash + semantic）与本地/云端入库

3. `modules/workflow_engine`
- 新增 7 步工作流核心引擎（旧路径兼容壳转发）

4. `modules/step1_material_analysis` ~ `modules/step7_final_render`
- 形成步骤化模块边界；step1/step4/step7 影响最大

5. `apps/desktop`
- 新增桌面启动器与前端页面（`index.html` / `app.js` / `styles.css`）

6. `.agents/skills/video-editor/scripts/*` 与 `.agents/skills/manage-videos/*`
- 从“实现本体”转为“兼容入口壳（wrapper）”

7. `modules/legacy_lab/manage_videos/*`
- 历史 demo/test/learn 脚本迁移到隔离区

---

## 3) 接口变化说明

### A. 脚本入口与导入接口

#### 兼容保留（对外命令路径不变）
- 旧入口路径仍可调用，例如：
  - `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/workflow.py`
  - `/Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/auto_render.py`
  - `/Users/angelwang/videoeditor/.agents/skills/manage-videos/run_toolkit.py`

#### 实现主体迁移（内部导入路径变化）
- 迁移到 `modules/*` 与 `apps/*`，旧入口通过 wrapper 转发。
- 对“直接 import 旧实现内部私有函数”的外部脚本存在潜在兼容风险（需按新模块 API 调整）。

### B. HTTP API（新增）

新增核心端点（示例）：
- `GET /api/settings/ai`
- `POST /api/settings/ai`
- `GET /api/system/load`
- `GET /api/library/stats`
- `GET /api/library/search`
- `POST /api/library/assets`
- `POST /api/library/preview/local`
- `POST /api/library/ingest/local`
- `POST /api/library/preview/gdrive`
- `POST /api/library/ingest/gdrive`
- `POST /api/job/<job_id>/cancel`

### C. 关键请求/响应契约变化
1. `POST /api/init`
- 支持两种初始化模式：
  - 传统：`videos_dir`
  - 新增：`selected_video_uids`（最多 50）
- 选择素材模式会直接写入 `data/materials.json`，并把 Step1 置为已完成

2. `GET /api/library/search`
- 支持分页参数：`limit`、`offset`
- 返回新增：`total_matches`、`total_assets`、`has_more`、`truncated`

3. `GET /api/job/<job_id>`
- 返回新增：`progress`、`cancel_requested`、`system`、`state`

### D. 数据层契约变化
- 新增全局库数据库：`.video_library/library.db`
- 关键字段：
  - `assets.sha256`（唯一精确指纹）
  - `assets.phash`（相似检索）
  - `asset_locations`（多位置与可用性）
- 新增语义结构字段（`semantic_json`、`keywords_json`、`semantic_version`）

---

## 4) 回滚策略

### 推荐回滚（代码）
1. **整提交回滚（首选）**
- `git revert 943fcff`

2. **分层回滚（仅当必须局部回退）**
- 先回退 `modules/app_api` 与 `apps/desktop`（UI/API 层）
- 再回退 `modules/library`（状态层）
- 最后回退 wrappers（`.agents/skills/*`）

### 运行态回滚（数据）
1. 保留或备份 `.video_library/`：
- 回滚代码前建议先备份 `.video_library/library.db`
- 回滚后若出现兼容问题，清理缓存目录后重建

2. 项目级产物不回滚删除：
- `proj_*` 目录按项目独立保留，避免误删用户结果

### 回滚后验证
1. `python3 /Users/angelwang/videoeditor/.agents/skills/manage-videos/run_toolkit.py --help`
2. `python3 /Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/workflow.py --help`
3. `python3 /Users/angelwang/videoeditor/.agents/skills/video-editor/scripts/app.py --help`
4. `python3 -m py_compile /Users/angelwang/videoeditor/modules/workflow_engine/workflow.py /Users/angelwang/videoeditor/modules/app_api/server.py /Users/angelwang/videoeditor/modules/library/global_media_library.py`

---

## 线程边界约束（执行策略）

- 本线程只做“评估与报告”，**不执行 merge/rebase/cherry-pick**。
- merge + 重构动作请在新线程执行，避免与功能开发线程交叉污染。

