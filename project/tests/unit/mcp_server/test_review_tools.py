"""Unit tests for MCP review tools (A1)."""

import json
from unittest.mock import patch, MagicMock

import pytest

from modules.mcp_server.tools.review_tools import (
    review_init,
    review_add_comment,
    review_resolve_comment,
    review_ai_reedit,
    review_export_comments,
)


def _mock_urlopen(response_data):
    """Create a mock for urllib.request.urlopen that returns response_data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@patch("modules.mcp_server.tools.review_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_tools.urllib.request.urlopen")
def test_review_init(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"session_id": "s123"})
    result = review_init("/tmp/proj", "/tmp/video.mp4")
    assert result["session_id"] == "s123"


@patch("modules.mcp_server.tools.review_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_tools.urllib.request.urlopen")
def test_review_add_comment(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"comment_id": "c1", "success": True})
    result = review_add_comment("s123", "Good shot", 1500)
    assert result["comment_id"] == "c1"


@patch("modules.mcp_server.tools.review_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_tools.urllib.request.urlopen")
def test_review_resolve(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"resolved": True})
    result = review_resolve_comment("c1")
    assert result["resolved"] is True


@patch("modules.mcp_server.tools.review_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_tools.urllib.request.urlopen")
def test_review_ai_reedit(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"version": 2, "changes": []})
    result = review_ai_reedit("s123")
    assert result["version"] == 2


@patch("modules.mcp_server.tools.review_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_tools.urllib.request.urlopen")
def test_review_export(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"comments": [{"id": "c1"}]})
    result = review_export_comments("s123")
    assert len(result["comments"]) == 1
