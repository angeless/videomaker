"""Tests for VLM API routes (v0.17.0 R16)."""

import base64
import io
import json

import pytest

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

pytestmark = pytest.mark.skipif(not _HAS_PIL, reason="PIL not available")

from flask import Flask

from modules.adapters.vlm_adapter import StubVLMAdapter
from modules.app_api.routes.vlm_routes import create_vlm_blueprint
from modules.review_engine.review_store import ReviewStore


@pytest.fixture
def app(tmp_path):
    store = ReviewStore(str(tmp_path / "test.db"))
    sid = store.create_session(
        project_path="/tmp", video_path="/tmp/v.mp4", video_type="speech",
    )
    adapter = StubVLMAdapter(fixed_response=json.dumps({
        "summary": "test object",
        "objects": ["cup"],
        "scene_type": "indoor",
        "visual_issues": [],
    }))

    app = Flask(__name__)
    bp = create_vlm_blueprint(
        review_store_getter=lambda: store,
        vlm_adapter_getter=lambda: adapter,
    )
    app.register_blueprint(bp)
    app.config["TESTING"] = True
    app.config["_test_session_id"] = sid
    app.config["_test_store"] = store
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def session_id(app):
    return app.config["_test_session_id"]


def _make_frame_b64():
    img = Image.new("RGB", (100, 100), "red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class TestDescribe:
    def test_describe_success(self, client, session_id):
        resp = client.post(
            f"/api/review/{session_id}/vlm/describe",
            json={"frame_base64": _make_frame_b64(), "strokes": []},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "description" in data
        assert "summary" in data["description"]

    def test_describe_missing_frame(self, client, session_id):
        resp = client.post(
            f"/api/review/{session_id}/vlm/describe",
            json={},
        )
        assert resp.status_code == 400
        assert "MISSING_FRAME" in resp.get_json()["error"]

    def test_describe_invalid_session(self, client):
        resp = client.post(
            "/api/review/nonexistent/vlm/describe",
            json={"frame_base64": _make_frame_b64()},
        )
        assert resp.status_code == 404


class TestDiagnose:
    def test_diagnose_success(self, client, session_id):
        resp = client.post(
            f"/api/review/{session_id}/vlm/diagnose",
            json={"frame_base64": _make_frame_b64()},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "diagnostics" in data
        assert isinstance(data["diagnostics"], list)


class TestDiagnosticsList:
    def test_get_diagnostics_empty(self, client, session_id):
        resp = client.get(f"/api/review/{session_id}/vlm/diagnostics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0


class TestStatus:
    def test_status_available(self, client):
        resp = client.get("/api/vlm/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is True
        assert data["provider"] == "stub"

    def test_status_unavailable(self, tmp_path):
        """Test with no adapter configured."""
        store = ReviewStore(str(tmp_path / "test2.db"))
        app = Flask(__name__)
        bp = create_vlm_blueprint(
            review_store_getter=lambda: store,
            vlm_adapter_getter=lambda: None,
        )
        app.register_blueprint(bp)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/api/vlm/status")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["available"] is False
