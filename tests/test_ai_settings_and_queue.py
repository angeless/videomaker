import sys
import time
import types
import sqlite3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


fake_library_mod = types.ModuleType("modules.library.global_media_library")


class _FakeGlobalMediaLibrary:
    def __init__(self, *args, **kwargs):
        self.db_path = ROOT / ".tmp_fake_library_ai_queue.db"

    def stats(self):
        return {}

    def ingest_local_path(self, source_path, max_videos=600, progress_callback=None, should_cancel=None):
        total = 8
        for i in range(total):
            if callable(should_cancel) and should_cancel():
                return {"cancelled": True}
            if callable(progress_callback):
                progress_callback(i + 1, total, f"{source_path}/clip_{i}.mp4")
            time.sleep(0.04)
        return {
            "cancelled": False,
            "scanned": total,
            "indexed": min(total, int(max_videos)),
            "dedup_hits": 0,
            "failed": 0,
            "total_candidates": total,
            "assets": [],
            "truncated": False,
        }


fake_library_mod.GlobalMediaLibrary = _FakeGlobalMediaLibrary
sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

from modules.app_api import server  # noqa: E402


class _FakeSecretStore:
    def __init__(self, available: bool = True):
        self.available = bool(available)
        self.backend = "fake_secret_store"
        self.values = {}

    def info(self):
        return type(
            "_Info",
            (),
            {
                "backend": self.backend,
                "available": self.available,
                "reason": "" if self.available else "disabled_for_test",
            },
        )()

    def public_status(self):
        meta = self.info()
        return {
            "backend": meta.backend,
            "available": bool(meta.available),
            "reason": str(meta.reason or ""),
        }

    def get(self, name: str) -> str:
        return str(self.values.get(str(name), "") or "")

    def set(self, name: str, value: str) -> bool:
        if not self.available:
            return False
        self.values[str(name)] = str(value or "")
        return True

    def delete(self, name: str) -> bool:
        self.values.pop(str(name), None)
        return True


def _wait_job_done(client, job_id: str, attempts: int = 160, sleep_s: float = 0.03):
    payload = None
    for _ in range(attempts):
        resp = client.get(f"/api/job/{job_id}")
        assert resp.status_code == 200
        payload = resp.get_json()
        if payload["status"] in {"done", "error", "cancelled"}:
            break
        time.sleep(sleep_s)
    assert payload is not None
    return payload


def test_ai_settings_catalog_and_provider_alias_roundtrip(tmp_path):
    old_library = server._library
    old_secret_store = server._secret_store
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_settings.db"
        server._library = lib
        server._secret_store = _FakeSecretStore(available=False)
        client = server.app.test_client()

        get_resp = client.get("/api/settings/ai")
        assert get_resp.status_code == 200
        get_payload = get_resp.get_json()
        assert get_payload["ok"] is True
        assert get_payload["catalog"]["default_embedding_model"] == "text-embedding-3-small"
        provider_ids = {item["provider_id"] for item in get_payload["catalog"]["providers"]}
        assert {"openai", "anthropic", "moonshot"}.issubset(provider_ids)

        post_resp = client.post(
            "/api/settings/ai",
            json={
                "provider": "kimi",
                "ai_model": "moonshot-v1-8k",
                "embedding_model": "",
                "ai_base_url": "",
            },
        )
        assert post_resp.status_code == 200
        post_payload = post_resp.get_json()
        assert post_payload["ok"] is True
        assert post_payload["provider"] == "moonshot"
        assert post_payload["recommended_base_url"].startswith("https://api.moonshot.cn/")
        assert post_payload["embedding_model"] == ""
        assert post_payload["embedding_model_resolved"] == "text-embedding-3-small"
    finally:
        server._library = old_library
        server._secret_store = old_secret_store


def test_ai_settings_persist_keys_in_secret_store_when_available(tmp_path):
    old_library = server._library
    old_secret_store = server._secret_store
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_ai_secrets.db"
        server._library = lib
        fake_secret = _FakeSecretStore(available=True)
        server._secret_store = fake_secret
        client = server.app.test_client()

        post_resp = client.post(
            "/api/settings/ai",
            json={
                "provider": "openai",
                "ai_model": "gpt-4o-mini",
                "openai_api_key": "sk-openai-test-key",
                "anthropic_api_key": "sk-anthropic-test-key",
            },
        )
        assert post_resp.status_code == 200
        post_payload = post_resp.get_json()
        assert post_payload["ok"] is True
        assert post_payload["openai_api_key_set"] is True
        assert post_payload["anthropic_api_key_set"] is True
        assert post_payload["secret_storage"]["backend"] == "fake_secret_store"
        assert post_payload["secret_storage"]["available"] is True

        settings_file = lib.db_path.parent / "app_settings.json"
        raw = json.loads(settings_file.read_text(encoding="utf-8"))
        ai_saved = raw.get("ai", {})
        assert ai_saved.get("openai_api_key_ref") == "ai.openai_api_key"
        assert ai_saved.get("anthropic_api_key_ref") == "ai.anthropic_api_key"
        assert "openai_api_key" not in ai_saved
        assert "anthropic_api_key" not in ai_saved
        assert fake_secret.values.get("ai.openai_api_key") == "sk-openai-test-key"
        assert fake_secret.values.get("ai.anthropic_api_key") == "sk-anthropic-test-key"

        get_resp = client.get("/api/settings/ai")
        assert get_resp.status_code == 200
        get_payload = get_resp.get_json()
        assert get_payload["openai_api_key_set"] is True
        assert get_payload["anthropic_api_key_set"] is True
    finally:
        server._library = old_library
        server._secret_store = old_secret_store


def test_ai_settings_clear_keys_removes_secret_refs_and_values(tmp_path):
    old_library = server._library
    old_secret_store = server._secret_store
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_ai_secrets_clear.db"
        server._library = lib
        fake_secret = _FakeSecretStore(available=True)
        server._secret_store = fake_secret
        client = server.app.test_client()

        save_resp = client.post(
            "/api/settings/ai",
            json={
                "provider": "openai",
                "openai_api_key": "sk-openai-clear-me",
                "anthropic_api_key": "sk-anthropic-clear-me",
            },
        )
        assert save_resp.status_code == 200
        assert fake_secret.values.get("ai.openai_api_key")
        assert fake_secret.values.get("ai.anthropic_api_key")

        clear_resp = client.post(
            "/api/settings/ai",
            json={
                "clear_openai_api_key": True,
                "clear_anthropic_api_key": True,
            },
        )
        assert clear_resp.status_code == 200
        clear_payload = clear_resp.get_json()
        assert clear_payload["openai_api_key_set"] is False
        assert clear_payload["anthropic_api_key_set"] is False
        assert fake_secret.values.get("ai.openai_api_key", "") == ""
        assert fake_secret.values.get("ai.anthropic_api_key", "") == ""

        settings_file = lib.db_path.parent / "app_settings.json"
        raw = json.loads(settings_file.read_text(encoding="utf-8"))
        ai_saved = raw.get("ai", {})
        assert "openai_api_key_ref" not in ai_saved
        assert "anthropic_api_key_ref" not in ai_saved
        assert "openai_api_key" not in ai_saved
        assert "anthropic_api_key" not in ai_saved
    finally:
        server._library = old_library
        server._secret_store = old_secret_store


def test_ui_settings_roundtrip_and_bounds(tmp_path):
    old_library = server._library
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_ui_settings.db"
        server._library = lib
        client = server.app.test_client()

        get_resp = client.get("/api/settings/ui")
        assert get_resp.status_code == 200
        payload = get_resp.get_json()
        assert payload["ok"] is True
        assert payload["preferred_production_view"] in {"hub", "workflow"}
        assert 0.85 <= float(payload["font_scale"]) <= 1.45

        save_resp = client.post(
            "/api/settings/ui",
            json={
                "onboarding_completed": True,
                "creator_mode": False,
                "font_scale": 9.9,
                "preferred_production_view": "workflow",
                "default_videos_dir": "/tmp/videos",
                "default_project_dir": "/tmp/projects",
                "auto_open_last_project": False,
            },
        )
        assert save_resp.status_code == 200
        saved = save_resp.get_json()
        assert saved["ok"] is True
        assert saved["onboarding_completed"] is True
        assert saved["creator_mode"] is False
        assert saved["preferred_production_view"] == "workflow"
        assert saved["default_videos_dir"] == "/tmp/videos"
        assert saved["default_project_dir"] == "/tmp/projects"
        assert saved["auto_open_last_project"] is False
        # enforced max bound
        assert float(saved["font_scale"]) == 1.45
    finally:
        server._library = old_library


def test_local_api_token_guard_and_bootstrap(tmp_path):
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    old_token = server._LOCAL_API_TOKEN
    old_csrf = server._LOCAL_CSRF_TOKEN
    old_require_csrf = server._REQUIRE_CSRF_PROTECTION
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_local_token.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = True
        server._LOCAL_API_TOKEN = "token_for_test_only"
        server._LOCAL_CSRF_TOKEN = "csrf_for_test_only"
        server._REQUIRE_CSRF_PROTECTION = True
        client = server.app.test_client()

        denied = client.get("/api/status")
        assert denied.status_code == 401
        denied_payload = denied.get_json()
        assert denied_payload["code"] == "local_auth_required"

        bootstrap = client.get("/api/session/bootstrap")
        assert bootstrap.status_code == 200
        boot_payload = bootstrap.get_json()
        assert boot_payload["ok"] is True
        assert boot_payload["auth_required"] is True
        assert boot_payload["csrf_required"] is True
        assert boot_payload["token"] == "token_for_test_only"
        assert boot_payload["csrf_token"] == "csrf_for_test_only"

        ok = client.get("/api/status", headers={"X-VideoEditor-Token": "token_for_test_only"})
        assert ok.status_code == 200

        missing_csrf = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.0},
            headers={"X-VideoEditor-Token": "token_for_test_only"},
        )
        assert missing_csrf.status_code == 403
        assert missing_csrf.get_json()["code"] == "csrf_required"

        bad_origin = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.0},
            headers={
                "X-VideoEditor-Token": "token_for_test_only",
                "X-VideoEditor-CSRF": "csrf_for_test_only",
                "Origin": "https://evil.example.com",
            },
        )
        assert bad_origin.status_code == 403
        assert bad_origin.get_json()["code"] == "origin_forbidden"

        ok_post = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.02},
            headers={
                "X-VideoEditor-Token": "token_for_test_only",
                "X-VideoEditor-CSRF": "csrf_for_test_only",
                "Origin": "http://127.0.0.1:9527",
            },
        )
        assert ok_post.status_code == 200
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require
        server._LOCAL_API_TOKEN = old_token
        server._LOCAL_CSRF_TOKEN = old_csrf
        server._REQUIRE_CSRF_PROTECTION = old_require_csrf


def test_publish_settings_mask_secret_fields(tmp_path):
    old_library = server._library
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_publish_settings.db"
        server._library = lib
        client = server.app.test_client()

        save = client.post(
            "/api/settings/publish",
            json={
                "connectors": {
                    "youtube": {
                        "kind": "webhook",
                        "endpoint": "https://example.com/hook",
                        "token": "secret_token_123456",
                        "headers": {"Authorization": "Bearer abcdefghijklmnop"},
                    }
                }
            },
        )
        assert save.status_code == 200
        save_payload = save.get_json()
        assert save_payload["ok"] is True
        assert save_payload["connector_count"] == 1
        masked = save_payload["connectors"]["youtube"]
        assert masked["token"] != "secret_token_123456"
        assert "*" in masked["token"]
        assert "*" in masked["headers"]["Authorization"]

        get_resp = client.get("/api/settings/publish")
        assert get_resp.status_code == 200
        get_payload = get_resp.get_json()
        assert get_payload["ok"] is True
        assert get_payload["connector_count"] == 1
    finally:
        server._library = old_library


def test_publish_settings_keep_secret_sentinel_preserves_token(tmp_path):
    old_library = server._library
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_publish_settings_keep.db"
        server._library = lib
        client = server.app.test_client()

        initial = client.post(
            "/api/settings/publish",
            json={
                "connectors": {
                    "youtube": {
                        "kind": "webhook",
                        "endpoint": "https://example.com/hook-a",
                        "token": "secret_token_keep_me",
                    }
                }
            },
        )
        assert initial.status_code == 200

        keep = client.post(
            "/api/settings/publish",
            json={
                "connectors": {
                    "youtube": {
                        "kind": "webhook",
                        "endpoint": "https://example.com/hook-b",
                        "token": "__KEEP__",
                    }
                }
            },
        )
        assert keep.status_code == 200
        payload = keep.get_json()
        assert payload["ok"] is True

        settings_file = lib.db_path.parent / "app_settings.json"
        raw = json.loads(settings_file.read_text(encoding="utf-8"))
        connectors = raw.get("publish", {}).get("connectors", {})
        youtube = connectors.get("youtube", {})
        assert youtube.get("endpoint") == "https://example.com/hook-b"
        assert youtube.get("token") == "secret_token_keep_me"
    finally:
        server._library = old_library


def test_heavy_jobs_enter_queue_and_support_cancel_queued(tmp_path):
    old_library = server._library
    old_project_dir = server._project_dir
    with server._heavy_queue_lock:
        server._jobs.clear()
        server._heavy_job_queue.clear()
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_queue.db"
        server._library = lib
        server._project_dir = None
        client = server.app.test_client()

        src = tmp_path / "videos"
        src.mkdir(parents=True, exist_ok=True)

        r1 = client.post("/api/library/ingest/local", json={"path": str(src), "max_videos": 100})
        assert r1.status_code == 200
        j1 = r1.get_json()["job_id"]

        r2 = client.post("/api/library/ingest/local", json={"path": str(src), "max_videos": 100})
        assert r2.status_code == 200
        j2 = r2.get_json()["job_id"]

        q = client.get("/api/tasks/queue")
        assert q.status_code == 200
        q_payload = q.get_json()["task_queue"]
        queued_ids = {item["job_id"] for item in q_payload.get("queued", [])}
        assert j2 in queued_ids
        assert q_payload["queued_count"] >= 1

        j2_snapshot = client.get(f"/api/job/{j2}")
        assert j2_snapshot.status_code == 200
        j2_eta = j2_snapshot.get_json().get("eta", {})
        assert isinstance(j2_eta, dict)
        assert "source" in j2_eta

        cancel = client.post(f"/api/job/{j2}/cancel")
        assert cancel.status_code == 200
        cancel_payload = cancel.get_json()
        assert cancel_payload["ok"] is True
        assert cancel_payload["cancel_requested"] is True

        j2_state = client.get(f"/api/job/{j2}")
        assert j2_state.status_code == 200
        assert j2_state.get_json()["status"] == "cancelled"

        j1_final = _wait_job_done(client, j1)
        assert j1_final["status"] == "done"
        assert isinstance(j1_final.get("eta"), dict)
    finally:
        server._library = old_library
        server._project_dir = old_project_dir


def test_jobs_persisted_and_restored_from_sqlite(tmp_path):
    old_library = server._library
    old_project_dir = server._project_dir
    with server._heavy_queue_lock:
        server._jobs.clear()
        server._heavy_job_queue.clear()
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_jobs_restore.db"
        server._library = lib
        server._project_dir = None
        server._reset_job_store_for_tests()
        client = server.app.test_client()

        src = tmp_path / "videos_restore"
        src.mkdir(parents=True, exist_ok=True)

        submit = client.post("/api/library/ingest/local", json={"path": str(src), "max_videos": 50})
        assert submit.status_code == 200
        job_id = submit.get_json()["job_id"]

        final_payload = _wait_job_done(client, job_id)
        assert final_payload["status"] == "done"

        state_db = tmp_path / "app_state.db"
        assert state_db.exists()
        with sqlite3.connect(str(state_db)) as conn:
            row = conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            assert row is not None
            assert str(row[0]) == "done"

        with server._heavy_queue_lock:
            server._jobs.clear()
            server._heavy_job_queue.clear()
        server._restore_jobs_from_store()

        restored = client.get(f"/api/job/{job_id}")
        assert restored.status_code == 200
        restored_payload = restored.get_json()
        assert restored_payload["status"] == "done"
    finally:
        server._library = old_library
        server._project_dir = old_project_dir
        server._reset_job_store_for_tests()


def test_job_store_uses_schema_migrations(tmp_path):
    old_library = server._library
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_jobs_migration.db"
        server._library = lib
        server._reset_job_store_for_tests()
        _ = server._ensure_job_store()

        state_db = tmp_path / "app_state.db"
        assert state_db.exists()
        with sqlite3.connect(str(state_db)) as conn:
            table_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            assert table_row is not None
            version_row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            assert version_row is not None
            assert int(version_row[0] or 0) >= 1
    finally:
        server._library = old_library
        server._reset_job_store_for_tests()
