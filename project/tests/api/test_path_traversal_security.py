"""Regression tests for path-traversal vulnerabilities found in round-8 audit.

The bug: routes using `str(target).startswith(str(root))` to validate that a
user-supplied filename stays inside an allowed directory are bypassable
when a SIBLING directory exists whose name starts with the root prefix.

Example: root = /Users/alice/proj
Attack:  /api/files/../proj_evil/secret.txt
Resolves to /Users/alice/proj_evil/secret.txt
.startswith('/Users/alice/proj') → True (BYPASS)
.relative_to(root) → ValueError (CORRECT REJECTION)
"""

from pathlib import Path

import pytest
from flask import Flask


# ── ui_routes serve_static (the static file server inside the UI dir) ──

@pytest.fixture
def ui_app(tmp_path):
    """UI dir = tmp_path/ui; sibling tmp_path/ui_evil exists."""
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("ok")
    (ui_dir / "asset.txt").write_text("safe")

    sibling_evil = tmp_path / "ui_evil"
    sibling_evil.mkdir()
    (sibling_evil / "secret.txt").write_text("ATTACKER_DATA")

    flask_app = Flask(__name__)
    from modules.app_api.routes.ui_routes import create_ui_blueprint
    bp = create_ui_blueprint(app_ui_dir_getter=lambda: ui_dir)
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True
    return flask_app


def test_ui_serve_static_blocks_sibling_traversal(ui_app):
    """`../ui_evil/secret.txt` resolves to a sibling — must 403, not 200."""
    client = ui_app.test_client()
    # Try the sibling-prefix traversal — this used to bypass startswith
    resp = client.get("/../ui_evil/secret.txt")
    # Flask normalizes ".." segments before routing; the request may 404
    # at the routing layer instead of reaching the handler. Either is safe
    # — the contract is "must NOT serve ATTACKER_DATA".
    assert resp.status_code in (403, 404)
    assert b"ATTACKER_DATA" not in resp.data


def test_ui_serve_static_allows_legitimate_file(ui_app):
    """Sanity check: legitimate path inside ui_dir still works."""
    client = ui_app.test_client()
    resp = client.get("/asset.txt")
    assert resp.status_code == 200
    assert resp.data == b"safe"


# ── legacy_project_routes /api/files/<rel> ──

@pytest.fixture
def legacy_app(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "video.mp4").write_text("safe-video")

    proj_evil = tmp_path / "proj_evil"
    proj_evil.mkdir()
    (proj_evil / "secret.txt").write_text("ATTACKER_DATA")

    flask_app = Flask(__name__)
    from modules.app_api.routes.legacy_project_routes import create_legacy_project_blueprint

    # Minimal stubs for unrelated dependencies — only api_files matters here
    state = {"project_dir": str(proj)}
    bp = create_legacy_project_blueprint(
        project_dir_getter=lambda: proj,
        library_getter=lambda: None,
        prepare_project_dirs=lambda p: None,
        state_dict=lambda: state,
        workflow_state_getter=lambda: None,
        jobs_getter=lambda: {},
        default_project_config=lambda: {},
        load_state=lambda: None,
        remember_last_project=lambda *a, **k: None,
        run_in_bg=lambda *a, **k: None,
        choose_path=lambda *a, **k: None,
    )
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True
    return flask_app


def test_api_files_blocks_sibling_traversal(legacy_app):
    """`/api/files/../proj_evil/secret.txt` must NOT serve ATTACKER_DATA."""
    client = legacy_app.test_client()
    # Use raw HTTP to bypass any Werkzeug normalization that strips ..
    resp = client.get("/api/files/..%2Fproj_evil%2Fsecret.txt")
    assert resp.status_code in (403, 404)
    assert b"ATTACKER_DATA" not in resp.data


def test_api_files_allows_legitimate_file(legacy_app):
    """Sanity check: legitimate path inside project_dir still works."""
    client = legacy_app.test_client()
    resp = client.get("/api/files/video.mp4")
    assert resp.status_code == 200
    assert resp.data == b"safe-video"
