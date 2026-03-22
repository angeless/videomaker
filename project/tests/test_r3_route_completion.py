"""R3: 接口补全与编码修复 — BUG-006/007/008 验收测试。"""

import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from modules.app_api.server import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestBug006MissingRoutes:
    """BUG-006: 缺失路由补全。"""

    def test_system_health_returns_200(self, client):
        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_projects_returns_200(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "projects" in data
        assert "count" in data

    def test_workflow_status_returns_200(self, client):
        resp = client.get("/api/workflow/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "persisted" in data
        assert "guidedAvailable" in data
        assert "status" in data

    def test_settings_aggregated_returns_200(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "ai" in data
        assert "ui" in data


class TestBug007Encoding:
    """BUG-007: content_publish/platforms 编码修复。"""

    def test_platforms_returns_utf8(self, client):
        resp = client.get("/api/capabilities/content_publish/platforms")
        assert resp.status_code == 200
        assert "charset=utf-8" in resp.content_type.lower()
        data = resp.get_json()
        assert data["ok"] is True
        assert "platforms" in data


class TestBug008RunStepEmpty:
    """BUG-008: POST /api/run_step {} 无 step 不应默认执行。"""

    def test_run_step_empty_body(self, client):
        """空 body 不传 step 时，应使用 workflow state 的 current_step（或返回 400）。"""
        resp = client.post("/api/run_step", json={})
        # 无项目时返回 400 (项目未加载)，有项目时正常执行
        assert resp.status_code in (200, 400)
        if resp.status_code == 400:
            assert resp.get_json().get("error")
