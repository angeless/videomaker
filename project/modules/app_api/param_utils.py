#!/usr/bin/env python3
"""Shared parameter parsing utilities for API route handlers."""

from __future__ import annotations

import json
from typing import Any


def parse_int_param(
    value: Any,
    default: int,
    min_val: int = 0,
    max_val: int = 10000,
) -> int:
    """Parse an integer from a request parameter with bounds clamping.

    Safely converts *value* to int and clamps to [min_val, max_val].
    Returns *default* if conversion fails (None, empty string, non-numeric).

    >>> parse_int_param("42", default=10, min_val=1, max_val=100)
    42
    >>> parse_int_param(None, default=10, min_val=1, max_val=100)
    10
    >>> parse_int_param("abc", default=10, min_val=1, max_val=100)
    10
    >>> parse_int_param("-5", default=10, min_val=1, max_val=100)
    1
    >>> parse_int_param("999", default=10, min_val=1, max_val=100)
    100
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return max(min_val, min(default, max_val))
    return max(min_val, min(v, max_val))


def parse_float_param(
    value: Any,
    default: float,
    min_val: float = 0.0,
    max_val: float = 1e9,
) -> float:
    """Parse a float from a request parameter with bounds clamping.

    >>> parse_float_param("3.14", default=1.0, min_val=0.0, max_val=10.0)
    3.14
    >>> parse_float_param(None, default=1.0, min_val=0.0, max_val=10.0)
    1.0
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return max(min_val, min(default, max_val))
    return max(min_val, min(v, max_val))


def parse_str_param(value: Any, default: str = "") -> str:
    """Parse a string from a request parameter with safe defaults.

    Converts *value* to a stripped string, falling back to *default*
    when *value* is falsy (None, empty string, 0, etc.).

    Replaces the repetitive ``str(payload.get("key", "") or "").strip()`` pattern.

    >>> parse_str_param("  hello  ")
    'hello'
    >>> parse_str_param(None, default="fallback")
    'fallback'
    >>> parse_str_param("", default="x")
    'x'
    >>> parse_str_param(0, default="zero")
    'zero'
    """
    return str(value or default).strip()


def safe_error_response(exc: Exception, fallback_msg: str = "操作失败，请重试") -> str:
    """Return a user-friendly error string from an exception.

    Strips Python-internal traceback details; keeps the first line of the
    message up to 120 chars so it is safe to display in a toast.
    """
    msg = str(exc).strip().split("\n")[0][:120]
    if not msg or msg.startswith("Traceback") or "Error" in type(exc).__name__:
        return fallback_msg
    return msg


def sanitize_ffmpeg_bin(value: Any, default: str = "ffmpeg") -> str:
    """Sanitize a user-supplied ffmpeg/ffprobe binary path.

    Many capability routes accept ``ffmpeg_bin`` / ``ffprobe_bin`` from
    the request payload so operators can point the server at a custom
    build. Without sanitization this is an **arbitrary-program execution**
    hazard: any local-token holder (or a token leaked via XSS) could POST
    ``{"ffmpeg_bin": "/tmp/malicious.sh"}`` and the server would invoke
    it via ``subprocess.run(cmd, ...)`` with the app's privileges.

    Accepted forms:
      - Empty / None → returns *default* ("ffmpeg" or "ffprobe")
      - A plain basename matching the default (e.g. "ffmpeg", "ffprobe"):
        resolved via ``shutil.which`` when available, else returned as-is
        (PATH lookup).
      - An absolute path whose basename is ffmpeg / ffprobe / ffmpeg.exe
        / ffprobe.exe: allowed, so operators with a custom toolchain still
        work.

    Anything else (shell metacharacters, paths that don't end in the
    expected binary name, etc.) falls back to *default*.

    >>> sanitize_ffmpeg_bin("ffmpeg")
    'ffmpeg'
    >>> sanitize_ffmpeg_bin("/tmp/evil.sh", default="ffmpeg")
    'ffmpeg'
    >>> sanitize_ffmpeg_bin("/usr/local/bin/ffmpeg")
    '/usr/local/bin/ffmpeg'
    >>> sanitize_ffmpeg_bin("", default="ffprobe")
    'ffprobe'
    """
    import os
    import re

    if default not in ("ffmpeg", "ffprobe"):
        default = "ffmpeg"

    v = str(value or "").strip()
    if not v:
        return default
    # Reject any shell metacharacter — defence in depth even though shell=False.
    if re.search(r"[;&|`$<>\n\r\t]", v):
        return default
    # Plain name: must match the default family
    if v == default or v == f"{default}.exe":
        return v
    # Absolute path: verify it exists and has the expected basename.
    if os.path.isabs(v):
        base = os.path.basename(v).lower()
        if base in (default, f"{default}.exe") and os.path.isfile(v):
            return v
    # Anything else (relative paths, wrong basename, dotdot segments, etc.) → default
    return default


def is_safe_outbound_url(url: str) -> tuple[bool, str]:
    """SSRF guard for server-side outbound HTTP requests.

    When a route calls ``urlopen(user_supplied_url)``, an attacker with
    local-token access can weaponize the server to probe internal hosts
    (AWS metadata at 169.254.169.254, internal admin panels, loopback
    services like Ollama on 127.0.0.1:11434, etc.). This helper rejects
    URLs whose resolved IP falls inside any private / loopback / link-local /
    multicast / reserved range, and rejects non-http(s) schemes outright.

    Returns ``(ok, reason)``. ``reason`` is empty on success.

    >>> is_safe_outbound_url("https://example.com/hook")[0]
    True
    >>> is_safe_outbound_url("http://127.0.0.1/ssh")[0]
    False
    >>> is_safe_outbound_url("http://169.254.169.254/")[0]
    False
    >>> is_safe_outbound_url("file:///etc/passwd")[0]
    False
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception as exc:
        return False, f"URL 格式无效: {exc}"
    if parsed.scheme not in ("http", "https"):
        return False, f"仅支持 http/https (got {parsed.scheme})"
    host = parsed.hostname
    if not host:
        return False, "URL 缺少主机名"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return False, f"DNS 解析失败: {exc}"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError):
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_multicast or ip.is_reserved:
            return False, f"禁止连接内网/回环地址: {ip}"
    return True, ""


def atomic_write_json(path: Any, data: Any, *, indent: int = 2) -> None:
    """Atomically write JSON to *path*.

    Plain ``p.write_text(json.dumps(...))`` truncates then writes, so a
    crash / power loss / kill-9 mid-write leaves an empty or half-written
    file. For app_settings.json this wipes stored API-key references; for
    workflow.json / idempotency caches it corrupts the ledger.

    This helper writes to a sibling tmp file, fsync's, then atomically
    renames (POSIX rename is atomic on the same filesystem) — callers
    always see either the old file or the new one, never a partial write.

    Round-12 finding: 10+ service files had open-coded ``write_text``.
    Standardizing through this helper is cheaper than auditing each.
    """
    import json as _json
    import os as _os
    import tempfile as _tf
    from pathlib import Path as _Path

    target = _Path(path) if not isinstance(path, _Path) else path
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = _tf.mkstemp(dir=str(target.parent), suffix=".tmp", prefix=target.name + ".")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            _os.fsync(f.fileno())
        _os.replace(tmp, str(target))
    except BaseException:
        if _os.path.exists(tmp):
            try:
                _os.unlink(tmp)
            except OSError:
                pass
        raise


def write_json_result(path_obj: Any, data: Any) -> bool:
    """Write *data* as pretty-printed JSON to *path_obj* if it is not None.

    This is a convenience wrapper for the repetitive pattern::

        out = project_data_path("some_file.json")
        if out is not None:
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    Returns True if the file was written, False if *path_obj* was None.
    """
    if path_obj is None:
        return False
    path_obj.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True
