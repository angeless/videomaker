from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.capabilities.content_publish import (
    bootstrap_publish_session,
    build_publish_plan,
    list_publish_platforms,
    run_publish_plan,
)


def test_content_publish_platform_matrix_contains_required_platforms():
    payload = list_publish_platforms()
    ids = {item["platform_id"] for item in payload["platforms"]}
    required = {
        "xiaohongshu",
        "ixigua",
        "douyin",
        "wechat_channels",
        "wechat_mp",
        "youtube",
        "instagram",
        "twitter",
        "threads",
        "facebook",
        "blog",
    }
    assert required.issubset(ids)
    assert payload["aliases"]["thread"] == "threads"
    assert payload["aliases"]["微信号"] == "wechat_channels"


def test_content_publish_plan_waiting_auth_without_valid_session():
    plan = build_publish_plan(
        content={"title": "标题", "description": "描述", "keywords": ["旅行"]},
        platform_ids=["xiaohongshu", "blog"],
        platform_content_type="video_post",
        dry_run=False,
        session={},
    )
    assert plan["status"] == "waiting_auth"
    assert len(plan["steps"]) == 2


def test_content_publish_run_posted_with_authenticated_session_and_blog_dual_format():
    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=60)
    plan = build_publish_plan(
        content={
            "title": "旅行记录",
            "description": "这是一次短视频旅行记录",
            "keywords": ["旅行", "vlog"],
        },
        platform_ids=["blog", "youtube"],
        platform_content_type="video_post",
        dry_run=False,
        session=session,
    )
    result = run_publish_plan(plan=plan, session=session, dry_run=False)
    assert result["status"] == "posted"
    assert result["summary"]["posted"] == 2
    blog_step = next(item for item in result["steps"] if item["platform_id"] == "blog")
    assert blog_step["content"]["markdown_frontmatter"].startswith("---")
    assert "<article>" in blog_step["content"]["html"]


def test_content_publish_run_waiting_auth_when_session_expired():
    session = bootstrap_publish_session(authenticated=False, expires_in_minutes=1)
    plan = build_publish_plan(
        content={"title": "T", "description": "D"},
        platform_ids=["twitter"],
        platform_content_type="article_post",
        dry_run=False,
        session=session,
    )
    result = run_publish_plan(plan=plan, session=session, dry_run=False)
    assert result["status"] == "waiting_auth"
    assert result["steps"][0]["run_state"] == "waiting_auth"


def test_content_publish_api_plan_and_run(tmp_path):
    fake_library_mod = types.ModuleType("modules.library.global_media_library")

    class _FakeGlobalMediaLibrary:
        def __init__(self, *args, **kwargs):
            self.db_path = ROOT / ".tmp_fake_library_content_publish.db"

    fake_library_mod.GlobalMediaLibrary = _FakeGlobalMediaLibrary
    sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

    from modules.app_api import server  # noqa: E402

    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        session_resp = client.post(
            "/api/capabilities/content_publish/session/bootstrap",
            json={"input_mode": "project", "authenticated": True, "expires_in_minutes": 30},
        )
        assert session_resp.status_code == 200
        session_payload = session_resp.get_json()
        assert session_payload["ok"] is True
        session_id = session_payload["session"]["session_id"]

        plan_resp = client.post(
            "/api/capabilities/content_publish/plan",
            json={
                "input_mode": "project",
                "platforms": ["blog", "thread", "微信号"],
                "platform_content_type": "article_post",
                "dry_run": True,
                "session_id": session_id,
                "content": {
                    "title": "标题",
                    "description": "描述",
                    "keywords": ["旅行"],
                    "article_markdown": "# Test",
                },
            },
        )
        assert plan_resp.status_code == 200
        plan_payload = plan_resp.get_json()
        assert plan_payload["ok"] is True
        plan = plan_payload["plan"]
        ids = [x["platform_id"] for x in plan["steps"]]
        assert ids == ["blog", "threads", "wechat_channels"]

        run_resp = client.post(
            "/api/capabilities/content_publish/run",
            json={"input_mode": "project", "session_id": session_id, "dry_run": True, "plan": plan},
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True
        assert run_payload["run"]["result"]["dry_run"] is True
    finally:
        server._project_dir = old_project_dir
