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

    def search_assets(self, query="", limit=120, offset=0, retrieval_mode="hybrid", media_type="all"):
        return [{"uid": "fake_001", "filename": "clip.mp4", "score": 0.9}][:limit]

    def count_matching_assets(self, query="", retrieval_mode="hybrid", media_type="all"):
        return 1

    def get_assets(self, uids):
        return [{"uid": u, "filename": f"{u}.mp4"} for u in uids]

    def discover_videos(self, root):
        return []

    def discover_images(self, root):
        return []

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
    old_max_running = server._HEAVY_QUEUE_MAX_RUNNING
    server._set_heavy_queue_max_running(1)
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
        server._set_heavy_queue_max_running(old_max_running)


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
        conn = sqlite3.connect(str(state_db))
        try:
            row = conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            assert row is not None
            assert str(row[0]) == "done"
        finally:
            conn.close()

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
        conn = sqlite3.connect(str(state_db))
        try:
            table_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            assert table_row is not None
            version_row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            assert version_row is not None
            assert int(version_row[0] or 0) >= 1
        finally:
            conn.close()
    finally:
        server._library = old_library
        server._reset_job_store_for_tests()


# ---------------------------------------------------------------------------
# S1-S3: Security guard edge-case tests (v0.3.2)
# ---------------------------------------------------------------------------


def test_security_s1_forged_csrf_token_rejected(tmp_path):
    """S1: A POST with a wrong/forged CSRF token must be rejected with 403."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    old_token = server._LOCAL_API_TOKEN
    old_csrf = server._LOCAL_CSRF_TOKEN
    old_require_csrf = server._REQUIRE_CSRF_PROTECTION
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_s1_csrf.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = True
        server._LOCAL_API_TOKEN = "s1_token"
        server._LOCAL_CSRF_TOKEN = "s1_real_csrf"
        server._REQUIRE_CSRF_PROTECTION = True
        client = server.app.test_client()

        # Forged CSRF token — must be 403
        forged = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.0},
            headers={
                "X-VideoEditor-Token": "s1_token",
                "X-VideoEditor-CSRF": "forged_csrf_value",
                "Origin": "http://127.0.0.1:9527",
            },
        )
        assert forged.status_code == 403
        assert forged.get_json()["code"] == "csrf_required"

        # Empty CSRF token — must also be 403
        empty_csrf = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.0},
            headers={
                "X-VideoEditor-Token": "s1_token",
                "X-VideoEditor-CSRF": "",
                "Origin": "http://127.0.0.1:9527",
            },
        )
        assert empty_csrf.status_code == 403
        assert empty_csrf.get_json()["code"] == "csrf_required"

        # Correct CSRF token — must succeed
        ok = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.01},
            headers={
                "X-VideoEditor-Token": "s1_token",
                "X-VideoEditor-CSRF": "s1_real_csrf",
                "Origin": "http://127.0.0.1:9527",
            },
        )
        assert ok.status_code == 200
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require
        server._LOCAL_API_TOKEN = old_token
        server._LOCAL_CSRF_TOKEN = old_csrf
        server._REQUIRE_CSRF_PROTECTION = old_require_csrf


def test_security_s2_nonexistent_job_id_returns_404(tmp_path):
    """S2: GET/POST to /api/job/<invalid_id> must return 404."""
    old_library = server._library
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_s2_job.db"
        server._library = lib
        client = server.app.test_client()

        # Non-existent job — GET must return 404
        resp = client.get("/api/job/nonexistent_job_id_12345")
        assert resp.status_code == 404
        assert "不存在" in resp.get_json().get("error", "")

        # Non-existent job — cancel must return 404
        cancel = client.post("/api/job/nonexistent_job_id_12345/cancel")
        assert cancel.status_code == 404
        assert "不存在" in cancel.get_json().get("error", "")
    finally:
        server._library = old_library


def test_security_s3_post_without_token_rejected(tmp_path):
    """S3: POST without X-VideoEditor-Token must be rejected when token is required."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    old_token = server._LOCAL_API_TOKEN
    old_csrf = server._LOCAL_CSRF_TOKEN
    old_require_csrf = server._REQUIRE_CSRF_PROTECTION
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_s3_token.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = True
        server._LOCAL_API_TOKEN = "s3_real_token"
        server._LOCAL_CSRF_TOKEN = "s3_csrf"
        server._REQUIRE_CSRF_PROTECTION = True
        client = server.app.test_client()

        # POST with valid CSRF but NO API token — must be 401
        no_token = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.0},
            headers={
                "X-VideoEditor-CSRF": "s3_csrf",
                "Origin": "http://127.0.0.1:9527",
            },
        )
        assert no_token.status_code == 401
        assert no_token.get_json()["code"] == "local_auth_required"

        # POST with wrong API token — must be 401
        wrong_token = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.0},
            headers={
                "X-VideoEditor-Token": "wrong_token_value",
                "X-VideoEditor-CSRF": "s3_csrf",
                "Origin": "http://127.0.0.1:9527",
            },
        )
        assert wrong_token.status_code == 401
        assert wrong_token.get_json()["code"] == "local_auth_required"

        # GET without API token — must be 401
        no_token_get = client.get("/api/status")
        assert no_token_get.status_code == 401

        # POST with correct token + CSRF — must succeed
        ok = client.post(
            "/api/settings/ui",
            json={"font_scale": 1.05},
            headers={
                "X-VideoEditor-Token": "s3_real_token",
                "X-VideoEditor-CSRF": "s3_csrf",
                "Origin": "http://127.0.0.1:9527",
            },
        )
        assert ok.status_code == 200
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require
        server._LOCAL_API_TOKEN = old_token
        server._LOCAL_CSRF_TOKEN = old_csrf
        server._REQUIRE_CSRF_PROTECTION = old_require_csrf


# ---------------------------------------------------------------------------
# v0.3.3 — Input validation bounds checks
# ---------------------------------------------------------------------------


def test_v033_idempotency_limit_offset_bounds(tmp_path):
    """v0.3.3: Verify limit/offset bounds clamping on idempotency cache GET."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_bounds.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        # negative limit should be clamped to 1 (not crash)
        resp = client.get("/api/capabilities/idempotency/cache?limit=-5&offset=-10")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True

        # absurdly large limit should be clamped to 1000 (not crash)
        resp2 = client.get("/api/capabilities/idempotency/cache?limit=99999")
        assert resp2.status_code == 200

        # non-numeric limit should fallback to default 200
        resp3 = client.get("/api/capabilities/idempotency/cache?limit=abc")
        assert resp3.status_code == 200
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v033_social_export_quality_enum_fallback(tmp_path):
    """v0.3.3: Invalid quality value falls back to 'high' without error."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_quality.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        # social_export/plan requires input_video; test validation fires
        # before quality matters, but the quality param should be sanitized
        resp = client.post(
            "/api/capabilities/social_export/plan",
            json={
                "input_mode": "inline",
                "quality": "INVALID_VALUE",
                "input_video": "/nonexistent/video.mp4",
            },
        )
        # Will fail because file doesn't exist, not because quality is invalid
        assert resp.status_code in {400, 404}
        payload = resp.get_json()
        assert "quality" not in str(payload.get("error", "")).lower()
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v033_system_get_endpoints(tmp_path):
    """v0.3.3: Basic GET endpoints (/api/status, /api/system/load, /api/tasks/queue) respond 200."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_system.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        # /api/status
        resp = client.get("/api/status")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert isinstance(payload, dict)

        # /api/system/load
        resp2 = client.get("/api/system/load")
        assert resp2.status_code == 200
        payload2 = resp2.get_json()
        assert payload2["ok"] is True
        assert "system" in payload2
        assert "task_queue" in payload2

        # /api/tasks/queue
        resp3 = client.get("/api/tasks/queue")
        assert resp3.status_code == 200
        payload3 = resp3.get_json()
        assert payload3["ok"] is True
        assert "task_queue" in payload3
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v033_library_stats_endpoint(tmp_path):
    """v0.3.3: GET /api/library/stats returns 200."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_libstats.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        resp = client.get("/api/library/stats")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert isinstance(payload, dict)
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v033_workflows_catalog_endpoint(tmp_path):
    """v0.3.3: GET /api/workflows/catalog returns 200 with catalog list."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_catalog.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        resp = client.get("/api/workflows/catalog")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert "catalog" in payload
        assert isinstance(payload["catalog"], list)
        assert "count" in payload
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


# ---------------------------------------------------------------------------
# v0.3.5 — JSON error handlers for 404/405
# ---------------------------------------------------------------------------


def test_v035_unknown_route_returns_json_404(tmp_path):
    """v0.3.5: Unknown route returns JSON 404 instead of HTML."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_404.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        resp = client.get("/api/this_route_does_not_exist")
        assert resp.status_code == 404
        payload = resp.get_json()
        assert payload is not None, "Expected JSON response, got HTML"
        assert payload["code"] == "not_found"
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v035_wrong_method_returns_json_405(tmp_path):
    """v0.3.5: Wrong HTTP method returns JSON 405 instead of HTML."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_405.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        # /api/status only accepts GET; sending DELETE should be 405
        resp = client.delete("/api/status")
        assert resp.status_code == 405
        payload = resp.get_json()
        assert payload is not None, "Expected JSON response, got HTML"
        assert payload["code"] == "method_not_allowed"
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


# ============================================================
# v0.3.10 — parse_int_param / parse_float_param 工具函数测试
# ============================================================


def test_v0310_parse_int_param():
    from modules.app_api.param_utils import parse_int_param

    # 正常值
    assert parse_int_param("42", default=10, min_val=1, max_val=100) == 42
    # None → default
    assert parse_int_param(None, default=10, min_val=1, max_val=100) == 10
    # 空字符串 → default
    assert parse_int_param("", default=10, min_val=1, max_val=100) == 10
    # 非数字 → default
    assert parse_int_param("abc", default=10, min_val=1, max_val=100) == 10
    # 低于下限 → min_val
    assert parse_int_param("-5", default=10, min_val=1, max_val=100) == 1
    # 超过上限 → max_val
    assert parse_int_param("999", default=10, min_val=1, max_val=100) == 100
    # float 字符串 → 转换失败回退 default
    assert parse_int_param("3.14", default=10, min_val=1, max_val=100) == 10
    # int 类型直接传入
    assert parse_int_param(50, default=10, min_val=1, max_val=100) == 50


def test_v0310_parse_float_param():
    from modules.app_api.param_utils import parse_float_param

    assert parse_float_param("3.14", default=1.0, min_val=0.0, max_val=10.0) == 3.14
    assert parse_float_param(None, default=1.0, min_val=0.0, max_val=10.0) == 1.0
    assert parse_float_param("abc", default=1.0, min_val=0.0, max_val=10.0) == 1.0
    assert parse_float_param("-5.0", default=1.0, min_val=0.0, max_val=10.0) == 0.0
    assert parse_float_param("99.9", default=1.0, min_val=0.0, max_val=10.0) == 10.0
    assert parse_float_param(2.5, default=1.0, min_val=0.0, max_val=10.0) == 2.5


# ============================================================
# v0.3.10 — POST 端点测试（编辑类能力缺失项目时返回 400）
# ============================================================


def test_v0310_editing_post_endpoints_require_project():
    """POST editing endpoints should return 400 when project not loaded."""
    old_library = server._library
    old_project = server._project_dir
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = ROOT / ".tmp_v0310_editing.db"
        server._library = lib
        server._project_dir = None  # 确保无项目加载
        server._REQUIRE_LOCAL_API_TOKEN = False
        server._reset_job_store_for_tests()

        client = server.app.test_client()

        # Endpoints that strictly require project mode
        strict_project_endpoints = [
            "/api/capabilities/topic_copy/draft",
            "/api/capabilities/text_rough_cut/plan",
            "/api/capabilities/short_clip/plan",
            "/api/capabilities/refinement/handoff",
            "/api/capabilities/refinement/execute",
        ]
        for ep in strict_project_endpoints:
            resp = client.post(ep, json={"input_mode": "project"})
            assert resp.status_code == 400, f"{ep} should return 400 without project, got {resp.status_code}"

        # text_rough_cut/source is GET
        resp_get = client.get("/api/capabilities/text_rough_cut/source?input_mode=project")
        assert resp_get.status_code == 400, f"text_rough_cut/source should return 400 without project"

        # refinement/plan auto-degrades to inline mode (returns 200)
        resp_plan = client.post("/api/capabilities/refinement/plan", json={"input_mode": "project"})
        assert resp_plan.status_code == 200, "refinement/plan should auto-degrade to inline mode"
    finally:
        server._library = old_library
        server._project_dir = old_project
        server._REQUIRE_LOCAL_API_TOKEN = old_require
        server._reset_job_store_for_tests()


def test_v0310_topic_library_list_inline_returns_200():
    """GET topic_library with input_mode=inline should return 200."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = ROOT / ".tmp_v0310_topic.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        server._reset_job_store_for_tests()

        client = server.app.test_client()
        resp = client.get("/api/capabilities/topic_library?input_mode=inline")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)

        # Without project, project mode should return 400
        resp_proj = client.get("/api/capabilities/topic_library?input_mode=project")
        assert resp_proj.status_code == 400
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require
        server._reset_job_store_for_tests()


# ---------------------------------------------------------------------------
# v0.3.12 — library search / assets / preview endpoint tests
# ---------------------------------------------------------------------------


def test_v0312_library_search_default_params(tmp_path):
    """GET /api/library/search with no params returns 200 and browse mode."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_search.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        resp = client.get("/api/library/search")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["retrieval_mode"] == "browse"
        assert data["limit"] >= 1
        assert data["offset"] == 0
        assert isinstance(data["results"], list)
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v0312_library_search_with_query_and_bounds(tmp_path):
    """GET /api/library/search validates limit/offset bounds."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_search2.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        # Invalid limit → falls back to default
        resp = client.get("/api/library/search?q=test&limit=abc&offset=-5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["limit"] == 150  # default when query present
        assert data["offset"] == 0  # clamped to min_val=0
        assert data["retrieval_mode"] == "hybrid"

        # Oversized limit → clamped to 500
        resp2 = client.get("/api/library/search?limit=9999")
        assert resp2.status_code == 200
        assert resp2.get_json()["limit"] == 500
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v0312_library_assets_post(tmp_path):
    """POST /api/library/assets returns asset details for given UIDs."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_assets.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        resp = client.post("/api/library/assets", json={"uids": ["a1", "b2"]})
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["assets"], list)
        assert len(data["assets"]) == 2
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v0312_library_preview_local_missing_path(tmp_path):
    """POST /api/library/preview/local without path returns 400."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_preview.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        resp = client.post("/api/library/preview/local", json={})
        assert resp.status_code == 400
        assert "path" in resp.get_json().get("error", "").lower() or "空" in resp.get_json().get("error", "")
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


def test_v0312_library_preview_local_invalid_max_results(tmp_path):
    """POST /api/library/preview/local with invalid max_results uses default."""
    old_library = server._library
    old_require = server._REQUIRE_LOCAL_API_TOKEN
    try:
        lib = _FakeGlobalMediaLibrary()
        lib.db_path = tmp_path / "test_preview2.db"
        server._library = lib
        server._REQUIRE_LOCAL_API_TOKEN = False
        client = server.app.test_client()

        resp = client.post(
            "/api/library/preview/local",
            json={"path": str(tmp_path), "max_results": "not_a_number"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["preview"]["max_results"] == 30  # default
    finally:
        server._library = old_library
        server._REQUIRE_LOCAL_API_TOKEN = old_require


# ── v0.3.14 tests ─────────────────────────────────────────────────────
def test_v0314_parse_str_param():
    """parse_str_param handles falsy, None, whitespace, and default."""
    from modules.app_api.param_utils import parse_str_param

    assert parse_str_param("  hello  ") == "hello"
    assert parse_str_param(None) == ""
    assert parse_str_param(None, default="fallback") == "fallback"
    assert parse_str_param("", default="x") == "x"
    assert parse_str_param(0, default="zero") == "zero"
    assert parse_str_param("  video_post  ", default="video_post") == "video_post"
    assert parse_str_param(False, default="no") == "no"
    assert parse_str_param(42) == "42"
    # chaining .lower() still works
    assert parse_str_param("  TEXT_ONLY  ").lower() == "text_only"


def test_v0314_write_json_result(tmp_path):
    """write_json_result writes pretty JSON and returns True; None returns False."""
    from modules.app_api.param_utils import write_json_result

    p = tmp_path / "out.json"
    data = {"key": "值", "num": 42}
    assert write_json_result(p, data) is True
    assert p.exists()
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded == data
    # check pretty print (indent=2)
    raw = p.read_text(encoding="utf-8")
    assert "  " in raw

    # None path returns False
    assert write_json_result(None, data) is False


def test_v0314_library_routes_use_logging():
    """library_routes.py uses logging.getLogger, not print()."""
    import ast
    src = (ROOT / "modules" / "app_api" / "routes" / "library_routes.py").read_text()
    tree = ast.parse(src)
    # ensure no bare print calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                raise AssertionError(f"Found bare print() at line {node.lineno}")
    # ensure logging import exists
    assert "import logging" in src
    assert 'logging.getLogger(__name__)' in src


def test_v0314_content_publish_no_direct_json_import():
    """content_publish_routes uses write_json_result, no direct json import."""
    src = (ROOT / "modules" / "app_api" / "routes" / "capability_content_publish_routes.py").read_text()
    assert "write_json_result" in src
    assert "parse_str_param" in src
    # json module should NOT be imported (all writes go through write_json_result)
    lines = [l.strip() for l in src.splitlines()]
    assert "import json" not in lines


def test_v0314_audio_voice_no_direct_json_import():
    """audio_voice_routes uses write_json_result, no direct json import."""
    src = (ROOT / "modules" / "app_api" / "routes" / "capability_audio_voice_routes.py").read_text()
    assert "write_json_result" in src
    lines = [l.strip() for l in src.splitlines()]
    assert "import json" not in lines


# ── v0.3.15 tests ─────────────────────────────────────────────────────


def test_v0315_editing_routes_no_direct_json_import():
    """editing_routes uses write_json_result, no direct json import."""
    src = (ROOT / "modules" / "app_api" / "routes" / "capability_editing_routes.py").read_text()
    assert "write_json_result" in src
    lines = [l.strip() for l in src.splitlines()]
    assert "import json" not in lines
    # verify 7 write_json_result calls exist
    assert src.count("write_json_result(") >= 7


def test_v0315_social_export_routes_no_direct_json_import():
    """social_export_routes uses write_json_result, no direct json import."""
    src = (ROOT / "modules" / "app_api" / "routes" / "capability_social_export_routes.py").read_text()
    assert "write_json_result" in src
    lines = [l.strip() for l in src.splitlines()]
    assert "import json" not in lines
    assert src.count("write_json_result(") >= 2


def test_v0315_observability_routes_no_direct_json_import():
    """observability uses write_json_result + parse_str_param, no direct json."""
    src = (ROOT / "modules" / "app_api" / "routes" / "agent_observability_routes.py").read_text()
    assert "write_json_result" in src
    assert "parse_str_param" in src
    lines = [l.strip() for l in src.splitlines()]
    assert "import json" not in lines


def test_v0315_task_query_routes_no_direct_json_import():
    """task_query uses write_json_result + parse_str_param, no direct json."""
    src = (ROOT / "modules" / "app_api" / "routes" / "agent_task_query_routes.py").read_text()
    assert "write_json_result" in src
    assert "parse_str_param" in src
    lines = [l.strip() for l in src.splitlines()]
    assert "import json" not in lines


def test_v0315_legacy_routes_write_json_result():
    """legacy_project_routes uses write_json_result (json still needed for reads)."""
    src = (ROOT / "modules" / "app_api" / "routes" / "legacy_project_routes.py").read_text()
    assert "write_json_result" in src
    assert src.count("write_json_result(") >= 2
    # json import still needed for json.loads
    assert "json.loads" in src


def test_v0315_no_remaining_json_dumps_in_routes():
    """All route files in the write_json_result migration have no stale json.dumps."""
    migrated_files = [
        "capability_editing_routes.py",
        "capability_social_export_routes.py",
        "capability_text_semantic_routes.py",
        "capability_content_publish_routes.py",
        "capability_audio_voice_routes.py",
        "agent_observability_routes.py",
        "agent_task_query_routes.py",
    ]
    routes_dir = ROOT / "modules" / "app_api" / "routes"
    for fname in migrated_files:
        src = (routes_dir / fname).read_text()
        assert "json.dumps(" not in src, f"{fname} still contains json.dumps()"


# ── v0.3.16 tests ────────────────────────────────────────────────────


def test_v0316_parse_str_param_imported_in_all_route_files():
    """Every route file that has str(...or '').strip() patterns must import parse_str_param."""
    files_with_parse_str_param = [
        "capability_editing_routes.py",
        "capability_audio_voice_routes.py",
        "capability_text_semantic_routes.py",
        "capability_social_export_routes.py",
        "agent_observability_routes.py",
        "agent_task_query_routes.py",
        "agent_task_run_routes.py",
        "agent_template_routes.py",
        "agent_skill_routes.py",
        "settings_routes.py",
        "legacy_project_routes.py",
        "workflow_routes.py",
        "job_routes.py",
    ]
    routes_dir = ROOT / "modules" / "app_api" / "routes"
    for fname in files_with_parse_str_param:
        src = (routes_dir / fname).read_text()
        assert "parse_str_param" in src, f"{fname} missing parse_str_param import"


def test_v0316_no_simple_str_strip_patterns_in_migrated_files():
    """Simple str(payload.get(key, '') or '').strip() patterns are fully replaced.

    Only remaining patterns should be multi-dict fallback chains
    (e.g. str(payload.get(x) or ai.get(y) or '').strip()).
    """
    import re

    # These files should have zero simple str-strip patterns
    fully_migrated = [
        "capability_audio_voice_routes.py",
        "capability_social_export_routes.py",
        "agent_observability_routes.py",
        "agent_template_routes.py",
        "agent_skill_routes.py",
        "settings_routes.py",
        "legacy_project_routes.py",
        "workflow_routes.py",
        "job_routes.py",
    ]
    # Simple pattern: str(x.get("key", "") or "").strip() without multi-dict fallback
    simple_pattern = re.compile(
        r'str\(\w+\.get\("[^"]+",\s*"[^"]*"\)\s+or\s+""\)\.strip\(\)'
    )
    routes_dir = ROOT / "modules" / "app_api" / "routes"
    for fname in fully_migrated:
        src = (routes_dir / fname).read_text()
        matches = simple_pattern.findall(src)
        assert not matches, f"{fname} still has simple str-strip patterns: {matches[:3]}"


def test_v0316_remaining_str_strip_are_multi_dict_only():
    """Remaining str-strip patterns in partially migrated files are all multi-dict fallback chains."""
    import re

    partially_migrated = {
        "capability_text_semantic_routes.py": 20,
        "capability_editing_routes.py": 2,
        "agent_task_run_routes.py": 2,
    }
    pattern = re.compile(r'str\(.*or ""\)\.strip\(\)')
    routes_dir = ROOT / "modules" / "app_api" / "routes"
    for fname, expected_count in partially_migrated.items():
        src = (routes_dir / fname).read_text()
        matches = pattern.findall(src)
        assert len(matches) <= expected_count, (
            f"{fname}: expected ≤{expected_count} remaining str-strip patterns, got {len(matches)}"
        )


def test_v0316_parse_str_param_usage_count():
    """Verify parse_str_param is used broadly (at least 90 occurrences total)."""
    routes_dir = ROOT / "modules" / "app_api" / "routes"
    total = 0
    for py_file in routes_dir.glob("*.py"):
        src = py_file.read_text()
        total += src.count("parse_str_param(")
    assert total >= 90, f"Expected ≥90 parse_str_param() calls, got {total}"


# ── v0.3.17 tests ────────────────────────────────────────────────


def test_v0317_no_print_in_api_layer():
    """server.py and route files must not use print() for logging."""
    import ast
    # server.py
    server_src = (ROOT / "modules" / "app_api" / "server.py").read_text()
    tree = ast.parse(server_src)
    prints = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]
    assert len(prints) == 0, f"server.py still has {len(prints)} print() calls"
    # route files
    routes_dir = ROOT / "modules" / "app_api" / "routes"
    for py_file in routes_dir.glob("*.py"):
        src = py_file.read_text()
        tree = ast.parse(src)
        prints = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ]
        assert len(prints) == 0, f"{py_file.name} still has {len(prints)} print() calls"


def test_v0317_no_print_in_render_modules():
    """Render pipeline modules must use logging, not print()."""
    import ast
    render_files = [
        "modules/step7_final_render/beauty.py",
        "modules/step7_final_render/pipeline.py",
        "modules/step7_final_render/auto_render.py",
    ]
    for rel in render_files:
        src = (ROOT / rel).read_text()
        tree = ast.parse(src)
        prints = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ]
        fname = Path(rel).name
        assert len(prints) == 0, f"{fname} still has {len(prints)} print() calls"


def test_v0317_no_traceback_print_exc_in_api():
    """API layer must use logger.exception(), not traceback.print_exc()."""
    api_files = [
        "modules/app_api/server.py",
        "modules/app_api/services/job_runtime.py",
    ]
    for rel in api_files:
        src = (ROOT / rel).read_text()
        assert "traceback.print_exc()" not in src, (
            f"{Path(rel).name} still uses traceback.print_exc()"
        )


# ── v0.3.18 tests ────────────────────────────────────────────────


def test_v0318_zero_print_in_all_production_modules():
    """All production modules must use logging, not print(). Excludes legacy_lab."""
    import ast as _ast

    prod_root = ROOT / "modules"
    skip_dirs = {"legacy_lab", "__pycache__"}
    violations = []
    for py_file in prod_root.rglob("*.py"):
        if any(s in py_file.parts for s in skip_dirs):
            continue
        try:
            tree = _ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        # Collect print() calls, but skip those inside `if __name__ == "__main__"` blocks
        main_guard_lines = set()
        for node in _ast.walk(tree):
            if (isinstance(node, _ast.If)
                and isinstance(node.test, _ast.Compare)
                and isinstance(node.test.left, _ast.Name)
                and node.test.left.id == "__name__"):
                for child in _ast.walk(node):
                    if hasattr(child, 'lineno'):
                        main_guard_lines.add(child.lineno)
        prints = [
            node for node in _ast.walk(tree)
            if isinstance(node, _ast.Call)
            and isinstance(node.func, _ast.Name)
            and node.func.id == "print"
            and node.lineno not in main_guard_lines
        ]
        if prints:
            violations.append(f"{py_file.relative_to(ROOT)}:{len(prints)}")
    assert not violations, f"print() found in: {violations}"


def test_v0318_no_print_in_workflow_engine():
    """workflow.py must use logging, not print()."""
    import ast as _ast

    src = (ROOT / "modules" / "workflow_engine" / "workflow.py").read_text()
    tree = _ast.parse(src)
    prints = [
        node for node in _ast.walk(tree)
        if isinstance(node, _ast.Call)
        and isinstance(node.func, _ast.Name)
        and node.func.id == "print"
    ]
    assert len(prints) == 0, f"workflow.py still has {len(prints)} print() calls"


def test_v0318_no_print_in_indexer_modules():
    """Indexer modules (semantic.py, fingerprint.py) must use logging."""
    import ast as _ast

    indexer_files = [
        "modules/step1_material_analysis/indexer/semantic.py",
        "modules/step1_material_analysis/indexer/fingerprint.py",
        "modules/step1_material_analysis/video_asset_toolkit.py",
    ]
    for rel in indexer_files:
        src = (ROOT / rel).read_text()
        tree = _ast.parse(src)
        prints = [
            node for node in _ast.walk(tree)
            if isinstance(node, _ast.Call)
            and isinstance(node.func, _ast.Name)
            and node.func.id == "print"
        ]
        fname = Path(rel).name
        assert len(prints) == 0, f"{fname} still has {len(prints)} print() calls"
