# 视频脚本格式规范

VideoEditer 使用的脚本 JSON 格式，用于描述视频内容、时间轴和素材关联。

## 脚本结构

```json
{
  "title": "视频标题",
  "description": "视频描述",
  "duration": 120,
  "resolution": {
    "width": 1080,
    "height": 1920
  },
  "clips": [],
  "subtitles": [],
  "bgm": {},
  "narration": {}
}
```

## 字段说明

### Clips（视频片段）

```json
{
  "clips": [
    {
      "id": "clip_001",
      "path": "/path/to/video.mp4",
      "start_time": 0,
      "end_time": 5.5,
      "source_start": 10.0,
      "source_end": 15.5,
      "description": "日出航拍",
      "tags": ["风景", "日出", "航拍"],
      "transition": {
        "type": "fade",
        "duration": 0.5
      }
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 片段唯一标识 |
| `path` | string | 是 | 素材文件路径 |
| `start_time` | float | 是 | 在时间轴上的开始时间（秒） |
| `end_time` | float | 是 | 在时间轴上的结束时间（秒） |
| `source_start` | float | 否 | 素材本身的开始时间（秒），默认0 |
| `source_end` | float | 否 | 素材本身的结束时间（秒），默认全长 |
| `description` | string | 否 | 片段描述 |
| `tags` | array | 否 | 标签列表 |
| `transition` | object | 否 | 转场效果 |

### Subtitles（字幕）

```json
{
  "subtitles": [
    {
      "id": "sub_001",
      "start_time": 0,
      "end_time": 5,
      "cn_text": "这是中文台词",
      "en_text": "This is English subtitle",
      "style": {
        "cn_size": 56,
        "en_size": 40,
        "color": "#FFFFFF"
      }
    }
  ]
}
```

### BGM（背景音乐）

```json
{
  "bgm": {
    "path": "/path/to/music.mp3",
    "start_time": 0,
    "end_time": 120,
    "volume": 0.4,
    "mood": "抒情",
    "fade_in": 2.0,
    "fade_out": 3.0
  }
}
```

### Narration（旁白/配音）

```json
{
  "narration": {
    "type": "recorded",
    "path": "/path/to/narration.mp3",
    "segments": [
      {
        "start_time": 0,
        "end_time": 30,
        "text": "这是第一段旁白文案"
      }
    ]
  }
}
```

`type` 可选值：
- `recorded`: 用户提供的录音
- `ai_clone`: AI 克隆声音合成

## 完整示例

```json
{
  "title": "2024 冰岛之旅",
  "description": "记录冰岛 ring road 自驾游",
  "duration": 180,
  "resolution": {
    "width": 1080,
    "height": 1920
  },
  "clips": [
    {
      "id": "clip_001",
      "path": "/素材/冰岛/DJI_0001.mp4",
      "start_time": 0,
      "end_time": 8,
      "source_start": 5,
      "source_end": 13,
      "description": "黑沙滩航拍",
      "tags": ["航拍", "黑沙滩", "海浪"]
    },
    {
      "id": "clip_002",
      "path": "/素材/ Iceland/DJI_0002.mp4",
      "start_time": 7.5,
      "end_time": 15,
      "description": "瀑布全景",
      "transition": {
        "type": "fade",
        "duration": 0.5
      }
    }
  ],
  "subtitles": [
    {
      "id": "sub_001",
      "start_time": 0,
      "end_time": 8,
      "cn_text": "冰岛的黑沙滩，\n海浪拍打着黑色的沙滩",
      "en_text": "Iceland's black sand beach,\nwaves crashing on the dark shore"
    },
    {
      "id": "sub_002",
      "start_time": 8,
      "end_time": 15,
      "cn_text": "塞里雅兰瀑布，\n高达60米",
      "en_text": "Seljalandsfoss,\n60 meters high"
    }
  ],
  "bgm": {
    "path": "/素材/音乐/epic-cinematic.mp3",
    "start_time": 0,
    "end_time": 180,
    "volume": 0.35,
    "mood": "史诗"
  },
  "narration": {
    "type": "recorded",
    "path": "/素材/配音/narration.mp3"
  }
}
```

## 情绪标签

BGM mood 可选值：
- `欢快` - 节奏轻快，适合旅行开场
- `抒情` - 舒缓温柔，适合情感段落
- `紧张` - 节奏紧凑，适合探险/刺激场景
- `温馨` - 温暖治愈，适合人文/美食
- `史诗` - 宏大壮阔，适合风景/航拍
- `神秘` - 空灵神秘，适合特殊场景
