"""API tests for style routes — R24."""

import pytest
from flask import Flask

from modules.app_api.routes.style_routes import create_style_blueprint

try:
    import yaml as _yaml
except ImportError:
    _yaml = None

_skip_no_yaml = pytest.mark.skipif(_yaml is None, reason="pyyaml not installed")


@pytest.fixture
def app(tmp_path):
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    project_dir = str(tmp_path)
    flask_app.register_blueprint(
        create_style_blueprint(project_dir_getter=lambda: project_dir)
    )
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestStyleAPI:

    def test_list_styles_empty(self, client):
        resp = client.get("/api/review/styles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["styles"] == []

    @_skip_no_yaml
    def test_save_and_list_style(self, client):
        """Save a style, then list it back."""
        resp = client.post("/api/review/styles", json={
            "name": "vlog_warm",
            "color_grade": "warm",
            "pacing": "fast",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["style_id"] == "vlog_warm"

        # List should return the saved style
        resp2 = client.get("/api/review/styles")
        assert resp2.status_code == 200
        styles = resp2.get_json()["styles"]
        assert len(styles) == 1
        assert styles[0]["name"] == "vlog_warm"
        assert styles[0]["color_grade"] == "warm"

    def test_save_style_missing_name(self, client):
        resp = client.post("/api/review/styles", json={
            "color_grade": "warm",
        })
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "MISSING_PARAM"
