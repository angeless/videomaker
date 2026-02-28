import sys
import types
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


fake_library_mod = types.ModuleType("modules.library.global_media_library")


class _FakeGlobalMediaLibrary:
    def __init__(self, *args, **kwargs):
        self.db_path = ROOT / ".tmp_fake_library.db"


fake_library_mod.GlobalMediaLibrary = _FakeGlobalMediaLibrary
sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

from modules.app_api import server  # noqa: E402


def test_capabilities_response_includes_request_context_and_summary():
    client = server.app.test_client()
    resp = client.get("/api/capabilities?actor_type=agent&actor_id=bot_1&run_mode=headless&trace_id=t001")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["request_context"]["actor_type"] == "agent"
    assert payload["request_context"]["actor_id"] == "bot_1"
    assert payload["request_context"]["run_mode"] == "headless"
    assert payload["request_context"]["trace_id"] == "t001"
    assert isinstance(payload.get("plan_summary"), dict)
    assert isinstance(payload.get("artifacts"), list)
    assert isinstance(payload.get("warnings"), list)


def test_agent_capabilities_and_task_plan(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "agent_cost_model.json").write_text(
        json.dumps(
            {
                "default_rates": {
                    "prompt_usd_per_1k_tokens": 0.003,
                    "completion_usd_per_1k_tokens": 0.009,
                    "compute_usd_per_second": 0.0001,
                },
                "providers": {
                    "openai": {
                        "default_rates": {
                            "prompt_usd_per_1k_tokens": 0.004,
                            "completion_usd_per_1k_tokens": 0.01,
                            "compute_usd_per_second": 0.0002,
                        },
                        "models": {
                            "gpt-4o-mini": {
                                "prompt_usd_per_1k_tokens": 0.005,
                                "completion_usd_per_1k_tokens": 0.012,
                                "compute_usd_per_second": 0.00025,
                            }
                        },
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    client = server.app.test_client()
    try:
        resp = client.get("/api/agent/capabilities?actor_type=agent&actor_id=planner")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["request_context"]["actor_type"] == "agent"
        assert "request_context_schema" in payload
        assert "agent_template_schema" in payload
        assert "agent_task_modes" in payload
        assert "parallel" in payload["agent_task_modes"]["skill_sequence"]["supported_strategy"]
        assert "conditional" in payload["agent_task_modes"]["skill_sequence"]["supported_strategy"]
        assert "budget_fields" in payload["agent_task_modes"]["skill_sequence"]
        assert "agent_governance" in payload
        assert "cost_model" in payload["agent_governance"]
        assert payload["agent_governance"]["cost_model_file"] == "data/agent_cost_model.json"
        assert payload["agent_governance"]["cost_model"]["providers"]["openai"]["models"]["gpt-4o-mini"][
            "prompt_usd_per_1k_tokens"
        ] == 0.005
        assert "agent_skills" in payload
        assert payload["agent_management_routes"]["skills_invoke"] == "POST /api/agent/skills/invoke"
        assert payload["agent_management_routes"]["tasks_history"] == "GET /api/agent/tasks/history"
        assert payload["agent_management_routes"]["tasks_export"] == "POST /api/agent/tasks/<job_id>/export"
        assert payload["agent_management_routes"]["tasks_replay"] == "POST /api/agent/tasks/<job_id>/replay"
        assert payload["agent_management_routes"]["observability_summary"] == "GET /api/agent/observability"
        assert payload["agent_management_routes"]["observability_export"] == "POST /api/agent/observability/export"
        assert any(x.get("skill_id") == "skill.text_rough_cut.plan" for x in payload["agent_skills"])
        assert any(x.get("skill_id") == "skill.subtitle_calibration.run" for x in payload["agent_skills"])
        assert any(x.get("skill_id") == "skill.image_semantic.analyze" for x in payload["agent_skills"])
        assert any(x.get("skill_id") == "skill.article_expand.generate" for x in payload["agent_skills"])
        assert any(x.get("skill_id") == "skill.content_publish.run" for x in payload["agent_skills"])

        by_cap = {x.get("capability_id"): x for x in payload["capabilities"]}
        assert by_cap["subtitle_calibration"]["agent_routes"]["run"] == "POST /api/capabilities/subtitle_calibration/run"
        assert by_cap["image_semantic"]["agent_routes"]["analyze"] == "POST /api/capabilities/image_semantic/analyze"
        assert by_cap["article_expand"]["agent_routes"]["generate"] == "POST /api/capabilities/article_expand/generate"
        assert by_cap["content_publish"]["agent_routes"]["run"] == "POST /api/capabilities/content_publish/run"

        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "capability_id": "text_rough_cut",
                "input": {"target_duration_s": 20},
                "actor_type": "agent",
                "actor_id": "planner",
                "trace_id": "tr_plan_1",
            },
        )
        assert plan_resp.status_code == 200
        plan_payload = plan_resp.get_json()
        assert plan_payload["ok"] is True
        assert plan_payload["task_plan"]["capability_id"] == "text_rough_cut"
        assert plan_payload["task_plan"]["primary_call"]["endpoint"] == "/api/capabilities/text_rough_cut/plan"
    finally:
        server._project_dir = old_project_dir


def test_capability_post_idempotency_replay(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._capability_idempotency_lock:
        server._capability_idempotency_cache.clear()

    client = server.app.test_client()
    body = {
        "title": "城市夜景漫游",
        "category": "travel",
        "idempotency_key": "idem_topic_1",
        "actor_type": "agent",
        "actor_id": "planner",
    }
    try:
        first = client.post("/api/capabilities/topic_library", json=body)
        second = client.post("/api/capabilities/topic_library", json=body)
        assert first.status_code == 200
        assert second.status_code == 200
        p1 = first.get_json()
        p2 = second.get_json()
        assert p1["ok"] is True
        assert p2["ok"] is True
        assert p1["idempotency"]["key"] == "idem_topic_1"
        assert p1["idempotency"]["replayed"] is False
        assert p2["idempotency"]["replayed"] is True
        assert p1["slug"] == p2["slug"]
    finally:
        server._project_dir = old_project_dir


def test_capability_post_idempotency_replay_from_persisted_store(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    with server._capability_idempotency_lock:
        server._capability_idempotency_cache.clear()

    client = server.app.test_client()
    body = {
        "title": "海边骑行片段",
        "category": "travel",
        "idempotency_key": "idem_topic_persist_1",
        "actor_type": "agent",
        "actor_id": "planner_persist",
    }
    try:
        first = client.post("/api/capabilities/topic_library", json=body)
        assert first.status_code == 200
        p1 = first.get_json()
        assert p1["ok"] is True
        assert p1["idempotency"]["replayed"] is False

        store_path = data_dir / "capability_idempotency_cache.json"
        assert store_path.exists()
        store_payload = json.loads(store_path.read_text(encoding="utf-8"))
        assert isinstance(store_payload.get("records"), list)
        assert any(str(item.get("cache_key", "")).find("idem_topic_persist_1") >= 0 for item in store_payload["records"])

        with server._capability_idempotency_lock:
            server._capability_idempotency_cache.clear()

        second = client.post("/api/capabilities/topic_library", json=body)
        assert second.status_code == 200
        p2 = second.get_json()
        assert p2["ok"] is True
        assert p2["idempotency"]["replayed"] is True
        assert p2["idempotency"]["source"] == "persisted"
        assert p1["slug"] == p2["slug"]
    finally:
        server._project_dir = old_project_dir


def test_capability_post_idempotency_ignores_expired_persisted_entry(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._capability_idempotency_lock:
        server._capability_idempotency_cache.clear()

    cache_key = server._make_capability_idempotency_cache_key(
        "/api/capabilities/topic_library",
        {
            "actor_id": "planner_expired",
            "idempotency_key": "idem_topic_expired_1",
        },
    )
    expired_entry = {
        "status": 200,
        "body": {
            "ok": True,
            "slug": "expired-old",
            "idempotency": {"key": "idem_topic_expired_1", "replayed": True},
        },
        "created_at": (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds"),
    }
    server._save_capability_idempotency_store({cache_key: expired_entry})

    client = server.app.test_client()
    body = {
        "title": "过期幂等缓存不应被回放",
        "category": "travel",
        "idempotency_key": "idem_topic_expired_1",
        "actor_type": "agent",
        "actor_id": "planner_expired",
    }
    try:
        resp = client.post("/api/capabilities/topic_library", json=body)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["idempotency"]["replayed"] is False
    finally:
        server._project_dir = old_project_dir


def test_capability_idempotency_cache_list_and_prune(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    active_key = server._make_capability_idempotency_cache_key(
        "/api/capabilities/topic_library",
        {"actor_id": "planner_cache", "idempotency_key": "idem_active_1"},
    )
    expired_key = server._make_capability_idempotency_cache_key(
        "/api/capabilities/topic_library",
        {"actor_id": "planner_cache", "idempotency_key": "idem_expired_1"},
    )
    other_active_key = server._make_capability_idempotency_cache_key(
        "/api/capabilities/topic_copy/draft",
        {"actor_id": "planner_other", "idempotency_key": "idem_other_1"},
    )
    now_dt = datetime.now()
    active_entry = {
        "status": 200,
        "body": {"ok": True, "idempotency": {"key": "idem_active_1", "replayed": False}},
        "created_at": (now_dt - timedelta(seconds=2)).isoformat(timespec="seconds"),
    }
    expired_entry = {
        "status": 200,
        "body": {"ok": True, "idempotency": {"key": "idem_expired_1", "replayed": True}},
        "created_at": (now_dt - timedelta(days=30)).isoformat(timespec="seconds"),
    }
    other_active_entry = {
        "status": 200,
        "body": {"ok": True, "idempotency": {"key": "idem_other_1", "replayed": False}},
        "created_at": (now_dt - timedelta(seconds=1)).isoformat(timespec="seconds"),
    }

    with server._capability_idempotency_lock:
        server._capability_idempotency_cache.clear()
        server._capability_idempotency_cache.update(
            {
                active_key: active_entry,
                expired_key: expired_entry,
                other_active_key: other_active_entry,
            }
        )
    server._save_capability_idempotency_store(
        {
            active_key: active_entry,
            expired_key: expired_entry,
            other_active_key: other_active_entry,
        }
    )

    client = server.app.test_client()
    try:
        list_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=false"
        )
        assert list_resp.status_code == 200
        list_payload = list_resp.get_json()
        assert list_payload["ok"] is True
        assert list_payload["stats"]["total"] == 2
        assert list_payload["stats"]["expired"] == 0
        assert all(x.get("expired") is False for x in list_payload.get("records", []))

        list_expired_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=true"
        )
        assert list_expired_resp.status_code == 200
        list_expired_payload = list_expired_resp.get_json()
        assert list_expired_payload["stats"]["total"] == 3
        assert list_expired_payload["stats"]["expired"] == 1
        assert any(x.get("expired") is True for x in list_expired_payload.get("records", []))
        assert list_expired_payload["stats"]["offset"] == 0
        assert list_expired_payload["stats"]["limit"] == 200

        page_1_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=true&limit=1&offset=0"
        )
        assert page_1_resp.status_code == 200
        page_1_payload = page_1_resp.get_json()
        assert page_1_payload["stats"]["total"] == 3
        assert page_1_payload["stats"]["returned"] == 1
        assert page_1_payload["stats"]["has_more"] is True
        assert page_1_payload["stats"]["offset"] == 0
        assert page_1_payload["records"][0]["idempotency_key"] == "idem_other_1"

        page_2_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=true&limit=1&offset=1"
        )
        assert page_2_resp.status_code == 200
        page_2_payload = page_2_resp.get_json()
        assert page_2_payload["stats"]["returned"] == 1
        assert page_2_payload["stats"]["has_more"] is True
        assert page_2_payload["stats"]["offset"] == 1
        assert page_2_payload["records"][0]["idempotency_key"] == "idem_active_1"

        page_3_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=true&limit=1&offset=2"
        )
        assert page_3_resp.status_code == 200
        page_3_payload = page_3_resp.get_json()
        assert page_3_payload["stats"]["returned"] == 1
        assert page_3_payload["stats"]["has_more"] is False
        assert page_3_payload["stats"]["offset"] == 2
        assert page_3_payload["records"][0]["idempotency_key"] == "idem_expired_1"

        actor_filter_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=true&actor_id=planner_cache"
        )
        assert actor_filter_resp.status_code == 200
        actor_filter_payload = actor_filter_resp.get_json()
        assert actor_filter_payload["stats"]["total"] == 2
        assert all((x.get("actor_id") or "") == "planner_cache" for x in actor_filter_payload.get("records", []))

        endpoint_filter_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=true&endpoint=topic_copy"
        )
        assert endpoint_filter_resp.status_code == 200
        endpoint_filter_payload = endpoint_filter_resp.get_json()
        assert endpoint_filter_payload["stats"]["total"] == 1
        assert all("topic_copy" in (x.get("endpoint") or "") for x in endpoint_filter_payload.get("records", []))

        idem_filter_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=true&idempotency_key=idem_active_1&match_mode=exact"
        )
        assert idem_filter_resp.status_code == 200
        idem_filter_payload = idem_filter_resp.get_json()
        assert idem_filter_payload["stats"]["total"] == 1
        assert all((x.get("idempotency_key") or "") == "idem_active_1" for x in idem_filter_payload.get("records", []))

        idem_exact_miss_resp = client.get(
            "/api/capabilities/idempotency/cache?source=merged&ttl_seconds=3600&include_expired=true&idempotency_key=idem_active&match_mode=exact"
        )
        assert idem_exact_miss_resp.status_code == 200
        idem_exact_miss_payload = idem_exact_miss_resp.get_json()
        assert idem_exact_miss_payload["stats"]["total"] == 0

        keep_expired_resp = client.post(
            "/api/capabilities/idempotency/cache/prune",
            json={
                "ttl_seconds": 3600,
                "remove_expired": False,
                "max_entries": 10,
            },
        )
        assert keep_expired_resp.status_code == 200
        keep_expired_payload = keep_expired_resp.get_json()
        assert keep_expired_payload["ok"] is True
        assert keep_expired_payload["prune"]["memory_after"] == 3
        assert keep_expired_payload["prune"]["persisted_after"] == 3

        prune_resp = client.post(
            "/api/capabilities/idempotency/cache/prune",
            json={
                "ttl_seconds": 3600,
                "remove_expired": True,
            },
        )
        assert prune_resp.status_code == 200
        prune_payload = prune_resp.get_json()
        assert prune_payload["ok"] is True
        assert prune_payload["prune"]["memory_before"] == 3
        assert prune_payload["prune"]["memory_after"] == 2
        assert prune_payload["prune"]["persisted_before"] == 3
        assert prune_payload["prune"]["persisted_after"] == 2

        bad_source_resp = client.get("/api/capabilities/idempotency/cache?source=invalid")
        assert bad_source_resp.status_code == 400
        bad_match_mode_resp = client.get("/api/capabilities/idempotency/cache?match_mode=prefix")
        assert bad_match_mode_resp.status_code == 400
    finally:
        server._project_dir = old_project_dir


def test_agent_task_run_and_status(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "capability_id": "text_rough_cut",
                "input": {"target_duration_s": 12},
                "actor_type": "agent",
                "actor_id": "runner_1",
                "trace_id": "tr_run_1",
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True
        assert run_payload["capability_id"] == "text_rough_cut"
        job_id = run_payload["job_id"]

        final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"
        assert final["result"]["capability_id"] == "text_rough_cut"
        assert final["result"]["response"]["ok"] is True
        assert final["chain_view"]["mode"] == "single_capability"
        assert final["chain_view"]["node_count"] == 1
        assert final["chain_view"]["counts"]["done"] >= 1
    finally:
        server._project_dir = old_project_dir


def test_agent_skill_invoke_and_status(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        invoke_resp = client.post(
            "/api/agent/skills/invoke",
            json={
                "skill_id": "skill.text_rough_cut.plan",
                "input": {"target_duration_s": 14},
                "retry_policy": {"max_retries": 1, "backoff_ms": 10},
                "actor_type": "agent",
                "actor_id": "skill_runner_1",
                "trace_id": "tr_skill_1",
            },
        )
        assert invoke_resp.status_code == 200
        invoke_payload = invoke_resp.get_json()
        assert invoke_payload["ok"] is True
        assert invoke_payload["skill_id"] == "skill.text_rough_cut.plan"
        job_id = invoke_payload["job_id"]

        final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["kind"] == "agent_skill"
        assert final["status"] == "done"
        assert final["result"]["skill_id"] == "skill.text_rough_cut.plan"
        assert final["result"]["response"]["ok"] is True
        assert final["chain_view"]["mode"] == "skill_invoke"
        assert final["chain_view"]["node_count"] == 1
        assert final["chain_view"]["totals"]["total_tokens"] >= 0

        bad_skill = client.post(
            "/api/agent/skills/invoke",
            json={
                "skill_id": "skill.unknown",
                "input": {},
                "actor_type": "agent",
                "actor_id": "skill_runner_1",
            },
        )
        assert bad_skill.status_code == 400
        assert "不支持的 skill_id" in str((bad_skill.get_json() or {}).get("error", ""))
    finally:
        server._project_dir = old_project_dir


def test_agent_task_replay(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "capability_id": "refinement",
                "action": "plan",
                "input": {"style": "clean_vlog", "quality": "high"},
                "actor_type": "agent",
                "actor_id": "replay_bot_1",
                "trace_id": "tr_replay_base_1",
                "idempotency_key": "idem_replay_base_1",
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True
        base_job_id = run_payload["job_id"]

        final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{base_job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"

        replay_resp = client.post(
            f"/api/agent/tasks/{base_job_id}/replay",
            json={
                "payload_overrides": {
                    "input": {"style": "cinematic", "quality": "premium"},
                },
                "new_trace_id": "tr_replay_run_2",
                "clear_idempotency": True,
            },
        )
        assert replay_resp.status_code == 200
        replay_payload = replay_resp.get_json()
        assert replay_payload["ok"] is True
        assert replay_payload["target"]["endpoint"] == "/api/agent/tasks/run"
        assert "idempotency_key" not in replay_payload["request_payload"]
        assert replay_payload["request_payload"]["trace_id"] == "tr_replay_run_2"
        assert replay_payload["request_payload"]["input"]["style"] == "cinematic"
        new_job_id = replay_payload.get("new_job_id", "")
        assert new_job_id

        replay_final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{new_job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            replay_final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert replay_final is not None
        assert replay_final["status"] == "done"
        plan = (
            replay_final.get("result", {})
            .get("response", {})
            .get("plan", {})
        )
        assert plan.get("transition_style") == "smoothleft"
    finally:
        server._project_dir = old_project_dir


def test_agent_skill_replay(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        invoke_resp = client.post(
            "/api/agent/skills/invoke",
            json={
                "skill_id": "skill.text_rough_cut.plan",
                "input": {"target_duration_s": 14},
                "actor_type": "agent",
                "actor_id": "replay_skill_bot",
                "trace_id": "tr_skill_replay_base",
                "idempotency_key": "idem_skill_replay_1",
            },
        )
        assert invoke_resp.status_code == 200
        invoke_payload = invoke_resp.get_json()
        assert invoke_payload["ok"] is True
        base_job_id = invoke_payload["job_id"]

        base_final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{base_job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            base_final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert base_final is not None
        assert base_final["status"] == "done"

        replay_resp = client.post(
            f"/api/agent/tasks/{base_job_id}/replay",
            json={
                "payload_overrides": {
                    "input": {"target_duration_s": 22},
                },
                "context_overrides": {"trace_id": "tr_skill_replay_2"},
                "clear_idempotency": True,
            },
        )
        assert replay_resp.status_code == 200
        replay_payload = replay_resp.get_json()
        assert replay_payload["ok"] is True
        assert replay_payload["target"]["endpoint"] == "/api/agent/skills/invoke"
        assert replay_payload["request_payload"]["skill_id"] == "skill.text_rough_cut.plan"
        assert replay_payload["request_payload"]["input"]["target_duration_s"] == 22
        assert "idempotency_key" not in replay_payload["request_payload"]
        new_job_id = replay_payload.get("new_job_id", "")
        assert new_job_id

        replay_final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{new_job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            replay_final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert replay_final is not None
        assert replay_final["status"] == "done"
        assert replay_final["result"]["skill_id"] == "skill.text_rough_cut.plan"
        assert replay_final["result"]["response"]["ok"] is True
    finally:
        server._project_dir = old_project_dir


def test_agent_task_replay_from_history_when_memory_missing(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "capability_id": "refinement",
                "action": "plan",
                "input": {"style": "travel_story", "quality": "high"},
                "actor_type": "agent",
                "actor_id": "history_replay_bot",
                "trace_id": "tr_history_replay_1",
            },
        )
        assert run_resp.status_code == 200
        base_job_id = run_resp.get_json()["job_id"]

        final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{base_job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"

        history_path = data_dir / "agent_task_history.json"
        assert history_path.exists()
        history_data = json.loads(history_path.read_text(encoding="utf-8"))
        matched = [x for x in history_data if isinstance(x, dict) and x.get("job_id") == base_job_id]
        assert matched
        assert matched[-1].get("replay_supported") is True
        assert isinstance(matched[-1].get("replay"), dict)
        assert matched[-1]["replay"]["endpoint"] == "/api/agent/tasks/run"

        server._jobs.pop(base_job_id, None)
        replay_resp = client.post(
            f"/api/agent/tasks/{base_job_id}/replay",
            json={
                "payload_overrides": {
                    "input": {"style": "cinematic", "quality": "premium"},
                },
                "new_trace_id": "tr_history_replay_2",
            },
        )
        assert replay_resp.status_code == 200
        replay_payload = replay_resp.get_json()
        assert replay_payload["ok"] is True
        assert replay_payload["source"] == "history"
        assert replay_payload["target"]["endpoint"] == "/api/agent/tasks/run"
        assert replay_payload["request_payload"]["input"]["style"] == "cinematic"
        new_job_id = replay_payload.get("new_job_id", "")
        assert new_job_id

        replay_final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{new_job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            replay_final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert replay_final is not None
        assert replay_final["status"] == "done"
    finally:
        server._project_dir = old_project_dir


def test_agent_tasks_history_filters_and_pagination(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    history_path = data_dir / "agent_task_history.json"
    history_path.write_text(
        json.dumps(
            [
                {
                    "job_id": "job_a",
                    "kind": "agent_task",
                    "status": "done",
                    "task_mode": "single_capability",
                    "actor_id": "bot_a",
                    "trace_id": "trace_a",
                    "capability_ids": ["text_rough_cut"],
                    "skill_ids": [],
                    "replay_supported": True,
                    "started_at": "2026-02-25T10:00:00",
                    "finished_at": "2026-02-25T10:00:10",
                },
                {
                    "job_id": "job_b",
                    "kind": "agent_skill",
                    "status": "error",
                    "task_mode": "skill_invoke",
                    "actor_id": "bot_b",
                    "trace_id": "trace_b",
                    "capability_ids": ["topic_copy"],
                    "skill_ids": ["skill.topic_copy.draft"],
                    "replay_supported": False,
                    "started_at": "2026-02-25T10:01:00",
                    "finished_at": "2026-02-25T10:01:05",
                },
                {
                    "job_id": "job_c",
                    "kind": "agent_task",
                    "status": "done",
                    "task_mode": "skill_sequence",
                    "actor_id": "bot_a",
                    "trace_id": "trace_c",
                    "capability_ids": ["text_rough_cut", "short_clip"],
                    "skill_ids": ["skill.text_rough_cut.plan", "skill.short_clip.plan"],
                    "replay_supported": True,
                    "started_at": "2026-02-25T10:02:00",
                    "finished_at": "2026-02-25T10:02:30",
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    client = server.app.test_client()
    try:
        resp = client.get(
            "/api/agent/tasks/history"
            "?actor_id=bot_a"
            "&status=done"
            "&task_mode=skill_sequence"
            "&capability_id=short_clip"
            "&replay_supported=true"
            "&sort=asc"
            "&limit=10"
            "&offset=0"
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["total_count"] == 1
        assert payload["returned_count"] == 1
        assert payload["items"][0]["job_id"] == "job_c"
        assert payload["filters"]["replay_supported"] is True

        page_resp = client.get("/api/agent/tasks/history?sort=desc&limit=1&offset=0")
        assert page_resp.status_code == 200
        page_payload = page_resp.get_json()
        assert page_payload["ok"] is True
        assert page_payload["total_count"] == 3
        assert page_payload["returned_count"] == 1
        assert page_payload["has_more"] is True
        assert page_payload["items"][0]["job_id"] == "job_c"
    finally:
        server._project_dir = old_project_dir


def test_agent_task_status_fallback_to_history(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "agent_task_history.json").write_text(
        json.dumps(
            [
                {
                    "job_id": "hist_job_1",
                    "kind": "agent_task",
                    "status": "done",
                    "task_mode": "skill_sequence",
                    "actor_id": "hist_bot",
                    "capability_ids": ["text_rough_cut"],
                    "skill_ids": ["skill.text_rough_cut.plan"],
                    "total_steps": 2,
                    "success_steps": 2,
                    "failed_steps": 0,
                    "skipped_steps": 0,
                    "prompt_tokens": 100,
                    "completion_tokens": 60,
                    "total_tokens": 160,
                    "estimated_cost_usd": 0.0012,
                    "started_at": "2026-02-26T09:00:00",
                    "finished_at": "2026-02-26T09:00:12",
                    "error": "",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    client = server.app.test_client()
    try:
        resp = client.get("/api/agent/tasks/hist_job_1")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["source"] == "history"
        assert payload["status"] == "done"
        assert payload["result"]["history_summary"]["job_id"] == "hist_job_1"
        assert payload["chain_view"]["mode"] == "skill_sequence"
        assert payload["chain_view"]["counts"]["done"] == 2
    finally:
        server._project_dir = old_project_dir


def test_agent_task_export_from_memory_and_history(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "capability_id": "text_rough_cut",
                "input": {"target_duration_s": 12},
                "actor_type": "agent",
                "actor_id": "export_bot",
                "trace_id": "tr_export_1",
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        base_job_id = run_payload["job_id"]

        final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{base_job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"

        export_json_resp = client.post(
            f"/api/agent/tasks/{base_job_id}/export",
            json={"format": "json", "include_logs": True, "include_result": True},
        )
        assert export_json_resp.status_code == 200
        export_json_payload = export_json_resp.get_json()
        assert export_json_payload["ok"] is True
        assert export_json_payload["source"] in {"memory", "history"}
        json_path = Path(export_json_payload["output"])
        assert json_path.exists()
        exported = json.loads(json_path.read_text(encoding="utf-8"))
        assert exported["job_id"] == base_job_id
        assert exported["source"] in {"memory", "history"}
        assert isinstance(exported.get("summary"), dict)

        server._jobs.pop(base_job_id, None)
        export_csv_resp = client.post(
            f"/api/agent/tasks/{base_job_id}/export",
            json={"format": "csv"},
        )
        assert export_csv_resp.status_code == 200
        export_csv_payload = export_csv_resp.get_json()
        assert export_csv_payload["ok"] is True
        assert export_csv_payload["source"] == "history"
        csv_path = Path(export_csv_payload["output"])
        assert csv_path.exists()
        csv_text = csv_path.read_text(encoding="utf-8")
        assert "job_id,status,kind,task_mode" in csv_text
        assert base_job_id in csv_text
    finally:
        server._project_dir = old_project_dir


def test_agent_task_history_persists_step_summaries(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "mode": "skill_sequence",
                "strategy": "conditional",
                "skills": [
                    {"step_id": "s1", "skill_id": "skill.topic_library.search", "input": {"q": "海边"}},
                    {
                        "step_id": "s2",
                        "skill_id": "skill.topic_copy.draft",
                        "input": {},
                        "continue_on_error": True,
                        "condition": {"depends_on": ["s1"], "status_in": ["done"], "require_all": True},
                    },
                ],
                "actor_type": "agent",
                "actor_id": "history_step_summary_bot",
            },
        )
        assert run_resp.status_code == 200
        job_id = run_resp.get_json()["job_id"]

        final = None
        for _ in range(80):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None

        history_path = data_dir / "agent_task_history.json"
        history_data = json.loads(history_path.read_text(encoding="utf-8"))
        item = next(x for x in history_data if isinstance(x, dict) and x.get("job_id") == job_id)
        steps = item.get("step_summaries", [])
        assert isinstance(steps, list)
        assert len(steps) == 2
        assert steps[0]["step_id"] == "s1"
        assert "condition" in steps[1]
    finally:
        server._project_dir = old_project_dir


def test_agent_task_status_history_uses_step_summaries_for_edges(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "agent_task_history.json").write_text(
        json.dumps(
            [
                {
                    "job_id": "hist_job_edges",
                    "kind": "agent_task",
                    "status": "error",
                    "task_mode": "skill_sequence",
                    "strategy": "conditional",
                    "actor_id": "hist_bot",
                    "capability_ids": ["topic_library", "topic_copy"],
                    "skill_ids": ["skill.topic_library.search", "skill.topic_copy.draft"],
                    "total_steps": 2,
                    "success_steps": 1,
                    "failed_steps": 1,
                    "skipped_steps": 0,
                    "prompt_tokens": 88,
                    "completion_tokens": 24,
                    "total_tokens": 112,
                    "estimated_cost_usd": 0.0018,
                    "step_summaries": [
                        {
                            "step_id": "s1",
                            "index": 1,
                            "skill_id": "skill.topic_library.search",
                            "capability_id": "topic_library",
                            "status": "done",
                            "error": "",
                            "condition": {},
                        },
                        {
                            "step_id": "s2",
                            "index": 2,
                            "skill_id": "skill.topic_copy.draft",
                            "capability_id": "topic_copy",
                            "status": "error",
                            "error": "缺少 slug",
                            "condition": {"depends_on": ["s1"], "status_in": ["done"]},
                        },
                    ],
                    "failed_nodes": [
                        {"skill_id": "skill.topic_copy.draft", "capability_id": "topic_copy", "error": "缺少 slug"}
                    ],
                    "started_at": "2026-02-26T09:00:00",
                    "finished_at": "2026-02-26T09:00:12",
                    "error": "缺少 slug",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    client = server.app.test_client()
    try:
        resp = client.get("/api/agent/tasks/hist_job_edges")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["source"] == "history"
        assert payload["chain_view"]["node_count"] == 2
        assert payload["chain_view"]["counts"]["error"] == 1
        assert any(e.get("type") == "condition_depends_on" for e in payload["chain_view"]["edges"])
        err_nodes = [n for n in payload["chain_view"]["nodes"] if n.get("status") == "error"]
        assert err_nodes
        assert "缺少 slug" in str(err_nodes[0].get("error", ""))
    finally:
        server._project_dir = old_project_dir


def test_agent_task_plan_skill_sequence(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "mode": "skill_sequence",
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "海边日落"}},
                    {"skill_id": "skill.text_rough_cut.plan", "input": {"target_duration_s": 16}},
                ],
                "actor_type": "agent",
                "actor_id": "planner_seq_1",
            },
        )
        assert plan_resp.status_code == 200
        plan_payload = plan_resp.get_json()
        assert plan_payload["ok"] is True
        assert plan_payload["task_plan"]["mode"] == "skill_sequence"
        assert plan_payload["task_plan"]["skill_flow"]["strategy"] == "sequential"
        assert len(plan_payload["task_plan"]["skill_flow"]["steps"]) == 2
        assert plan_payload["plan_summary"]["total_steps"] == 2
    finally:
        server._project_dir = old_project_dir


def test_agent_task_plan_skill_sequence_parallel(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "mode": "skill_sequence",
                "strategy": "parallel",
                "max_parallel": 3,
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "雪山"}},
                    {"skill_id": "skill.topic_library.search", "input": {"q": "海边"}},
                ],
                "actor_type": "agent",
                "actor_id": "planner_seq_parallel_1",
            },
        )
        assert plan_resp.status_code == 200
        plan_payload = plan_resp.get_json()
        assert plan_payload["ok"] is True
        assert plan_payload["task_plan"]["mode"] == "skill_sequence"
        assert plan_payload["task_plan"]["skill_flow"]["strategy"] == "parallel"
        assert plan_payload["task_plan"]["skill_flow"]["max_parallel"] == 3
        assert plan_payload["plan_summary"]["strategy"] == "parallel"
    finally:
        server._project_dir = old_project_dir


def test_agent_task_plan_skill_sequence_conditional(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "mode": "skill_sequence",
                "strategy": "conditional",
                "skills": [
                    {"step_id": "s1", "skill_id": "skill.topic_library.search", "input": {"q": "海边"}},
                    {
                        "step_id": "s2",
                        "skill_id": "skill.topic_library.search",
                        "input": {"q": "雪山"},
                        "condition": {"depends_on": ["s1"], "status_in": ["done"], "require_all": True},
                    },
                ],
                "actor_type": "agent",
                "actor_id": "planner_conditional_1",
            },
        )
        assert plan_resp.status_code == 200
        plan_payload = plan_resp.get_json()
        assert plan_payload["ok"] is True
        assert plan_payload["task_plan"]["skill_flow"]["strategy"] == "conditional"
        assert plan_payload["plan_summary"]["strategy"] == "conditional"
        assert plan_payload["plan_summary"]["conditional_steps"] >= 1
    finally:
        server._project_dir = old_project_dir


def test_agent_task_run_skill_sequence_with_continue_on_error(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "mode": "skill_sequence",
                "skills": [
                    {
                        "step_id": "search_topic",
                        "skill_id": "skill.topic_library.search",
                        "input": {"q": "城市夜景"},
                    },
                    {
                        "step_id": "draft_copy",
                        "skill_id": "skill.topic_copy.draft",
                        "input": {},
                        "continue_on_error": True,
                    },
                ],
                "actor_type": "agent",
                "actor_id": "runner_seq_1",
                "trace_id": "tr_seq_run_1",
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True
        assert run_payload["mode"] == "skill_sequence"
        assert run_payload["total_steps"] == 2
        job_id = run_payload["job_id"]

        final = None
        for _ in range(60):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"
        assert final["kind"] == "agent_task"
        assert final["result"]["mode"] == "skill_sequence"
        assert final["result"]["total_steps"] == 2
        assert final["result"]["success_steps"] == 1
        assert final["result"]["failed_steps"] == 1
        assert final["result"]["overall_ok"] is False
        failed_step = next(x for x in final["result"]["steps"] if x["step_id"] == "draft_copy")
        assert failed_step["status"] == "error"
        assert failed_step["continue_on_error"] is True
        assert final["chain_view"]["mode"] == "skill_sequence"
        assert final["chain_view"]["node_count"] == 2
        assert final["chain_view"]["edge_count"] >= 1
        assert final["chain_view"]["counts"]["error"] == 1
    finally:
        server._project_dir = old_project_dir


def test_agent_task_run_skill_sequence_conditional(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "mode": "skill_sequence",
                "strategy": "conditional",
                "skills": [
                    {
                        "step_id": "draft_fail",
                        "skill_id": "skill.topic_copy.draft",
                        "input": {},
                        "continue_on_error": True,
                    },
                    {
                        "step_id": "skip_by_overall",
                        "skill_id": "skill.topic_library.search",
                        "input": {"q": "海边"},
                        "condition": {"if_overall_ok": True},
                    },
                    {
                        "step_id": "run_when_fail",
                        "skill_id": "skill.topic_library.search",
                        "input": {"q": "城市"},
                        "condition": {"depends_on": ["draft_fail"], "status_in": ["error"]},
                    },
                ],
                "actor_type": "agent",
                "actor_id": "runner_conditional_1",
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True
        assert run_payload["strategy"] == "conditional"
        job_id = run_payload["job_id"]

        final = None
        for _ in range(80):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"
        assert final["result"]["strategy"] == "conditional"
        assert final["result"]["success_steps"] == 1
        assert final["result"]["failed_steps"] == 1
        assert final["result"]["skipped_steps"] == 1
        skipped = next(x for x in final["result"]["steps"] if x["step_id"] == "skip_by_overall")
        assert skipped["status"] == "skipped"
        run_when_fail = next(x for x in final["result"]["steps"] if x["step_id"] == "run_when_fail")
        assert run_when_fail["status"] == "done"
        assert final["chain_view"]["mode"] == "skill_sequence"
        assert final["chain_view"]["node_count"] == 3
        assert final["chain_view"]["counts"]["skipped"] == 1
        assert any(e["type"] == "condition_depends_on" for e in final["chain_view"]["edges"])
    finally:
        server._project_dir = old_project_dir


def test_agent_task_run_skill_sequence_parallel_with_continue_on_error(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "mode": "skill_sequence",
                "strategy": "parallel",
                "max_parallel": 2,
                "skills": [
                    {
                        "step_id": "search_city",
                        "skill_id": "skill.topic_library.search",
                        "input": {"q": "城市"},
                    },
                    {
                        "step_id": "search_beach",
                        "skill_id": "skill.topic_library.search",
                        "input": {"q": "海边"},
                    },
                    {
                        "step_id": "draft_fail",
                        "skill_id": "skill.topic_copy.draft",
                        "input": {},
                        "continue_on_error": True,
                    },
                ],
                "actor_type": "agent",
                "actor_id": "runner_seq_parallel_1",
                "trace_id": "tr_seq_parallel_1",
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True
        assert run_payload["mode"] == "skill_sequence"
        assert run_payload["strategy"] == "parallel"
        assert run_payload["max_parallel"] == 2
        job_id = run_payload["job_id"]

        final = None
        for _ in range(80):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"
        assert final["result"]["strategy"] == "parallel"
        assert final["result"]["max_parallel"] == 2
        assert final["result"]["total_steps"] == 3
        assert final["result"]["success_steps"] == 2
        assert final["result"]["failed_steps"] == 1
        assert final["result"]["overall_ok"] is False
        draft_fail = next(x for x in final["result"]["steps"] if x["step_id"] == "draft_fail")
        assert draft_fail["status"] == "error"
        assert draft_fail["continue_on_error"] is True
        assert final["chain_view"]["mode"] == "skill_sequence"
        assert final["chain_view"]["node_count"] == 3
        assert final["chain_view"]["edge_count"] == 0
    finally:
        server._project_dir = old_project_dir


def test_agent_task_run_parallel_rejects_condition(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "mode": "skill_sequence",
                "strategy": "parallel",
                "skills": [
                    {
                        "step_id": "s1",
                        "skill_id": "skill.topic_library.search",
                        "input": {"q": "海边"},
                        "condition": {"if_overall_ok": True},
                    }
                ],
                "actor_type": "agent",
                "actor_id": "runner_parallel_condition_1",
            },
        )
        assert run_resp.status_code == 400
        assert "strategy=parallel" in str((run_resp.get_json() or {}).get("error", ""))
    finally:
        server._project_dir = old_project_dir


def test_agent_task_skill_sequence_budget_limit_max_steps(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "mode": "skill_sequence",
                "strategy": "parallel",
                "budget_limit": {"max_steps": 1},
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "城市"}},
                    {"skill_id": "skill.topic_library.search", "input": {"q": "海边"}},
                ],
                "actor_type": "agent",
                "actor_id": "budget_planner_1",
            },
        )
        assert plan_resp.status_code == 400
        assert "steps 超出预算上限" in str((plan_resp.get_json() or {}).get("error", ""))

        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "mode": "skill_sequence",
                "strategy": "parallel",
                "budget_limit": {"max_steps": 1},
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "城市"}},
                    {"skill_id": "skill.topic_library.search", "input": {"q": "海边"}},
                ],
                "actor_type": "agent",
                "actor_id": "budget_runner_1",
            },
        )
        assert run_resp.status_code == 400
        assert "steps 超出预算上限" in str((run_resp.get_json() or {}).get("error", ""))
    finally:
        server._project_dir = old_project_dir


def test_agent_task_plan_governance_actor_capability_limits(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    policy = {
        "default_limits": {"max_steps": 20, "max_failures": 8, "max_duration_seconds": 1200, "max_parallel": 6},
        "actor_limits": {
            "governed_bot": {"max_steps": 8, "max_parallel": 3},
        },
        "capability_limits": {
            "topic_library": {"max_steps": 5},
        },
        "actor_capability_limits": {
            "governed_bot": {
                "topic_library": {"max_steps": 2, "max_parallel": 2},
            }
        },
    }
    (data_dir / "agent_governance.json").write_text(
        json.dumps(policy, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    client = server.app.test_client()
    try:
        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "mode": "skill_sequence",
                "strategy": "parallel",
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "城市"}},
                    {"skill_id": "skill.topic_library.search", "input": {"q": "海边"}},
                ],
                "actor_type": "agent",
                "actor_id": "governed_bot",
            },
        )
        assert plan_resp.status_code == 200
        plan_payload = plan_resp.get_json()
        assert plan_payload["ok"] is True
        summary = plan_payload["plan_summary"]
        assert summary["budget_limit"]["max_steps"] == 2
        assert summary["max_parallel"] == 2
        assert "governance" in summary
        trace = summary["governance"]["limit_trace"]
        assert "actor_capability:governed_bot:topic_library" in str(trace.get("max_steps", ""))

        reject_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "mode": "skill_sequence",
                "strategy": "parallel",
                "max_parallel": 5,
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "城市"}},
                    {"skill_id": "skill.topic_library.search", "input": {"q": "海边"}},
                ],
                "actor_type": "agent",
                "actor_id": "governed_bot",
            },
        )
        assert reject_resp.status_code == 400
        assert "治理校验失败" in str((reject_resp.get_json() or {}).get("error", ""))
    finally:
        server._project_dir = old_project_dir


def test_agent_task_plan_governance_blocked_skill(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    policy = {
        "blocked_skills_by_actor": {
            "blocked_bot": ["skill.topic_library.search"],
        }
    }
    (data_dir / "agent_governance.json").write_text(
        json.dumps(policy, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    client = server.app.test_client()
    try:
        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "mode": "skill_sequence",
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "城市"}},
                ],
                "actor_type": "agent",
                "actor_id": "blocked_bot",
            },
        )
        assert plan_resp.status_code == 400
        assert "治理校验失败" in str((plan_resp.get_json() or {}).get("error", ""))
        assert "skill 被治理策略禁用" in str((plan_resp.get_json() or {}).get("error", ""))
    finally:
        server._project_dir = old_project_dir


def test_agent_task_run_writes_governance_usage(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "mode": "skill_sequence",
                "strategy": "sequential",
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "城市"}},
                ],
                "actor_type": "agent",
                "actor_id": "usage_bot_1",
            },
        )
        assert run_resp.status_code == 200
        job_id = run_resp.get_json()["job_id"]

        final = None
        for _ in range(60):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            payload = status_resp.get_json()
            final = payload
            if payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"
        usage_meta = final["result"]["governance_usage"]
        assert usage_meta["ok"] is True
        assert "summary_cost" in usage_meta
        assert final["chain_view"]["mode"] == "skill_sequence"
        assert final["chain_view"]["node_count"] == 1
        assert final["chain_view"]["counts"]["done"] == 1
        usage_file = data_dir / "agent_governance_usage.json"
        assert usage_file.exists()
        usage_data = json.loads(usage_file.read_text(encoding="utf-8"))
        actor_bucket = usage_data["actors"]["usage_bot_1"]
        assert actor_bucket["summary"]["run_count"] >= 1
        assert actor_bucket["summary"]["step_count"] >= 1
        assert "total_estimated_cost_usd" in actor_bucket["summary"]
        assert "total_tokens" in actor_bucket["summary"]
        assert isinstance(actor_bucket["summary"].get("recent_runs", []), list)
        assert len(actor_bucket["summary"].get("recent_runs", [])) >= 1
    finally:
        server._project_dir = old_project_dir


def test_agent_task_plan_applies_dynamic_usage_limits(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    usage_seed = {
        "version": 1,
        "updated_at": "2026-02-26T00:00:00",
        "actors": {
            "dynamic_bot": {
                "summary": {
                    "run_count": 5,
                    "step_count": 10,
                    "success_step_count": 7,
                    "failed_step_count": 3,
                    "skipped_step_count": 0,
                    "total_duration_seconds": 120.0,
                    "last_duration_seconds": 20.0,
                    "avg_duration_seconds": 24.0,
                    "last_run_at": "2026-02-26T00:00:00",
                    "suggested_limits": {
                        "max_steps": 1,
                        "max_failures": 1,
                        "max_duration_seconds": 60,
                        "max_parallel": 1,
                    },
                },
                "capabilities": {},
            }
        },
    }
    (data_dir / "agent_governance_usage.json").write_text(
        json.dumps(usage_seed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    client = server.app.test_client()
    try:
        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "mode": "skill_sequence",
                "strategy": "parallel",
                "skills": [
                    {"skill_id": "skill.topic_library.search", "input": {"q": "城市"}},
                    {"skill_id": "skill.topic_library.search", "input": {"q": "海边"}},
                ],
                "actor_type": "agent",
                "actor_id": "dynamic_bot",
            },
        )
        assert plan_resp.status_code == 400
        err = str((plan_resp.get_json() or {}).get("error", ""))
        assert "治理校验失败" in err
        assert "steps 超出预算上限" in err
    finally:
        server._project_dir = old_project_dir


def test_usage_bucket_auto_tuning_recent_window():
    bucket = {}
    bucket = server._update_usage_bucket(
        bucket,
        steps_total=6,
        steps_success=2,
        steps_failed=4,
        steps_skipped=0,
        duration_seconds=680.0,
        prompt_tokens=110000,
        completion_tokens=20000,
        estimated_cost_usd=0.42,
        now_iso="2026-02-26T10:00:00",
    )
    first_limits = bucket["suggested_limits"]
    assert first_limits["max_parallel"] == 1

    # 追加稳定成功窗口，验证建议额度会逐步放宽（仍会在治理应用层 tighten-only）。
    for idx in range(1, 9):
        bucket = server._update_usage_bucket(
            bucket,
            steps_total=3,
            steps_success=3,
            steps_failed=0,
            steps_skipped=0,
            duration_seconds=40.0,
            prompt_tokens=3000,
            completion_tokens=1500,
            estimated_cost_usd=0.008,
            now_iso=f"2026-02-26T10:0{idx}:00",
        )

    relaxed_limits = bucket["suggested_limits"]
    assert relaxed_limits["max_parallel"] >= 2
    assert relaxed_limits["max_steps"] >= first_limits["max_steps"]
    assert isinstance(bucket.get("recent_runs", []), list)
    assert len(bucket.get("recent_runs", [])) >= 9

    for i in range(20):
        bucket = server._update_usage_bucket(
            bucket,
            steps_total=1,
            steps_success=1,
            steps_failed=0,
            steps_skipped=0,
            duration_seconds=10.0,
            prompt_tokens=100,
            completion_tokens=50,
            estimated_cost_usd=0.0005,
            now_iso=f"2026-02-27T00:{i:02d}:00",
        )
    assert len(bucket.get("recent_runs", [])) == server._AGENT_USAGE_RECENT_RUNS_MAX


def test_agent_observability_summary_and_export(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    history_seed = [
        {
            "job_id": "job1",
            "kind": "agent_task",
            "status": "done",
            "task_mode": "skill_sequence",
            "strategy": "sequential",
            "actor_type": "agent",
            "actor_id": "obs_bot",
            "trace_id": "t1",
            "capability_ids": ["topic_library"],
            "skill_ids": ["skill.topic_library.search"],
            "total_steps": 1,
            "success_steps": 1,
            "failed_steps": 0,
            "skipped_steps": 0,
            "retry_count": 0,
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "estimated_cost_usd": 0.01,
            "duration_seconds": 12.0,
            "template_hits": ["text_rough_remove_fillers"],
            "template_hit_count": 1,
            "failed_nodes": [],
            "error": "",
            "started_at": "2026-02-26T10:00:00",
            "finished_at": "2026-02-26T10:00:12",
        },
        {
            "job_id": "job2",
            "kind": "agent_task",
            "status": "error",
            "task_mode": "skill_sequence",
            "strategy": "conditional",
            "actor_type": "agent",
            "actor_id": "obs_bot",
            "trace_id": "t2",
            "capability_ids": ["topic_copy"],
            "skill_ids": ["skill.topic_copy.draft"],
            "total_steps": 1,
            "success_steps": 0,
            "failed_steps": 1,
            "skipped_steps": 0,
            "retry_count": 2,
            "prompt_tokens": 800,
            "completion_tokens": 100,
            "total_tokens": 900,
            "estimated_cost_usd": 0.02,
            "duration_seconds": 9.0,
            "template_hits": [],
            "template_hit_count": 0,
            "failed_nodes": [{"skill_id": "skill.topic_copy.draft", "capability_id": "topic_copy", "error": "x"}],
            "error": "x",
            "started_at": "2026-02-26T10:01:00",
            "finished_at": "2026-02-26T10:01:09",
        },
        {
            "job_id": "job3",
            "kind": "agent_skill",
            "status": "done",
            "task_mode": "skill_invoke",
            "strategy": "",
            "actor_type": "agent",
            "actor_id": "obs_bot_2",
            "trace_id": "t3",
            "capability_ids": ["text_rough_cut"],
            "skill_ids": ["skill.text_rough_cut.plan"],
            "total_steps": 1,
            "success_steps": 1,
            "failed_steps": 0,
            "skipped_steps": 0,
            "retry_count": 1,
            "prompt_tokens": 200,
            "completion_tokens": 80,
            "total_tokens": 280,
            "estimated_cost_usd": 0.003,
            "duration_seconds": 4.0,
            "template_hits": ["topic_copy_travel_story"],
            "template_hit_count": 1,
            "failed_nodes": [],
            "error": "",
            "started_at": "2026-02-26T10:02:00",
            "finished_at": "2026-02-26T10:02:04",
        },
    ]
    (data_dir / "agent_task_history.json").write_text(
        json.dumps(history_seed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    client = server.app.test_client()
    try:
        summary_resp = client.get("/api/agent/observability?actor_id=obs_bot&include_items=true&limit=50&top_n=3")
        assert summary_resp.status_code == 200
        payload = summary_resp.get_json()
        assert payload["ok"] is True
        assert payload["actor_id"] == "obs_bot"
        assert payload["window_count"] == 2
        assert payload["summary"]["total_tasks"] == 2
        assert payload["summary"]["status_counts"]["done"] == 1
        assert payload["summary"]["status_counts"]["error"] == 1
        assert payload["summary"]["rates"]["retry_rate"] > 0
        assert len(payload["items"]) == 2

        filtered_resp = client.get(
            "/api/agent/observability"
            "?actor_id=obs_bot"
            "&status=error"
            "&task_mode=skill_sequence"
            "&capability_id=topic_copy"
            "&since=2026-02-26T10:00:30"
            "&until=2026-02-26T10:01:30"
            "&include_items=true"
            "&limit=50"
            "&top_n=3"
        )
        assert filtered_resp.status_code == 200
        filtered_payload = filtered_resp.get_json()
        assert filtered_payload["ok"] is True
        assert filtered_payload["history_count"] == 1
        assert filtered_payload["window_count"] == 1
        assert filtered_payload["summary"]["total_tasks"] == 1
        assert filtered_payload["summary"]["status_counts"]["error"] == 1
        assert filtered_payload["filters"]["status"] == ["error"]
        assert filtered_payload["items"][0]["job_id"] == "job2"

        export_json_resp = client.post(
            "/api/agent/observability/export",
            json={"actor_id": "obs_bot", "format": "json", "limit": 50},
        )
        assert export_json_resp.status_code == 200
        export_json_payload = export_json_resp.get_json()
        assert export_json_payload["ok"] is True
        assert export_json_payload["format"] == "json"
        json_path = Path(export_json_payload["output"])
        assert json_path.exists()
        json_export_data = json.loads(json_path.read_text(encoding="utf-8"))
        assert json_export_data["summary"]["total_tasks"] == 2

        export_csv_resp = client.post(
            "/api/agent/observability/export",
            json={"actor_id": "obs_bot", "format": "csv", "limit": 50},
        )
        assert export_csv_resp.status_code == 200
        export_csv_payload = export_csv_resp.get_json()
        assert export_csv_payload["ok"] is True
        assert export_csv_payload["format"] == "csv"
        csv_path = Path(export_csv_payload["output"])
        assert csv_path.exists()
        csv_text = csv_path.read_text(encoding="utf-8")
        assert "job_id,status,kind,task_mode" in csv_text
        assert "job1" in csv_text

        filtered_export_resp = client.post(
            "/api/agent/observability/export",
            json={
                "actor_id": "obs_bot",
                "format": "json",
                "limit": 50,
                "status": "error",
                "task_mode": "skill_sequence",
                "capability_id": "topic_copy",
                "since": "2026-02-26T10:00:30",
                "until": "2026-02-26T10:01:30",
            },
        )
        assert filtered_export_resp.status_code == 200
        filtered_export_payload = filtered_export_resp.get_json()
        assert filtered_export_payload["ok"] is True
        assert filtered_export_payload["window_count"] == 1
        filtered_json_path = Path(filtered_export_payload["output"])
        filtered_json_data = json.loads(filtered_json_path.read_text(encoding="utf-8"))
        assert filtered_json_data["window_count"] == 1
        assert filtered_json_data["summary"]["total_tasks"] == 1
        assert filtered_json_data["items"][0]["job_id"] == "job2"
    finally:
        server._project_dir = old_project_dir


def test_execute_agent_skill_uses_provider_model_cost_override(tmp_path):
    old_project_dir = server._project_dir
    old_invoke = server._invoke_agent_primary_call
    server._project_dir = tmp_path
    data_dir = (tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "agent_cost_model.json").write_text(
        json.dumps(
            {
                "default_rates": {
                    "prompt_usd_per_1k_tokens": 0.001,
                    "completion_usd_per_1k_tokens": 0.002,
                    "compute_usd_per_second": 0.0,
                },
                "providers": {
                    "openai": {
                        "default_rates": {
                            "prompt_usd_per_1k_tokens": 0.01,
                            "completion_usd_per_1k_tokens": 0.02,
                            "compute_usd_per_second": 0.0,
                        },
                        "models": {
                            "gpt-4o-mini": {
                                "prompt_usd_per_1k_tokens": 0.02,
                                "completion_usd_per_1k_tokens": 0.03,
                                "compute_usd_per_second": 0.0,
                            }
                        },
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def _fake_invoke_agent_primary_call(**kwargs):
        return {
            "status_code": 200,
            "data": {
                "ok": True,
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        }

    server._invoke_agent_primary_call = _fake_invoke_agent_primary_call
    try:
        result = server._execute_agent_skill(
            skill_id="skill.topic_library.search",
            input_payload={"q": "海边"},
            retry_policy={"max_retries": 0},
            timeout_seconds=10.0,
            request_context={},
        )
        assert result["status_code"] == 200
        assert result["pricing_hint"]["provider"] == "openai"
        assert result["pricing_hint"]["model"] == "gpt-4o-mini"
        estimated = result["estimated_cost"]
        assert estimated["rate_source"] == "provider:openai:model:gpt-4o-mini"
        assert abs(float(estimated["prompt_cost_usd"]) - 0.02) < 1e-9
        assert abs(float(estimated["completion_cost_usd"]) - 0.015) < 1e-9
        assert abs(float(estimated["total_cost_usd"]) - 0.035) < 1e-9
        assert float(estimated["rates"]["compute_usd_per_second"]) == 0.0
    finally:
        server._invoke_agent_primary_call = old_invoke
        server._project_dir = old_project_dir


def test_agent_templates_crud_and_readonly_guards(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        base_list = client.get("/api/agent/templates?actor_type=agent&actor_id=agent_bot_1")
        assert base_list.status_code == 200
        base_payload = base_list.get_json()
        assert base_payload["ok"] is True
        assert base_payload["count"] >= 3
        assert any(
            t.get("template_id") == "topic_copy_travel_story" and t.get("readonly") is True
            for t in base_payload["templates"]
        )

        upsert_resp = client.post(
            "/api/agent/templates",
            json={
                "template_id": "agent_rough_remove_fillers_v2",
                "name": "Agent粗剪去口头词v2",
                "capability_id": "text_rough_cut",
                "scope": "agent",
                "actor_type": "agent",
                "actor_id": "agent_bot_1",
                "tags": ["rough_cut", "agent"],
                "content": {
                    "target_duration_s": 12,
                    "removed_phrases": ["嗯", "啊", "然后", "就是", "这个"],
                },
            },
        )
        assert upsert_resp.status_code == 200
        upsert_payload = upsert_resp.get_json()
        assert upsert_payload["ok"] is True
        assert upsert_payload["template"]["template_id"] == "agent_rough_remove_fillers_v2"
        assert upsert_payload["template"]["scope"] == "agent"
        assert upsert_payload["template"]["actor_id"] == "agent_bot_1"

        listed_agent = client.get(
            "/api/agent/templates?scope=agent&actor_type=agent&actor_id=agent_bot_1"
        )
        assert listed_agent.status_code == 200
        listed_agent_payload = listed_agent.get_json()
        assert listed_agent_payload["ok"] is True
        assert listed_agent_payload["count"] == 1
        assert listed_agent_payload["templates"][0]["template_id"] == "agent_rough_remove_fillers_v2"
        assert listed_agent_payload["templates"][0]["readonly"] is False

        reject_system_upsert = client.post(
            "/api/agent/templates",
            json={
                "template_id": "topic_copy_travel_story",
                "name": "系统模板改写尝试",
                "scope": "system",
                "actor_type": "agent",
                "actor_id": "agent_bot_1",
            },
        )
        assert reject_system_upsert.status_code == 400
        assert "只读" in str((reject_system_upsert.get_json() or {}).get("error", ""))

        reject_system_delete = client.delete(
            "/api/agent/templates/topic_copy_travel_story?scope=system&actor_type=agent&actor_id=agent_bot_1"
        )
        assert reject_system_delete.status_code == 400
        assert "只读" in str((reject_system_delete.get_json() or {}).get("error", ""))

        delete_ok = client.delete(
            "/api/agent/templates/agent_rough_remove_fillers_v2?scope=agent&actor_type=agent&actor_id=agent_bot_1"
        )
        assert delete_ok.status_code == 200
        delete_payload = delete_ok.get_json()
        assert delete_payload["ok"] is True
        assert delete_payload["deleted"]["template_id"] == "agent_rough_remove_fillers_v2"

        listed_after_delete = client.get(
            "/api/agent/templates?scope=agent&actor_type=agent&actor_id=agent_bot_1"
        )
        assert listed_after_delete.status_code == 200
        listed_after_delete_payload = listed_after_delete.get_json()
        assert listed_after_delete_payload["ok"] is True
        assert listed_after_delete_payload["count"] == 0
    finally:
        server._project_dir = old_project_dir


def test_agent_templates_inheritance_and_variable_constraints(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        project_base = client.post(
            "/api/agent/templates",
            json={
                "template_id": "topic_copy_project_base",
                "name": "项目文案基模板",
                "scope": "project",
                "capability_id": "topic_copy",
                "content": {
                    "tone": "warm_real",
                    "hook_style": "story",
                    "target_duration_s": 60,
                },
                "variables": [
                    {
                        "key": "target_duration_s",
                        "type": "integer",
                        "required": True,
                        "minimum": 10,
                        "maximum": 180,
                    }
                ],
            },
        )
        assert project_base.status_code == 200
        assert project_base.get_json()["ok"] is True

        child = client.post(
            "/api/agent/templates",
            json={
                "template_id": "topic_copy_agent_variant",
                "name": "Agent文案变体",
                "scope": "agent",
                "capability_id": "topic_copy",
                "actor_type": "agent",
                "actor_id": "agent_bot_2",
                "base_template_id": "topic_copy_project_base",
                "content": {
                    "hook_style": "conflict",
                },
                "overrides": {
                    "target_duration_s": 45,
                },
            },
        )
        assert child.status_code == 200
        child_payload = child.get_json()
        assert child_payload["ok"] is True
        assert child_payload["template"]["base_template_id"] == "topic_copy_project_base"

        listed = client.get(
            "/api/agent/templates?scope=agent&actor_type=agent&actor_id=agent_bot_2&resolve=true"
        )
        assert listed.status_code == 200
        listed_payload = listed.get_json()
        assert listed_payload["ok"] is True
        assert listed_payload["count"] == 1
        item = listed_payload["templates"][0]
        assert item["template_id"] == "topic_copy_agent_variant"
        assert item["effective_content"]["tone"] == "warm_real"
        assert item["effective_content"]["hook_style"] == "conflict"
        assert item["effective_content"]["target_duration_s"] == 45
        assert item["resolve_warnings"] == []
        assert len(item["template_chain"]) >= 2

        bad_slot_value = client.post(
            "/api/agent/templates",
            json={
                "template_id": "topic_copy_bad_slot",
                "name": "非法变量值模板",
                "scope": "agent",
                "capability_id": "topic_copy",
                "actor_type": "agent",
                "actor_id": "agent_bot_2",
                "variables": [
                    {"key": "target_duration_s", "type": "integer", "minimum": 10, "maximum": 180}
                ],
                "content": {"target_duration_s": "fast"},
            },
        )
        assert bad_slot_value.status_code == 400
        assert "变量约束不满足" in str((bad_slot_value.get_json() or {}).get("error", ""))

        missing_required = client.post(
            "/api/agent/templates",
            json={
                "template_id": "topic_copy_required_missing",
                "name": "缺少必填变量模板",
                "scope": "agent",
                "capability_id": "topic_copy",
                "actor_type": "agent",
                "actor_id": "agent_bot_2",
                "variables": [
                    {"key": "opening_line", "type": "string", "required": True}
                ],
                "content": {},
            },
        )
        assert missing_required.status_code == 200

        listed_missing = client.get(
            "/api/agent/templates?scope=agent&actor_type=agent&actor_id=agent_bot_2&capability_id=topic_copy&resolve=true"
        )
        assert listed_missing.status_code == 200
        listed_missing_payload = listed_missing.get_json()
        assert listed_missing_payload["ok"] is True
        missing_item = next(
            x for x in listed_missing_payload["templates"] if x["template_id"] == "topic_copy_required_missing"
        )
        assert any("变量缺失(required)" in msg for msg in missing_item.get("resolve_warnings", []))
    finally:
        server._project_dir = old_project_dir


def test_legacy_topic_library_and_topic_copy_support_inline_mode_without_project():
    old_project_dir = server._project_dir
    server._project_dir = None
    client = server.app.test_client()
    try:
        upsert = client.post(
            "/api/capabilities/topic_library",
            json={"input_mode": "inline", "title": "城市漫步高光", "category": "travel", "tags": ["城市", "夜景"]},
        )
        assert upsert.status_code == 200
        upsert_payload = upsert.get_json()
        assert upsert_payload["ok"] is True
        assert upsert_payload["input_mode"] == "inline"
        topic = upsert_payload["topic"]

        listed = client.get(
            "/api/capabilities/topic_library?input_mode=inline&q=城市",
            json={"topics": [topic]},
        )
        assert listed.status_code == 200
        listed_payload = listed.get_json()
        assert listed_payload["ok"] is True
        assert listed_payload["input_mode"] == "inline"
        assert len(listed_payload["topics"]) == 1

        draft = client.post(
            "/api/capabilities/topic_copy/draft",
            json={
                "input_mode": "inline",
                "topic": topic,
                "target_duration_s": 45,
                "materials": {
                    "v1": {"semantic": {"setting": "城市街区", "activity": "漫步", "mood": "轻快"}},
                    "v2": {"semantic": {"setting": "地铁站", "activity": "转场", "mood": "节奏"}},
                },
            },
        )
        assert draft.status_code == 200
        draft_payload = draft.get_json()
        assert draft_payload["ok"] is True
        assert draft_payload["input_mode"] == "inline"
        assert draft_payload["draft"]["title"] == topic["title"]
    finally:
        server._project_dir = old_project_dir


def test_legacy_text_rough_and_short_clip_support_inline_mode_without_project():
    old_project_dir = server._project_dir
    server._project_dir = None
    client = server.app.test_client()
    try:
        source_resp = client.get(
            "/api/capabilities/text_rough_cut/source?input_mode=inline",
            json={
                "script": {
                    "subtitles": [
                        {"start_time": 0.0, "end_time": 1.0, "cn_text": "大家好"},
                        {"start_time": 1.1, "end_time": 2.0, "cn_text": "今天去徒步"},
                    ]
                }
            },
        )
        assert source_resp.status_code == 200
        source_payload = source_resp.get_json()
        assert source_payload["ok"] is True
        assert source_payload["input_mode"] == "inline"
        assert source_payload["total"] == 2

        rough_plan = client.post(
            "/api/capabilities/text_rough_cut/plan",
            json={
                "input_mode": "inline",
                "spans": source_payload["spans"],
                "target_duration_s": 1.2,
                "removed_phrases": ["嗯"],
            },
        )
        assert rough_plan.status_code == 200
        rough_payload = rough_plan.get_json()
        assert rough_payload["ok"] is True
        assert rough_payload["input_mode"] == "inline"
        assert rough_payload["plan"]["total_span_count"] == 2

        short_clip = client.post(
            "/api/capabilities/short_clip/plan",
            json={
                "input_mode": "inline",
                "script": {
                    "clips": [
                        {"source_start": 0.0, "source_end": 4.0, "highlight_score": 0.9, "has_face": True},
                        {"source_start": 4.0, "source_end": 8.0, "highlight_score": 0.8, "has_face": False},
                    ]
                },
                "target_duration_s": 5.0,
                "max_clips": 2,
            },
        )
        assert short_clip.status_code == 200
        short_payload = short_clip.get_json()
        assert short_payload["ok"] is True
        assert short_payload["input_mode"] == "inline"
        assert short_payload["plan"]["total_duration_s"] <= 5.1
    finally:
        server._project_dir = old_project_dir


def test_refinement_collect_master_supports_inline_mode_without_project(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = None
    client = server.app.test_client()
    source = tmp_path / "master_source.mp4"
    source.write_bytes(b"fake-video")
    target_dir = tmp_path / "collected"
    try:
        resp = client.post(
            "/api/capabilities/refinement/collect_master",
            json={
                "input_mode": "inline",
                "source_video": str(source),
                "output_dir": str(target_dir),
                "output_name": "final_inline.mp4",
                "copy_mode": "copy",
            },
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["input_mode"] == "inline"
        out_video = Path(payload["collect"]["output_video"])
        assert out_video.exists()
        assert out_video.name == "final_inline.mp4"
    finally:
        server._project_dir = old_project_dir


def test_social_export_and_audio_voice_support_inline_mode_without_project(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = None
    client = server.app.test_client()
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake")
    try:
        export_plan = client.post(
            "/api/capabilities/social_export/plan",
            json={
                "input_mode": "inline",
                "input_video": str(input_video),
                "output_dir": str(tmp_path / "exports"),
                "platforms": ["douyin", "thread", "微信号"],
                "strict_duration_limit": False,
            },
        )
        assert export_plan.status_code == 200
        export_payload = export_plan.get_json()
        assert export_payload["ok"] is True
        assert export_payload["input_mode"] == "inline"
        ids = [x["platform_id"] for x in export_payload["plan"]["jobs"]]
        assert ids == ["douyin", "threads", "wechat_channels"]

        audio_plan = client.post(
            "/api/capabilities/audio_voice/plan",
            json={
                "input_mode": "inline",
                "script": {
                    "clips": [{"duration": 2.0}, {"duration": 3.0}],
                    "subtitles": [{"cn_text": "你好，欢迎来到冰岛", "start_time": 0.0, "end_time": 1.5}],
                },
            },
        )
        assert audio_plan.status_code == 200
        audio_payload = audio_plan.get_json()
        assert audio_payload["ok"] is True
        assert audio_payload["input_mode"] == "inline"
        assert len(audio_payload["plan"]["voiceover_segments"]) == 1

        timeline_resp = client.post(
            "/api/capabilities/audio_voice/build_track",
            json={
                "input_mode": "inline",
                "dry_run": True,
                "segments": [
                    {"output_audio": str(tmp_path / "seg1.mp3"), "start": 0.5, "text": "A"},
                    {"output_audio": str(tmp_path / "seg2.mp3"), "start": 2.0, "text": "B"},
                ],
                "output_audio": str(tmp_path / "narration.m4a"),
            },
        )
        assert timeline_resp.status_code == 200
        timeline_payload = timeline_resp.get_json()
        assert timeline_payload["ok"] is True
        assert timeline_payload["input_mode"] == "inline"
        assert timeline_payload["timeline"]["status"] == "planned"
    finally:
        server._project_dir = old_project_dir


def test_agent_task_plan_and_run_default_to_inline_without_project():
    old_project_dir = server._project_dir
    server._project_dir = None
    client = server.app.test_client()
    try:
        plan_resp = client.post(
            "/api/agent/tasks/plan",
            json={
                "capability_id": "topic_copy",
                "input": {
                    "topic": {
                        "slug": "city_walk",
                        "title": "城市漫步高光",
                        "category": "travel",
                        "audience": "general",
                        "hook_style": "story",
                        "outline_template": "",
                        "tags": ["城市"],
                        "enabled": True,
                    },
                    "materials": {
                        "v1": {"semantic": {"setting": "城市街区", "activity": "漫步", "mood": "轻快"}},
                    },
                },
                "actor_type": "agent",
                "actor_id": "inline_agent_1",
            },
        )
        assert plan_resp.status_code == 200
        plan_payload = plan_resp.get_json()
        assert plan_payload["ok"] is True
        assert plan_payload["task_plan"]["primary_call"]["payload"]["input_mode"] == "inline"

        run_resp = client.post(
            "/api/agent/tasks/run",
            json={
                "capability_id": "topic_copy",
                "input": {
                    "topic": {
                        "slug": "city_walk",
                        "title": "城市漫步高光",
                        "category": "travel",
                        "audience": "general",
                        "hook_style": "story",
                        "outline_template": "",
                        "tags": ["城市"],
                        "enabled": True,
                    },
                    "materials": {
                        "v1": {"semantic": {"setting": "城市街区", "activity": "漫步", "mood": "轻快"}},
                    },
                },
                "actor_type": "agent",
                "actor_id": "inline_agent_1",
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True
        job_id = run_payload["job_id"]

        final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"
        assert final["result"]["response"]["input_mode"] == "inline"
    finally:
        server._project_dir = old_project_dir


def test_agent_skill_invoke_default_to_inline_without_project():
    old_project_dir = server._project_dir
    server._project_dir = None
    client = server.app.test_client()
    try:
        invoke_resp = client.post(
            "/api/agent/skills/invoke",
            json={
                "skill_id": "skill.topic_copy.draft",
                "input": {
                    "topic": {
                        "slug": "lake_walk",
                        "title": "湖边散步高光",
                        "category": "travel",
                        "audience": "general",
                        "hook_style": "story",
                        "outline_template": "",
                        "tags": ["湖边"],
                        "enabled": True,
                    },
                    "materials": {
                        "v1": {"semantic": {"setting": "湖边", "activity": "散步", "mood": "舒缓"}},
                    },
                },
                "actor_type": "agent",
                "actor_id": "inline_agent_2",
            },
        )
        assert invoke_resp.status_code == 200
        invoke_payload = invoke_resp.get_json()
        assert invoke_payload["ok"] is True
        job_id = invoke_payload["job_id"]

        final = None
        for _ in range(40):
            status_resp = client.get(f"/api/agent/tasks/{job_id}")
            assert status_resp.status_code == 200
            status_payload = status_resp.get_json()
            final = status_payload
            if status_payload["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.02)
        assert final is not None
        assert final["status"] == "done"
        assert final["result"]["response"]["input_mode"] == "inline"
        assert final["result"]["primary_call"]["payload"]["input_mode"] == "inline"
    finally:
        server._project_dir = old_project_dir
