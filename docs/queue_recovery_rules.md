# Queue Recovery Rules

## Overview

When a task fails, is cancelled, or partially completes, the system provides unified recovery judgment via `recovery_rules.py`. All recovery endpoints return **advice only** (`action: "advice_only"`, `retry_submitted: false`) — they never auto-resubmit tasks.

## Status Model

| Status | Terminal? | Retryable? | Meaning |
|--------|-----------|------------|---------|
| `queued` | No | No | Waiting in heavy job queue |
| `running` | No | No | Currently executing |
| `done` | Yes | No | Completed successfully |
| `error` | Yes | Yes | Execution failed with exception |
| `cancelled` | Yes | Yes | User cancelled |
| `interrupted` | Yes | Yes | App restart interrupted the task |
| `partial` | Yes | Yes (batch) | Batch partially succeeded |

## Recovery Rules

### Can Retry

- `error` — task failed, safe to retry via capability endpoint
- `cancelled` — user cancelled, safe to resubmit
- `interrupted` — app restart, safe to resubmit

### Cannot Retry

- `done` — already succeeded, no action needed
- `running` — still active, wait or cancel first
- `queued` — not yet started, wait or cancel first
- `running` with `cancel_requested` — stopping in progress, wait

### Batch (partial)

- `partial` status indicates some items succeeded, some failed
- Recovery scope is `batch` — use capability rerun endpoint
- Already-done items should be skipped (e.g. `rerun_failed_only=true`)
- Duplicate execution risk exists for publish/export kinds

## API Endpoints

### GET /api/job/\<id\>

Returns existing fields plus new `recovery` object:

```json
{
  "status": "error",
  "recovery": {
    "current_status": "error",
    "can_retry": true,
    "retry_scope": "single",
    "reason": "...",
    "next_action": "...",
    "blocked_reason": null,
    "duplicate_risk": false,
    "retry_hint": {"kind": "social_export", "endpoint": "/api/capabilities/social_export/rerun"}
  }
}
```

### POST /api/job/\<id\>/retry

Advice-only recovery assessment for a single job.

**Success (200):**
```json
{
  "ok": true,
  "action": "advice_only",
  "retry_submitted": false,
  "source_job_id": "abc123",
  "recovery": { ... }
}
```

**Blocked (409):**
```json
{
  "error": "...",
  "action": "advice_only",
  "retry_submitted": false,
  "recovery": { ... }
}
```

### POST /api/jobs/batch-retry

Advice-only batch recovery assessment.

**Request:** `{"job_ids": ["id1", "id2", ...]}`

**Response (200):**
```json
{
  "ok": true,
  "action": "advice_only",
  "retry_submitted": false,
  "summary": {"total": 5, "retryable": 2, "skipped": 2, "blocked": 1},
  "reason": "...",
  "items": [...]
}
```

## Retry Hint Map

| Job Kind | Retry Endpoint |
|----------|---------------|
| `social_export` | `/api/capabilities/social_export/rerun` |
| `custom_workflow` | `/api/workflows/runs/{run_id}/rerun` |
| `library_ingest_local` | `/api/library/ingest/local` |
| `library_ingest_local_images` | `/api/library/ingest/local/images` |
| `library_ingest_gdrive` | `/api/library/ingest/gdrive` |
| `audio_voice` | None (manual resubmit) |
| `workflow_step` | None (manual resubmit) |

When `retry_hint` is `null`, the user/agent must manually resubmit with original parameters.

## Idempotency & Duplicate Protection

- Recovery endpoints never auto-execute — they only advise
- Each retry creates a **new** job with a new ID; the original job record is preserved
- For publish/export kinds, `duplicate_risk: true` warns about potential re-posting
- Content publish supports `rerun_failed_only=true` to skip already-posted items
- Social export currently re-runs all platforms on rerun (no per-platform filtering)

## Audit Logging

All recovery actions write to audit_log:

| Action | operation | detail |
|--------|-----------|--------|
| Single retry (allowed) | `retry` | `{source_status, kind}` |
| Single retry (blocked) | `retry_blocked` | `{current_status, reason}` |
| Batch retry | `batch_retry` | `{total, retryable, skippable, blocked}` |
