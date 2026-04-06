"""Unit tests for MCP VLM tools (A2)."""

import json
from unittest.mock import patch, MagicMock

import pytest

from modules.mcp_server.tools.vlm_tools import (
    vlm_describe_region,
    vlm_diagnose_frame,
    vlm_status,
)


def _mock_urlopen(response_data):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@patch("modules.mcp_server.tools.vlm_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.vlm_tools.urllib.request.urlopen")
def test_vlm_describe(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"description": "sunset beach", "objects": ["person"]})
    result = vlm_describe_region("s1", "base64data", [{"tool": "rect"}], 1000)
    assert result["description"] == "sunset beach"


@patch("modules.mcp_server.tools.vlm_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.vlm_tools.urllib.request.urlopen")
def test_vlm_diagnose(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"issues": [], "score": 85})
    result = vlm_diagnose_frame("s1", "base64data", 500)
    assert result["score"] == 85


@patch("modules.mcp_server.tools.vlm_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.vlm_tools.urllib.request.urlopen")
def test_vlm_status(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"provider": "stub", "available": True})
    result = vlm_status()
    assert result["available"] is True
