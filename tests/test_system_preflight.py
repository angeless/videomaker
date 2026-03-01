import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

fake_library_mod = types.ModuleType("modules.library.global_media_library")


class _FakeGlobalMediaLibrary:
    def __init__(self, *args, **kwargs):
        self.db_path = ROOT / ".tmp_fake_library_preflight.db"


fake_library_mod.GlobalMediaLibrary = _FakeGlobalMediaLibrary
sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

from modules.app_api import server  # noqa: E402
from modules.app_api.services import preflight_service  # noqa: E402


def test_preflight_service_returns_structured_report(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight_service, "_which", lambda _bin: "/usr/bin/mock")
    monkeypatch.setattr(preflight_service, "_module_exists", lambda _name: True)

    report = preflight_service.run_startup_preflight(
        repo_root=tmp_path,
        library_db_path=tmp_path / "video_library.db",
        app_state_db_path=tmp_path / "app_state.db",
        ai_settings={"provider": "openai", "ai_model": "gpt-4o-mini", "openai_api_key": "sk-test"},
        ui_settings={"default_videos_dir": str(tmp_path)},
        secret_storage_status={"backend": "mock", "available": True, "reason": ""},
        require_local_token=True,
        require_csrf=True,
    )

    assert isinstance(report, dict)
    assert "summary" in report
    assert "checks" in report
    assert report["summary"]["total"] >= 10
    ids = {item["id"] for item in report["checks"]}
    assert "runtime.ffmpeg" in ids
    assert "nle.davinci" in ids


def test_system_preflight_route_returns_report():
    client = server.app.test_client()
    resp = client.get("/api/system/preflight")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    preflight = payload["preflight"]
    assert isinstance(preflight, dict)
    assert "summary" in preflight
    assert "checks" in preflight
    assert isinstance(preflight.get("checks"), list)


def test_refinement_connectors_route_returns_status():
    client = server.app.test_client()
    resp = client.get("/api/capabilities/refinement/connectors")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    connectors = payload.get("connectors", [])
    assert isinstance(connectors, list)
    assert any(item.get("editor") == "davinci" for item in connectors)
