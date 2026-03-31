# VideoEditor MCP Server

Exposes VideoEditor's 7-step video pipeline and 5 capability tools via [FastMCP](https://github.com/jlowin/fastmcp).

## Quick Start

```bash
# Install dependency
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

## 12 Tools

### Workflow (7 steps)
| Tool | Description |
|------|-------------|
| `video_step1_analyze` | Analyze raw materials |
| `video_step2_plan` | Generate content plan |
| `video_step3_script` | Generate script |
| `video_step4_match` | Match script to clips |
| `video_step5_preview` | Frame preview |
| `video_step6_cut` | Rough cut |
| `video_step7_render` | Final render |

### Capabilities (5)
| Tool | Description |
|------|-------------|
| `library_search_tool` | Search video library |
| `library_ingest_tool` | Ingest local files |
| `project_list_tool` | List projects |
| `project_create_tool` | Create project |
| `workflow_run_tool` | Run custom workflow |

## Security

- **No delete operations** exposed
- **Path whitelist**: Write paths restricted to `~/Movies/VideoEditor/exports/` and `/tmp/`
- **Traversal prevention**: `..` in paths is rejected
- **Lazy connection**: Backend offline returns readable error with startup instructions
