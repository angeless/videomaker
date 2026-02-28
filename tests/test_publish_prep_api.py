import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


fake_library_mod = types.ModuleType("modules.library.global_media_library")


class _FakeGlobalMediaLibrary:
    def __init__(self, *args, **kwargs):
        self.db_path = ROOT / ".tmp_fake_library_publish_prep_api.db"


fake_library_mod.GlobalMediaLibrary = _FakeGlobalMediaLibrary
sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

from modules.app_api import server  # noqa: E402


def test_publish_prep_profiles_upsert_and_list(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        upsert_resp = client.post(
            "/api/capabilities/publish_prep/profiles",
            json={
                "profiles": {
                    "youtube": {
                        "platform_id": "youtube",
                        "name": "YouTube Custom",
                        "title_prompt": "YT-TITLE::{script}",
                        "body_prompt": "YT-BODY::{voiceover}",
                        "keywords_prompt": "YT-KW::{script}",
                        "max_keywords": 6,
                    }
                }
            },
        )
        assert upsert_resp.status_code == 200
        upsert_payload = upsert_resp.get_json()
        assert upsert_payload["ok"] is True
        assert upsert_payload["override_count"] >= 1

        profile_file = tmp_path / "data" / "publish_prep_profiles.json"
        assert profile_file.exists()
        persisted = json.loads(profile_file.read_text(encoding="utf-8"))
        assert "youtube" in persisted

        list_resp = client.get("/api/capabilities/publish_prep/profiles")
        assert list_resp.status_code == 200
        list_payload = list_resp.get_json()
        assert list_payload["ok"] is True
        by_id = {item["platform_id"]: item for item in list_payload["profiles"]}
        assert by_id["youtube"]["name"] == "YouTube Custom"
        assert by_id["youtube"]["max_keywords"] == 6
    finally:
        server._project_dir = old_project_dir


def test_publish_prep_generate_with_saved_and_request_overrides(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        client.post(
            "/api/capabilities/publish_prep/profiles",
            json={
                "profiles": {
                    "youtube": {
                        "platform_id": "youtube",
                        "name": "YouTube Save",
                        "title_prompt": "YT-SAVED::{script}",
                        "body_prompt": "YT-SAVED-B::{voiceover}",
                        "keywords_prompt": "YT-SAVED-K::{script}",
                        "max_keywords": 5,
                    }
                }
            },
        )

        gen_resp = client.post(
            "/api/capabilities/publish_prep/generate",
            json={
                "script_text": "开场海边，结尾山顶，总结拍摄机位和时间点。",
                "voiceover_text": "这条路线适合第一次来拍 vlog 的朋友。",
                "platforms": ["youtube", "xhs"],
                "profile_overrides": {
                    "xhs": {
                        "platform_id": "xiaohongshu",
                        "name": "XHS Custom",
                        "title_prompt": "XHS-T::{script}",
                        "body_prompt": "XHS-B::{voiceover}",
                        "keywords_prompt": "XHS-K::{script}",
                        "max_keywords": 2,
                    }
                },
                "store_result": True,
            },
        )
        assert gen_resp.status_code == 200
        payload = gen_resp.get_json()
        assert payload["ok"] is True

        results = {item["platform_id"]: item for item in payload["result"]["platform_results"]}
        assert set(results.keys()) == {"youtube", "xiaohongshu"}
        assert results["youtube"]["prompts"]["title"].startswith("YT-SAVED::")
        assert results["xiaohongshu"]["prompts"]["title"].startswith("XHS-T::")
        assert len(results["xiaohongshu"]["content"]["keywords"]) <= 2

        output_path = payload["output"]
        assert output_path
        assert Path(output_path).exists()
    finally:
        server._project_dir = old_project_dir


def test_publish_prep_generate_supports_project_input_mode_and_llm_fallback_warning(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "script_draft.json").write_text(
        json.dumps(
            {
                "clips": [{"text": "第一段脚本"}, {"text": "第二段脚本"}],
                "subtitles": [
                    {"start_time": 0.0, "end_time": 1.0, "cn_text": "字幕一"},
                    {"start_time": 1.1, "end_time": 2.2, "cn_text": "字幕二"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    client = server.app.test_client()
    try:
        gen_resp = client.post(
            "/api/capabilities/publish_prep/generate",
            json={
                "input_mode": "project",
                "platforms": ["微信号", "thread", "facebook"],
                "platform_content_type": "article_post",
                "use_llm": True,  # no key in test env -> should fallback with warning
                "store_result": True,
            },
        )
        assert gen_resp.status_code == 200
        payload = gen_resp.get_json()
        assert payload["ok"] is True
        assert payload["input_mode"] == "project"
        assert payload["platform_content_type"] == "article_post"
        assert payload["llm"]["enabled"] is True
        assert payload["llm"]["fallback"] is True
        assert any("降级" in msg for msg in payload.get("warnings", []))

        results = {item["platform_id"]: item for item in payload["result"]["platform_results"]}
        assert set(results.keys()) == {"wechat_channels", "threads", "facebook"}
        assert results["wechat_channels"]["platform_content_type"] == "article_post"
    finally:
        server._project_dir = old_project_dir


def test_agent_capabilities_and_task_plan_include_publish_prep(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        cap_resp = client.get("/api/agent/capabilities?actor_type=agent&actor_id=publish_planner")
        assert cap_resp.status_code == 200
        cap_payload = cap_resp.get_json()
        assert cap_payload["ok"] is True
        assert any(x.get("skill_id") == "skill.publish_prep.generate" for x in cap_payload["agent_skills"])
        specs = {x.get("capability_id"): x for x in cap_payload["capabilities"]}
        assert "publish_prep" in specs
        assert specs["publish_prep"]["agent_routes"]["plan"] == "POST /api/capabilities/publish_prep/generate"

        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "capability_id": "publish_prep",
                "input": {
                    "script_text": "a",
                    "voiceover_text": "b",
                    "platforms": ["youtube"],
                },
                "actor_type": "agent",
                "actor_id": "publish_planner",
            },
        )
        assert plan_resp.status_code == 200
        plan_payload = plan_resp.get_json()
        assert plan_payload["ok"] is True
        assert plan_payload["task_plan"]["primary_call"]["endpoint"] == "/api/capabilities/publish_prep/generate"
    finally:
        server._project_dir = old_project_dir
