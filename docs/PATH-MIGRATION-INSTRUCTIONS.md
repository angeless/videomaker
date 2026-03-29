# 路径迁移指令 — VideoEditor 项目结构重组

> 版本: v1.0 | 日期: 2026-03-19 | 执行者: Claude Code
> 本文件包含完整的 shell 指令，用于将项目从扁平结构重组为 Cowork + Claude Code 双工作区结构。

---

## 一、目标结构

```
videoeditor/                           # 根目录 — Cowork 产品控制台
├── CLAUDE.md                          # 双模式指令（顶部路由 + Cowork 指令 + Claude Code 自动化指令）
├── README.md                          # 项目总说明（面向人类读者）
├── product_design.md                  # 产品设计文档
├── UX_REPORT_20260315.md              # UX 报告
├── statement.md                       # 项目声明
├── blog/                              # 内容分发/营销
├── demo/                              # 演示数据
├── results/                           # Cowork 产出结果
├── output_canada_video/               # 项目产出
├── project_canada_vlog/               # 项目产出
├── proj_selected_*/                   # 历史项目数据
│
├── docs/                              # 产品文档（Cowork 管理）
│   ├── prd/                           # PRD 文档
│   ├── competitive-analysis/          # 竞品分析
│   ├── ux-audit/                      # UX 审计
│   └── meeting-notes/                 # 会议/决策记录
│
└── project/                           # ← Claude Code 开发工作区
    ├── .claude/
    │   └── CLAUDE.md                  # Claude Code 项目级指令（指向 tech-specs）
    ├── modules/                       # 业务模块（从根目录迁入）
    ├── apps/                          # 应用入口（从根目录迁入）
    ├── tests/                         # 测试（从根目录迁入）
    ├── tools/                         # 开发工具（从根目录迁入）
    ├── logs/                          # 运行日志
    ├── .venv/                         # Python 虚拟环境
    ├── .video_library/                # 运行时数据
    ├── .gitignore
    ├── requirements.txt
    ├── LICENSE
    ├── VERSION                        # 版本号文件
    ├── CHANGELOG.md                   # 变更日志
    ├── QUICKSTART.md                  # 开发快速启动
    ├── README.md                      # 技术 README
    │
    └── docs/                          # 技术文档（Claude Code 读取）
        ├── tech-specs/                # 技术规范（核心治理文档）
        │   ├── architecture.md        # 架构与模块边界
        │   ├── dev-governance.md      # 开发治理流程
        │   └── coding-standards.md    # 编码标准与质量要求
        ├── dev-plans/                 # 开发计划（按版本/阶段）
        ├── audit/                     # 审计记录（每次迭代）
        ├── test-reports/              # 测试报告（每次迭代）
        └── decisions/                 # 架构决策记录 (ADR)
```

---

## 二、迁移前检查

```bash
# 在项目根目录执行

# 1. 确认当前位置
pwd
# 应输出包含 videoeditor 的路径

# 2. 确认 git 状态干净（建议先提交所有未提交的变更）
git status
# 如有未提交变更，先处理：
# git add -A && git commit -m "chore: pre-migration snapshot"

# 3. 创建备份标签
git tag pre-migration-backup-$(date +%Y%m%d)
```

---

## 三、迁移指令（按顺序执行）

### Step 1: 创建目标目录结构

```bash
# 创建 project/ 及其子目录
mkdir -p project/.claude
mkdir -p project/docs/tech-specs
mkdir -p project/docs/dev-plans
mkdir -p project/docs/audit
mkdir -p project/docs/test-reports
mkdir -p project/docs/decisions

# 创建 docs/ 产品文档目录
mkdir -p docs/prd
mkdir -p docs/competitive-analysis
mkdir -p docs/ux-audit
mkdir -p docs/meeting-notes
```

### Step 2: 迁移开发代码到 project/

```bash
# 移动核心开发目录
git mv modules/ project/modules/
git mv apps/ project/apps/
git mv tests/ project/tests/
git mv tools/ project/tools/
git mv logs/ project/logs/ 2>/dev/null || true

# 移动开发配置文件
git mv requirements.txt project/requirements.txt
git mv LICENSE project/LICENSE
git mv QUICKSTART.md project/QUICKSTART.md

# 移动运行时数据目录（不在 git 中的用 mv）
mv .venv project/.venv 2>/dev/null || true
mv .video_library project/.video_library 2>/dev/null || true
mv app_state.db project/app_state.db 2>/dev/null || true

# 移动独立 Python 脚本（这些是开发相关的）
git mv add_subtitles.py project/add_subtitles.py 2>/dev/null || true
git mv analyze_canada_videos.py project/analyze_canada_videos.py 2>/dev/null || true
git mv render_canada_direct.py project/render_canada_direct.py 2>/dev/null || true
git mv render_canada_v2.py project/render_canada_v2.py 2>/dev/null || true
git mv render_canada_v3.py project/render_canada_v3.py 2>/dev/null || true
git mv render_canada_video.py project/render_canada_video.py 2>/dev/null || true
```

### Step 3: 迁移技术文档到 project/docs/

```bash
# 移动已有的技术规范文档（如果已创建在 docs/tech-specs/）
git mv docs/tech-specs/ project/docs/tech-specs/ 2>/dev/null || true
```

### Step 4: 移动 .agents 到 project/

```bash
git mv .agents/ project/.agents/ 2>/dev/null || true
```

### Step 5: 创建 project 级 Claude Code 指令

```bash
# 创建 project/.claude/CLAUDE.md（内容见下方 Step 7）
```

### Step 6: 创建版本文件

```bash
echo "v0.9.0" > project/VERSION
```

### Step 7: 创建 project/.claude/CLAUDE.md

将以下内容写入 `project/.claude/CLAUDE.md`：

```markdown
# VideoEditor — Claude Code 项目指令

> 本文件是 Claude Code 在 project/ 目录下开发时的主入口指令。
> 每次启动开发前，必须先读取技术规范文档。

## 技术规范文档路由

开始任何开发任务前，必须按顺序读取以下文件：

1. `docs/tech-specs/architecture.md` — 架构与模块边界
2. `docs/tech-specs/dev-governance.md` — 开发治理流程
3. `docs/tech-specs/coding-standards.md` — 编码标准与质量要求

## 状态文件路由

- `VERSION` — 当前版本号
- `CHANGELOG.md` — 变更日志
- `docs/dev-plans/` — 开发计划（按版本）
- `docs/audit/` — 审计记录
- `docs/test-reports/` — 测试报告
- `docs/decisions/` — 架构决策记录

## 自动化开发循环

详见根目录 CLAUDE.md 中的「Claude Code 自动化开发指令」章节。
```

### Step 8: 更新 .gitignore

```bash
# 在根目录 .gitignore 中追加
cat >> .gitignore << 'EOF'

# === 迁移后新增 ===
project/.venv/
project/.video_library/
project/app_state.db
project/logs/
project/**/__pycache__/
project/.pytest_cache/
EOF
```

### Step 9: 更新根目录 README.md

更新 README.md 说明新的目录结构，指出：
- Cowork 用户看根目录
- Claude Code 开发者看 `project/` 目录
- 技术规范在 `project/docs/tech-specs/`

### Step 10: 提交迁移

```bash
git add -A
git commit -m "refactor: restructure project into Cowork root + Claude Code project/ workspace

- Move all development code (modules/, apps/, tests/, tools/) into project/
- Create project/docs/tech-specs/ for technical governance documents
- Create docs/ for product documents (PRD, competitive analysis, UX audit)
- Add project/.claude/CLAUDE.md as Claude Code entry point
- Preserve all product-level files at root for Cowork access
- No code logic changes, only directory reorganization"
```

---

## 四、迁移后验证

```bash
# 1. 确认项目结构正确
ls -la project/modules/
ls -la project/apps/
ls -la project/tests/
ls -la project/docs/tech-specs/

# 2. 确认 Cowork 文件仍在根目录
ls CLAUDE.md README.md product_design.md

# 3. 确认虚拟环境可用（需要更新路径引用）
cd project
source .venv/bin/activate
python -c "import flask; print(flask.__version__)"

# 4. 确认应用可启动
python apps/desktop/launcher.py
# 如有路径硬编码问题，需修复（见 Step 11）
```

### Step 11: 修复路径引用（迁移后必做）

迁移后需检查以下文件中的路径引用：

```bash
# 搜索所有硬编码的绝对路径
grep -rn "videoeditor/modules" project/ --include="*.py"
grep -rn "videoeditor/apps" project/ --include="*.py"

# 搜索相对路径引用
grep -rn "\.\./modules" project/ --include="*.py"
grep -rn "\.\./apps" project/ --include="*.py"

# 关注以下文件（最可能有路径引用）：
# - project/apps/desktop/launcher.py（启动入口）
# - project/modules/app_api/server.py（API 服务）
# - project/.claude/launch.json（launch 配置）
# - project/.claude/run-vite.sh（启动脚本）
```

修复所有路径引用后重新测试启动。

---

## 五、回滚方案

如果迁移出现问题：

```bash
# 回滚到迁移前的状态
git reset --hard pre-migration-backup-$(date +%Y%m%d)
```

---

## 六、注意事项

1. **blog/ 目录保留在根目录** — 这是内容分发相关的，由 Cowork 管理
2. **demo/ 目录保留在根目录** — 演示数据
3. **results/ 目录保留在根目录** — Cowork 产出
4. **project_canada_vlog/ 等项目目录保留在根目录** — 具体项目产出
5. **.claude/ 目录在根目录保留** — 根目录的 .claude/ 用于 Cowork 设置（launch.json 等）
6. **project/.claude/ 是新建的** — 用于 Claude Code 开发指令
7. **start.command 需要更新路径** — 如果存在的话

---

*文档结束*
