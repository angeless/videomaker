# VideoEditor 版本开发计划（v0.15.0）

**文档版本：** V1.0
**日期：** 2026-03-31
**基线 Commit：** 待定（v0.14.0 完成后）
**基线 VERSION：** 0.14.0

---

## 1. 版本目标

核心评审 UI（播放器 + 时间轴 + 评论系统 + 快捷键）+ 高级标注（画笔 + 形状 + 缩略图条 + 波形 + 字幕编辑 + 安全帧），为 v0.16.0 AI 重编辑引擎打基础。

## 2. 版本范围

### 包含的需求

- 视频播放器（逐帧导航 + SMPTE timecode + 倍速 + 循环 + 全屏 + 画面缩放）
- 评论系统 UI（评论输入 + 评论面板 + 时间区间选择 + 7 种评论类型）
- 时间轴整合（评论标记轨道 + 缩略图条 + 波形）
- 画笔/形状标注（Canvas 叠加层 + 8 种工具 + 撤销重做）
- 字幕编辑器（SRT/VTT 编辑 + 时间轴对齐）
- 安全帧叠加（9:16 / 16:9 / 1:1 / 4:5）
- 键盘快捷键系统
- ReviewView.vue 页面整合 + review.js Store
- 缩略图 sprite sheet 生成（FFmpeg）
- 波形数据生成（FFmpeg）

### 不包含的需求（Future）

| 需求 | 推迟到 |
|------|--------|
| AI 重编辑引擎（CommentResolver + IntentRouter + EditPlanner） | v0.16.0 |
| 版本 diff + AI 回复 | v0.16.0 |
| 音频增强 / TTS / BGM / 转场 / reframe | v0.16.0 |
| Stock 素材搜索 / Style Skill / 评论导出 | v0.16.0 |

---

## 3. 任务列表

| 任务ID | 任务名称 | 优先级 | 状态 |
|--------|---------|--------|------|
| R1 | ReviewPlayer.vue — 视频播放 + 逐帧导航 | P0 | Planned |
| R2 | PlayerControls.vue — 播放控制栏 + SMPTE | P0 | Planned |
| R3 | PlayerControls.vue — 倍速 + 循环 + 音量 | P0 | Planned |
| R4 | PlayerControls.vue — 画面缩放/平移 + 全屏 | P1 | Planned |
| R5 | CommentInput.vue — 评论输入 + 类型选择 | P0 | Planned |
| R6 | CommentCard.vue — 单条评论展示 + 操作 | P0 | Planned |
| R7 | CommentPanel.vue — 评论列表 + 筛选/排序 | P0 | Planned |
| R8 | TrackComments.vue — 时间轴评论标记轨道 | P0 | Planned |
| R9 | ReviewTimeline.vue — 时间轴容器 + 缩放/拖拽 | P0 | Planned |
| R10 | 键盘快捷键系统 (useKeyboardShortcuts) | P0 | Planned |
| R11 | review.js Store + ReviewView.vue 页面整合 | P0 | Planned |
| R12 | DrawingOverlay.vue — Canvas 画笔 + 自由绘制 | P1 | Planned |
| R13 | DrawingOverlay.vue — 形状工具 (矩形/椭圆/箭头/线/文字) | P1 | Planned |
| R14 | AnnotationToolbar.vue — 工具栏 + 调色板 + 撤销重做 | P1 | Planned |
| R15 | DrawingOverlay.vue — 聚光灯 + 模糊标注 | P2 | Planned |
| R16 | 缩略图 sprite sheet 生成 (FFmpeg) | P1 | Planned |
| R17 | ThumbnailStrip.vue — 缩略图条 + 悬停预览 | P1 | Planned |
| R18 | 波形数据生成 (FFmpeg) | P1 | Planned |
| R19 | WaveformTrack.vue — 波形可视化 | P1 | Planned |
| R20 | SubtitleEditor.vue — 字幕轨道编辑 | P1 | Planned |
| R21 | SafeZoneOverlay.vue — 安全帧叠加 | P2 | Planned |
| R22 | VersionSwitcher.vue — 版本切换 UI | P1 | Planned |
| R23 | 集成测试 + 回归测试 | P0 | Planned |

---

## 4. 各任务详细定义

### R1: ReviewPlayer.vue — 视频播放 + 逐帧导航

**目标：** 专业级视频播放器组件，支持逐帧导航和 seek。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/ReviewPlayer.vue` — 新建
- `tests/ui/review/test_review_player.py` — 新建（API 交互测试）

**输入：** video_path (from store), currentTime, playbackRate
**输出：** 视频播放 + 帧精确 seek + currentTime 双向绑定

**验收标准：**
- [ ] HTML5 `<video>` 标签加载视频并播放
- [ ] 逐帧导航: `←` 后退 1 帧 (1/fps), `→` 前进 1 帧
- [ ] 拖拽 seek bar 跳转到指定时间
- [ ] currentTime 变化时 emit 事件 (供评论面板同步)
- [ ] 错误状态: 视频加载失败 → 显示错误提示

**依赖项：** 无
**已知约束：** HTML5 video 逐帧精度依赖浏览器实现，pywebview 使用 WebKit

---

### R2: PlayerControls.vue — 播放控制栏 + SMPTE

**目标：** 播放/暂停、前进/后退、SMPTE timecode 显示。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/PlayerControls.vue` — 新建

**输入：** currentTime, duration, fps
**输出：** 播放控制操作 (play/pause/seek) + SMPTE 时间显示

**验收标准：**
- [ ] 播放/暂停按钮 (▶/⏸ 切换)
- [ ] -5s / -1帧 / +1帧 / +5s 按钮
- [ ] SMPTE timecode 显示 (HH:MM:SS:FF)
- [ ] 进度条 + 拖拽 seek
- [ ] 已播放时间 / 总时长显示

**依赖项：** R1
**已知约束：** 无

---

### R3: PlayerControls.vue — 倍速 + 循环 + 音量

**目标：** 播放倍速切换、I/O 入出点循环、音量控制。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/PlayerControls.vue` — 扩展

**输入：** playbackRate, volume, loopIn, loopOut
**输出：** 倍速/音量控制操作

**验收标准：**
- [ ] 倍速切换: 0.25x / 0.5x / 1x / 1.5x / 2x / 4x
- [ ] J/K/L 快捷键: 倒放/暂停/正放，连按 L 加速
- [ ] I 键设入点, O 键设出点
- [ ] Cmd+L 循环播放入出点区间
- [ ] 音量滑块 + 静音按钮

**依赖项：** R2
**已知约束：** 倒放 (J 键) 可能需要逐帧模拟

---

### R4: PlayerControls.vue — 画面缩放/平移 + 全屏

**目标：** 画面缩放检查细节，全屏模式。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/PlayerControls.vue` — 扩展
- `apps/desktop/ui-vue/src/components/review/ReviewPlayer.vue` — 扩展 (缩放逻辑)

**输入：** zoomLevel, panOffset
**输出：** 缩放/平移/全屏操作

**验收标准：**
- [ ] Cmd+滚轮 缩放 (1x-4x)
- [ ] 缩放后鼠标拖拽平移
- [ ] [适应] 按钮重置到适应窗口
- [ ] F 键切换全屏
- [ ] Esc 退出全屏

**依赖项：** R1
**已知约束：** pywebview 全屏 API

---

### R5: CommentInput.vue — 评论输入 + 类型选择

**目标：** 评论输入组件，支持 7 种评论类型和时间区间选择。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/CommentInput.vue` — 新建

**输入：** currentTime, loopIn/loopOut (可选区间)
**输出：** 新评论对象 (type, text, time_start_ms, time_end_ms)

**验收标准：**
- [ ] C 键打开评论输入框，自动填入当前 timecode
- [ ] 7 种评论类型: cut(🔴) / keep(🟢) / modify(🔵) / transition(🟡) / audio(🟣) / subtitle(🟤) / general(⚪)
- [ ] 数字键 1-7 快速切换类型
- [ ] 支持设置时间区间 (start + end)
- [ ] Cmd+Enter 提交评论
- [ ] 提交后调用 API 并更新 store

**依赖项：** R11 (store)
**已知约束：** 无

---

### R6: CommentCard.vue — 单条评论展示 + 操作

**目标：** 单条评论卡片，显示时间、类型、内容和操作按钮。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/CommentCard.vue` — 新建

**输入：** comment 对象
**输出：** 展示 + 操作 (编辑/删除/跳转)

**验收标准：**
- [ ] 评论类型颜色图标
- [ ] 时间戳显示 (HH:MM:SS)，区间评论显示 start-end
- [ ] 评论文字 + 画笔缩略图 (如有)
- [ ] 状态标记: pending / resolved / rejected
- [ ] AI 回复显示 (如有，灰色 🤖 前缀)
- [ ] [编辑] [删除] [跳转] 操作按钮
- [ ] 点击 → 视频跳转到评论时间

**依赖项：** R5
**已知约束：** 无

---

### R7: CommentPanel.vue — 评论列表 + 筛选/排序

**目标：** 右侧评论面板，列表展示所有评论，支持筛选和排序。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/CommentPanel.vue` — 新建

**输入：** comments[] (from store)
**输出：** 筛选/排序后的评论列表

**验收标准：**
- [ ] 评论计数标题 "评论 (N)"
- [ ] 筛选: 按类型 / 按状态 (全部/pending/resolved)
- [ ] 排序: 时间 / 类型 / 状态
- [ ] `[` / `]` 键跳转上/下一条评论
- [ ] 当前播放时间附近的评论高亮

**依赖项：** R6, R11
**已知约束：** 无

---

### R8: TrackComments.vue — 时间轴评论标记轨道

**目标：** 在时间轴上用彩色标记显示评论位置。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/TrackComments.vue` — 新建

**输入：** comments[], duration, timelineScale
**输出：** 时间轴上的评论标记

**验收标准：**
- [ ] 点评论 → 彩色三角标记 (颜色=评论类型)
- [ ] 区间评论 → 彩色条带
- [ ] 悬停标记 → tooltip 显示评论摘要
- [ ] 点击标记 → 跳转到评论时间 + 高亮评论卡片
- [ ] resolved 评论半透明 (区分 pending)

**依赖项：** R9
**已知约束：** 无

---

### R9: ReviewTimeline.vue — 时间轴容器 + 缩放/拖拽

**目标：** 时间轴容器组件，管理缩放级别和拖拽 seek。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/ReviewTimeline.vue` — 新建

**输入：** duration, currentTime
**输出：** timelineScale, seek 操作

**验收标准：**
- [ ] 时间刻度尺 (自适应精度: 1s/5s/10s/30s/1min)
- [ ] Cmd+/- 缩放时间轴
- [ ] 拖拽 playhead 跳转
- [ ] 滚轮横向滚动
- [ ] 播放时 playhead 自动跟随
- [ ] slot 插入子轨道 (评论/缩略图/波形)

**依赖项：** R1
**已知约束：** 无

---

### R10: 键盘快捷键系统

**目标：** 统一的快捷键管理，避免冲突，支持模式切换。

**涉及文件：**
- `apps/desktop/ui-vue/src/composables/useKeyboardShortcuts.js` — 新建
- `apps/desktop/ui-vue/src/config/shortcuts.js` — 新建 (快捷键映射表)

**输入：** 当前模式 (normal/drawing/comment)
**输出：** 事件分发

**验收标准：**
- [ ] 快捷键映射表 (见总参考文档 §4.3)
- [ ] 模式感知: 画笔模式下 1-7 不触发评论类型切换
- [ ] 输入框聚焦时禁用单键快捷键
- [ ] Space 播放/暂停, J/K/L, ←/→, I/O, C, D, F, R, [/], Cmd+Z 等
- [ ] Esc 退出画笔模式/全屏

**依赖项：** R1, R5
**已知约束：** pywebview 可能拦截部分系统快捷键

---

### R11: review.js Store + ReviewView.vue 页面整合

**目标：** 前端状态管理 + 评审页面布局整合。

**涉及文件：**
- `apps/desktop/ui-vue/src/stores/review.js` — 新建
- `apps/desktop/ui-vue/src/views/ReviewView.vue` — 新建

**输入：** API 响应
**输出：** 响应式状态 + 页面布局

**验收标准：**
- [ ] store: session, comments[], versions[], currentVersion, currentTime, mode 状态
- [ ] API 调用封装: loading/error 状态
- [ ] ReviewView 布局: 左上播放器 + 左下时间轴 + 右侧评论面板
- [ ] 从 RoughCutView 进入评审: "进入评审" 按钮 → 路由跳转
- [ ] 版本切换 (Cmd+[/]) → 加载对应版本视频

**依赖项：** v0.14.0 R26-R28 (评审 API)
**已知约束：** 无

---

### R12: DrawingOverlay.vue — Canvas 画笔 + 自由绘制

**目标：** Canvas 叠加在视频上，支持自由画笔绘制。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/DrawingOverlay.vue` — 新建

**输入：** 视频尺寸, 当前帧
**输出：** 画笔数据 (points[], color, width)

**验收标准：**
- [ ] Canvas 精确覆盖视频区域
- [ ] D 键进入画笔模式, Esc 退出
- [ ] 鼠标按下+移动 = 绘制线条
- [ ] 7 色可选 (红/橙/黄/绿/蓝/紫/白)
- [ ] 3 级粗细 (1px/3px/5px)
- [ ] 绘制完成 → 序列化为 JSON + 生成 WebP 缩略图

**依赖项：** R1
**已知约束：** Canvas 坐标需映射到视频原始分辨率

---

### R13: DrawingOverlay.vue — 形状工具

**目标：** 矩形、椭圆、箭头、直线、文字标注。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/DrawingOverlay.vue` — 扩展

**输入：** 当前工具, 起点/终点
**输出：** 形状数据 (tool, points[], color, width, text?)

**验收标准：**
- [ ] 矩形: 拖拽绘制, Shift 约束正方形
- [ ] 椭圆: 拖拽绘制, Shift 约束正圆
- [ ] 箭头: 起点→终点 + 箭头
- [ ] 直线: 起点→终点, Shift 约束水平/垂直/45°
- [ ] 文字: 点击后输入文字，字号可调
- [ ] 所有形状支持 7 色 + 3 级粗细

**依赖项：** R12
**已知约束：** 无

---

### R14: AnnotationToolbar.vue — 工具栏 + 调色板 + 撤销重做

**目标：** 标注工具栏 UI + 撤销重做栈。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/AnnotationToolbar.vue` — 新建

**输入：** 当前工具/颜色/粗细
**输出：** 工具/颜色/粗细选择 + undo/redo

**验收标准：**
- [ ] 8 种工具按钮 (画笔/矩形/椭圆/箭头/线/文字/聚光灯/模糊)
- [ ] 7 色调色板
- [ ] 3 级粗细选择
- [ ] 透明度滑块
- [ ] Cmd+Z 撤销, Cmd+Shift+Z 重做
- [ ] 橡皮擦 (逐笔删除)
- [ ] [清除全部] 按钮

**依赖项：** R12
**已知约束：** 无

---

### R15: DrawingOverlay.vue — 聚光灯 + 模糊标注

**目标：** 聚光灯效果（高亮区域，其余变暗）和模糊标注。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/DrawingOverlay.vue` — 扩展

**输入：** 选区
**输出：** 聚光灯/模糊效果

**验收标准：**
- [ ] 聚光灯: 选区内正常，选区外半透明黑色遮罩
- [ ] 模糊: 选区内应用 CSS blur 效果
- [ ] 均支持矩形和椭圆选区
- [ ] 序列化保存 (tool + region)

**依赖项：** R13
**已知约束：** CSS blur 在 Canvas 上可能需要离屏渲染

---

### R16: 缩略图 sprite sheet 生成

**目标：** 用 FFmpeg 从视频生成 sprite sheet，供时间轴悬停预览。

**涉及文件：**
- `modules/review_engine/thumbnail_generator.py` — 新建
- `tests/unit/review_engine/test_thumbnail_generator.py` — 新建

**输入：** video_path, interval_sec (默认 1s)
**输出：** sprite sheet 图片 + 元数据 JSON (行列数, 单帧尺寸)

**验收标准：**
- [ ] 每 1s 截取一帧，缩放到 160x90
- [ ] 拼接为 sprite sheet (每行 10 帧)
- [ ] 输出元数据: `{cols, rows, width, height, interval, total_frames}`
- [ ] 3min 视频 < 5s 生成
- [ ] FFmpeg: timeout 60s + stderr 捕获 + 重试 2 次
- [ ] UT 2 条: generates_sprite / metadata_correct

**依赖项：** 无 (FFmpeg)
**已知约束：** 长视频 sprite sheet 可能很大，考虑分段

---

### R17: ThumbnailStrip.vue — 缩略图条 + 悬停预览

**目标：** 时间轴下方缩略图条，鼠标悬停显示该时间点的帧。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/ThumbnailStrip.vue` — 新建

**输入：** spriteSheet URL, metadata
**输出：** 缩略图条 + 悬停预览弹窗

**验收标准：**
- [ ] 沿时间轴水平排列缩略图
- [ ] 鼠标悬停 → 放大预览弹窗 (从 sprite sheet 裁剪对应帧)
- [ ] 跟随时间轴缩放级别调整显示密度
- [ ] 点击缩略图 → seek 到对应时间

**依赖项：** R9, R16
**已知约束：** 使用 CSS background-position 从 sprite sheet 裁剪

---

### R18: 波形数据生成

**目标：** 用 FFmpeg 从视频音轨生成波形数据。

**涉及文件：**
- `modules/review_engine/waveform_generator.py` — 新建
- `tests/unit/review_engine/test_waveform_generator.py` — 新建

**输入：** video_path, samples_per_second (默认 10)
**输出：** JSON 波形数据 `{samples: [float], sample_rate, duration}`

**验收标准：**
- [ ] 提取音轨 → 计算 RMS 幅值
- [ ] 默认每秒 10 个采样点
- [ ] 归一化到 0.0-1.0 范围
- [ ] 无音轨 → 返回空数组 + 标记
- [ ] 3min 视频 < 3s 生成
- [ ] FFmpeg: timeout 60s + stderr 捕获 + 重试 2 次
- [ ] UT 2 条: generates_samples / no_audio_returns_empty

**依赖项：** 无 (FFmpeg)
**已知约束：** 无

---

### R19: WaveformTrack.vue — 波形可视化

**目标：** 时间轴中的音频波形轨道。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/WaveformTrack.vue` — 新建

**输入：** waveformData (from store), timelineScale
**输出：** 波形 Canvas 绘制

**验收标准：**
- [ ] Canvas 绘制波形 (镜像上下对称)
- [ ] 跟随时间轴缩放
- [ ] 播放位置高亮 (playhead 前后颜色不同)
- [ ] 静音段显示为贴底线

**依赖项：** R9, R18
**已知约束：** Canvas 重绘需要节流 (requestAnimationFrame)

---

### R20: SubtitleEditor.vue — 字幕轨道编辑

**目标：** 在时间轴上编辑字幕（修改文字、调整时间）。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/SubtitleEditor.vue` — 新建

**输入：** subtitles[] (from transcript), timelineScale
**输出：** 修改后的字幕列表

**验收标准：**
- [ ] 时间轴上显示字幕条 (每条字幕一个色块)
- [ ] 双击色块 → 编辑字幕文字
- [ ] 拖拽色块边缘 → 调整开始/结束时间
- [ ] 拖拽色块 → 移动字幕时间
- [ ] 右键 → 删除字幕 / 拆分 / 合并
- [ ] 变更后同步更新 store

**依赖项：** R9, R11
**已知约束：** 字幕数据来自 v0.14.0 的转录结果

---

### R21: SafeZoneOverlay.vue — 安全帧叠加

**目标：** 在视频上叠加不同平台的安全帧标记。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/SafeZoneOverlay.vue` — 新建

**输入：** 当前选择的安全帧比例
**输出：** 半透明遮罩叠加

**验收标准：**
- [ ] 支持: 无 / 9:16 / 16:9 / 1:1 / 4:5
- [ ] 安全区域内清晰，区域外半透明遮罩
- [ ] 切换比例时平滑过渡
- [ ] 📐 按钮切换 + 下拉菜单

**依赖项：** R1
**已知约束：** 无

---

### R22: VersionSwitcher.vue — 版本切换 UI

**目标：** 版本列表 + 快速切换 + 回退按钮。

**涉及文件：**
- `apps/desktop/ui-vue/src/components/review/VersionSwitcher.vue` — 新建

**输入：** versions[] (from store)
**输出：** 版本切换操作

**验收标准：**
- [ ] 版本下拉列表 (v1 粗剪 → v2 AI修改 → ...)
- [ ] Cmd+[ / Cmd+] 快捷切换
- [ ] [回退到此版本] 按钮 → 调用 rollback API
- [ ] 当前版本高亮
- [ ] 版本变更摘要显示

**依赖项：** R11, v0.14.0 R27
**已知约束：** 无

---

### R23: 集成测试 + 回归测试

**目标：** 端到端验证评审 UI 功能 + 回归。

**涉及文件：**
- `tests/integration/test_review_ui_flow.py` — 新建
- `tests/conftest.py` — 新增 fixtures

**输入：** 测试视频 + v0.14.0 生成的粗剪
**输出：** 测试报告

**验收标准：**
- [ ] IT: 加载粗剪视频 → 添加评论 → 评论显示在时间轴 → 筛选
- [ ] IT: 画笔标注 → 序列化 → 反序列化 → 显示
- [ ] IT: sprite sheet 生成 → 缩略图条加载
- [ ] IT: 波形生成 → 波形轨道显示
- [ ] REG: `pytest project/tests/ -v` 全量 0 失败
- [ ] 测试报告: `docs/test-reports/test-report-v0.15.0-release.md`

**依赖项：** R1-R22
**已知约束：** UI 交互测试可能需要模拟 DOM

---

## 5. 完成状态追踪

| 任务 | 计划周期 | 实际完成 | 迭代 | 备注 |
|------|---------|---------|------|------|
| R1-R4 | 2 天 | — | 0 | 播放器 |
| R5-R8 | 1.5 天 | — | 0 | 评论系统 |
| R9-R11 | 1.5 天 | — | 0 | 时间轴+整合 |
| R12-R15 | 2 天 | — | 0 | 画笔标注 |
| R16-R19 | 1.5 天 | — | 0 | 缩略图+波形 |
| R20-R22 | 1 天 | — | 0 | 字幕+安全帧+版本 |
| R23 | 1 天 | — | 0 | 测试 |
| **总计** | **10.5 天** | | | |

## 6. 决策和假设

| # | 内容 | 理由 |
|---|------|------|
| D1 | 使用 HTML5 `<video>` 而非自定义播放器 | pywebview 环境下最简单可靠 |
| D2 | Canvas 叠加层实现画笔 (非 SVG) | 性能更好，自由绘制更自然 |
| D3 | sprite sheet 而非逐帧图片 | 减少 HTTP 请求，Clapshot 也是此方案 |
| A1 | 视频 fps ≤ 60 | 逐帧导航精度 |
| A2 | v0.14.0 评审 API 可用 | 依赖数据层 |

## 7. 风险和缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| pywebview Canvas 性能不足 | 中 | 中 | 简化画笔渲染，降低实时性 |
| 逐帧导航不精确 | 中 | 低 | 文档标注限制 (±1帧) |
| 长视频 sprite sheet 过大 | 低 | 中 | 分段生成，按需加载 |

## 8. 变更记录

| 版本 | 日期 | 变更 | 责任人 |
|------|------|------|--------|
| V1.0 | 2026-03-31 | 初版，23 个 R 任务 | Claude Code |

---

*文档结束*
