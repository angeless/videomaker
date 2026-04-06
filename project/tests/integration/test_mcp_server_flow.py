"""Integration tests for MCP Server end-to-end flow (A6).

Verifies:
1. FastMCP server instantiation + module import (Python 3.10+ only)
2. Tool discovery — all 29 tools registered
3. Review chain — review_init → review_add_comment → review_query_comments
4. VLM chain — vlm_status → vlm_describe_region (mock backend)
5. Security — path whitelist + traversal prevention
"""

import json
import sys
from unittest.mock import patch, MagicMock

import pytest


# ── Helpers ──────────────────────────────────────────────────────────


def _mock_urlopen(response_data):
    """Create a mock for urllib.request.urlopen returning JSON response."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


HEALTH_OK = (True, "ok")

# Expected 29 tools: 7 workflow + 5 capability + 6 review + 3 VLM + 4 enhance + 4 query
EXPECTED_TOOL_NAMES = sorted([
    # Workflow (7)
    "video_step1_analyze", "video_step2_plan", "video_step3_script",
    "video_step4_match", "video_step5_preview", "video_step6_cut",
    "video_step7_render",
    # Capability (5)
    "library_search_tool", "library_ingest_tool", "project_list_tool",
    "project_create_tool", "workflow_run_tool",
    # Review A1 (6)
    "review_init_tool", "review_add_comment_tool",
    "review_resolve_comment_tool", "review_ai_reedit_tool",
    "review_ai_reedit_dry_run_tool", "review_export_comments_tool",
    # VLM A2 (3)
    "vlm_describe_region_tool", "vlm_diagnose_frame_tool", "vlm_status_tool",
    # Enhance A3 (4)
    "enhance_audio_tool", "enhance_tts_tool", "enhance_bgm_tool",
    "enhance_transition_tool",
    # Query A4 (4)
    "review_query_state_tool", "review_query_comments_tool",
    "review_query_diagnostics_tool", "review_query_versions_tool",
])

EXPECTED_TOOL_COUNT = 29


# ── Test 1: Server starts (Python 3.10+ only) ───────────────────────


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="MCP server requires Python 3.10+ (dict | None syntax)",
)
def test_server_starts():
    """FastMCP object can be imported and is properly configured."""
    fastmcp = pytest.importorskip("fastmcp")  # noqa: F841
    from modules.mcp_server.server import mcp

    assert mcp is not None
    assert mcp.name == "VideoEditor"


# ── Test 2: Tool discovery (Python 3.10+ only) ──────────────────────


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="MCP server requires Python 3.10+ (dict | None syntax)",
)
def test_tool_discovery():
    """All 29 tools are registered in the FastMCP server."""
    pytest.importorskip("fastmcp")
    from modules.mcp_server.server import mcp

    # FastMCP stores tools in _tool_manager._tools (dict keyed by name).
    # Guard against internal API changes.
    tool_mgr = getattr(mcp, "_tool_manager", None)
    assert tool_mgr is not None, "FastMCP internal structure changed — _tool_manager not found"
    tools = getattr(tool_mgr, "_tools", None)
    assert tools is not None, "FastMCP internal structure changed — _tools dict not found"
    registered_names = sorted(tools.keys())
    assert len(registered_names) == EXPECTED_TOOL_COUNT, (
        f"Expected {EXPECTED_TOOL_COUNT} tools, got {len(registered_names)}. "
        f"Missing: {set(EXPECTED_TOOL_NAMES) - set(registered_names)}. "
        f"Extra: {set(registered_names) - set(EXPECTED_TOOL_NAMES)}."
    )
    assert registered_names == EXPECTED_TOOL_NAMES


# ── Test 3: Review chain ────────────────────────────────────────────


@patch("modules.mcp_server.tools.review_query_tools.check_backend_health", return_value=HEALTH_OK)
@patch("modules.mcp_server.tools.review_tools.check_backend_health", return_value=HEALTH_OK)
@patch("urllib.request.urlopen")
def test_review_chain(mock_urlopen, mock_review_health, mock_query_health):
    """End-to-end review flow: init → add_comment → query_comments."""
    from modules.mcp_server.tools.review_tools import review_init, review_add_comment
    from modules.mcp_server.tools.review_query_tools import review_query_comments

    # Step 1: Init session
    mock_urlopen.return_value = _mock_urlopen({"session_id": "s-test-001"})
    init_result = review_init("/tmp/project", "/tmp/video.mp4")
    assert init_result["session_id"] == "s-test-001"

    # Step 2: Add comment
    mock_urlopen.return_value = _mock_urlopen({
        "comment_id": "c-001", "success": True,
    })
    comment_result = review_add_comment("s-test-001", "Nice transition", 3000)
    assert comment_result["comment_id"] == "c-001"

    # Step 3: Query comments
    mock_urlopen.return_value = _mock_urlopen({
        "comments": [{"id": "c-001", "text": "Nice transition", "timestamp_ms": 3000}],
    })
    query_result = review_query_comments("s-test-001")
    assert len(query_result["comments"]) == 1
    assert query_result["comments"][0]["text"] == "Nice transition"


# ── Test 4: VLM chain ───────────────────────────────────────────────


@patch("modules.mcp_server.tools.vlm_tools.check_backend_health", return_value=HEALTH_OK)
@patch("modules.mcp_server.tools.vlm_tools.urllib.request.urlopen")
def test_vlm_chain(mock_urlopen, mock_health):
    """VLM flow: status check → describe region (mock backend)."""
    from modules.mcp_server.tools.vlm_tools import vlm_status, vlm_describe_region

    # Step 1: Check VLM status
    mock_urlopen.return_value = _mock_urlopen({
        "available": True, "provider": "stub", "model": "stub-v1",
    })
    status = vlm_status()
    assert status["available"] is True
    assert status["provider"] == "stub"

    # Step 2: Describe region
    mock_urlopen.return_value = _mock_urlopen({
        "description": "A person walking on the beach",
        "objects": ["person", "beach", "ocean"],
    })
    result = vlm_describe_region(
        session_id="s-test-001",
        frame_base64="base64data",
        strokes=[{"tool": "rect", "points": [[0.1, 0.1], [0.5, 0.5]]}],
        timestamp_ms=5000,
    )
    assert "description" in result
    assert "person" in result["objects"]


# ── Test 5: Security ────────────────────────────────────────────────


def test_security_path_traversal():
    """Path traversal with '..' is detected and rejected."""
    from modules.mcp_server.security import (
        is_path_traversal,
        is_safe_write_path,
        validate_source_path,
        get_permission_level,
        PERMISSION_READ,
        PERMISSION_WRITE,
    )

    # Traversal detection
    assert is_path_traversal("../../../etc/passwd") is True
    assert is_path_traversal("/tmp/safe/path") is False
    assert is_path_traversal("path/with/../dots") is True

    # Safe write path
    assert is_safe_write_path("/tmp/output.mp4") is True
    assert is_safe_write_path("/etc/evil") is False

    # Validate source path rejects traversal
    err = validate_source_path("../../../etc/passwd")
    assert "traversal" in err.lower()

    # Permission levels
    assert get_permission_level("review_query_state_tool") == PERMISSION_READ
    assert get_permission_level("review_init_tool") == PERMISSION_WRITE
    assert get_permission_level("unknown_tool") == PERMISSION_WRITE  # default
