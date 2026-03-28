#!/usr/bin/env python3
"""VideoEditor MCP Server — FastMCP wrapper for the 7-step video pipeline + 5 capabilities.

Usage:
    python -m modules.mcp_server.server

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "videoeditor": {
          "command": "python3",
          "args": ["-m", "modules.mcp_server.server"],
          "cwd": "/path/to/videoeditor/project"
        }
      }
    }
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("mcp_server")

try:
    from fastmcp import FastMCP
except ImportError:
    logger.error(
        "fastmcp not installed. Run: pip install 'fastmcp>=0.9'\n"
        "Note: FastMCP requires Python 3.10+."
    )
    sys.exit(1)

# Ensure project root is on path
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from modules.mcp_server.health import check_backend_health
from modules.mcp_server.tools.workflow_tools import run_workflow_step, STEP_MAP
from modules.mcp_server.tools.capability_tools import (
    library_ingest,
    library_search,
    project_create,
    project_list,
    workflow_run,
)

mcp = FastMCP("VideoEditor", dependencies=["fastmcp>=0.9"])


# ── 7 Workflow Tools ──────────────────────────────────────────────

@mcp.tool()
def video_step1_analyze(project_dir: str, config: dict | None = None) -> dict:
    """Analyze raw video materials (Step 1). Extracts metadata, transcripts, and semantic tags."""
    return run_workflow_step("video_step1_analyze", project_dir, config)


@mcp.tool()
def video_step2_plan(project_dir: str, config: dict | None = None) -> dict:
    """Generate topic/content plan from analyzed materials (Step 2)."""
    return run_workflow_step("video_step2_plan", project_dir, config)


@mcp.tool()
def video_step3_script(project_dir: str, config: dict | None = None) -> dict:
    """Generate video script with timeline and narration (Step 3)."""
    return run_workflow_step("video_step3_script", project_dir, config)


@mcp.tool()
def video_step4_match(project_dir: str, config: dict | None = None) -> dict:
    """Match script segments to source video clips (Step 4)."""
    return run_workflow_step("video_step4_match", project_dir, config)


@mcp.tool()
def video_step5_preview(project_dir: str, config: dict | None = None) -> dict:
    """Generate frame-level preview of the edit (Step 5)."""
    return run_workflow_step("video_step5_preview", project_dir, config)


@mcp.tool()
def video_step6_cut(project_dir: str, config: dict | None = None) -> dict:
    """Execute rough cut assembly (Step 6)."""
    return run_workflow_step("video_step6_cut", project_dir, config)


@mcp.tool()
def video_step7_render(project_dir: str, config: dict | None = None) -> dict:
    """Final render with beauty, color grading, subtitles, BGM (Step 7)."""
    return run_workflow_step("video_step7_render", project_dir, config)


# ── 5 Capability Tools ───────────────────────────────────────────

@mcp.tool()
def library_search_tool(query: str, top_k: int = 10, mode: str = "hybrid") -> dict:
    """Search the video library by semantic query. Returns top-k matching assets."""
    return library_search(query, top_k, mode)


@mcp.tool()
def library_ingest_tool(source_path: str, recursive: bool = True) -> dict:
    """Ingest local video files into the library. Path must not contain '..' traversal."""
    return library_ingest(source_path, recursive)


@mcp.tool()
def project_list_tool() -> dict:
    """List all video editing projects."""
    return project_list()


@mcp.tool()
def project_create_tool(name: str, source_dir: str) -> dict:
    """Create a new video project from a source directory."""
    return project_create(name, source_dir)


@mcp.tool()
def workflow_run_tool(workflow_id: str, project_dir: str, config: dict | None = None) -> dict:
    """Run a custom workflow by ID."""
    return workflow_run(workflow_id, project_dir, config)


if __name__ == "__main__":
    mcp.run()
