"""Tests for R1 fixes: M3 (project filtering), H2 (library sync), M5 (render config)."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# === M3: Filter missing projects ===

class TestFilterMissingProjects:
    """settings_service._get_recent_projects should skip missing projects."""

    def test_missing_project_filtered(self, tmp_path):
        """Projects whose dirs don't exist should not appear in results."""
        from modules.app_api.services.settings_service import _get_recent_projects, _read_settings, _write_settings

        existing_dir = tmp_path / "real_project"
        existing_dir.mkdir()
        (existing_dir / "workflow.json").write_text(
            json.dumps({"current_step": 1, "total_steps": 7, "completed_steps": []}),
            encoding="utf-8",
        )

        settings = _read_settings()
        settings["recent_projects"] = [
            {"path": str(existing_dir), "name": "real"},
            {"path": str(tmp_path / "ghost_project"), "name": "ghost"},
        ]
        _write_settings(settings)

        projects = _get_recent_projects()
        names = [p["name"] for p in projects]
        assert "real" in names
        assert "ghost" not in names

    def test_cleanup_missing_projects(self, tmp_path):
        """cleanup_missing_projects removes entries for non-existent dirs."""
        from modules.app_api.services.settings_service import cleanup_missing_projects, _read_settings, _write_settings

        existing_dir = tmp_path / "exists"
        existing_dir.mkdir()

        settings = _read_settings()
        settings["recent_projects"] = [
            {"path": str(existing_dir), "name": "exists"},
            {"path": str(tmp_path / "gone1"), "name": "gone1"},
            {"path": str(tmp_path / "gone2"), "name": "gone2"},
        ]
        _write_settings(settings)

        removed = cleanup_missing_projects()
        assert removed == 2

        settings_after = _read_settings()
        assert len(settings_after["recent_projects"]) == 1


# === H2: Library sync ===

class TestLibrarySync:
    """GlobalMediaLibrary.sync_project_materials should update library records."""

    def test_sync_no_materials_file(self, tmp_path):
        """Returns error when no materials.json exists."""
        from modules.library.global_media_library import GlobalMediaLibrary
        lib = GlobalMediaLibrary(db_path=tmp_path / "lib.db")
        lib._init_db()
        result = lib.sync_project_materials(tmp_path / "nonexistent")
        assert result["error"]

    def test_sync_updates_records(self, tmp_path):
        """Syncs project analysis data back to library."""
        from modules.library.global_media_library import GlobalMediaLibrary
        lib = GlobalMediaLibrary(db_path=tmp_path / "lib.db")
        lib._init_db()

        # Insert a dummy asset
        import sqlite3
        conn = sqlite3.connect(str(tmp_path / "lib.db"))
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO assets (uid, sha256, filename, source_type, primary_path, analysis_json, semantic_json, keywords_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("test-uid", "abc123sha256", "test.mp4", "local", "/tmp/test.mp4", "{}", "{}", "[]", "2026-01-01", "2026-01-01"),
        )
        conn.commit()
        conn.close()

        # Create project materials.json
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        materials = {
            "test-uid": {
                "filename": "test.mp4",
                "analysis": {"scene": "beach"},
                "semantic": {"mood": "happy"},
                "semantic_keywords": ["beach", "sunset"],
            }
        }
        (project_dir / "materials.json").write_text(
            json.dumps(materials), encoding="utf-8"
        )

        result = lib.sync_project_materials(project_dir)
        assert result["updated"] == 1
        assert result["not_found"] == 0

        # Verify update in DB
        conn = sqlite3.connect(str(tmp_path / "lib.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT analysis_json, semantic_json FROM assets WHERE uid='test-uid'").fetchone()
        conn.close()
        assert "beach" in row["analysis_json"]
        assert "happy" in row["semantic_json"]


# === M5: Render config from preset ===

class TestRenderConfigPreset:
    """RenderConfig.from_aesthetic_preset should match preset orientation."""

    def test_travel_story_vertical(self):
        from modules.step7_final_render.auto_render import RenderConfig
        cfg = RenderConfig.from_aesthetic_preset("travel_story")
        assert cfg.width == 1080
        assert cfg.height == 1920

    def test_cinematic_horizontal(self):
        from modules.step7_final_render.auto_render import RenderConfig
        cfg = RenderConfig.from_aesthetic_preset("cinematic")
        assert cfg.width == 1920
        assert cfg.height == 1080

    def test_clean_vlog_vertical(self):
        from modules.step7_final_render.auto_render import RenderConfig
        cfg = RenderConfig.from_aesthetic_preset("clean_vlog")
        assert cfg.width == 1080
        assert cfg.height == 1920

    def test_unknown_preset_defaults_vertical(self):
        from modules.step7_final_render.auto_render import RenderConfig
        cfg = RenderConfig.from_aesthetic_preset("unknown_style")
        assert cfg.width == 1080
        assert cfg.height == 1920

    def test_override_works(self):
        from modules.step7_final_render.auto_render import RenderConfig
        cfg = RenderConfig.from_aesthetic_preset("cinematic", fps=60)
        assert cfg.width == 1920
        assert cfg.fps == 60
