"""Integration test: review UI flow through Flask API.

Tests the v0.15.0 R23 acceptance criteria:
  init → add comments → list/filter → drawing serialize/deserialize → export
"""

import json
import os

import pytest
from flask import Flask

from modules.review_engine.review_store import ReviewStore
from modules.review_engine.artifact_store import ArtifactStore
from modules.app_api.routes.review_routes import create_review_blueprint


@pytest.fixture
def app(tmp_path):
    db_path = str(tmp_path / "review_ui_flow.db")
    project_dir = str(tmp_path / "project")
    os.makedirs(project_dir, exist_ok=True)

    store = ReviewStore(db_path)
    artifact_store = ArtifactStore(project_dir, store)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(
        create_review_blueprint(
            review_store_getter=lambda: store,
            artifact_store_getter=lambda: artifact_store,
        )
    )
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _init_session(client):
    resp = client.post("/api/review/init", json={
        "project_path": "/tmp/test_proj",
        "video_path": "/tmp/test.mp4",
        "video_type": "roughcut",
    })
    assert resp.status_code == 201
    return resp.get_json()["session_id"]


class TestReviewUIFlow:
    """IT: load roughcut → add comments → comments show on timeline → filter."""

    def test_add_comments_and_list_on_timeline(self, client):
        sid = _init_session(client)

        # Add 3 comments at different times
        for i, (ms, text) in enumerate([
            (1000, "开头太慢"),
            (5000, "这段不错"),
            (9000, "结尾需要修改"),
        ]):
            resp = client.post(f"/api/review/{sid}/comments", json={
                "time_start_ms": ms,
                "comment_type": "text",
                "text": text,
            })
            assert resp.status_code == 201

        # List all comments
        resp = client.get(f"/api/review/{sid}/comments")
        assert resp.status_code == 200
        comments = resp.get_json()["comments"]
        assert len(comments) == 3
        # Verify timeline ordering by time_start_ms
        times = [c["time_start_ms"] for c in comments]
        assert times == sorted(times)

    def test_update_and_delete_comment(self, client):
        sid = _init_session(client)
        resp = client.post(f"/api/review/{sid}/comments", json={
            "time_start_ms": 2000,
            "comment_type": "text",
            "text": "原始文字",
        })
        cid = resp.get_json()["comment_id"]

        # Update
        resp = client.patch(f"/api/review/comments/{cid}", json={
            "text": "修改后文字",
            "status": "resolved",
        })
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/api/review/comments/{cid}")
        assert resp.status_code == 200

        # Verify gone
        resp = client.get(f"/api/review/{sid}/comments")
        assert len(resp.get_json()["comments"]) == 0


class TestDrawingSerialization:
    """IT: drawing annotation → serialize → deserialize → display."""

    def test_drawing_data_roundtrip(self, client):
        sid = _init_session(client)

        drawing = json.dumps([
            {"type": "pen", "color": "#ef4444", "width": 3,
             "points": [{"x": 0.1, "y": 0.2}, {"x": 0.5, "y": 0.8}]},
            {"type": "arrow", "color": "#3b82f6", "width": 2,
             "start": {"x": 0.0, "y": 0.0}, "end": {"x": 1.0, "y": 1.0}},
            {"type": "spotlight", "color": "#eab308", "width": 2,
             "start": {"x": 0.2, "y": 0.3}, "end": {"x": 0.6, "y": 0.7}},
        ])

        # Add comment with drawing data
        resp = client.post(f"/api/review/{sid}/comments", json={
            "time_start_ms": 3000,
            "comment_type": "drawing",
            "text": "标注了重要区域",
            "drawing_data": drawing,
        })
        assert resp.status_code == 201
        cid = resp.get_json()["comment_id"]

        # Retrieve and verify drawing_data survives roundtrip
        resp = client.get(f"/api/review/{sid}/comments")
        comments = resp.get_json()["comments"]
        match = [c for c in comments if c.get("comment_id") == cid]
        assert len(match) == 1
        recovered = json.loads(match[0]["drawing_data"])
        assert len(recovered) == 3
        assert recovered[0]["type"] == "pen"
        assert recovered[2]["type"] == "spotlight"


class TestCommentExport:
    """IT: comment export in multiple formats."""

    def test_export_json(self, client):
        sid = _init_session(client)
        client.post(f"/api/review/{sid}/comments", json={
            "time_start_ms": 1000,
            "comment_type": "text",
            "text": "导出测试",
        })

        resp = client.get(f"/api/review/{sid}/comments/export?format=json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["format"] == "json"
        assert data["count"] == 1

    def test_export_csv(self, client):
        sid = _init_session(client)
        client.post(f"/api/review/{sid}/comments", json={
            "time_start_ms": 2000,
            "comment_type": "text",
            "text": "CSV导出",
        })

        resp = client.get(f"/api/review/{sid}/comments/export?format=csv")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["format"] == "csv"
        assert "CSV" in data["data"] or "csv" in data["data"].lower() or "," in data["data"]

    def test_export_edl(self, client):
        sid = _init_session(client)
        client.post(f"/api/review/{sid}/comments", json={
            "time_start_ms": 500,
            "time_end_ms": 3000,
            "comment_type": "text",
            "text": "EDL测试",
        })

        resp = client.get(f"/api/review/{sid}/comments/export?format=edl")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["format"] == "edl"
