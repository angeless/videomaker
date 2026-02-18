# 素材索引格式规范

VideoEditer 与素材整理 skill 的数据交换格式，确保两个 skill 能够无缝协作。

## 索引文件结构

```json
{
  "version": "1.0",
  "created_at": "2024-06-15T08:30:00",
  "total_videos": 150,
  "base_path": "/Users/username/素材库",
  "videos": {
    "video_hash_id": {
      "file_info": {
        "filename": "DJI_0001.mp4",
        "path": "/绝对/路径/DJI_0001.mp4",
        "relative_path": "冰岛/航拍/DJI_0001.mp4",
        "file_size": 1234567890,
        "file_size_human": "1.2 GB",
        "created_time": "2024-06-15T08:30:00",
        "modified_time": "2024-06-15T08:30:00"
      },
      "technical_summary": {
        "duration": 45.5,
        "duration_formatted": "00:00:45",
        "resolution": "3840x2160",
        "width": 3840,
        "height": 2160,
        "fps": 30,
        "bitrate": "50000k",
        "codec": "h264",
        "has_audio": true,
        "quality_score": 9.2,
        "quality_level": "优秀"
      },
      "content_summary": {
        "description": "无人机航拍冰岛黑沙滩，白色海浪拍打着黑色沙滩",
        "mood": "史诗、壮观、宁静",
        "location": "冰岛 - Reynisfjara Beach",
        "objects": ["海滩", "海浪", "悬崖", "天空"],
        "notes": ["适合开场", "4K高清", "光线良好"]
      },
      "index_data": {
        "tags": ["航拍", "冰岛", "海滩", "4K", "自然风光"],
        "search_keywords": ["drone", "beach", "iceland", "waves", "black sand"],
        "preview_info": {
          "thumbnail_path": "./thumbnails/DJI_0001.jpg",
          "preview_frame": 450,
          "duration": 45.5,
          "resolution": "3840x2160",
          "has_audio": true
        }
      },
      "editing_info": {
        "usable_segments": [
          {
            "start": 5.0,
            "end": 15.0,
            "duration": 10.0,
            "description": "最佳航拍镜头",
            "quality_score": 9.5
          }
        ],
        "suggested_usage": ["开场", "过渡", "结尾"],
        "color_profile": {
          "dominant_colors": ["#1a1a2e", "#16213e", "#ffffff"],
          "color_temperature": "冷色调"
        }
      }
    }
  }
}
```

## 字段说明

### file_info（文件信息）

| 字段 | 类型 | 说明 |
|------|------|------|
| `filename` | string | 文件名 |
| `path` | string | 绝对路径（剪映草稿需要） |
| `relative_path` | string | 相对路径（便于迁移） |
| `file_size` | int | 文件大小（字节） |
| `file_size_human` | string | 人类可读大小 |

### technical_summary（技术摘要）

| 字段 | 类型 | 说明 |
|------|------|------|
| `duration` | float | 时长（秒） |
| `resolution` | string | 分辨率（如 1920x1080） |
| `quality_score` | float | 质量评分（0-10） |
| `quality_level` | string | 质量等级：优秀/良好/一般/较差 |

### content_summary（内容摘要）

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 中文语义描述 |
| `mood` | string | 情绪标签 |
| `location` | string | 拍摄地点 |
| `objects` | array | 画面中的物体 |

### editing_info（剪辑专用信息）

VideoEditer 扩展字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `usable_segments` | array | 可用片段列表（入出点） |
| `suggested_usage` | array | 建议使用场景 |
| `color_profile` | object | 色彩信息（用于调色匹配） |

## 与素材整理 skill 的协作

### 调用方式

VideoEditer 调用素材整理 skill 进行索引：

```bash
# 1. 使用素材整理 skill 分析视频
python managevideos/run_toolkit.py \
    --input "/path/to/videos" \
    --output json

# 2. 转换为 VideoEditer 兼容格式
python video-editor/scripts/convert_index.py \
    --input video_analysis_*.json \
    --output materials_index.json
```

### 搜索接口

```python
from managevideos.search_videos import VideoSearch

# 初始化搜索
search = VideoSearch("materials_index.json")

# 语义搜索
results = search.search("滑雪 第一视角")

# 按标签搜索
results = search.search_by_tags(["航拍", "4K", "冰岛"])

# 按质量筛选
results = search.search_by_resolution(min_width=1920, min_height=1080)
```

### 返回格式

搜索结果格式：

```json
{
  "video_id": "abc123",
  "filename": "DJI_0001.mp4",
  "path": "/绝对/路径/DJI_0001.mp4",
  "match_score": 25,
  "match_details": ["标签匹配: 航拍", "描述匹配: 冰岛"],
  "preview_info": {...},
  "content_summary": {...}
}
```

## 数据流

```
原始素材
    ↓
素材整理 skill (analyze_videos.py)
    ↓
生成索引文件 (video_index.json)
    ↓
VideoEditer 读取索引
    ↓
语义搜索匹配脚本需求
    ↓
生成候选素材清单 → 用户确认
    ↓
生成剪映草稿
```

## 生成剪映草稿时的数据映射

| 素材索引字段 | 剪映草稿字段 |
|-------------|-------------|
| `file_info.path` | `materials.videos[].path` |
| `technical_summary.duration` | `materials.videos[].duration` |
| `technical_summary.width/height` | `materials.videos[].width/height` |
| `editing_info.usable_segments[].start` | `tracks[].segments[].source_start` |
| `editing_info.usable_segments[].end` | `tracks[].segments[].source_end` |
