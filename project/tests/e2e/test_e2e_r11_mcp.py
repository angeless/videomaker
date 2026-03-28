"""E2E test for R11: MCP Server — 12 tools, security, offline handling."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.mcp_server.security import is_path_traversal, is_safe_write_path, validate_source_path
from modules.mcp_server.health import check_backend_health
from modules.mcp_server.tools.workflow_tools import STEP_MAP, run_workflow_step
from modules.mcp_server.tools.capability_tools import library_ingest, library_search, project_create


def test_e2e_12_tools_available():
    """Verify 12 tools are defined (7 workflow + 5 capability)."""
    assert len(STEP_MAP) == 7

    from modules.mcp_server.tools import capability_tools as cap
    cap_funcs = [f for f in ["library_search", "library_ingest", "project_list", "project_create", "workflow_run"]
                 if hasattr(cap, f)]
    assert len(cap_funcs) == 5


def test_e2e_no_delete_tools():
    """No delete/remove operations in tool names."""
    for name in STEP_MAP:
        assert "delete" not in name.lower()

    from modules.mcp_server.tools import capability_tools as cap
    for attr in dir(cap):
        if callable(getattr(cap, attr)) and not attr.startswith("_"):
            assert "delete" not in attr.lower()


def test_e2e_path_traversal_blocked():
    result = library_ingest("../../etc/passwd")
    assert "error" in result
    assert result.get("success") is False or "denied" in result["error"].lower()


def test_e2e_project_create_traversal_blocked():
    result = project_create("test", "../../../root")
    assert "error" in result


def test_e2e_offline_backend_readable_error():
    healthy, msg = check_backend_health("http://127.0.0.1:1")
    assert healthy is False
    assert len(msg) > 20  # Should have a helpful message

    result = run_workflow_step("video_step1_analyze", "/tmp/test")
    assert "error" in result
    assert result.get("success") is False


@patch("urllib.request.urlopen")
def test_e2e_step1_analyze_calls_backend(mock_urlopen):
    """When backend is healthy, step1 should call POST /api/agent/tasks/run."""
    # Mock health check
    mock_health_resp = MagicMock()
    mock_health_resp.status = 200
    mock_health_resp.__enter__ = MagicMock(return_value=mock_health_resp)
    mock_health_resp.__exit__ = MagicMock(return_value=False)

    # Mock task response
    mock_task_resp = MagicMock()
    mock_task_resp.status = 200
    mock_task_resp.read.return_value = b'{"success": true, "job_id": "test-123"}'
    mock_task_resp.__enter__ = MagicMock(return_value=mock_task_resp)
    mock_task_resp.__exit__ = MagicMock(return_value=False)

    mock_urlopen.side_effect = [mock_health_resp, mock_task_resp]

    result = run_workflow_step("video_step1_analyze", "/tmp/test_project")
    assert result.get("success") is True
    assert result.get("job_id") == "test-123"


def test_e2e_safe_write_paths():
    home = str(Path.home())
    assert is_safe_write_path(f"{home}/Movies/VideoEditor/exports/out.mp4")
    assert not is_safe_write_path(f"{home}/Desktop/out.mp4")
