---
name: manage-videos
description: 视频素材语义索引与搜索工具。用于旅游视频素材库的智能标注、分类和语义检索。当用户需要：(1) 批量分析视频素材，(2) 为视频建立语义索引，(3) 根据关键词/标签搜索视频，(4) 提取视频元数据和技术信息时触发。
---

# 视界工具箱 - 视频素材管理

专为 8TB 级旅游视频素材库设计的语义搜索与归纳系统。支持本地/云端混合分析，实现海量素材的智能索引与快速检索。

## 核心功能

- **多维度分析**：技术质量、内容标签、地点识别、业务价值
- **混合架构**：本地轻量筛选 + 云端深度索引，极致成本优化
- **语义搜索**：支持中文/英文关键词检索
- **AI 友好**：提供结构化 JSON 输出，可供其他 Agent 直接调用

## 使用方式

本 skill 提供两种方式使用：
1. **命令行调用** - 直接执行 Python 脚本
2. **Python API** - 在其他 skill 中导入使用

## 快速开始

### 命令行方式

```bash
# 批量分析视频
python3 video_asset_toolkit.py /path/to/videos --output json

# 交互式搜索
python3 chinese_search_ui.py --interactive

# 命令行搜索
python3 chinese_search_ui.py --query "滑雪 第一视角"

# 按标签搜索
python3 search_videos.py --tags "航拍,4K,冰岛"
```

### Python API 方式

```python
from video_asset_toolkit import VideoAssetToolkit
from search_videos import VideoSearch
from chinese_search_ui import ChineseVideoSearchUI

# 分析视频
toolkit = VideoAssetToolkit("config.json")
results = toolkit.analyze_videos(["/path/to/video.mp4"])

# 搜索视频
search = VideoSearch("video_index.json")
results = search.search("冰岛 黑沙滩")

# 中文语义搜索
ui = ChineseVideoSearchUI("manual_enhanced_index.json")
results = ui.search(query="滑雪", content_type="运动", location="日本")
```

## 核心脚本

### video_asset_toolkit.py

视频分析主入口，支持批量处理。

**命令行用法：**
```bash
python3 video_asset_toolkit.py [视频路径/目录] [选项]

选项：
  --config          配置文件路径
  --output          输出格式: json/markdown/csv/all
  --batch           批量处理模式
```

**主要方法：**
- `analyze_videos(video_paths, output_format)` - 分析视频列表
- `extract_metadata(video_path)` - 提取视频元数据
- `technical_analysis(video_path)` - 技术质量分析
- `generate_recommendations(analysis_result)` - 生成优化建议

### chinese_search_ui.py

中文视频搜索界面，支持语义搜索。

**命令行用法：**
```bash
python3 chinese_search_ui.py [选项]

选项：
  --query, -q       搜索关键词
  --content-type    内容类型筛选
  --location        地点筛选
  --interactive, -i 交互模式
  --index           索引文件路径
```

**主要方法：**
- `search(query, content_type, location)` - 搜索视频
- `interactive_search()` - 交互式搜索
- `print_all_tags()` - 显示所有可用标签

### search_videos.py

视频索引搜索工具。

**命令行用法：**
```bash
python3 search_videos.py [查询] [选项]

选项：
  --tags            按标签搜索
  --resolution      按分辨率搜索
  --min-width       最小宽度
  --min-height      最小高度
  --min-duration    最小时长（秒）
  --max-duration    最大时长（秒）
  --index           索引文件路径
```

**主要方法：**
- `search(query, search_field)` - 通用搜索
- `search_by_tags(tags)` - 按标签搜索
- `search_by_resolution(min_width, min_height)` - 按分辨率搜索
- `search_by_duration(min_seconds, max_seconds)` - 按时长搜索

## 数据格式

### 视频分析输出格式

```json
{
  "video_hash_id": {
    "filename": "DJI_0001.mp4",
    "path": "/absolute/path/to/video.mp4",
    "hash": "abc123",
    "timestamp": "2024-06-15T08:30:00",
    "analysis": {
      "metadata": {
        "duration": "45.5",
        "size": "1234567890",
        "bitrate": "50000k",
        "video_streams": [...],
        "audio_streams": [...]
      },
      "local_analysis": {
        "technical": {
          "resolution": "3840x2160",
          "resolution_score": 0.95,
          "overall_quality": 0.90,
          "quality_level": "优秀"
        },
        "objects": {
          "detected_objects": ["person", "snow", "mountain"],
          "confidence": 0.85
        },
        "scene": {
          "description": "Snowboarder carving through fresh powder",
          "mood": "adventurous, energetic",
          "confidence": 0.78
        }
      },
      "recommendations": [
        {
          "type": "content",
          "priority": "medium",
          "message": "适合旅行/冒险类内容",
          "action": "可制作滑雪教程或旅行vlog"
        }
      ]
    }
  }
}
```

### 中文索引格式

```json
{
  "videos": {
    "video_id": {
      "filename": "DJI_0001.mp4",
      "analysis": {
        "description": "无人机航拍冰岛黑沙滩",
        "content_type": "航拍风景",
        "location": "冰岛 - Reynisfjara",
        "perspective": "航拍俯视",
        "confidence": 0.92
      },
      "technical": {
        "resolution": "3840x2160",
        "duration": "45.5s",
        "quality": "优秀",
        "special": "4K, 60fps"
      },
      "business": {
        "primary_use": "旅行vlog开场",
        "target_audience": "旅游爱好者",
        "content_angle": "展示自然壮观"
      },
      "search_tags": ["航拍", "冰岛", "海滩", "4K", "自然风光"]
    }
  }
}
```

## 搜索评分机制

搜索时按以下权重计算匹配度：

| 字段 | 权重 | 说明 |
|------|------|------|
| 描述 | 10分 | 语义描述完全匹配 |
| 标签 | 8分 | 标签匹配 |
| 物体 | 5分 | 检测到的物体匹配 |
| 内容类型 | 3分 | 内容分类匹配 |
| 地点 | 3分 | 拍摄地点匹配 |
| 用途 | 3分 | 建议使用场景匹配 |

## 与 video-editor skill 协作

本 skill 生成的索引可直接被 video-editor skill 使用：

```python
# 1. 使用 manage-videos 生成索引
from video_asset_toolkit import VideoAssetToolkit

toolkit = VideoAssetToolkit()
results = toolkit.analyze_videos("/素材/冰岛", output_format="json")

# 2. video-editor 读取并搜索
from search_videos import VideoSearch

search = VideoSearch("results/video_analysis_*.json")
matched = search.search("黑沙滩 航拍")

# 3. 生成剪映草稿（video-editor skill 处理）
```

或使用转换脚本：

```bash
# 转换索引格式
python video-editor/scripts/convert_index.py \
    --input results/video_analysis_*.json \
    --output materials_index.json
```

## 配置文件

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
  },
  "analysis_dimensions": [
    "objects", "scenes", "colors", "composition",
    "mood", "business_value", "technical_quality"
  ],
  "output_formats": ["json", "markdown", "csv"],
  "max_videos_per_batch": 100
}
```

## 输出文件

分析结果默认保存在 `./results/` 目录：
- `{timestamp}_video_analysis.json` - JSON 格式
- `{timestamp}_video_analysis.md` - Markdown 报告
- `{timestamp}_video_analysis.csv` - CSV 表格

## 依赖

```bash
pip install -r requirements.txt
```

必需：Python 3.8+, FFmpeg

## 技术质量评分标准

| 分辨率 | 评分 | 说明 |
|--------|------|------|
| 4K+ | 0.95 | 3840x2160 或更高 |
| 1080p | 0.85 | 1920x1080 |
| 720p | 0.70 | 1280x720 |
| 480p | 0.50 | 640x480 |

| 码率 | 评分 | 说明 |
|------|------|------|
| >10Mbps | 0.95 | 专业级 |
| 5-10Mbps | 0.85 | 良好 |
| 2-5Mbps | 0.70 | 标准 |
| 1-2Mbps | 0.50 | 较低 |

## 效率优化建议

- **大批量处理**：使用 `--batch` 模式
- **云端分析**：配置 API 密钥启用 Gemini/OpenAI 深度分析
- **增量更新**：只分析新增视频，合并索引文件
- **本地优先**：无 API 密钥时自动降级到本地分析
