"""Unit tests for MCP enhance tools (A3)."""

import json
from unittest.mock import patch, MagicMock

import pytest

from modules.mcp_server.tools.enhance_tools import (
    enhance_audio,
    enhance_tts,
    enhance_bgm,
    enhance_transition,
)


def _mock_urlopen(response_data):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@patch("modules.mcp_server.tools.enhance_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.enhance_tools.urllib.request.urlopen")
def test_enhance_audio(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"success": True, "output_path": "/tmp/enhanced.wav"})
    result = enhance_audio("s1", denoise=True, eq=True, compressor=True, loudness_target=-16.0)
    assert result["success"] is True


@patch("modules.mcp_server.tools.enhance_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.enhance_tools.urllib.request.urlopen")
def test_enhance_tts(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"success": True, "audio_path": "/tmp/tts.wav"})
    result = enhance_tts("s1", "Hello world", voice="default", language="en")
    assert result["success"] is True


@patch("modules.mcp_server.tools.enhance_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.enhance_tools.urllib.request.urlopen")
def test_enhance_bgm(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"success": True, "bgm_path": "/tmp/bgm.mp3"})
    result = enhance_bgm("s1", genre="chill", beat_align=True)
    assert result["success"] is True


@patch("modules.mcp_server.tools.enhance_tools.check_backend_health", return_value=(True, "ok"))
@patch("modules.mcp_server.tools.enhance_tools.urllib.request.urlopen")
def test_enhance_transition(mock_urlopen, mock_health):
    mock_urlopen.return_value = _mock_urlopen({"success": True, "effect": "cross_dissolve"})
    result = enhance_transition("s1", effect="cross_dissolve", duration_ms=500)
    assert result["success"] is True
