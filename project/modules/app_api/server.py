#!/usr/bin/env python3
"""Flask API 服务器 —— 为 pywebview GUI 提供后端接口。

Core module: job store, queue management, blueprint registration, and create_app().
Business logic is extracted into services/ and middleware/ sub-packages.
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
from modules.app_api.routes.review_routes import create_review_blueprint
from modules.app_api.routes.roughcut_routes import create_roughcut_blueprint
from modules.app_api.routes.enhance_routes import create_enhance_blueprint
from modules.app_api.routes.stock_routes import create_stock_blueprint
from modules.app_api.routes.style_routes import create_style_blueprint
from modules.app_api.routes.vlm_routes import create_vlm_blueprint
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
        choose_files_multiple=lambda file_types=(): _choose_files_multiple(file_types),
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
# ── Review & Roughcut API (v0.14.0) ──
_review_store = None

def _get_review_store():
    global _review_store
    if _review_store is None:
        from modules.review_engine.review_store import ReviewStore
        db_path = str((_project_dir or Path("/tmp")) / "data" / "review.db")
        _review_store = ReviewStore(db_path)
    return _review_store

def _get_vlm_adapter():
    """Lazy-load VLM adapter based on settings."""
    from modules.adapters.vlm_adapter import get_vlm_adapter
    import os
    # Check settings for provider preference; default to env var or None
    provider = os.environ.get("VIDEOEDITOR_VLM_PROVIDER", "")
    if not provider:
        # Try loading from AI settings
        try:
            from modules.app_api.services.settings_service import load_ai_settings
            ai = load_ai_settings()
            provider = ai.get("vlm_provider", "")
        except Exception:
            pass
    return get_vlm_adapter(provider) if provider else None

app.register_blueprint(
    create_review_blueprint(
        review_store_getter=_get_review_store,
        artifact_store_getter=lambda: None,
    )
)
app.register_blueprint(
    create_roughcut_blueprint(
        review_store_getter=_get_review_store,
    )
)

app.register_blueprint(
    create_enhance_blueprint(
        review_store_getter=_get_review_store,
        jobs_getter=lambda: _jobs,
    )
)
app.register_blueprint(
    create_stock_blueprint(
        jobs_getter=lambda: _jobs,
    )
)
app.register_blueprint(
    create_style_blueprint(
        project_dir_getter=lambda: _project_dir,
    )
)

app.register_blueprint(
    create_vlm_blueprint(
        review_store_getter=_get_review_store,
        vlm_adapter_getter=_get_vlm_adapter,
    )
)

app.register_blueprint(
    create_ui_blueprint(
        app_ui_dir_getter=lambda: APP_UI_DIR,
    )
)

# ── Middleware: error handlers (extracted to middleware/error_handler.py) ──
from modules.app_api.middleware.error_handler import (  # noqa: E402
    handle_request_entity_too_large,
    handle_not_found,
    handle_method_not_allowed,
    handle_unexpected_error,
)
from modules.app_api.middleware import error_handler as _err_handler_mod  # noqa: E402
_err_handler_mod.init(app=app)
app.errorhandler(RequestEntityTooLarge)(handle_request_entity_too_large)
app.errorhandler(404)(handle_not_found)
app.errorhandler(405)(handle_method_not_allowed)
app.errorhandler(Exception)(handle_unexpected_error)

# ── Middleware: security (extracted to middleware/security.py) ──
from modules.app_api.middleware.security import (  # noqa: E402
    _request_is_local,
    _is_mutating_method,
    _is_allowed_local_origin,
    _guard_local_api_token,
)
from modules.app_api.middleware import security as _security_mod  # noqa: E402
_security_mod.init(
    require_local_api_token=_REQUIRE_LOCAL_API_TOKEN,
    require_csrf_protection=_REQUIRE_CSRF_PROTECTION,
    local_api_token=_LOCAL_API_TOKEN,
    local_csrf_token=_LOCAL_CSRF_TOKEN,
)
app.before_request(_guard_local_api_token)

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

# ── Settings service (extracted to services/settings_service.py L1-6) ──
from modules.app_api.services.settings_service import (  # noqa: E402
    _prepare_project_dirs, _settings_path, _read_settings, _write_settings,
    _normalize_production_view, _normalize_font_scale, _load_ui_settings,
    _save_ui_settings, _remember_last_project, _add_to_recent_projects,
    _get_recent_projects, _normalize_publish_connectors,
    _merge_publish_connectors_with_existing, _mask_publish_connectors,
    _load_publish_settings, _save_publish_settings, _mask_secret,
    _normalize_ai_provider, _recommended_ai_base_url, _ai_catalog_payload,
    _ai_secret_ref_name, _read_ai_secret_field, _persist_ai_secret_field,
    _load_ai_settings, _save_ai_settings, _apply_ai_env, _public_ai_settings,
    _default_project_config, _project_data_path, _read_project_json,
)
# Early init so module-level calls (e.g. _apply_ai_env) work before create_app()
from modules.app_api.services import settings_service as _settings_svc_early  # noqa: E402
_settings_svc_early.init(library=_library, secret_store=_secret_store, project_dir=_project_dir)

# ── Workflow management (extracted to services/workflow_runner.py) ──
from modules.app_api.services.workflow_runner import (  # noqa: E402
    _read_agent_task_history, _save_agent_task_history, _find_agent_task_history_record,
    _custom_workflow_store_path, _custom_workflow_runs_path, _normalize_custom_workflow_id,
    _parse_custom_workflow_tags, _normalize_custom_workflow_step, _normalize_custom_workflow_payload,
    _read_custom_workflow_store, _save_custom_workflow_store, _read_custom_workflow_runs,
    _save_custom_workflow_runs, _append_custom_workflow_run, _find_custom_workflow_run,
    _build_custom_workflow_catalog, _extract_agent_replay_spec, _extract_template_ids_from_value,
    _normalize_agent_skill_condition, _capability_supports_input_mode,
    _normalize_agent_input_mode_value, _apply_agent_capability_input_defaults,
    _normalize_agent_skill_steps, _resolve_agent_primary_call, _invoke_agent_primary_call,
    _workflow_get_path_value, _resolve_workflow_templates, _workflow_truthy,
    _workflow_pick_next_step_id, _workflow_pick_target_with_source, _workflow_graph_has_cycle,
    _build_custom_workflow_graph, _build_failed_only_workflow_subset,
    _resolve_custom_workflow_from_payload, _build_custom_workflow_plan,
    _execute_custom_workflow_plan, _start_custom_workflow_run,
    _normalize_agent_replay_context, _execute_agent_skill, _should_run_conditional_step,
)

# ── Job analytics service (extracted to services/job_analytics_service.py) ──
from modules.app_api.services.job_analytics_service import (  # noqa: E402
    _parse_iso_datetime, _duration_from_iso_range, _trimmed_avg,
    _refresh_eta_history_cache, _historical_avg_duration_for_kind, _estimate_job_eta,
    _build_agent_task_history_record, _record_agent_task_history_from_job,
    _parse_agent_history_filter_tokens, _agent_history_anchor_time,
    _filter_agent_task_history, _build_agent_task_export_snapshot,
    _build_chain_view_from_history_item, _build_agent_observability_summary, _read_script_json,
)
from modules.app_api.services import job_analytics_service as _analytics_svc_early  # noqa: E402
_analytics_svc_early.init(
    project_dir=_project_dir, eta_history_lock=_eta_history_lock,
    eta_history_cache=_eta_history_cache, ensure_job_store=lambda: _ensure_job_store(),
    jobs=_jobs, agent_history_lock=_agent_history_lock,
)
# ── Capability helpers (extracted to services/capability_helpers.py) ──
from modules.app_api.services.capability_helpers import (  # noqa: E402
    _slugify, _extract_material_semantics, _parse_platforms, _parse_capability_input_mode,
    _request_json_any_method, _capability_base_dir, _resolve_path_with_base,
    _coerce_script_input, _coerce_materials_input, _extract_subtitles_from_script,
    _script_to_text_blocks, _parse_str_list, _default_master_video_path,
    _default_bgm_library_dirs, _default_bgm_output_dir, _is_remote_media_url,
    _append_social_export_history, _get_social_export_history, _normalize_export_template_id,
    _normalize_export_template_payload, _get_social_export_templates,
    _save_social_export_templates, _coerce_social_export_overrides,
)
from modules.app_api.services import capability_helpers as _cap_helpers_early  # noqa: E402
_cap_helpers_early.init(project_dir=_project_dir, ws=_ws)

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

# ── Agent template service (extracted to services/agent_template_service.py L1-6) ──
from modules.app_api.services.agent_template_service import (  # noqa: E402
    _agent_template_value_matches_type, _validate_agent_template_slot_value,
    _normalize_agent_template_variables, _validate_template_slot_values,
    _hydrate_agent_template_defaults, _normalize_agent_template_payload,
    _read_agent_template_store, _agent_template_lookup_key, _agent_template_chain_token,
    _agent_template_base_candidate_keys, _resolve_agent_template_effective,
    _collect_agent_templates, _validate_agent_template_base_reference,
    _save_agent_template_store, _list_agent_templates,
)
from modules.app_api.services import agent_template_service as _template_svc_early  # noqa: E402
_template_svc_early.init(project_dir=_project_dir, agent_system_templates=_AGENT_SYSTEM_TEMPLATES,
                         agent_template_scope_order=_AGENT_TEMPLATE_SCOPE_ORDER)

# -- publish orchestrator: Group A (runners) imported from services/publish_orchestrator.py --
from modules.app_api.services.publish_orchestrator import (
    _build_social_export_runner,
    _build_audio_voice_runner,
)

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

def _choose_files_multiple(file_types: tuple = ()) -> Dict:
    """多选文件对话框。返回 {"paths": [...], "cancelled": bool, "error": str}"""
    # 方法 1：pywebview
    if _window is not None:
        try:
            import webview
            dialog_type = getattr(webview, "OPEN_DIALOG", None) or getattr(webview.FileDialog, "OPEN", None)
            result = _window.create_file_dialog(
                dialog_type=dialog_type,
                allow_multiple=True,
                file_types=file_types if file_types else (),
            )
            if result:
                return {"paths": list(result), "cancelled": False, "error": ""}
            return {"paths": [], "cancelled": True, "error": ""}
        except Exception:
            pass

    # 方法 2：osascript 多选
    if sys.platform == "darwin":
        # AppleScript 多选文件，支持类型过滤
        ext_filter = ""
        if file_types:
            # file_types 格式如 ("Video Files (*.mp4;*.mov)",) — 提取扩展名
            import re
            all_exts = re.findall(r'\*\.(\w+)', ';'.join(file_types))
            if all_exts:
                quoted = ', '.join(f'"{e}"' for e in all_exts)
                ext_filter = f' of type {{{quoted}}}'

        script = f'set f to (choose file with prompt "选择视频文件（可多选）" with multiple selections allowed{ext_filter})\n'
        script += 'set output to ""\n'
        script += 'repeat with p in f\n'
        script += '  set output to output & POSIX path of p & linefeed\n'
        script += 'end repeat\n'
        script += 'return output'

        try:
            proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0:
                err = (proc.stderr or "").strip()
                if "-128" in err or "User canceled" in err:
                    return {"paths": [], "cancelled": True, "error": ""}
                return {"paths": [], "cancelled": False, "error": err}
            lines = [l.strip() for l in (proc.stdout or "").strip().split("\n") if l.strip()]
            return {"paths": lines, "cancelled": len(lines) == 0, "error": ""}
        except Exception as exc:
            return {"paths": [], "cancelled": False, "error": str(exc)}

    return {"paths": [], "cancelled": False, "error": "当前系统不支持多选文件对话框"}


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

# ── Agent governance service (extracted to services/agent_governance_service.py L1-6) ──
from modules.app_api.services.agent_governance_service import (  # noqa: E402
    _agent_capability_route_map, _list_agent_skills, _normalize_skill_retry_policy,
    _normalize_skill_timeout_seconds, _normalize_skill_budget_limit,
    _normalize_governance_limit_item, _normalize_governance_string_list,
    _normalize_agent_governance_policy, _read_agent_governance_policy,
    _read_agent_governance_usage, _save_agent_governance_usage, _normalize_cost_rate_item,
    _normalize_agent_cost_model_config, _read_agent_cost_model_config,
    _extract_pricing_hint_from_response, _resolve_cost_rates,
    _extract_usage_tokens_from_response, _estimate_step_cost_metrics,
    _normalize_usage_bucket, _compute_usage_suggested_limits, _update_usage_bucket,
    _record_governance_usage_for_skill_flow, _extract_dynamic_limits_from_usage,
    _pick_actor_rule, _tighten_governance_limit,
    _resolve_agent_governance_for_skill_flow, _apply_governance_to_skill_flow,
)
from modules.app_api.services import agent_governance_service as _governance_svc_early  # noqa: E402
_governance_svc_early.init(
    project_dir=_project_dir, agent_skill_registry=_AGENT_SKILL_REGISTRY,
    agent_governance_default=_AGENT_GOVERNANCE_DEFAULT,
    agent_governance_usage_default=_AGENT_GOVERNANCE_USAGE_DEFAULT,
    agent_usage_recent_runs_max=_AGENT_USAGE_RECENT_RUNS_MAX,
    agent_cost_model_default=_AGENT_COST_MODEL_DEFAULT,
)

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

# -- publish orchestrator: Group B (content publish) imported from services/publish_orchestrator.py --
from modules.app_api.services.publish_orchestrator import (  # noqa: E402
    _read_content_publish_sessions,
    _save_content_publish_sessions,
    _read_content_publish_history,
    _save_content_publish_history,
    _resolve_content_publish_content,
    _resolve_content_publish_connectors,
    _inject_youtube_oauth_token,
    _refresh_youtube_token,
)

# ── 工厂函数（供 app.py 调用）─────────────────────────────────────────

def create_app(project_dir: Optional[str] = None):
    """创建并配置 Flask app，可选预加载项目。"""
    # Inject shared state into extracted workflow_runner module
    from modules.app_api.services import workflow_runner as _workflow_runner_mod
    _workflow_runner_mod.init(
        project_dir=_project_dir,
        custom_workflow_lock=_custom_workflow_lock,
        custom_workflow_store_mem=_custom_workflow_store_mem,
        custom_workflow_runs_mem=_custom_workflow_runs_mem,
    )
    # Inject shared state into extracted publish_orchestrator module
    from modules.app_api.services import publish_orchestrator as _publish_orch_mod
    _publish_orch_mod.init(
        project_dir=_project_dir,
        secret_store=_secret_store,
        jobs=_jobs,
    )
    # Inject shared state into extracted settings_service module
    from modules.app_api.services import settings_service as _settings_mod
    _settings_mod.init(
        library=_library,
        secret_store=_secret_store,
        project_dir=_project_dir,
    )
    # Inject shared state into extracted agent_template_service module
    from modules.app_api.services import agent_template_service as _template_mod
    _template_mod.init(
        project_dir=_project_dir,
        agent_system_templates=_AGENT_SYSTEM_TEMPLATES,
        agent_template_scope_order=_AGENT_TEMPLATE_SCOPE_ORDER,
    )
    # Inject shared state into extracted agent_governance_service module
    from modules.app_api.services import agent_governance_service as _governance_mod
    _governance_mod.init(
        project_dir=_project_dir, agent_skill_registry=_AGENT_SKILL_REGISTRY,
        agent_governance_default=_AGENT_GOVERNANCE_DEFAULT,
        agent_governance_usage_default=_AGENT_GOVERNANCE_USAGE_DEFAULT,
        agent_usage_recent_runs_max=_AGENT_USAGE_RECENT_RUNS_MAX,
        agent_cost_model_default=_AGENT_COST_MODEL_DEFAULT,
    )
    # Inject shared state into extracted job_analytics_service module
    from modules.app_api.services import job_analytics_service as _analytics_mod
    _analytics_mod.init(
        project_dir=_project_dir, eta_history_lock=_eta_history_lock,
        eta_history_cache=_eta_history_cache, ensure_job_store=lambda: _ensure_job_store(),
        jobs=_jobs, agent_history_lock=_agent_history_lock,
    )
    # Inject shared state into extracted capability_helpers module
    from modules.app_api.services import capability_helpers as _cap_helpers_mod
    _cap_helpers_mod.init(project_dir=_project_dir, ws=_ws)
    # Inject shared state into extracted middleware/security module
    from modules.app_api.middleware import security as _security_mod2
    _security_mod2.init(
        require_local_api_token=_REQUIRE_LOCAL_API_TOKEN,
        require_csrf_protection=_REQUIRE_CSRF_PROTECTION,
        local_api_token=_LOCAL_API_TOKEN, local_csrf_token=_LOCAL_CSRF_TOKEN,
    )
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
