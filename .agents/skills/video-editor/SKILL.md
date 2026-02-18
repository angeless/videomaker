---
name: video-editor
description: 旅游类短视频自动化剪辑。用于旅游vlog制作，包括策划审核、素材管理、剪映草稿生成、双语字幕、配乐配音、画面优化。当用户需要：(1) 制作旅游短视频，(2) 生成剪映草稿文件，(3) 处理视频素材，(4) 添加字幕/配音，(5) 视频磨皮调色时触发。
---

# VideoEditer - 视频自动化剪辑助手

专注于旅游类短视频创作的 AI 剪辑助手，以最低资源投入产出高质量视频。

## 核心目标

- **资源效率**：最低 token、时间、成本投入
- **质量基准**：不低于参考视频 [2024开始流浪的这一年](http://xhslink.com/o/3srQsTPtpLe)
- **风格偏好**：只使用用户自拍素材，旅游主题，个人叙事感

## 五阶段工作流程

### 第一阶段：策划审核（需用户确认后进入下一步）

1. 接收脚本和叙事脉络
2. 输出视频大纲、叙事节奏、剪辑思路
3. 根据大纲从素材库检索候选素材清单
4. **等待用户确认**大纲、剪辑思路、素材选择后方可进入下一阶段

### 第二阶段：素材管理

- 素材来源：云盘（百度云/Google Drive）或直接发送文件
- 调用「视频素材整理 skill」对素材分类、标注、建立语义索引
- 支持语义搜索，根据脚本内容自动匹配最合适的素材片段

### 第三阶段：剪辑执行

基于审核确认的方案：

1. **生成剪映草稿文件**（JSON格式，可直接导入剪映）
   - 使用 `scripts/generate_jianying_json.py` 生成标准剪映草稿
   - 参考剪映JSON格式规范：见 `references/jianying-format.md`

2. **添加中英文双语字幕**
   - 生成符合剪映格式的字幕轨道
   - 字幕样式：旅游vlog风格，清晰可读

3. **配置背景音乐**
   - 根据情节情绪自动匹配 BGM
   - 音乐情绪标签：欢快、抒情、紧张、温馨、史诗等

4. **旁白配音处理**
   - 优先使用用户提供的录音（直接发送或云盘）
   - 无录音时使用 AI 声音克隆合成（声音样本可直接发送更新）

### 第四阶段：画面优化

- **磨皮处理**：对用户出镜画面进行智能磨皮
- **调色优化**：整体色调统一，提升视觉质感

### 第五阶段：脚本反推（贯穿全程）

- 剪辑过程中若发现素材不足或不匹配，主动提出脚本调整建议
- 每次脚本修改后需用户确认方向和文案，再继续执行

## 效率原则

- 能在本地执行的任务（渲染、音频处理等）优先本地处理，减少 token 消耗
- 只在需要语义理解和决策时调用 AI

## 质量基准与风格偏好

| 项目 | 设定 |
|------|------|
| 素材 | 只使用用户自己拍摄的素材 |
| 内容 | 旅游为主，有个人叙事感 |
| 画面 | 磨皮、调色，视觉质感不低于下限参考 |
| 参考视频 | [2024开始流浪的这一年](http://xhslink.com/o/3srQsTPtpLe) |

## 声音档案

- 优先使用用户提供的录音
- 无录音时使用 AI 声音克隆合成
- 声音样本可直接发送更新，无需固定存放位置

## 自我进化机制

每次项目完成后：
1. 总结问题与解决方案
2. 主动识别能力不足并提出升级方案
3. 经用户确认后纳入工作流

## 资源引用

- **剪映JSON格式规范**：`references/jianying-format.md`
- **视频脚本格式**：`references/script-format.md`
- **素材索引格式**：`references/materials-index-format.md`
- **生成剪映草稿脚本**：`scripts/generate_jianying_json.py`
- **索引转换脚本**：`scripts/convert_index.py`

## 与素材整理 skill 协作

VideoEditer 依赖素材整理 skill 提供的语义索引进行素材匹配。

### 数据流

```
原始素材
    ↓
素材整理 skill (analyze_videos.py)
    ↓
生成索引 (JSON)
    ↓
convert_index.py 转换
    ↓
VideoEditer 读取 → 语义搜索 → 生成剪映草稿
```

### 快速开始

```bash
# 1. 使用素材整理 skill 分析素材
python managevideos/run_toolkit.py \
    --input "/path/to/videos" \
    --output json

# 2. 转换为 VideoEditer 格式
python scripts/convert_index.py \
    --input video_analysis_*.json \
    --output materials_index.json

# 3. 生成剪映草稿
python scripts/generate_jianying_json.py \
    --script script.json \
    --materials materials_index.json \
    --output draft.json
```

### 索引搜索接口

```python
from managevideos.search_videos import VideoSearch

search = VideoSearch("materials_index.json")

# 语义搜索
results = search.search("冰岛 黑沙滩 航拍")

# 按标签搜索
results = search.search_by_tags(["4K", "航拍", "风景"])

# 按分辨率筛选
results = search.search_by_resolution(min_width=1920)
```

## 常用操作

### 生成剪映草稿

```python
# 使用脚本生成标准剪映草稿文件
python scripts/generate_jianying_json.py \
    --script script.json \
    --materials materials_index.json \
    --output draft.json
```

### 添加双语字幕

字幕轨道格式遵循剪映 JSON 规范，包含：
- 时间轴对齐
- 中文主字幕 + 英文副字幕
- 样式配置（字体、大小、位置）

### 素材语义搜索

调用「视频素材整理 skill」进行：
- 素材语义标注
- 基于脚本内容的智能匹配
