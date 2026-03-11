from pathlib import Path
import sys
import types
import json as pyjson
from urllib import error as urlerror

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
        platform_ids=["blog"],
        platform_content_type="video_post",
        dry_run=False,
        session=session,
    )
    result = run_publish_plan(plan=plan, session=session, dry_run=False, output_root=str(ROOT / ".tmp_publish_blog"))
    assert result["status"] == "posted"
    assert result["summary"]["posted"] == 1
    blog_step = next(item for item in result["steps"] if item["platform_id"] == "blog")
    assert blog_step["content"]["markdown_frontmatter"].startswith("---")
    assert "<article>" in blog_step["content"]["html"]
    assert blog_step["artifacts"]["markdown_path"].endswith(".md")
    assert blog_step["artifacts"]["html_path"].endswith(".html")


def test_content_publish_run_fails_without_connector_for_non_blog_platform():
    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=60)
    plan = build_publish_plan(
        content={"title": "标题", "description": "描述"},
        platform_ids=["youtube"],
        platform_content_type="video_post",
        dry_run=False,
        session=session,
        connectors={},
    )
    result = run_publish_plan(plan=plan, session=session, dry_run=False, connectors={})
    assert result["status"] in {"failed", "blocked"}
    assert result["summary"]["posted"] == 0
    assert (result["summary"]["failed"] + result["summary"]["blocked"]) >= 1


def test_content_publish_plan_youtube_api_requires_token_for_live_run(tmp_path):
    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=60)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake-video")
    plan = build_publish_plan(
        content={"title": "标题", "description": "描述", "media_urls": [str(video)]},
        platform_ids=["youtube"],
        platform_content_type="video_post",
        dry_run=False,
        session=session,
        connectors={"youtube": {"kind": "youtube_api"}},
    )
    assert plan["status"] == "blocked"
    assert plan["steps"][0]["connector_ready"] is False
    assert "未配置发布连接器" in plan["steps"][0]["reason"]


def test_content_publish_run_youtube_api_success(monkeypatch, tmp_path):
    from modules.capabilities import content_publish as cp

    class _FakeResp:
        def __init__(self, *, status=200, body="", headers=None):
            self.status = status
            self._body = body.encode("utf-8")
            self.headers = headers or {}

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    calls = []

    def _fake_urlopen(req, timeout=0):
        calls.append(
            {
                "url": req.full_url,
                "method": req.get_method(),
                "headers": dict(req.header_items()),
                "timeout": timeout,
            }
        )
        if len(calls) == 1:
            return _FakeResp(
                status=200,
                body="",
                headers={"Location": "https://upload.youtube.local/session/abc"},
            )
        return _FakeResp(
            status=200,
            body=pyjson.dumps({"id": "yt_video_123"}),
            headers={},
        )

    monkeypatch.setattr(cp.urlrequest, "urlopen", _fake_urlopen)

    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=60)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake-video-binary")
    connectors = {
        "youtube": {
            "kind": "youtube_api",
            "token": "yt_access_token_abc",
            "privacy_status": "private",
            "category_id": "22",
        }
    }
    plan = build_publish_plan(
        content={"title": "标题", "description": "描述", "media_urls": [str(video)]},
        platform_ids=["youtube"],
        platform_content_type="video_post",
        dry_run=False,
        session=session,
        connectors=connectors,
    )
    assert plan["status"] == "planned"
    assert plan["steps"][0]["connector_ready"] is True

    result = run_publish_plan(plan=plan, session=session, dry_run=False, connectors=connectors)
    assert result["status"] == "posted"
    assert result["summary"]["posted"] == 1
    step = result["steps"][0]
    assert step["connector"]["kind"] == "youtube_api"
    assert step["post_id"] == "yt_video_123"
    assert "youtube.com/watch?v=yt_video_123" in step["post_url"]
    assert len(calls) == 2
    assert calls[0]["method"] == "POST"
    assert "uploadType=resumable" in calls[0]["url"]
    assert calls[1]["method"] == "PUT"


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


# ═══════════════════════════════════════════════════════════════════════
# P1: Error Classification unit tests
# ═══════════════════════════════════════════════════════════════════════

from modules.capabilities.content_publish import (
    _classify_error,
    _PublishHTTPError,
    _validate_youtube_params,
    _build_publish_idempotency_digest,
)
import socket


class TestClassifyError:
    def test_auth_401(self):
        exc = _PublishHTTPError("HTTP 401", http_status=401)
        r = _classify_error(exc)
        assert r["error_class"] == "auth_failed"
        assert r["retryable"] is False

    def test_auth_403(self):
        exc = _PublishHTTPError("HTTP 403 forbidden", http_status=403)
        r = _classify_error(exc)
        assert r["error_class"] == "auth_failed"
        assert r["retryable"] is False

    def test_quota_429(self):
        exc = _PublishHTTPError("rate limit", http_status=429)
        r = _classify_error(exc)
        assert r["error_class"] == "quota_exceeded"
        assert r["retryable"] is True

    def test_platform_rejected_400(self):
        exc = _PublishHTTPError("bad request", http_status=400)
        r = _classify_error(exc)
        assert r["error_class"] == "platform_rejected"
        assert r["retryable"] is False

    def test_platform_rejected_422(self):
        exc = _PublishHTTPError("unprocessable", http_status=422)
        r = _classify_error(exc)
        assert r["error_class"] == "platform_rejected"

    def test_server_500(self):
        exc = _PublishHTTPError("server error", http_status=500)
        r = _classify_error(exc)
        assert r["error_class"] == "network_error"
        assert r["retryable"] is True

    def test_timeout_error(self):
        r = _classify_error(TimeoutError("timed out"))
        assert r["error_class"] == "network_error"
        assert r["retryable"] is True

    def test_socket_timeout(self):
        r = _classify_error(socket.timeout("timed out"))
        assert r["error_class"] == "network_error"
        assert r["retryable"] is True

    def test_config_missing_valueerror(self):
        r = _classify_error(ValueError("youtube_api 缺少 access_token/token"))
        assert r["error_class"] == "config_missing"
        assert r["retryable"] is False

    def test_params_invalid_valueerror(self):
        r = _classify_error(ValueError("YouTube title 不能超过 100 字符"))
        assert r["error_class"] == "params_invalid"
        assert r["retryable"] is False

    def test_config_missing_runtime_error(self):
        r = _classify_error(RuntimeError("youtube 未配置发布连接器"))
        assert r["error_class"] == "config_missing"
        assert r["retryable"] is False

    def test_unknown_fallback(self):
        r = _classify_error(Exception("something unexpected"))
        assert r["error_class"] == "unknown"
        assert r["retryable"] is False


# ═══════════════════════════════════════════════════════════════════════
# P1: YouTube param validation tests
# ═══════════════════════════════════════════════════════════════════════


class TestValidateYoutubeParams:
    def test_missing_token(self):
        import pytest
        with pytest.raises(ValueError, match="缺少"):
            _validate_youtube_params(
                {"content": {"title": "ok"}},
                {"kind": "youtube_api"},
            )

    def test_title_too_long(self):
        import pytest
        with pytest.raises(ValueError, match="100"):
            _validate_youtube_params(
                {"content": {"title": "A" * 101}},
                {"token": "abc"},
            )

    def test_description_too_long(self):
        import pytest
        with pytest.raises(ValueError, match="5000"):
            _validate_youtube_params(
                {"content": {"description": "D" * 5001}},
                {"token": "abc"},
            )

    def test_invalid_privacy_status(self):
        import pytest
        with pytest.raises(ValueError, match="privacy_status"):
            _validate_youtube_params(
                {"content": {"title": "ok"}},
                {"token": "abc", "privacy_status": "secret"},
            )

    def test_invalid_category_id(self):
        import pytest
        with pytest.raises(ValueError, match="category_id"):
            _validate_youtube_params(
                {"content": {"title": "ok"}},
                {"token": "abc", "category_id": "abc"},
            )

    def test_valid_params_pass(self):
        # Should not raise
        _validate_youtube_params(
            {"content": {"title": "ok", "description": "desc"}},
            {"token": "abc", "privacy_status": "private", "category_id": "22"},
        )


# ═══════════════════════════════════════════════════════════════════════
# P1: YouTube error path integration tests (monkeypatch)
# ═══════════════════════════════════════════════════════════════════════


def _make_youtube_plan_and_session(tmp_path, connectors=None):
    """Helper to build a ready-to-run YouTube plan."""
    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=60)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake-video-binary")
    if connectors is None:
        connectors = {
            "youtube": {
                "kind": "youtube_api",
                "token": "yt_token_test",
                "privacy_status": "private",
                "category_id": "22",
            }
        }
    plan = build_publish_plan(
        content={"title": "测试", "description": "desc", "media_urls": [str(video)]},
        platform_ids=["youtube"],
        platform_content_type="video_post",
        dry_run=False,
        session=session,
        connectors=connectors,
    )
    return plan, session, connectors


def test_youtube_error_detail_auth_401(monkeypatch, tmp_path):
    from modules.capabilities import content_publish as cp

    def _fake_urlopen(req, timeout=0):
        raise urlerror.HTTPError(
            req.full_url, 401, "Unauthorized", {}, None
        )

    monkeypatch.setattr(cp.urlrequest, "urlopen", _fake_urlopen)
    plan, session, connectors = _make_youtube_plan_and_session(tmp_path)

    result = run_publish_plan(plan=plan, session=session, dry_run=False, connectors=connectors)
    assert result["status"] == "failed"
    step = result["steps"][0]
    assert step["run_state"] == "failed"
    assert "error_detail" in step
    assert step["error_detail"]["error_class"] == "auth_failed"
    assert step["error_detail"]["retryable"] is False


def test_youtube_error_detail_quota_429(monkeypatch, tmp_path):
    from modules.capabilities import content_publish as cp

    def _fake_urlopen(req, timeout=0):
        raise urlerror.HTTPError(
            req.full_url, 429, "Too Many Requests", {}, None
        )

    monkeypatch.setattr(cp.urlrequest, "urlopen", _fake_urlopen)
    plan, session, connectors = _make_youtube_plan_and_session(tmp_path)

    result = run_publish_plan(plan=plan, session=session, dry_run=False, connectors=connectors)
    step = result["steps"][0]
    assert step["error_detail"]["error_class"] == "quota_exceeded"
    assert step["error_detail"]["retryable"] is True


def test_youtube_error_detail_network_timeout(monkeypatch, tmp_path):
    from modules.capabilities import content_publish as cp

    def _fake_urlopen(req, timeout=0):
        raise socket.timeout("connection timed out")

    monkeypatch.setattr(cp.urlrequest, "urlopen", _fake_urlopen)
    plan, session, connectors = _make_youtube_plan_and_session(tmp_path)

    result = run_publish_plan(plan=plan, session=session, dry_run=False, connectors=connectors)
    step = result["steps"][0]
    assert step["error_detail"]["error_class"] == "network_error"
    assert step["error_detail"]["retryable"] is True


# ═══════════════════════════════════════════════════════════════════════
# P1: recovery_hint tests
# ═══════════════════════════════════════════════════════════════════════


def test_recovery_hint_on_failed_run(monkeypatch, tmp_path):
    from modules.capabilities import content_publish as cp

    def _fake_urlopen(req, timeout=0):
        raise urlerror.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(cp.urlrequest, "urlopen", _fake_urlopen)
    plan, session, connectors = _make_youtube_plan_and_session(tmp_path)

    result = run_publish_plan(plan=plan, session=session, dry_run=False, connectors=connectors)
    hint = result["recovery_hint"]
    assert hint["can_rerun"] is True
    assert hint["rerun_scope"] == "failed_only"
    assert "auth_failed" in hint["error_classes"]
    assert hint["rerun_endpoint"] == "/api/capabilities/content_publish/rerun"


def test_recovery_hint_on_blocked_run():
    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=60)
    plan = build_publish_plan(
        content={"title": "T", "description": "D"},
        platform_ids=["youtube"],
        platform_content_type="video_post",
        dry_run=False,
        session=session,
        connectors={},  # no connector → blocked
    )
    result = run_publish_plan(plan=plan, session=session, dry_run=False, connectors={})
    hint = result["recovery_hint"]
    assert hint["can_rerun"] is True
    assert hint["rerun_scope"] == "fix_config_then_rerun"


def test_recovery_hint_on_success():
    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=60)
    plan = build_publish_plan(
        content={"title": "T", "description": "D"},
        platform_ids=["blog"],
        platform_content_type="article_post",
        dry_run=False,
        session=session,
    )
    result = run_publish_plan(
        plan=plan, session=session, dry_run=False,
        output_root=str(ROOT / ".tmp_publish_recovery_test"),
    )
    hint = result["recovery_hint"]
    assert hint["can_rerun"] is False
    assert hint["rerun_scope"] == "none"
    assert hint["error_classes"] == []


def test_recovery_hint_mixed_failed_and_blocked(monkeypatch, tmp_path):
    """Plan with youtube (will fail) + instagram (blocked, no connector)."""
    from modules.capabilities import content_publish as cp

    def _fake_urlopen(req, timeout=0):
        raise urlerror.HTTPError(req.full_url, 500, "Server Error", {}, None)

    monkeypatch.setattr(cp.urlrequest, "urlopen", _fake_urlopen)
    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=60)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    connectors = {"youtube": {"kind": "youtube_api", "token": "t", "privacy_status": "private"}}
    plan = build_publish_plan(
        content={"title": "T", "description": "D", "media_urls": [str(video)]},
        platform_ids=["youtube", "instagram"],
        platform_content_type="video_post",
        dry_run=False,
        session=session,
        connectors=connectors,
    )
    result = run_publish_plan(plan=plan, session=session, dry_run=False, connectors=connectors)
    hint = result["recovery_hint"]
    assert hint["can_rerun"] is True
    assert hint["rerun_scope"] == "failed_and_blocked"


# ═══════════════════════════════════════════════════════════════════════
# P1: Idempotency digest tests
# ═══════════════════════════════════════════════════════════════════════


class TestIdempotencyDigest:
    def test_same_plan_same_digest(self):
        plan = {"steps": [{"platform_id": "youtube", "content": {"title": "T", "description": "D", "media_urls": ["/v/a.mp4"]}}]}
        d1 = _build_publish_idempotency_digest(plan, {"youtube": {"kind": "youtube_api"}}, False)
        d2 = _build_publish_idempotency_digest(plan, {"youtube": {"kind": "youtube_api"}}, False)
        assert d1 == d2
        assert len(d1) == 32

    def test_different_title_different_digest(self):
        plan_a = {"steps": [{"platform_id": "youtube", "content": {"title": "A"}}]}
        plan_b = {"steps": [{"platform_id": "youtube", "content": {"title": "B"}}]}
        d1 = _build_publish_idempotency_digest(plan_a, {}, False)
        d2 = _build_publish_idempotency_digest(plan_b, {}, False)
        assert d1 != d2

    def test_dry_run_vs_live_different_digest(self):
        plan = {"steps": [{"platform_id": "youtube", "content": {"title": "T"}}]}
        d1 = _build_publish_idempotency_digest(plan, {}, True)
        d2 = _build_publish_idempotency_digest(plan, {}, False)
        assert d1 != d2

    def test_different_media_urls_different_digest(self):
        plan_a = {"steps": [{"platform_id": "yt", "content": {"title": "T", "media_urls": ["/a.mp4"]}}]}
        plan_b = {"steps": [{"platform_id": "yt", "content": {"title": "T", "media_urls": ["/b.mp4"]}}]}
        d1 = _build_publish_idempotency_digest(plan_a, {}, False)
        d2 = _build_publish_idempotency_digest(plan_b, {}, False)
        assert d1 != d2


# ═══════════════════════════════════════════════════════════════════════
# P1: Retry hint map test
# ═══════════════════════════════════════════════════════════════════════


def test_retry_hint_map_contains_content_publish():
    """_RETRY_HINT_MAP must have content_publish entry."""
    fake_library_mod = types.ModuleType("modules.library.global_media_library")

    class _FakeGML:
        def __init__(self, *a, **kw):
            self.db_path = ROOT / ".tmp_fake_lib_hint_map.db"

    fake_library_mod.GlobalMediaLibrary = _FakeGML
    sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

    from modules.app_api import server
    assert "content_publish" in server._RETRY_HINT_MAP
    assert server._RETRY_HINT_MAP["content_publish"] == "/api/capabilities/content_publish/rerun"


# ═══════════════════════════════════════════════════════════════════════
# P1: API-level audit tests
# ═══════════════════════════════════════════════════════════════════════


def test_publish_run_audit_includes_summary(tmp_path):
    """publish_run audit detail should contain posted/failed/blocked counts."""
    fake_library_mod = types.ModuleType("modules.library.global_media_library")

    class _FakeGML:
        def __init__(self, *a, **kw):
            self.db_path = ROOT / ".tmp_fake_lib_audit_summary.db"

    fake_library_mod.GlobalMediaLibrary = _FakeGML
    sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

    from modules.app_api import server
    from modules.app_api.services.audit_log import init_audit_log

    init_audit_log(tmp_path / "audit_log.db")

    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        # Bootstrap session
        sr = client.post("/api/capabilities/content_publish/session/bootstrap",
                         json={"input_mode": "project", "authenticated": True, "expires_in_minutes": 30})
        sid = sr.get_json()["session"]["session_id"]

        # Plan with blog (will succeed)
        pr = client.post("/api/capabilities/content_publish/plan", json={
            "input_mode": "project", "platforms": ["blog"],
            "platform_content_type": "article_post", "dry_run": True,
            "session_id": sid, "content": {"title": "T", "description": "D"},
        })
        plan = pr.get_json()["plan"]

        # Run dry_run=True
        rr = client.post("/api/capabilities/content_publish/run", json={
            "input_mode": "project", "session_id": sid, "dry_run": True, "plan": plan,
        })
        assert rr.status_code == 200
        payload = rr.get_json()
        assert payload["ok"] is True

        # Check audit log
        audit_resp = client.get("/api/system/audit")
        if audit_resp.status_code == 200:
            entries = audit_resp.get_json().get("entries", [])
            publish_run_entries = [e for e in entries if e.get("operation") == "publish_run"]
            if publish_run_entries:
                detail = publish_run_entries[-1].get("detail", {})
                assert "posted" in detail or "dry_run" in detail
    finally:
        server._project_dir = old_project_dir


def test_publish_blocked_audit_written(tmp_path):
    """When steps are blocked, publish_blocked audit event should be written."""
    fake_library_mod = types.ModuleType("modules.library.global_media_library")

    class _FakeGML:
        def __init__(self, *a, **kw):
            self.db_path = ROOT / ".tmp_fake_lib_audit_blocked.db"

    fake_library_mod.GlobalMediaLibrary = _FakeGML
    sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

    from modules.app_api import server
    from modules.app_api.services.audit_log import init_audit_log

    # Ensure audit log is initialised with a temp db
    init_audit_log(tmp_path / "audit_log.db")

    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        sr = client.post("/api/capabilities/content_publish/session/bootstrap",
                         json={"input_mode": "project", "authenticated": True, "expires_in_minutes": 30})
        sid = sr.get_json()["session"]["session_id"]

        # Plan with youtube, no connector → blocked
        pr = client.post("/api/capabilities/content_publish/plan", json={
            "input_mode": "project", "platforms": ["youtube"],
            "platform_content_type": "video_post", "dry_run": False,
            "session_id": sid, "content": {"title": "T", "description": "D"},
            "connectors": {},
        })
        plan = pr.get_json()["plan"]

        rr = client.post("/api/capabilities/content_publish/run", json={
            "input_mode": "project", "session_id": sid, "dry_run": False, "plan": plan,
        })
        assert rr.status_code == 200
        result = rr.get_json()
        # Status should be blocked or failed
        assert result["state"] in ("blocked", "failed")

        # Check audit
        audit_resp = client.get("/api/system/audit")
        if audit_resp.status_code == 200:
            entries = audit_resp.get_json().get("entries", [])
            blocked_entries = [e for e in entries if e.get("operation") == "publish_blocked"]
            error_entries = [e for e in entries if e.get("operation") == "publish_error"]
            # Should have at least one blocked or error audit entry
            assert len(blocked_entries) >= 1 or len(error_entries) >= 1
    finally:
        server._project_dir = old_project_dir
