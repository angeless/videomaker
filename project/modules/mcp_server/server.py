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
from modules.mcp_server.tools.review_tools import (
    review_init,
    review_add_comment,
    review_resolve_comment,
    review_ai_reedit,
    review_ai_reedit_dry_run,
    review_export_comments,
)
from modules.mcp_server.tools.vlm_tools import (
    vlm_describe_region,
    vlm_diagnose_frame,
    vlm_status,
)
from modules.mcp_server.tools.enhance_tools import (
    enhance_audio,
    enhance_tts,
    enhance_bgm,
    enhance_transition,
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


# ── 6 Review Tools (A1) ────────────────────────────────────────

@mcp.tool()
def review_init_tool(project_dir: str, video_path: str) -> dict:
    """Create a review session for a video. Returns session_id."""
    return review_init(project_dir, video_path)


@mcp.tool()
def review_add_comment_tool(session_id: str, text: str, timestamp_ms: int = 0, visual_context: dict | None = None) -> dict:
    """Add a comment to a review session with optional VLM visual context."""
    return review_add_comment(session_id, text, timestamp_ms, visual_context)


@mcp.tool()
def review_resolve_comment_tool(comment_id: str) -> dict:
    """Mark a review comment as resolved."""
    return review_resolve_comment(comment_id)


@mcp.tool()
def review_ai_reedit_tool(session_id: str) -> dict:
    """Trigger AI re-edit based on review comments."""
    return review_ai_reedit(session_id)


@mcp.tool()
def review_ai_reedit_dry_run_tool(session_id: str) -> dict:
    """Preview AI re-edit changes without applying (dry-run)."""
    return review_ai_reedit_dry_run(session_id)


@mcp.tool()
def review_export_comments_tool(session_id: str) -> dict:
    """Export all comments from a review session."""
    return review_export_comments(session_id)


# ── 3 VLM Tools (A2) ───────────────────────────────────────────

@mcp.tool()
def vlm_describe_region_tool(session_id: str, frame_base64: str, strokes: list, timestamp_ms: int = 0) -> dict:
    """Analyze a brush-selected region using VLM. frame_base64 max 10MB."""
    return vlm_describe_region(session_id, frame_base64, strokes, timestamp_ms)


@mcp.tool()
def vlm_diagnose_frame_tool(session_id: str, frame_base64: str, timestamp_ms: int = 0) -> dict:
    """Run frame diagnostics (composition, exposure, color temp). Synchronous."""
    return vlm_diagnose_frame(session_id, frame_base64, timestamp_ms)


@mcp.tool()
def vlm_status_tool() -> dict:
    """Check VLM availability and provider status."""
    return vlm_status()


# ── 4 Enhance Tools (A3) ───────────────────────────────────────

@mcp.tool()
def enhance_audio_tool(session_id: str, denoise: bool = True, eq: bool = True, compressor: bool = True, loudness_target: float = -16.0) -> dict:
    """Apply audio enhancement (denoise, EQ, compression, loudness normalization)."""
    return enhance_audio(session_id, denoise, eq, compressor, loudness_target)


@mcp.tool()
def enhance_tts_tool(session_id: str, text: str, voice: str = "default", language: str = "zh") -> dict:
    """Generate text-to-speech voiceover for a review session."""
    return enhance_tts(session_id, text, voice, language)


@mcp.tool()
def enhance_bgm_tool(session_id: str, genre: str = "ambient", beat_align: bool = True) -> dict:
    """Select and apply background music with optional beat alignment."""
    return enhance_bgm(session_id, genre, beat_align)


@mcp.tool()
def enhance_transition_tool(session_id: str, effect: str = "cross_dissolve", duration_ms: int = 500) -> dict:
    """Add transition effect between video segments."""
    return enhance_transition(session_id, effect, duration_ms)


if __name__ == "__main__":
    mcp.run()
