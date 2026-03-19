#!/usr/bin/env python3
"""
Flask API 服务器 —— 为 pywebview GUI 提供后端接口

端点:
  GET  /api/status               → 当前 workflow 状态
  GET  /api/system/load          → 系统负载与运行任务
  GET  /api/system/preflight     → 启动前自检/诊断报告
  GET  /api/settings/ai          → 读取 AI 配置
  POST /api/settings/ai          → 保存 AI 配置
  GET  /api/settings/ui          → 读取 UI/引导配置
  POST /api/settings/ui          → 保存 UI/引导配置
  GET  /api/settings/publish     → 读取发布连接器配置
  POST /api/settings/publish     → 保存发布连接器配置
  GET  /api/session/bootstrap    → 获取本地 API 会话 token
  POST /api/library/preview/local/images → 预览本地图片目录
  POST /api/library/ingest/local/images  → 异步分析本地图片语义并入库
  POST /api/init                 → 初始化新项目
  POST /api/open_project         → 打开已有项目
  POST /api/approve/<int:step>   → 审核通过某步骤（含表单数据）
  POST /api/run_step             → 后台运行当前步骤（返回 job_id）
  GET  /api/job/<job_id>         → 轮询后台任务状态
  POST /api/job/<job_id>/cancel  → 取消后台任务
  GET  /api/files/<path:rel>     → 提供项目文件（视频/图片）
  GET  /api/frames               → 列出帧预览图片
  GET  /api/stage_files          → 列出 Step 7 各 stage 文件存在情况
  GET  /api/capabilities         → 能力模块注册信息
  GET  /api/capabilities/idempotency/cache
  POST /api/capabilities/idempotency/cache/prune
  GET/POST /api/capabilities/topic_library
  POST /api/capabilities/topic_library/bootstrap
  POST /api/capabilities/topic_copy/draft
  GET  /api/capabilities/text_rough_cut/source
  POST /api/capabilities/text_rough_cut/plan
  POST /api/capabilities/short_clip/plan
  POST /api/capabilities/refinement/plan
  POST /api/capabilities/refinement/handoff
  POST /api/capabilities/refinement/execute
  POST /api/capabilities/refinement/collect_master
  GET  /api/capabilities/refinement/connectors
  GET/POST /api/capabilities/publish_prep/profiles
  POST /api/capabilities/publish_prep/generate
  POST /api/capabilities/subtitle_calibration/plan
  POST /api/capabilities/subtitle_calibration/run
  POST /api/capabilities/image_semantic/analyze
  POST /api/capabilities/image_semantic/search
  POST /api/capabilities/article_expand/generate
  GET  /api/capabilities/content_publish/platforms
  POST /api/capabilities/content_publish/session/bootstrap
  POST /api/capabilities/content_publish/plan
  POST /api/capabilities/content_publish/run
  POST /api/capabilities/content_publish/rerun
  GET  /api/capabilities/social_export/profiles
  GET  /api/capabilities/social_export/specs
  GET/POST /api/capabilities/social_export/templates
  DELETE /api/capabilities/social_export/templates/<template_id>
  GET  /api/capabilities/social_export/history
  POST /api/capabilities/social_export/validate_source
  POST /api/capabilities/social_export/plan
  POST /api/capabilities/social_export/run
  POST /api/capabilities/social_export/rerun
  POST /api/capabilities/audio_voice/plan
  POST /api/capabilities/audio_voice/pick_bgm
  POST /api/capabilities/audio_voice/synthesize
  POST /api/capabilities/audio_voice/build_track
  POST /api/capabilities/audio_voice/mix_master
  POST /api/capabilities/audio_voice/run
  GET  /api/agent/capabilities
  POST /api/agent/tasks/plan
  POST /api/agent/tasks/run
  GET  /api/agent/tasks/<job_id>
  GET  /api/agent/tasks/history
  POST /api/agent/tasks/<job_id>/export
  POST /api/agent/tasks/<job_id>/replay
  GET  /api/agent/observability
  POST /api/agent/observability/export
  GET/POST /api/agent/templates
  DELETE /api/agent/templates/<template_id>
  POST /api/agent/skills/invoke
  GET  /api/workflows/catalog
  GET/POST /api/workflows
  DELETE /api/workflows/<workflow_id>
  POST /api/workflows/plan
  POST /api/workflows/run
  GET  /api/workflows/runs
  GET  /api/workflows/runs/<run_id>
  POST /api/workflows/runs/<run_id>/rerun
  POST /api/open_in_finder       → 在 Finder 中打开文件/目录
  POST /api/dialog/folder        → 触发 pywebview 文件夹选择对话框
  POST /api/dialog/file          → 触发 pywebview 文件选择对话框
"""

import sys
import os
import json
import re
import csv
import io
import uuid
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import subprocess
import logging
import traceback
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_UI_DIR = Path(os.environ.get("VIDEOEDITOR_UI_DIR", "")) if os.environ.get("VIDEOEDITOR_UI_DIR") else REPO_ROOT / "apps" / "desktop" / "ui-vue" / "dist"

from flask import Flask, jsonify, request, send_file, abort
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from modules.app_api.job_store import JobStore
from modules.app_api.publish_prep_api import create_publish_prep_blueprint
from modules.app_api.secure_store import build_secret_store, SecretStore
from modules.app_api.services.idempotency_store import CapabilityIdempotencyStore
from modules.app_api.services.job_runtime import JobRuntime, ManagedJob as _ManagedJob, ManagedJobLog as _ManagedJobLog
from modules.app_api.services.preflight_service import run_startup_preflight
from modules.app_api.routes.agent_template_routes import create_agent_template_blueprint
from modules.app_api.routes.agent_capability_routes import create_agent_capability_blueprint
from modules.app_api.routes.agent_observability_routes import create_agent_observability_blueprint
from modules.app_api.routes.agent_skill_routes import create_agent_skill_blueprint
from modules.app_api.routes.agent_task_query_routes import create_agent_task_query_blueprint
from modules.app_api.routes.agent_task_run_routes import create_agent_task_run_blueprint
from modules.app_api.routes.capability_audio_voice_routes import create_audio_voice_capability_blueprint
from modules.app_api.routes.capability_content_publish_routes import create_content_publish_capability_blueprint
from modules.app_api.routes.capability_editing_routes import create_editing_capability_blueprint
from modules.app_api.routes.capability_social_export_routes import create_social_export_capability_blueprint
from modules.app_api.routes.capability_text_semantic_routes import create_text_semantic_capability_blueprint
from modules.app_api.routes.idempotency_routes import create_idempotency_blueprint
from modules.app_api.routes.job_routes import create_job_blueprint
from modules.app_api.routes.legacy_project_routes import create_legacy_project_blueprint
from modules.app_api.routes.library_routes import create_library_blueprint
from modules.app_api.routes.settings_routes import create_settings_blueprint
from modules.app_api.routes.system_routes import create_system_blueprint
from modules.app_api.routes.timeline_routes import create_timeline_blueprint
from modules.app_api.routes.ui_routes import create_ui_blueprint
from modules.app_api.routes.workflow_routes import create_workflow_blueprint
from modules.workflow_engine.workflow import WorkflowState, WorkflowRunner
from modules.library.global_media_library import GlobalMediaLibrary
from modules.step2_topic_planning.ai_client import AIClient

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=None)
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = max(
    int(os.environ.get("VIDEOEDITOR_MAX_REQUEST_BYTES", str(25 * 1024 * 1024)) or (25 * 1024 * 1024)),
    1024 * 1024,
)

_REQUIRE_LOCAL_API_TOKEN = str(os.environ.get("VIDEOEDITOR_REQUIRE_LOCAL_TOKEN", "0") or "0").strip() == "1"
_LOCAL_API_TOKEN = str(os.environ.get("VIDEOEDITOR_LOCAL_API_TOKEN", "") or uuid.uuid4().hex).strip()
_LOCAL_CSRF_TOKEN = str(os.environ.get("VIDEOEDITOR_LOCAL_CSRF_TOKEN", "") or uuid.uuid4().hex).strip()
_REQUIRE_CSRF_PROTECTION = str(os.environ.get("VIDEOEDITOR_REQUIRE_CSRF", "1") or "1").strip() != "0"

# ── 全局状态 ────────────────────────────────────────────────────────
_project_dir: Optional[Path] = None
_ws: Optional[WorkflowState] = None
_jobs: Dict[str, dict] = {}      # job_id → {status, log, progress}
_window = None                    # pywebview window（由 app.py 注入）
_library = GlobalMediaLibrary()
_secret_store: SecretStore = build_secret_store(service_name="videoeditor.ai")
_job_store: Optional[JobStore] = None
_job_store_path: Optional[Path] = None

# kind → rerun/run endpoint for recovery hints
_RETRY_HINT_MAP: Dict[str, Optional[str]] = {
    "social_export": "/api/capabilities/social_export/rerun",
    "custom_workflow": "/api/workflows/runs/{run_id}/rerun",
    "library_ingest_local": "/api/library/ingest/local",
    "library_ingest_local_images": "/api/library/ingest/local/images",
    "library_ingest_gdrive": "/api/library/ingest/gdrive",
    "library_ingest_gdrive_images": "/api/library/ingest/gdrive",
    "content_publish": "/api/capabilities/content_publish/rerun",
    "audio_voice": None,
    "workflow_step": None,
}

app.register_blueprint(
    create_publish_prep_blueprint(
        project_dir_getter=lambda: _project_dir,
        ai_settings_getter=lambda: _load_ai_settings(),
    )
)
app.register_blueprint(
    create_settings_blueprint(
        request_is_local=lambda: _request_is_local(),
        require_local_token_getter=lambda: bool(_REQUIRE_LOCAL_API_TOKEN),
        require_csrf_getter=lambda: bool(_REQUIRE_CSRF_PROTECTION and _REQUIRE_LOCAL_API_TOKEN),
        local_token_getter=lambda: _LOCAL_API_TOKEN,
        local_csrf_token_getter=lambda: _LOCAL_CSRF_TOKEN,
        load_ai_settings=lambda: _load_ai_settings(),
        save_ai_settings=lambda payload: _save_ai_settings(payload),
        apply_ai_env=lambda payload: _apply_ai_env(payload),
        public_ai_settings=lambda payload: _public_ai_settings(payload),
        load_ui_settings=lambda: _load_ui_settings(),
        save_ui_settings=lambda payload: _save_ui_settings(payload),
        load_publish_settings=lambda: _load_publish_settings(),
        save_publish_settings=lambda payload: _save_publish_settings(payload),
        mask_publish_connectors=lambda payload: _mask_publish_connectors(payload),
        secret_store_getter=lambda: _secret_store,
    )
)
app.register_blueprint(
    create_library_blueprint(
        library_getter=lambda: _library,
        jobs_getter=lambda: _jobs,
        run_in_bg=lambda job_id, fn, *args, kind="generic", job_meta=None, **kwargs: _run_in_bg(
            job_id, fn, *args, kind=kind, job_meta=job_meta, **kwargs
        ),
        running_heavy_jobs_getter=lambda: _running_heavy_jobs(),
        system_load_snapshot_getter=lambda: _system_load_snapshot(),
        task_queue_snapshot_getter=lambda: _task_queue_snapshot(),
        cancel_token_getter=lambda: CANCEL_TOKEN,
        job_cancelled_error_getter=lambda: JobCancelledError,
    )
)
app.register_blueprint(
    create_workflow_blueprint(
        parse_request_context=lambda: _parse_request_context(),
        build_custom_workflow_catalog=lambda: _build_custom_workflow_catalog(),
        normalize_agent_template_id=lambda value: _normalize_agent_template_id(value),
        parse_boolish=lambda value, default=False: _parse_boolish(value, default=default),
        coerce_bool=lambda value, default=False: _coerce_bool(value, default=default),
        custom_workflow_lock_getter=lambda: _custom_workflow_lock,
        read_custom_workflow_store=lambda: _read_custom_workflow_store(),
        save_custom_workflow_store=lambda store: _save_custom_workflow_store(store),
        normalize_custom_workflow_payload=lambda payload, existing=None: _normalize_custom_workflow_payload(
            payload, existing=existing
        ),
        resolve_custom_workflow_from_payload=lambda payload: _resolve_custom_workflow_from_payload(payload),
        build_custom_workflow_plan=lambda workflow, payload, dry_run=False: _build_custom_workflow_plan(
            workflow=workflow, payload=payload, dry_run=dry_run
        ),
        start_custom_workflow_run=lambda workflow, payload, request_context, source: _start_custom_workflow_run(
            workflow=workflow,
            payload=payload,
            request_context=request_context,
            source=source,
        ),
        read_custom_workflow_runs=lambda: _read_custom_workflow_runs(),
        find_custom_workflow_run=lambda run_id: _find_custom_workflow_run(run_id),
        build_failed_only_workflow_subset=lambda workflow, base_run: _build_failed_only_workflow_subset(
            workflow=workflow,
            base_run=base_run,
        ),
        project_dir_getter=lambda: _project_dir,
    )
)
app.register_blueprint(
    create_system_blueprint(
        state_dict_getter=lambda: _state_dict(),
        system_load_snapshot_getter=lambda: _system_load_snapshot(),
        overloaded_getter=lambda: _is_overloaded(),
        running_heavy_jobs_getter=lambda: _running_heavy_jobs(),
        task_queue_snapshot_getter=lambda: _task_queue_snapshot(),
        preflight_snapshot_getter=lambda force=False: _system_preflight_snapshot(force=bool(force)),
        queue_max_running_getter=lambda: _HEAVY_QUEUE_MAX_RUNNING,
        queue_max_running_setter=lambda v: _set_heavy_queue_max_running(v),
    )
)
app.register_blueprint(
    create_job_blueprint(
        jobs_getter=lambda: _jobs,
        load_job_from_store=lambda job_id: _load_job_from_store(job_id),
        heavy_queue_lock_getter=lambda: _heavy_queue_lock,
        heavy_job_queue_getter=lambda: _heavy_job_queue,
        dispatch_heavy_queue_locked=lambda: _dispatch_heavy_queue_locked(),
        persist_job_snapshot=lambda job_id, event_type="": _persist_job_snapshot(job_id, event_type=event_type),
        system_load_snapshot_getter=lambda: _system_load_snapshot(),
        state_dict_getter=lambda: _state_dict(),
        estimate_job_eta=lambda job: _estimate_job_eta(job),
        retry_hint_map=_RETRY_HINT_MAP,
    )
)
app.register_blueprint(
    create_legacy_project_blueprint(
        project_dir_getter=lambda: _project_dir,
        workflow_state_getter=lambda: _ws,
        jobs_getter=lambda: _jobs,
        prepare_project_dirs=lambda project_path: _prepare_project_dirs(project_path),
        library_getter=lambda: _library,
        default_project_config=lambda extra=None: _default_project_config(extra),
        load_state=lambda path: _load_state(path),
        remember_last_project=lambda path: _remember_last_project(path),
        recent_projects_getter=lambda: _get_recent_projects(),
        state_dict=lambda: _state_dict(),
        run_in_bg=lambda job_id, fn, *args, kind="generic", job_meta=None, **kwargs: _run_in_bg(
            job_id, fn, *args, kind=kind, job_meta=job_meta, **kwargs
        ),
        choose_path=lambda mode: _choose_path(mode),
    )
)
app.register_blueprint(
    create_content_publish_capability_blueprint(
        project_dir_getter=lambda: _project_dir,
        parse_capability_input_mode=lambda value, default="project": _parse_capability_input_mode(value, default=default),
        parse_platforms=lambda value: _parse_platforms(value),
        resolve_content_publish_content=lambda payload, input_mode: _resolve_content_publish_content(
            payload, input_mode=input_mode
        ),
        resolve_content_publish_connectors=lambda payload: _resolve_content_publish_connectors(payload),
        read_content_publish_sessions=lambda: _read_content_publish_sessions(),
        save_content_publish_sessions=lambda sessions: _save_content_publish_sessions(sessions),
        read_content_publish_history=lambda: _read_content_publish_history(),
        save_content_publish_history=lambda history: _save_content_publish_history(history),
        read_project_json=lambda filename, fallback=None: _read_project_json(filename, fallback=fallback),
        project_data_path=lambda filename: _project_data_path(filename),
        idempotency_lookup=lambda key: _ensure_capability_idempotency_store().lookup(key),
        idempotency_put_success=lambda key, **kw: _ensure_capability_idempotency_store().put_success(key, **kw),
        idempotency_make_cache_key=lambda path, ctx: _ensure_capability_idempotency_store().make_cache_key(path, ctx),
    )
)
app.register_blueprint(
    create_text_semantic_capability_blueprint(
        project_dir_getter=lambda: _project_dir,
        parse_capability_input_mode=lambda value, default="project": _parse_capability_input_mode(value, default=default),
        read_script_json=lambda: _read_script_json(),
        extract_subtitles_from_script=lambda script_payload: _extract_subtitles_from_script(script_payload),
        script_to_text_blocks=lambda script_payload: _script_to_text_blocks(script_payload),
        load_ai_settings=lambda: _load_ai_settings(),
        library_getter=lambda: _library,
        project_data_path=lambda filename: _project_data_path(filename),
    )
)
app.register_blueprint(
    create_timeline_blueprint(
        project_dir_getter=lambda: _project_dir,
        workflow_state_getter=lambda: _ws,
    )
)
app.register_blueprint(
    create_social_export_capability_blueprint(
        project_dir_getter=lambda: _project_dir,
        request_json_any_method=lambda: _request_json_any_method(),
        parse_capability_input_mode=lambda value, default="project": _parse_capability_input_mode(value, default=default),
        coerce_social_export_overrides=lambda payload, input_mode: _coerce_social_export_overrides(
            payload,
            input_mode=input_mode,
        ),
        normalize_export_template_payload=lambda payload: _normalize_export_template_payload(payload),
        save_social_export_templates=lambda templates: _save_social_export_templates(templates),
        normalize_export_template_id=lambda template_id: _normalize_export_template_id(template_id),
        get_social_export_history=lambda: _get_social_export_history(),
        capability_base_dir=lambda input_mode: _capability_base_dir(input_mode),
        resolve_path_with_base=lambda path_raw, base_dir=None: _resolve_path_with_base(path_raw, base_dir=base_dir),
        default_master_video_path=lambda: _default_master_video_path(),
        parse_platforms=lambda payload_value: _parse_platforms(payload_value),
        project_data_path=lambda filename: _project_data_path(filename),
        build_social_export_runner=lambda **kwargs: _build_social_export_runner(**kwargs),
        run_in_bg=lambda job_id, fn, *args, kind="generic", job_meta=None, **kwargs: _run_in_bg(
            job_id, fn, *args, kind=kind, job_meta=job_meta, **kwargs
        ),
        task_queue_snapshot=lambda: _task_queue_snapshot(),
    )
)
app.register_blueprint(
    create_audio_voice_capability_blueprint(
        project_dir_getter=lambda: _project_dir,
        parse_capability_input_mode=lambda value, default="project": _parse_capability_input_mode(value, default=default),
        capability_base_dir=lambda input_mode: _capability_base_dir(input_mode),
        coerce_script_input=lambda payload, input_mode: _coerce_script_input(payload, input_mode=input_mode),
        project_data_path=lambda filename: _project_data_path(filename),
        parse_str_list=lambda value: _parse_str_list(value),
        default_bgm_library_dirs=lambda custom_dir="", custom_dirs=(): _default_bgm_library_dirs(
            custom_dir=custom_dir,
            custom_dirs=custom_dirs,
        ),
        default_bgm_output_dir=lambda custom_dir="": _default_bgm_output_dir(custom_dir),
        resolve_path_with_base=lambda path_raw, base_dir=None: _resolve_path_with_base(path_raw, base_dir=base_dir),
        read_project_json=lambda filename, fallback=None: _read_project_json(filename, fallback=fallback),
        default_master_video_path=lambda: _default_master_video_path(),
        is_remote_media_url=lambda url: _is_remote_media_url(url),
        build_audio_voice_runner=lambda **kwargs: _build_audio_voice_runner(**kwargs),
        run_in_bg=lambda job_id, fn, *args, kind="generic", job_meta=None, **kwargs: _run_in_bg(
            job_id, fn, *args, kind=kind, job_meta=job_meta, **kwargs
        ),
        task_queue_snapshot=lambda: _task_queue_snapshot(),
    )
)
app.register_blueprint(
    create_editing_capability_blueprint(
        project_dir_getter=lambda: _project_dir,
        workflow_state_getter=lambda: _ws,
        request_json_any_method=lambda: _request_json_any_method(),
        parse_capability_input_mode=lambda value, default="project": _parse_capability_input_mode(value, default=default),
        parse_boolish=lambda value, default=False: _parse_boolish(value, default=default),
        project_data_path=lambda filename: _project_data_path(filename),
        slugify=lambda value: _slugify(value),
        read_project_json=lambda filename, fallback=None: _read_project_json(filename, fallback=fallback),
        coerce_materials_input=lambda payload, input_mode: _coerce_materials_input(payload, input_mode=input_mode),
        extract_material_semantics=lambda materials: _extract_material_semantics(materials),
        coerce_script_input=lambda payload, input_mode: _coerce_script_input(payload, input_mode=input_mode),
        capability_base_dir=lambda input_mode: _capability_base_dir(input_mode),
        resolve_path_with_base=lambda path_raw, base_dir=None: _resolve_path_with_base(path_raw, base_dir=base_dir),
        parse_str_list=lambda value: _parse_str_list(value),
    )
)
app.register_blueprint(
    create_agent_capability_blueprint(
        agent_capability_route_map=lambda: _agent_capability_route_map(),
        list_agent_skills=lambda: _list_agent_skills(),
        read_agent_cost_model_config=lambda: _read_agent_cost_model_config(),
    )
)
app.register_blueprint(
    create_agent_skill_blueprint(
        jobs_getter=lambda: _jobs,
        parse_request_context=lambda: _parse_request_context(),
        agent_skill_registry_getter=lambda: _AGENT_SKILL_REGISTRY,
        list_agent_skills=lambda: _list_agent_skills(),
        apply_agent_capability_input_defaults=lambda capability_id, input_payload, default_input: _apply_agent_capability_input_defaults(
            capability_id,
            input_payload,
            default_input=default_input,
        ),
        normalize_skill_retry_policy=lambda policy: _normalize_skill_retry_policy(policy),
        normalize_skill_timeout_seconds=lambda value, default=120.0: _normalize_skill_timeout_seconds(value, default=default),
        execute_agent_skill=lambda **kwargs: _execute_agent_skill(**kwargs),
        run_in_bg=lambda job_id, fn, *args, kind="generic", job_meta=None, **kwargs: _run_in_bg(
            job_id, fn, *args, kind=kind, job_meta=job_meta, **kwargs
        ),
        extract_template_ids_from_value=lambda payload: _extract_template_ids_from_value(payload),
    )
)
app.register_blueprint(
    create_agent_observability_blueprint(
        project_dir_getter=lambda: _project_dir,
        parse_agent_history_filter_tokens=lambda value: _parse_agent_history_filter_tokens(value),
        parse_boolish=lambda value, default=False: _parse_boolish(value, default=default),
        read_agent_task_history=lambda: _read_agent_task_history(),
        filter_agent_task_history=lambda history, **kwargs: _filter_agent_task_history(history, **kwargs),
        build_agent_observability_summary=lambda items, top_n=5: _build_agent_observability_summary(items, top_n=top_n),
        project_data_path=lambda filename: _project_data_path(filename),
    )
)
app.register_blueprint(
    create_agent_task_query_blueprint(
        project_dir_getter=lambda: _project_dir,
        jobs_getter=lambda: _jobs,
        find_agent_task_history_record=lambda job_id: _find_agent_task_history_record(job_id),
        build_chain_view_from_history_item=lambda item: _build_chain_view_from_history_item(item),
        read_agent_task_history=lambda: _read_agent_task_history(),
        parse_agent_history_filter_tokens=lambda value: _parse_agent_history_filter_tokens(value),
        filter_agent_task_history=lambda history, **kwargs: _filter_agent_task_history(history, **kwargs),
        parse_boolish=lambda value, default=False: _parse_boolish(value, default=default),
        coerce_bool=lambda value, default=False: _coerce_bool(value, default=default),
        build_agent_task_export_snapshot=lambda job_id, include_logs=True, include_result=True: _build_agent_task_export_snapshot(
            job_id,
            include_logs=include_logs,
            include_result=include_result,
        ),
        project_data_path=lambda filename: _project_data_path(filename),
        extract_agent_replay_spec=lambda replay_raw: _extract_agent_replay_spec(replay_raw),
        deep_merge_dict=lambda base, override: _deep_merge_dict(base, override),
        normalize_agent_replay_context=lambda raw: _normalize_agent_replay_context(raw),
        invoke_agent_primary_call=lambda **kwargs: _invoke_agent_primary_call(**kwargs),
    )
)
app.register_blueprint(
    create_agent_task_run_blueprint(
        jobs_getter=lambda: _jobs,
        parse_request_context=lambda: _parse_request_context(),
        normalize_skill_budget_limit=lambda raw: _normalize_skill_budget_limit(raw),
        normalize_agent_skill_steps=lambda skills_raw, default_retry_policy=None, default_timeout_seconds=120.0: _normalize_agent_skill_steps(
            skills_raw,
            default_retry_policy=default_retry_policy,
            default_timeout_seconds=default_timeout_seconds,
        ),
        normalize_skill_timeout_seconds=lambda value, default=120.0: _normalize_skill_timeout_seconds(value, default=default),
        apply_governance_to_skill_flow=lambda **kwargs: _apply_governance_to_skill_flow(**kwargs),
        apply_agent_capability_input_defaults=lambda capability_id, input_payload: _apply_agent_capability_input_defaults(
            capability_id,
            input_payload,
        ),
        agent_capability_route_map=lambda: _agent_capability_route_map(),
        resolve_agent_primary_call=lambda capability_id, routes, action="auto": _resolve_agent_primary_call(
            capability_id=capability_id,
            routes=routes,
            action=action,
        ),
        invoke_agent_primary_call=lambda **kwargs: _invoke_agent_primary_call(**kwargs),
        should_run_conditional_step=lambda condition, previous_results: _should_run_conditional_step(
            condition,
            previous_results,
        ),
        execute_agent_skill=lambda **kwargs: _execute_agent_skill(**kwargs),
        record_governance_usage_for_skill_flow=lambda actor_id, summary: _record_governance_usage_for_skill_flow(
            actor_id=actor_id,
            summary=summary,
        ),
        extract_template_ids_from_value=lambda value: _extract_template_ids_from_value(value),
        run_in_bg=lambda job_id, fn, *args, kind="generic", job_meta=None, **kwargs: _run_in_bg(
            job_id, fn, *args, kind=kind, job_meta=job_meta, **kwargs
        ),
    )
)
app.register_blueprint(
    create_idempotency_blueprint(
        parse_boolish=lambda value, default=False: _parse_boolish(value, default=default),
        normalize_filter_text=lambda value: _normalize_capability_idempotency_filter_text(value),
        normalize_ttl=lambda value, default: _normalize_capability_idempotency_ttl(value, default=default),
        collect_records=lambda **kwargs: _collect_capability_idempotency_records(**kwargs),
        capability_idempotency_ttl_getter=lambda: _CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
        capability_idempotency_limit_getter=lambda: _CAPABILITY_IDEMPOTENCY_LIMIT,
        capability_cache_getter=lambda: _capability_idempotency_cache,
        capability_lock_getter=lambda: _capability_idempotency_lock,
        filter_entries=lambda entries, ttl_seconds, include_expired: _filter_capability_idempotency_entries(
            entries,
            ttl_seconds=ttl_seconds,
            include_expired=include_expired,
        ),
        trim_entries_with_limit=lambda entries, max_entries, ttl_seconds: _trim_capability_idempotency_entries_with_limit(
            entries,
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
        ),
        limit_entries=lambda entries, max_entries: _limit_capability_idempotency_entries(
            entries,
            max_entries=max_entries,
        ),
        load_store=lambda include_expired=True, ttl_seconds=None: _load_capability_idempotency_store(
            include_expired=include_expired,
            ttl_seconds=ttl_seconds,
        ),
        save_store=lambda entries: _save_capability_idempotency_store(entries),
    )
)
app.register_blueprint(
    create_agent_template_blueprint(
        project_dir_getter=lambda: _project_dir,
        parse_request_context=lambda: _parse_request_context(),
        parse_boolish=lambda value, default=False: _parse_boolish(value, default=default),
        list_agent_templates=lambda **kwargs: _list_agent_templates(**kwargs),
        normalize_agent_template_payload=lambda payload, scope_default, actor_id_default: _normalize_agent_template_payload(
            payload,
            scope_default=scope_default,
            actor_id_default=actor_id_default,
        ),
        read_agent_template_store=lambda: _read_agent_template_store(),
        validate_agent_template_base_reference=lambda template, store: _validate_agent_template_base_reference(
            template,
            store=store,
        ),
        save_agent_template_store=lambda store: _save_agent_template_store(store),
        normalize_agent_template_id=lambda value: _normalize_agent_template_id(value),
    )
)
app.register_blueprint(
    create_ui_blueprint(
        app_ui_dir_getter=lambda: APP_UI_DIR,
    )
)


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_exc):
    limit_mb = int(max(app.config.get("MAX_CONTENT_LENGTH", 0), 0) / (1024 * 1024))
    return (
        jsonify(
            {
                "error": f"请求内容过大（上限约 {limit_mb}MB）。请减少单次提交内容，或按批次执行。"
            }
        ),
        413,
    )


@app.errorhandler(404)
def handle_not_found(_exc):
    return jsonify({"error": "路由不存在", "code": "not_found"}), 404


@app.errorhandler(405)
def handle_method_not_allowed(_exc):
    return jsonify({"error": "HTTP 方法不允许", "code": "method_not_allowed"}), 405


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    if isinstance(exc, HTTPException):
        return jsonify({"error": str(exc.description), "code": exc.name}), exc.code
    logger.exception("未捕获异常: %s", exc)
    return (
        jsonify(
            {
                "error": "系统发生异常，已记录日志。请重试；若持续失败，请在设置中导出诊断信息。"
            }
        ),
        500,
    )


def _request_is_local() -> bool:
    remote = str(request.remote_addr or "").strip()
    if remote in {"127.0.0.1", "::1", "localhost", ""}:
        return True
    return False


def _is_mutating_method(method: str) -> bool:
    return str(method or "").strip().upper() in {"POST", "PUT", "PATCH", "DELETE"}


def _is_allowed_local_origin(origin: str) -> bool:
    text = str(origin or "").strip().lower()
    if not text:
        return True
    if text in {"null", "file://"}:
        return True
    allowed_prefixes = (
        "http://127.0.0.1",
        "https://127.0.0.1",
        "http://localhost",
        "https://localhost",
    )
    return any(text.startswith(prefix) for prefix in allowed_prefixes)


@app.before_request
def _guard_local_api_token():
    if request.method == "OPTIONS":
        return None
    path = str(request.path or "")
    if not path.startswith("/api/"):
        return None
    enforce_csrf = bool(_REQUIRE_CSRF_PROTECTION and _REQUIRE_LOCAL_API_TOKEN)
    origin = str(request.headers.get("Origin", "") or "").strip()
    if enforce_csrf and _is_mutating_method(request.method) and not _is_allowed_local_origin(origin):
        return jsonify({"error": "非法来源，请在本地应用内发起请求。", "code": "origin_forbidden"}), 403
    if path == "/api/session/bootstrap":
        return None
    if enforce_csrf and _is_mutating_method(request.method):
        provided_csrf = str(request.headers.get("X-VideoEditor-CSRF", "") or "").strip()
        if not provided_csrf:
            provided_csrf = str(request.args.get("_csrf", "") or "").strip()
        if provided_csrf != _LOCAL_CSRF_TOKEN:
            return (
                jsonify(
                    {
                        "error": "请求缺少安全校验，请刷新应用后重试。",
                        "code": "csrf_required",
                    }
                ),
                403,
            )
    if not _REQUIRE_LOCAL_API_TOKEN:
        return None
    if not _request_is_local():
        return jsonify({"error": "仅允许本机访问该 API"}), 403
    provided = str(request.headers.get("X-VideoEditor-Token", "") or "").strip()
    if not provided:
        provided = str(request.args.get("_vt", "") or "").strip()
    if provided != _LOCAL_API_TOKEN:
        return (
            jsonify(
                {
                    "error": "未授权请求，请先完成本地会话握手。",
                    "code": "local_auth_required",
                }
            ),
            401,
        )
    return None

_heavy_job_submit_lock = threading.Lock()
_agent_history_lock = threading.Lock()
_custom_workflow_lock = threading.Lock()
_HEAVY_JOB_KINDS = {
    "workflow_step",
    "library_ingest_local",
    "library_ingest_local_images",
    "library_ingest_gdrive",
    "library_ingest_gdrive_images",
    "social_export",
    "audio_voice",
    "custom_workflow",
}
_HEAVY_QUEUE_MAX_RUNNING = max(1, min(int(os.environ.get("VIDEOEDITOR_HEAVY_QUEUE_MAX_RUNNING", "2") or 2), 4))
_job_runtime: Optional[JobRuntime] = None


def _set_heavy_queue_max_running(val: int):
    global _HEAVY_QUEUE_MAX_RUNNING
    val = max(1, min(int(val), 4))
    _HEAVY_QUEUE_MAX_RUNNING = val
    if _job_runtime is not None:
        _job_runtime._max_running = val
_heavy_queue_lock = threading.Lock()
_heavy_job_queue = []
CANCEL_TOKEN = "__CANCELLED__"
_eta_history_lock = threading.Lock()
_eta_history_cache: Dict[str, Any] = {
    "updated_at": 0.0,
    "avg_by_kind": {},
    "fallback_avg": 0.0,
}
_preflight_lock = threading.Lock()
_preflight_cache: Dict[str, Any] = {
    "updated_at": 0.0,
    "report": None,
}
_PREFLIGHT_CACHE_TTL_SECONDS = 15.0


def _app_state_db_path() -> Path:
    base = _library.db_path.parent if hasattr(_library, "db_path") else (REPO_ROOT / ".video_library")
    path = Path(base) / "app_state.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_job_store() -> JobStore:
    global _job_store, _job_store_path
    target = _app_state_db_path().resolve()
    if _job_store is None or _job_store_path is None or _job_store_path != target:
        _job_store = JobStore(target)
        _job_store_path = target
    return _job_store


def _safe_copy(value: Any, fallback: Any):
    try:
        return deepcopy(value)
    except Exception:
        return fallback


def _job_payload_for_store(job: Dict[str, Any]) -> Dict[str, Any]:
    meta = job.get("meta", {}) if isinstance(job.get("meta"), dict) else {}
    log_items = job.get("log", []) if isinstance(job.get("log"), list) else []
    payload = {
        "status": str(job.get("status", "queued") or "queued"),
        "kind": str(job.get("kind", "generic") or "generic"),
        "progress": int(job.get("progress", 0) or 0),
        "queued_at": job.get("queued_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "cancel_requested": bool(job.get("cancel_requested", False)),
        "cancel_requested_at": job.get("cancel_requested_at"),
        "queue_position": int(job.get("queue_position", 0) or 0),
        "error": str(job.get("error", "") or "") or None,
        "meta": _safe_copy(meta, {}),
        "result": _safe_copy(job.get("result"), None),
        "log": [str(item) for item in log_items][-500:],
        "created_at": str(job.get("created_at", "") or "") or str(job.get("queued_at", "") or ""),
    }
    return payload


def _persist_job_snapshot(job_id: str, event_type: str = ""):
    jid = str(job_id or "").strip()
    if not jid:
        return
    job = _jobs.get(jid)
    if not isinstance(job, dict):
        return
    for attempt in range(4):
        try:
            store = _ensure_job_store()
            store.upsert_job(jid, _job_payload_for_store(job))
            if event_type:
                store.append_event(
                    jid,
                    event_type=event_type,
                    payload={
                        "status": str(job.get("status", "unknown") or "unknown"),
                        "progress": int(job.get("progress", 0) or 0),
                    },
                )
            return
        except Exception as exc:
            if "locked" in str(exc).lower() and attempt < 3:
                time.sleep(0.04 * (attempt + 1))
                continue
            return


def _make_managed_job(job_id: str, payload: Dict[str, Any]) -> _ManagedJob:
    if _job_runtime is None:
        return _ManagedJob(str(job_id or ""), dict(payload or {}))
    return _job_runtime.make_managed_job(job_id, payload)


def _restore_jobs_from_store():
    global _jobs
    if _job_runtime is None:
        return
    try:
        store = _ensure_job_store()
        rows = store.list_jobs(limit=1200)
    except Exception:
        return
    _job_runtime.restore_jobs(rows)
    _jobs = _job_runtime.jobs


def _load_job_from_store(job_id: str) -> Optional[Dict[str, Any]]:
    jid = str(job_id or "").strip()
    if not jid or _job_runtime is None:
        return None
    try:
        store = _ensure_job_store()
        row = store.get_job(jid)
    except Exception:
        row = None
    if not isinstance(row, dict):
        return None
    return _job_runtime.adopt_job(jid, row)


def _reset_job_store_for_tests():
    global _job_store, _job_store_path
    _job_store = None
    _job_store_path = None
    if _job_runtime is not None:
        _job_runtime.jobs.clear()
        with _job_runtime.heavy_queue_lock:
            _job_runtime.heavy_job_queue.clear()
    with _eta_history_lock:
        _eta_history_cache["updated_at"] = 0.0
        _eta_history_cache["avg_by_kind"] = {}
        _eta_history_cache["fallback_avg"] = 0.0
_capability_idempotency_cache: Dict[str, Dict[str, Any]] = {}
_capability_idempotency_lock = threading.Lock()
_CAPABILITY_IDEMPOTENCY_LIMIT = 400
_CAPABILITY_IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600
_capability_idempotency_store: Optional[CapabilityIdempotencyStore] = None
_CUSTOM_WORKFLOW_HISTORY_MAX = 500
_CUSTOM_WORKFLOW_STEP_LIMIT = 60
_custom_workflow_store_mem: Dict[str, Dict[str, Any]] = {}
_custom_workflow_runs_mem: List[Dict[str, Any]] = []
_AGENT_TEMPLATE_SCOPE_ORDER = {"system": 0, "project": 1, "agent": 2}
_AGENT_SYSTEM_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "topic_copy_travel_story": {
        "template_id": "topic_copy_travel_story",
        "name": "选题文案-旅行叙事",
        "capability_id": "topic_copy",
        "scope": "system",
        "actor_id": "",
        "tags": ["travel", "story"],
        "base_template_id": "",
        "overrides": {},
        "variables": [
            {
                "key": "target_duration_s",
                "type": "integer",
                "required": False,
                "default": 60,
                "minimum": 10,
                "maximum": 300,
            }
        ],
        "content": {
            "input_mode": "auto",
            "target_duration_s": 60,
            "hook_style": "story",
            "tone": "warm_real",
        },
        "updated_at": "system",
    },
    "text_rough_remove_fillers": {
        "template_id": "text_rough_remove_fillers",
        "name": "文字粗剪-去口头词",
        "capability_id": "text_rough_cut",
        "scope": "system",
        "actor_id": "",
        "tags": ["rough_cut", "fillers"],
        "base_template_id": "",
        "overrides": {},
        "variables": [
            {
                "key": "target_duration_s",
                "type": "integer",
                "required": False,
                "default": 15,
                "minimum": 5,
                "maximum": 120,
            },
            {
                "key": "merge_gap_s",
                "type": "number",
                "required": False,
                "default": 0.15,
                "minimum": 0.0,
                "maximum": 2.0,
            },
        ],
        "content": {
            "input_mode": "auto",
            "target_duration_s": 15,
            "merge_gap_s": 0.15,
            "removed_phrases": ["嗯", "啊", "然后", "就是", "那个"],
        },
        "updated_at": "system",
    },
    "social_export_cn_bundle": {
        "template_id": "social_export_cn_bundle",
        "name": "社媒导出-中文平台组合",
        "capability_id": "social_export",
        "scope": "system",
        "actor_id": "",
        "tags": ["export", "cn_platforms"],
        "base_template_id": "",
        "overrides": {},
        "variables": [
            {
                "key": "quality",
                "type": "string",
                "required": False,
                "default": "high",
                "enum": ["high", "medium", "fast"],
            }
        ],
        "content": {
            "input_mode": "auto",
            "platforms": ["douyin", "xiaohongshu", "wechat_short", "bilibili"],
            "quality": "high",
            "strict_duration_limit": True,
        },
        "updated_at": "system",
    },
}
_AGENT_SKILL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "skill.topic_library.search": {
        "skill_id": "skill.topic_library.search",
        "name": "选题库检索",
        "method": "GET",
        "endpoint": "/api/capabilities/topic_library",
        "capability_id": "topic_library",
        "description": "检索项目选题库并返回候选主题。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.topic_copy.draft": {
        "skill_id": "skill.topic_copy.draft",
        "name": "选题文案草拟",
        "method": "POST",
        "endpoint": "/api/capabilities/topic_copy/draft",
        "capability_id": "topic_copy",
        "description": "基于选题 slug 生成文案草稿。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.text_rough_cut.plan": {
        "skill_id": "skill.text_rough_cut.plan",
        "name": "文字粗剪规划",
        "method": "POST",
        "endpoint": "/api/capabilities/text_rough_cut/plan",
        "capability_id": "text_rough_cut",
        "description": "按逐句文本生成粗剪计划。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.short_clip.plan": {
        "skill_id": "skill.short_clip.plan",
        "name": "短视频快剪规划",
        "method": "POST",
        "endpoint": "/api/capabilities/short_clip/plan",
        "capability_id": "short_clip",
        "description": "按目标时长提炼高光片段。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.publish_prep.generate": {
        "skill_id": "skill.publish_prep.generate",
        "name": "发布文案准备",
        "method": "POST",
        "endpoint": "/api/capabilities/publish_prep/generate",
        "capability_id": "publish_prep",
        "description": "按平台生成标题、正文与关键词发布包。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.subtitle_calibration.run": {
        "skill_id": "skill.subtitle_calibration.run",
        "name": "字幕校准执行",
        "method": "POST",
        "endpoint": "/api/capabilities/subtitle_calibration/run",
        "capability_id": "subtitle_calibration",
        "description": "执行中英字幕校准（可选时间轴重对齐与翻译）。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.image_semantic.analyze": {
        "skill_id": "skill.image_semantic.analyze",
        "name": "图片语义分析",
        "method": "POST",
        "endpoint": "/api/capabilities/image_semantic/analyze",
        "capability_id": "image_semantic",
        "description": "对单图/批量图片执行语义分析并返回结构化标签。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.article_expand.generate": {
        "skill_id": "skill.article_expand.generate",
        "name": "公众号扩写生成",
        "method": "POST",
        "endpoint": "/api/capabilities/article_expand/generate",
        "capability_id": "article_expand",
        "description": "生成微信公众号文章扩写草稿（标题/导语/正文/CTA）。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.content_publish.run": {
        "skill_id": "skill.content_publish.run",
        "name": "内容发布执行",
        "method": "POST",
        "endpoint": "/api/capabilities/content_publish/run",
        "capability_id": "content_publish",
        "description": "按发布计划执行跨平台内容发布，支持 dry_run 与真实发布。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.social_export.plan": {
        "skill_id": "skill.social_export.plan",
        "name": "社媒导出规划",
        "method": "POST",
        "endpoint": "/api/capabilities/social_export/plan",
        "capability_id": "social_export",
        "description": "生成多平台导出计划，不执行转码。",
        "default_input": {"input_mode": "auto"},
    },
    "skill.audio_voice.plan": {
        "skill_id": "skill.audio_voice.plan",
        "name": "配乐配音规划",
        "method": "POST",
        "endpoint": "/api/capabilities/audio_voice/plan",
        "capability_id": "audio_voice",
        "description": "生成配音与配乐的执行计划。",
        "default_input": {"input_mode": "auto"},
    },
}
_AGENT_GOVERNANCE_DEFAULT: Dict[str, Any] = {
    "default_limits": {
        "max_steps": 40,
        "max_failures": 12,
        "max_duration_seconds": 1800,
        "max_parallel": 4,
    },
    "actor_limits": {},
    "capability_limits": {},
    "actor_capability_limits": {},
    "blocked_skills": [],
    "blocked_capabilities": [],
    "blocked_skills_by_actor": {},
    "blocked_capabilities_by_actor": {},
}
_AGENT_GOVERNANCE_USAGE_DEFAULT: Dict[str, Any] = {
    "version": 1,
    "updated_at": "",
    "actors": {},
}
_AGENT_USAGE_RECENT_RUNS_MAX = 16
_AGENT_TASK_HISTORY_MAX = 600
_AGENT_COST_MODEL_DEFAULT: Dict[str, Any] = {
    "default_rates": {
        "prompt_usd_per_1k_tokens": 0.002,
        "completion_usd_per_1k_tokens": 0.006,
        "compute_usd_per_second": 0.00005,
    },
    "providers": {},
}


class JobCancelledError(RuntimeError):
    def __init__(self, message: str = "任务已取消", result=None):
        super().__init__(message)
        self.result = result


def _on_job_runtime_finished(job_id: str, job: Dict[str, Any]):
    kind = str((job or {}).get("kind", "") or "")
    if kind in {"agent_task", "agent_skill"}:
        try:
            _record_agent_task_history_from_job(job_id)
        except Exception:
            pass
    if _ws:
        try:
            _ws.load()
        except Exception:
            pass


_job_runtime = JobRuntime(
    heavy_job_kinds=_HEAVY_JOB_KINDS,
    max_running=_HEAVY_QUEUE_MAX_RUNNING,
    cancel_token=CANCEL_TOKEN,
    job_cancelled_error_cls=JobCancelledError,
    persist_snapshot=lambda job_id, event_type="": _persist_job_snapshot(job_id, event_type=event_type),
    after_job_finished=_on_job_runtime_finished,
)
_jobs = _job_runtime.jobs
_heavy_queue_lock = _job_runtime.heavy_queue_lock
_heavy_job_queue = _job_runtime.heavy_job_queue

RENDER_DEFAULTS = {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "crf_rough": 28,
    "crf_final": 18,
    "preset_rough": "ultrafast",
    "preset_final": "slow",
    "enable_skin_smooth": True,
    "enable_color_grading": True,
    "enable_skill_enhance": True,
    "aesthetic_preset": "travel_story",
    "transition_style": "fade",
    "transition_duration": 0.35,
    "timeout_concat_sec": 1500,
    "timeout_stage_sec": 900,
    "timeout_audio_sec": 480,
    "bgm_volume": 0.3,
    "subtitle_font": "PingFangSC-Regular",
    "subtitle_size": 56,
    "audio_bitrate": "192k",
    "rough_target_seconds": 15,
    "rough_max_clips": 8,
    "rough_min_gap_s": 0.25,
    "rough_merge_gap_s": 0.15,
    "rough_remove_phrases": "嗯,啊,然后,就是,那个",
}

# ── 辅助 ─────────────────────────────────────────────────────────────

def _load_state(project_dir: Path) -> WorkflowState:
    global _ws, _project_dir
    _project_dir = project_dir
    _ws = WorkflowState(project_dir)
    _ws.load()
    return _ws


def _state_dict() -> dict:
    if _ws is None:
        return {"ready": False}
    ws = _ws
    steps_info = []
    for n in range(1, 8):
        sd = ws.get_step(n)
        steps_info.append({
            "n": n,
            "name": WorkflowState.STEP_NAMES.get(n, f"Step {n}"),
            "status": sd.get("status", "not_started"),
            "review_status": sd.get("review_status"),
            "output": sd.get("output"),
            "review_file": sd.get("review_file"),
        })
    history_raw = ws.data.get("social_export_history", [])
    history = history_raw if isinstance(history_raw, list) else []
    recent_history = list(reversed(history[-20:]))
    return {
        "ready": True,
        "project_dir": str(ws.data.get("project_dir", "")),
        "videos_dir": str(ws.data.get("videos_dir", "")),
        "current_step": ws.data.get("current_step", 1),
        "steps": steps_info,
        "config": ws.config,
        "social_export_history": recent_history,
        "system": _system_load_snapshot(),
        "running_jobs": _running_heavy_jobs(),
        "task_queue": _task_queue_snapshot(),
    }


def _is_heavy_kind(kind: Any) -> bool:
    return bool(_job_runtime and _job_runtime.is_heavy_kind(kind))


def _count_running_heavy_jobs_locked() -> int:
    if _job_runtime is None:
        return 0
    return _job_runtime._count_running_heavy_jobs_locked()


def _queued_heavy_jobs_locked() -> List[Dict[str, Any]]:
    if _job_runtime is None:
        return []
    return _job_runtime._queued_heavy_jobs_locked()


def _task_queue_snapshot() -> Dict[str, Any]:
    if _job_runtime is None:
        return {"max_running": _HEAVY_QUEUE_MAX_RUNNING, "running_count": 0, "queued_count": 0, "running": [], "queued": []}
    return _job_runtime.task_queue_snapshot()


def _start_job_worker_thread(
    job_id: str,
    fn: Callable,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
):
    if _job_runtime is None:
        return
    _job_runtime._start_job_worker_thread(job_id, fn, args, kwargs)


def _dispatch_heavy_queue_locked():
    if _job_runtime is None:
        return
    _job_runtime.dispatch_heavy_queue_locked()


def _run_in_bg(job_id: str, fn, *args, kind: str = "generic", job_meta: Optional[Dict[str, Any]] = None, **kwargs):
    """在后台线程运行 fn，捕获 stdout 并更新 _jobs[job_id]。重任务自动进入队列。"""
    if _job_runtime is None:
        return job_id
    return _job_runtime.run_in_bg(job_id, fn, *args, kind=kind, job_meta=job_meta, **kwargs)


def _running_heavy_jobs() -> list:
    if _job_runtime is None:
        return []
    return _job_runtime.running_heavy_jobs()


def _system_load_snapshot() -> Dict:
    cpu_count = os.cpu_count() or 1
    try:
        l1, l5, l15 = os.getloadavg()
    except Exception:
        l1, l5, l15 = 0.0, 0.0, 0.0
    return {
        "cpu_count": cpu_count,
        "load_1m": round(float(l1), 3),
        "load_5m": round(float(l5), 3),
        "load_15m": round(float(l15), 3),
        "load_ratio_1m": round(float(l1) / max(cpu_count, 1), 3),
    }


def _system_preflight_snapshot(force: bool = False) -> Dict[str, Any]:
    now_ts = time.time()
    with _preflight_lock:
        report_cached = _preflight_cache.get("report")
        updated_at = float(_preflight_cache.get("updated_at", 0.0) or 0.0)
        if (not force) and isinstance(report_cached, dict) and (now_ts - updated_at) <= _PREFLIGHT_CACHE_TTL_SECONDS:
            return deepcopy(report_cached)

    try:
        report = run_startup_preflight(
            repo_root=REPO_ROOT,
            library_db_path=_library.db_path if hasattr(_library, "db_path") else (REPO_ROOT / ".video_library" / "library.db"),
            app_state_db_path=_app_state_db_path(),
            ai_settings=_load_ai_settings(),
            ui_settings=_load_ui_settings(),
            secret_storage_status=_secret_store.public_status(),
            require_local_token=bool(_REQUIRE_LOCAL_API_TOKEN),
            require_csrf=bool(_REQUIRE_CSRF_PROTECTION and _REQUIRE_LOCAL_API_TOKEN),
        )
    except Exception as exc:
        report = {
            "ok": False,
            "startup_ready": False,
            "summary": {
                "total": 1,
                "ok": 0,
                "warning": 0,
                "error": 1,
                "score": 0.0,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
            "checks": [
                {
                    "id": "preflight.internal_error",
                    "title": "系统自检",
                    "status": "error",
                    "severity": "error",
                    "detail": f"系统自检失败: {exc}",
                    "hint": "请重启应用后重试；若持续失败请导出日志。",
                    "data": {},
                }
            ],
            "blockers": [],
            "warnings": [],
            "recommended_actions": ["请重启应用后重试；若持续失败请导出日志。"],
            "nle_connectors": [],
            "meta": {"repo_root": str(REPO_ROOT)},
        }

    with _preflight_lock:
        _preflight_cache["updated_at"] = time.time()
        _preflight_cache["report"] = deepcopy(report)
    return report


def _is_overloaded() -> bool:
    snap = _system_load_snapshot()
    # 比较保守：1分钟 load 超过 CPU 核心数的 1.6 倍时拒绝启动新的重任务
    return snap.get("load_ratio_1m", 0.0) >= 1.6


def _prepare_project_dirs(project_path: Path):
    for sub in ("data", "reviews", "preview", "output"):
        (project_path / sub).mkdir(parents=True, exist_ok=True)


def _settings_path() -> Path:
    p = _library.db_path.parent / "app_settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_settings() -> Dict:
    p = _settings_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_settings(data: Dict):
    p = _settings_path()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


_DEFAULT_UI_SETTINGS: Dict[str, Any] = {
    "onboarding_completed": False,
    "creator_mode": True,
    "font_scale": 1.0,
    "preferred_production_view": "hub",
    "default_videos_dir": "",
    "default_project_dir": "",
    "auto_open_last_project": True,
    "last_project_dir": "",
}


def _normalize_production_view(raw: Any) -> str:
    key = str(raw or "").strip().lower()
    if key in {"workflow", "graph"}:
        return "workflow"
    return "hub"


def _normalize_font_scale(raw: Any) -> float:
    try:
        value = float(raw)
    except Exception:
        value = 1.0
    return round(max(0.85, min(value, 1.45)), 2)


def _load_ui_settings() -> Dict[str, Any]:
    src = _read_settings().get("ui", {})
    if not isinstance(src, dict):
        src = {}
    out = dict(_DEFAULT_UI_SETTINGS)
    out["onboarding_completed"] = bool(src.get("onboarding_completed", out["onboarding_completed"]))
    out["creator_mode"] = bool(src.get("creator_mode", out["creator_mode"]))
    out["font_scale"] = _normalize_font_scale(src.get("font_scale", out["font_scale"]))
    out["preferred_production_view"] = _normalize_production_view(
        src.get("preferred_production_view", out["preferred_production_view"])
    )
    out["default_videos_dir"] = str(src.get("default_videos_dir", out["default_videos_dir"]) or "").strip()
    out["default_project_dir"] = str(src.get("default_project_dir", out["default_project_dir"]) or "").strip()
    out["auto_open_last_project"] = bool(src.get("auto_open_last_project", out["auto_open_last_project"]))
    out["last_project_dir"] = str(src.get("last_project_dir", out["last_project_dir"]) or "").strip()
    return out


def _save_ui_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    src = payload if isinstance(payload, dict) else {}
    settings = _read_settings()
    ui = settings.get("ui", {})
    if not isinstance(ui, dict):
        ui = {}

    if "onboarding_completed" in src:
        ui["onboarding_completed"] = bool(src.get("onboarding_completed"))
    if "creator_mode" in src:
        ui["creator_mode"] = bool(src.get("creator_mode"))
    if "font_scale" in src:
        ui["font_scale"] = _normalize_font_scale(src.get("font_scale"))
    if "preferred_production_view" in src:
        ui["preferred_production_view"] = _normalize_production_view(src.get("preferred_production_view"))
    if "default_videos_dir" in src:
        ui["default_videos_dir"] = str(src.get("default_videos_dir", "") or "").strip()
    if "default_project_dir" in src:
        ui["default_project_dir"] = str(src.get("default_project_dir", "") or "").strip()
    if "auto_open_last_project" in src:
        ui["auto_open_last_project"] = bool(src.get("auto_open_last_project"))
    if "last_project_dir" in src:
        ui["last_project_dir"] = str(src.get("last_project_dir", "") or "").strip()

    settings["ui"] = ui
    _write_settings(settings)
    return _load_ui_settings()


def _remember_last_project(project_path: Path):
    if not isinstance(project_path, Path):
        return
    try:
        resolved = str(project_path.resolve())
        _save_ui_settings({"last_project_dir": resolved})
        # Also maintain recent_projects list
        _add_to_recent_projects(resolved, project_path.name)
    except Exception:
        pass


def _add_to_recent_projects(path_str: str, name: str):
    """Maintain a recent_projects list (max 20) in settings."""
    try:
        settings = _read_settings()
        recents = settings.get("recent_projects", [])
        if not isinstance(recents, list):
            recents = []
        # Remove existing entry for this path
        recents = [r for r in recents if r.get("path") != path_str]
        # Prepend new entry
        recents.insert(0, {
            "path": path_str,
            "name": name,
            "opened_at": datetime.now().isoformat(timespec="seconds"),
        })
        # Trim to 20
        recents = recents[:20]
        settings["recent_projects"] = recents
        _write_settings(settings)
    except Exception:
        pass


def _get_recent_projects() -> List[Dict[str, Any]]:
    """Return recent projects with status info."""
    settings = _read_settings()
    recents = settings.get("recent_projects", [])
    if not isinstance(recents, list):
        return []
    result = []
    for entry in recents[:20]:
        if not isinstance(entry, dict):
            continue
        p = entry.get("path", "")
        if not p:
            continue
        proj_path = Path(p)
        wf_file = proj_path / "workflow.json"
        status = "unknown"
        current_step = 0
        total_steps = 7
        completed_steps = 0
        if wf_file.exists():
            try:
                wf = json.loads(wf_file.read_text(encoding="utf-8"))
                current_step = int(wf.get("current_step", 0))
                total_steps = int(wf.get("total_steps", 7))
                completed_steps = len(wf.get("completed_steps", []))
                if completed_steps >= total_steps:
                    status = "completed"
                elif current_step > 0:
                    status = "in_progress"
                else:
                    status = "draft"
            except Exception:
                status = "draft"
        else:
            status = "missing"
        result.append({
            "path": p,
            "name": entry.get("name", proj_path.name),
            "opened_at": entry.get("opened_at", ""),
            "status": status,
            "current_step": current_step,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "exists": proj_path.exists(),
        })
    return result


_DEFAULT_PUBLISH_SETTINGS: Dict[str, Any] = {
    "connectors": {},
}
_PUBLISH_SECRET_KEEP_SENTINEL = "__KEEP__"


def _normalize_publish_connectors(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for platform_id, item in raw.items():
        pid = str(platform_id or "").strip().lower()
        if not pid:
            continue
        if not isinstance(item, dict):
            continue
        row = {
            "kind": str(item.get("kind", "webhook") or "webhook").strip().lower() or "webhook",
            "endpoint": str(item.get("endpoint", "") or "").strip(),
            "method": str(item.get("method", "POST") or "POST").strip().upper() or "POST",
            "timeout_s": max(1.0, min(float(item.get("timeout_s", 25) or 25), 120.0)),
            "token": str(item.get("token", "") or "").strip(),
            "headers": item.get("headers", {}) if isinstance(item.get("headers"), dict) else {},
        }
        out[pid] = row
    return out


def _merge_publish_connectors_with_existing(
    existing: Dict[str, Dict[str, Any]],
    incoming: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    old = existing if isinstance(existing, dict) else {}
    new = incoming if isinstance(incoming, dict) else {}
    for pid, row in new.items():
        if not isinstance(row, dict):
            continue
        prev = old.get(pid, {}) if isinstance(old.get(pid), dict) else {}
        token = str(row.get("token", "") or "").strip()
        if token == _PUBLISH_SECRET_KEEP_SENTINEL:
            token = str(prev.get("token", "") or "").strip()

        headers_raw = row.get("headers", {}) if isinstance(row.get("headers"), dict) else {}
        prev_headers = prev.get("headers", {}) if isinstance(prev.get("headers"), dict) else {}
        headers: Dict[str, Any] = {}
        for hk, hv in headers_raw.items():
            key = str(hk or "").strip()
            if not key:
                continue
            value = str(hv or "").strip()
            if value == _PUBLISH_SECRET_KEEP_SENTINEL:
                value = str(prev_headers.get(key, "") or "").strip()
            headers[key] = value

        merged[pid] = {
            "kind": str(row.get("kind", "webhook") or "webhook").strip().lower() or "webhook",
            "endpoint": str(row.get("endpoint", "") or "").strip(),
            "method": str(row.get("method", "POST") or "POST").strip().upper() or "POST",
            "timeout_s": max(1.0, min(float(row.get("timeout_s", 25) or 25), 120.0)),
            "token": token,
            "headers": headers,
        }
    return merged


def _mask_publish_connectors(connectors: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for pid, item in (connectors or {}).items():
        if not isinstance(item, dict):
            continue
        headers_raw = item.get("headers", {}) if isinstance(item.get("headers"), dict) else {}
        headers_masked: Dict[str, Any] = {}
        for hk, hv in headers_raw.items():
            key = str(hk or "")
            val = str(hv or "")
            if key.lower() in {"authorization", "x-api-key", "x-auth-token"}:
                headers_masked[key] = _mask_secret(val)
            else:
                headers_masked[key] = val
        out[str(pid)] = {
            **item,
            "token": _mask_secret(item.get("token", "")),
            "headers": headers_masked,
        }
    return out


def _load_publish_settings() -> Dict[str, Any]:
    src = _read_settings().get("publish", {})
    if not isinstance(src, dict):
        src = {}
    connectors = _normalize_publish_connectors(src.get("connectors", {}))
    return {
        "connectors": connectors,
    }


def _save_publish_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    src = payload if isinstance(payload, dict) else {}
    settings = _read_settings()
    publish = settings.get("publish", {})
    if not isinstance(publish, dict):
        publish = {}
    if "connectors" in src:
        existing_connectors = _normalize_publish_connectors(publish.get("connectors", {}))
        incoming_connectors = _normalize_publish_connectors(src.get("connectors", {}))
        publish["connectors"] = _merge_publish_connectors_with_existing(existing_connectors, incoming_connectors)
    settings["publish"] = publish
    _write_settings(settings)
    return _load_publish_settings()


def _mask_secret(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"


_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_AI_PROVIDER_CATALOG: Dict[str, Dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "aliases": ["openai"],
        "default_base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini", "o3-mini"],
        "embedding_models": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
    },
    "anthropic": {
        "label": "Anthropic",
        "aliases": ["anthropic", "claude"],
        "default_base_url": "https://api.anthropic.com",
        "models": ["claude-sonnet-4-6", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"],
        "embedding_models": [],
    },
    "moonshot": {
        "label": "Moonshot / Kimi",
        "aliases": ["moonshot", "kimi"],
        "default_base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "embedding_models": [],
    },
    "qwen": {
        "label": "Qwen",
        "aliases": ["qwen"],
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "embedding_models": [],
    },
    "gemini": {
        "label": "Gemini",
        "aliases": ["gemini"],
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "embedding_models": [],
    },
    "maxmini": {
        "label": "MiniMax",
        "aliases": ["maxmini", "minimax"],
        "default_base_url": "https://api.minimax.chat/v1",
        "models": ["abab6.5s-chat", "abab6.5t-chat", "abab6.5g-chat"],
        "embedding_models": [],
    },
}
_AI_PROVIDER_ALIASES: Dict[str, str] = {}
for _provider_id, _provider_cfg in _AI_PROVIDER_CATALOG.items():
    aliases = _provider_cfg.get("aliases", []) if isinstance(_provider_cfg, dict) else []
    for alias in aliases:
        key = str(alias or "").strip().lower()
        if key:
            _AI_PROVIDER_ALIASES[key] = _provider_id
    _AI_PROVIDER_ALIASES[_provider_id] = _provider_id


def _normalize_ai_provider(provider: Any) -> str:
    key = str(provider or "").strip().lower()
    if not key:
        return ""
    return _AI_PROVIDER_ALIASES.get(key, key)


def _recommended_ai_base_url(provider: Any, model: Any = "") -> str:
    provider_id = _normalize_ai_provider(provider)
    item = _AI_PROVIDER_CATALOG.get(provider_id, {}) if provider_id else {}
    if not isinstance(item, dict):
        return ""
    model_base_urls = item.get("model_base_urls", {})
    if isinstance(model_base_urls, dict):
        picked_model = str(model or "").strip().lower()
        if picked_model:
            for model_id, base_url in model_base_urls.items():
                if picked_model == str(model_id or "").strip().lower():
                    return str(base_url or "").strip()
    return str(item.get("default_base_url", "") or "").strip()


def _ai_catalog_payload() -> Dict[str, Any]:
    providers: List[Dict[str, Any]] = []
    for provider_id, item in _AI_PROVIDER_CATALOG.items():
        if not isinstance(item, dict):
            continue
        providers.append(
            {
                "provider_id": provider_id,
                "label": str(item.get("label", provider_id) or provider_id),
                "aliases": [str(x).strip() for x in item.get("aliases", []) if str(x).strip()],
                "default_base_url": str(item.get("default_base_url", "") or "").strip(),
                "models": [str(x).strip() for x in item.get("models", []) if str(x).strip()],
                "embedding_models": [str(x).strip() for x in item.get("embedding_models", []) if str(x).strip()],
            }
        )
    return {
        "providers": providers,
        "default_provider": "openai",
        "default_embedding_model": _DEFAULT_EMBEDDING_MODEL,
    }


def _ai_secret_ref_name(field_name: str) -> str:
    token = str(field_name or "").strip().lower()
    if not token:
        return ""
    return f"ai.{token}"


def _read_ai_secret_field(settings_ai: Dict[str, Any], field_name: str) -> str:
    if not isinstance(settings_ai, dict):
        return ""
    ref_key = f"{field_name}_ref"
    ref_name = str(settings_ai.get(ref_key, "") or "").strip()
    store_meta = _secret_store.info()
    if ref_name and bool(store_meta.available):
        try:
            from_store = _secret_store.get(ref_name)
        except Exception:
            from_store = ""
        if from_store:
            return str(from_store).strip()
    return str(settings_ai.get(field_name, "") or "").strip()


def _persist_ai_secret_field(settings_ai: Dict[str, Any], field_name: str, incoming_value: str, clear_flag: bool) -> None:
    if not isinstance(settings_ai, dict):
        return
    name = str(field_name or "").strip()
    if not name:
        return
    ref_key = f"{name}_ref"
    ref_name = str(settings_ai.get(ref_key, "") or _ai_secret_ref_name(name)).strip() or _ai_secret_ref_name(name)
    store_meta = _secret_store.info()

    if clear_flag:
        if ref_name and bool(store_meta.available):
            try:
                _secret_store.delete(ref_name)
            except Exception:
                pass
        settings_ai.pop(name, None)
        settings_ai.pop(ref_key, None)
        return

    value = str(incoming_value or "").strip()
    if value:
        if ref_name and bool(store_meta.available):
            try:
                stored = _secret_store.set(ref_name, value)
            except Exception:
                stored = False
            if stored:
                settings_ai[ref_key] = ref_name
                settings_ai.pop(name, None)
                return
        settings_ai[name] = value
        settings_ai.pop(ref_key, None)
        return

    # No new value passed: try to migrate existing legacy plaintext key into secret store.
    legacy_value = str(settings_ai.get(name, "") or "").strip()
    if legacy_value and ref_name and bool(store_meta.available):
        try:
            migrated = _secret_store.set(ref_name, legacy_value)
        except Exception:
            migrated = False
        if migrated:
            settings_ai[ref_key] = ref_name
            settings_ai.pop(name, None)


def _load_ai_settings() -> Dict:
    data = _read_settings().get("ai", {})
    if not isinstance(data, dict):
        data = {}
    provider = _normalize_ai_provider(data.get("provider", ""))
    return {
        "provider": provider or "openai",
        "ai_model": str(data.get("ai_model", "") or "").strip(),
        "embedding_model": str(data.get("embedding_model", "") or "").strip(),
        "ai_base_url": str(data.get("ai_base_url", "") or "").strip(),
        "openai_api_key": _read_ai_secret_field(data, "openai_api_key"),
        "anthropic_api_key": _read_ai_secret_field(data, "anthropic_api_key"),
    }


def _save_ai_settings(payload: Dict) -> Dict:
    settings = _read_settings()
    ai = settings.get("ai", {})
    if not isinstance(ai, dict):
        ai = {}

    provider = _normalize_ai_provider(payload.get("provider", ""))
    model = str(payload.get("ai_model", "") or "").strip()
    embedding_model = str(payload.get("embedding_model", "") or "").strip()
    base_url = str(payload.get("ai_base_url", "") or "").strip()
    if provider:
        ai["provider"] = provider
    elif "provider" in payload:
        ai.pop("provider", None)
    if model:
        ai["ai_model"] = model
    elif "ai_model" in payload:
        ai.pop("ai_model", None)
    if embedding_model:
        ai["embedding_model"] = embedding_model
    elif "embedding_model" in payload:
        ai.pop("embedding_model", None)
    if base_url:
        ai["ai_base_url"] = base_url
    elif "ai_base_url" in payload:
        ai.pop("ai_base_url", None)

    openai_api_key = str(payload.get("openai_api_key", "") or "").strip()
    anthropic_api_key = str(payload.get("anthropic_api_key", "") or "").strip()
    clear_openai = bool(payload.get("clear_openai_api_key", False))
    clear_anthropic = bool(payload.get("clear_anthropic_api_key", False))
    _persist_ai_secret_field(ai, "openai_api_key", openai_api_key, clear_openai)
    _persist_ai_secret_field(ai, "anthropic_api_key", anthropic_api_key, clear_anthropic)

    settings["ai"] = ai
    _write_settings(settings)
    return _load_ai_settings()


def _apply_ai_env(ai: Dict):
    provider = _normalize_ai_provider(ai.get("provider", ""))
    openai_api_key = str(ai.get("openai_api_key", "") or "").strip()
    anthropic_api_key = str(ai.get("anthropic_api_key", "") or "").strip()
    ai_base_url = str(ai.get("ai_base_url", "") or "").strip()
    ai_model = str(ai.get("ai_model", "") or "").strip()
    embedding_model = str(ai.get("embedding_model", "") or "").strip()

    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key
    else:
        os.environ.pop("OPENAI_API_KEY", None)
    if anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_api_key
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    openai_compatible_provider = provider in {"", "openai", "moonshot", "qwen", "gemini", "maxmini"}
    if ai_base_url and openai_compatible_provider:
        os.environ["OPENAI_BASE_URL"] = ai_base_url
    else:
        os.environ.pop("OPENAI_BASE_URL", None)
    if ai_model and openai_compatible_provider:
        os.environ["OPENAI_MODEL"] = ai_model
    else:
        os.environ.pop("OPENAI_MODEL", None)
    if embedding_model:
        os.environ["OPENAI_EMBEDDING_MODEL"] = embedding_model
    else:
        os.environ.pop("OPENAI_EMBEDDING_MODEL", None)


def _public_ai_settings(ai: Dict) -> Dict:
    provider = _normalize_ai_provider(ai.get("provider", "")) or "openai"
    model = str(ai.get("ai_model", "") or "").strip()
    base_url = str(ai.get("ai_base_url", "") or "").strip()
    embedding_model = str(ai.get("embedding_model", "") or "").strip()
    secret_status = _secret_store.public_status()
    return {
        "provider": provider,
        "ai_model": model,
        "embedding_model": embedding_model,
        "embedding_model_resolved": embedding_model or _DEFAULT_EMBEDDING_MODEL,
        "ai_base_url": base_url,
        "recommended_base_url": _recommended_ai_base_url(provider, model),
        "openai_api_key_set": bool(ai.get("openai_api_key")),
        "anthropic_api_key_set": bool(ai.get("anthropic_api_key")),
        "openai_api_key_masked": _mask_secret(ai.get("openai_api_key", "")),
        "anthropic_api_key_masked": _mask_secret(ai.get("anthropic_api_key", "")),
        "secret_storage": secret_status,
        "catalog": _ai_catalog_payload(),
    }


def _default_project_config(extra: Optional[Dict] = None) -> Dict:
    ai = _load_ai_settings()
    config = {
        "use_semantic_index": False,
        "ai_provider": ai.get("provider") or None,
        "ai_base_url": ai.get("ai_base_url") or None,
        "ai_model": ai.get("ai_model") or None,
        "render": dict(RENDER_DEFAULTS),
    }
    if extra:
        config.update(extra)
    return config


def _project_data_path(filename: str) -> Optional[Path]:
    if _project_dir is None:
        return None
    return _project_dir / "data" / filename


def _read_project_json(filename: str, fallback=None):
    p = _project_data_path(filename)
    if p is None or not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _read_agent_task_history() -> List[Dict[str, Any]]:
    raw = _read_project_json("agent_task_history.json", fallback=[])
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    if len(out) > _AGENT_TASK_HISTORY_MAX:
        out = out[-_AGENT_TASK_HISTORY_MAX:]
    return out


def _save_agent_task_history(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                out.append(item)
    if len(out) > _AGENT_TASK_HISTORY_MAX:
        out = out[-_AGENT_TASK_HISTORY_MAX:]
    p = _project_data_path("agent_task_history.json")
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _find_agent_task_history_record(job_id: str) -> Optional[Dict[str, Any]]:
    jid = str(job_id or "").strip()
    if not jid:
        return None
    history = _read_agent_task_history()
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("job_id", "") or "").strip() == jid:
            return deepcopy(item)
    return None


def _custom_workflow_store_path() -> Optional[Path]:
    return _project_data_path("custom_workflows.json")


def _custom_workflow_runs_path() -> Optional[Path]:
    return _project_data_path("custom_workflow_runs.json")


def _normalize_custom_workflow_id(value: Any, fallback: str = "") -> str:
    raw = str(value or "").strip() or str(fallback or "").strip()
    if not raw:
        return ""
    normalized = _normalize_agent_template_id(raw)
    if normalized:
        return normalized
    return f"workflow_{uuid.uuid4().hex[:8]}"


def _parse_custom_workflow_tags(raw: Any) -> List[str]:
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        items = text.replace("，", ",").split(",")
    out: List[str] = []
    seen = set()
    for item in items:
        tag = str(item or "").strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag[:64])
    return out[:20]


def _normalize_custom_workflow_step(step_raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    if not isinstance(step_raw, dict):
        raise ValueError(f"steps[{idx}] 必须是对象")
    node_type = str(step_raw.get("node_type", "action") or "action").strip().lower()
    if node_type not in {"action", "condition"}:
        raise ValueError(f"steps[{idx}].node_type 仅支持 action/condition")
    capability_id = str(step_raw.get("capability_id", "") or "").strip().lower()
    if node_type == "action" and not capability_id:
        raise ValueError(f"steps[{idx}].capability_id 不能为空")
    step_id = _normalize_agent_template_id(step_raw.get("step_id", ""))
    if not step_id:
        step_id = f"step_{idx:02d}"
    action = str(step_raw.get("action", "auto") or "auto").strip().lower()
    if not action:
        action = "auto"
    input_payload = step_raw.get("input", {})
    if input_payload is None:
        input_payload = {}
    if not isinstance(input_payload, dict):
        raise ValueError(f"steps[{idx}].input 必须是对象")
    input_mode_raw = str(step_raw.get("input_mode", "auto") or "auto").strip().lower()
    if input_mode_raw not in {"auto", "project", "inline"}:
        raise ValueError(f"steps[{idx}].input_mode 仅支持 auto/project/inline")
    save_as = _normalize_agent_template_id(step_raw.get("save_as", ""))
    next_step_id = _normalize_agent_template_id(step_raw.get("next_step_id", ""))
    next_on_success = _normalize_agent_template_id(step_raw.get("next_on_success", ""))
    next_on_error = _normalize_agent_template_id(step_raw.get("next_on_error", ""))
    next_on_skip = _normalize_agent_template_id(step_raw.get("next_on_skip", ""))
    return {
        "index": idx,
        "step_id": step_id,
        "node_type": node_type,
        "name": str(step_raw.get("name", "") or "").strip(),
        "description": str(step_raw.get("description", "") or "").strip(),
        "capability_id": capability_id,
        "action": action,
        "input": deepcopy(input_payload),
        "input_mode": input_mode_raw,
        "continue_on_error": _coerce_bool(step_raw.get("continue_on_error", False), default=False),
        "enabled": _coerce_bool(step_raw.get("enabled", True), default=True),
        "save_as": save_as,
        "next_step_id": next_step_id,
        "next_on_success": next_on_success,
        "next_on_error": next_on_error,
        "next_on_skip": next_on_skip,
        "run_if": deepcopy(step_raw.get("run_if", "")),
        "condition": deepcopy(step_raw.get("condition", "")),
    }


def _normalize_custom_workflow_payload(
    payload: Dict[str, Any],
    *,
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    base = existing if isinstance(existing, dict) else {}

    name = str(raw.get("name", base.get("name", "")) or "").strip()
    workflow_id = _normalize_custom_workflow_id(raw.get("workflow_id", base.get("workflow_id", "")), fallback=name)
    if not workflow_id:
        workflow_id = f"workflow_{uuid.uuid4().hex[:8]}"
    if not name:
        name = str(base.get("name", "") or workflow_id).strip() or workflow_id
    description = str(raw.get("description", base.get("description", "")) or "").strip()

    input_mode = str(raw.get("input_mode", base.get("input_mode", "auto")) or "auto").strip().lower()
    if input_mode not in {"auto", "project", "inline"}:
        input_mode = "auto"

    tags = _parse_custom_workflow_tags(raw.get("tags", base.get("tags", [])))
    steps_raw = raw.get("steps", base.get("steps", []))
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("steps 不能为空")
    if len(steps_raw) > _CUSTOM_WORKFLOW_STEP_LIMIT:
        raise ValueError(f"steps 最多支持 {_CUSTOM_WORKFLOW_STEP_LIMIT} 个")

    steps: List[Dict[str, Any]] = []
    seen_step_ids = set()
    for idx, step_raw in enumerate(steps_raw, start=1):
        step = _normalize_custom_workflow_step(step_raw, idx)
        sid = step["step_id"]
        if sid in seen_step_ids:
            raise ValueError(f"steps.step_id 重复: {sid}")
        seen_step_ids.add(sid)
        steps.append(step)

    start_step_id = _normalize_agent_template_id(raw.get("start_step_id", base.get("start_step_id", "")))
    if start_step_id and start_step_id not in seen_step_ids:
        raise ValueError(f"start_step_id 不存在于 steps: {start_step_id}")

    now_iso = datetime.now().isoformat(timespec="seconds")
    created_at = str(base.get("created_at", raw.get("created_at", now_iso)) or now_iso)
    return {
        "workflow_id": workflow_id,
        "name": name[:128],
        "description": description[:500],
        "input_mode": input_mode,
        "start_step_id": start_step_id,
        "tags": tags,
        "steps": steps,
        "created_at": created_at,
        "updated_at": now_iso,
    }


def _read_custom_workflow_store() -> Dict[str, Dict[str, Any]]:
    if _project_dir is None:
        return deepcopy(_custom_workflow_store_mem)

    p = _custom_workflow_store_path()
    raw: Any = {}
    if p is not None and p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    if raw is None:
        raw = {}

    candidates: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        workflows_raw = raw.get("workflows")
        if isinstance(workflows_raw, list):
            candidates.extend([x for x in workflows_raw if isinstance(x, dict)])
        else:
            for key, value in raw.items():
                if not isinstance(value, dict):
                    continue
                item = deepcopy(value)
                item.setdefault("workflow_id", str(key))
                candidates.append(item)
    elif isinstance(raw, list):
        candidates.extend([x for x in raw if isinstance(x, dict)])

    out: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        try:
            normalized = _normalize_custom_workflow_payload(item)
        except Exception:
            continue
        out[normalized["workflow_id"]] = normalized
    return out


def _save_custom_workflow_store(store: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(store, dict):
        for key, value in store.items():
            if not isinstance(value, dict):
                continue
            candidate = deepcopy(value)
            if not str(candidate.get("workflow_id", "") or "").strip():
                candidate["workflow_id"] = str(key or "")
            try:
                normalized = _normalize_custom_workflow_payload(candidate, existing=value)
            except Exception:
                continue
            out[normalized["workflow_id"]] = normalized

    _custom_workflow_store_mem.clear()
    _custom_workflow_store_mem.update(deepcopy(out))

    p = _custom_workflow_store_path()
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "updated_at": datetime.now().isoformat(timespec="seconds"), "workflows": list(out.values())}
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _read_custom_workflow_runs() -> List[Dict[str, Any]]:
    if _project_dir is None:
        return deepcopy(_custom_workflow_runs_mem)
    p = _custom_workflow_runs_path()
    if p is None or not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    if len(out) > _CUSTOM_WORKFLOW_HISTORY_MAX:
        out = out[-_CUSTOM_WORKFLOW_HISTORY_MAX:]
    return out


def _save_custom_workflow_runs(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                out.append(item)
    if len(out) > _CUSTOM_WORKFLOW_HISTORY_MAX:
        out = out[-_CUSTOM_WORKFLOW_HISTORY_MAX:]

    _custom_workflow_runs_mem.clear()
    _custom_workflow_runs_mem.extend(deepcopy(out))

    p = _custom_workflow_runs_path()
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _append_custom_workflow_run(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    with _custom_workflow_lock:
        history = _read_custom_workflow_runs()
        history.append(record if isinstance(record, dict) else {})
        return _save_custom_workflow_runs(history)


def _find_custom_workflow_run(run_id: str) -> Optional[Dict[str, Any]]:
    rid = str(run_id or "").strip()
    if not rid:
        return None
    runs = _read_custom_workflow_runs()
    for item in reversed(runs):
        if not isinstance(item, dict):
            continue
        if str(item.get("run_id", "") or "").strip() == rid:
            return deepcopy(item)
    return None


def _build_custom_workflow_catalog() -> List[Dict[str, Any]]:
    route_map = _agent_capability_route_map()
    catalog: List[Dict[str, Any]] = []
    for capability_id in sorted(route_map.keys()):
        routes = route_map.get(capability_id, {})
        if not isinstance(routes, dict) or not routes:
            continue
        actions: List[Dict[str, str]] = []
        for action, route in routes.items():
            route_text = str(route or "").strip()
            if not route_text:
                continue
            method, endpoint = route_text.split(" ", 1) if " " in route_text else ("POST", route_text)
            actions.append(
                {
                    "action": str(action or "").strip().lower(),
                    "method": str(method or "POST").strip().upper(),
                    "endpoint": str(endpoint or "").strip(),
                }
            )
        if not actions:
            continue
        try:
            primary = _resolve_agent_primary_call(capability_id=capability_id, routes=routes, action="auto")
        except Exception:
            primary = {"method": actions[0]["method"], "endpoint": actions[0]["endpoint"]}
        catalog.append(
            {
                "capability_id": capability_id,
                "actions": actions,
                "default_action": "auto",
                "primary_call": primary,
                "supports_input_mode": _capability_supports_input_mode(capability_id),
            }
        )
    return catalog


def _extract_agent_replay_spec(replay_raw: Any) -> Dict[str, Any]:
    raw = replay_raw if isinstance(replay_raw, dict) else {}
    endpoint = str(raw.get("endpoint", "") or "").strip()
    if not endpoint:
        return {}
    method = str(raw.get("method", "POST") or "POST").strip().upper()
    if method not in {"GET", "POST"}:
        method = "POST"
    payload = deepcopy(raw.get("payload", {})) if isinstance(raw.get("payload"), dict) else {}
    request_context = _normalize_agent_replay_context(raw.get("request_context", {}))
    return {
        "method": method,
        "endpoint": endpoint,
        "payload": payload,
        "request_context": request_context,
    }


def _extract_template_ids_from_value(value: Any, max_count: int = 64) -> List[str]:
    found: List[str] = []
    seen = set()

    def _push(text: str):
        tid = _normalize_agent_template_id(str(text or "").strip())
        if not tid or tid in seen:
            return
        seen.add(tid)
        found.append(tid)

    def _walk(node: Any):
        if len(found) >= max_count:
            return
        if isinstance(node, dict):
            for key, val in node.items():
                key_text = str(key or "").strip().lower()
                if key_text in {"template_id", "base_template_id"}:
                    if isinstance(val, str):
                        _push(val)
                    elif isinstance(val, list):
                        for x in val:
                            if isinstance(x, str):
                                _push(x)
                elif key_text in {"template_ids", "templates"} and isinstance(val, list):
                    for x in val:
                        if isinstance(x, str):
                            _push(x)
                        elif isinstance(x, dict):
                            inner_tid = x.get("template_id")
                            if isinstance(inner_tid, str):
                                _push(inner_tid)
                _walk(val)
                if len(found) >= max_count:
                    return
        elif isinstance(node, list):
            for item in node:
                _walk(item)
                if len(found) >= max_count:
                    return

    _walk(value)
    return found


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _duration_from_iso_range(started_at: Any, finished_at: Any) -> float:
    begin = _parse_iso_datetime(started_at)
    end = _parse_iso_datetime(finished_at)
    if begin is None or end is None:
        return 0.0
    return max((end - begin).total_seconds(), 0.0)


def _trimmed_avg(values: List[float]) -> float:
    nums = sorted(float(x) for x in values if float(x) > 0.0)
    if not nums:
        return 0.0
    if len(nums) >= 10:
        trim = max(1, int(len(nums) * 0.1))
        nums = nums[trim:-trim] or nums
    return max(sum(nums) / max(len(nums), 1), 0.0)


def _refresh_eta_history_cache(*, limit: int = 800, ttl_seconds: float = 30.0) -> Dict[str, Any]:
    now_ts = time.time()
    with _eta_history_lock:
        updated_at = float(_eta_history_cache.get("updated_at", 0.0) or 0.0)
        if now_ts - updated_at <= max(float(ttl_seconds), 1.0):
            return deepcopy(_eta_history_cache)

    try:
        rows = _ensure_job_store().list_jobs(limit=limit)
    except Exception:
        rows = []
    if not isinstance(rows, list):
        rows = []

    durations_by_kind: Dict[str, List[float]] = {}
    all_durations: List[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "") or "").strip().lower() != "done":
            continue
        d = _duration_from_iso_range(row.get("started_at"), row.get("finished_at"))
        if d < 2.0:
            continue
        kind = str(row.get("kind", "") or "").strip()
        all_durations.append(d)
        bucket = durations_by_kind.setdefault(kind, [])
        if len(bucket) < 200:
            bucket.append(d)

    avg_by_kind = {kind: _trimmed_avg(vals) for kind, vals in durations_by_kind.items()}
    payload = {
        "updated_at": now_ts,
        "avg_by_kind": avg_by_kind,
        "fallback_avg": _trimmed_avg(all_durations),
    }
    with _eta_history_lock:
        _eta_history_cache.update(payload)
        return deepcopy(_eta_history_cache)


def _historical_avg_duration_for_kind(kind: Any, *, ttl_seconds: float = 30.0) -> float:
    snapshot = _refresh_eta_history_cache(ttl_seconds=ttl_seconds)
    avg_by_kind = snapshot.get("avg_by_kind", {})
    if not isinstance(avg_by_kind, dict):
        avg_by_kind = {}
    kind_text = str(kind or "").strip()
    if kind_text:
        exact = avg_by_kind.get(kind_text)
        if isinstance(exact, (int, float)) and float(exact) > 0:
            return float(exact)
    fallback_avg = snapshot.get("fallback_avg", 0.0)
    try:
        return max(float(fallback_avg), 0.0)
    except Exception:
        return 0.0


def _estimate_job_eta(job: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict):
        return {"available": False, "remaining_seconds": None, "source": "none", "confidence": 0.0}

    status = str(job.get("status", "") or "").strip().lower()
    kind = str(job.get("kind", "") or "").strip()
    avg_history = _historical_avg_duration_for_kind(kind)

    if status in {"done", "error", "cancelled", "interrupted"}:
        return {
            "available": False,
            "remaining_seconds": 0,
            "source": "finished",
            "confidence": 1.0,
            "historical_avg_seconds": int(round(avg_history)) if avg_history > 0 else None,
        }

    if status == "queued":
        try:
            queue_position = int(job.get("queue_position", 0) or 0)
        except Exception:
            queue_position = 0
        if avg_history <= 0:
            return {
                "available": False,
                "remaining_seconds": None,
                "source": "queue_unknown",
                "confidence": 0.0,
                "historical_avg_seconds": None,
                "queue_position": queue_position,
            }
        wait_seconds = avg_history * max(queue_position - 1, 0)
        return {
            "available": True,
            "remaining_seconds": int(max(round(wait_seconds), 0)),
            "source": "history_queue",
            "confidence": 0.55,
            "historical_avg_seconds": int(round(avg_history)),
            "queue_position": queue_position,
        }

    if status != "running":
        return {"available": False, "remaining_seconds": None, "source": "unknown", "confidence": 0.0}

    started = _parse_iso_datetime(job.get("started_at"))
    elapsed = 0.0
    if started is not None:
        elapsed = max((datetime.now() - started).total_seconds(), 0.0)

    try:
        progress = int(job.get("progress", 0) or 0)
    except Exception:
        progress = 0
    progress = max(0, min(progress, 100))

    by_progress: Optional[float] = None
    if elapsed > 0 and progress >= 2 and progress < 100:
        by_progress = elapsed * max(100 - progress, 0) / max(progress, 1)

    by_history: Optional[float] = None
    if avg_history > 0:
        by_history = max(avg_history - elapsed, 0.0)

    remaining = None
    source = "none"
    confidence = 0.0

    if by_progress is not None and by_history is not None:
        # Blend historical signal and live progress; progress gets more weight once >20%.
        progress_weight = 0.7 if progress >= 20 else 0.5
        history_weight = 1.0 - progress_weight
        remaining = (by_progress * progress_weight) + (by_history * history_weight)
        source = "blended"
        confidence = 0.78 if progress >= 20 else 0.62
    elif by_progress is not None:
        remaining = by_progress
        source = "progress"
        confidence = 0.58 if progress >= 20 else 0.42
    elif by_history is not None:
        remaining = by_history
        source = "history"
        confidence = 0.5

    if remaining is None:
        return {
            "available": False,
            "remaining_seconds": None,
            "source": source,
            "confidence": confidence,
            "elapsed_seconds": int(round(elapsed)),
            "historical_avg_seconds": int(round(avg_history)) if avg_history > 0 else None,
        }

    remaining = max(min(float(remaining), 72 * 3600), 0.0)
    return {
        "available": True,
        "remaining_seconds": int(round(remaining)),
        "source": source,
        "confidence": round(confidence, 3),
        "elapsed_seconds": int(round(elapsed)),
        "historical_avg_seconds": int(round(avg_history)) if avg_history > 0 else None,
        "progress": progress,
    }


def _build_agent_task_history_record(job_id: str, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _project_dir is None or not isinstance(job, dict):
        return None
    kind = str(job.get("kind", "") or "")
    if kind not in {"agent_task", "agent_skill"}:
        return None
    meta = job.get("meta", {}) if isinstance(job.get("meta"), dict) else {}
    result = job.get("result", {}) if isinstance(job.get("result"), dict) else {}
    status = str(job.get("status", "unknown") or "unknown").strip().lower()
    started_at = str(job.get("started_at", "") or "")
    finished_at = str(job.get("finished_at", "") or "")
    error_text = str(job.get("error", "") or "")

    def _safe_int(v: Any) -> int:
        try:
            parsed = int(v)
        except Exception:
            parsed = 0
        return max(parsed, 0)

    def _safe_float(v: Any) -> float:
        try:
            parsed = float(v)
        except Exception:
            parsed = 0.0
        return max(parsed, 0.0)

    task_mode = "single_capability"
    strategy = ""
    capability_ids: List[str] = []
    skill_ids: List[str] = []
    total_steps = 1
    success_steps = 0
    failed_steps = 0
    skipped_steps = 0
    retry_count = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_cost = 0.0
    failed_nodes: List[Dict[str, str]] = []
    step_summaries: List[Dict[str, Any]] = []

    if kind == "agent_skill":
        task_mode = "skill_invoke"
        sid = str(result.get("skill_id", "") or "").strip()
        cid = str(result.get("capability_id", "") or "").strip()
        if sid:
            skill_ids.append(sid)
        if cid:
            capability_ids.append(cid)
        attempts = _safe_int(result.get("attempts", 1))
        retry_count = max(attempts - 1, 0)
        usage_tokens = result.get("usage_tokens", {}) if isinstance(result.get("usage_tokens"), dict) else {}
        prompt_tokens += _safe_int(usage_tokens.get("prompt_tokens", 0))
        completion_tokens += _safe_int(usage_tokens.get("completion_tokens", 0))
        estimated = result.get("estimated_cost", {}) if isinstance(result.get("estimated_cost"), dict) else {}
        total_cost += _safe_float(estimated.get("total_cost_usd", 0.0))
        step_summaries.append({
            "step_id": str(result.get("invoke_id", "") or "invoke"),
            "index": 1,
            "skill_id": sid,
            "capability_id": cid,
            "status": status if status in {"done", "error", "cancelled"} else "unknown",
            "error": error_text or str(result.get("error", "") or ""),
            "continue_on_error": False,
            "duration_seconds": round(_safe_float(result.get("duration_seconds", 0.0)), 4),
            "prompt_tokens": _safe_int(usage_tokens.get("prompt_tokens", 0)),
            "completion_tokens": _safe_int(usage_tokens.get("completion_tokens", 0)),
            "estimated_cost_usd": round(_safe_float(estimated.get("total_cost_usd", 0.0)), 8),
            "condition": {},
        })
        if status == "done":
            success_steps = 1
        elif status == "cancelled":
            skipped_steps = 1
        else:
            failed_steps = 1
            failed_nodes.append({
                "skill_id": sid,
                "capability_id": cid,
                "error": error_text or str(result.get("error", "") or ""),
            })
    elif str(result.get("mode", "") or "").strip().lower() == "skill_sequence":
        task_mode = "skill_sequence"
        strategy = str(result.get("strategy", "") or "").strip().lower()
        total_steps = _safe_int(result.get("total_steps", 0))
        success_steps = _safe_int(result.get("success_steps", 0))
        failed_steps = _safe_int(result.get("failed_steps", 0))
        skipped_steps = _safe_int(result.get("skipped_steps", 0))
        steps = result.get("steps", []) if isinstance(result.get("steps"), list) else []
        if total_steps <= 0:
            total_steps = len(steps)
        for item in steps:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("skill_id", "") or "").strip()
            cid = str(item.get("capability_id", "") or "").strip()
            step_status = str(item.get("status", "") or "").strip().lower() or "unknown"
            if sid and sid not in skill_ids:
                skill_ids.append(sid)
            if cid and cid not in capability_ids:
                capability_ids.append(cid)
            retry_count += max(_safe_int(item.get("attempts", 1)) - 1, 0)
            usage_tokens = item.get("usage_tokens", {}) if isinstance(item.get("usage_tokens"), dict) else {}
            prompt_tokens += _safe_int(usage_tokens.get("prompt_tokens", 0))
            completion_tokens += _safe_int(usage_tokens.get("completion_tokens", 0))
            estimated = item.get("estimated_cost", {}) if isinstance(item.get("estimated_cost"), dict) else {}
            total_cost += _safe_float(estimated.get("total_cost_usd", 0.0))
            step_summaries.append({
                "step_id": str(item.get("step_id", "") or ""),
                "index": _safe_int(item.get("index", len(step_summaries) + 1)),
                "skill_id": sid,
                "capability_id": cid,
                "status": step_status,
                "error": str(item.get("error", "") or ""),
                "continue_on_error": bool(item.get("continue_on_error", False)),
                "duration_seconds": round(_safe_float(item.get("duration_seconds", 0.0)), 4),
                "prompt_tokens": _safe_int(usage_tokens.get("prompt_tokens", 0)),
                "completion_tokens": _safe_int(usage_tokens.get("completion_tokens", 0)),
                "estimated_cost_usd": round(_safe_float(estimated.get("total_cost_usd", 0.0)), 8),
                "condition": deepcopy(item.get("condition", {})) if isinstance(item.get("condition"), dict) else {},
            })
            if step_status == "error":
                failed_nodes.append({
                    "skill_id": sid,
                    "capability_id": cid,
                    "error": str(item.get("error", "") or ""),
                })
    else:
        task_mode = "single_capability"
        cid = str(result.get("capability_id", "") or "").strip()
        if cid:
            capability_ids.append(cid)
        step_summaries.append({
            "step_id": str(result.get("task_id", "") or "task"),
            "index": 1,
            "skill_id": "",
            "capability_id": cid,
            "status": status if status in {"done", "error", "cancelled"} else "unknown",
            "error": error_text or str(result.get("error", "") or ""),
            "continue_on_error": False,
            "duration_seconds": round(_safe_float(result.get("duration_seconds", 0.0)), 4),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost_usd": 0.0,
            "condition": {},
        })
        total_steps = 1
        if status == "done":
            success_steps = 1
        elif status == "cancelled":
            skipped_steps = 1
        else:
            failed_steps = 1
            failed_nodes.append({
                "skill_id": "",
                "capability_id": cid,
                "error": error_text or str(result.get("error", "") or ""),
            })

    template_hits = _extract_template_ids_from_value({
        "meta": meta,
        "result": result,
    })
    replay_spec = _extract_agent_replay_spec(meta.get("replay", {}))
    duration_seconds = _safe_float(result.get("duration_seconds", 0.0))
    if duration_seconds <= 0.0:
        duration_seconds = _duration_from_iso_range(started_at, finished_at)

    return {
        "job_id": str(job_id or ""),
        "kind": kind,
        "status": status,
        "task_mode": task_mode,
        "strategy": strategy,
        "actor_type": str(meta.get("actor_type", "") or ""),
        "actor_id": str(meta.get("actor_id", "") or ""),
        "trace_id": str(meta.get("trace_id", "") or ""),
        "capability_ids": capability_ids,
        "skill_ids": skill_ids,
        "total_steps": max(total_steps, 0),
        "success_steps": max(success_steps, 0),
        "failed_steps": max(failed_steps, 0),
        "skipped_steps": max(skipped_steps, 0),
        "retry_count": max(retry_count, 0),
        "prompt_tokens": max(prompt_tokens, 0),
        "completion_tokens": max(completion_tokens, 0),
        "total_tokens": max(prompt_tokens + completion_tokens, 0),
        "estimated_cost_usd": round(max(total_cost, 0.0), 8),
        "duration_seconds": round(max(duration_seconds, 0.0), 4),
        "template_hits": template_hits,
        "template_hit_count": len(template_hits),
        "replay_supported": bool(replay_spec),
        "replay": replay_spec,
        "failed_nodes": failed_nodes,
        "step_summaries": step_summaries,
        "error": error_text,
        "started_at": started_at,
        "finished_at": finished_at,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
    }


def _record_agent_task_history_from_job(job_id: str):
    if _project_dir is None:
        return
    job = _jobs.get(job_id)
    if not isinstance(job, dict):
        return
    record = _build_agent_task_history_record(job_id, job)
    if not isinstance(record, dict):
        return
    with _agent_history_lock:
        history = _read_agent_task_history()
        history.append(record)
        _save_agent_task_history(history)


def _parse_agent_history_filter_tokens(raw: Any) -> List[str]:
    text = str(raw or "").replace("，", ",")
    out: List[str] = []
    seen = set()
    for token in text.split(","):
        item = str(token or "").strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _agent_history_anchor_time(item: Dict[str, Any]) -> Optional[datetime]:
    if not isinstance(item, dict):
        return None
    for key in ("finished_at", "started_at", "recorded_at"):
        dt = _parse_iso_datetime(item.get(key))
        if dt is not None:
            return dt
    return None


def _filter_agent_task_history(
    history: List[Dict[str, Any]],
    *,
    actor_id: str = "",
    statuses: Optional[List[str]] = None,
    task_modes: Optional[List[str]] = None,
    kinds: Optional[List[str]] = None,
    capability_id: str = "",
    skill_id: str = "",
    trace_id: str = "",
    replay_supported: Optional[bool] = None,
    since: Any = None,
    until: Any = None,
) -> List[Dict[str, Any]]:
    items = [x for x in history if isinstance(x, dict)]
    status_set = {str(x or "").strip().lower() for x in (statuses or []) if str(x or "").strip()}
    mode_set = {str(x or "").strip().lower() for x in (task_modes or []) if str(x or "").strip()}
    kind_set = {str(x or "").strip().lower() for x in (kinds or []) if str(x or "").strip()}
    actor_text = str(actor_id or "").strip()
    capability_text = str(capability_id or "").strip().lower()
    skill_text = str(skill_id or "").strip().lower()
    trace_text = str(trace_id or "").strip()
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)

    out: List[Dict[str, Any]] = []
    for item in items:
        if actor_text and str(item.get("actor_id", "") or "").strip() != actor_text:
            continue
        if status_set:
            status_val = str(item.get("status", "") or "").strip().lower()
            if status_val not in status_set:
                continue
        if mode_set:
            mode_val = str(item.get("task_mode", "") or "").strip().lower()
            if mode_val not in mode_set:
                continue
        if kind_set:
            kind_val = str(item.get("kind", "") or "").strip().lower()
            if kind_val not in kind_set:
                continue
        if capability_text:
            capability_ids = item.get("capability_ids", [])
            capability_values = capability_ids if isinstance(capability_ids, list) else []
            capability_ok = any(str(x or "").strip().lower() == capability_text for x in capability_values)
            if not capability_ok:
                continue
        if skill_text:
            skill_ids = item.get("skill_ids", [])
            skill_values = skill_ids if isinstance(skill_ids, list) else []
            skill_ok = any(str(x or "").strip().lower() == skill_text for x in skill_values)
            if not skill_ok:
                continue
        if trace_text and str(item.get("trace_id", "") or "").strip() != trace_text:
            continue
        if replay_supported is not None and bool(item.get("replay_supported", False)) != bool(replay_supported):
            continue

        item_time = _agent_history_anchor_time(item)
        if since_dt is not None and (item_time is None or item_time < since_dt):
            continue
        if until_dt is not None and (item_time is None or item_time > until_dt):
            continue
        out.append(item)
    return out


def _build_agent_task_export_snapshot(
    job_id: str,
    *,
    include_logs: bool = True,
    include_result: bool = True,
) -> Optional[Dict[str, Any]]:
    jid = str(job_id or "").strip()
    if not jid:
        return None

    live_job = _jobs.get(jid)
    if isinstance(live_job, dict) and live_job.get("kind") in {"agent_task", "agent_skill"}:
        summary = _build_agent_task_history_record(jid, live_job)
        payload: Dict[str, Any] = {
            "job_id": jid,
            "source": "memory",
            "summary": summary if isinstance(summary, dict) else {},
            "status": str(live_job.get("status", "unknown") or "unknown"),
            "kind": str(live_job.get("kind", "") or ""),
            "started_at": live_job.get("started_at"),
            "finished_at": live_job.get("finished_at"),
            "error": live_job.get("error"),
            "meta": deepcopy(live_job.get("meta", {})) if isinstance(live_job.get("meta"), dict) else {},
        }
        if include_logs:
            payload["log"] = list(live_job.get("log", []))
        if include_result:
            payload["result"] = deepcopy(live_job.get("result", {})) if isinstance(live_job.get("result"), dict) else {}
        return payload

    history_item = _find_agent_task_history_record(jid)
    if not isinstance(history_item, dict):
        return None
    return {
        "job_id": jid,
        "source": "history",
        "summary": history_item,
        "status": str(history_item.get("status", "unknown") or "unknown"),
        "kind": str(history_item.get("kind", "") or ""),
        "started_at": history_item.get("started_at"),
        "finished_at": history_item.get("finished_at"),
        "error": history_item.get("error", ""),
    }


def _build_chain_view_from_history_item(history_item: Dict[str, Any]) -> Dict[str, Any]:
    item = history_item if isinstance(history_item, dict) else {}
    mode = str(item.get("task_mode", "") or "single_capability").strip().lower() or "single_capability"
    strategy = str(item.get("strategy", "") or "").strip().lower()
    status = str(item.get("status", "") or "unknown").strip().lower()
    if status == "done":
        overall_status = "done"
    elif status == "error":
        overall_status = "error"
    elif status == "cancelled":
        overall_status = "cancelled"
    else:
        overall_status = "unknown"

    step_summaries = item.get("step_summaries", [])
    steps = step_summaries if isinstance(step_summaries, list) else []
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    known_step_ids = set()

    if mode == "skill_sequence" and steps:
        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("step_id", "") or f"step_{idx:02d}")
            known_step_ids.add(step_id)
            nodes.append({
                "node_id": step_id,
                "node_type": "skill",
                "index": max(int(step.get("index", idx) or idx), 1),
                "status": str(step.get("status", "unknown") or "unknown").strip().lower() or "unknown",
                "skill_id": str(step.get("skill_id", "") or ""),
                "capability_id": str(step.get("capability_id", "") or ""),
                "continue_on_error": bool(step.get("continue_on_error", False)),
                "duration_seconds": round(max(float(step.get("duration_seconds", 0.0) or 0.0), 0.0), 4),
                "prompt_tokens": max(int(step.get("prompt_tokens", 0) or 0), 0),
                "completion_tokens": max(int(step.get("completion_tokens", 0) or 0), 0),
                "estimated_cost_usd": round(max(float(step.get("estimated_cost_usd", 0.0) or 0.0), 0.0), 8),
                "error": str(step.get("error", "") or ""),
                "condition": deepcopy(step.get("condition", {})) if isinstance(step.get("condition"), dict) else {},
            })

        for idx, node in enumerate(nodes):
            node_id = str(node.get("node_id", "") or "")
            condition = node.get("condition", {}) if isinstance(node.get("condition"), dict) else {}
            depends_on_raw = condition.get("depends_on", [])
            depends_on = depends_on_raw if isinstance(depends_on_raw, list) else []
            deps_added = False
            for dep in depends_on:
                dep_id = str(dep or "").strip()
                if not dep_id or dep_id not in known_step_ids:
                    continue
                edges.append({"from": dep_id, "to": node_id, "type": "condition_depends_on"})
                deps_added = True
            if not deps_added and strategy in {"sequential", "conditional"} and idx > 0:
                prev_node_id = str(nodes[idx - 1].get("node_id", "") or "")
                if prev_node_id:
                    edges.append({"from": prev_node_id, "to": node_id, "type": "sequence"})
    elif mode == "skill_sequence":
        total_steps = max(int(item.get("total_steps", 0) or 0), 0)
        success_steps = max(int(item.get("success_steps", 0) or 0), 0)
        failed_steps = max(int(item.get("failed_steps", 0) or 0), 0)
        skipped_steps = max(int(item.get("skipped_steps", 0) or 0), 0)
        if total_steps <= 0:
            total_steps = max(success_steps + failed_steps + skipped_steps, 1)
        statuses = (["done"] * success_steps) + (["error"] * failed_steps) + (["skipped"] * skipped_steps)
        if len(statuses) < total_steps:
            statuses.extend(["unknown"] * (total_steps - len(statuses)))
        capability_first = str((item.get("capability_ids", [""])[0] if isinstance(item.get("capability_ids"), list) and item.get("capability_ids") else "") or "")
        skill_first = str((item.get("skill_ids", [""])[0] if isinstance(item.get("skill_ids"), list) and item.get("skill_ids") else "") or "")
        for idx in range(total_steps):
            nodes.append({
                "node_id": f"step_{idx + 1:02d}",
                "node_type": "skill",
                "index": idx + 1,
                "status": statuses[idx],
                "skill_id": skill_first,
                "capability_id": capability_first,
                "continue_on_error": False,
                "duration_seconds": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "error": "",
                "condition": {},
            })
        if total_steps > 1 and strategy in {"", "sequential", "conditional"}:
            for idx in range(1, total_steps):
                edges.append({"from": f"step_{idx:02d}", "to": f"step_{idx + 1:02d}", "type": "sequence"})
    elif mode == "skill_invoke":
        nodes.append({
            "node_id": str(item.get("job_id", "") or "invoke"),
            "node_type": "skill",
            "status": status,
            "skill_id": str((item.get("skill_ids", [""])[0] if isinstance(item.get("skill_ids"), list) and item.get("skill_ids") else "") or ""),
            "capability_id": str((item.get("capability_ids", [""])[0] if isinstance(item.get("capability_ids"), list) and item.get("capability_ids") else "") or ""),
            "duration_seconds": round(max(float(item.get("duration_seconds", 0.0) or 0.0), 0.0), 4),
            "prompt_tokens": max(int(item.get("prompt_tokens", 0) or 0), 0),
            "completion_tokens": max(int(item.get("completion_tokens", 0) or 0), 0),
            "estimated_cost_usd": round(max(float(item.get("estimated_cost_usd", 0.0) or 0.0), 0.0), 8),
            "error": str(item.get("error", "") or ""),
        })
    else:
        nodes.append({
            "node_id": str(item.get("job_id", "") or "task"),
            "node_type": "capability",
            "status": status,
            "skill_id": "",
            "capability_id": str((item.get("capability_ids", [""])[0] if isinstance(item.get("capability_ids"), list) and item.get("capability_ids") else "") or ""),
            "duration_seconds": round(max(float(item.get("duration_seconds", 0.0) or 0.0), 0.0), 4),
            "prompt_tokens": max(int(item.get("prompt_tokens", 0) or 0), 0),
            "completion_tokens": max(int(item.get("completion_tokens", 0) or 0), 0),
            "estimated_cost_usd": round(max(float(item.get("estimated_cost_usd", 0.0) or 0.0), 0.0), 8),
            "error": str(item.get("error", "") or ""),
        })

    status_done = sum(1 for n in nodes if str(n.get("status", "")).lower() == "done")
    status_error = sum(1 for n in nodes if str(n.get("status", "")).lower() == "error")
    status_skipped = sum(1 for n in nodes if str(n.get("status", "")).lower() == "skipped")
    if nodes and status_error > 0:
        overall_status = "error"
    elif nodes and status_done == len(nodes):
        overall_status = "done"
    elif nodes and (status_done + status_skipped) == len(nodes):
        overall_status = "partial"

    total_prompt = sum(max(int(n.get("prompt_tokens", 0) or 0), 0) for n in nodes)
    total_completion = sum(max(int(n.get("completion_tokens", 0) or 0), 0) for n in nodes)
    total_cost = sum(max(float(n.get("estimated_cost_usd", 0.0) or 0.0), 0.0) for n in nodes)

    item_prompt = max(int(item.get("prompt_tokens", 0) or 0), 0)
    item_completion = max(int(item.get("completion_tokens", 0) or 0), 0)
    item_cost = max(float(item.get("estimated_cost_usd", 0.0) or 0.0), 0.0)
    if total_prompt <= 0 and item_prompt > 0:
        total_prompt = item_prompt
    if total_completion <= 0 and item_completion > 0:
        total_completion = item_completion
    if total_cost <= 0.0 and item_cost > 0.0:
        total_cost = item_cost

    return {
        "mode": mode,
        "overall_status": overall_status,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "counts": {
            "done": status_done,
            "error": status_error,
            "skipped": status_skipped,
            "other": max(len(nodes) - status_done - status_error - status_skipped, 0),
        },
        "totals": {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "estimated_cost_usd": round(total_cost, 8),
        },
        "nodes": nodes,
        "edges": edges,
    }


def _build_agent_observability_summary(history: List[Dict[str, Any]], *, top_n: int = 5) -> Dict[str, Any]:
    items = [x for x in history if isinstance(x, dict)]
    total = len(items)
    if total <= 0:
        return {
            "total_tasks": 0,
            "status_counts": {"done": 0, "error": 0, "cancelled": 0, "other": 0},
            "rates": {
                "success_rate": 0.0,
                "error_rate": 0.0,
                "cancel_rate": 0.0,
                "retry_rate": 0.0,
                "template_hit_rate": 0.0,
            },
            "averages": {
                "duration_seconds": 0.0,
                "retry_count": 0.0,
                "total_tokens": 0.0,
                "estimated_cost_usd": 0.0,
            },
            "mode_counts": {},
            "top_templates": [],
            "failed_top": [],
        }

    status_counts = {"done": 0, "error": 0, "cancelled": 0, "other": 0}
    mode_counts: Dict[str, int] = {}
    retry_tasks = 0
    template_hit_tasks = 0
    total_retry = 0
    total_duration = 0.0
    total_tokens = 0
    total_cost = 0.0
    template_counter: Dict[str, int] = {}
    failed_counter: Dict[str, Dict[str, Any]] = {}

    for item in items:
        status = str(item.get("status", "") or "").strip().lower()
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts["other"] += 1

        mode = str(item.get("task_mode", "") or "unknown").strip().lower() or "unknown"
        mode_counts[mode] = int(mode_counts.get(mode, 0)) + 1

        retry_count = max(int(item.get("retry_count", 0) or 0), 0)
        if retry_count > 0:
            retry_tasks += 1
        total_retry += retry_count

        total_duration += max(float(item.get("duration_seconds", 0.0) or 0.0), 0.0)
        total_tokens += max(int(item.get("total_tokens", 0) or 0), 0)
        total_cost += max(float(item.get("estimated_cost_usd", 0.0) or 0.0), 0.0)

        template_hits = item.get("template_hits", [])
        if isinstance(template_hits, list) and template_hits:
            template_hit_tasks += 1
            for tid in template_hits:
                k = str(tid or "").strip()
                if not k:
                    continue
                template_counter[k] = int(template_counter.get(k, 0)) + 1

        failed_nodes = item.get("failed_nodes", [])
        if isinstance(failed_nodes, list):
            for node in failed_nodes:
                if not isinstance(node, dict):
                    continue
                sid = str(node.get("skill_id", "") or "").strip()
                cid = str(node.get("capability_id", "") or "").strip()
                err = str(node.get("error", "") or "").strip()
                label = sid or cid or "unknown"
                if err:
                    label = f"{label}|{err[:80]}"
                bucket = failed_counter.get(label)
                if not isinstance(bucket, dict):
                    bucket = {
                        "skill_id": sid,
                        "capability_id": cid,
                        "error": err[:120],
                        "count": 0,
                    }
                    failed_counter[label] = bucket
                bucket["count"] = int(bucket.get("count", 0)) + 1

    top_templates = [
        {"template_id": k, "count": v}
        for k, v in sorted(template_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:max(int(top_n), 1)]
    ]
    failed_top = sorted(
        failed_counter.values(),
        key=lambda x: (-int(x.get("count", 0) or 0), str(x.get("skill_id", "") or ""), str(x.get("capability_id", "") or "")),
    )[:max(int(top_n), 1)]

    return {
        "total_tasks": total,
        "status_counts": status_counts,
        "rates": {
            "success_rate": round(float(status_counts["done"]) / float(total), 4),
            "error_rate": round(float(status_counts["error"]) / float(total), 4),
            "cancel_rate": round(float(status_counts["cancelled"]) / float(total), 4),
            "retry_rate": round(float(retry_tasks) / float(total), 4),
            "template_hit_rate": round(float(template_hit_tasks) / float(total), 4),
        },
        "averages": {
            "duration_seconds": round(float(total_duration) / float(total), 4),
            "retry_count": round(float(total_retry) / float(total), 4),
            "total_tokens": round(float(total_tokens) / float(total), 2),
            "estimated_cost_usd": round(float(total_cost) / float(total), 8),
        },
        "totals": {
            "duration_seconds": round(total_duration, 4),
            "retry_count": int(total_retry),
            "total_tokens": int(total_tokens),
            "estimated_cost_usd": round(total_cost, 8),
        },
        "mode_counts": mode_counts,
        "top_templates": top_templates,
        "failed_top": failed_top,
    }


def _read_script_json() -> Dict:
    if _project_dir is None:
        return {}
    for name in ("script_matched.json", "script_draft.json"):
        p = _project_data_path(name)
        if p is not None and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def _slugify(text: str) -> str:
    raw = str(text or "").strip().lower()
    cleaned = []
    for ch in raw:
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in {"-", "_", " ", "/"}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:64] or "topic"


def _extract_material_semantics(materials: Dict, limit: int = 80) -> List[Dict]:
    out: List[Dict] = []
    for _, vdata in materials.items():
        sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic"), dict) else {}
        scene = (
            vdata.get("analysis", {})
            .get("local_analysis", {})
            .get("scene", {})
        )
        item = {
            "setting": sem.get("setting") or "",
            "activity": sem.get("activity") or "",
            "mood": sem.get("mood") or scene.get("mood") or "",
            "time_of_day": sem.get("time_of_day") or "",
            "weather": sem.get("weather") or "",
            "narrative_role": sem.get("narrative_role") or "",
        }
        if any(str(v).strip() for v in item.values()):
            out.append(item)
        if len(out) >= max(int(limit), 1):
            break
    return out


def _parse_platforms(payload_value) -> List[str]:
    if isinstance(payload_value, list):
        return [str(x).strip().lower() for x in payload_value if str(x).strip()]
    text = str(payload_value or "").strip()
    if not text:
        return []
    return [x.strip().lower() for x in text.replace("，", ",").split(",") if x.strip()]


def _parse_capability_input_mode(raw_value: Any, default: str = "project") -> str:
    mode = str(raw_value or default).strip().lower()
    if mode not in {"inline", "project"}:
        mode = default if default in {"inline", "project"} else "project"
    return mode


def _request_json_any_method() -> Dict[str, Any]:
    try:
        payload = request.get_json(silent=True)
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else {}


def _capability_base_dir(input_mode: str) -> Path:
    if input_mode == "project" and _project_dir is not None:
        return _project_dir
    if _project_dir is not None:
        return _project_dir
    return Path.cwd()


def _resolve_path_with_base(path_raw: str, *, base_dir: Optional[Path]) -> Path:
    p = Path(str(path_raw or "").strip()).expanduser()
    if not p.is_absolute():
        anchor = base_dir if base_dir is not None else Path.cwd()
        p = (anchor / p).resolve()
    return p


def _coerce_script_input(payload: Dict[str, Any], *, input_mode: str) -> Dict[str, Any]:
    script_raw = payload.get("script")
    if isinstance(script_raw, dict):
        return script_raw
    clips_raw = payload.get("clips")
    subtitles_raw = payload.get("subtitles")
    if isinstance(clips_raw, list) or isinstance(subtitles_raw, list):
        return {
            "clips": clips_raw if isinstance(clips_raw, list) else [],
            "subtitles": subtitles_raw if isinstance(subtitles_raw, list) else [],
        }
    if input_mode == "project":
        return _read_script_json()
    return {}


def _coerce_materials_input(payload: Dict[str, Any], *, input_mode: str) -> Dict[str, Any]:
    materials = payload.get("materials")
    if isinstance(materials, dict):
        return materials
    if input_mode == "project":
        loaded = _read_project_json("materials.json", fallback={})
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _extract_subtitles_from_script(script: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    subtitles = script.get("subtitles", []) if isinstance(script, dict) else []
    for idx, item in enumerate(subtitles, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("cn_text") or "").strip()
        cn_text = str(item.get("cn_text") or text).strip()
        en_text = str(item.get("en_text") or "").strip()
        try:
            start = float(item.get("start_time"))
            end = float(item.get("end_time"))
        except Exception:
            continue
        if end <= start:
            continue
        out.append(
            {
                "index": int(item.get("index", idx) or idx),
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "text": text,
                "cn_text": cn_text,
                "en_text": en_text,
            }
        )
    return out


def _script_to_text_blocks(script: Dict[str, Any]) -> Dict[str, str]:
    clips = script.get("clips", []) if isinstance(script.get("clips"), list) else []
    subtitles = script.get("subtitles", []) if isinstance(script.get("subtitles"), list) else []

    script_parts: List[str] = []
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        for key in ("text", "narration", "voiceover", "description", "summary"):
            val = str(clip.get(key) or "").strip()
            if val:
                script_parts.append(val)
                break

    voice_parts: List[str] = []
    for sub in subtitles:
        if not isinstance(sub, dict):
            continue
        val = str(sub.get("cn_text") or sub.get("text") or "").strip()
        if val:
            voice_parts.append(val)

    return {
        "script_text": "\n".join(script_parts).strip(),
        "voiceover_text": "\n".join(voice_parts).strip(),
    }


def _parse_str_list(payload_value) -> List[str]:
    if isinstance(payload_value, list):
        return [str(x).strip() for x in payload_value if str(x).strip()]
    text = str(payload_value or "").strip()
    if not text:
        return []
    return [x.strip() for x in text.replace("，", ",").split(",") if x.strip()]


def _default_master_video_path() -> Optional[Path]:
    if _project_dir is None:
        return None
    candidates = [
        _project_dir / "output" / "final.mp4",
        _project_dir / "preview" / "rough_cut.mp4",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _default_bgm_library_dirs(custom_dir: str = "", custom_dirs: Optional[List[str]] = None) -> List[Path]:
    """Resolve candidate BGM library folders with project defaults."""
    if _project_dir is None:
        return []
    seen = set()
    resolved: List[Path] = []

    candidates: List[str] = []
    if str(custom_dir or "").strip():
        candidates.append(str(custom_dir))
    if isinstance(custom_dirs, list):
        candidates.extend(str(x) for x in custom_dirs if str(x).strip())

    defaults = [
        _project_dir / "assets" / "bgm",
        _project_dir / "assets" / "music",
        _project_dir / "data" / "bgm",
        _project_dir / "data" / "music",
        _project_dir / "bgm",
        _project_dir / "music",
    ]
    candidates.extend(str(x) for x in defaults)

    for raw in candidates:
        p = Path(str(raw or "").strip()).expanduser()
        if not p.is_absolute():
            p = (_project_dir / p).resolve()
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists() and p.is_dir():
            resolved.append(p)
    return resolved


def _default_bgm_output_dir(custom_dir: str = "") -> Optional[Path]:
    """Resolve BGM download output dir."""
    if _project_dir is None:
        return None
    raw = str(custom_dir or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (_project_dir / p).resolve()
        return p
    return (_project_dir / "data" / "audio_voice" / "bgm").resolve()


def _is_remote_media_url(value: str) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://")


def _append_social_export_history(record: Dict, max_entries: int = 100) -> List[Dict]:
    """Persist social export batch summary into workflow.json and data file."""
    if _ws is None or _project_dir is None:
        return []
    ws = _ws
    history = ws.data.get("social_export_history", [])
    if not isinstance(history, list):
        history = []
    history.append(record)
    if len(history) > max(int(max_entries), 10):
        history = history[-max(int(max_entries), 10):]
    ws.data["social_export_history"] = history
    ws.save()

    p = _project_data_path("social_export_history.json")
    if p is not None:
        p.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def _get_social_export_history() -> List[Dict]:
    if _ws is not None:
        raw = _ws.data.get("social_export_history", [])
        if isinstance(raw, list):
            return raw
    p = _project_data_path("social_export_history.json")
    if p is not None and p.exists():
        try:
            parsed = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
    return []


def _normalize_export_template_id(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    cleaned = []
    for ch in raw:
        if ch.isalnum() or ch == "_":
            cleaned.append(ch)
        elif ch in {"-", " ", "/"}:
            cleaned.append("_")
    out = "".join(cleaned).strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    return out[:64]


def _normalize_export_template_payload(payload: Dict) -> Dict:
    if not isinstance(payload, dict):
        raise ValueError("模板参数必须是对象")
    platform_id_raw = str(payload.get("platform_id", "") or payload.get("template_id", "")).strip()
    name_raw = str(payload.get("name", "") or "").strip()
    platform_id = _normalize_export_template_id(platform_id_raw or name_raw)
    if not platform_id:
        raise ValueError("模板 ID 不能为空")
    if not name_raw:
        raise ValueError("模板名称不能为空")

    def _to_int(value, default: int, min_val: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = int(default)
        return max(parsed, min_val)

    return {
        "platform_id": platform_id,
        "name": name_raw,
        "width": _to_int(payload.get("width", 1080), 1080, 16),
        "height": _to_int(payload.get("height", 1920), 1920, 16),
        "fps": _to_int(payload.get("fps", 30), 30, 1),
        "video_bitrate": str(payload.get("video_bitrate", "10M") or "10M").strip() or "10M",
        "audio_bitrate": str(payload.get("audio_bitrate", "192k") or "192k").strip() or "192k",
        "max_duration_s": _to_int(payload.get("max_duration_s", 180), 180, 1),
    }


def _get_social_export_templates() -> Dict[str, Dict]:
    if _project_dir is None:
        return {}
    raw = _read_project_json("social_export_templates.json", fallback={})
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict] = {}
    for _, item in raw.items():
        try:
            normalized = _normalize_export_template_payload(item)
        except Exception:
            continue
        out[normalized["platform_id"]] = normalized
    return out


def _save_social_export_templates(templates: Dict[str, Dict]) -> Dict[str, Dict]:
    if _project_dir is None:
        return {}
    out: Dict[str, Dict] = {}
    if isinstance(templates, dict):
        for _, item in templates.items():
            try:
                normalized = _normalize_export_template_payload(item)
            except Exception:
                continue
            out[normalized["platform_id"]] = normalized
    p = _project_data_path("social_export_templates.json")
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _coerce_social_export_overrides(payload: Dict[str, Any], *, input_mode: str) -> Dict[str, Dict]:
    explicit = payload.get("profile_overrides")
    if isinstance(explicit, dict):
        out: Dict[str, Dict] = {}
        for key, value in explicit.items():
            if not isinstance(value, dict):
                continue
            try:
                normalized = _normalize_export_template_payload(value)
            except Exception:
                continue
            out[str(normalized.get("platform_id") or key)] = normalized
        return out

    templates = payload.get("templates")
    if isinstance(templates, dict):
        out: Dict[str, Dict] = {}
        for _, value in templates.items():
            if not isinstance(value, dict):
                continue
            try:
                normalized = _normalize_export_template_payload(value)
            except Exception:
                continue
            out[normalized["platform_id"]] = normalized
        if out:
            return out
    if isinstance(templates, list):
        out: Dict[str, Dict] = {}
        for value in templates:
            if not isinstance(value, dict):
                continue
            try:
                normalized = _normalize_export_template_payload(value)
            except Exception:
                continue
            out[normalized["platform_id"]] = normalized
        if out:
            return out

    if input_mode == "project" and _project_dir is not None:
        return _get_social_export_templates()
    return {}


def _normalize_agent_template_id(value: str) -> str:
    return _normalize_export_template_id(value)


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base) if isinstance(base, dict) else {}
    if not isinstance(override, dict):
        return out
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out.get(key, {}), value)
        else:
            out[key] = deepcopy(value)
    return out


def _get_nested_value(data: Dict[str, Any], path: str):
    if not isinstance(data, dict):
        return False, None
    parts = [x for x in str(path or "").split(".") if x]
    if not parts:
        return False, None
    cur: Any = data
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _set_nested_value(data: Dict[str, Any], path: str, value: Any):
    if not isinstance(data, dict):
        return
    parts = [x for x in str(path or "").split(".") if x]
    if not parts:
        return
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = deepcopy(value)


def _agent_template_value_matches_type(value: Any, slot_type: str) -> bool:
    t = str(slot_type or "").strip().lower()
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return True


def _validate_agent_template_slot_value(slot: Dict[str, Any], value: Any) -> Optional[str]:
    slot_type = str(slot.get("type", "string") or "string").strip().lower()
    if not _agent_template_value_matches_type(value, slot_type):
        return f"类型不匹配（期望 {slot_type}）"

    enum_raw = slot.get("enum")
    if isinstance(enum_raw, list) and enum_raw and value not in enum_raw:
        return f"不在 enum 范围内: {enum_raw}"

    if slot_type in {"number", "integer"} and isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = slot.get("minimum")
        maximum = slot.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            return f"小于最小值 {minimum}"
        if isinstance(maximum, (int, float)) and value > maximum:
            return f"大于最大值 {maximum}"
    return None


def _normalize_agent_template_variables(variables_raw: Any) -> List[Dict[str, Any]]:
    if variables_raw in (None, ""):
        return []
    if not isinstance(variables_raw, list):
        raise ValueError("variables 必须是数组")

    out: List[Dict[str, Any]] = []
    seen_keys = set()
    allowed_types = {"string", "number", "integer", "boolean", "array", "object"}
    for idx, item in enumerate(variables_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"variables[{idx}] 必须是对象")
        key = str(item.get("key", "") or item.get("name", "")).strip()
        if not key:
            raise ValueError(f"variables[{idx}].key 不能为空")
        if key in seen_keys:
            raise ValueError(f"variables 存在重复 key: {key}")
        seen_keys.add(key)

        slot_type = str(item.get("type", "string") or "string").strip().lower()
        if slot_type not in allowed_types:
            raise ValueError(f"variables[{idx}].type 仅支持 {sorted(allowed_types)}")

        slot: Dict[str, Any] = {
            "key": key,
            "type": slot_type,
            "required": _coerce_bool(item.get("required", False), default=False),
        }
        if "description" in item:
            slot["description"] = str(item.get("description", "") or "").strip()[:240]
        if "enum" in item and item.get("enum") is not None:
            if not isinstance(item.get("enum"), list):
                raise ValueError(f"variables[{idx}].enum 必须是数组")
            slot["enum"] = list(item.get("enum", []))
        if "minimum" in item and item.get("minimum") is not None:
            if not isinstance(item.get("minimum"), (int, float)):
                raise ValueError(f"variables[{idx}].minimum 必须是数字")
            slot["minimum"] = item.get("minimum")
        if "maximum" in item and item.get("maximum") is not None:
            if not isinstance(item.get("maximum"), (int, float)):
                raise ValueError(f"variables[{idx}].maximum 必须是数字")
            slot["maximum"] = item.get("maximum")
        if "minimum" in slot and "maximum" in slot and slot["minimum"] > slot["maximum"]:
            raise ValueError(f"variables[{idx}] minimum 不能大于 maximum")
        if "default" in item:
            default_val = item.get("default")
            err = _validate_agent_template_slot_value(slot, default_val)
            if err:
                raise ValueError(f"variables[{idx}].default 非法: {err}")
            slot["default"] = deepcopy(default_val)
        out.append(slot)
    return out


def _validate_template_slot_values(
    *,
    variables: List[Dict[str, Any]],
    payload: Dict[str, Any],
    source_label: str,
) -> List[str]:
    if not isinstance(payload, dict) or not variables:
        return []
    errors: List[str] = []
    for slot in variables:
        key = str(slot.get("key", "") or "").strip()
        if not key:
            continue
        exists, value = _get_nested_value(payload, key)
        if not exists:
            continue
        err = _validate_agent_template_slot_value(slot, value)
        if err:
            errors.append(f"{source_label}.{key}: {err}")
    return errors


def _hydrate_agent_template_defaults(template_raw: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(template_raw) if isinstance(template_raw, dict) else {}
    out["template_id"] = _normalize_agent_template_id(out.get("template_id", ""))
    out["name"] = str(out.get("name", "") or "").strip()
    out["capability_id"] = str(out.get("capability_id", "") or "").strip() or "generic"
    out["scope"] = str(out.get("scope", "") or "").strip().lower()
    out["actor_id"] = str(out.get("actor_id", "") or "").strip()
    tags_raw = out.get("tags", [])
    out["tags"] = [str(x).strip() for x in tags_raw if str(x).strip()] if isinstance(tags_raw, list) else []
    out["content"] = deepcopy(out.get("content", {})) if isinstance(out.get("content"), dict) else {}
    out["overrides"] = deepcopy(out.get("overrides", {})) if isinstance(out.get("overrides"), dict) else {}
    out["base_template_id"] = _normalize_agent_template_id(str(out.get("base_template_id", "") or ""))
    try:
        out["variables"] = _normalize_agent_template_variables(out.get("variables", []))
    except Exception:
        out["variables"] = []
    out["updated_at"] = str(out.get("updated_at", "") or "")
    if out["scope"] != "agent":
        out["actor_id"] = ""
    if out["scope"] not in {"system", "project", "agent"}:
        out["scope"] = "project"
    if out["base_template_id"] == out["template_id"]:
        out["base_template_id"] = ""
    return out


def _normalize_agent_template_payload(
    payload: Dict,
    *,
    scope_default: str = "agent",
    actor_id_default: str = "",
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("模板参数必须是对象")
    template_id_raw = str(payload.get("template_id", "") or payload.get("id", "")).strip()
    name_raw = str(payload.get("name", "") or "").strip()
    template_id = _normalize_agent_template_id(template_id_raw or name_raw)
    if not template_id:
        raise ValueError("template_id 不能为空")
    if not name_raw:
        raise ValueError("name 不能为空")

    scope = str(payload.get("scope", scope_default) or scope_default).strip().lower()
    if scope not in {"system", "project", "agent"}:
        raise ValueError("scope 仅支持 system/project/agent")

    actor_id = str(payload.get("actor_id", actor_id_default) or actor_id_default).strip()
    if scope == "agent" and not actor_id:
        raise ValueError("agent scope 需要 actor_id")
    if scope != "agent":
        actor_id = ""

    capability_id = str(payload.get("capability_id", "") or "").strip() or "generic"
    base_template_id = _normalize_agent_template_id(str(payload.get("base_template_id", "") or ""))
    if base_template_id == template_id:
        raise ValueError("base_template_id 不能指向自己")

    content_raw = payload.get("content", {})
    if content_raw is None:
        content_raw = {}
    if not isinstance(content_raw, dict):
        raise ValueError("content 必须是对象")
    overrides_raw = payload.get("overrides", {})
    if overrides_raw is None:
        overrides_raw = {}
    if not isinstance(overrides_raw, dict):
        raise ValueError("overrides 必须是对象")
    variables = _normalize_agent_template_variables(payload.get("variables", []))
    slot_errors = _validate_template_slot_values(
        variables=variables,
        payload=content_raw,
        source_label="content",
    ) + _validate_template_slot_values(
        variables=variables,
        payload=overrides_raw,
        source_label="overrides",
    )
    if slot_errors:
        raise ValueError(f"变量约束不满足: {'; '.join(slot_errors[:5])}")

    tags_raw = payload.get("tags", [])
    tags = tags_raw if isinstance(tags_raw, list) else []
    tags = [str(x).strip() for x in tags if str(x).strip()]

    return {
        "template_id": template_id,
        "name": name_raw,
        "capability_id": capability_id,
        "scope": scope,
        "actor_id": actor_id,
        "tags": tags,
        "base_template_id": base_template_id,
        "overrides": deepcopy(overrides_raw),
        "variables": variables,
        "content": content_raw,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _read_agent_template_store() -> Dict[str, Any]:
    raw = _read_project_json("agent_templates.json", fallback={})
    if not isinstance(raw, dict):
        return {"project": {}, "agent": {}}
    project = raw.get("project", {})
    agent = raw.get("agent", {})
    return {
        "project": project if isinstance(project, dict) else {},
        "agent": agent if isinstance(agent, dict) else {},
    }


def _agent_template_lookup_key(scope: str, actor_id: str, template_id: str) -> str:
    return f"{str(scope or '').strip().lower()}|{str(actor_id or '').strip()}|{_normalize_agent_template_id(template_id)}"


def _agent_template_chain_token(template: Dict[str, Any]) -> str:
    scope = str(template.get("scope", "") or "").strip().lower()
    actor_id = str(template.get("actor_id", "") or "").strip()
    template_id = str(template.get("template_id", "") or "").strip()
    if scope == "agent" and actor_id:
        return f"{scope}:{actor_id}:{template_id}"
    return f"{scope}:{template_id}"


def _agent_template_base_candidate_keys(template: Dict[str, Any]) -> List[str]:
    scope = str(template.get("scope", "") or "").strip().lower()
    actor_id = str(template.get("actor_id", "") or "").strip()
    base_id = _normalize_agent_template_id(str(template.get("base_template_id", "") or ""))
    if not base_id:
        return []
    if scope == "agent":
        return [
            _agent_template_lookup_key("agent", actor_id, base_id),
            _agent_template_lookup_key("project", "", base_id),
            _agent_template_lookup_key("system", "", base_id),
        ]
    if scope == "project":
        return [
            _agent_template_lookup_key("project", "", base_id),
            _agent_template_lookup_key("system", "", base_id),
        ]
    return [_agent_template_lookup_key("system", "", base_id)]


def _resolve_agent_template_effective(
    template: Dict[str, Any],
    *,
    lookup: Dict[str, Dict[str, Any]],
    cache: Dict[str, Dict[str, Any]],
    visiting: Optional[set] = None,
) -> Dict[str, Any]:
    hydrated = _hydrate_agent_template_defaults(template)
    own_key = _agent_template_lookup_key(
        hydrated.get("scope", ""),
        hydrated.get("actor_id", ""),
        hydrated.get("template_id", ""),
    )
    cached = cache.get(own_key)
    if isinstance(cached, dict):
        return cached

    if visiting is None:
        visiting = set()
    if own_key in visiting:
        token = _agent_template_chain_token(hydrated)
        ret = {
            "effective_content": deepcopy(hydrated.get("content", {})),
            "template_chain": [token],
            "resolve_warnings": [f"模板继承存在循环引用: {token}"],
        }
        cache[own_key] = ret
        return ret

    visiting.add(own_key)
    warnings: List[str] = []
    chain: List[str] = []
    effective: Dict[str, Any] = {}

    base_template = None
    for candidate_key in _agent_template_base_candidate_keys(hydrated):
        candidate = lookup.get(candidate_key)
        if isinstance(candidate, dict):
            base_template = candidate
            break
    if hydrated.get("base_template_id"):
        if base_template is None:
            warnings.append(f"base_template_id 不存在或不可见: {hydrated.get('base_template_id')}")
        else:
            base_resolved = _resolve_agent_template_effective(
                base_template,
                lookup=lookup,
                cache=cache,
                visiting=visiting,
            )
            effective = deepcopy(base_resolved.get("effective_content", {}))
            chain.extend(base_resolved.get("template_chain", []))
            warnings.extend(base_resolved.get("resolve_warnings", []))

    effective = _deep_merge_dict(effective, hydrated.get("content", {}))
    effective = _deep_merge_dict(effective, hydrated.get("overrides", {}))

    for slot in hydrated.get("variables", []):
        key = str(slot.get("key", "") or "").strip()
        if not key:
            continue
        exists, _ = _get_nested_value(effective, key)
        if not exists and "default" in slot:
            _set_nested_value(effective, key, slot.get("default"))

    for slot in hydrated.get("variables", []):
        key = str(slot.get("key", "") or "").strip()
        if not key:
            continue
        exists, value = _get_nested_value(effective, key)
        if not exists:
            if _coerce_bool(slot.get("required", False), default=False):
                warnings.append(f"变量缺失(required): {key}")
            continue
        err = _validate_agent_template_slot_value(slot, value)
        if err:
            warnings.append(f"变量约束不满足 {key}: {err}")

    chain.append(_agent_template_chain_token(hydrated))
    ret = {
        "effective_content": effective,
        "template_chain": list(dict.fromkeys(str(x) for x in chain if str(x).strip())),
        "resolve_warnings": list(dict.fromkeys(str(x) for x in warnings if str(x).strip())),
    }
    cache[own_key] = ret
    visiting.discard(own_key)
    return ret


def _collect_agent_templates(
    *,
    store: Optional[Dict[str, Any]] = None,
    actor_id: str = "",
    include_system: bool = True,
) -> List[Dict[str, Any]]:
    actor_norm = str(actor_id or "").strip()
    current_store = store if isinstance(store, dict) else _read_agent_template_store()
    out: List[Dict[str, Any]] = []
    if include_system:
        out.extend(_hydrate_agent_template_defaults(x) for x in _AGENT_SYSTEM_TEMPLATES.values())

    project_templates = current_store.get("project", {})
    if isinstance(project_templates, dict):
        for item in project_templates.values():
            out.append(_hydrate_agent_template_defaults(item))

    if actor_norm:
        agent_bucket = current_store.get("agent", {})
        actor_templates = agent_bucket.get(actor_norm, {}) if isinstance(agent_bucket, dict) else {}
        if isinstance(actor_templates, dict):
            for item in actor_templates.values():
                out.append(_hydrate_agent_template_defaults(item))
    return out


def _validate_agent_template_base_reference(template: Dict[str, Any], *, store: Dict[str, Any]) -> Optional[str]:
    hydrated = _hydrate_agent_template_defaults(template)
    base_id = str(hydrated.get("base_template_id", "") or "").strip()
    if not base_id:
        return None

    actor_id = str(hydrated.get("actor_id", "") or "").strip()
    pool = _collect_agent_templates(store=store, actor_id=actor_id, include_system=True)
    lookup: Dict[str, Dict[str, Any]] = {}
    own_key = _agent_template_lookup_key(
        hydrated.get("scope", ""),
        hydrated.get("actor_id", ""),
        hydrated.get("template_id", ""),
    )
    for item in pool:
        key = _agent_template_lookup_key(item.get("scope", ""), item.get("actor_id", ""), item.get("template_id", ""))
        if key == own_key:
            continue
        lookup[key] = item
    lookup[own_key] = hydrated

    if not any(candidate_key in lookup for candidate_key in _agent_template_base_candidate_keys(hydrated)):
        return f"base_template_id 不存在或不可见: {base_id}"

    cache: Dict[str, Dict[str, Any]] = {}
    resolved = _resolve_agent_template_effective(hydrated, lookup=lookup, cache=cache, visiting=set())
    for msg in resolved.get("resolve_warnings", []):
        if "循环引用" in str(msg):
            return str(msg)
    return None


def _save_agent_template_store(store: Dict[str, Any]) -> Dict[str, Any]:
    if _project_dir is None:
        return {"project": {}, "agent": {}}
    project_raw = store.get("project", {}) if isinstance(store, dict) else {}
    agent_raw = store.get("agent", {}) if isinstance(store, dict) else {}

    project_out: Dict[str, Dict] = {}
    if isinstance(project_raw, dict):
        for _, item in project_raw.items():
            try:
                tmpl = _normalize_agent_template_payload(item, scope_default="project")
            except Exception:
                continue
            if tmpl.get("scope") != "project":
                tmpl["scope"] = "project"
                tmpl["actor_id"] = ""
            project_out[tmpl["template_id"]] = tmpl

    agent_out: Dict[str, Dict[str, Dict]] = {}
    if isinstance(agent_raw, dict):
        for actor_key, actor_templates in agent_raw.items():
            actor_id = str(actor_key or "").strip()
            if not actor_id or not isinstance(actor_templates, dict):
                continue
            bucket: Dict[str, Dict] = {}
            for _, item in actor_templates.items():
                try:
                    tmpl = _normalize_agent_template_payload(
                        item,
                        scope_default="agent",
                        actor_id_default=actor_id,
                    )
                except Exception:
                    continue
                tmpl["scope"] = "agent"
                tmpl["actor_id"] = actor_id
                bucket[tmpl["template_id"]] = tmpl
            if bucket:
                agent_out[actor_id] = bucket

    out = {"project": project_out, "agent": agent_out}
    p = _project_data_path("agent_templates.json")
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _list_agent_templates(
    *,
    capability_id: str = "",
    scope: str = "",
    actor_id: str = "",
    include_system: bool = True,
    resolve: bool = True,
) -> List[Dict[str, Any]]:
    capability_norm = str(capability_id or "").strip()
    scope_norm = str(scope or "").strip().lower()
    actor_norm = str(actor_id or "").strip()
    store = _read_agent_template_store()
    full_pool = _collect_agent_templates(store=store, actor_id=actor_norm, include_system=True)
    out: List[Dict[str, Any]] = []
    for item in full_pool:
        scope_item = str(item.get("scope", "") or "").strip().lower()
        if scope_norm and scope_item != scope_norm:
            continue
        if not include_system and scope_item == "system":
            continue
        out.append(deepcopy(item))

    if capability_norm:
        out = [x for x in out if str(x.get("capability_id", "") or "") == capability_norm]

    if resolve:
        lookup = {
            _agent_template_lookup_key(item.get("scope", ""), item.get("actor_id", ""), item.get("template_id", "")): item
            for item in full_pool
        }
        cache: Dict[str, Dict[str, Any]] = {}
        for item in out:
            resolved = _resolve_agent_template_effective(item, lookup=lookup, cache=cache, visiting=set())
            item["effective_content"] = deepcopy(resolved.get("effective_content", item.get("content", {})))
            item["template_chain"] = list(resolved.get("template_chain", []))
            item["resolve_warnings"] = list(resolved.get("resolve_warnings", []))

    def _sort_key(item: Dict[str, Any]):
        return (
            _AGENT_TEMPLATE_SCOPE_ORDER.get(str(item.get("scope", "")).lower(), 99),
            str(item.get("name", "")).lower(),
            str(item.get("template_id", "")).lower(),
        )

    out.sort(key=_sort_key)
    for item in out:
        scope_item = str(item.get("scope", "")).lower()
        item["readonly"] = scope_item == "system"
    return out


def _build_social_export_runner(
    *,
    input_video_raw: str,
    output_dir_raw: str,
    platforms: List[str],
    quality: str,
    ffmpeg_bin: str,
    ffprobe_bin: str,
    strict_duration_limit: bool,
    timeout_seconds: float,
    job_id: str,
    profile_overrides: Optional[Dict] = None,
    input_mode: str = "project",
    base_dir: Optional[Path] = None,
    persist_history: bool = True,
):
    from modules.capabilities.social_export import build_export_plan, run_export_plan

    def _do_export():
        anchor = base_dir if base_dir is not None else (_project_dir if _project_dir is not None else Path.cwd())
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + job_id
        started_at = datetime.now().isoformat(timespec="seconds")
        if input_video_raw:
            in_path = _resolve_path_with_base(input_video_raw, base_dir=anchor)
        else:
            if input_mode == "project":
                in_path = _default_master_video_path()
                if in_path is None:
                    raise RuntimeError("找不到可导出的母版视频")
            else:
                raise RuntimeError("inline 模式需要提供 input_video")
        if not in_path.exists():
            raise RuntimeError(f"输入视频不存在: {in_path}")

        final_platforms = platforms if platforms else ["douyin", "xiaohongshu", "tiktok"]
        out_dir = (
            (anchor / "output" / "social_exports")
            if not output_dir_raw
            else _resolve_path_with_base(output_dir_raw, base_dir=anchor)
        )

        plan = build_export_plan(
            input_video=str(in_path),
            output_dir=str(out_dir),
            platform_ids=final_platforms,
            quality=quality,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
            strict_duration_limit=bool(strict_duration_limit),
            profile_overrides=profile_overrides,
        )
        logger.info("[社媒导出] 总任务 %d，输出目录: %s", len(plan.get("jobs", [])), out_dir)
        for i, job in enumerate(plan.get("jobs", []), start=1):
            logger.info("[社媒导出] %d/%d %s -> %s", i, len(plan["jobs"]), job.get("platform_id"), job.get("output_video"))
        try:
            result = run_export_plan(plan, timeout_seconds=timeout_seconds)
        except Exception as exc:
            failed_record = {
                "batch_id": batch_id,
                "job_id": job_id,
                "status": "failed",
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "input_video": str(in_path),
                "output_dir": str(out_dir),
                "platforms": [j.get("platform_id") for j in plan.get("jobs", [])],
                "quality": quality,
                "strict_duration_limit": bool(strict_duration_limit),
                "total": len(plan.get("jobs", [])),
                "success": 0,
                "failed": len(plan.get("jobs", [])),
                "error": str(exc),
                "output_files": [],
            }
            if persist_history and input_mode == "project":
                _append_social_export_history(failed_record)
            raise

        done_files = [
            r.get("output_video")
            for r in result.get("results", [])
            if r.get("status") == "done" and r.get("output_video")
        ]
        record = {
            "batch_id": batch_id,
            "job_id": job_id,
            "status": "done" if int(result.get("failed", 0)) == 0 else "partial",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "input_video": str(in_path),
            "output_dir": str(out_dir),
            "platforms": [j.get("platform_id") for j in plan.get("jobs", [])],
            "quality": quality,
            "strict_duration_limit": bool(strict_duration_limit),
            "total": int(result.get("total", 0)),
            "success": int(result.get("success", 0)),
            "failed": int(result.get("failed", 0)),
            "output_files": done_files,
        }
        if persist_history and input_mode == "project":
            _append_social_export_history(record)
        logger.info("[社媒导出] 完成，成功 %d，失败 %d", result.get("success", 0), result.get("failed", 0))
        return {"plan": plan, "result": result, "batch": record}

    return _do_export


def _build_audio_voice_runner(
    *,
    payload: Dict,
    job_id: str,
    input_mode: str = "project",
    base_dir: Optional[Path] = None,
):
    from modules.capabilities.audio_voice import (
        build_audio_capability_payload,
        build_voiceover_timeline,
        mix_voiceover_to_video,
        pick_bgm,
        synthesize_voiceover_segments,
    )

    def _set_progress(p: int, msg: str = ""):
        if job_id in _jobs:
            _jobs[job_id]["progress"] = max(0, min(99, int(p)))
            if msg:
                _jobs[job_id]["log"].append(msg)
                _jobs[job_id]["log"] = _jobs[job_id]["log"][-220:]

    def _do_audio_voice():
        if input_mode == "project" and _project_dir is None:
            raise RuntimeError("项目未加载")
        anchor = base_dir if base_dir is not None else _capability_base_dir(input_mode)

        mood = str(payload.get("mood", "travel_story") or "travel_story")
        provider = str(payload.get("provider", "elevenlabs") or "elevenlabs")
        voice_id = str(payload.get("voice_id", "") or "").strip()
        api_key = str(payload.get("api_key", "") or "").strip()
        model_id = str(payload.get("model_id", "eleven_multilingual_v2") or "eleven_multilingual_v2")
        output_format = str(payload.get("output_format", "mp3_44100_128") or "mp3_44100_128")
        dry_run = bool(payload.get("dry_run", False))

        _set_progress(5, "[配音] 读取脚本与字幕")
        script = _coerce_script_input(payload, input_mode=input_mode)
        plan = build_audio_capability_payload(script, mood=mood)
        segments = payload.get("segments", plan.get("voiceover_segments", []))
        if not isinstance(segments, list) or not segments:
            raise RuntimeError("缺少可合成的字幕分段，请先完成脚本/字幕")
        clip_duration_s = plan.get("music_plan", {}).get("duration_s")
        if clip_duration_s in {None, 0, 0.0}:
            clip_duration_s = payload.get("target_duration_s")

        output_dir_raw = str(payload.get("output_dir", "") or "").strip()
        output_dir = (
            (anchor / "data" / "audio_voice" / "voiceover")
            if not output_dir_raw
            else _resolve_path_with_base(output_dir_raw, base_dir=anchor)
        )

        _set_progress(20, "[配音] 开始 ElevenLabs 合成")
        synthesis = synthesize_voiceover_segments(
            segments,
            output_dir=str(output_dir),
            provider=provider,
            voice_id=voice_id,
            api_key=api_key,
            model_id=model_id,
            output_format=output_format,
            timeout_seconds=float(payload.get("tts_timeout_seconds", 90) or 90),
            dry_run=dry_run,
        )

        output_audio_raw = str(payload.get("output_audio", "") or "").strip()
        output_audio = (
            (anchor / "data" / "audio_voice" / "narration_timeline.m4a")
            if not output_audio_raw
            else _resolve_path_with_base(output_audio_raw, base_dir=anchor)
        )

        _set_progress(55, "[配音] 生成旁白时间线轨")
        timeline = build_voiceover_timeline(
            synthesis.get("segments", []),
            output_audio=str(output_audio),
            ffmpeg_bin=str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg"),
            timeout_seconds=float(payload.get("track_timeout_seconds", 600) or 600),
            dry_run=dry_run,
        )

        input_video_raw = str(payload.get("input_video", "") or "").strip()
        if input_video_raw:
            input_video = _resolve_path_with_base(input_video_raw, base_dir=anchor)
        else:
            if input_mode == "project":
                input_video = _default_master_video_path()
                if input_video is None:
                    raise RuntimeError("找不到可混音的输入视频")
            else:
                raise RuntimeError("inline 模式需要提供 input_video")
        if not input_video.exists():
            raise RuntimeError(f"输入视频不存在: {input_video}")

        bgm_audio_raw = str(payload.get("bgm_audio", "") or "").strip()
        bgm_audio = ""
        bgm_pick = None
        if bgm_audio_raw:
            if _is_remote_media_url(bgm_audio_raw):
                bgm_audio = bgm_audio_raw
            else:
                bgm_path = _resolve_path_with_base(bgm_audio_raw, base_dir=anchor)
                bgm_audio = str(bgm_path)
        elif bool(payload.get("auto_pick_bgm", True)):
            _set_progress(68, "[配乐] 自动匹配 BGM")
            library_dir = str(payload.get("bgm_library_dir", "") or "").strip()
            library_dirs = _parse_str_list(payload.get("bgm_library_dirs", []))
            if input_mode == "project":
                resolved_dirs = _default_bgm_library_dirs(custom_dir=library_dir, custom_dirs=library_dirs)
            else:
                resolved_dirs = []
                for item in [library_dir, *library_dirs]:
                    raw = str(item or "").strip()
                    if not raw:
                        continue
                    resolved = _resolve_path_with_base(raw, base_dir=anchor)
                    if resolved.exists() and resolved.is_dir():
                        resolved_dirs.append(resolved)
            bgm_provider = str(payload.get("bgm_provider", "local_library") or "local_library")
            if input_mode == "project":
                bgm_output_dir = _default_bgm_output_dir(str(payload.get("bgm_output_dir", "") or "").strip())
            else:
                bgm_output_raw = str(payload.get("bgm_output_dir", "") or "").strip()
                bgm_output_dir = (
                    (anchor / "data" / "audio_voice" / "bgm")
                    if not bgm_output_raw
                    else _resolve_path_with_base(bgm_output_raw, base_dir=anchor)
                )
            bgm_force_refresh = bool(payload.get("bgm_force_refresh", False))
            bgm_cache_max_age_days = float(payload.get("bgm_cache_max_age_days", 0) or 0)
            bgm_cache_max_age_seconds = max(bgm_cache_max_age_days, 0.0) * 86400.0
            try:
                bgm_pick = pick_bgm(
                    provider=bgm_provider,
                    mood=mood,
                    target_duration_s=float(clip_duration_s or 0.0) or None,
                    library_dirs=[str(x) for x in resolved_dirs],
                    ffprobe_bin=str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe"),
                    max_candidates=int(payload.get("bgm_max_candidates", 20) or 20),
                    api_key=str(payload.get("bgm_api_key", "") or "").strip(),
                    endpoint=str(payload.get("bgm_endpoint", "") or "").strip(),
                    timeout_seconds=float(payload.get("bgm_timeout_seconds", 45) or 45),
                    output_dir=str(bgm_output_dir) if bgm_output_dir is not None else "",
                    download_audio=bool(payload.get("bgm_download", True)),
                    strict_schema=bool(payload.get("bgm_strict_schema", False)),
                    cache_enabled=bool(payload.get("bgm_cache_enabled", True)),
                    force_refresh=bgm_force_refresh,
                    cache_max_age_seconds=bgm_cache_max_age_seconds,
                )
                maybe_track = str(bgm_pick.get("selected_track", "") or "").strip() if isinstance(bgm_pick, dict) else ""
                if maybe_track:
                    bgm_audio = maybe_track
                    _set_progress(71, f"[配乐] 已选择 BGM: {Path(maybe_track).name}")
                elif isinstance(bgm_pick, dict) and str(bgm_pick.get("selected_url", "")).strip():
                    bgm_audio = str(bgm_pick.get("selected_url", "")).strip()
                    _set_progress(71, "[配乐] 使用远端 BGM URL 参与混音")
                else:
                    _set_progress(71, "[配乐] 未找到可用 BGM，将仅混入旁白")
            except Exception as exc:
                bgm_pick = {"status": "failed", "error": str(exc), "provider": bgm_provider}
                _set_progress(71, f"[配乐] 自动匹配失败，改为仅混入旁白: {exc}")

        replace_master = bool(payload.get("replace_master", input_mode == "project"))
        output_video_raw = str(payload.get("output_video", "") or "").strip()
        if replace_master:
            output_video = anchor / "output" / "final.mp4"
        elif output_video_raw:
            output_video = _resolve_path_with_base(output_video_raw, base_dir=anchor)
        else:
            output_video = anchor / "output" / "final_voice.mp4"

        mix_target = output_video
        used_temp = False
        if output_video.resolve() == input_video.resolve():
            used_temp = True
            mix_target = output_video.with_suffix(".audio_pipeline_tmp.mp4")

        _set_progress(75, "[配音] 混音到成片")
        mix = mix_voiceover_to_video(
            input_video=str(input_video),
            output_video=str(mix_target),
            narration_audio=str(output_audio),
            bgm_audio=bgm_audio,
            ffmpeg_bin=str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg"),
            ffprobe_bin=str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe"),
            origin_volume=float(payload.get("origin_volume", 0.8) or 0.8),
            narration_volume=float(payload.get("narration_volume", 1.0) or 1.0),
            bgm_volume=float(payload.get("bgm_volume", 0.25) or 0.25),
            bgm_loop=bool(payload.get("bgm_loop", True)),
            bgm_fade_out_s=float(payload.get("bgm_fade_out_s", 2.0) or 0.0),
            enable_ducking=bool(payload.get("enable_ducking", True)),
            ducking_threshold=float(payload.get("ducking_threshold", 0.03) or 0.03),
            ducking_ratio=float(payload.get("ducking_ratio", 8.0) or 8.0),
            ducking_attack_ms=float(payload.get("ducking_attack_ms", 15.0) or 15.0),
            ducking_release_ms=float(payload.get("ducking_release_ms", 250.0) or 250.0),
            audio_bitrate=str(payload.get("audio_bitrate", "192k") or "192k"),
            timeout_seconds=float(payload.get("mix_timeout_seconds", 900) or 900),
            dry_run=dry_run,
        )

        if used_temp and not dry_run and mix.get("status") == "done":
            mix_target.replace(output_video)
            mix["output_video"] = str(output_video.resolve())

        _set_progress(95, "[配音] 写入结果摘要")
        summary = {
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "input_mode": input_mode,
            "dry_run": dry_run,
            "plan": plan,
            "bgm_pick": bgm_pick,
            "synthesis": synthesis,
            "timeline": timeline,
            "mix": mix,
        }
        out_path = _project_data_path("audio_voice_pipeline_last.json") if input_mode == "project" else None
        if out_path is not None:
            out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    return _do_audio_voice


def _request_json_payload() -> Dict:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return {}
    try:
        payload = request.get_json(silent=True)
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else {}


def _parse_boolish(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _parse_request_context() -> Dict[str, str]:
    payload = _request_json_payload()
    actor_type_raw = (
        payload.get("actor_type")
        or request.args.get("actor_type")
        or request.headers.get("X-Actor-Type")
        or "human"
    )
    actor_type = str(actor_type_raw or "human").strip().lower()
    if actor_type not in {"human", "agent"}:
        actor_type = "human"

    actor_id = str(
        payload.get("actor_id")
        or request.args.get("actor_id")
        or request.headers.get("X-Actor-Id")
        or ""
    ).strip()[:128]

    run_mode_raw = (
        payload.get("run_mode")
        or request.args.get("run_mode")
        or request.headers.get("X-Run-Mode")
        or ("headless" if actor_type == "agent" else "interactive")
    )
    run_mode = str(run_mode_raw or "").strip().lower()
    if run_mode not in {"interactive", "headless"}:
        run_mode = "headless" if actor_type == "agent" else "interactive"

    idempotency_key = str(
        payload.get("idempotency_key")
        or request.args.get("idempotency_key")
        or request.headers.get("X-Idempotency-Key")
        or ""
    ).strip()[:128]

    trace_id = str(
        payload.get("trace_id")
        or request.args.get("trace_id")
        or request.headers.get("X-Trace-Id")
        or ""
    ).strip()[:128]

    return {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "run_mode": run_mode,
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
    }


def _extract_artifacts_from_payload(payload: Dict) -> List[Dict[str, str]]:
    if not isinstance(payload, dict):
        return []
    out: List[Dict[str, str]] = []

    def _add_candidate(value):
        s = str(value or "").strip()
        if not s:
            return
        if s.startswith("http://") or s.startswith("https://"):
            out.append({"type": "url", "value": s})
        else:
            out.append({"type": "path", "value": s})

    for key in ("output", "output_video", "output_audio", "output_dir", "input_video"):
        _add_candidate(payload.get(key))

    for key in (
        "plan",
        "result",
        "batch",
        "mix",
        "timeline",
        "synthesis",
        "handoff",
        "collect",
        "record",
        "pick",
        "report",
    ):
        section = payload.get(key)
        if isinstance(section, dict):
            for sub_key in ("output", "output_video", "output_audio", "output_dir", "input_video"):
                _add_candidate(section.get(sub_key))
            files = section.get("output_files")
            if isinstance(files, list):
                for item in files:
                    _add_candidate(item)

    dedup: List[Dict[str, str]] = []
    seen = set()
    for item in out:
        marker = (item.get("type"), item.get("value"))
        if marker in seen:
            continue
        seen.add(marker)
        dedup.append(item)
    return dedup


def _build_capability_plan_summary(payload: Dict) -> Dict:
    if not isinstance(payload, dict):
        return {}
    summary: Dict[str, Any] = {
        "ok": bool(payload.get("ok", False)),
    }
    plan = payload.get("plan")
    if isinstance(plan, dict):
        if isinstance(plan.get("jobs"), list):
            summary["planned_jobs"] = len(plan.get("jobs", []))
        if isinstance(plan.get("segments"), list):
            summary["planned_segments"] = len(plan.get("segments", []))
        if isinstance(plan.get("voiceover_segments"), list):
            summary["planned_voiceover_segments"] = len(plan.get("voiceover_segments", []))
    result = payload.get("result")
    if isinstance(result, dict):
        if "success" in result:
            summary["success"] = int(result.get("success", 0) or 0)
        if "failed" in result:
            summary["failed"] = int(result.get("failed", 0) or 0)
        if "total" in result:
            summary["total"] = int(result.get("total", 0) or 0)
    return summary


def _capability_idempotency_project_anchor() -> str:
    if _project_dir is None:
        return ""
    try:
        return str(_project_dir.resolve())
    except Exception:
        return str(_project_dir)


def _ensure_capability_idempotency_store() -> CapabilityIdempotencyStore:
    global _capability_idempotency_store
    if _capability_idempotency_store is None:
        _capability_idempotency_store = CapabilityIdempotencyStore(
            store_path_getter=lambda: _project_data_path("capability_idempotency_cache.json"),
            project_anchor_getter=lambda: _capability_idempotency_project_anchor(),
            default_ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
            default_limit=_CAPABILITY_IDEMPOTENCY_LIMIT,
            memory_cache=_capability_idempotency_cache,
            lock=_capability_idempotency_lock,
        )
    return _capability_idempotency_store


def _capability_idempotency_store_path() -> Optional[Path]:
    return _ensure_capability_idempotency_store().store_path()


def _normalize_capability_idempotency_entry(raw: Any) -> Optional[Dict[str, Any]]:
    return _ensure_capability_idempotency_store().normalize_entry(raw)


def _capability_idempotency_entry_expired(
    entry: Dict[str, Any],
    *,
    ttl_seconds: Optional[int] = None,
    now_epoch: Optional[float] = None,
) -> bool:
    return _ensure_capability_idempotency_store().entry_expired(
        entry,
        ttl_seconds=ttl_seconds,
        now_epoch=now_epoch,
    )


def _filter_capability_idempotency_entries(
    entries: Dict[str, Dict[str, Any]],
    *,
    ttl_seconds: Optional[int] = None,
    include_expired: bool = False,
) -> Dict[str, Dict[str, Any]]:
    return _ensure_capability_idempotency_store().filter_entries(
        entries,
        ttl_seconds=ttl_seconds,
        include_expired=include_expired,
    )


def _load_capability_idempotency_store(
    *,
    include_expired: bool = False,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    return _ensure_capability_idempotency_store().load_store(
        include_expired=include_expired,
        ttl_seconds=ttl_seconds,
    )


def _save_capability_idempotency_store(records: Dict[str, Dict[str, Any]]):
    _ensure_capability_idempotency_store().save_store(records)


def _trim_capability_idempotency_entries(
    entries: Dict[str, Dict[str, Any]],
    *,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    return _ensure_capability_idempotency_store().trim_entries(
        entries,
        ttl_seconds=ttl_seconds,
    )


def _trim_capability_idempotency_entries_with_limit(
    entries: Dict[str, Dict[str, Any]],
    *,
    max_entries: int,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    return _ensure_capability_idempotency_store().trim_entries_with_limit(
        entries,
        max_entries=max_entries,
        ttl_seconds=ttl_seconds,
    )


def _limit_capability_idempotency_entries(
    entries: Dict[str, Dict[str, Any]],
    *,
    max_entries: int,
) -> Dict[str, Dict[str, Any]]:
    return _ensure_capability_idempotency_store().limit_entries(
        entries,
        max_entries=max_entries,
    )


def _get_persisted_capability_idempotency_entry(cache_key: str) -> Optional[Dict[str, Any]]:
    return _ensure_capability_idempotency_store().get_persisted_entry(
        cache_key,
        ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
    )


def _compact_persisted_capability_idempotency_store(
    *,
    ttl_seconds: Optional[int] = None,
    max_entries: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    return _ensure_capability_idempotency_store().compact_persisted_store(
        ttl_seconds=ttl_seconds,
        max_entries=max_entries,
    )


def _upsert_persisted_capability_idempotency_entry(cache_key: str, entry: Dict[str, Any]):
    _ensure_capability_idempotency_store().upsert_persisted_entry(
        cache_key,
        entry,
        ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
        max_entries=_CAPABILITY_IDEMPOTENCY_LIMIT,
    )


def _make_capability_idempotency_cache_key(path: str, ctx: Dict[str, str]) -> str:
    return _ensure_capability_idempotency_store().make_cache_key(path, ctx)


def _trim_capability_idempotency_cache():
    _ensure_capability_idempotency_store().trim_memory_cache()


@app.before_request
def _capability_idempotency_before_request():
    if request.method != "POST":
        return None
    if not request.path.startswith("/api/capabilities/"):
        return None
    if request.path.startswith("/api/capabilities/idempotency/"):
        return None
    ctx = _parse_request_context()
    if not ctx.get("idempotency_key"):
        return None
    cache_key = _make_capability_idempotency_cache_key(request.path, ctx)
    store = _ensure_capability_idempotency_store()
    hit, replay_source = store.lookup(cache_key)
    if not isinstance(hit, dict):
        return None
    body = deepcopy(hit.get("body", {}))
    if isinstance(body, dict):
        idem = body.get("idempotency") if isinstance(body.get("idempotency"), dict) else {}
        idem["key"] = ctx.get("idempotency_key", "")
        idem["replayed"] = True
        idem["source"] = replay_source
        body["idempotency"] = idem
        body["request_context"] = ctx
    return jsonify(body), int(hit.get("status", 200) or 200)


@app.after_request
def _capability_context_after_request(response):
    if not (
        request.path.startswith("/api/capabilities")
        or request.path.startswith("/api/agent")
    ):
        return response
    if not (response.content_type or "").startswith("application/json"):
        return response

    body = response.get_json(silent=True)
    if not isinstance(body, dict):
        return response

    ctx = _parse_request_context()
    body["request_context"] = ctx
    if request.path.startswith("/api/capabilities") and "plan_summary" not in body:
        body["plan_summary"] = _build_capability_plan_summary(body)
    if request.path.startswith("/api/capabilities") and "artifacts" not in body:
        body["artifacts"] = _extract_artifacts_from_payload(body)
    if request.path.startswith("/api/capabilities") and "warnings" not in body:
        body["warnings"] = body.get("warnings") if isinstance(body.get("warnings"), list) else []

    if request.path.startswith("/api/capabilities/"):
        idem = body.get("idempotency") if isinstance(body.get("idempotency"), dict) else {}
        idem["key"] = ctx.get("idempotency_key", "")
        idem["replayed"] = bool(idem.get("replayed", False))
        body["idempotency"] = idem

        if (
            request.method == "POST"
            and ctx.get("idempotency_key")
            and response.status_code < 400
            and bool(body.get("ok", False))
            and not idem.get("replayed", False)
        ):
            cache_key = _make_capability_idempotency_cache_key(request.path, ctx)
            _ensure_capability_idempotency_store().put_success(
                cache_key,
                status=int(response.status_code),
                body=deepcopy(body),
            )

    response.set_data(json.dumps(body, ensure_ascii=False))
    return response


def _choose_path_via_osascript(mode: str) -> Dict:
    if sys.platform != "darwin":
        return {"path": None, "cancelled": False, "error": "当前系统不支持 osascript 对话框"}

    if mode == "folder":
        script = 'POSIX path of (choose folder with prompt "Select a folder")'
    else:
        script = 'POSIX path of (choose file with prompt "Select a file")'

    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        if "-128" in err or "User canceled" in err:
            return {"path": None, "cancelled": True, "error": ""}
        return {"path": None, "cancelled": False, "error": err or "系统文件对话框调用失败"}
    out = (proc.stdout or "").strip()
    if not out:
        return {"path": None, "cancelled": True, "error": ""}
    return {"path": out, "cancelled": False, "error": ""}


def _choose_path(mode: str) -> Dict:
    if mode not in {"folder", "file"}:
        mode = "folder"

    pywebview_error = ""
    if _window is not None:
        try:
            import webview
            if hasattr(webview, "FileDialog"):
                dialog_type = webview.FileDialog.FOLDER if mode == "folder" else webview.FileDialog.OPEN
            else:
                dialog_type = webview.FOLDER_DIALOG if mode == "folder" else webview.OPEN_DIALOG
            result = _window.create_file_dialog(
                dialog_type=dialog_type,
                allow_multiple=False,
            )
            if result:
                return {"path": result[0], "cancelled": False, "error": ""}
            return {"path": None, "cancelled": True, "error": ""}
        except Exception as exc:
            pywebview_error = str(exc)

    osascript_result = _choose_path_via_osascript(mode)
    if osascript_result.get("path") or osascript_result.get("cancelled"):
        return osascript_result
    if pywebview_error:
        base_error = osascript_result.get("error", "")
        if base_error:
            base_error = f"{base_error}; pywebview: {pywebview_error}"
        else:
            base_error = f"pywebview: {pywebview_error}"
        osascript_result["error"] = base_error
    return osascript_result


# 启动时加载并注入 AI 设置（支持无重启使用）
_apply_ai_env(_load_ai_settings())
_restore_jobs_from_store()


# ── Capability API ────────────────────────────────────────────────────

def _agent_capability_route_map() -> Dict[str, Dict[str, str]]:
    return {
        "topic_library": {
            "list": "GET /api/capabilities/topic_library",
            "upsert": "POST /api/capabilities/topic_library",
            "bootstrap": "POST /api/capabilities/topic_library/bootstrap",
        },
        "topic_copy": {"draft": "POST /api/capabilities/topic_copy/draft"},
        "text_rough_cut": {
            "source": "GET /api/capabilities/text_rough_cut/source",
            "plan": "POST /api/capabilities/text_rough_cut/plan",
        },
        "short_clip": {"plan": "POST /api/capabilities/short_clip/plan"},
        "refinement": {
            "plan": "POST /api/capabilities/refinement/plan",
            "handoff": "POST /api/capabilities/refinement/handoff",
            "execute": "POST /api/capabilities/refinement/execute",
            "collect_master": "POST /api/capabilities/refinement/collect_master",
        },
        "publish_prep": {
            "profiles": "GET /api/capabilities/publish_prep/profiles",
            "plan": "POST /api/capabilities/publish_prep/generate",
            "generate": "POST /api/capabilities/publish_prep/generate",
        },
        "subtitle_calibration": {
            "plan": "POST /api/capabilities/subtitle_calibration/plan",
            "run": "POST /api/capabilities/subtitle_calibration/run",
        },
        "image_semantic": {
            "analyze": "POST /api/capabilities/image_semantic/analyze",
            "search": "POST /api/capabilities/image_semantic/search",
        },
        "article_expand": {
            "generate": "POST /api/capabilities/article_expand/generate",
            "plan": "POST /api/capabilities/article_expand/generate",
        },
        "content_publish": {
            "platforms": "GET /api/capabilities/content_publish/platforms",
            "bootstrap": "POST /api/capabilities/content_publish/session/bootstrap",
            "plan": "POST /api/capabilities/content_publish/plan",
            "run": "POST /api/capabilities/content_publish/run",
            "rerun": "POST /api/capabilities/content_publish/rerun",
        },
        "social_export": {
            "profiles": "GET /api/capabilities/social_export/profiles",
            "specs": "GET /api/capabilities/social_export/specs",
            "validate_source": "POST /api/capabilities/social_export/validate_source",
            "plan": "POST /api/capabilities/social_export/plan",
            "run": "POST /api/capabilities/social_export/run",
            "history": "GET /api/capabilities/social_export/history",
            "rerun": "POST /api/capabilities/social_export/rerun",
        },
        "audio_voice": {
            "plan": "POST /api/capabilities/audio_voice/plan",
            "pick_bgm": "POST /api/capabilities/audio_voice/pick_bgm",
            "synthesize": "POST /api/capabilities/audio_voice/synthesize",
            "build_track": "POST /api/capabilities/audio_voice/build_track",
            "mix_master": "POST /api/capabilities/audio_voice/mix_master",
            "run": "POST /api/capabilities/audio_voice/run",
        },
    }


def _list_agent_skills() -> List[Dict[str, Any]]:
    out = [deepcopy(x) for x in _AGENT_SKILL_REGISTRY.values()]
    out.sort(key=lambda item: str(item.get("skill_id", "")).lower())
    return out


def _normalize_skill_retry_policy(policy_raw: Any) -> Dict[str, Any]:
    raw = policy_raw if isinstance(policy_raw, dict) else {}
    try:
        max_retries = int(raw.get("max_retries", 0) or 0)
    except Exception:
        max_retries = 0
    try:
        backoff_ms = int(raw.get("backoff_ms", 0) or 0)
    except Exception:
        backoff_ms = 0
    retry_on_http_raw = raw.get("retry_on_http", [429, 500, 502, 503, 504])
    retry_on_http: List[int] = []
    if isinstance(retry_on_http_raw, list):
        for item in retry_on_http_raw:
            try:
                code = int(item)
            except Exception:
                continue
            if 100 <= code <= 599:
                retry_on_http.append(code)
    if not retry_on_http:
        retry_on_http = [429, 500, 502, 503, 504]
    return {
        "max_retries": max(0, min(max_retries, 3)),
        "backoff_ms": max(0, min(backoff_ms, 5000)),
        "retry_on_http": sorted(set(retry_on_http)),
    }


def _normalize_skill_timeout_seconds(value: Any, default: float = 120.0) -> float:
    try:
        timeout_seconds = float(value if value is not None else default)
    except Exception:
        timeout_seconds = float(default)
    return max(1.0, min(timeout_seconds, 3600.0))


def _normalize_skill_budget_limit(raw: Any) -> Dict[str, int]:
    src = raw if isinstance(raw, dict) else {}
    try:
        max_steps = int(src.get("max_steps", 0) or 0)
    except Exception:
        max_steps = 0
    try:
        max_failures = int(src.get("max_failures", 0) or 0)
    except Exception:
        max_failures = 0
    try:
        max_duration_seconds = int(src.get("max_duration_seconds", 0) or 0)
    except Exception:
        max_duration_seconds = 0
    return {
        "max_steps": max(0, min(max_steps, 200)),
        "max_failures": max(0, min(max_failures, 200)),
        "max_duration_seconds": max(0, min(max_duration_seconds, 7200)),
    }


def _normalize_governance_limit_item(raw: Any) -> Dict[str, int]:
    src = raw if isinstance(raw, dict) else {}
    base = _normalize_skill_budget_limit(src)
    try:
        max_parallel = int(src.get("max_parallel", 0) or 0)
    except Exception:
        max_parallel = 0
    base["max_parallel"] = max(0, min(max_parallel, 8))
    return base


def _normalize_governance_string_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return list(dict.fromkeys(out))


def _normalize_agent_governance_policy(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    default_raw = deepcopy(_AGENT_GOVERNANCE_DEFAULT)
    merged: Dict[str, Any] = deepcopy(default_raw)
    for key in (
        "default_limits",
        "actor_limits",
        "capability_limits",
        "actor_capability_limits",
        "blocked_skills",
        "blocked_capabilities",
        "blocked_skills_by_actor",
        "blocked_capabilities_by_actor",
    ):
        if key in src:
            merged[key] = src.get(key)

    out: Dict[str, Any] = {
        "default_limits": _normalize_governance_limit_item(merged.get("default_limits", {})),
        "actor_limits": {},
        "capability_limits": {},
        "actor_capability_limits": {},
        "blocked_skills": _normalize_governance_string_list(merged.get("blocked_skills", [])),
        "blocked_capabilities": _normalize_governance_string_list(merged.get("blocked_capabilities", [])),
        "blocked_skills_by_actor": {},
        "blocked_capabilities_by_actor": {},
    }

    actor_limits_raw = merged.get("actor_limits", {})
    if isinstance(actor_limits_raw, dict):
        for actor_key, item in actor_limits_raw.items():
            actor_id = str(actor_key or "").strip()
            if actor_id:
                out["actor_limits"][actor_id] = _normalize_governance_limit_item(item)

    capability_limits_raw = merged.get("capability_limits", {})
    if isinstance(capability_limits_raw, dict):
        for capability_key, item in capability_limits_raw.items():
            capability_id = str(capability_key or "").strip()
            if capability_id:
                out["capability_limits"][capability_id] = _normalize_governance_limit_item(item)

    actor_cap_raw = merged.get("actor_capability_limits", {})
    if isinstance(actor_cap_raw, dict):
        for actor_key, cap_map in actor_cap_raw.items():
            actor_id = str(actor_key or "").strip()
            if not actor_id or not isinstance(cap_map, dict):
                continue
            bucket: Dict[str, Dict[str, int]] = {}
            for capability_key, item in cap_map.items():
                capability_id = str(capability_key or "").strip()
                if not capability_id:
                    continue
                bucket[capability_id] = _normalize_governance_limit_item(item)
            if bucket:
                out["actor_capability_limits"][actor_id] = bucket

    for field in ("blocked_skills_by_actor", "blocked_capabilities_by_actor"):
        raw_map = merged.get(field, {})
        if isinstance(raw_map, dict):
            bucket: Dict[str, List[str]] = {}
            for actor_key, values in raw_map.items():
                actor_id = str(actor_key or "").strip()
                if not actor_id:
                    continue
                bucket[actor_id] = _normalize_governance_string_list(values)
            out[field] = bucket
    return out


def _read_agent_governance_policy() -> Dict[str, Any]:
    if _project_dir is None:
        return _normalize_agent_governance_policy({})
    raw = _read_project_json("agent_governance.json", fallback={})
    return _normalize_agent_governance_policy(raw)


def _read_agent_governance_usage() -> Dict[str, Any]:
    raw = _read_project_json("agent_governance_usage.json", fallback={})
    if not isinstance(raw, dict):
        raw = {}
    out = deepcopy(_AGENT_GOVERNANCE_USAGE_DEFAULT)
    actors_raw = raw.get("actors", {})
    out["updated_at"] = str(raw.get("updated_at", "") or "")
    if isinstance(actors_raw, dict):
        out["actors"] = actors_raw
    return out


def _save_agent_governance_usage(usage: Dict[str, Any]) -> Dict[str, Any]:
    out = usage if isinstance(usage, dict) else {}
    out.setdefault("version", 1)
    out["updated_at"] = datetime.now().isoformat(timespec="seconds")
    p = _project_data_path("agent_governance_usage.json")
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _normalize_cost_rate_item(raw: Any, fallback: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    base = {
        "prompt_usd_per_1k_tokens": 0.0,
        "completion_usd_per_1k_tokens": 0.0,
        "compute_usd_per_second": 0.0,
    }
    if isinstance(fallback, dict):
        for key in base.keys():
            try:
                base[key] = max(float(fallback.get(key, base[key]) or 0.0), 0.0)
            except Exception:
                base[key] = max(float(base[key]), 0.0)
    src = raw if isinstance(raw, dict) else {}
    for key in base.keys():
        if key not in src:
            continue
        try:
            base[key] = max(float(src.get(key, base[key]) or 0.0), 0.0)
        except Exception:
            continue
    return base


def _normalize_agent_cost_model_config(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out = deepcopy(_AGENT_COST_MODEL_DEFAULT)
    fallback_rates = _normalize_cost_rate_item(out.get("default_rates", {}))

    default_rates_raw = src.get("default_rates", src)
    out["default_rates"] = _normalize_cost_rate_item(default_rates_raw, fallback=fallback_rates)
    out["providers"] = {}

    providers_raw = src.get("providers", {})
    if not isinstance(providers_raw, dict):
        return out

    for provider_key, provider_item_raw in providers_raw.items():
        provider_id = str(provider_key or "").strip().lower()
        if not provider_id:
            continue
        provider_item = provider_item_raw if isinstance(provider_item_raw, dict) else {}
        provider_default = _normalize_cost_rate_item(
            provider_item.get("default_rates", provider_item),
            fallback=out["default_rates"],
        )
        models_out: Dict[str, Dict[str, float]] = {}
        models_raw = provider_item.get("models", {})
        if isinstance(models_raw, dict):
            for model_key, model_rate_raw in models_raw.items():
                model_id = str(model_key or "").strip()
                if not model_id:
                    continue
                models_out[model_id] = _normalize_cost_rate_item(model_rate_raw, fallback=provider_default)
        out["providers"][provider_id] = {
            "default_rates": provider_default,
            "models": models_out,
        }
    return out


def _read_agent_cost_model_config() -> Dict[str, Any]:
    if _project_dir is None:
        return _normalize_agent_cost_model_config({})
    raw = _read_project_json("agent_cost_model.json", fallback={})
    return _normalize_agent_cost_model_config(raw)


def _extract_pricing_hint_from_response(payload: Dict[str, Any]) -> Dict[str, str]:
    data = payload if isinstance(payload, dict) else {}

    def _pick_text(root: Dict[str, Any], keys: List[str]) -> str:
        for key in keys:
            val = root.get(key)
            if isinstance(val, str):
                t = val.strip()
                if t:
                    return t
        return ""

    provider_keys = ["provider", "ai_provider", "llm_provider", "model_provider"]
    model_keys = ["model", "ai_model", "model_name", "llm_model"]
    roots: List[Dict[str, Any]] = [data]
    for key in ("response", "meta", "metadata", "llm", "model_info"):
        item = data.get(key)
        if isinstance(item, dict):
            roots.append(item)
            for sub_key in ("meta", "metadata", "llm", "model_info"):
                sub_item = item.get(sub_key)
                if isinstance(sub_item, dict):
                    roots.append(sub_item)

    provider = ""
    model = ""
    for root in roots:
        if not provider:
            provider = _pick_text(root, provider_keys)
        if not model:
            model = _pick_text(root, model_keys)
        if provider and model:
            break
    return {"provider": provider.lower(), "model": model}


def _resolve_cost_rates(
    *,
    provider: str,
    model: str,
    cost_model: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = _normalize_agent_cost_model_config(cost_model) if isinstance(cost_model, dict) else _read_agent_cost_model_config()
    default_rates = _normalize_cost_rate_item(cfg.get("default_rates", {}))
    providers = cfg.get("providers", {})
    if not isinstance(providers, dict):
        providers = {}

    provider_norm = str(provider or "").strip().lower()
    model_req = str(model or "").strip()
    selected_rates = deepcopy(default_rates)
    rate_source = "default"
    resolved_model = model_req
    if provider_norm:
        provider_item = providers.get(provider_norm)
        if isinstance(provider_item, dict):
            provider_default = _normalize_cost_rate_item(provider_item.get("default_rates", {}), fallback=selected_rates)
            selected_rates = provider_default
            rate_source = f"provider:{provider_norm}:default"
            models = provider_item.get("models", {})
            if isinstance(models, dict) and model_req:
                if model_req in models and isinstance(models.get(model_req), dict):
                    selected_rates = _normalize_cost_rate_item(models.get(model_req), fallback=selected_rates)
                    rate_source = f"provider:{provider_norm}:model:{model_req}"
                else:
                    lower_map = {
                        str(k).strip().lower(): str(k).strip()
                        for k in models.keys()
                        if str(k).strip()
                    }
                    match_key = lower_map.get(model_req.lower())
                    if match_key and isinstance(models.get(match_key), dict):
                        selected_rates = _normalize_cost_rate_item(models.get(match_key), fallback=selected_rates)
                        resolved_model = match_key
                        rate_source = f"provider:{provider_norm}:model:{match_key}"
    return {
        "provider": provider_norm,
        "model": resolved_model,
        "rate_source": rate_source,
        "rates": selected_rates,
    }


def _extract_usage_tokens_from_response(payload: Dict[str, Any]) -> Dict[str, int]:
    data = payload if isinstance(payload, dict) else {}

    def _pick_usage_obj(root: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("usage", "token_usage", "llm_usage"):
            val = root.get(key)
            if isinstance(val, dict):
                return val
        return {}

    usage = _pick_usage_obj(data)
    if not usage:
        response_data = data.get("response")
        if isinstance(response_data, dict):
            usage = _pick_usage_obj(response_data)

    def _to_int(value) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = 0
        return max(parsed, 0)

    prompt_tokens = _to_int(usage.get("prompt_tokens", usage.get("input_tokens", usage.get("prompt_tokens_total", 0))))
    completion_tokens = _to_int(usage.get("completion_tokens", usage.get("output_tokens", usage.get("completion_tokens_total", 0))))
    total_tokens_raw = usage.get("total_tokens", usage.get("total", 0))
    total_tokens = _to_int(total_tokens_raw)
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _estimate_step_cost_metrics(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    duration_seconds: float,
    provider: str = "",
    model: str = "",
    cost_model: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    p = max(int(prompt_tokens or 0), 0)
    c = max(int(completion_tokens or 0), 0)
    d = max(float(duration_seconds or 0.0), 0.0)
    resolved = _resolve_cost_rates(provider=provider, model=model, cost_model=cost_model)
    rates = resolved.get("rates", {}) if isinstance(resolved.get("rates"), dict) else {}
    prompt_rate = float(rates.get("prompt_usd_per_1k_tokens", 0.0) or 0.0)
    completion_rate = float(rates.get("completion_usd_per_1k_tokens", 0.0) or 0.0)
    compute_rate = float(rates.get("compute_usd_per_second", 0.0) or 0.0)
    prompt_cost = (p / 1000.0) * prompt_rate
    completion_cost = (c / 1000.0) * completion_rate
    compute_cost = d * compute_rate
    total_cost = prompt_cost + completion_cost + compute_cost
    return {
        "prompt_cost_usd": round(prompt_cost, 8),
        "completion_cost_usd": round(completion_cost, 8),
        "compute_cost_usd": round(compute_cost, 8),
        "total_cost_usd": round(total_cost, 8),
        "compute_seconds": round(d, 4),
        "rate_source": str(resolved.get("rate_source", "default") or "default"),
        "provider": str(resolved.get("provider", "") or ""),
        "model": str(resolved.get("model", "") or ""),
        "rates": {
            "prompt_usd_per_1k_tokens": round(prompt_rate, 8),
            "completion_usd_per_1k_tokens": round(completion_rate, 8),
            "compute_usd_per_second": round(compute_rate, 8),
        },
    }


def _normalize_usage_bucket(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}

    def _normalize_recent_run_item(item_raw: Any) -> Optional[Dict[str, Any]]:
        item = item_raw if isinstance(item_raw, dict) else {}
        run_at = str(item.get("run_at", "") or "").strip()
        status_raw = str(item.get("status", "") or "").strip().lower()
        status = status_raw if status_raw in {"ok", "partial", "failed"} else "partial"

        def _to_int(v: Any) -> int:
            try:
                parsed = int(v)
            except Exception:
                parsed = 0
            return max(parsed, 0)

        def _to_float(v: Any) -> float:
            try:
                parsed = float(v)
            except Exception:
                parsed = 0.0
            return max(parsed, 0.0)

        steps_total = _to_int(item.get("steps_total", 0))
        steps_success = _to_int(item.get("steps_success", 0))
        steps_failed = _to_int(item.get("steps_failed", 0))
        steps_skipped = _to_int(item.get("steps_skipped", 0))
        prompt_tokens = _to_int(item.get("prompt_tokens", 0))
        completion_tokens = _to_int(item.get("completion_tokens", 0))
        total_tokens = _to_int(item.get("total_tokens", prompt_tokens + completion_tokens))
        failure_rate_raw = _to_float(item.get("failure_rate", 0.0))
        failure_rate = min(max(failure_rate_raw, 0.0), 1.0)
        if steps_total > 0:
            failure_rate = min(max(float(steps_failed) / float(max(steps_total, 1)), 0.0), 1.0)

        if not run_at and steps_total <= 0 and total_tokens <= 0 and _to_float(item.get("estimated_cost_usd", 0.0)) <= 0.0:
            return None
        return {
            "run_at": run_at,
            "status": status,
            "steps_total": steps_total,
            "steps_success": steps_success,
            "steps_failed": steps_failed,
            "steps_skipped": steps_skipped,
            "failure_rate": round(failure_rate, 4),
            "duration_seconds": round(_to_float(item.get("duration_seconds", 0.0)), 4),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(_to_float(item.get("estimated_cost_usd", 0.0)), 8),
        }

    recent_runs_raw = src.get("recent_runs", [])
    recent_runs: List[Dict[str, Any]] = []
    if isinstance(recent_runs_raw, list):
        for item_raw in recent_runs_raw:
            normalized = _normalize_recent_run_item(item_raw)
            if isinstance(normalized, dict):
                recent_runs.append(normalized)
            if len(recent_runs) >= _AGENT_USAGE_RECENT_RUNS_MAX:
                recent_runs = recent_runs[-_AGENT_USAGE_RECENT_RUNS_MAX:]

    out = {
        "run_count": int(src.get("run_count", 0) or 0),
        "step_count": int(src.get("step_count", 0) or 0),
        "success_step_count": int(src.get("success_step_count", 0) or 0),
        "failed_step_count": int(src.get("failed_step_count", 0) or 0),
        "skipped_step_count": int(src.get("skipped_step_count", 0) or 0),
        "total_duration_seconds": float(src.get("total_duration_seconds", 0.0) or 0.0),
        "last_duration_seconds": float(src.get("last_duration_seconds", 0.0) or 0.0),
        "avg_duration_seconds": float(src.get("avg_duration_seconds", 0.0) or 0.0),
        "total_prompt_tokens": int(src.get("total_prompt_tokens", 0) or 0),
        "total_completion_tokens": int(src.get("total_completion_tokens", 0) or 0),
        "total_tokens": int(src.get("total_tokens", 0) or 0),
        "total_estimated_cost_usd": float(src.get("total_estimated_cost_usd", 0.0) or 0.0),
        "avg_estimated_cost_usd": float(src.get("avg_estimated_cost_usd", 0.0) or 0.0),
        "last_estimated_cost_usd": float(src.get("last_estimated_cost_usd", 0.0) or 0.0),
        "last_run_at": str(src.get("last_run_at", "") or ""),
        "recent_runs": recent_runs,
        "suggested_limits": _normalize_governance_limit_item(src.get("suggested_limits", {})),
    }
    out["run_count"] = max(out["run_count"], 0)
    out["step_count"] = max(out["step_count"], 0)
    out["success_step_count"] = max(out["success_step_count"], 0)
    out["failed_step_count"] = max(out["failed_step_count"], 0)
    out["skipped_step_count"] = max(out["skipped_step_count"], 0)
    out["total_duration_seconds"] = max(out["total_duration_seconds"], 0.0)
    out["last_duration_seconds"] = max(out["last_duration_seconds"], 0.0)
    out["avg_duration_seconds"] = max(out["avg_duration_seconds"], 0.0)
    out["total_prompt_tokens"] = max(out["total_prompt_tokens"], 0)
    out["total_completion_tokens"] = max(out["total_completion_tokens"], 0)
    out["total_tokens"] = max(out["total_tokens"], 0)
    out["total_estimated_cost_usd"] = max(out["total_estimated_cost_usd"], 0.0)
    out["avg_estimated_cost_usd"] = max(out["avg_estimated_cost_usd"], 0.0)
    out["last_estimated_cost_usd"] = max(out["last_estimated_cost_usd"], 0.0)
    return out


def _compute_usage_suggested_limits(bucket: Dict[str, Any]) -> Dict[str, int]:
    run_count = int(bucket.get("run_count", 0) or 0)
    step_count = int(bucket.get("step_count", 0) or 0)
    failed_steps = int(bucket.get("failed_step_count", 0) or 0)
    total_duration = float(bucket.get("total_duration_seconds", 0.0) or 0.0)
    total_cost = float(bucket.get("total_estimated_cost_usd", 0.0) or 0.0)
    total_tokens = int(bucket.get("total_tokens", 0) or 0)
    if run_count <= 0 or step_count <= 0:
        return {"max_steps": 0, "max_failures": 0, "max_duration_seconds": 0, "max_parallel": 0}

    avg_steps = step_count / max(run_count, 1)
    avg_failed_per_run = failed_steps / max(run_count, 1)
    avg_duration = total_duration / max(run_count, 1)
    avg_cost = total_cost / max(run_count, 1)
    avg_tokens = total_tokens / max(run_count, 1)
    failure_rate = failed_steps / max(step_count, 1)

    suggested_max_steps = max(2, min(int(max(avg_steps * 2.0, 2.0)), 200))
    suggested_max_failures = max(1, min(int(max(avg_failed_per_run * 2.0 + 1.0, 1.0)), 200))
    suggested_max_duration = max(30, min(int(max(avg_duration * 2.0, 30.0)), 7200))
    if failure_rate >= 0.35:
        suggested_max_parallel = 1
    elif failure_rate >= 0.20:
        suggested_max_parallel = 2
    else:
        suggested_max_parallel = 4
    if avg_cost >= 0.20 or avg_tokens >= 120000:
        suggested_max_parallel = min(suggested_max_parallel, 1)
        suggested_max_steps = max(2, min(suggested_max_steps, int(max(avg_steps * 1.2, 2))))
    elif avg_cost >= 0.08 or avg_tokens >= 50000:
        suggested_max_parallel = min(suggested_max_parallel, 2)
        suggested_max_steps = max(2, min(suggested_max_steps, int(max(avg_steps * 1.5, 2))))

    recent_runs_raw = bucket.get("recent_runs", [])
    recent_runs: List[Dict[str, Any]] = recent_runs_raw if isinstance(recent_runs_raw, list) else []
    if len(recent_runs) >= 3:
        window = recent_runs[-min(len(recent_runs), 8):]
        total_window = max(len(window), 1)

        recent_failure_rate = sum(float(x.get("failure_rate", 0.0) or 0.0) for x in window) / float(total_window)
        recent_avg_cost = sum(float(x.get("estimated_cost_usd", 0.0) or 0.0) for x in window) / float(total_window)
        recent_avg_duration = sum(float(x.get("duration_seconds", 0.0) or 0.0) for x in window) / float(total_window)
        recent_avg_tokens = sum(int(x.get("total_tokens", 0) or 0) for x in window) / float(total_window)

        success_streak = 0
        for item in reversed(recent_runs):
            if str(item.get("status", "")).lower() == "ok":
                success_streak += 1
            else:
                break

        # High pressure runs should tighten quickly to reduce retries/cost.
        high_pressure = (
            recent_failure_rate >= 0.30
            or recent_avg_cost >= 0.12
            or recent_avg_tokens >= 80000
            or recent_avg_duration >= 300.0
        )
        severe_pressure = (
            recent_failure_rate >= 0.45
            or recent_avg_cost >= 0.20
            or recent_avg_tokens >= 120000
            or recent_avg_duration >= 600.0
        )
        stable_window = (
            recent_failure_rate <= 0.05
            and recent_avg_cost <= 0.03
            and recent_avg_tokens <= 25000
            and recent_avg_duration <= 120.0
        )

        if high_pressure:
            suggested_max_parallel = min(suggested_max_parallel, 1 if severe_pressure else 2)
            suggested_max_steps = max(2, min(suggested_max_steps, int(max(avg_steps * (1.1 if severe_pressure else 1.3), 2))))
            suggested_max_duration = max(30, min(suggested_max_duration, int(max(avg_duration * 1.4, 30.0))))
        elif stable_window and success_streak >= 3:
            # Stable successful window can cautiously loosen dynamic suggestions.
            suggested_max_parallel = min(6, suggested_max_parallel + 1)
            suggested_max_steps = min(200, max(suggested_max_steps, int(max(avg_steps * 2.5, 3.0))))
            suggested_max_failures = min(200, max(suggested_max_failures, int(max(avg_failed_per_run * 2.5 + 1.0, 1.0))))
            suggested_max_duration = min(7200, max(suggested_max_duration, int(max(avg_duration * 2.2, 45.0))))

    return {
        "max_steps": suggested_max_steps,
        "max_failures": suggested_max_failures,
        "max_duration_seconds": suggested_max_duration,
        "max_parallel": suggested_max_parallel,
    }


def _update_usage_bucket(
    bucket_raw: Any,
    *,
    steps_total: int,
    steps_success: int,
    steps_failed: int,
    steps_skipped: int,
    duration_seconds: float,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_cost_usd: float,
    now_iso: str,
) -> Dict[str, Any]:
    bucket = _normalize_usage_bucket(bucket_raw)
    steps_total_i = max(int(steps_total), 0)
    steps_success_i = max(int(steps_success), 0)
    steps_failed_i = max(int(steps_failed), 0)
    steps_skipped_i = max(int(steps_skipped), 0)
    duration_f = max(float(duration_seconds), 0.0)
    prompt_tokens_i = max(int(prompt_tokens), 0)
    completion_tokens_i = max(int(completion_tokens), 0)
    estimated_cost_f = max(float(estimated_cost_usd), 0.0)
    total_tokens_i = prompt_tokens_i + completion_tokens_i
    failure_rate = float(steps_failed_i) / float(max(steps_total_i, 1)) if steps_total_i > 0 else 0.0
    if steps_failed_i <= 0:
        run_status = "ok"
    elif steps_success_i <= 0:
        run_status = "failed"
    else:
        run_status = "partial"

    bucket["run_count"] = int(bucket.get("run_count", 0) or 0) + 1
    bucket["step_count"] = int(bucket.get("step_count", 0) or 0) + steps_total_i
    bucket["success_step_count"] = int(bucket.get("success_step_count", 0) or 0) + steps_success_i
    bucket["failed_step_count"] = int(bucket.get("failed_step_count", 0) or 0) + steps_failed_i
    bucket["skipped_step_count"] = int(bucket.get("skipped_step_count", 0) or 0) + steps_skipped_i
    bucket["total_duration_seconds"] = float(bucket.get("total_duration_seconds", 0.0) or 0.0) + duration_f
    bucket["last_duration_seconds"] = duration_f
    bucket["avg_duration_seconds"] = float(bucket["total_duration_seconds"]) / max(int(bucket["run_count"]), 1)
    bucket["total_prompt_tokens"] = int(bucket.get("total_prompt_tokens", 0) or 0) + prompt_tokens_i
    bucket["total_completion_tokens"] = int(bucket.get("total_completion_tokens", 0) or 0) + completion_tokens_i
    bucket["total_tokens"] = int(bucket.get("total_tokens", 0) or 0) + total_tokens_i
    bucket["total_estimated_cost_usd"] = float(bucket.get("total_estimated_cost_usd", 0.0) or 0.0) + estimated_cost_f
    bucket["last_estimated_cost_usd"] = estimated_cost_f
    bucket["avg_estimated_cost_usd"] = float(bucket["total_estimated_cost_usd"]) / max(int(bucket["run_count"]), 1)
    bucket["last_run_at"] = now_iso
    recent_runs_raw = bucket.get("recent_runs", [])
    recent_runs = list(recent_runs_raw) if isinstance(recent_runs_raw, list) else []
    recent_runs.append({
        "run_at": now_iso,
        "status": run_status,
        "steps_total": steps_total_i,
        "steps_success": steps_success_i,
        "steps_failed": steps_failed_i,
        "steps_skipped": steps_skipped_i,
        "failure_rate": round(min(max(failure_rate, 0.0), 1.0), 4),
        "duration_seconds": round(duration_f, 4),
        "prompt_tokens": prompt_tokens_i,
        "completion_tokens": completion_tokens_i,
        "total_tokens": total_tokens_i,
        "estimated_cost_usd": round(estimated_cost_f, 8),
    })
    if len(recent_runs) > _AGENT_USAGE_RECENT_RUNS_MAX:
        recent_runs = recent_runs[-_AGENT_USAGE_RECENT_RUNS_MAX:]
    bucket["recent_runs"] = recent_runs
    bucket["suggested_limits"] = _compute_usage_suggested_limits(bucket)
    return bucket


def _record_governance_usage_for_skill_flow(
    *,
    actor_id: str,
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    actor = str(actor_id or "").strip()
    if not actor:
        return {"ok": False, "reason": "actor_id 为空"}
    usage = _read_agent_governance_usage()
    actors = usage.get("actors", {})
    if not isinstance(actors, dict):
        actors = {}
    actor_entry = actors.get(actor, {})
    if not isinstance(actor_entry, dict):
        actor_entry = {}
    actor_summary_bucket = actor_entry.get("summary", {})
    cap_buckets = actor_entry.get("capabilities", {})
    if not isinstance(cap_buckets, dict):
        cap_buckets = {}

    total_steps = int(summary.get("total_steps", 0) or 0)
    success_steps = int(summary.get("success_steps", 0) or 0)
    failed_steps = int(summary.get("failed_steps", 0) or 0)
    skipped_steps = int(summary.get("skipped_steps", 0) or 0)
    duration_seconds = float(summary.get("duration_seconds", 0.0) or 0.0)
    steps = summary.get("steps", [])
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_estimated_cost_usd = 0.0
    now_iso = datetime.now().isoformat(timespec="seconds")
    if isinstance(steps, list):
        for item in steps:
            if not isinstance(item, dict):
                continue
            usage_tokens = item.get("usage_tokens", {})
            if isinstance(usage_tokens, dict):
                total_prompt_tokens += max(int(usage_tokens.get("prompt_tokens", 0) or 0), 0)
                total_completion_tokens += max(int(usage_tokens.get("completion_tokens", 0) or 0), 0)
            estimated_cost = item.get("estimated_cost", {})
            if isinstance(estimated_cost, dict):
                total_estimated_cost_usd += max(float(estimated_cost.get("total_cost_usd", 0.0) or 0.0), 0.0)

    actor_summary_bucket = _update_usage_bucket(
        actor_summary_bucket,
        steps_total=total_steps,
        steps_success=success_steps,
        steps_failed=failed_steps,
        steps_skipped=skipped_steps,
        duration_seconds=duration_seconds,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        estimated_cost_usd=total_estimated_cost_usd,
        now_iso=now_iso,
    )

    cap_stats: Dict[str, Dict[str, Any]] = {}
    if isinstance(steps, list):
        for item in steps:
            if not isinstance(item, dict):
                continue
            capability_id = str(item.get("capability_id", "") or "").strip()
            if not capability_id:
                continue
            bucket = cap_stats.setdefault(
                capability_id,
                {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "skipped": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "duration_seconds": 0.0,
                },
            )
            bucket["total"] += 1
            st = str(item.get("status", "") or "").strip().lower()
            if st == "done":
                bucket["success"] += 1
            elif st == "error":
                bucket["failed"] += 1
            elif st == "skipped":
                bucket["skipped"] += 1
            usage_tokens = item.get("usage_tokens", {})
            if isinstance(usage_tokens, dict):
                bucket["prompt_tokens"] += max(int(usage_tokens.get("prompt_tokens", 0) or 0), 0)
                bucket["completion_tokens"] += max(int(usage_tokens.get("completion_tokens", 0) or 0), 0)
            estimated_cost = item.get("estimated_cost", {})
            if isinstance(estimated_cost, dict):
                bucket["estimated_cost_usd"] += max(float(estimated_cost.get("total_cost_usd", 0.0) or 0.0), 0.0)
                bucket["duration_seconds"] += max(float(estimated_cost.get("compute_seconds", 0.0) or 0.0), 0.0)
            else:
                bucket["duration_seconds"] += max(float(item.get("duration_seconds", 0.0) or 0.0), 0.0)

    for capability_id, stat in cap_stats.items():
        old_bucket = cap_buckets.get(capability_id, {})
        cap_buckets[capability_id] = _update_usage_bucket(
            old_bucket,
            steps_total=int(stat.get("total", 0)),
            steps_success=int(stat.get("success", 0)),
            steps_failed=int(stat.get("failed", 0)),
            steps_skipped=int(stat.get("skipped", 0)),
            duration_seconds=float(stat.get("duration_seconds", 0.0) or 0.0),
            prompt_tokens=int(stat.get("prompt_tokens", 0) or 0),
            completion_tokens=int(stat.get("completion_tokens", 0) or 0),
            estimated_cost_usd=float(stat.get("estimated_cost_usd", 0.0) or 0.0),
            now_iso=now_iso,
        )

    actor_entry["summary"] = actor_summary_bucket
    actor_entry["capabilities"] = cap_buckets
    actors[actor] = actor_entry
    usage["actors"] = actors
    saved = _save_agent_governance_usage(usage)
    return {
        "ok": True,
        "actor_id": actor,
        "summary_suggested_limits": actor_summary_bucket.get("suggested_limits", {}),
        "summary_cost": {
            "total_estimated_cost_usd": actor_summary_bucket.get("total_estimated_cost_usd", 0.0),
            "avg_estimated_cost_usd": actor_summary_bucket.get("avg_estimated_cost_usd", 0.0),
            "total_tokens": actor_summary_bucket.get("total_tokens", 0),
        },
        "capability_suggested_limits": {
            cap: (bucket.get("suggested_limits", {}) if isinstance(bucket, dict) else {})
            for cap, bucket in cap_buckets.items()
            if cap in cap_stats
        },
        "usage_file": "data/agent_governance_usage.json",
        "updated_at": saved.get("updated_at", ""),
    }


def _extract_dynamic_limits_from_usage(
    *,
    actor_id: str,
    capability_ids: List[str],
) -> Dict[str, Any]:
    actor = str(actor_id or "").strip()
    if not actor:
        return {"summary": None, "by_capability": {}}
    usage = _read_agent_governance_usage()
    actors = usage.get("actors", {})
    if not isinstance(actors, dict):
        return {"summary": None, "by_capability": {}}
    actor_entry = actors.get(actor, {})
    if not isinstance(actor_entry, dict):
        return {"summary": None, "by_capability": {}}
    summary_bucket = actor_entry.get("summary", {})
    summary_limits = _normalize_governance_limit_item(
        summary_bucket.get("suggested_limits", {}) if isinstance(summary_bucket, dict) else {}
    )
    cap_map = actor_entry.get("capabilities", {})
    out_caps: Dict[str, Dict[str, int]] = {}
    if isinstance(cap_map, dict):
        for capability_id in capability_ids:
            b = cap_map.get(capability_id, {})
            if not isinstance(b, dict):
                continue
            out_caps[capability_id] = _normalize_governance_limit_item(b.get("suggested_limits", {}))
    return {"summary": summary_limits, "by_capability": out_caps}


def _pick_actor_rule(mapping: Any, actor_id: str):
    if not isinstance(mapping, dict):
        return None
    actor = str(actor_id or "").strip()
    if not actor:
        return None
    if actor in mapping:
        return mapping.get(actor)
    lower = actor.lower()
    if lower in mapping:
        return mapping.get(lower)
    return None


def _tighten_governance_limit(base: Dict[str, int], incoming: Dict[str, int], *, source: str, trace: Dict[str, str]):
    if not isinstance(base, dict) or not isinstance(incoming, dict):
        return
    for key in ("max_steps", "max_failures", "max_duration_seconds", "max_parallel"):
        val = int(incoming.get(key, 0) or 0)
        if val <= 0:
            continue
        cur = int(base.get(key, 0) or 0)
        if cur <= 0 or val < cur:
            base[key] = val
            trace[key] = source


def _resolve_agent_governance_for_skill_flow(
    *,
    actor_id: str,
    steps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    policy = _read_agent_governance_policy()
    effective = _normalize_governance_limit_item(policy.get("default_limits", {}))
    trace = {k: "default_limits" for k in effective.keys()}
    actor_rule = _pick_actor_rule(policy.get("actor_limits", {}), actor_id)
    if isinstance(actor_rule, dict):
        _tighten_governance_limit(effective, actor_rule, source=f"actor:{actor_id}", trace=trace)

    capability_ids = sorted({
        str(x.get("capability_id", "") or "").strip()
        for x in (steps or [])
        if isinstance(x, dict) and str(x.get("capability_id", "") or "").strip()
    })
    for capability_id in capability_ids:
        cap_rule = policy.get("capability_limits", {}).get(capability_id) if isinstance(policy.get("capability_limits", {}), dict) else None
        if isinstance(cap_rule, dict):
            _tighten_governance_limit(effective, cap_rule, source=f"capability:{capability_id}", trace=trace)

        actor_cap_map = _pick_actor_rule(policy.get("actor_capability_limits", {}), actor_id)
        actor_cap_rule = actor_cap_map.get(capability_id) if isinstance(actor_cap_map, dict) else None
        if isinstance(actor_cap_rule, dict):
            _tighten_governance_limit(
                effective,
                actor_cap_rule,
                source=f"actor_capability:{actor_id}:{capability_id}",
                trace=trace,
            )

    dynamic_limits = _extract_dynamic_limits_from_usage(
        actor_id=actor_id,
        capability_ids=capability_ids,
    )
    dyn_summary = dynamic_limits.get("summary") if isinstance(dynamic_limits, dict) else None
    if isinstance(dyn_summary, dict):
        _tighten_governance_limit(effective, dyn_summary, source=f"dynamic_actor:{actor_id}", trace=trace)
    dyn_caps = dynamic_limits.get("by_capability") if isinstance(dynamic_limits, dict) else {}
    if isinstance(dyn_caps, dict):
        for capability_id, cap_dyn in dyn_caps.items():
            if isinstance(cap_dyn, dict):
                _tighten_governance_limit(
                    effective,
                    cap_dyn,
                    source=f"dynamic_actor_capability:{actor_id}:{capability_id}",
                    trace=trace,
                )

    blocked_skills = set(_normalize_governance_string_list(policy.get("blocked_skills", [])))
    blocked_caps = set(_normalize_governance_string_list(policy.get("blocked_capabilities", [])))
    blocked_skills_actor = _pick_actor_rule(policy.get("blocked_skills_by_actor", {}), actor_id)
    blocked_caps_actor = _pick_actor_rule(policy.get("blocked_capabilities_by_actor", {}), actor_id)
    blocked_skills.update(_normalize_governance_string_list(blocked_skills_actor))
    blocked_caps.update(_normalize_governance_string_list(blocked_caps_actor))

    return {
        "effective_limits": effective,
        "limit_trace": trace,
        "dynamic_limits": dynamic_limits,
        "blocked_skills": sorted(blocked_skills),
        "blocked_capabilities": sorted(blocked_caps),
        "capability_ids": capability_ids,
    }


def _apply_governance_to_skill_flow(
    *,
    actor_id: str,
    steps: List[Dict[str, Any]],
    requested_budget: Dict[str, int],
    requested_max_parallel: int,
    explicit_max_parallel: bool,
) -> Dict[str, Any]:
    governance = _resolve_agent_governance_for_skill_flow(actor_id=actor_id, steps=steps)
    limits = governance.get("effective_limits", {}) if isinstance(governance.get("effective_limits"), dict) else {}
    blocked_skills = set(governance.get("blocked_skills", [])) if isinstance(governance.get("blocked_skills"), list) else set()
    blocked_caps = set(governance.get("blocked_capabilities", [])) if isinstance(governance.get("blocked_capabilities"), list) else set()

    for step in steps:
        skill_id = str(step.get("skill_id", "") or "").strip()
        capability_id = str(step.get("capability_id", "") or "").strip()
        if skill_id and skill_id in blocked_skills:
            raise ValueError(f"skill 被治理策略禁用: {skill_id}")
        if capability_id and capability_id in blocked_caps:
            raise ValueError(f"capability 被治理策略禁用: {capability_id}")

    final_budget = _normalize_skill_budget_limit(requested_budget)
    for field in ("max_steps", "max_failures", "max_duration_seconds"):
        req_val = int(final_budget.get(field, 0) or 0)
        limit_val = int(limits.get(field, 0) or 0)
        if req_val > 0 and limit_val > 0 and req_val > limit_val:
            raise ValueError(f"超出治理额度: {field}={req_val} > {limit_val}")
        if req_val <= 0:
            final_budget[field] = limit_val if limit_val > 0 else 0

    req_mp = max(1, min(int(requested_max_parallel or 1), 8))
    limit_mp = int(limits.get("max_parallel", 0) or 0)
    if explicit_max_parallel and limit_mp > 0 and req_mp > limit_mp:
        raise ValueError(f"超出治理额度: max_parallel={req_mp} > {limit_mp}")
    final_mp = req_mp
    if not explicit_max_parallel and limit_mp > 0:
        final_mp = limit_mp
    if final_budget.get("max_steps", 0) > 0 and len(steps) > int(final_budget.get("max_steps", 0)):
        raise ValueError(f"steps 超出预算上限: {len(steps)} > {final_budget.get('max_steps')}")

    return {
        "budget_limit": final_budget,
        "max_parallel": final_mp,
        "governance": governance,
    }


def _normalize_agent_skill_condition(condition_raw: Any) -> Dict[str, Any]:
    raw = condition_raw if isinstance(condition_raw, dict) else {}
    if not raw:
        return {}
    depends_on_raw = raw.get("depends_on", [])
    depends_on: List[str] = []
    if isinstance(depends_on_raw, list):
        for item in depends_on_raw:
            sid = _normalize_agent_template_id(str(item or "").strip())
            if sid:
                depends_on.append(sid)
    status_in_raw = raw.get("status_in", ["done"])
    status_in: List[str] = []
    if isinstance(status_in_raw, list):
        for item in status_in_raw:
            st = str(item or "").strip().lower()
            if st in {"done", "error", "skipped"}:
                status_in.append(st)
    if not status_in:
        status_in = ["done"]
    return {
        "depends_on": list(dict.fromkeys(depends_on)),
        "status_in": sorted(set(status_in)),
        "require_all": _coerce_bool(raw.get("require_all", True), default=True),
        "if_overall_ok": _coerce_bool(raw.get("if_overall_ok", False), default=False),
    }


def _capability_supports_input_mode(capability_id: str) -> bool:
    cid = str(capability_id or "").strip().lower()
    return cid in {
        "topic_library",
        "topic_copy",
        "text_rough_cut",
        "short_clip",
        "refinement",
        "publish_prep",
        "subtitle_calibration",
        "image_semantic",
        "article_expand",
        "content_publish",
        "social_export",
        "audio_voice",
    }


def _normalize_agent_input_mode_value(raw_value: Any) -> str:
    text = str(raw_value or "").strip().lower()
    if text == "auto":
        return "project" if _project_dir is not None else "inline"
    return _parse_capability_input_mode(text or "project", default="project")


def _apply_agent_capability_input_defaults(
    capability_id: str,
    input_payload: Dict[str, Any],
    *,
    default_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out = deepcopy(default_input) if isinstance(default_input, dict) else {}
    out.update(input_payload if isinstance(input_payload, dict) else {})

    if not _capability_supports_input_mode(capability_id):
        return out
    if "input_mode" in out:
        out["input_mode"] = _normalize_agent_input_mode_value(out.get("input_mode"))
    else:
        out["input_mode"] = "project" if _project_dir is not None else "inline"
    return out


def _normalize_agent_skill_steps(
    steps_raw: Any,
    *,
    default_retry_policy: Optional[Dict[str, Any]] = None,
    default_timeout_seconds: float = 120.0,
) -> List[Dict[str, Any]]:
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("skills 不能为空，且必须是数组")
    out: List[Dict[str, Any]] = []
    for idx, item in enumerate(steps_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"skills[{idx}] 必须是对象")
        skill_id = str(item.get("skill_id", "") or "").strip()
        if not skill_id:
            raise ValueError(f"skills[{idx}].skill_id 不能为空")
        skill_spec = _AGENT_SKILL_REGISTRY.get(skill_id)
        if not isinstance(skill_spec, dict):
            raise ValueError(f"不支持的 skill_id: {skill_id}")

        input_payload = item.get("input", {})
        if input_payload is None:
            input_payload = {}
        if not isinstance(input_payload, dict):
            raise ValueError(f"skills[{idx}].input 必须是对象")
        capability_id = str(skill_spec.get("capability_id", "") or "")
        input_payload = _apply_agent_capability_input_defaults(
            capability_id,
            input_payload,
            default_input=skill_spec.get("default_input", {}),
        )

        retry_base = default_retry_policy if isinstance(default_retry_policy, dict) else {}
        retry_policy = _normalize_skill_retry_policy(
            item.get("retry_policy", retry_base),
        )
        timeout_seconds = _normalize_skill_timeout_seconds(
            item.get("timeout_seconds", default_timeout_seconds),
            default=default_timeout_seconds,
        )
        continue_on_error = _coerce_bool(item.get("continue_on_error", False), default=False)
        step_id_raw = str(item.get("step_id", "") or "").strip()
        step_id = _normalize_agent_template_id(step_id_raw) or f"step_{idx:02d}"
        condition = _normalize_agent_skill_condition(item.get("condition", item.get("when", {})))

        out.append({
            "index": idx,
            "step_id": step_id,
            "skill_id": skill_id,
            "skill_name": str(skill_spec.get("name", "") or ""),
            "capability_id": capability_id,
            "method": str(skill_spec.get("method", "POST") or "POST").strip().upper(),
            "endpoint": str(skill_spec.get("endpoint", "") or "").strip(),
            "input": deepcopy(input_payload),
            "retry_policy": retry_policy,
            "timeout_seconds": timeout_seconds,
            "continue_on_error": continue_on_error,
            "condition": condition,
        })
    return out


def _resolve_agent_primary_call(
    *,
    capability_id: str,
    routes: Dict[str, str],
    action: str = "auto",
) -> Dict[str, str]:
    action_norm = str(action or "auto").strip().lower()
    picked = ""
    if action_norm and action_norm != "auto":
        picked = str(routes.get(action_norm, "") or "").strip()
        if not picked:
            raise ValueError(f"capability={capability_id} 不支持 action={action_norm}")
    else:
        picked = (
            str(routes.get("run", "") or "").strip()
            or str(routes.get("plan", "") or "").strip()
            or str(routes.get("draft", "") or "").strip()
            or str(routes.get("list", "") or "").strip()
            or str(next(iter(routes.values()), "") or "").strip()
        )
    if not picked:
        raise ValueError(f"capability={capability_id} 缺少可执行路由")
    method, endpoint = picked.split(" ", 1) if " " in picked else ("POST", picked)
    return {"method": str(method or "POST").strip().upper(), "endpoint": str(endpoint or "").strip()}


def _invoke_agent_primary_call(
    *,
    method: str,
    endpoint: str,
    payload: Dict,
    request_context: Dict[str, str],
) -> Dict:
    method_upper = str(method or "POST").strip().upper()
    req_payload = dict(payload) if isinstance(payload, dict) else {}

    with app.test_client() as client:
        if method_upper == "GET":
            query: Dict[str, str] = {}
            for k, v in req_payload.items():
                if v is None:
                    continue
                if isinstance(v, dict):
                    query[str(k)] = json.dumps(v, ensure_ascii=False)
                elif isinstance(v, (list, tuple, set)):
                    query[str(k)] = ",".join(str(x) for x in v)
                else:
                    query[str(k)] = str(v)
            for k in ("actor_type", "actor_id", "run_mode", "idempotency_key", "trace_id"):
                val = str(request_context.get(k, "") or "").strip()
                if val:
                    query[k] = val
            resp = client.open(endpoint, method=method_upper, query_string=query)
        else:
            for k in ("actor_type", "actor_id", "run_mode", "idempotency_key", "trace_id"):
                val = str(request_context.get(k, "") or "").strip()
                if val and k not in req_payload:
                    req_payload[k] = val
            resp = client.open(endpoint, method=method_upper, json=req_payload)

    data = resp.get_json(silent=True)
    if not isinstance(data, dict):
        data = {
            "ok": False,
            "error": f"目标接口返回非 JSON: {endpoint}",
            "status_code": int(resp.status_code),
        }
    return {"status_code": int(resp.status_code), "data": data}


_WORKFLOW_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _workflow_get_path_value(path_expr: str, context: Dict[str, Any]) -> Any:
    path = str(path_expr or "").strip()
    if not path:
        return None
    cur: Any = context
    for token in path.split("."):
        key = str(token or "").strip()
        if not key:
            return None
        if isinstance(cur, dict):
            if key not in cur:
                return None
            cur = cur.get(key)
            continue
        if isinstance(cur, list):
            try:
                idx = int(key)
            except Exception:
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        return None
    return deepcopy(cur)


def _resolve_workflow_templates(
    value: Any,
    *,
    context: Dict[str, Any],
    warnings: List[str],
) -> Any:
    if isinstance(value, dict):
        return {
            k: _resolve_workflow_templates(v, context=context, warnings=warnings)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_workflow_templates(item, context=context, warnings=warnings)
            for item in value
        ]
    if not isinstance(value, str):
        return value

    text = value
    matches = list(_WORKFLOW_TEMPLATE_PATTERN.finditer(text))
    if not matches:
        return value

    if len(matches) == 1 and matches[0].span() == (0, len(text)):
        key = str(matches[0].group(1) or "").strip()
        resolved = _workflow_get_path_value(key, context)
        if resolved is None:
            warnings.append(f"workflow 模板变量未命中: {key}")
            return value
        return resolved

    out = text
    for match in matches:
        key = str(match.group(1) or "").strip()
        resolved = _workflow_get_path_value(key, context)
        if resolved is None:
            warnings.append(f"workflow 模板变量未命中: {key}")
            continue
        if isinstance(resolved, (dict, list)):
            repl = json.dumps(resolved, ensure_ascii=False)
        else:
            repl = str(resolved)
        out = out.replace(match.group(0), repl)
    return out


def _workflow_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "0", "false", "no", "off", "null", "none"}:
            return False
        if text in {"1", "true", "yes", "on"}:
            return True
        return True
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return bool(value)


def _workflow_pick_next_step_id(
    *,
    step: Dict[str, Any],
    current_step_id: str,
    default_next_map: Dict[str, str],
    status: str,
) -> str:
    st = str(status or "").strip().lower()
    next_explicit = str(step.get("next_step_id", "") or "").strip()
    next_success = str(step.get("next_on_success", "") or "").strip()
    next_error = str(step.get("next_on_error", "") or "").strip()
    next_skip = str(step.get("next_on_skip", "") or "").strip()

    if st == "error":
        return next_error or next_explicit or default_next_map.get(current_step_id, "")
    if st == "skipped":
        return next_skip or next_explicit or default_next_map.get(current_step_id, "")
    return next_success or next_explicit or default_next_map.get(current_step_id, "")


def _workflow_pick_target_with_source(
    *candidates: Tuple[Any, str],
) -> Tuple[str, str]:
    for target_raw, source in candidates:
        target = str(target_raw or "").strip()
        if target:
            return target, str(source or "").strip() or "unknown"
    return "", "none"


def _workflow_graph_has_cycle(adjacency: Dict[str, List[str]]) -> bool:
    state: Dict[str, int] = {}
    # 0=unvisited, 1=visiting, 2=done

    def _dfs(node: str) -> bool:
        st = state.get(node, 0)
        if st == 1:
            return True
        if st == 2:
            return False
        state[node] = 1
        for nxt in adjacency.get(node, []):
            if _dfs(nxt):
                return True
        state[node] = 2
        return False

    for node in adjacency.keys():
        if state.get(node, 0) == 0 and _dfs(node):
            return True
    return False


def _build_custom_workflow_graph(
    *,
    steps: List[Dict[str, Any]],
    requested_start_step_id: str,
) -> Dict[str, Any]:
    rows = steps if isinstance(steps, list) else []
    ordered_step_ids: List[str] = []
    step_map: Dict[str, Dict[str, Any]] = {}
    default_next_map: Dict[str, str] = {}
    nodes: List[Dict[str, Any]] = []
    transitions: List[Dict[str, Any]] = []
    edge_seen = set()
    edges: List[Dict[str, str]] = []

    for idx, step in enumerate(rows):
        sid = str(step.get("step_id", "") or "").strip()
        if not sid:
            continue
        ordered_step_ids.append(sid)
        step_map[sid] = step
        default_next_map[sid] = (
            str(rows[idx + 1].get("step_id", "") or "").strip()
            if idx + 1 < len(rows)
            else ""
        )
        nodes.append(
            {
                "index": int(step.get("index", idx + 1) or (idx + 1)),
                "step_id": sid,
                "node_type": str(step.get("node_type", "action") or "action"),
                "capability_id": str(step.get("capability_id", "") or ""),
                "action": str(step.get("action", "auto") or "auto"),
                "enabled": _coerce_bool(step.get("enabled", True), default=True),
            }
        )

    def _append_transition_edge(
        from_step: str,
        to_step: str,
        *,
        when: str,
        source: str,
    ):
        tgt = str(to_step or "").strip()
        if not tgt:
            return
        transition_key = (str(from_step or "").strip(), str(when or "").strip(), tgt, str(source or "").strip())
        if transition_key in edge_seen:
            return
        edge_seen.add(transition_key)
        edges.append(
            {
                "from": str(from_step or "").strip(),
                "to": tgt,
                "when": str(when or "").strip(),
                "source": str(source or "").strip(),
            }
        )

    for sid in ordered_step_ids:
        step = step_map.get(sid, {})
        node_type = str(step.get("node_type", "action") or "action").strip().lower()
        next_step_id = str(step.get("next_step_id", "") or "").strip()
        next_on_success = str(step.get("next_on_success", "") or "").strip()
        next_on_error = str(step.get("next_on_error", "") or "").strip()
        next_on_skip = str(step.get("next_on_skip", "") or "").strip()
        default_next = default_next_map.get(sid, "")

        if node_type == "condition":
            true_to, true_source = _workflow_pick_target_with_source(
                (next_on_success, "next_on_success"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            false_to, false_source = _workflow_pick_target_with_source(
                (next_on_error, "next_on_error"),
                (next_on_skip, "next_on_skip"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            branches = [
                {"when": "condition_true", "to": true_to, "source": true_source},
                {"when": "condition_false", "to": false_to, "source": false_source},
            ]
        else:
            success_to, success_source = _workflow_pick_target_with_source(
                (next_on_success, "next_on_success"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            error_to, error_source = _workflow_pick_target_with_source(
                (next_on_error, "next_on_error"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            skip_to, skip_source = _workflow_pick_target_with_source(
                (next_on_skip, "next_on_skip"),
                (next_step_id, "next_step_id"),
                (default_next, "implicit_sequence"),
            )
            branches = [
                {"when": "success", "to": success_to, "source": success_source},
                {"when": "error", "to": error_to, "source": error_source},
                {"when": "skip", "to": skip_to, "source": skip_source},
            ]

        for branch in branches:
            _append_transition_edge(
                sid,
                branch.get("to", ""),
                when=str(branch.get("when", "") or ""),
                source=str(branch.get("source", "") or ""),
            )
        transitions.append(
            {
                "step_id": sid,
                "node_type": node_type,
                "branches": branches,
            }
        )

    requested_start = _normalize_agent_template_id(requested_start_step_id)
    resolved_start = requested_start if requested_start in step_map else (ordered_step_ids[0] if ordered_step_ids else "")

    adjacency: Dict[str, List[str]] = {}
    for sid in ordered_step_ids:
        adjacency.setdefault(sid, [])
    for edge in edges:
        frm = str(edge.get("from", "") or "").strip()
        to = str(edge.get("to", "") or "").strip()
        if not frm or not to:
            continue
        if frm not in adjacency:
            adjacency[frm] = []
        if to not in adjacency[frm]:
            adjacency[frm].append(to)

    reachable = set()
    if resolved_start:
        stack = [resolved_start]
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            for nxt in adjacency.get(cur, []):
                if nxt not in reachable:
                    stack.append(nxt)

    has_cycle = _workflow_graph_has_cycle(adjacency)
    unreached = [sid for sid in ordered_step_ids if sid not in reachable]

    return {
        "requested_start_step_id": requested_start,
        "start_step_id": resolved_start,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "transitions": transitions,
        "has_cycle": bool(has_cycle),
        "unreached_nodes": unreached,
    }


def _build_failed_only_workflow_subset(
    *,
    workflow: Dict[str, Any],
    base_run: Dict[str, Any],
) -> Dict[str, Any]:
    steps = workflow.get("steps", []) if isinstance(workflow.get("steps"), list) else []
    if not steps:
        raise ValueError("workflow.steps 不能为空")

    failed_step_ids = [
        _normalize_agent_template_id(step.get("step_id", ""))
        for step in (base_run.get("steps", []) if isinstance(base_run.get("steps"), list) else [])
        if str(step.get("status", "") or "").strip().lower() == "error"
    ]
    failed_set = {sid for sid in failed_step_ids if sid}
    if not failed_set:
        raise ValueError("历史 run 没有失败步骤，无法 rerun_failed_only")

    step_order: Dict[str, int] = {}
    step_id_set = set()
    for idx, step in enumerate(steps):
        sid = _normalize_agent_template_id(step.get("step_id", ""))
        if not sid:
            continue
        step_order[sid] = idx
        step_id_set.add(sid)

    failed_set = {sid for sid in failed_set if sid in step_id_set}
    if not failed_set:
        raise ValueError("无法匹配失败步骤到当前 workflow 定义")

    requested_start = _normalize_agent_template_id(workflow.get("start_step_id", ""))
    graph = _build_custom_workflow_graph(
        steps=steps,
        requested_start_step_id=requested_start,
    )

    reverse_adj: Dict[str, set] = {}
    for edge in (graph.get("edges", []) if isinstance(graph.get("edges"), list) else []):
        if not isinstance(edge, dict):
            continue
        frm = _normalize_agent_template_id(edge.get("from", ""))
        to = _normalize_agent_template_id(edge.get("to", ""))
        if not frm or not to:
            continue
        reverse_adj.setdefault(to, set()).add(frm)

    required_set = set(failed_set)
    stack = list(failed_set)
    while stack:
        cur = stack.pop()
        for parent in reverse_adj.get(cur, set()):
            if parent in required_set:
                continue
            required_set.add(parent)
            stack.append(parent)

    subset_steps: List[Dict[str, Any]] = []
    included_set = set()
    for step in steps:
        sid = _normalize_agent_template_id(step.get("step_id", ""))
        if not sid or sid not in required_set:
            continue
        subset_steps.append(deepcopy(step))
        included_set.add(sid)
    if not subset_steps:
        raise ValueError("无法匹配失败步骤到当前 workflow 定义")

    for step in subset_steps:
        for route_key in ("next_step_id", "next_on_success", "next_on_error", "next_on_skip"):
            target = _normalize_agent_template_id(step.get(route_key, ""))
            if target and target not in included_set:
                step[route_key] = ""

    start_step_id = requested_start if requested_start in included_set else ""
    if not start_step_id:
        sub_graph = _build_custom_workflow_graph(steps=subset_steps, requested_start_step_id="")
        in_degree = {
            _normalize_agent_template_id(step.get("step_id", "")): 0
            for step in subset_steps
            if _normalize_agent_template_id(step.get("step_id", ""))
        }
        for edge in (sub_graph.get("edges", []) if isinstance(sub_graph.get("edges"), list) else []):
            if not isinstance(edge, dict):
                continue
            to = _normalize_agent_template_id(edge.get("to", ""))
            frm = _normalize_agent_template_id(edge.get("from", ""))
            if to in in_degree and frm in in_degree:
                in_degree[to] = int(in_degree.get(to, 0) or 0) + 1
        roots = [sid for sid, deg in in_degree.items() if deg == 0]
        if roots:
            roots.sort(key=lambda sid: int(step_order.get(sid, 10**9)))
            start_step_id = roots[0]
        else:
            start_step_id = _normalize_agent_template_id(subset_steps[0].get("step_id", ""))

    out = deepcopy(workflow)
    out["steps"] = subset_steps
    out["start_step_id"] = start_step_id
    return out


def _resolve_custom_workflow_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    workflow_raw = raw.get("workflow")
    if isinstance(workflow_raw, dict):
        return _normalize_custom_workflow_payload(workflow_raw)

    workflow_id = _normalize_agent_template_id(raw.get("workflow_id", ""))
    if workflow_id and not str(raw.get("workflow", "")).strip():
        store = _read_custom_workflow_store()
        item = store.get(workflow_id)
        if isinstance(item, dict):
            return deepcopy(item)
        raise ValueError(f"workflow 不存在: {workflow_id}")

    if isinstance(raw.get("steps"), list):
        return _normalize_custom_workflow_payload(raw)

    raise ValueError("缺少 workflow/workflow_id（或 inline steps）")


def _build_custom_workflow_plan(
    *,
    workflow: Dict[str, Any],
    payload: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    route_map = _agent_capability_route_map()
    steps_raw = workflow.get("steps", []) if isinstance(workflow, dict) else []
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("workflow.steps 不能为空")

    step_inputs_raw = payload.get("step_inputs", {})
    step_inputs = step_inputs_raw if isinstance(step_inputs_raw, dict) else {}
    workflow_input_raw = payload.get("input", {})
    workflow_input = workflow_input_raw if isinstance(workflow_input_raw, dict) else {}
    workflow_default_mode = str(workflow.get("input_mode", "auto") or "auto").strip().lower()
    if workflow_default_mode not in {"auto", "project", "inline"}:
        workflow_default_mode = "auto"

    planned_steps: List[Dict[str, Any]] = []
    for idx, step in enumerate(steps_raw, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{idx}] 必须是对象")
        node_type = str(step.get("node_type", "action") or "action").strip().lower()
        if node_type not in {"action", "condition"}:
            raise ValueError(f"steps[{idx}].node_type 仅支持 action/condition")
        capability_id = str(step.get("capability_id", "") or "").strip().lower()
        action = str(step.get("action", "auto") or "auto").strip().lower()
        if not action:
            action = "auto"

        step_id = _normalize_agent_template_id(step.get("step_id", "")) or f"step_{idx:02d}"
        input_template = step.get("input", {})
        if input_template is None:
            input_template = {}
        if not isinstance(input_template, dict):
            raise ValueError(f"steps[{idx}].input 必须是对象")
        input_template = deepcopy(input_template)

        step_override = step_inputs.get(step_id, {})
        if isinstance(step_override, dict) and step_override:
            input_template = _deep_merge_dict(input_template, step_override)

        candidate_mode = str(step.get("input_mode", workflow_default_mode) or workflow_default_mode).strip().lower()
        if candidate_mode not in {"auto", "project", "inline"}:
            candidate_mode = workflow_default_mode

        resolved_method = "POST"
        resolved_endpoint = ""
        if node_type == "action":
            if not capability_id:
                raise ValueError(f"steps[{idx}].capability_id 不能为空")
            routes = route_map.get(capability_id)
            if not isinstance(routes, dict) or not routes:
                raise ValueError(f"steps[{idx}] 不支持 capability_id={capability_id}")
            resolved = _resolve_agent_primary_call(capability_id=capability_id, routes=routes, action=action)
            resolved_method = str(resolved.get("method", "POST") or "POST").strip().upper()
            resolved_endpoint = str(resolved.get("endpoint", "") or "").strip()

            if _capability_supports_input_mode(capability_id):
                if "input_mode" not in input_template:
                    input_template["input_mode"] = candidate_mode
                input_template = _apply_agent_capability_input_defaults(capability_id, input_template)

            if dry_run and resolved_method != "GET" and "dry_run" not in input_template:
                input_template["dry_run"] = True
        else:
            if capability_id:
                # condition 节点允许 capability_id 留空；若传入则仅作为注释信息保留
                capability_id = str(capability_id).strip().lower()

        planned_steps.append(
            {
                "index": idx,
                "step_id": step_id,
                "node_type": node_type,
                "name": str(step.get("name", "") or "").strip(),
                "description": str(step.get("description", "") or "").strip(),
                "capability_id": capability_id,
                "action": action,
                "method": resolved_method,
                "endpoint": resolved_endpoint,
                "input_template": input_template,
                "condition": deepcopy(step.get("condition", "")),
                "run_if": deepcopy(step.get("run_if", "")),
                "continue_on_error": _coerce_bool(step.get("continue_on_error", False), default=False),
                "enabled": _coerce_bool(step.get("enabled", True), default=True),
                "save_as": _normalize_agent_template_id(step.get("save_as", "")),
                "next_step_id": _normalize_agent_template_id(step.get("next_step_id", "")),
                "next_on_success": _normalize_agent_template_id(step.get("next_on_success", "")),
                "next_on_error": _normalize_agent_template_id(step.get("next_on_error", "")),
                "next_on_skip": _normalize_agent_template_id(step.get("next_on_skip", "")),
            }
        )

    step_ids = {str(item.get("step_id", "") or "") for item in planned_steps}
    for item in planned_steps:
        sid = str(item.get("step_id", "") or "")
        for route_key in ("next_step_id", "next_on_success", "next_on_error", "next_on_skip"):
            target = str(item.get(route_key, "") or "").strip()
            if target and target not in step_ids:
                raise ValueError(f"step={sid} 的 {route_key} 指向不存在的 step_id: {target}")

    start_step_id = _normalize_agent_template_id(payload.get("start_step_id", workflow.get("start_step_id", "")))
    graph = _build_custom_workflow_graph(
        steps=planned_steps,
        requested_start_step_id=start_step_id,
    )

    return {
        "workflow_id": str(workflow.get("workflow_id", "") or ""),
        "name": str(workflow.get("name", "") or ""),
        "description": str(workflow.get("description", "") or ""),
        "input_mode": workflow_default_mode,
        "input": deepcopy(workflow_input),
        "start_step_id": start_step_id,
        "graph": graph,
        "dry_run": bool(dry_run),
        "steps": planned_steps,
        "total_steps": len(planned_steps),
    }


def _execute_custom_workflow_plan(
    *,
    plan: Dict[str, Any],
    request_context: Dict[str, str],
    job_id: str,
) -> Dict[str, Any]:
    started_at_iso = datetime.now().isoformat(timespec="seconds")
    started = time.monotonic()
    steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
    total = len(steps)

    step_map: Dict[str, Dict[str, Any]] = {}
    ordered_step_ids: List[str] = []
    default_next_map: Dict[str, str] = {}
    for idx, step in enumerate(steps):
        sid = str(step.get("step_id", "") or "").strip()
        if not sid:
            continue
        step_map[sid] = step
        ordered_step_ids.append(sid)
        default_next_map[sid] = (
            str(steps[idx + 1].get("step_id", "") or "").strip()
            if idx + 1 < len(steps)
            else ""
        )

    history_steps: List[Dict[str, Any]] = []
    warnings: List[str] = []
    artifact_rows: List[Dict[str, str]] = []
    artifact_seen = set()
    execution_path: List[str] = []
    reached_set = set()

    state = "done"
    success_count = 0
    failed_count = 0
    skipped_count = 0

    template_context: Dict[str, Any] = {
        "workflow": {"input": deepcopy(plan.get("input", {})) if isinstance(plan.get("input"), dict) else {}},
        "input": deepcopy(plan.get("input", {})) if isinstance(plan.get("input"), dict) else {},
        "steps": {},
        "vars": {},
        "last": {},
        "request_context": deepcopy(request_context),
    }

    start_step_id = _normalize_agent_template_id(plan.get("start_step_id", ""))
    if not start_step_id:
        start_step_id = ordered_step_ids[0] if ordered_step_ids else ""
    if start_step_id and start_step_id not in step_map:
        warnings.append(f"start_step_id 不存在，已回退首节点: {start_step_id}")
        start_step_id = ordered_step_ids[0] if ordered_step_ids else ""

    max_hops = max(total * 4, 20)
    hops = 0
    current_step_id = start_step_id
    while current_step_id:
        hops += 1
        if hops > max_hops:
            warnings.append(f"workflow 路径超过最大跳数 {max_hops}，已提前停止（可能存在环路）")
            break
        if current_step_id in reached_set:
            warnings.append(f"检测到环路或重复节点: {current_step_id}，已停止")
            break
        step = step_map.get(current_step_id)
        if not isinstance(step, dict):
            warnings.append(f"节点不存在: {current_step_id}，执行提前终止")
            break
        reached_set.add(current_step_id)
        execution_path.append(current_step_id)

        idx = int(step.get("index", len(history_steps) + 1) or (len(history_steps) + 1))
        step_id = str(step.get("step_id", current_step_id) or current_step_id)
        node_type = str(step.get("node_type", "action") or "action").strip().lower()
        continue_on_error = _coerce_bool(step.get("continue_on_error", False), default=False)

        if _jobs.get(job_id, {}).get("cancel_requested"):
            raise JobCancelledError("任务已取消")

        progress = min(10 + int((len(execution_path) - 1) * 80 / max(total, 1)), 89)
        _jobs[job_id]["progress"] = progress
        _jobs[job_id]["log"].append(
            f"[Workflow] step_id={step_id} type={node_type} {step.get('method')} {step.get('endpoint')}"
        )

        base_item: Dict[str, Any] = {
            "index": idx,
            "step_id": step_id,
            "node_type": node_type,
            "capability_id": str(step.get("capability_id", "") or ""),
            "action": str(step.get("action", "auto") or "auto"),
            "method": str(step.get("method", "POST") or "POST"),
            "endpoint": str(step.get("endpoint", "") or ""),
            "continue_on_error": continue_on_error,
            "enabled": _coerce_bool(step.get("enabled", True), default=True),
            "next_step_id": str(step.get("next_step_id", "") or ""),
            "next_on_success": str(step.get("next_on_success", "") or ""),
            "next_on_error": str(step.get("next_on_error", "") or ""),
            "next_on_skip": str(step.get("next_on_skip", "") or ""),
        }

        next_step_id = ""
        request_payload: Dict[str, Any] = {}
        status_code = 0
        response_data: Dict[str, Any] = {}
        step_status = "done"
        step_error = ""
        step_duration = 0.0

        if not _coerce_bool(step.get("enabled", True), default=True):
            step_status = "skipped"
            step_error = "步骤 disabled=true"
            skipped_count += 1
            next_step_id = _workflow_pick_next_step_id(
                step=step,
                current_step_id=step_id,
                default_next_map=default_next_map,
                status="skipped",
            )
            response_data = {"ok": True, "skipped": True, "reason": step_error}
        elif node_type == "condition":
            cond_raw = step.get("condition", True)
            resolved_cond = _resolve_workflow_templates(
                deepcopy(cond_raw),
                context=template_context,
                warnings=warnings,
            )
            passed = _workflow_truthy(resolved_cond)
            step_status = "done"
            status_code = 200
            response_data = {"ok": True, "passed": passed, "condition": resolved_cond}
            step_duration = 0.0001
            success_count += 1
            if passed:
                next_step_id = (
                    str(step.get("next_on_success", "") or "").strip()
                    or str(step.get("next_step_id", "") or "").strip()
                    or default_next_map.get(step_id, "")
                )
            else:
                next_step_id = (
                    str(step.get("next_on_error", "") or "").strip()
                    or str(step.get("next_on_skip", "") or "").strip()
                    or str(step.get("next_step_id", "") or "").strip()
                    or default_next_map.get(step_id, "")
                )
        else:
            run_if_raw = step.get("run_if", "")
            run_if_enabled = not (
                run_if_raw is None
                or (isinstance(run_if_raw, str) and not str(run_if_raw).strip())
            )
            if run_if_enabled:
                run_if_resolved = _resolve_workflow_templates(
                    deepcopy(run_if_raw),
                    context=template_context,
                    warnings=warnings,
                )
                if not _workflow_truthy(run_if_resolved):
                    step_status = "skipped"
                    step_error = "run_if 条件不满足"
                    skipped_count += 1
                    response_data = {"ok": True, "skipped": True, "run_if": run_if_resolved}
                    next_step_id = _workflow_pick_next_step_id(
                        step=step,
                        current_step_id=step_id,
                        default_next_map=default_next_map,
                        status="skipped",
                    )
                else:
                    request_payload = {}
                    input_template = step.get("input_template", {})
                    resolved_input = _resolve_workflow_templates(
                        input_template if isinstance(input_template, dict) else {},
                        context=template_context,
                        warnings=warnings,
                    )
                    if isinstance(resolved_input, dict):
                        request_payload = resolved_input
                    step_begin = time.monotonic()
                    ret = _invoke_agent_primary_call(
                        method=str(step.get("method", "POST") or "POST"),
                        endpoint=str(step.get("endpoint", "") or ""),
                        payload=request_payload,
                        request_context=request_context,
                    )
                    step_duration = round(max(time.monotonic() - step_begin, 0.0), 4)
                    status_code = int(ret.get("status_code", 0) or 0)
                    response_data = ret.get("data") if isinstance(ret.get("data"), dict) else {}
                    ok = status_code < 400 and bool(response_data.get("ok", False))
                    if ok:
                        step_status = "done"
                        success_count += 1
                        next_step_id = _workflow_pick_next_step_id(
                            step=step,
                            current_step_id=step_id,
                            default_next_map=default_next_map,
                            status="done",
                        )
                    else:
                        step_status = "error"
                        step_error = str(response_data.get("error", "") or f"step 调用失败（status={status_code}）")
                        failed_count += 1
                        _jobs[job_id]["log"].append(f"[Workflow:{step_id}] 失败: {step_error}")
                        if continue_on_error:
                            next_step_id = _workflow_pick_next_step_id(
                                step=step,
                                current_step_id=step_id,
                                default_next_map=default_next_map,
                                status="error",
                            )
                        else:
                            next_step_id = (
                                str(step.get("next_on_error", "") or "").strip()
                                or str(step.get("next_step_id", "") or "").strip()
                            )
            else:
                request_payload = {}
                input_template = step.get("input_template", {})
                resolved_input = _resolve_workflow_templates(
                    input_template if isinstance(input_template, dict) else {},
                    context=template_context,
                    warnings=warnings,
                )
                if isinstance(resolved_input, dict):
                    request_payload = resolved_input
                step_begin = time.monotonic()
                ret = _invoke_agent_primary_call(
                    method=str(step.get("method", "POST") or "POST"),
                    endpoint=str(step.get("endpoint", "") or ""),
                    payload=request_payload,
                    request_context=request_context,
                )
                step_duration = round(max(time.monotonic() - step_begin, 0.0), 4)
                status_code = int(ret.get("status_code", 0) or 0)
                response_data = ret.get("data") if isinstance(ret.get("data"), dict) else {}
                ok = status_code < 400 and bool(response_data.get("ok", False))
                if ok:
                    step_status = "done"
                    success_count += 1
                    next_step_id = _workflow_pick_next_step_id(
                        step=step,
                        current_step_id=step_id,
                        default_next_map=default_next_map,
                        status="done",
                    )
                else:
                    step_status = "error"
                    step_error = str(response_data.get("error", "") or f"step 调用失败（status={status_code}）")
                    failed_count += 1
                    _jobs[job_id]["log"].append(f"[Workflow:{step_id}] 失败: {step_error}")
                    if continue_on_error:
                        next_step_id = _workflow_pick_next_step_id(
                            step=step,
                            current_step_id=step_id,
                            default_next_map=default_next_map,
                            status="error",
                        )
                    else:
                        next_step_id = (
                            str(step.get("next_on_error", "") or "").strip()
                            or str(step.get("next_step_id", "") or "").strip()
                        )

        step_item = dict(base_item)
        step_item["status"] = step_status
        step_item["status_code"] = status_code
        step_item["duration_seconds"] = step_duration
        step_item["request_payload"] = deepcopy(request_payload)
        step_item["response"] = deepcopy(response_data)
        step_item["next_selected"] = str(next_step_id or "")
        if step_error:
            step_item["error"] = step_error
        history_steps.append(step_item)

        context_entry = {
            "status": step_status,
            "response": deepcopy(response_data),
            "status_code": status_code,
            "error": step_error,
            "request_payload": deepcopy(request_payload),
            "next_selected": str(next_step_id or ""),
        }
        template_context["steps"][step_id] = context_entry
        template_context["last"] = context_entry
        save_as = _normalize_agent_template_id(step.get("save_as", ""))
        if save_as:
            template_context.setdefault("vars", {})[save_as] = deepcopy(response_data)

        if isinstance(response_data, dict):
            for artifact in _extract_artifacts_from_payload(response_data):
                marker = (artifact.get("type", ""), artifact.get("value", ""))
                if marker in artifact_seen:
                    continue
                artifact_seen.add(marker)
                artifact_rows.append(artifact)

        if next_step_id:
            if next_step_id not in step_map:
                warnings.append(f"step={step_id} 跳转到不存在节点: {next_step_id}，执行终止")
                break
            current_step_id = next_step_id
            continue
        current_step_id = ""

    for sid in ordered_step_ids:
        if sid in reached_set:
            continue
        step = step_map.get(sid, {})
        item = {
            "index": int(step.get("index", len(history_steps) + 1) or (len(history_steps) + 1)),
            "step_id": sid,
            "node_type": str(step.get("node_type", "action") or "action"),
            "capability_id": str(step.get("capability_id", "") or ""),
            "action": str(step.get("action", "auto") or "auto"),
            "method": str(step.get("method", "POST") or "POST"),
            "endpoint": str(step.get("endpoint", "") or ""),
            "status": "unreached",
            "error": "未进入执行路径",
            "continue_on_error": _coerce_bool(step.get("continue_on_error", False), default=False),
            "enabled": _coerce_bool(step.get("enabled", True), default=True),
            "next_step_id": str(step.get("next_step_id", "") or ""),
            "next_on_success": str(step.get("next_on_success", "") or ""),
            "next_on_error": str(step.get("next_on_error", "") or ""),
            "next_on_skip": str(step.get("next_on_skip", "") or ""),
            "status_code": 0,
            "duration_seconds": 0.0,
            "request_payload": {},
            "response": {},
            "next_selected": "",
        }
        history_steps.append(item)
        skipped_count += 1

    finished_at_iso = datetime.now().isoformat(timespec="seconds")
    duration_seconds = round(max(time.monotonic() - started, 0.0), 4)
    if failed_count == 0:
        state = "done"
    elif success_count > 0:
        state = "partial"
    else:
        state = "failed"

    return {
        "run_id": str(uuid.uuid4())[:8],
        "workflow_id": str(plan.get("workflow_id", "") or ""),
        "workflow_name": str(plan.get("name", "") or ""),
        "status": state,
        "dry_run": bool(plan.get("dry_run", False)),
        "started_at": started_at_iso,
        "finished_at": finished_at_iso,
        "duration_seconds": duration_seconds,
        "summary": {
            "total_steps": total,
            "traversed_steps": len(execution_path),
            "unreached_steps": max(total - len(execution_path), 0),
            "success_steps": success_count,
            "failed_steps": failed_count,
            "skipped_steps": skipped_count,
            "overall_ok": failed_count == 0,
        },
        "execution_path": execution_path,
        "steps": history_steps,
        "warnings": list(dict.fromkeys(str(x) for x in warnings if str(x).strip())),
        "artifacts": artifact_rows,
    }


def _start_custom_workflow_run(
    *,
    workflow: Dict[str, Any],
    payload: Dict[str, Any],
    request_context: Dict[str, str],
    source: str,
) -> Dict[str, Any]:
    dry_run = _coerce_bool(payload.get("dry_run", False), default=False)
    plan = _build_custom_workflow_plan(workflow=workflow, payload=payload, dry_run=dry_run)
    rerun_context_raw = payload.get("rerun_context", {})
    rerun_context = deepcopy(rerun_context_raw) if isinstance(rerun_context_raw, dict) else {}
    if rerun_context:
        rerun_context.setdefault("mode", "custom")
        rerun_context.setdefault("source", source)

    job_id = str(uuid.uuid4())[:8]
    run_id = str(uuid.uuid4())[:8]
    source_text = str(source or "manual").strip() or "manual"

    def _do_run():
        _jobs[job_id]["progress"] = 5
        _jobs[job_id]["log"].append(
            f"[Workflow] run_id={run_id} workflow={plan.get('workflow_id')} source={source_text}"
        )
        result = _execute_custom_workflow_plan(
            plan=plan,
            request_context=request_context,
            job_id=job_id,
        )
        result["run_id"] = run_id
        record = {
            "run_id": run_id,
            "workflow_id": str(plan.get("workflow_id", "") or ""),
            "workflow_name": str(plan.get("name", "") or ""),
            "status": str(result.get("status", "done") or "done"),
            "dry_run": bool(plan.get("dry_run", False)),
            "started_at": str(result.get("started_at", "") or ""),
            "finished_at": str(result.get("finished_at", "") or ""),
            "duration_seconds": float(result.get("duration_seconds", 0.0) or 0.0),
            "summary": deepcopy(result.get("summary", {})) if isinstance(result.get("summary"), dict) else {},
            "execution_path": deepcopy(result.get("execution_path", [])) if isinstance(result.get("execution_path"), list) else [],
            "steps": deepcopy(result.get("steps", [])) if isinstance(result.get("steps"), list) else [],
            "warnings": deepcopy(result.get("warnings", [])) if isinstance(result.get("warnings"), list) else [],
            "artifacts": deepcopy(result.get("artifacts", [])) if isinstance(result.get("artifacts"), list) else [],
            "request_context": deepcopy(request_context),
            "source": source_text,
            "workflow": deepcopy(workflow),
            "plan": deepcopy(plan),
        }
        if rerun_context:
            record["rerun_context"] = deepcopy(rerun_context)
        _append_custom_workflow_run(record)
        _jobs[job_id]["progress"] = 95
        return {"ok": True, "run": record}

    _run_in_bg(
        job_id,
        _do_run,
        kind="custom_workflow",
        job_meta={
            "workflow_id": str(plan.get("workflow_id", "") or ""),
            "source": source_text,
            "dry_run": bool(plan.get("dry_run", False)),
            "request_context": deepcopy(request_context),
            "replay": {
                "method": "POST",
                "endpoint": "/api/workflows/run",
                "payload": deepcopy(payload),
                "request_context": deepcopy(request_context),
            },
        },
    )
    return {
        "ok": True,
        "job_id": job_id,
        "run_id": run_id,
        "workflow_id": str(plan.get("workflow_id", "") or ""),
        "workflow_name": str(plan.get("name", "") or ""),
        "dry_run": bool(plan.get("dry_run", False)),
        "total_steps": int(plan.get("total_steps", 0) or 0),
        "status_endpoint": f"/api/job/{job_id}",
        "rerun_context": deepcopy(rerun_context) if rerun_context else {},
    }


def _normalize_agent_replay_context(raw: Any) -> Dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    actor_type = str(src.get("actor_type", "agent") or "agent").strip().lower()
    if actor_type not in {"human", "agent"}:
        actor_type = "agent"
    actor_id = str(src.get("actor_id", "") or "").strip()[:128]
    run_mode = str(src.get("run_mode", "headless") or "headless").strip().lower()
    if run_mode not in {"interactive", "headless"}:
        run_mode = "headless" if actor_type == "agent" else "interactive"
    idempotency_key = str(src.get("idempotency_key", "") or "").strip()[:128]
    trace_id = str(src.get("trace_id", "") or "").strip()[:128]
    return {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "run_mode": run_mode,
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
    }


def _execute_agent_skill(
    *,
    skill_id: str,
    input_payload: Dict[str, Any],
    retry_policy: Dict[str, Any],
    timeout_seconds: float,
    request_context: Dict[str, str],
    logger=None,
) -> Dict[str, Any]:
    skill_spec = _AGENT_SKILL_REGISTRY.get(skill_id)
    if not isinstance(skill_spec, dict):
        raise ValueError(f"不支持的 skill_id: {skill_id}")
    method = str(skill_spec.get("method", "POST") or "POST").strip().upper()
    endpoint = str(skill_spec.get("endpoint", "") or "").strip()
    if not endpoint:
        raise RuntimeError(f"skill 配置缺少 endpoint: {skill_id}")
    capability_id = str(skill_spec.get("capability_id", "") or "")
    effective_input = _apply_agent_capability_input_defaults(
        capability_id,
        input_payload if isinstance(input_payload, dict) else {},
        default_input=skill_spec.get("default_input", {}),
    )

    max_attempts = int(retry_policy.get("max_retries", 0) or 0) + 1
    retry_http_codes = set(retry_policy.get("retry_on_http", []))
    backoff_s = float(int(retry_policy.get("backoff_ms", 0) or 0)) / 1000.0
    timeout_s = _normalize_skill_timeout_seconds(timeout_seconds, default=120.0)
    begin = time.monotonic()
    final_status = 0
    final_data: Dict[str, Any] = {}
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        if callable(logger):
            logger(f"尝试 {attempt}/{max_attempts} -> {method} {endpoint}")
        ret = _invoke_agent_primary_call(
            method=method,
            endpoint=endpoint,
            payload=effective_input,
            request_context=request_context,
        )
        final_status = int(ret.get("status_code", 0) or 0)
        final_data = ret.get("data") if isinstance(ret.get("data"), dict) else {}
        if final_status < 400 and bool(final_data.get("ok", False)):
            duration_seconds = round(max(time.monotonic() - begin, 0.0), 4)
            usage_tokens = _extract_usage_tokens_from_response(final_data)
            pricing_hint = _extract_pricing_hint_from_response(final_data)
            estimated_cost = _estimate_step_cost_metrics(
                prompt_tokens=int(usage_tokens.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage_tokens.get("completion_tokens", 0) or 0),
                duration_seconds=duration_seconds,
                provider=str(pricing_hint.get("provider", "") or ""),
                model=str(pricing_hint.get("model", "") or ""),
            )
            return {
                "skill_id": skill_id,
                "skill_name": str(skill_spec.get("name", "") or ""),
                "capability_id": str(skill_spec.get("capability_id", "") or ""),
                "primary_call": {
                    "method": method,
                    "endpoint": endpoint,
                    "payload": deepcopy(effective_input),
                },
                "attempts": attempts,
                "status_code": final_status,
                "response": final_data,
                "duration_seconds": duration_seconds,
                "usage_tokens": usage_tokens,
                "pricing_hint": pricing_hint,
                "estimated_cost": estimated_cost,
            }

        elapsed = time.monotonic() - begin
        if elapsed >= timeout_s:
            raise RuntimeError(f"skill 调用超时（{timeout_s:.1f}s）")
        can_retry = attempt < max_attempts and final_status in retry_http_codes
        if not can_retry:
            break
        if backoff_s > 0:
            if callable(logger):
                logger(f"重试等待 {backoff_s:.2f}s")
            time.sleep(backoff_s)

    err = str(final_data.get("error", "") or f"skill 调用失败（status={final_status}）")
    raise RuntimeError(err)


def _should_run_conditional_step(
    condition: Dict[str, Any],
    previous_results: Dict[str, Dict[str, Any]],
) -> (bool, str):
    cond = condition if isinstance(condition, dict) else {}
    if_overall_ok = _coerce_bool(cond.get("if_overall_ok", False), default=False)
    if if_overall_ok:
        for item in previous_results.values():
            if str(item.get("status", "")).lower() == "error":
                return False, "if_overall_ok 未满足（前序存在 error）"

    depends_on = cond.get("depends_on", [])
    if not isinstance(depends_on, list) or not depends_on:
        return True, ""
    status_in_raw = cond.get("status_in", ["done"])
    status_in = {str(x).lower().strip() for x in status_in_raw} if isinstance(status_in_raw, list) else {"done"}
    if not status_in:
        status_in = {"done"}
    require_all = _coerce_bool(cond.get("require_all", True), default=True)

    matched = []
    missing = []
    for dep in depends_on:
        dep_id = _normalize_agent_template_id(str(dep or "").strip())
        if not dep_id:
            continue
        dep_item = previous_results.get(dep_id)
        if not isinstance(dep_item, dict):
            missing.append(dep_id)
            matched.append(False)
            continue
        dep_status = str(dep_item.get("status", "")).strip().lower()
        matched.append(dep_status in status_in)
    if missing:
        return False, f"依赖未完成: {','.join(missing)}"

    passed = all(matched) if require_all else any(matched)
    if passed:
        return True, ""
    return False, "依赖状态不满足 condition"

def _parse_capability_idempotency_cache_key(cache_key: str) -> Dict[str, str]:
    text = str(cache_key or "")
    parts = text.split("|", 3)
    if len(parts) == 4:
        return {
            "project_path": parts[0],
            "endpoint": parts[1],
            "actor_id": parts[2],
            "idempotency_key": parts[3],
        }
    return {
        "project_path": "",
        "endpoint": "",
        "actor_id": "",
        "idempotency_key": "",
    }


def _normalize_capability_idempotency_ttl(value, default: int = _CAPABILITY_IDEMPOTENCY_TTL_SECONDS) -> int:
    try:
        ttl = int(value)
    except Exception:
        ttl = int(default)
    if ttl < 0:
        ttl = 0
    return ttl


def _normalize_capability_idempotency_filter_text(value: Any) -> str:
    return str(value or "").strip()


def _capability_idempotency_match_text(candidate: Any, pattern: str, *, exact: bool = False) -> bool:
    query = _normalize_capability_idempotency_filter_text(pattern).lower()
    if not query:
        return True
    text = _normalize_capability_idempotency_filter_text(candidate).lower()
    if exact:
        return text == query
    return query in text


def _collect_capability_idempotency_records(
    *,
    source: str = "merged",
    ttl_seconds: int = _CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
    include_expired: bool = False,
    limit: int = 200,
    offset: int = 0,
    actor_id_filter: str = "",
    endpoint_filter: str = "",
    idempotency_key_filter: str = "",
    project_path_filter: str = "",
    match_mode: str = "contains",
) -> Dict[str, Any]:
    with _capability_idempotency_lock:
        memory_raw = deepcopy(_capability_idempotency_cache)
    persisted_raw = _load_capability_idempotency_store(include_expired=True, ttl_seconds=ttl_seconds)
    now_epoch = time.time()

    def _rows_from(raw_map: Dict[str, Dict[str, Any]], src: str) -> List[Dict[str, Any]]:
        rows = []
        for cache_key, entry in raw_map.items():
            normalized = _normalize_capability_idempotency_entry(entry)
            if normalized is None:
                continue
            expired = _capability_idempotency_entry_expired(
                normalized,
                ttl_seconds=ttl_seconds,
                now_epoch=now_epoch,
            )
            if expired and not include_expired:
                continue
            parsed = _parse_capability_idempotency_cache_key(cache_key)
            rows.append(
                {
                    "cache_key": str(cache_key),
                    "source": src,
                    "created_at": str(normalized.get("created_at", "") or ""),
                    "status": int(normalized.get("status", 200) or 200),
                    "expired": bool(expired),
                    "project_path": parsed.get("project_path", ""),
                    "endpoint": parsed.get("endpoint", ""),
                    "actor_id": parsed.get("actor_id", ""),
                    "idempotency_key": parsed.get("idempotency_key", ""),
                }
            )
        return rows

    memory_rows = _rows_from(memory_raw, "memory")
    persisted_rows = _rows_from(persisted_raw, "persisted")

    if source == "memory":
        rows = memory_rows
    elif source == "persisted":
        rows = persisted_rows
    else:
        merged = {row["cache_key"]: row for row in persisted_rows}
        for row in memory_rows:
            merged[row["cache_key"]] = row
        rows = list(merged.values())

    exact_match = str(match_mode or "contains").strip().lower() == "exact"
    actor_filter_text = _normalize_capability_idempotency_filter_text(actor_id_filter)
    endpoint_filter_text = _normalize_capability_idempotency_filter_text(endpoint_filter)
    idem_key_filter_text = _normalize_capability_idempotency_filter_text(idempotency_key_filter)
    project_filter_text = _normalize_capability_idempotency_filter_text(project_path_filter)
    if actor_filter_text or endpoint_filter_text or idem_key_filter_text or project_filter_text:
        rows = [
            row for row in rows
            if _capability_idempotency_match_text(row.get("actor_id", ""), actor_filter_text, exact=exact_match)
            and _capability_idempotency_match_text(row.get("endpoint", ""), endpoint_filter_text, exact=exact_match)
            and _capability_idempotency_match_text(
                row.get("idempotency_key", ""),
                idem_key_filter_text,
                exact=exact_match,
            )
            and _capability_idempotency_match_text(
                row.get("project_path", ""),
                project_filter_text,
                exact=exact_match,
            )
        ]

    rows.sort(key=lambda x: str(x.get("created_at", "") or ""), reverse=True)
    limit_final = max(1, min(int(limit or 200), 1000))
    offset_final = max(int(offset or 0), 0)
    final_rows = rows[offset_final: offset_final + limit_final]
    active_count = sum(1 for r in rows if not r.get("expired"))
    expired_count = sum(1 for r in rows if r.get("expired"))
    has_more = (offset_final + len(final_rows)) < len(rows)
    return {
        "records": final_rows,
        "stats": {
            "source": source,
            "ttl_seconds": int(ttl_seconds),
            "include_expired": bool(include_expired),
            "total": len(rows),
            "active": active_count,
            "expired": expired_count,
            "memory_total_raw": len(memory_raw),
            "persisted_total_raw": len(persisted_raw),
            "returned": len(final_rows),
            "limit": limit_final,
            "offset": offset_final,
            "has_more": bool(has_more),
            "filters": {
                "actor_id": actor_filter_text,
                "endpoint": endpoint_filter_text,
                "idempotency_key": idem_key_filter_text,
                "project_path": project_filter_text,
                "match_mode": "exact" if exact_match else "contains",
            },
        },
    }


def _read_content_publish_sessions() -> Dict[str, Dict[str, Any]]:
    raw = _read_project_json("content_publish_sessions.json", fallback={})
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        sid = str(key or "").strip()
        if sid and isinstance(value, dict):
            out[sid] = value
    return out


def _save_content_publish_sessions(sessions: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    p = _project_data_path("content_publish_sessions.json")
    if p is None:
        return sessions
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = sessions if isinstance(sessions, dict) else {}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _read_content_publish_history() -> List[Dict[str, Any]]:
    raw = _read_project_json("content_publish_history.json", fallback=[])
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _save_content_publish_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    p = _project_data_path("content_publish_history.json")
    if p is None:
        return history
    p.parent.mkdir(parents=True, exist_ok=True)
    items = [x for x in history if isinstance(x, dict)]
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def _resolve_content_publish_content(
    payload: Dict[str, Any],
    *,
    input_mode: str,
) -> Dict[str, Any]:
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    out = dict(content)
    if input_mode == "project":
        if not out.get("title") or not out.get("description"):
            publish_prep = _read_project_json("publish_prep_last.json", fallback={})
            result = publish_prep.get("platform_results", []) if isinstance(publish_prep, dict) else []
            first = result[0] if isinstance(result, list) and result else {}
            generated = first.get("content", {}) if isinstance(first, dict) else {}
            if not out.get("title"):
                out["title"] = str(generated.get("title") or "").strip()
            if not out.get("description"):
                out["description"] = str(generated.get("body") or "").strip()
            if not out.get("keywords") and isinstance(generated.get("keywords"), list):
                out["keywords"] = generated.get("keywords")
        if not out.get("article_markdown") or not out.get("article_html"):
            article = _read_project_json("article_expand_last.json", fallback={})
            if isinstance(article, dict):
                if not out.get("article_markdown"):
                    out["article_markdown"] = str(article.get("markdown") or "").strip()
                if not out.get("article_html"):
                    md = str(article.get("markdown") or "").strip()
                    title = str(article.get("title_candidates", ["Untitled"])[0] if isinstance(article.get("title_candidates"), list) and article.get("title_candidates") else "Untitled")
                    if md:
                        out["article_html"] = f"<article><h1>{title}</h1><pre>{md}</pre></article>"
    return out


def _resolve_content_publish_connectors(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    connectors = payload.get("connectors", {})
    if isinstance(connectors, dict) and connectors:
        result = _normalize_publish_connectors(connectors)
    else:
        saved = _load_publish_settings()
        result = saved.get("connectors", {}) if isinstance(saved.get("connectors"), dict) else {}
    # Auto-inject YouTube OAuth token from secure_store
    result = _inject_youtube_oauth_token(result)
    return result


def _inject_youtube_oauth_token(connectors: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """If YouTube connector has no access_token, inject from secure_store OAuth."""
    yt = connectors.get("youtube", {})
    if isinstance(yt, dict) and yt.get("access_token"):
        return connectors  # Already has a token, don't override
    try:
        raw = _secret_store.get("youtube_oauth")
        if not raw:
            return connectors
        import json as _json
        token_data = _json.loads(raw)
        access_token = token_data.get("access_token", "")
        if not access_token:
            return connectors
        # Auto-refresh if expired
        expires_at = float(token_data.get("expires_at", 0))
        if expires_at and (time.time() > expires_at - 300):
            refreshed = _refresh_youtube_token(token_data)
            if refreshed:
                token_data = refreshed
                access_token = token_data.get("access_token", "")
        yt_connector = dict(yt) if isinstance(yt, dict) else {}
        yt_connector.update({
            "kind": "youtube_api",
            "access_token": access_token,
        })
        connectors = dict(connectors)
        connectors["youtube"] = yt_connector
    except Exception:
        pass
    return connectors


def _refresh_youtube_token(token_data: dict) -> Optional[dict]:
    """Refresh YouTube OAuth token using refresh_token."""
    refresh_token = token_data.get("refresh_token", "")
    if not refresh_token:
        return None
    import os
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    try:
        import urllib.request
        import urllib.parse
        import json as _json
        post_data = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            new_token = _json.loads(resp.read().decode("utf-8"))
        new_access = new_token.get("access_token", "")
        if not new_access:
            return None
        token_data["access_token"] = new_access
        token_data["expires_at"] = time.time() + int(new_token.get("expires_in", 3600))
        # Persist refreshed token
        _secret_store.set("youtube_oauth", _json.dumps(token_data, ensure_ascii=False))
        return token_data
    except Exception:
        return None


# ── 工厂函数（供 app.py 调用）─────────────────────────────────────────

def create_app(project_dir: Optional[str] = None):
    """创建并配置 Flask app，可选预加载项目。"""
    # Ensure logging & perf_log are initialised (no-op if launcher already did it)
    try:
        from modules.app_api.services.logging_service import init_logging
        init_logging()
    except Exception:
        pass
    try:
        from modules.app_api.services.perf_log import init_perf_log as _init_pl
        _pl_path = Path(_library.db_path).parent / "perf_log.db" if _library.db_path else None
        if _pl_path:
            _init_pl(_pl_path)
    except Exception:
        pass
    try:
        from modules.app_api.services.audit_log import init_audit_log as _init_al
        _al_path = Path(_library.db_path).parent / "audit_log.db" if _library.db_path else None
        if _al_path:
            _init_al(_al_path)
    except Exception:
        pass
    try:
        _restore_jobs_from_store()
    except Exception:
        pass
    if project_dir:
        p = Path(project_dir)
        if (p / "workflow.json").exists():
            _load_state(p)
    else:
        try:
            ui = _load_ui_settings()
            if bool(ui.get("auto_open_last_project", True)):
                last = str(ui.get("last_project_dir", "") or "").strip()
                if last:
                    p = Path(last).expanduser().resolve()
                    if (p / "workflow.json").exists():
                        _load_state(p)
        except Exception:
            pass
    return app


def set_window(window):
    """由 app.py 在窗口创建后注入 pywebview window 引用。"""
    global _window
    _window = window
