"""API tests for render endpoints (D4a)."""

import os
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


@pytest.fixture
def app(tmp_path):
    flask_app = Flask(__name__)
    from modules.app_api.routes.render_routes import create_render_blueprint

    # Mock TimelineStore with a timeline that has clips
    store = MagicMock()
    clip = MagicMock()
    clip.start_ms = 0
    clip.end_ms = 3000
    clip.source_path = "/tmp/clip.mp4"
    clip.source_in_ms = 0
    clip.source_out_ms = 3000

    track = MagicMock()
    track.track_type = "video"
    track.clips = [clip]

    timeline = MagicMock()
    timeline.tracks = [track]
    timeline.timeline_id = "tl1"
    store.get_timeline.return_value = timeline

    # Mock ReviewStore so session.project_path points inside tmp_path — this
    # becomes the allowed output directory for path validation.
    review_store = MagicMock()
    review_store.get_session.return_value = {"project_path": str(tmp_path)}

    # Mock JobManager
    jm = MagicMock()
    jm.submit.return_value = "job_001"
    jm.get_status.return_value = {
        "status": "running",
        "progress_pct": 50.0,
        "error": None,
    }
    jm.cancel.return_value = True

    bp = create_render_blueprint(
        timeline_store_getter=lambda: store,
        job_manager_getter=lambda: jm,
        review_store_getter=lambda: review_store,
    )
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True
    # Expose tmp_path so tests can construct valid output paths
    flask_app.config["_RENDER_OUT_DIR"] = str(tmp_path / "output")
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


SID = "test-session"


def test_trigger_render(client, app):
    """POST /api/review/{id}/render returns 202 + job_id."""
    out_path = f"{app.config['_RENDER_OUT_DIR']}/output.mp4"
    resp = client.post(
        f"/api/review/{SID}/render",
        json={"output_path": out_path},
    )
    data = resp.get_json()
    assert resp.status_code == 202
    assert data["job_id"] == "job_001"


def test_trigger_render_rejects_path_traversal(client):
    """POST with output_path outside allowed dir returns 400."""
    resp = client.post(
        f"/api/review/{SID}/render",
        json={"output_path": "/etc/passwd"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "PATH_NOT_ALLOWED"


def test_trigger_render_blocks_concurrent_render_on_same_session(client, app):
    """A second render POST while one is rendering must 409, not orphan the first."""
    out_path = f"{app.config['_RENDER_OUT_DIR']}/first.mp4"
    r1 = client.post(f"/api/review/{SID}/render", json={"output_path": out_path})
    assert r1.status_code == 202

    out_path2 = f"{app.config['_RENDER_OUT_DIR']}/second.mp4"
    r2 = client.post(f"/api/review/{SID}/render", json={"output_path": out_path2})
    assert r2.status_code == 409
    assert r2.get_json()["error"] == "RENDER_IN_PROGRESS"


def test_render_progress(client):
    """GET /api/review/{id}/render/progress returns live progress."""
    # First trigger a render
    client.post(f"/api/review/{SID}/render", json={})
    # Then check progress
    resp = client.get(f"/api/review/{SID}/render/progress")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert "percent" in data
    assert "encoder" in data
    assert "elapsed_s" in data


def test_render_cancel(client):
    """POST /api/review/{id}/render/cancel stops the render."""
    client.post(f"/api/review/{SID}/render", json={})
    resp = client.post(f"/api/review/{SID}/render/cancel")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["cancelled"] is True


def test_render_complete_status(client, app):
    """After render completes, progress shows status=done."""
    # Trigger render first (must use an allowed path)
    out_path = f"{app.config['_RENDER_OUT_DIR']}/done.mp4"
    client.post(f"/api/review/{SID}/render", json={"output_path": out_path})

    # Simulate completion by querying progress
    resp = client.get(f"/api/review/{SID}/render/progress")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "status" in data


def test_progress_not_found_for_unknown_session(client):
    """/progress on a session that never rendered returns 404."""
    resp = client.get("/api/review/ghost-session/render/progress")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "NOT_FOUND"


# ── Reconciliation regression: a real test that exercises the failed branch ──

@pytest.fixture
def app_with_jm_control(tmp_path):
    """Like `app` but exposes the jm mock so tests can mutate get_status."""
    flask_app = Flask(__name__)
    from modules.app_api.routes.render_routes import create_render_blueprint

    store = MagicMock()
    clip = MagicMock()
    clip.start_ms = 0
    clip.end_ms = 3000
    clip.source_path = "/tmp/clip.mp4"
    clip.source_in_ms = 0
    clip.source_out_ms = 3000
    track = MagicMock()
    track.track_type = "video"
    track.clips = [clip]
    timeline = MagicMock()
    timeline.tracks = [track]
    timeline.timeline_id = "tl1"
    store.get_timeline.return_value = timeline

    review_store = MagicMock()
    review_store.get_session.return_value = {"project_path": str(tmp_path)}

    jm = MagicMock()
    jm.submit.return_value = "job_001"
    jm.get_status.return_value = {"status": "running", "progress_pct": 50.0, "error": None}
    jm.cancel.return_value = True

    bp = create_render_blueprint(
        timeline_store_getter=lambda: store,
        job_manager_getter=lambda: jm,
        review_store_getter=lambda: review_store,
    )
    flask_app.register_blueprint(bp)
    flask_app.config["TESTING"] = True
    flask_app.config["_RENDER_OUT_DIR"] = str(tmp_path / "output")
    flask_app.config["_JM_MOCK"] = jm  # exposed for tests to mutate
    return flask_app


def test_progress_reconciles_failed_status_unblocks_next_render(app_with_jm_control):
    """When JM reports 'failed' for a session whose state still says 'rendering',
    /progress must write back the terminal status so the 409 guard releases
    and the user can retry."""
    client = app_with_jm_control.test_client()
    out_path = f"{app_with_jm_control.config['_RENDER_OUT_DIR']}/r1.mp4"
    jm = app_with_jm_control.config["_JM_MOCK"]

    # 1. POST first render — state=rendering, jm=running
    r1 = client.post(f"/api/review/{SID}/render", json={"output_path": out_path})
    assert r1.status_code == 202

    # 2. Second POST blocked (409) because state=rendering
    r2 = client.post(f"/api/review/{SID}/render", json={"output_path": out_path})
    assert r2.status_code == 409

    # 3. Simulate the worker raising before _do_render's except branch ran
    #    (e.g., killed mid-task). JM record updates to "failed" but _render_state
    #    is stuck at "rendering". Mutate jm to report failed.
    jm.get_status.return_value = {
        "status": "failed", "progress_pct": 30.0, "error": "ffmpeg crashed",
    }

    # 4. /progress should now reconcile state.status -> "failed"
    p = client.get(f"/api/review/{SID}/render/progress")
    pdata = p.get_json()
    assert pdata["status"] == "failed"
    assert pdata.get("error") == "ffmpeg crashed"

    # 5. With state reconciled to terminal, next POST must succeed (not 409)
    r3 = client.post(f"/api/review/{SID}/render", json={"output_path": out_path})
    assert r3.status_code == 202, f"expected 202 after reconciliation, got {r3.status_code}: {r3.get_data(as_text=True)}"
