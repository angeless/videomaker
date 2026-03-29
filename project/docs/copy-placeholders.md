# VideoEditor — UI 文案占位清单（Copy Placeholder Registry）

> **版本**：v0.11.0 配套
> **状态**：占位中 — 正式发布前统一审核替换
> **创建日期**：2026-03-21
> **负责人**：产品 / 内容

## 使用规则

1. **开发时直接使用占位文案**，不需要等待最终确认
2. **正式发布前**，由产品/内容完成统一审核，按此清单批量替换
3. 占位文案中的 `{变量}` 用实际值替换（如 `{N}` 替换为实际数量）
4. 如开发过程中发现占位文案明显不合适，可临时调整，但需在本文件对应条目增加备注
5. 含 emoji 的文案（如 ✓ ⚠️）需在发布前验证各平台渲染一致性

---

## R4 — 启动引导

| ID | 位置 | 占位文案 | 说明 |
|----|------|---------|------|
| COPY-001 | StartupView → 预检 error 弹窗标题 | `检测到环境问题` | Modal 标题，告知用户预检发现异常 |
| COPY-002 | StartupView → 预检 error 弹窗正文 | `检测到 {N} 个问题，部分功能可能无法正常使用。建议先修复后继续。` | `{N}` 替换为实际 error 数量 |
| COPY-003 | StartupView → 弹窗确认按钮 | `了解风险，继续进入` | 允许用户忽略错误继续的主操作按钮 |
| COPY-004 | StartupView → 弹窗返回按钮 | `返回检查` | 次操作按钮，返回启动界面 |
| COPY-005 | 主界面顶部警告横幅 | `环境检查发现 {N} 个问题，部分功能可能受影响` | 进入主界面后的持续提示横幅 |
| COPY-006 | CreateView/LibraryView → 空状态标题 | `还没有开始` | 向导跳过 + 素材库为空时的引导标题（empty-state 组件）|
| COPY-007 | CreateView/LibraryView → 空状态描述 | `先导入你的视频素材，然后新建项目开始创作` | empty-state 组件的 desc 文字 |
| COPY-008 | CreateView/LibraryView → 空状态主按钮 | `导入素材` | empty-state 主操作按钮 |

---

## R5 — 项目弹窗

| ID | 位置 | 占位文案 | 说明 |
|----|------|---------|------|
| COPY-009 | ProjectDialog → 素材目录路径框 helper text | `你的视频素材所在的文件夹（可选多个来源）` | 帮助用户理解素材目录的用途 |
| COPY-010 | ProjectDialog → 项目保存位置路径框 helper text | `项目文件的保存位置，每个项目独占一个子文件夹` | 帮助用户理解项目目录的用途 |
| COPY-011 | ProjectDialog → 项目名称输入框 helper text | `用于识别项目，实际文件夹名由系统自动生成` | 解释用户填写的名称会如何被使用 |

---

## R6 — 操作确认

| ID | 位置 | 占位文案 | 说明 |
|----|------|---------|------|
| COPY-012 | WorkflowManagerView → 删除工作流弹窗标题 | `删除工作流` | 危险操作确认弹窗标题（使用设计规范 modal-danger 样式）|
| COPY-013 | WorkflowManagerView → 删除工作流弹窗正文 | `确定删除「{名称}」？此操作不可撤销。` | `{名称}` 替换为实际工作流名称 |
| COPY-014 | SettingsView → 断开 YouTube 弹窗正文 | `断开后需要重新授权才能使用 YouTube 发布功能。确认断开？` | 告知断开的影响 |
| COPY-015 | ProjectDialog → 遮罩关闭中断确认 | `内容尚未保存，确认关闭？` | 表单有内容时误触遮罩的提示 |
| COPY-016 | SettingsView → AI 测试连接按钮文字（默认）| `测试连接` | 按钮默认状态文字 |
| COPY-017 | SettingsView → AI 测试连接成功提示 | `✓ 连接成功` | 连通性测试通过后的反馈 |
| COPY-018 | SettingsView → AI 测试连接失败提示 | `连接失败：{error}` | `{error}` 替换为具体错误信息，不暴露 stack trace |

---

## R7 — 进度可视化与空状态

| ID | 位置 | 占位文案 | 说明 |
|----|------|---------|------|
| COPY-019 | CreateView → 无项目空状态标题 | `还没有项目` | 侧栏无项目时的引导区块标题（empty-state 模式）|
| COPY-020 | CreateView → 无项目空状态描述 | `先导入素材，再新建项目开始创作` | 空状态引导区块说明文字 |
| COPY-021 | CreateView → 无项目空状态按钮 | `新建项目` | 空状态区块主操作按钮 |
| COPY-022 | Job 进度 → Step 1 素材分析描述 | `正在分析素材...` | 后端 job description 字段的前端兜底文案（Step 1）|
| COPY-023 | Job 进度 → 已处理数量格式 | `已处理 {processed} / {total} 个文件` | 进度展示，字段不存在时不显示此行 |

---

## R7 — 标签种子数据（DATA-001）

> ⚠️ 以下分类和标签为**占位内容**，正式发布前请内容运营确认是否符合目标用户（短视频创作者）的实际使用习惯。

| ID | 内容 | 说明 |
|----|------|------|
| COPY-SEED-01 | tag_category 分类（占位）: `场景`、`人物`、`动作`、`情绪`、`构图`、`色调`、`画质` | 7 个基础分类，每个素材可打多个类别的标签 |
| COPY-SEED-02 | `场景` 基础标签（占位）: 室内、室外、城市、自然、水面、山地、夜景 | |
| COPY-SEED-03 | `人物` 基础标签（占位）: 单人、多人、无人、近景人物、群体 | |
| COPY-SEED-04 | `动作` 基础标签（占位）: 行走、静止、运动、交谈、特写动作 | |
| COPY-SEED-05 | `情绪` 基础标签（占位）: 轻松、活力、安静、戏剧性 | |
| COPY-SEED-06 | `构图` 基础标签（占位）: 横构图、竖构图、中心构图、三分法 | |
| COPY-SEED-07 | `色调` 基础标签（占位）: 暖色调、冷色调、高饱和、低饱和、黑白 | |
| COPY-SEED-08 | `画质` 基础标签（占位）: 清晰、模糊、噪点、曝光过度、曝光不足 | |

---

## R10 — 视觉一致性

| ID | 位置 | 占位文案 | 说明 |
|----|------|---------|------|
| COPY-024 | TagBrowser.vue → 空库状态说明 | `暂无标签，导入并分析素材后自动生成` | 素材库为空时 TagBrowser 面板的说明文字 |
| COPY-025 | CreateView → Canvas 入口使用场景说明 | `自由模式：拖拽节点连接各模块，适合非线性创作` | 帮助用户区分 Canvas 和引导式工作流 |
| COPY-026 | CreateView → 引导式工作流区域说明 | `标准模式：按 7 步流程完成素材→脚本→剪辑→发布` | 帮助用户理解引导式工作流的定位 |

---

## ~~尚待产品确认的非文案事项~~（已全部解决）

> 以下问题已于 2026-03-21 V5.0 通过代码读取或产品授权全部解决，不再阻塞任何任务。

| 问题 | 解决方式 |
|------|---------|
| Q1 - provider 枚举值 | ✅ 代码中 `_AI_PROVIDER_CATALOG` 已定义：openai / anthropic / moonshot / qwen / gemini / maxmini |
| Q3 - `GET /api/projects` 响应字段 | ✅ 产品授权：project_id / name / project_dir / videos_dir / created_at / updated_at / workflow_count |
| Q4 - `GET /api/workflow/status` 字段 | ✅ 产品授权：persisted / current_run_id / status / current_step / guidedAvailable（不暴露原始 workflow.json）|
| Q5 - `GET /api/settings` 聚合范围 | ✅ 产品授权：ai（provider/model/api_key 脱敏）+ ui（主题/语言），api_key 用 `_mask_secret()` 处理 |
| Q12 - Step 3 脚本输出 JSON 格式 | ✅ 从 jianying_draft.py 代码反推：`{ title, description, clips[{source_asset_id, start_ms, end_ms, description}], subtitles[{start_ms, end_ms, text}], bgm{source, asset_id, volume} }` |
| Q13 - requirements.txt 必选/可选分类 | ✅ 代码注释已明确：Flask/numpy/Pillow/opencv/ffmpeg-python/pywebview = 必选；torch/transformers/mediapipe/librosa = 可选 |
| Q15 - 应用品牌名称 | ✅ 产品授权：统一用 **VideoEditor**（与代码/文档/commit 一致），中文界面说明文字用"视频编辑器" |
| Q17 - Library 拆分目录结构 | ✅ 产品授权：确认计划中的参考结构（core / maintenance / tagging / integrations / db）|

---

*文件更新于 2026-03-21 | v5.0 — 全部待确认项已解决，无阻塞项*
