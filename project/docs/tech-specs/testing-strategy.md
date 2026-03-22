# VideoEditor 测试策略与规范 (Testing Strategy)

**文档类型：** 技术规范 - 测试策略
**版本：** v1.0
**日期：** 2026-03-20
**作者/责任人：** 架构团队
**适用范围：** 所有开发者（AI 和人类）
**最后更新：** 2026-03-20

---

## 1. 文档目的

本文档定义 VideoEditor 项目的测试策略、测试类型、执行频率、目录结构和报告规范。

**与其他规范文档的关系：**

| 文档 | 关系 |
|------|------|
| `coding-standards.md` | 编码标准中的测试章节定义了代码级测试写法；本文档定义测试体系全局策略 |
| `dev-governance.md` | Phase 3（测试验证）引用本文档的测试流程；Phase 6（审计）引用本文档的报告格式 |
| `architecture.md` | 模块边界决定测试隔离范围；分层架构决定 mock 策略 |

**强制性标记：** **MUST** = 必须遵守，**SHOULD** = 强烈建议，**MAY** = 可选参考。

---

## 2. 启用的测试类型

| 缩写 | 类型 | 状态 | 说明 |
|------|------|------|------|
| UT | Unit Test 单元测试 | ✅ Core | 所有业务模块必须覆盖 |
| IT | Integration Test 集成测试 | ✅ Core | 跨模块业务流程验证 |
| SMK | Smoke Test 冒烟测试 | ✅ Core | 核心路径快速检查（< 30s） |
| REG | Regression Test 回归测试 | ✅ Core | 每次迭代全量回归 |
| API | API Test 接口测试 | ✅ Enabled | Flask REST 端点验证 |
| E2E | End-to-End Test 端到端测试 | ✅ Enabled | pywebview 完整用户场景 |
| UI | UI Test 界面测试 | ✅ Enabled | 前端交互与渲染验证 |
| USECASE | Use Case Test 用例测试 | ✅ Enabled | 产品用例场景覆盖 |
| UAT | User Acceptance Test 验收测试 | ✅ Enabled | PRD 验收标准逐项核查 |
| DATA | Data Migration Test 数据测试 | ✅ Enabled | SQLite schema 迁移与数据完整性 |
| PERF | Performance Test 性能测试 | ⚠️ On-demand | 视频处理性能基准（按需执行） |
| SEC | Security Test 安全测试 | ⚠️ On-demand | 路径遍历、注入、权限检查 |
| SDK | SDK Test | ❌ Disabled | 无公共 SDK |
| WEBHOOK | Webhook Test | ❌ Disabled | 无 webhook 功能 |
| CONTRACT | Contract Test | ❌ Disabled | 单体架构，无微服务 |
| LOAD | Load Test | ❌ Disabled | 桌面应用，无并发负载 |
| CHAOS | Chaos Test | ❌ Disabled | 桌面应用，非分布式 |
| A11Y | Accessibility Test | ❌ Disabled | 未来计划（v2.0+） |
| COMPAT | Compatibility Test | ❌ Disabled | 当前仅 macOS |
| L10N | Localization Test | ❌ Disabled | 当前仅中文界面 |

---

## 3. 测试频率与触发时机

| 频率 | 触发条件 | 执行范围 | 执行者 |
|------|---------|---------|--------|
| **Per-task** | 每个 R 任务完成时（Phase 3） | UT + IT + SMK + 当前任务相关测试 | Claude Code |
| **Per-feature** | 功能模块开发完成时 | UT + IT + API + USECASE | Claude Code |
| **Per-version** | 版本发布前 | 全量 REG + E2E + UAT + DATA | Claude Code + 人类 |
| **On-demand** | 人类指定时 | PERF / SEC / 指定范围 | Claude Code |

**MUST** 规则：
- 每个 R 任务完成后，**MUST** 运行 `pytest project/tests/ -v` 全量回归
- 如有 API 变更，**MUST** 运行 API 测试并 curl 验证
- 如有 UI 变更，**MUST** 启动应用进行手动/自动化验证
- 如有数据库 schema 变更，**MUST** 运行 DATA 测试

---

## 4. 通用测试流程（五步法）

所有测试类型遵循统一的五步流程：

```
Prepare → Design → Execute → Verify → Record
准备       设计      执行      验证      记录
```

### 4.1 Prepare（准备）

- 确认测试范围（哪些模块、哪些功能受影响）
- 检查测试环境（Python 版本、依赖安装、FFmpeg 可用性）
- 准备测试数据（fixtures、临时文件、测试用 SQLite 数据库）

### 4.2 Design（设计）

- 编写测试用例（遵循第 5 章命名和结构规范）
- 覆盖矩阵：每个被测功能 **MUST** 覆盖 happy path、error path、boundary case
- 如果是回归测试，确认已有用例覆盖了上次发现的问题

### 4.3 Execute（执行）

- 运行 pytest，收集结果
- 失败的测试先尝试自修复（最多 2 次），仍失败则报告

### 4.4 Verify（验证）

- 确认所有测试通过
- 确认没有跳过关键测试（`@pytest.mark.skip` 必须有理由）
- 确认测试结果与预期一致（不是"测试通过但行为错误"）

### 4.5 Record（记录）

- 生成测试报告（见第 7 章）
- 记录失败项和修复措施
- 更新测试用例（如发现遗漏场景）

### 4.6 各测试类型的特殊要求

| 类型 | Prepare 特殊要求 | Execute 特殊要求 |
|------|-----------------|-----------------|
| UT | mock 外部依赖（FFmpeg、网络、文件系统） | 单个测试 < 1s |
| IT | 准备真实 SQLite 测试库 | 允许 < 5s/用例 |
| API | 启动 Flask test client | 验证状态码 + 响应体 + header |
| E2E | 需要桌面环境 + pywebview | 允许 < 30s/场景 |
| SMK | 无 | 全部 < 30s 完成 |
| DATA | 准备旧版 schema 的测试库 | 验证迁移前后数据完整性 |
| PERF | 准备标准视频素材（1080p, 10s） | 记录耗时基准，与上次对比 |

---

## 5. 测试用例规范

### 5.1 命名规范

**Python 测试函数（MUST）：**

```python
def test_<subject>_<scenario>_<expected>():
    """简短描述测试目的"""
    ...
```

示例：
```python
def test_video_import_hevc_format_success():
    """HEVC 格式的 iPhone MOV 文件应成功导入"""

def test_workflow_run_missing_project_raises_error():
    """运行工作流时项目不存在应抛出 ProjectNotFoundError"""

def test_publish_article_empty_title_returns_400():
    """发布文章时标题为空应返回 400"""
```

**测试文件命名（MUST）：**
- 单元测试：`test_<module_name>.py`
- 集成测试：`test_<flow_name>_flow.py`
- API 测试：`test_<resource>_api.py`
- E2E 测试：`test_e2e_<scenario>.py`

### 5.2 AAA 结构（MUST）

每个测试函数 **MUST** 遵循 Arrange-Act-Assert 结构：

```python
def test_library_search_by_tag_returns_matching():
    # Arrange — 准备测试数据
    db = create_test_db()
    db.insert_video(tags=["travel", "canada"])

    # Act — 执行被测操作
    results = library.search(query="travel")

    # Assert — 验证结果
    assert len(results) == 1
    assert "travel" in results[0].tags
```

### 5.3 覆盖矩阵（MUST）

每个被测功能至少覆盖三类场景：

| 场景类型 | 说明 | 示例 |
|---------|------|------|
| Happy path | 正常输入，预期成功 | 合法视频文件成功导入 |
| Error path | 异常输入或故障条件 | 文件不存在、格式不支持、磁盘满 |
| Boundary | 边界值和极端情况 | 空文件、超大文件、特殊字符文件名 |

### 5.4 测试用例 ID（SHOULD）

格式：`TC-<TYPE>-<MODULE>-<SEQ>`

示例：`TC-UT-LIB-001`（单元测试-素材库-001）、`TC-API-WF-003`（API测试-工作流-003）

---

## 6. 测试目录结构

### 6.1 标准目录（目标结构）

```
project/tests/
├── conftest.py                  # 全局 fixtures 和配置
├── unit/                        # UT — 按模块镜像
│   ├── material_analysis/       # 素材分析模块
│   ├── creative_engine/         # 创作引擎模块
│   ├── workflow/                # 工作流模块
│   ├── library/                 # 素材库模块
│   └── app_api/                 # API 路由层
├── integration/                 # IT — 跨模块业务流
├── api/                         # API — Flask 端点测试
├── e2e/                         # E2E — 完整用户场景
├── smoke/                       # SMK — 核心路径快速检查
├── fixtures/                    # 共享测试数据
│   ├── conftest.py
│   └── test_data/               # 测试用视频/图片/JSON
├── helpers/                     # 共享测试工具函数
└── reports/                     # 测试报告输出（gitignore）
```

### 6.2 当前状态与迁移计划

当前测试文件扁平放置在 `project/tests/` 根目录。迁移到标准结构将在后续版本中逐步完成。迁移规则：

- 新增测试 **MUST** 放入标准子目录
- 已有测试在被修改时 **SHOULD** 迁移到对应子目录
- 迁移时 **MUST** 确保 `pytest project/tests/ -v` 全量通过

---

## 7. 测试报告规范

### 7.1 任务级报告

文件名：`test-report-v{X.Y.Z}-r{N}.md`
存放位置：`project/docs/test-reports/`

**MUST** 包含以下内容：

```markdown
# 测试报告 — v{X.Y.Z} R{N}

**日期：** YYYY-MM-DD
**测试范围：** {本次任务涉及的模块}
**测试环境：** Python {version}, macOS {version}

## 测试执行摘要

| 指标 | 值 |
|------|-----|
| 总用例数 | N |
| 通过 | N |
| 失败 | N |
| 跳过 | N |
| 耗时 | Ns |

## 测试详情

### 新增测试
- test_xxx — 测试目的

### 失败项（如有）
- test_xxx — 失败原因 — 修复措施

### 跳过项（如有）
- test_xxx — 跳过原因

## 回归测试结果
pytest project/tests/ -v 全量通过: ✅ / ❌
```

### 7.2 版本级报告

文件名：`test-report-v{X.Y.Z}-release.md`

在版本发布前生成，汇总该版本所有 R 任务的测试结果。

---

## 8. 测试数据管理

### 8.1 Fixtures（MUST）

- 共享 fixtures 放在 `project/tests/conftest.py` 或 `project/tests/fixtures/conftest.py`
- 使用 `@pytest.fixture` 装饰器，遵循 pytest 标准
- 数据库 fixture **MUST** 使用临时目录（`tmp_path`），不污染真实数据

### 8.2 临时文件清理（MUST）

- 测试产生的临时文件 **MUST** 在测试结束后清理
- 使用 `tmp_path` fixture 或 `tempfile` 模块
- 不在项目目录中留下 `.tmp_*` 文件

### 8.3 SQLite 测试数据库

- 每个需要数据库的测试 **MUST** 创建独立的临时数据库
- 不使用生产数据库文件
- 使用 `:memory:` SQLite 或 `tmp_path` 下的 `.db` 文件

### 8.4 视频测试素材

- 测试用视频文件放在 `project/tests/fixtures/test_data/`
- 保持文件体积最小化（< 1MB，短片段即可）
- 如果测试不需要真实视频处理，**SHOULD** mock FFmpeg 调用

---

## 9. 项目特定测试注意事项

### 9.1 FFmpeg 依赖

```python
import shutil
import pytest

HAS_FFMPEG = shutil.which("ffmpeg") is not None

@pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg not available")
def test_video_transcode():
    ...
```

- 依赖 FFmpeg 的测试 **MUST** 加 `skipif` 守卫
- 本机 FFmpeg 路径可能为 `/opt/homebrew/bin/ffmpeg`
- 本机 FFmpeg **未编译 libass**，`subtitles` filter 不可用

### 9.2 视频处理测试

- 视频处理测试需要真实媒体文件，执行时间较长
- **SHOULD** 使用 `@pytest.mark.slow` 标记慢速测试
- 日常回归可跳过慢速测试：`pytest -m "not slow"`
- 版本发布前 **MUST** 运行全量（含慢速）测试

### 9.3 pywebview / UI 测试

- E2E 和 UI 测试需要桌面图形环境
- 无头环境（SSH、CI 容器）下 **MUST** 跳过这些测试
- 使用 `@pytest.mark.ui` 标记需要图形环境的测试

### 9.4 可选依赖测试

- 部分模块依赖可选库（torch、mediapipe、CLIP）
- 可选依赖不可用时测试 **MUST** 优雅跳过，不报错
- 使用 try/import 模式检测：

```python
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

@pytest.mark.skipif(not HAS_TORCH, reason="torch not installed")
def test_semantic_analysis_with_clip():
    ...
```

### 9.5 pytest 配置建议

在 `project/pyproject.toml` 或 `project/pytest.ini` 中配置：

```ini
[tool:pytest]
testpaths = tests
markers =
    slow: 执行时间较长的测试（视频处理等）
    ui: 需要桌面图形环境的测试
    ffmpeg: 依赖 FFmpeg 的测试
```

---

## 10. 测试质量红线

以下情况 **MUST** 视为测试不通过，不得跳过或忽略：

1. **核心路径测试失败** — 素材导入、工作流执行、视频渲染、发布流程
2. **回归测试新增失败** — 之前通过的测试本次失败
3. **数据完整性测试失败** — SQLite schema 迁移后数据丢失或损坏
4. **API 契约测试失败** — 返回格式、状态码与文档不一致
5. **安全测试失败** — 路径遍历、未授权访问等安全问题

以下情况 **MAY** 标记为已知问题并继续：

1. 可选依赖不可用导致的跳过（torch、mediapipe）
2. 环境限制导致的跳过（无 FFmpeg、无桌面环境）
3. 性能测试基准浮动在 ±10% 以内

---

*文档结束*
