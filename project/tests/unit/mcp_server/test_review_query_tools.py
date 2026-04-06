"""Unit tests for MCP read-only query tools (A4)."""

import json
from unittest.mock import patch, MagicMock

from modules.mcp_server.tools.review_query_tools import (
    review_query_state,
    review_query_comments,
    review_query_diagnostics,
    review_query_versions,
)


def _mock_urlopen(response_data):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@patch("modules.mcp_server.tools.review_query_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_query_tools.urllib.request.urlopen")
def test_query_state(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"session_id": "s1", "version": 3})
    result = review_query_state("s1")
    assert result["version"] == 3


@patch("modules.mcp_server.tools.review_query_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_query_tools.urllib.request.urlopen")
def test_query_comments(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"comments": [{"id": "c1"}]})
    result = review_query_comments("s1")
    assert len(result["comments"]) == 1


@patch("modules.mcp_server.tools.review_query_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_query_tools.urllib.request.urlopen")
def test_query_diagnostics(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"diagnostics": [], "score": 90})
    result = review_query_diagnostics("s1")
    assert result["score"] == 90


@patch("modules.mcp_server.tools.review_query_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.review_query_tools.urllib.request.urlopen")
def test_query_versions(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"versions": [1, 2, 3]})
    result = review_query_versions("s1")
    assert len(result["versions"]) == 3
