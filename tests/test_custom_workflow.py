import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


fake_library_mod = types.ModuleType("modules.library.global_media_library")


class _FakeGlobalMediaLibrary:
    def __init__(self, *args, **kwargs):
        self.db_path = ROOT / ".tmp_fake_library_workflow.db"


fake_library_mod.GlobalMediaLibrary = _FakeGlobalMediaLibrary
sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

from modules.app_api import server  # noqa: E402


def _wait_job_done(client, job_id: str, attempts: int = 120, sleep_s: float = 0.02):
    final = None
    for _ in range(attempts):
        resp = client.get(f"/api/job/{job_id}")
        assert resp.status_code == 200
        payload = resp.get_json()
        final = payload
        if payload["status"] in {"done", "error", "cancelled"}:
            break
        time.sleep(sleep_s)
    assert final is not None
    return final


def test_custom_workflow_catalog_and_crud(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._custom_workflow_lock:
        server._custom_workflow_store_mem.clear()
        server._custom_workflow_runs_mem.clear()

    client = server.app.test_client()
    try:
        catalog_resp = client.get("/api/workflows/catalog")
        assert catalog_resp.status_code == 200
        catalog_payload = catalog_resp.get_json()
        assert catalog_payload["ok"] is True
        ids = {x.get("capability_id") for x in catalog_payload.get("catalog", [])}
        assert "subtitle_calibration" in ids
        assert "article_expand" in ids

        upsert_resp = client.post(
            "/api/workflows",
            json={
                "workflow_id": "wf_subtitle_article",
                "name": "字幕到文章",
                "description": "先做字幕校准，再做文章扩写",
                "start_step_id": "subtitle_run",
                "steps": [
                    {
                        "step_id": "subtitle_run",
                        "capability_id": "subtitle_calibration",
                        "action": "run",
                        "input": {
                            "input_mode": "inline",
                            "mode": "text_only",
                            "translation": "off",
                            "subtitles": [
                                {"index": 1, "start_time": 0.0, "end_time": 1.2, "cn_text": "第一句"},
                                {"index": 2, "start_time": 1.3, "end_time": 2.5, "cn_text": "第二句"},
                            ],
                        },
                    }
                ],
            },
        )
        assert upsert_resp.status_code == 200
        upsert_payload = upsert_resp.get_json()
        assert upsert_payload["ok"] is True
        assert upsert_payload["workflow"]["workflow_id"] == "wf_subtitle_article"
        assert upsert_payload["workflow"]["start_step_id"] == "subtitle_run"

        list_resp = client.get("/api/workflows")
        assert list_resp.status_code == 200
        list_payload = list_resp.get_json()
        assert list_payload["ok"] is True
        by_id = {x.get("workflow_id"): x for x in list_payload.get("workflows", [])}
        assert "wf_subtitle_article" in by_id
        assert by_id["wf_subtitle_article"]["name"] == "字幕到文章"
        assert by_id["wf_subtitle_article"]["start_step_id"] == "subtitle_run"

        delete_resp = client.delete("/api/workflows/wf_subtitle_article")
        assert delete_resp.status_code == 200
        delete_payload = delete_resp.get_json()
        assert delete_payload["ok"] is True
        assert delete_payload["deleted"]["workflow_id"] == "wf_subtitle_article"
    finally:
        server._project_dir = old_project_dir


def test_custom_workflow_run_supports_step_template_chaining(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._custom_workflow_lock:
        server._custom_workflow_store_mem.clear()
        server._custom_workflow_runs_mem.clear()

    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/workflows/run",
            json={
                "dry_run": True,
                "workflow": {
                    "workflow_id": "wf_chain_inline",
                    "name": "链路编排示例",
                    "steps": [
                        {
                            "step_id": "step_sub",
                            "capability_id": "subtitle_calibration",
                            "action": "run",
                            "input": {
                                "input_mode": "inline",
                                "mode": "text_only",
                                "translation": "off",
                                "subtitles": [
                                    {"index": 1, "start_time": 0.0, "end_time": 1.0, "cn_text": "字幕A"},
                                    {"index": 2, "start_time": 1.1, "end_time": 2.1, "cn_text": "字幕B"},
                                ],
                            },
                        },
                        {
                            "step_id": "step_article",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "字幕总数={{steps.step_sub.response.result.quality_report.total_subtitles}}",
                                "key_points": "强调工作流顺序执行",
                                "length_target": 500,
                                "title_count": 3,
                            },
                        },
                    ],
                },
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True
        job_id = run_payload["job_id"]

        final = _wait_job_done(client, job_id)
        assert final["status"] == "done"
        run_result = final["result"]["run"]
        assert run_result["status"] == "done"
        assert run_result["summary"]["total_steps"] == 2
        assert run_result["summary"]["success_steps"] == 2
        second_step = run_result["steps"][1]
        assert second_step["status"] == "done"
        assert "字幕总数=2" in second_step["request_payload"]["source_text"]
    finally:
        server._project_dir = old_project_dir


def test_custom_workflow_continue_on_error_and_rerun_failed_only(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._custom_workflow_lock:
        server._custom_workflow_store_mem.clear()
        server._custom_workflow_runs_mem.clear()

    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/workflows/run",
            json={
                "dry_run": True,
                "workflow": {
                    "workflow_id": "wf_continue_on_error",
                    "name": "失败继续",
                    "steps": [
                        {
                            "step_id": "bad_subtitle",
                            "capability_id": "subtitle_calibration",
                            "action": "run",
                            "continue_on_error": True,
                            "input": {
                                "input_mode": "inline",
                                "mode": "timeline_align",
                                "translation": "off",
                            },
                        },
                        {
                            "step_id": "article_ok",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "继续执行第二步",
                                "key_points": "验证 continue_on_error",
                                "length_target": 300,
                                "title_count": 2,
                            },
                        },
                    ],
                },
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True

        first_final = _wait_job_done(client, run_payload["job_id"])
        assert first_final["status"] == "done"
        first_run = first_final["result"]["run"]
        assert first_run["summary"]["failed_steps"] == 1
        assert first_run["summary"]["success_steps"] == 1
        assert first_run["status"] == "partial"
        first_run_id = first_run["run_id"]

        rerun_resp = client.post(
            f"/api/workflows/runs/{first_run_id}/rerun",
            json={"dry_run": True, "rerun_failed_only": True},
        )
        assert rerun_resp.status_code == 200
        rerun_payload = rerun_resp.get_json()
        assert rerun_payload["ok"] is True

        second_final = _wait_job_done(client, rerun_payload["job_id"])
        assert second_final["status"] == "done"
        second_run = second_final["result"]["run"]
        assert second_run["plan"]["total_steps"] == 1
        assert second_run["plan"]["steps"][0]["step_id"] == "bad_subtitle"

        history_resp = client.get("/api/workflows/runs?limit=10")
        assert history_resp.status_code == 200
        history_payload = history_resp.get_json()
        assert history_payload["ok"] is True
        assert history_payload["total_count"] >= 2
    finally:
        server._project_dir = old_project_dir


def test_custom_workflow_condition_branch_and_error_route(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._custom_workflow_lock:
        server._custom_workflow_store_mem.clear()
        server._custom_workflow_runs_mem.clear()

    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/workflows/run",
            json={
                "dry_run": True,
                "input": {"use_fast_path": True},
                "workflow": {
                    "workflow_id": "wf_branch_graph",
                    "name": "条件分支与错误分支",
                    "steps": [
                        {
                            "step_id": "step_decide",
                            "node_type": "condition",
                            "condition": "{{input.use_fast_path}}",
                            "next_on_success": "step_fast",
                            "next_on_error": "step_slow",
                        },
                        {
                            "step_id": "step_fast",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "next_step_id": "step_bad",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "FAST_PATH",
                                "key_points": "走快速分支",
                                "length_target": 200,
                                "title_count": 2,
                            },
                        },
                        {
                            "step_id": "step_slow",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "next_step_id": "step_bad",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "SLOW_PATH",
                                "key_points": "走慢速分支",
                                "length_target": 200,
                                "title_count": 2,
                            },
                        },
                        {
                            "step_id": "step_bad",
                            "capability_id": "subtitle_calibration",
                            "action": "run",
                            "continue_on_error": False,
                            "next_on_error": "step_recover",
                            "input": {
                                "input_mode": "inline",
                                "mode": "timeline_align",
                                "translation": "off",
                            },
                        },
                        {
                            "step_id": "step_recover",
                            "capability_id": "publish_prep",
                            "action": "generate",
                            "input": {
                                "input_mode": "inline",
                                "platforms": ["douyin"],
                                "script_text": "恢复分支执行",
                                "voiceover_text": "继续后续节点",
                            },
                        },
                    ],
                },
            },
        )
        assert run_resp.status_code == 200
        payload = run_resp.get_json()
        assert payload["ok"] is True

        final = _wait_job_done(client, payload["job_id"])
        assert final["status"] == "done"
        run = final["result"]["run"]
        path = run.get("execution_path", [])
        assert path[0] == "step_decide"
        assert "step_fast" in path
        assert "step_slow" not in path
        assert "step_bad" in path
        assert "step_recover" in path
        statuses = {x.get("step_id"): x.get("status") for x in run.get("steps", [])}
        assert statuses["step_slow"] == "unreached"
        assert statuses["step_bad"] == "error"
        assert statuses["step_recover"] == "done"
        assert run["summary"]["failed_steps"] == 1
        assert run["summary"]["success_steps"] >= 3
        assert run["status"] == "partial"
    finally:
        server._project_dir = old_project_dir


def test_custom_workflow_start_step_id_override(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._custom_workflow_lock:
        server._custom_workflow_store_mem.clear()
        server._custom_workflow_runs_mem.clear()

    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/workflows/run",
            json={
                "dry_run": True,
                "start_step_id": "step_second",
                "workflow": {
                    "workflow_id": "wf_start_override",
                    "name": "入口节点覆盖",
                    "steps": [
                        {
                            "step_id": "step_first",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "FIRST",
                                "key_points": "first",
                                "length_target": 200,
                                "title_count": 2,
                            },
                        },
                        {
                            "step_id": "step_second",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "SECOND",
                                "key_points": "second",
                                "length_target": 200,
                                "title_count": 2,
                            },
                        },
                    ],
                },
            },
        )
        assert run_resp.status_code == 200
        payload = run_resp.get_json()
        assert payload["ok"] is True

        final = _wait_job_done(client, payload["job_id"])
        assert final["status"] == "done"
        run = final["result"]["run"]
        assert run["plan"]["start_step_id"] == "step_second"
        assert run["execution_path"] == ["step_second"]
        statuses = {x.get("step_id"): x.get("status") for x in run.get("steps", [])}
        assert statuses["step_second"] == "done"
        assert statuses["step_first"] == "unreached"
    finally:
        server._project_dir = old_project_dir


def test_custom_workflow_plan_contains_graph_summary(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._custom_workflow_lock:
        server._custom_workflow_store_mem.clear()
        server._custom_workflow_runs_mem.clear()

    client = server.app.test_client()
    try:
        resp = client.post(
            "/api/workflows/plan",
            json={
                "dry_run": True,
                "start_step_id": "step_decide",
                "workflow": {
                    "workflow_id": "wf_graph_plan",
                    "name": "图摘要测试",
                    "steps": [
                        {
                            "step_id": "step_decide",
                            "node_type": "condition",
                            "condition": "{{input.use_fast}}",
                            "next_on_success": "step_fast",
                            "next_on_error": "step_slow",
                        },
                        {
                            "step_id": "step_fast",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "next_step_id": "step_end",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "FAST",
                                "key_points": "fast",
                                "length_target": 200,
                                "title_count": 2,
                            },
                        },
                        {
                            "step_id": "step_slow",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "next_step_id": "step_end",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "SLOW",
                                "key_points": "slow",
                                "length_target": 200,
                                "title_count": 2,
                            },
                        },
                        {
                            "step_id": "step_end",
                            "capability_id": "publish_prep",
                            "action": "generate",
                            "input": {
                                "input_mode": "inline",
                                "platforms": ["douyin"],
                                "script_text": "END",
                                "voiceover_text": "END",
                            },
                        },
                    ],
                },
            },
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        graph = payload["plan"]["graph"]
        assert graph["start_step_id"] == "step_decide"
        assert graph["requested_start_step_id"] == "step_decide"
        assert graph["node_count"] == 4
        assert graph["edge_count"] >= 4
        assert graph["has_cycle"] is False
        edge_rows = {(x.get("from"), x.get("to"), x.get("when")) for x in graph.get("edges", [])}
        assert ("step_decide", "step_fast", "condition_true") in edge_rows
        assert ("step_decide", "step_slow", "condition_false") in edge_rows
        assert ("step_fast", "step_end", "success") in edge_rows
        assert ("step_slow", "step_end", "success") in edge_rows

        plan_summary = payload.get("plan_summary", {})
        assert plan_summary.get("start_step_id") == "step_decide"
        assert plan_summary.get("edge_count", 0) >= 4
    finally:
        server._project_dir = old_project_dir


def test_custom_workflow_rerun_failed_only_includes_ancestor_chain(tmp_path):
    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    with server._custom_workflow_lock:
        server._custom_workflow_store_mem.clear()
        server._custom_workflow_runs_mem.clear()

    client = server.app.test_client()
    try:
        run_resp = client.post(
            "/api/workflows/run",
            json={
                "dry_run": True,
                "input": {"use_fast_path": True},
                "workflow": {
                    "workflow_id": "wf_rerun_dep_chain",
                    "name": "重跑依赖链路",
                    "steps": [
                        {
                            "step_id": "step_decide",
                            "node_type": "condition",
                            "condition": "{{input.use_fast_path}}",
                            "next_on_success": "step_bad",
                            "next_on_error": "step_safe",
                        },
                        {
                            "step_id": "step_bad",
                            "capability_id": "subtitle_calibration",
                            "action": "run",
                            "continue_on_error": True,
                            "next_on_error": "step_tail",
                            "input": {
                                "input_mode": "inline",
                                "mode": "timeline_align",
                                "translation": "off",
                            },
                        },
                        {
                            "step_id": "step_safe",
                            "capability_id": "article_expand",
                            "action": "generate",
                            "input": {
                                "input_mode": "inline",
                                "source_text": "SAFE_PATH",
                                "key_points": "safe",
                                "length_target": 200,
                                "title_count": 2,
                            },
                        },
                        {
                            "step_id": "step_tail",
                            "capability_id": "publish_prep",
                            "action": "generate",
                            "input": {
                                "input_mode": "inline",
                                "platforms": ["douyin"],
                                "script_text": "TAIL",
                                "voiceover_text": "TAIL",
                            },
                        },
                    ],
                },
            },
        )
        assert run_resp.status_code == 200
        run_payload = run_resp.get_json()
        assert run_payload["ok"] is True

        first_final = _wait_job_done(client, run_payload["job_id"])
        assert first_final["status"] == "done"
        first_run = first_final["result"]["run"]
        assert first_run["status"] == "partial"
        statuses = {x.get("step_id"): x.get("status") for x in first_run.get("steps", [])}
        assert statuses["step_bad"] == "error"
        assert statuses["step_tail"] == "done"
        source_run_id = first_run["run_id"]

        rerun_resp = client.post(
            f"/api/workflows/runs/{source_run_id}/rerun",
            json={"dry_run": True, "rerun_failed_only": True},
        )
        assert rerun_resp.status_code == 200
        rerun_payload = rerun_resp.get_json()
        assert rerun_payload["ok"] is True

        rerun_final = _wait_job_done(client, rerun_payload["job_id"])
        assert rerun_final["status"] == "done"
        rerun_run = rerun_final["result"]["run"]
        rerun_step_ids = [x.get("step_id") for x in rerun_run["plan"]["steps"]]
        assert rerun_step_ids == ["step_decide", "step_bad"]
        assert rerun_run["plan"]["start_step_id"] == "step_decide"
        rerun_ctx = rerun_run.get("rerun_context", {})
        assert rerun_ctx.get("mode") == "failed_with_dependencies"
        assert rerun_ctx.get("source_run_id") == source_run_id
        assert rerun_ctx.get("failed_step_ids") == ["step_bad"]
        assert rerun_ctx.get("included_step_ids") == ["step_decide", "step_bad"]
        assert rerun_payload.get("rerun_context", {}).get("mode") == "failed_with_dependencies"
    finally:
        server._project_dir = old_project_dir
