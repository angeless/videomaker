"""Tests for R11: MCP Server module — security, tools, health check."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.mcp_server.security import (
    is_path_traversal,
    is_safe_write_path,
    validate_source_path,
)
from modules.mcp_server.health import check_backend_health
from modules.mcp_server.tools.workflow_tools import STEP_MAP, run_workflow_step
from modules.mcp_server.tools.capability_tools import (
    library_ingest,
    library_search,
    project_create,
)


class TestSecurity:
    def test_path_traversal_detected(self):
        assert is_path_traversal("../../etc/passwd")
        assert is_path_traversal("/home/user/../root")
        assert is_path_traversal("foo/../../bar")

    def test_path_traversal_clean(self):
        assert not is_path_traversal("/Users/user/videos/my_project")
        assert not is_path_traversal("/tmp/export.mp4")

    def test_safe_write_path_allowed(self):
        home = str(Path.home())
        assert is_safe_write_path(f"{home}/Movies/VideoEditor/exports/output.mp4")
        assert is_safe_write_path("/tmp/test_output.mp4")

    def test_safe_write_path_rejected(self):
        assert not is_safe_write_path("/etc/passwd")
        assert not is_safe_write_path("/usr/local/bin/evil")
        home = str(Path.home())
        assert not is_safe_write_path(f"{home}/Documents/secret.txt")

    def test_validate_source_path_empty(self):
        assert validate_source_path("") != ""

    def test_validate_source_path_traversal(self):
        err = validate_source_path("../../etc/passwd")
        assert "traversal" in err.lower()

    def test_validate_source_path_nonexistent(self):
        err = validate_source_path("/nonexistent/path/xyz123")
        assert "exist" in err.lower()


class TestHealthCheck:
    @patch("urllib.request.urlopen")
    def test_healthy_backend(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        healthy, msg = check_backend_health()
        assert healthy is True

    def test_offline_backend(self):
        healthy, msg = check_backend_health("http://127.0.0.1:1")
        assert healthy is False
        assert "offline" in msg.lower() or "Backend" in msg


class TestWorkflowTools:
    def test_step_map_has_7_steps(self):
        assert len(STEP_MAP) == 7
        expected = [
            "video_step1_analyze", "video_step2_plan", "video_step3_script",
            "video_step4_match", "video_step5_preview", "video_step6_cut",
            "video_step7_render",
        ]
        for name in expected:
            assert name in STEP_MAP

    def test_unknown_tool_returns_error(self):
        result = run_workflow_step("nonexistent_tool", "/tmp/test")
        assert "error" in result

    @patch("modules.mcp_server.tools.workflow_tools.check_backend_health")
    def test_offline_returns_readable_error(self, mock_health):
        mock_health.return_value = (False, "Backend offline (ConnectionRefused). Start it with: ...")
        result = run_workflow_step("video_step1_analyze", "/tmp/test")
        assert result["success"] is False
        assert "offline" in result["error"].lower() or "Backend" in result["error"]


class TestCapabilityTools:
    def test_ingest_rejects_traversal(self):
        result = library_ingest("../../etc/passwd")
        assert "error" in result
        assert "denied" in result["error"].lower() or "traversal" in result["error"].lower()

    def test_project_create_rejects_traversal(self):
        result = project_create("test", "../../evil")
        assert "error" in result
        assert "denied" in result["error"].lower() or "traversal" in result["error"].lower()

    @patch("modules.mcp_server.tools.capability_tools.check_backend_health")
    def test_search_offline(self, mock_health):
        mock_health.return_value = (False, "Backend offline")
        result = library_search("sunset")
        assert result["success"] is False


class TestNoDeleteTools:
    """Verify no delete operations are exposed."""
    def test_no_delete_in_workflow_tools(self):
        for name in STEP_MAP:
            assert "delete" not in name.lower()
            assert "remove" not in name.lower()

    def test_no_delete_in_capability_imports(self):
        import modules.mcp_server.tools.capability_tools as cap
        public_funcs = [f for f in dir(cap) if not f.startswith("_") and callable(getattr(cap, f))]
        for f in public_funcs:
            assert "delete" not in f.lower(), f"Found delete function: {f}"
            assert "remove" not in f.lower(), f"Found remove function: {f}"
