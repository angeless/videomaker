"""Tests for P0-1 security audit logging: service + API + end-to-end."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Unit tests: audit_log service ──────────────────────────────────────


class TestAuditLogService:
    """Direct tests against the audit_log module (no Flask)."""

    def _fresh_module(self):
        """Return a fresh audit_log module with reset state."""
        from modules.app_api.services import audit_log

        audit_log.close()
        return audit_log

    def test_init_creates_table(self, tmp_path):
        al = self._fresh_module()
        db_file = tmp_path / "audit_test.db"
        al.init_audit_log(db_file)
        try:
            al.audit("delete", "custom_tag", "ct_123", actor="local:127.0.0.1")
            rows = al.query()
            assert len(rows) == 1
            assert rows[0]["operation"] == "delete"
            assert rows[0]["resource_type"] == "custom_tag"
            assert rows[0]["resource_id"] == "ct_123"
            assert rows[0]["actor"] == "local:127.0.0.1"
            assert rows[0]["status"] == "ok"
        finally:
            al.close()

    def test_audit_never_raises_before_init(self):
        al = self._fresh_module()
        # These should silently do nothing, never raise
        al.audit("delete", "workflow", "wf_1")
        result = al.query()
        assert result == []
        assert al.count() == 0

    def test_query_filters(self, tmp_path):
        al = self._fresh_module()
        al.init_audit_log(tmp_path / "audit_filter.db")
        try:
            al.audit("delete", "custom_tag", "ct_1", actor="local:127.0.0.1")
            al.audit("config_change", "settings", "ai", actor="local:10.0.0.5")
            al.audit("delete", "workflow", "wf_1", actor="agent:bot_42")

            # filter by operation
            deletes = al.query(operation="delete")
            assert len(deletes) == 2

            # filter by resource_type
            settings = al.query(resource_type="settings")
            assert len(settings) == 1
            assert settings[0]["operation"] == "config_change"

            # filter by actor (LIKE match)
            agent_rows = al.query(actor="agent")
            assert len(agent_rows) == 1
            assert agent_rows[0]["resource_id"] == "wf_1"
        finally:
            al.close()

    def test_audit_records_detail_json(self, tmp_path):
        al = self._fresh_module()
        al.init_audit_log(tmp_path / "audit_detail.db")
        try:
            al.audit(
                "config_change", "settings", "ai",
                actor="local:127.0.0.1",
                detail={"keys_changed": ["provider", "model"]},
            )
            rows = al.query()
            assert len(rows) == 1
            assert rows[0]["detail"] == {"keys_changed": ["provider", "model"]}
        finally:
            al.close()

    def test_audit_records_error_status(self, tmp_path):
        al = self._fresh_module()
        al.init_audit_log(tmp_path / "audit_error.db")
        try:
            al.audit(
                "resolve", "duplicates", "gid_5",
                actor="local:127.0.0.1", status="error",
                detail={"error": "group not found"},
            )
            rows = al.query()
            assert len(rows) == 1
            assert rows[0]["status"] == "error"
            assert rows[0]["detail"]["error"] == "group not found"
        finally:
            al.close()

    def test_count(self, tmp_path):
        al = self._fresh_module()
        al.init_audit_log(tmp_path / "audit_count.db")
        try:
            for i in range(5):
                al.audit("ingest", "library", f"job_{i}")
            assert al.count() == 5
        finally:
            al.close()


# ── API integration tests ──────────────────────────────────────────────

import time
import types

fake_library_mod = types.ModuleType("modules.library.global_media_library")


class _FakeGML:
    def __init__(self, *args, **kwargs):
        self.db_path = ROOT / ".tmp_fake_library.db"

    def stats(self):
        return {}

    def search_assets(self, query="", limit=120, offset=0, retrieval_mode="hybrid", media_type="all"):
        return []

    def count_matching_assets(self, query="", retrieval_mode="hybrid", media_type="all"):
        return 0

    def get_assets(self, uids):
        return []

    def discover_videos(self, root):
        return []

    def discover_images(self, root):
        return []

    def ingest_local_path(self, source_path, max_videos=600, progress_callback=None, should_cancel=None):
        return {"cancelled": False, "scanned": 0, "indexed": 0, "dedup_hits": 0, "failed": 0, "total_candidates": 0, "assets": [], "truncated": False}


fake_library_mod.GlobalMediaLibrary = _FakeGML
sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

from modules.app_api import server  # noqa: E402


class _FakeSecretStore:
    def __init__(self):
        self.available = False
        self.backend = "fake"
        self.values = {}

    def info(self):
        return type("_I", (), {"backend": self.backend, "available": self.available, "reason": "test"})()

    def public_status(self):
        return {"backend": self.backend, "available": False, "reason": "test"}

    def get(self, name):
        return ""

    def set(self, name, value):
        return False

    def delete(self, name):
        return True


class TestAuditAPIEndpoint:
    """Test GET /api/system/audit via Flask test client."""

    def _setup(self, tmp_path):
        from modules.app_api.services import audit_log

        audit_log.close()
        db_file = tmp_path / "api_audit_test.db"
        audit_log.init_audit_log(db_file)

        old_lib = server._library
        old_ss = server._secret_store
        lib = _FakeGML()
        lib.db_path = tmp_path / "fake_lib.db"
        server._library = lib
        server._secret_store = _FakeSecretStore()
        client = server.app.test_client()
        return client, old_lib, old_ss, audit_log

    def _teardown(self, old_lib, old_ss, audit_log):
        server._library = old_lib
        server._secret_store = old_ss
        audit_log.close()

    def test_system_audit_endpoint(self, tmp_path):
        client, old_lib, old_ss, al = self._setup(tmp_path)
        try:
            al.audit("delete", "custom_tag", "ct_99", actor="local:127.0.0.1")
            al.audit("config_change", "settings", "ai", actor="local:10.0.0.1")

            resp = client.get("/api/system/audit")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["count"] == 2
            assert data["total"] >= 2
            assert isinstance(data["entries"], list)
            assert isinstance(data["filters"], dict)
        finally:
            self._teardown(old_lib, old_ss, al)

    def test_system_audit_endpoint_filters(self, tmp_path):
        client, old_lib, old_ss, al = self._setup(tmp_path)
        try:
            al.audit("delete", "custom_tag", "ct_1", actor="local:127.0.0.1")
            al.audit("delete", "workflow", "wf_1", actor="agent:bot_1")
            al.audit("config_change", "settings", "ai", actor="local:10.0.0.1")

            # Filter by operation
            resp = client.get("/api/system/audit?operation=delete")
            data = resp.get_json()
            assert data["count"] == 2
            assert all(e["operation"] == "delete" for e in data["entries"])

            # Filter by resource_type
            resp = client.get("/api/system/audit?resource_type=settings")
            data = resp.get_json()
            assert data["count"] == 1
            assert data["entries"][0]["resource_type"] == "settings"
        finally:
            self._teardown(old_lib, old_ss, al)


# ── End-to-end: real sensitive route → audit entry ─────────────────────


class TestAuditE2ESettingsRoute:
    """Trigger a real POST /api/settings/ai and verify audit entry appears."""

    def test_settings_ai_change_produces_audit(self, tmp_path):
        from modules.app_api.services import audit_log

        audit_log.close()
        al_db = tmp_path / "e2e_audit.db"
        audit_log.init_audit_log(al_db)

        old_lib = server._library
        old_ss = server._secret_store
        try:
            lib = _FakeGML()
            lib.db_path = tmp_path / "fake.db"
            server._library = lib
            server._secret_store = _FakeSecretStore()
            client = server.app.test_client()

            # POST /api/settings/ai triggers _audit("config_change", "settings", "ai", ...)
            resp = client.post(
                "/api/settings/ai",
                json={"provider": "openai", "model": "gpt-4o"},
                content_type="application/json",
            )
            assert resp.status_code == 200

            # Now query audit log for the entry
            entries = audit_log.query(operation="config_change", resource_type="settings")
            assert len(entries) >= 1
            entry = entries[0]
            assert entry["resource_id"] == "ai"
            assert entry["status"] == "ok"
            assert isinstance(entry.get("detail"), dict)
            assert "keys_changed" in entry["detail"]
        finally:
            server._library = old_lib
            server._secret_store = old_ss
            audit_log.close()


class TestDegradationAudit:
    """R2: Verify _log_degradation writes structured degradation events."""

    def _fresh_module(self):
        from modules.app_api.services import audit_log
        audit_log.close()
        return audit_log

    def test_degradation_event_written(self, tmp_path):
        al = self._fresh_module()
        al.init_audit_log(tmp_path / "degrad.db")
        try:
            from modules.workflow_engine.workflow import _log_degradation
            _log_degradation("step2_topic", "未配置 AI API Key", "素材驱动选题")

            entries = al.query(operation="degradation")
            assert len(entries) == 1
            e = entries[0]
            assert e["resource_type"] == "step2_topic"
            assert e["status"] == "degraded"
            assert e["actor"] == "workflow_engine"
            assert e["detail"]["reason"] == "未配置 AI API Key"
            assert e["detail"]["fallback_path"] == "素材驱动选题"
            assert e["detail"]["severity"] == "warning"
        finally:
            al.close()

    def test_degradation_multiple_events(self, tmp_path):
        al = self._fresh_module()
        al.init_audit_log(tmp_path / "degrad2.db")
        try:
            from modules.workflow_engine.workflow import _log_degradation
            _log_degradation("step1_clip", "CLIP 不可用", "跳过语义索引")
            _log_degradation("step2_topic", "AI 解析失败", "素材驱动选题")
            _log_degradation("step3_script", "AI 返回解析失败", "模板脚本生成")

            entries = al.query(operation="degradation")
            assert len(entries) == 3
            modules = {e["resource_type"] for e in entries}
            assert modules == {"step1_clip", "step2_topic", "step3_script"}
        finally:
            al.close()

    def test_degradation_api_filter(self, tmp_path):
        """Verify GET /api/system/audit?operation=degradation returns degradation events."""
        al = self._fresh_module()
        al.init_audit_log(tmp_path / "degrad_api.db")

        old_lib = server._library
        old_ss = server._secret_store
        try:
            lib = _FakeGML()
            lib.db_path = tmp_path / "fake_d.db"
            server._library = lib
            server._secret_store = _FakeSecretStore()
            client = server.app.test_client()

            al.audit("degradation", "step2_topic", None,
                     actor="workflow_engine", status="degraded",
                     detail={"reason": "test", "fallback_path": "fallback", "severity": "warning"})

            resp = client.get("/api/system/audit?operation=degradation")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["count"] == 1
            assert data["entries"][0]["resource_type"] == "step2_topic"
            assert data["entries"][0]["status"] == "degraded"
        finally:
            server._library = old_lib
            server._secret_store = old_ss
            al.close()

    def test_degradation_no_crash_without_init(self):
        """_log_degradation must never raise, even if audit_log is not initialized."""
        al = self._fresh_module()
        # Do NOT call init — audit should silently do nothing
        from modules.workflow_engine.workflow import _log_degradation
        _log_degradation("test_module", "test reason", "test fallback")
        # No assertion — just verifying no exception raised


class TestAuditE2ECustomTagDelete:
    """Trigger DELETE /api/library/custom-tags/<id> and verify audit entry."""

    def test_custom_tag_delete_produces_audit(self, tmp_path):
        from modules.app_api.services import audit_log

        audit_log.close()
        audit_log.init_audit_log(tmp_path / "e2e_audit2.db")

        old_lib = server._library
        old_ss = server._secret_store
        try:
            lib = _FakeGML()
            lib.db_path = tmp_path / "fake2.db"
            # Add fake methods needed by the custom-tag routes
            lib.create_custom_tag = lambda data: {"ok": True, "tag": {"id": 99, "label": data.get("label", "")}}
            lib.archive_custom_tag = lambda ct_id: {"ok": True}
            server._library = lib
            server._secret_store = _FakeSecretStore()
            client = server.app.test_client()

            # Create then delete a custom tag
            resp = client.post(
                "/api/library/custom-tags",
                json={"label": "test_audit_tag"},
                content_type="application/json",
            )
            assert resp.status_code in (200, 201)

            resp = client.delete("/api/library/custom-tags/99")
            assert resp.status_code == 200

            # Verify audit entry
            entries = audit_log.query(operation="delete", resource_type="custom_tag")
            assert len(entries) >= 1
            assert entries[0]["resource_id"] == "99"
            assert entries[0]["status"] == "ok"
        finally:
            server._library = old_lib
            server._secret_store = old_ss
            audit_log.close()
