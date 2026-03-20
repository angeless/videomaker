# Agent 最小调用示例（Inline / 单模块）

更新时间：2026-02-28

## 1. 默认行为

- `POST /api/agent/tasks/plan`
- `POST /api/agent/tasks/run`
- `POST /api/agent/skills/invoke`

当请求未显式传 `input_mode` 时：

- 已加载项目：默认 `input_mode=project`
- 未加载项目：默认 `input_mode=inline`

你仍可手动覆盖为 `project` 或 `inline`。

## 2. Agent 单能力调用（最小请求）

### 2.1 选题库（topic_library）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "planner_1",
    "capability_id": "topic_library",
    "input": {
      "q": "海边",
      "include_disabled": false
    }
  }'
```

### 2.2 选题+文案（topic_copy）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "writer_1",
    "capability_id": "topic_copy",
    "input": {
      "topic": {
        "slug": "city_walk",
        "title": "城市漫步高光",
        "category": "travel",
        "audience": "general",
        "hook_style": "story",
        "outline_template": "",
        "tags": ["城市"],
        "enabled": true
      },
      "materials": {
        "v1": {"semantic": {"setting": "城市街区", "activity": "漫步", "mood": "轻快"}}
      },
      "target_duration_s": 45
    }
  }'
```

### 2.3 文字粗剪（text_rough_cut）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "editor_1",
    "capability_id": "text_rough_cut",
    "input": {
      "spans": [
        {"start": 0.0, "end": 1.0, "text": "大家好"},
        {"start": 1.1, "end": 2.0, "text": "今天去徒步"}
      ],
      "target_duration_s": 1.5
    }
  }'
```

### 2.4 短视频快剪（short_clip）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "editor_2",
    "capability_id": "short_clip",
    "input": {
      "candidates": [
        {"start": 0.0, "end": 4.0, "score": 0.92, "reason": "hook"},
        {"start": 4.0, "end": 8.0, "score": 0.80, "reason": "scene"}
      ],
      "target_duration_s": 5.0
    }
  }'
```

### 2.5 字幕校准（subtitle_calibration）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "subtitle_1",
    "capability_id": "subtitle_calibration",
    "action": "run",
    "input": {
      "mode": "timeline_align",
      "translation": "bilingual",
      "subtitles": [
        {"start_time": 0, "end_time": 1.0, "cn_text": "你好"},
        {"start_time": 0.9, "end_time": 1.8, "en_text": "hello"}
      ]
    }
  }'
```

### 2.6 图片语义（image_semantic）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "media_1",
    "capability_id": "image_semantic",
    "action": "analyze",
    "input": {
      "image_paths": ["/abs/path/a.jpg", "/abs/path/b.jpg"]
    }
  }'
```

### 2.7 公众号扩写（article_expand）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "writer_2",
    "capability_id": "article_expand",
    "input": {
      "source_text": "今天复盘从选题到发布的完整链路。",
      "key_points": ["选题", "剪辑", "发布"]
    }
  }'
```

### 2.8 社媒导出计划（social_export）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "export_1",
    "capability_id": "social_export",
    "input": {
      "input_video": "/abs/path/final.mp4",
      "platforms": ["douyin", "threads", "wechat_channels"],
      "output_dir": "/abs/path/exports",
      "strict_duration_limit": false
    }
  }'
```

### 2.9 配乐配音计划（audio_voice）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "audio_1",
    "capability_id": "audio_voice",
    "input": {
      "script": {
        "clips": [{"duration": 2.0}, {"duration": 3.0}],
        "subtitles": [{"cn_text": "你好", "start_time": 0.0, "end_time": 1.2}]
      }
    }
  }'
```

### 2.10 内容发布（content_publish）

```bash
curl -X POST http://127.0.0.1:5000/api/agent/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "publisher_1",
    "capability_id": "content_publish",
    "action": "run",
    "input": {
      "plan": {
        "dry_run": true,
        "platforms": ["blog"],
        "steps": [{"platform_id": "blog"}]
      },
      "dry_run": true
    }
  }'
```

## 3. Agent Skill 调用（最小请求）

### 3.1 `skill.topic_copy.draft`

```bash
curl -X POST http://127.0.0.1:5000/api/agent/skills/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "skill_bot_1",
    "skill_id": "skill.topic_copy.draft",
    "input": {
      "topic": {
        "slug": "lake_walk",
        "title": "湖边散步高光",
        "category": "travel",
        "audience": "general",
        "hook_style": "story",
        "outline_template": "",
        "tags": ["湖边"],
        "enabled": true
      },
      "materials": {
        "v1": {"semantic": {"setting": "湖边", "activity": "散步", "mood": "舒缓"}}
      }
    }
  }'
```

### 3.2 `skill.text_rough_cut.plan`

```bash
curl -X POST http://127.0.0.1:5000/api/agent/skills/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "agent",
    "actor_id": "skill_bot_2",
    "skill_id": "skill.text_rough_cut.plan",
    "input": {
      "spans": [
        {"start": 0.0, "end": 1.0, "text": "大家好"},
        {"start": 1.1, "end": 2.0, "text": "今天去徒步"}
      ],
      "target_duration_s": 1.5
    }
  }'
```
