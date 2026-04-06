# VideoEditor MCP Server

Exposes VideoEditor's 29 tools via [FastMCP](https://github.com/jlowin/fastmcp): 7-step video pipeline, 5 capability tools, 6 review tools, 3 VLM tools, 4 enhancement tools, and 4 read-only query tools.

## Quick Start

```bash
# Install dependency (requires Python 3.10+)
pip install 'fastmcp>=0.9'

# Run the server (from project/ directory)
python -m modules.mcp_server.server
```

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "videoeditor": {
      "command": "python3",
      "args": ["-m", "modules.mcp_server.server"],
      "cwd": "/path/to/videoeditor/project"
    }
  }
}
```

## 29 Tools

### Workflow (7 steps)
| Tool | Description |
|------|-------------|
| `video_step1_analyze` | Analyze raw materials |
| `video_step2_plan` | Generate content plan |
| `video_step3_script` | Generate script with timeline |
| `video_step4_match` | Match script segments to clips |
| `video_step5_preview` | Frame-level preview of edit |
| `video_step6_cut` | Rough cut assembly |
| `video_step7_render` | Final render with beauty/subtitles/BGM |

### Capabilities (5)
| Tool | Description |
|------|-------------|
| `library_search_tool` | Search video library by semantic query |
| `library_ingest_tool` | Ingest local video files into library |
| `project_list_tool` | List all video editing projects |
| `project_create_tool` | Create new project from source directory |
| `workflow_run_tool` | Run custom workflow by ID |

### Review Operations — A1 (6)
| Tool | Description |
|------|-------------|
| `review_init_tool` | Create review session for a video |
| `review_add_comment_tool` | Add comment with optional VLM context |
| `review_resolve_comment_tool` | Mark comment as resolved |
| `review_ai_reedit_tool` | Trigger AI re-edit from comments |
| `review_ai_reedit_dry_run_tool` | Preview re-edit changes (dry-run) |
| `review_export_comments_tool` | Export all comments from session |

### VLM Analysis — A2 (3)
| Tool | Description |
|------|-------------|
| `vlm_describe_region_tool` | Analyze brush-selected region via VLM |
| `vlm_diagnose_frame_tool` | Frame diagnostics (composition, exposure, color) |
| `vlm_status_tool` | Check VLM availability and provider status |

### Enhancement — A3 (4)
| Tool | Description |
|------|-------------|
| `enhance_audio_tool` | Audio enhancement (denoise, EQ, compression, loudness) |
| `enhance_tts_tool` | Text-to-speech voiceover generation |
| `enhance_bgm_tool` | Background music with beat alignment |
| `enhance_transition_tool` | Transition effects between segments |

### Read-Only Queries — A4 (4)
| Tool | Description |
|------|-------------|
| `review_query_state_tool` | Session metadata and current version |
| `review_query_comments_tool` | All comments for a session |
| `review_query_diagnostics_tool` | VLM diagnostics results |
| `review_query_versions_tool` | Version history for a session |

## Security (A5)

- **No delete operations** exposed via MCP
- **Permission levels**: READ (7 tools) / WRITE (22 tools) — no DANGEROUS tier
- **Path whitelist**: Write paths restricted to `~/Movies/VideoEditor/exports/`, `~/Movies/VideoEditor/reviews/`, and `/tmp/`
- **Traversal prevention**: `..` in paths is rejected
- **Audit logging**: JSONL log at `data/mcp_audit.jsonl` (tool name, args hash, permission, timestamp)
- **Lazy connection**: Backend offline returns readable error with startup instructions
