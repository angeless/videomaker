# 剪映草稿 JSON 格式规范

剪映专业版使用 JSON 格式存储草稿项目。了解其结构对于生成可导入的草稿文件至关重要。

## 草稿文件位置

剪映草稿通常存储在：
- **Windows**: `%LOCALAPPDATA%/JianyingPro/User Data/Projects/com.lveditor.draft/`
- **macOS**: `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/`

## JSON 结构概览

```json
{
  "platform": {
    "os": "macOS",
    "app_version": "3.x.x"
  },
  "materials": {
    "videos": [],
    "audios": [],
    "texts": [],
    "effects": [],
    "filters": []
  },
  "tracks": [],
  "canvas_config": {
    "width": 1080,
    "height": 1920,
    "fps": 30
  }
}
```

## 关键字段说明

### 1. Materials（素材库）

#### Video 素材
```json
{
  "id": "uuid-v4-format",
  "type": "video",
  "path": "/absolute/path/to/video.mp4",
  "duration": 10000000,
  "width": 1920,
  "height": 1080,
  "fps": 30
}
```
- `duration`: 微秒级（1秒 = 1,000,000微秒）
- `path`: 绝对路径

#### Audio 素材
```json
{
  "id": "uuid-v4-format",
  "type": "audio",
  "path": "/absolute/path/to/audio.mp3",
  "duration": 5000000
}
```

#### Text 素材（字幕）
```json
{
  "id": "uuid-v4-format",
  "type": "text",
  "content": "字幕内容",
  "style": {
    "font": "PingFangSC-Regular",
    "size": 60,
    "color": "#FFFFFF"
  }
}
```

### 2. Tracks（轨道）

剪映支持多轨道编辑：

```json
{
  "tracks": [
    {
      "id": "track-1",
      "type": "video",
      "segments": [
        {
          "material_id": "uuid-of-video",
          "start_time": 0,
          "end_time": 5000000,
          "source_start": 0,
          "source_end": 5000000,
          "transform": {
            "scale": {"x": 1.0, "y": 1.0},
            "position": {"x": 0, "y": 0},
            "rotation": 0
          }
        }
      ]
    },
    {
      "id": "track-2",
      "type": "text",
      "segments": []
    },
    {
      "id": "track-3",
      "type": "audio",
      "segments": []
    }
  ]
}
```

#### Segment 字段说明

| 字段 | 说明 | 单位 |
|------|------|------|
| `material_id` | 引用的素材ID | - |
| `start_time` | 在时间轴上的开始位置 | 微秒 |
| `end_time` | 在时间轴上的结束位置 | 微秒 |
| `source_start` | 素材本身的开始时间点 | 微秒 |
| `source_end` | 素材本身的结束时间点 | 微秒 |

### 3. Canvas Config（画布配置）

```json
{
  "canvas_config": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "color_space": "sRGB"
  }
}
```

常见分辨率：
- 竖屏 9:16: 1080x1920
- 横屏 16:9: 1920x1080
- 方形 1:1: 1080x1080

## 双语字幕格式

剪映支持多行字幕：

```json
{
  "type": "text",
  "content": "中文主字幕\nEnglish Subtitle",
  "style": {
    "font": "PingFangSC-Regular",
    "size": 56,
    "color": "#FFFFFF",
    "outline": {
      "enabled": true,
      "color": "#000000",
      "width": 2
    }
  }
}
```

## 常用操作示例

### 创建视频片段

```python
def create_video_segment(material_id, start, end, source_start=0, source_end=None):
    if source_end is None:
        source_end = end - start
    return {
        "material_id": material_id,
        "start_time": int(start * 1000000),  # 转换为微秒
        "end_time": int(end * 1000000),
        "source_start": int(source_start * 1000000),
        "source_end": int(source_end * 1000000),
        "transform": {
            "scale": {"x": 1.0, "y": 1.0},
            "position": {"x": 0, "y": 0},
            "rotation": 0
        }
    }
```

### 创建字幕片段

```python
def create_text_segment(content, start, end, style=None):
    default_style = {
        "font": "PingFangSC-Regular",
        "size": 56,
        "color": "#FFFFFF",
        "alignment": "center"
    }
    return {
        "content": content,
        "start_time": int(start * 1000000),
        "end_time": int(end * 1000000),
        "style": style or default_style
    }
```

## 导入草稿步骤

1. 生成 JSON 文件
2. 放置到剪映草稿目录：`~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/YourProject/`
3. 文件命名为 `draft_info.json` 或 `draft_content.json`
4. 重启剪映，草稿应自动出现在项目列表中

## 注意事项

1. **路径问题**：剪映草稿中的素材路径必须是绝对路径，且文件必须存在
2. **UUID**：所有ID必须使用有效的 UUID v4 格式
3. **时间单位**：所有时间相关字段都是微秒级
4. **版本兼容**：不同剪映版本可能有细微格式差异

## 参考资源

- 剪映官方文档（如有）
- 社区逆向工程资料
