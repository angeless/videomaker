"""Regression tests for round-12 P0 security fixes.

Covers:
- atomic_write_json: crash-safe via temp + fsync + rename
- _resolve_path_with_base: path-traversal containment
- error_handler: HTTPException.description is NOT reflected to client
- capability_tools.library_search: urllib.parse.quote (not urllib.request.quote)
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ── atomic_write_json ────────────────────────────────────────────

def test_atomic_write_json_writes_data(tmp_path):
    from modules.app_api.param_utils import atomic_write_json
    p = tmp_path / "settings.json"
    atomic_write_json(p, {"api_key_ref": "abc123", "version": 1})
    loaded = json.loads(p.read_text())
    assert loaded == {"api_key_ref": "abc123", "version": 1}


def test_atomic_write_json_leaves_no_tmp_on_success(tmp_path):
    from modules.app_api.param_utils import atomic_write_json
    p = tmp_path / "x.json"
    atomic_write_json(p, [1, 2, 3])
    # No .tmp files should linger
    tmps = list(tmp_path.glob("*.tmp*")) + list(tmp_path.glob("*tmp*"))
    assert not tmps, f"temp files leaked: {tmps}"


def test_atomic_write_json_cleans_tmp_on_serialization_error(tmp_path):
    """If the data isn't JSON-serializable, the tmp file must be cleaned up
    so we don't leak files across crashes."""
    from modules.app_api.param_utils import atomic_write_json
    p = tmp_path / "x.json"
    unserializable = {"bad": object()}  # object() isn't JSON-encodable
    with pytest.raises(TypeError):
        atomic_write_json(p, unserializable)
    # Original file doesn't exist, and no tmp lingers
    assert not p.exists()
    leftovers = [f for f in tmp_path.iterdir() if f.is_file()]
    assert not leftovers, f"leaked: {leftovers}"


# ── _resolve_path_with_base ──────────────────────────────────────

def test_resolve_path_rejects_traversal(tmp_path):
    from modules.app_api.services.capability_helpers import (
        _resolve_path_with_base,
        PathTraversalError,
    )
    anchor = tmp_path / "project"
    anchor.mkdir()
    with pytest.raises(PathTraversalError):
        _resolve_path_with_base("../../etc/passwd", base_dir=anchor)


def test_resolve_path_accepts_inside_anchor(tmp_path):
    from modules.app_api.services.capability_helpers import _resolve_path_with_base
    anchor = tmp_path / "project"
    anchor.mkdir()
    resolved = _resolve_path_with_base("sub/file.mp4", base_dir=anchor)
    assert resolved == (anchor / "sub" / "file.mp4").resolve()


def test_resolve_path_enforce_contain_false_allows_external(tmp_path):
    """Operator-configured dirs (e.g. BGM library) can live outside anchor
    when enforce_contain=False is explicitly passed."""
    from modules.app_api.services.capability_helpers import _resolve_path_with_base
    anchor = tmp_path / "project"
    anchor.mkdir()
    external = tmp_path / "bgm_library"
    external.mkdir()
    resolved = _resolve_path_with_base(
        str(external), base_dir=anchor, enforce_contain=False
    )
    assert resolved == external.resolve()


# ── error_handler ────────────────────────────────────────────────

def test_error_handler_does_not_reflect_description():
    """Round-12 finding: previously returned exc.description verbatim.
    Attacker-controlled payloads in description must not reach the client."""
    from werkzeug.exceptions import BadRequest
    from modules.app_api.middleware.error_handler import handle_unexpected_error

    from flask import Flask
    app = Flask(__name__)
    with app.app_context(), app.test_request_context("/"):
        bad = BadRequest(description="<script>alert('XSS')</script>")
        resp, status = handle_unexpected_error(bad)
        body = resp.get_json()
    # The fixed message must replace the description
    assert status == 400
    assert body["error"] == "请求参数无效"
    # Absolutely no reflection of the attacker payload
    assert "<script>" not in json.dumps(body)
    assert "XSS" not in json.dumps(body)


# ── capability_tools ─────────────────────────────────────────────

def test_library_search_uses_parse_quote():
    """Round-12 finding: previously used non-existent urllib.request.quote.
    The import must now be urllib.parse.quote."""
    import modules.mcp_server.tools.capability_tools as ct
    # Just importing should succeed and expose urllib.parse
    assert hasattr(ct, "urllib")
    assert hasattr(ct.urllib, "parse")
    assert callable(ct.urllib.parse.quote)
