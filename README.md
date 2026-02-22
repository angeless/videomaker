# VideoEditer - 旅游短视频自动化剪辑工具箱

专为旅游类短视频创作设计的 AI 剪辑助手，包含素材管理和剪辑执行两大核心模块。

## 🎯 项目概述

本项目包含两个 Kimi Skill：

| Skill | 功能 | 触发场景 |
|-------|------|----------|
| **manage-videos** | 视频素材语义索引与搜索 | 素材整理、语义标注、智能检索 |
| **video-editor** | 视频剪辑执行与剪映草稿生成 | 脚本审核、剪辑执行、画面优化 |

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/videoediter.git
cd videoediter

# 安装依赖
pip install -r requirements.txt

# 确保 FFmpeg 已安装
ffmpeg -version
```

### 完整工作流（全自动渲染）

```bash
# 1. 分析素材（manage-videos）
python .agents/skills/manage-videos/run_toolkit.py \
    --input "/path/to/videos" \
    --output json

# 2. 转换索引格式（video-editor）
python .agents/skills/video-editor/scripts/convert_index.py \
    --input results/video_analysis_*.json \
    --output materials_index.json

# 3. 剧本自适应重写（video-editor）
python .agents/skills/video-editor/scripts/adaptive_rewriter.py \
    --script script.json \
    --materials materials_index.json \
    --output script_final.json

# 4. 全自动渲染（video-editor）- 无需剪映！
python .agents/skills/video-editor/scripts/auto_render.py \
    --script script_final.json \
    --materials materials_index.json \
    --output final_video.mp4 \
    --width 1080 --height 1920

# ✅ 完成！直接得到成品视频
```

### 传统方式（剪映草稿）

如需剪映手动调整：

```bash
python .agents/skills/video-editor/scripts/generate_jianying_json.py \
    --script your-script.json \
    --materials materials_index.json \
    --output draft.json
# 然后在剪映中导入 draft.json
```

## 📁 项目结构

```
videoeditor/
├── README.md
├── LICENSE
├── requirements.txt
└── .agents/skills/
    ├── manage-videos/              # 素材管理 skill
    │   ├── SKILL.md
    │   ├── video_asset_toolkit.py  # 多格式分析（JSON/Markdown/CSV）
    │   ├── search_videos.py        # 关键词/标签/分辨率搜索
    │   ├── run_toolkit.py          # CLI 入口
    │   ├── analyze_videos.py       # 本地 vs 云端分析对比
    │   └── indexer/                # ★ 高级索引（来自 opencut）
    │       ├── fingerprint.py      # pHash 去重 + SQLite
    │       └── semantic.py         # CLIP 语义搜索（中英文）
    └── video-editor/               # 剪辑执行 skill
        ├── SKILL.md
        └── scripts/
            ├── generate_jianying_json.py  # 剪映草稿生成
            ├── convert_index.py           # 索引格式转换
            ├── auto_render.py             # FFmpeg 全自动渲染
            ├── adaptive_rewriter.py       # 剧本自适应重写
            ├── orchestrator.py            # 三级确认 + 超时熔断
            └── render/                    # ★ 渲染子模块（来自 opencut）
                ├── beauty.py              # 频率分解磨皮（MediaPipe）
                └── pipeline.py            # 完整渲染管道（含音频混合）
```

## 🛠️ 功能特性

### manage-videos（素材管理）

- **批量分析**：技术质量、内容标签、地点识别
- **质量评分**：分辨率、码率综合评估
- **★ pHash 去重**：感知哈希 + SQLite，秒速检测 8TB 素材库中的重复片段
- **★ CLIP 语义搜索**：中英文文本直接匹配视频内容（未安装时自动降级关键词）

### video-editor（剪辑执行）

- **五阶段工作流**：策划 → 素材 → 剪辑 → 优化 → 反推
- **剪映集成**：生成可直接导入的 JSON 草稿
- **双语字幕**：中英文双字幕轨道
- **智能匹配**：根据脚本语义自动匹配素材
- **★ 频率分解磨皮**：MediaPipe 人脸检测 + 频率分离，精准处理毛孔/痘印
- **★ 三级确认熔断**：10 分钟超时自动降级 + 可选 Discord 通知
- **★ 剧本自适应重写**：素材不足时自动改戏（词汇替换 + 通用文案）

## 📖 使用指南

### 素材整理

```python
from .agents.skills.manage-videos.video_asset_toolkit import VideoAssetToolkit

# 初始化工具箱
toolkit = VideoAssetToolkit()

# 分析单个视频
result = toolkit.analyze_videos("/path/to/video.mp4")

# 批量分析
results = toolkit.analyze_videos("/path/to/video_folder/")
```

### 语义搜索

```python
from .agents.skills.manage-videos.search_videos import VideoSearch

# 加载索引
search = VideoSearch("video_index.json")

# 关键词搜索
results = search.search("冰岛 黑沙滩 航拍")

# 标签搜索
results = search.search_by_tags(["4K", "风景"])

# 分辨率筛选
results = search.search_by_resolution(min_width=1920)
```

### 生成剪映草稿

```python
from .agents.skills.video-editor.scripts.generate_jianying_json import JianyingDraftBuilder

# 创建构建器
builder = JianyingDraftBuilder(width=1080, height=1920)

# 添加视频片段
builder.add_video_clip(clip)

# 添加字幕
builder.add_bilingual_subtitle("中文", "English", 0, 5)

# 保存草稿
builder.save("draft.json")
```

## 🔧 配置文件

`config.json` 示例：

```json
{
  "local_models": {
    "enabled": true,
    "object_detection": true,
    "scene_description": true,
    "technical_analysis": true
  },
  "cloud_models": {
    "enabled": false,
    "gemini_api_key": "",
    "openai_api_key": ""
  }
}
```

## 📋 数据格式

### 脚本格式 (script.json)

```json
{
  "title": "2024 冰岛之旅",
  "clips": [
    {
      "path": "/素材/DJI_0001.mp4",
      "start_time": 0,
      "end_time": 8
    }
  ],
  "subtitles": [
    {
      "cn_text": "冰岛的黑沙滩",
      "en_text": "Iceland's black sand beach",
      "start_time": 0,
      "end_time": 5
    }
  ]
}
```

### 素材索引格式

详见 `.agents/skills/video-editor/references/materials-index-format.md`

## 🤝 Skill 协作

```
manage-videos (素材管理)
        │
        ├─ 分析视频 → 生成索引
        │
        ▼
video-editor (剪辑执行)
        │
        ├─ 读取索引 → 语义搜索
        ├─ 生成大纲 → 用户确认
        ├─ 匹配素材 → 生成草稿
        └─ 添加字幕/BGM
```

## ⚙️ 系统要求

- Python 3.8+
- FFmpeg
- 8GB+ RAM（批量处理时）

## 📄 许可证

MIT License

## 🙏 致谢

本项目为 Kimi Code CLI 的 Skill 系统开发，用于旅游类短视频自动化剪辑。
