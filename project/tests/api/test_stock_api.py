"""API tests for stock routes — R23."""

import pytest
from unittest.mock import patch
from flask import Flask

from modules.app_api.routes.stock_routes import create_stock_blueprint


@pytest.fixture
def app():
    jobs = {}
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(
        create_stock_blueprint(jobs_getter=lambda: jobs)
    )
    flask_app.config["_jobs"] = jobs
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestStockAPI:

    def test_search_missing_query(self, client):
        resp = client.get("/api/stock/search")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "MISSING_PARAM"

    def test_search_no_api_key(self, client):
        """Search without PEXELS_API_KEY returns 400."""
        resp = client.get("/api/stock/search?q=ocean")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "STOCK_SEARCH_FAILED"

    def test_download_returns_202(self, client, app):
        resp = client.post("/api/stock/download", json={
            "url": "https://example.com/video.mp4",
        })
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["success"] is True
        assert "job_id" in data
        # Verify job was created
        jobs = app.config["_jobs"]
        assert data["job_id"] in jobs

    def test_download_missing_url(self, client):
        resp = client.post("/api/stock/download", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "MISSING_PARAM"
