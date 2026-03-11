# YouTube Publish Connector

## 概述

YouTube connector 通过 YouTube Data API v3 的 resumable upload 协议将视频发布到 YouTube。支持完整的 config → call → result → status → error handling 闭环。

## Connector 配置

通过 `POST /api/settings/publish` 保存配置：

```json
{
  "connectors": {
    "youtube": {
      "kind": "youtube_api",
      "token": "<access_token>",
      "privacy_status": "private",
      "category_id": "22",
      "timeout_s": 120,
      "notify_subscribers": false
    }
  }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `kind` | 是 | 固定 `"youtube_api"` |
| `token` | 是 | OAuth2 access_token |
| `privacy_status` | 否 | `private` / `public` / `unlisted`（默认 `private`） |
| `category_id` | 否 | YouTube 分类 ID，数字字符串（默认 `"22"` = People & Blogs） |
| `timeout_s` | 否 | HTTP 超时秒数（默认 120，范围 3–120） |
| `notify_subscribers` | 否 | 是否通知订阅者（默认 `false`） |

## 参数校验（Pre-flight）

在调用 YouTube API 之前，connector 会执行以下本地校验：

| 检查项 | 规则 | 失败分类 |
|--------|------|----------|
| token 非空 | access_token 或 token 字段存在 | `config_missing` |
| 视频文件 | 本地文件存在且为文件 | `params_invalid` |
| title | ≤ 100 字符 | `params_invalid` |
| description | ≤ 5000 字符 | `params_invalid` |
| privacy_status | ∈ {private, public, unlisted} | `params_invalid` |
| category_id | 数字字符串 | `params_invalid` |

## 上传流程

1. **初始化**：POST `googleapis.com/upload/youtube/v3/videos?uploadType=resumable`
   - 携带 snippet + status metadata
   - 返回 `Location` header（resumable upload URL）
2. **上传**：PUT binary data 到 resumable URL
   - 返回 video resource JSON（含 `id`）
3. **结果**：`post_id = video_id`, `post_url = https://www.youtube.com/watch?v={id}`

## 错误分类

| error_class | HTTP 触发 | retryable | action_hint |
|-------------|-----------|-----------|-------------|
| `config_missing` | — | No | 补充配置后重试 |
| `auth_failed` | 401, 403 | No | 刷新 access_token 后重试 |
| `params_invalid` | — | No | 修正参数后重试 |
| `platform_rejected` | 400, 422 | No | 检查内容参数后重试 |
| `quota_exceeded` | 429 | Yes | 等待配额恢复后重试 |
| `network_error` | 500+, timeout | Yes | 可直接重试 |
| `unknown` | 其他 | No | 检查详情后决定 |

错误分类作为内部机制，通过 step 的 `error_detail` 字段暴露：

```json
{
  "error_detail": {
    "error_class": "auth_failed",
    "retryable": false,
    "action_hint": "刷新 access_token 后重试"
  }
}
```

## 幂等保护

`POST /run` 接入 idempotency store，基于发布请求摘要（platform_id + title + description + media_urls + connector kind + dry_run）计算稳定 hash。相同内容不会重复发布。

仅缓存明确成功（posted / planned）且无 failed / blocked 的结果。

## 审计事件

| operation | 触发条件 | detail 字段 |
|-----------|----------|-------------|
| `publish_run` | 每次 /run 调用 | dry_run, connector_count, posted, failed, blocked |
| `publish_blocked` | 存在 blocked steps | platforms |
| `publish_error` | 存在 failed steps（逐条） | platform, error_class, error（≤200 chars）, dry_run |
| `publish_rerun` | /rerun 调用 | source_run_id, connector_count |

## 恢复建议

run 结果包含 `recovery_hint` 字段：

```json
{
  "recovery_hint": {
    "can_rerun": true,
    "rerun_endpoint": "/api/capabilities/content_publish/rerun",
    "rerun_scope": "failed_only",
    "error_classes": ["auth_failed"]
  }
}
```

| rerun_scope | 含义 |
|-------------|------|
| `none` | 全部成功，无需 rerun |
| `failed_only` | 仅有失败步骤，可 rerun |
| `fix_config_then_rerun` | 仅有 blocked，需修复配置后 rerun |
| `failed_and_blocked` | 同时有失败和 blocked |
