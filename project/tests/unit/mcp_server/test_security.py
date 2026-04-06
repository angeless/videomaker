"""Unit tests for MCP security module (A5)."""

import os
import json
import tempfile
from unittest.mock import patch

from modules.mcp_server.security import (
    get_permission_level,
    log_audit,
    is_safe_write_path,
    PERMISSION_READ,
    PERMISSION_WRITE,
    TOOL_PERMISSIONS,
)


def test_permission_tag():
    """Read-only tools should have READ permission."""
    assert get_permission_level("review_query_state_tool") == PERMISSION_READ
    assert get_permission_level("enhance_audio_tool") == PERMISSION_WRITE
    assert get_permission_level("unknown_tool") == PERMISSION_WRITE


def test_audit_logged(tmp_path):
    """Audit log writes a valid JSONL entry."""
    log_path = str(tmp_path / "audit.jsonl")
    with patch("modules.mcp_server.security._AUDIT_LOG_PATH", log_path):
        log_audit("review_init_tool", "project_dir=/tmp/proj", "success")

    with open(log_path) as f:
        entry = json.loads(f.readline())
    assert entry["tool_name"] == "review_init_tool"
    assert entry["result_status"] == "success"
    assert entry["permission"] == PERMISSION_WRITE
    assert "timestamp" in entry


def test_path_whitelist():
    """Whitelist includes review session output directory."""
    from pathlib import Path
    reviews_dir = str(Path.home() / "Movies" / "VideoEditor" / "reviews" / "session1")
    assert is_safe_write_path(reviews_dir) is True


def test_no_delete_exposed():
    """No tool should have DANGEROUS permission (MCP doesn't expose deletes)."""
    from modules.mcp_server.security import PERMISSION_DANGEROUS
    for tool, perm in TOOL_PERMISSIONS.items():
        assert perm != PERMISSION_DANGEROUS, f"{tool} has DANGEROUS permission"
