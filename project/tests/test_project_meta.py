"""Tests for project meta / rename endpoints (T-0604)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flask import Flask
from modules.app_api.routes.legacy_project_routes import create_legacy_project_blueprint
from modules.app_api.param_utils import write_json_result


@pytest.fixture()
def project_dir(tmp_path):
    d = tmp_path / "proj_selected_20260312_193013"
    d.mkdir()
    (d / "data").mkdir()
    (d / "workflow.json").write_text("{}")
    return d


@pytest.fixture()
def client(project_dir):
    app = Flask(__name__)
    app.config["TESTING"] = True
    bp = create_legacy_project_blueprint(
        project_dir_getter=lambda: project_dir,
        workflow_state_getter=lambda: None,
        jobs_getter=lambda: {},
        prepare_project_dirs=lambda p: None,
        library_getter=lambda: None,
        default_project_config=lambda *a, **kw: {},
        load_state=lambda p: None,
        remember_last_project=lambda p: None,
        state_dict=lambda: {},
        run_in_bg=lambda *a, **kw: None,
        choose_path=lambda t: {},
    )
    app.register_blueprint(bp)
    with app.test_client() as c:
        yield c


class TestProjectMeta:
    def test_meta_fallback_display_name(self, client, project_dir):
        resp = client.get(f"/api/project/meta?project_dir={project_dir}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]
        assert data["meta"]["display_name"] == "项目 2026-03-12"

    def test_meta_reads_existing_file(self, client, project_dir):
        meta = {"display_name": "加拿大 Vlog", "created_at": "2026-03-12T19:30:13"}
        write_json_result(project_dir / "data" / "project_meta.json", meta)
        resp = client.get(f"/api/project/meta?project_dir={project_dir}")
        data = resp.get_json()
        assert data["meta"]["display_name"] == "加拿大 Vlog"

    def test_meta_no_project(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        bp = create_legacy_project_blueprint(
            project_dir_getter=lambda: None,
            workflow_state_getter=lambda: None,
            jobs_getter=lambda: {},
            prepare_project_dirs=lambda p: None,
            library_getter=lambda: None,
            default_project_config=lambda *a, **kw: {},
            load_state=lambda p: None,
            remember_last_project=lambda p: None,
            state_dict=lambda: {},
            run_in_bg=lambda *a, **kw: None,
            choose_path=lambda t: {},
        )
        app.register_blueprint(bp)
        with app.test_client() as c:
            resp = c.get("/api/project/meta")
            assert resp.status_code == 400


class TestProjectRename:
    def test_rename_success(self, client, project_dir):
        resp = client.post("/api/project/rename", json={
            "project_dir": str(project_dir),
            "display_name": "加拿大 Vlog",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]
        assert data["meta"]["display_name"] == "加拿大 Vlog"
        assert data["meta"]["created_at"]
        assert data["meta"]["updated_at"]

        # Verify persisted
        meta_path = project_dir / "data" / "project_meta.json"
        assert meta_path.exists()
        saved = json.loads(meta_path.read_text())
        assert saved["display_name"] == "加拿大 Vlog"

    def test_rename_empty_name(self, client, project_dir):
        resp = client.post("/api/project/rename", json={
            "project_dir": str(project_dir),
            "display_name": "",
        })
        assert resp.status_code == 400
        assert "不能为空" in resp.get_json()["error"]

    def test_rename_too_long(self, client, project_dir):
        resp = client.post("/api/project/rename", json={
            "project_dir": str(project_dir),
            "display_name": "x" * 101,
        })
        assert resp.status_code == 400
        assert "100" in resp.get_json()["error"]

    def test_rename_illegal_chars(self, client, project_dir):
        for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            resp = client.post("/api/project/rename", json={
                "project_dir": str(project_dir),
                "display_name": f"test{ch}name",
            })
            assert resp.status_code == 400, f"Should reject char: {ch}"

    def test_rename_preserves_existing_meta(self, client, project_dir):
        meta = {"display_name": "old", "created_at": "2026-03-01T00:00:00", "custom_field": "keep"}
        write_json_result(project_dir / "data" / "project_meta.json", meta)

        resp = client.post("/api/project/rename", json={
            "project_dir": str(project_dir),
            "display_name": "new name",
        })
        data = resp.get_json()
        assert data["meta"]["display_name"] == "new name"
        assert data["meta"]["created_at"] == "2026-03-01T00:00:00"
        assert data["meta"]["custom_field"] == "keep"
