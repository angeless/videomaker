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

    def test_download_returns_501(self, client, app):
        """Round-15 H2: endpoint used to dead-stub (create queued job
        with no worker). Now returns 501 to surface the gap."""
        resp = client.post("/api/stock/download", json={
            "url": "https://example.com/video.mp4",
        })
        assert resp.status_code == 501
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"] == "NOT_IMPLEMENTED"
        # No phantom job should be created
        jobs = app.config["_jobs"]
        assert len(jobs) == 0

    def test_download_missing_url_still_501(self, client):
        """Even with missing params, the endpoint is not implemented —
        501 takes precedence over 400 (the endpoint is deliberately dead)."""
        resp = client.post("/api/stock/download", json={})
        assert resp.status_code == 501
        assert resp.get_json()["error"] == "NOT_IMPLEMENTED"
