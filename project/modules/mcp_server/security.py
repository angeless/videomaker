"""Security utilities for MCP Server — path whitelist, traversal prevention, permission levels (A5)."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ── Path whitelist ───────────────────────────────────────────────

ALLOWED_WRITE_DIRS: List[str] = [
    str(Path.home() / "Movies" / "VideoEditor" / "exports"),
    str(Path.home() / "Movies" / "VideoEditor" / "reviews"),
    str(Path("/tmp").resolve()),
]


def is_safe_write_path(path_str: str) -> bool:
    """Check if a write path is within the allowed whitelist."""
    try:
        resolved = str(Path(path_str).expanduser().resolve())
    except (ValueError, OSError):
        return False
    return any(
        resolved == prefix or resolved.startswith(prefix + os.sep)
        for prefix in ALLOWED_WRITE_DIRS
    )


def is_path_traversal(path_str: str) -> bool:
    """Detect path traversal attempts (.. in path)."""
    return ".." in path_str


def validate_source_path(source_path: str) -> str:
    """Validate a source path for ingest operations. Returns error message or empty string."""
    if not source_path:
        return "source_path is required"
    if is_path_traversal(source_path):
        return f"Path traversal detected in source_path: {source_path}"
    resolved = Path(source_path).expanduser().resolve()
    if not resolved.exists():
        return f"Path does not exist: {source_path}"
    return ""


# ── Tool permission levels (A5) ─────────────────────────────────

PERMISSION_READ = "READ"
PERMISSION_WRITE = "WRITE"
PERMISSION_DANGEROUS = "DANGEROUS"

# Tool → permission level mapping
TOOL_PERMISSIONS: Dict[str, str] = {
    # Read-only tools
    "review_query_state_tool": PERMISSION_READ,
    "review_query_comments_tool": PERMISSION_READ,
    "review_query_diagnostics_tool": PERMISSION_READ,
    "review_query_versions_tool": PERMISSION_READ,
    "vlm_status_tool": PERMISSION_READ,
    "library_search_tool": PERMISSION_READ,
    "project_list_tool": PERMISSION_READ,
    # Write tools
    "review_init_tool": PERMISSION_WRITE,
    "review_add_comment_tool": PERMISSION_WRITE,
    "review_resolve_comment_tool": PERMISSION_WRITE,
    "review_ai_reedit_tool": PERMISSION_WRITE,
    "review_ai_reedit_dry_run_tool": PERMISSION_WRITE,
    "review_export_comments_tool": PERMISSION_READ,
    "vlm_describe_region_tool": PERMISSION_WRITE,
    "vlm_diagnose_frame_tool": PERMISSION_WRITE,
    "enhance_audio_tool": PERMISSION_WRITE,
    "enhance_tts_tool": PERMISSION_WRITE,
    "enhance_bgm_tool": PERMISSION_WRITE,
    "enhance_transition_tool": PERMISSION_WRITE,
    "library_ingest_tool": PERMISSION_WRITE,
    "project_create_tool": PERMISSION_WRITE,
    "workflow_run_tool": PERMISSION_WRITE,
    # Workflow step tools (all write)
    "video_step1_analyze": PERMISSION_WRITE,
    "video_step2_plan": PERMISSION_WRITE,
    "video_step3_script": PERMISSION_WRITE,
    "video_step4_match": PERMISSION_WRITE,
    "video_step5_preview": PERMISSION_WRITE,
    "video_step6_cut": PERMISSION_WRITE,
    "video_step7_render": PERMISSION_WRITE,
}


def get_permission_level(tool_name: str) -> str:
    """Get the permission level for a tool. Defaults to WRITE for unknown tools."""
    return TOOL_PERMISSIONS.get(tool_name, PERMISSION_WRITE)


# ── Audit logging (A5) ──────────────────────────────────────────

_AUDIT_LOG_PATH = os.path.join("data", "mcp_audit.jsonl")


def log_audit(tool_name: str, args_summary: str, result_status: str) -> None:
    """Append an audit entry to the JSONL log."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool_name": tool_name,
        "args_hash": args_summary[:200],
        "result_status": result_status,
        "permission": get_permission_level(tool_name),
    }
    try:
        os.makedirs(os.path.dirname(_AUDIT_LOG_PATH), exist_ok=True)
        with open(_AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("Audit log write failed: %s", exc)
