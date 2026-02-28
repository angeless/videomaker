#!/usr/bin/env python3
"""
Flask API 服务器 —— 为 pywebview GUI 提供后端接口

端点:
  GET  /api/status               → 当前 workflow 状态
  GET  /api/system/load          → 系统负载与运行任务
  GET  /api/settings/ai          → 读取 AI 配置
  POST /api/settings/ai          → 保存 AI 配置
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
import traceback
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_UI_DIR = REPO_ROOT / "apps" / "desktop" / "ui"

from flask import Flask, jsonify, request, send_file, abort
from modules.app_api.publish_prep_api import create_publish_prep_blueprint
from modules.workflow_engine.workflow import WorkflowState, WorkflowRunner
from modules.library.global_media_library import GlobalMediaLibrary
from modules.step2_topic_planning.ai_client import AIClient

app = Flask(__name__, static_folder=None)
app.config["JSON_AS_ASCII"] = False

# ── 全局状态 ────────────────────────────────────────────────────────
_project_dir: Optional[Path] = None
_ws: Optional[WorkflowState] = None
_jobs: Dict[str, dict] = {}      # job_id → {status, log, progress}
_window = None                    # pywebview window（由 app.py 注入）
_library = GlobalMediaLibrary()
app.register_blueprint(
    create_publish_prep_blueprint(
        project_dir_getter=lambda: _project_dir,
        ai_settings_getter=lambda: _load_ai_settings(),
    )
)
_heavy_job_submit_lock = threading.Lock()
_agent_history_lock = threading.Lock()
_custom_workflow_lock = threading.Lock()
CANCEL_TOKEN = "__CANCELLED__"
_capability_idempotency_cache: Dict[str, Dict[str, Any]] = {}
_capability_idempotency_lock = threading.Lock()
_CAPABILITY_IDEMPOTENCY_LIMIT = 400
_CAPABILITY_IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600
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
    }


def _run_in_bg(job_id: str, fn, *args, kind: str = "generic", job_meta: Optional[Dict[str, Any]] = None, **kwargs):
    """在后台线程运行 fn，捕获 stdout 并更新 _jobs[job_id]。"""
    _jobs[job_id] = {
        "status": "running",
        "log": [],
        "progress": 0,
        "kind": kind,
        "meta": deepcopy(job_meta) if isinstance(job_meta, dict) else {},
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "result": None,
        "cancel_requested": False,
    }

    class Tee:
        def __init__(self, real):
            self._real = real
        def write(self, s):
            self._real.write(s)
            if s.strip():
                _jobs[job_id]["log"].append(s.rstrip())
        def flush(self):
            self._real.flush()

    def _worker():
        old_stdout = sys.stdout
        sys.stdout = Tee(old_stdout)
        try:
            ret = fn(*args, **kwargs)
            _jobs[job_id]["result"] = ret
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["progress"] = 100
        except Exception as e:
            err_text = str(e)
            cancelled = isinstance(e, JobCancelledError) or (CANCEL_TOKEN in err_text)
            if cancelled:
                _jobs[job_id]["status"] = "cancelled"
                _jobs[job_id]["error"] = "任务已取消"
                if isinstance(e, JobCancelledError):
                    _jobs[job_id]["result"] = e.result
                _jobs[job_id]["log"].append("[系统] 任务已取消")
            else:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = err_text
                _jobs[job_id]["log"].append(traceback.format_exc())
        finally:
            sys.stdout = old_stdout
            _jobs[job_id]["finished_at"] = datetime.now().isoformat(timespec="seconds")
            if str(kind or "") in {"agent_task", "agent_skill"}:
                try:
                    _record_agent_task_history_from_job(job_id)
                except Exception:
                    pass
            # 刷新 state
            if _ws:
                try:
                    _ws.load()
                except Exception:
                    pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id


def _running_heavy_jobs() -> list:
    heavy_kinds = {
        "workflow_step",
        "library_ingest_local",
        "library_ingest_local_images",
        "library_ingest_gdrive",
        "library_ingest_gdrive_images",
        "social_export",
        "audio_voice",
        "custom_workflow",
    }
    return [
        {"job_id": jid, "kind": job.get("kind"), "started_at": job.get("started_at")}
        for jid, job in _jobs.items()
        if job.get("status") == "running" and job.get("kind") in heavy_kinds
    ]


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


def _mask_secret(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"


def _load_ai_settings() -> Dict:
    data = _read_settings().get("ai", {})
    if not isinstance(data, dict):
        data = {}
    return {
        "provider": str(data.get("provider", "") or "").strip(),
        "ai_model": str(data.get("ai_model", "") or "").strip(),
        "embedding_model": str(data.get("embedding_model", "") or "").strip(),
        "ai_base_url": str(data.get("ai_base_url", "") or "").strip(),
        "openai_api_key": str(data.get("openai_api_key", "") or "").strip(),
        "anthropic_api_key": str(data.get("anthropic_api_key", "") or "").strip(),
    }


def _save_ai_settings(payload: Dict) -> Dict:
    settings = _read_settings()
    ai = settings.get("ai", {})
    if not isinstance(ai, dict):
        ai = {}

    provider = str(payload.get("provider", "") or "").strip()
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
    if openai_api_key:
        ai["openai_api_key"] = openai_api_key
    if anthropic_api_key:
        ai["anthropic_api_key"] = anthropic_api_key

    if bool(payload.get("clear_openai_api_key", False)):
        ai.pop("openai_api_key", None)
    if bool(payload.get("clear_anthropic_api_key", False)):
        ai.pop("anthropic_api_key", None)

    settings["ai"] = ai
    _write_settings(settings)
    return _load_ai_settings()


def _apply_ai_env(ai: Dict):
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
    if ai_base_url:
        os.environ["OPENAI_BASE_URL"] = ai_base_url
    else:
        os.environ.pop("OPENAI_BASE_URL", None)
    if ai_model:
        os.environ["OPENAI_MODEL"] = ai_model
    else:
        os.environ.pop("OPENAI_MODEL", None)
    if embedding_model:
        os.environ["OPENAI_EMBEDDING_MODEL"] = embedding_model
    else:
        os.environ.pop("OPENAI_EMBEDDING_MODEL", None)


def _public_ai_settings(ai: Dict) -> Dict:
    return {
        "provider": ai.get("provider", ""),
        "ai_model": ai.get("ai_model", ""),
        "embedding_model": ai.get("embedding_model", ""),
        "ai_base_url": ai.get("ai_base_url", ""),
        "openai_api_key_set": bool(ai.get("openai_api_key")),
        "anthropic_api_key_set": bool(ai.get("anthropic_api_key")),
        "openai_api_key_masked": _mask_secret(ai.get("openai_api_key", "")),
        "anthropic_api_key_masked": _mask_secret(ai.get("anthropic_api_key", "")),
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
        print(f"[社媒导出] 总任务 {len(plan.get('jobs', []))}，输出目录: {out_dir}")
        for i, job in enumerate(plan.get("jobs", []), start=1):
            print(f"[社媒导出] {i}/{len(plan['jobs'])} {job.get('platform_id')} -> {job.get('output_video')}")
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
        print(f"[社媒导出] 完成，成功 {result.get('success', 0)}，失败 {result.get('failed', 0)}")
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


def _capability_idempotency_store_path() -> Optional[Path]:
    return _project_data_path("capability_idempotency_cache.json")


def _normalize_capability_idempotency_entry(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    body = raw.get("body")
    if not isinstance(body, dict):
        return None
    try:
        status = int(raw.get("status", 200) or 200)
    except Exception:
        status = 200
    created_at = str(raw.get("created_at", "") or "")
    return {
        "status": status,
        "body": deepcopy(body),
        "created_at": created_at,
    }


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        try:
            if text.endswith("Z"):
                return datetime.fromisoformat(text[:-1] + "+00:00")
        except Exception:
            return None
    return None


def _capability_idempotency_entry_expired(
    entry: Dict[str, Any],
    *,
    ttl_seconds: Optional[int] = None,
    now_epoch: Optional[float] = None,
) -> bool:
    ttl = _CAPABILITY_IDEMPOTENCY_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)
    if ttl <= 0:
        return False
    created = _parse_iso_datetime(str((entry or {}).get("created_at", "") or ""))
    if created is None:
        return False
    ts_now = time.time() if now_epoch is None else float(now_epoch)
    return (ts_now - created.timestamp()) > float(ttl)


def _filter_capability_idempotency_entries(
    entries: Dict[str, Dict[str, Any]],
    *,
    ttl_seconds: Optional[int] = None,
    include_expired: bool = False,
) -> Dict[str, Dict[str, Any]]:
    ttl = _CAPABILITY_IDEMPOTENCY_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)
    now_epoch = time.time()
    out: Dict[str, Dict[str, Any]] = {}
    for key, entry in (entries or {}).items():
        normalized = _normalize_capability_idempotency_entry(entry)
        if normalized is None:
            continue
        expired = _capability_idempotency_entry_expired(normalized, ttl_seconds=ttl, now_epoch=now_epoch)
        if expired and not include_expired:
            continue
        out[str(key)] = normalized
    return out


def _load_capability_idempotency_store(
    *,
    include_expired: bool = False,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    p = _capability_idempotency_store_path()
    if p is None or not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, dict) and isinstance(raw.get("records"), list):
        for item in raw.get("records", []):
            if not isinstance(item, dict):
                continue
            cache_key = str(item.get("cache_key", "") or "").strip()
            if not cache_key:
                continue
            normalized = _normalize_capability_idempotency_entry(item)
            if normalized is None:
                continue
            out[cache_key] = normalized
        return _filter_capability_idempotency_entries(
            out,
            ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS if ttl_seconds is None else ttl_seconds,
            include_expired=include_expired,
        )

    if isinstance(raw, dict):
        for cache_key, item in raw.items():
            key = str(cache_key or "").strip()
            if not key:
                continue
            normalized = _normalize_capability_idempotency_entry(item)
            if normalized is None:
                continue
            out[key] = normalized
    return _filter_capability_idempotency_entries(
        out,
        ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS if ttl_seconds is None else ttl_seconds,
        include_expired=include_expired,
    )


def _save_capability_idempotency_store(records: Dict[str, Dict[str, Any]]):
    p = _capability_idempotency_store_path()
    if p is None:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    items = []
    for cache_key, entry in records.items():
        normalized = _normalize_capability_idempotency_entry(entry)
        if normalized is None:
            continue
        if not str(normalized.get("created_at", "") or "").strip():
            normalized["created_at"] = datetime.now().isoformat(timespec="seconds")
        items.append({
            "cache_key": str(cache_key),
            **normalized,
        })
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "records": items,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _trim_capability_idempotency_entries(
    entries: Dict[str, Dict[str, Any]],
    *,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    filtered = _filter_capability_idempotency_entries(
        entries,
        ttl_seconds=ttl_seconds if ttl_seconds is not None else _CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
        include_expired=False,
    )
    if len(filtered) <= _CAPABILITY_IDEMPOTENCY_LIMIT:
        return filtered
    ordered = sorted(
        filtered.items(),
        key=lambda kv: str((kv[1] or {}).get("created_at", "") or ""),
    )
    kept = ordered[-_CAPABILITY_IDEMPOTENCY_LIMIT:]
    return {k: v for k, v in kept}


def _trim_capability_idempotency_entries_with_limit(
    entries: Dict[str, Dict[str, Any]],
    *,
    max_entries: int,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    max_n = max(int(max_entries or 0), 1)
    filtered = _filter_capability_idempotency_entries(
        entries,
        ttl_seconds=ttl_seconds if ttl_seconds is not None else _CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
        include_expired=False,
    )
    if len(filtered) <= max_n:
        return filtered
    ordered = sorted(
        filtered.items(),
        key=lambda kv: str((kv[1] or {}).get("created_at", "") or ""),
    )
    kept = ordered[-max_n:]
    return {k: v for k, v in kept}


def _limit_capability_idempotency_entries(
    entries: Dict[str, Dict[str, Any]],
    *,
    max_entries: int,
) -> Dict[str, Dict[str, Any]]:
    max_n = max(int(max_entries or 0), 1)
    normalized_map: Dict[str, Dict[str, Any]] = {}
    for key, entry in (entries or {}).items():
        normalized = _normalize_capability_idempotency_entry(entry)
        if normalized is None:
            continue
        normalized_map[str(key)] = normalized
    if len(normalized_map) <= max_n:
        return normalized_map
    ordered = sorted(
        normalized_map.items(),
        key=lambda kv: str((kv[1] or {}).get("created_at", "") or ""),
    )
    kept = ordered[-max_n:]
    return {k: v for k, v in kept}


def _get_persisted_capability_idempotency_entry(cache_key: str) -> Optional[Dict[str, Any]]:
    records = _load_capability_idempotency_store(
        include_expired=False,
        ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
    )
    item = records.get(cache_key)
    normalized = _normalize_capability_idempotency_entry(item)
    return deepcopy(normalized) if normalized is not None else None


def _compact_persisted_capability_idempotency_store(
    *,
    ttl_seconds: Optional[int] = None,
    max_entries: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    records_all = _load_capability_idempotency_store(
        include_expired=True,
        ttl_seconds=ttl_seconds if ttl_seconds is not None else _CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
    )
    if max_entries is None:
        compacted = _trim_capability_idempotency_entries(records_all)
    else:
        compacted = _trim_capability_idempotency_entries_with_limit(
            records_all,
            max_entries=max_entries,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else _CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
        )
    if compacted != records_all:
        _save_capability_idempotency_store(compacted)
    return compacted


def _upsert_persisted_capability_idempotency_entry(cache_key: str, entry: Dict[str, Any]):
    records = _compact_persisted_capability_idempotency_store(
        ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
        max_entries=_CAPABILITY_IDEMPOTENCY_LIMIT,
    )
    normalized = _normalize_capability_idempotency_entry(entry)
    if normalized is None:
        return
    records[str(cache_key)] = normalized
    trimmed = _trim_capability_idempotency_entries(records)
    _save_capability_idempotency_store(trimmed)


def _make_capability_idempotency_cache_key(path: str, ctx: Dict[str, str]) -> str:
    project_anchor = ""
    if _project_dir is not None:
        try:
            project_anchor = str(_project_dir.resolve())
        except Exception:
            project_anchor = str(_project_dir)
    return (
        f"{project_anchor}|"
        f"{path}|"
        f"{ctx.get('actor_id', '')}|"
        f"{ctx.get('idempotency_key', '')}"
    )


def _trim_capability_idempotency_cache():
    if len(_capability_idempotency_cache) <= _CAPABILITY_IDEMPOTENCY_LIMIT:
        return
    trimmed = _trim_capability_idempotency_entries(_capability_idempotency_cache)
    _capability_idempotency_cache.clear()
    _capability_idempotency_cache.update(trimmed)


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
    with _capability_idempotency_lock:
        hit = _capability_idempotency_cache.get(cache_key)
        replay_source = "memory"
        if isinstance(hit, dict) and _capability_idempotency_entry_expired(
            hit,
            ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
        ):
            _capability_idempotency_cache.pop(cache_key, None)
            hit = None
        if not isinstance(hit, dict):
            hit = _get_persisted_capability_idempotency_entry(cache_key)
            if isinstance(hit, dict):
                _capability_idempotency_cache[cache_key] = deepcopy(hit)
                _trim_capability_idempotency_cache()
                replay_source = "persisted"
        if isinstance(hit, dict) and _capability_idempotency_entry_expired(
            hit,
            ttl_seconds=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
        ):
            _capability_idempotency_cache.pop(cache_key, None)
            hit = None
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
            entry = {
                "status": int(response.status_code),
                "body": deepcopy(body),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            with _capability_idempotency_lock:
                _capability_idempotency_cache[cache_key] = deepcopy(entry)
                _trim_capability_idempotency_cache()
                _upsert_persisted_capability_idempotency_entry(cache_key, entry)

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


# ── API 端点 ─────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    return jsonify(_state_dict())


@app.route("/api/system/load")
def api_system_load():
    return jsonify({
        "ok": True,
        "system": _system_load_snapshot(),
        "overloaded": _is_overloaded(),
        "running_jobs": _running_heavy_jobs(),
    })


@app.route("/api/settings/ai", methods=["GET"])
def api_get_ai_settings():
    ai = _load_ai_settings()
    return jsonify({"ok": True, **_public_ai_settings(ai)})


@app.route("/api/settings/ai", methods=["POST"])
def api_save_ai_settings():
    data = request.json or {}
    ai = _save_ai_settings(data)
    _apply_ai_env(ai)
    return jsonify({"ok": True, **_public_ai_settings(ai)})


@app.route("/api/init", methods=["POST"])
def api_init():
    data = request.json or {}
    videos_dir = (data.get("videos_dir", "") or "").strip()
    project_dir = data.get("project_dir", "").strip()
    selected_uids = data.get("selected_video_uids") or []
    if isinstance(selected_uids, str):
        selected_uids = [x.strip() for x in selected_uids.split(",") if x.strip()]

    if selected_uids:
        if len(selected_uids) > 50:
            return jsonify({"error": "一次最多选择 50 个视频素材"}), 400

        if not project_dir:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_dir = str(Path.cwd() / f"proj_selected_{ts}")

        project_path = Path(project_dir).expanduser().resolve()
        _prepare_project_dirs(project_path)

        materials = _library.build_workflow_materials(selected_uids)
        if not materials:
            return jsonify({"error": "未找到可用素材，请先在素材库分析并选择素材"}), 400

        resolved_uids = [uid for uid in selected_uids if uid in materials]
        if not resolved_uids:
            return jsonify({"error": "所选素材均不可用（仅支持视频素材，且需本地路径可访问）"}), 400
        if len(resolved_uids) != len(selected_uids):
            return jsonify({"error": "所选素材中包含图片或不可用文件；制作流程当前仅支持视频"}), 400

        selected_paths = [materials[uid]["path"] for uid in resolved_uids]
        config = _default_project_config({
            "material_source": "global_library",
            "selected_video_uids": resolved_uids,
            "selected_video_paths": selected_paths,
        })
        ws = WorkflowState.create(project_path, "", config)

        materials_path = project_path / "data" / "materials.json"
        materials_path.write_text(
            json.dumps(materials, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        ws.data["steps"]["1"].update({
            "status": "done",
            "review_status": "approved",
            "output": "data/materials.json",
            "video_count": len(resolved_uids),
            "completed_at": datetime.now().isoformat(),
        })
        ws.data["steps"]["2"]["status"] = "pending"
        ws.data["current_step"] = 2
        ws.save()

        _load_state(project_path)
        return jsonify({
            "ok": True,
            "project_dir": str(project_path),
            "selected_count": len(resolved_uids),
            **_state_dict(),
        })

    if not videos_dir:
        return jsonify({"error": "videos_dir 不能为空（或传 selected_video_uids）"}), 400

    videos_path = Path(videos_dir).expanduser().resolve()
    if not videos_path.exists():
        return jsonify({"error": f"素材目录不存在: {videos_dir}"}), 400

    if not project_dir:
        project_dir = str(videos_path.parent / f"proj_{videos_path.name}")

    project_path = Path(project_dir).expanduser().resolve()
    _prepare_project_dirs(project_path)
    ws = WorkflowState.create(project_path, str(videos_path), _default_project_config())
    ws.save()
    _load_state(project_path)
    return jsonify({"ok": True, "project_dir": str(project_path), **_state_dict()})


@app.route("/api/library/stats")
def api_library_stats():
    return jsonify(_library.stats())


@app.route("/api/library/search")
def api_library_search():
    query = (request.args.get("q", "") or "").strip()
    retrieval_mode = (request.args.get("mode", "hybrid") or "hybrid").strip().lower()
    media_type = (request.args.get("media_type", "all") or "all").strip().lower()
    if media_type not in {"all", "video", "image"}:
        media_type = "all"
    if retrieval_mode not in {"hybrid", "keyword", "vector"}:
        retrieval_mode = "hybrid"
    try:
        default_limit = "120" if not query else "150"
        limit = int(request.args.get("limit", default_limit))
    except Exception:
        limit = 120 if not query else 150
    try:
        offset = int(request.args.get("offset", "0"))
    except Exception:
        offset = 0
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    effective_mode = retrieval_mode if query else "browse"
    results = _library.search_assets(
        query=query,
        limit=limit,
        offset=offset,
        retrieval_mode=retrieval_mode,
        media_type=media_type,
    )
    total_matches = _library.count_matching_assets(
        query=query,
        retrieval_mode=retrieval_mode,
        media_type=media_type,
    )
    stats = _library.stats()
    has_more = (offset + len(results)) < total_matches
    return jsonify({
        "query": query,
        "media_type": media_type,
        "retrieval_mode": effective_mode,
        "limit": limit,
        "offset": offset,
        "count": len(results),
        "total_matches": total_matches,
        "total_assets": stats.get("total_assets", 0),
        "hybrid_search_enabled": bool(stats.get("hybrid_search_enabled", False)),
        "embedding_enabled": bool(stats.get("embedding_enabled", False)),
        "embedding_status": stats.get("embedding_status", ""),
        "embedding_status_message": stats.get("embedding_status_message", ""),
        "embedding_ready_assets": int(stats.get("embedding_ready_assets", 0)),
        "truncated": has_more,
        "has_more": has_more,
        "results": results,
    })


@app.route("/api/library/assets", methods=["POST"])
def api_library_assets():
    data = request.json or {}
    uids = data.get("uids") or []
    if not isinstance(uids, list):
        return jsonify({"error": "uids 必须是数组"}), 400
    return jsonify({"assets": _library.get_assets(uids)})


@app.route("/api/library/preview/local", methods=["POST"])
def api_library_preview_local():
    data = request.json or {}
    source_path = (data.get("path", "") or "").strip()
    try:
        max_results = int(data.get("max_results", 30))
    except Exception:
        max_results = 30
    max_results = max(1, min(max_results, 200))
    if not source_path:
        return jsonify({"error": "path 不能为空"}), 400
    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再预览",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409

    root = Path(source_path).expanduser().resolve()
    if not root.exists():
        return jsonify({"error": f"路径不存在: {root}"}), 400

    videos = _library.discover_videos(root)
    sample = []
    for p in videos[:max_results]:
        try:
            rel = str(p.relative_to(root))
        except Exception:
            rel = str(p)
        sample.append(rel)

    return jsonify({
        "ok": True,
        "preview": {
            "path": str(root),
            "video_candidates": len(videos),
            "max_results": max_results,
            "sample_videos": sample,
        },
    })


@app.route("/api/library/ingest/local", methods=["POST"])
def api_library_ingest_local():
    data = request.json or {}
    source_path = (data.get("path", "") or "").strip()
    try:
        max_videos = int(data.get("max_videos", 600))
    except Exception:
        max_videos = 600
    max_videos = max(1, min(max_videos, 5000))

    if not source_path:
        return jsonify({"error": "path 不能为空"}), 400
    root = Path(source_path).expanduser().resolve()
    if not root.exists():
        return jsonify({"error": f"路径不存在: {root}"}), 400

    def _do_local():
        print(f"[素材分析] 开始本地分析: {source_path} (max_videos={max_videos})")

        def _should_cancel():
            return bool(_jobs.get(job_id, {}).get("cancel_requested"))

        def _progress(done, total, current_path):
            if _should_cancel():
                raise JobCancelledError(CANCEL_TOKEN)
            if total <= 0:
                _jobs[job_id]["progress"] = 0
                return
            _jobs[job_id]["progress"] = int(done * 100 / max(total, 1))
            name = Path(current_path).name if current_path else ""
            _jobs[job_id]["log"].append(f"已处理 {done}/{total} {name}")
            _jobs[job_id]["log"] = _jobs[job_id]["log"][-220:]

        result = _library.ingest_local_path(
            source_path,
            max_videos=max_videos,
            progress_callback=_progress,
            should_cancel=_should_cancel,
        )
        if result.get("cancelled"):
            raise JobCancelledError(
                CANCEL_TOKEN,
                {"ok": False, "cancelled": True, "result": result, "stats": _library.stats()},
            )
        print(
            f"[素材分析] 本地分析完成: 扫描 {result.get('scanned', 0)}，入库 {result.get('indexed', 0)}，"
            f"重复 {result.get('dedup_hits', 0)}，失败 {result.get('failed', 0)}"
        )
        return {"ok": True, "result": result, "stats": _library.stats()}

    with _heavy_job_submit_lock:
        running = _running_heavy_jobs()
        if running:
            return jsonify({
                "error": "已有重任务运行中，请等待完成后再开始素材分析",
                "running_jobs": running,
                "system": _system_load_snapshot(),
            }), 409
        if _is_overloaded():
            return jsonify({
                "error": "系统负载过高，暂不启动新分析任务，请稍后重试",
                "system": _system_load_snapshot(),
            }), 429
        job_id = str(uuid.uuid4())[:8]
        _run_in_bg(job_id, _do_local, kind="library_ingest_local")

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "mode": "async",
        "max_videos": max_videos,
        "system": _system_load_snapshot(),
    })


@app.route("/api/library/preview/local/images", methods=["POST"])
def api_library_preview_local_images():
    data = request.json or {}
    source_path = (data.get("path", "") or "").strip()
    try:
        max_results = int(data.get("max_results", 30))
    except Exception:
        max_results = 30
    max_results = max(1, min(max_results, 300))
    if not source_path:
        return jsonify({"error": "path 不能为空"}), 400
    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再预览",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409

    root = Path(source_path).expanduser().resolve()
    if not root.exists():
        return jsonify({"error": f"路径不存在: {root}"}), 400

    images = _library.discover_images(root)
    sample = []
    for p in images[:max_results]:
        try:
            rel = str(p.relative_to(root))
        except Exception:
            rel = str(p)
        sample.append(rel)

    return jsonify({
        "ok": True,
        "preview": {
            "path": str(root),
            "image_candidates": len(images),
            "max_results": max_results,
            "sample_images": sample,
        },
    })


@app.route("/api/library/ingest/local/images", methods=["POST"])
def api_library_ingest_local_images():
    data = request.json or {}
    source_path = (data.get("path", "") or "").strip()
    try:
        max_images = int(data.get("max_images", 1200))
    except Exception:
        max_images = 1200
    max_images = max(1, min(max_images, 8000))

    if not source_path:
        return jsonify({"error": "path 不能为空"}), 400
    root = Path(source_path).expanduser().resolve()
    if not root.exists():
        return jsonify({"error": f"路径不存在: {root}"}), 400

    def _do_local_images():
        print(f"[图片分析] 开始本地分析: {source_path} (max_images={max_images})")

        def _should_cancel():
            return bool(_jobs.get(job_id, {}).get("cancel_requested"))

        def _progress(done, total, current_path):
            if _should_cancel():
                raise JobCancelledError(CANCEL_TOKEN)
            if total <= 0:
                _jobs[job_id]["progress"] = 0
                return
            _jobs[job_id]["progress"] = int(done * 100 / max(total, 1))
            name = Path(current_path).name if current_path else ""
            _jobs[job_id]["log"].append(f"已处理 {done}/{total} {name}")
            _jobs[job_id]["log"] = _jobs[job_id]["log"][-220:]

        result = _library.ingest_local_images(
            source_path,
            max_images=max_images,
            progress_callback=_progress,
            should_cancel=_should_cancel,
        )
        if result.get("cancelled"):
            raise JobCancelledError(
                CANCEL_TOKEN,
                {"ok": False, "cancelled": True, "result": result, "stats": _library.stats()},
            )
        print(
            f"[图片分析] 本地分析完成: 扫描 {result.get('scanned', 0)}，入库 {result.get('indexed', 0)}，"
            f"重复 {result.get('dedup_hits', 0)}，失败 {result.get('failed', 0)}"
        )
        return {"ok": True, "result": result, "stats": _library.stats()}

    with _heavy_job_submit_lock:
        running = _running_heavy_jobs()
        if running:
            return jsonify({
                "error": "已有重任务运行中，请等待完成后再开始图片分析",
                "running_jobs": running,
                "system": _system_load_snapshot(),
            }), 409
        if _is_overloaded():
            return jsonify({
                "error": "系统负载过高，暂不启动新分析任务，请稍后重试",
                "system": _system_load_snapshot(),
            }), 429
        job_id = str(uuid.uuid4())[:8]
        _run_in_bg(job_id, _do_local_images, kind="library_ingest_local_images")

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "mode": "async",
        "max_images": max_images,
        "system": _system_load_snapshot(),
    })


@app.route("/api/library/ingest/gdrive", methods=["POST"])
def api_library_ingest_gdrive():
    data = request.json or {}
    url = (data.get("url", "") or "").strip()
    refresh = bool(data.get("refresh", False))
    priority_subdirs = data.get("priority_subdirs", "")
    try:
        max_videos = int(data.get("max_videos", 80))
    except Exception:
        max_videos = 80
    try:
        max_scan_folders = int(data.get("max_scan_folders", 120))
    except Exception:
        max_scan_folders = 120
    if max_videos <= 0:
        max_videos = 80
    max_videos = min(max_videos, 500)
    if max_scan_folders <= 0:
        max_scan_folders = 120
    max_scan_folders = min(max_scan_folders, 2000)
    if not url:
        return jsonify({"error": "url 不能为空"}), 400

    def _do_gdrive():
        print(
            f"[素材分析] 开始 Google Drive 分析: max_videos={max_videos}, "
            f"max_scan_folders={max_scan_folders}, refresh={refresh}"
        )

        def _should_cancel():
            return bool(_jobs.get(job_id, {}).get("cancel_requested"))

        def _progress(done, total, current_path):
            if _should_cancel():
                raise JobCancelledError(CANCEL_TOKEN)
            if total <= 0:
                _jobs[job_id]["progress"] = 0
                return
            _jobs[job_id]["progress"] = int(done * 100 / max(total, 1))
            name = Path(current_path).name if current_path else ""
            _jobs[job_id]["log"].append(f"已处理 {done}/{total} {name}")
            _jobs[job_id]["log"] = _jobs[job_id]["log"][-220:]

        result = _library.ingest_google_drive(
            url,
            refresh=refresh,
            max_videos=max_videos,
            priority_subdirs=priority_subdirs,
            max_scan_folders=max_scan_folders,
            progress_callback=_progress,
            should_cancel=_should_cancel,
        )
        if result.get("cancelled"):
            raise JobCancelledError(
                CANCEL_TOKEN,
                {"ok": False, "cancelled": True, "result": result, "stats": _library.stats()},
            )
        print(
            f"[素材分析] Google Drive 分析完成: 列出 {result.get('listed_files', 0)}，"
            f"候选 {result.get('video_candidates', 0)}，入库 {result.get('indexed', 0)}"
        )
        return {"ok": True, "result": result, "stats": _library.stats()}

    with _heavy_job_submit_lock:
        running = _running_heavy_jobs()
        if running:
            return jsonify({
                "error": "已有重任务运行中，请等待完成后再开始云端分析",
                "running_jobs": running,
                "system": _system_load_snapshot(),
            }), 409
        if _is_overloaded():
            return jsonify({
                "error": "系统负载过高，暂不启动新分析任务，请稍后重试",
                "system": _system_load_snapshot(),
            }), 429
        job_id = str(uuid.uuid4())[:8]
        _run_in_bg(job_id, _do_gdrive, kind="library_ingest_gdrive")

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "mode": "async",
        "max_videos": max_videos,
        "max_scan_folders": max_scan_folders,
        "system": _system_load_snapshot(),
    })


@app.route("/api/library/preview/gdrive", methods=["POST"])
def api_library_preview_gdrive():
    data = request.json or {}
    url = (data.get("url", "") or "").strip()
    priority_subdirs = data.get("priority_subdirs", "")
    try:
        max_scan_folders = int(data.get("max_scan_folders", 120))
    except Exception:
        max_scan_folders = 120
    try:
        max_results = int(data.get("max_results", 30))
    except Exception:
        max_results = 30
    if max_scan_folders <= 0:
        max_scan_folders = 120
    max_scan_folders = min(max_scan_folders, 2000)
    if max_results <= 0:
        max_results = 30
    max_results = min(max_results, 200)
    if not url:
        return jsonify({"error": "url 不能为空"}), 400
    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再预览",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409
    try:
        preview = _library.preview_google_drive(
            url=url,
            priority_subdirs=priority_subdirs,
            max_scan_folders=max_scan_folders,
            max_results=max_results,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "preview": preview})


@app.route("/api/library/ingest/gdrive/images", methods=["POST"])
def api_library_ingest_gdrive_images():
    data = request.json or {}
    url = (data.get("url", "") or "").strip()
    refresh = bool(data.get("refresh", False))
    priority_subdirs = data.get("priority_subdirs", "")
    try:
        max_images = int(data.get("max_images", 200))
    except Exception:
        max_images = 200
    try:
        max_scan_folders = int(data.get("max_scan_folders", 120))
    except Exception:
        max_scan_folders = 120
    if max_images <= 0:
        max_images = 200
    max_images = min(max_images, 2000)
    if max_scan_folders <= 0:
        max_scan_folders = 120
    max_scan_folders = min(max_scan_folders, 2000)
    if not url:
        return jsonify({"error": "url 不能为空"}), 400

    def _do_gdrive_images():
        print(
            f"[图片分析] 开始 Google Drive 分析: max_images={max_images}, "
            f"max_scan_folders={max_scan_folders}, refresh={refresh}"
        )

        def _should_cancel():
            return bool(_jobs.get(job_id, {}).get("cancel_requested"))

        def _progress(done, total, current_path):
            if _should_cancel():
                raise JobCancelledError(CANCEL_TOKEN)
            if total <= 0:
                _jobs[job_id]["progress"] = 0
                return
            _jobs[job_id]["progress"] = int(done * 100 / max(total, 1))
            name = Path(current_path).name if current_path else ""
            _jobs[job_id]["log"].append(f"已处理 {done}/{total} {name}")
            _jobs[job_id]["log"] = _jobs[job_id]["log"][-220:]

        result = _library.ingest_google_drive_images(
            url,
            refresh=refresh,
            max_images=max_images,
            priority_subdirs=priority_subdirs,
            max_scan_folders=max_scan_folders,
            progress_callback=_progress,
            should_cancel=_should_cancel,
        )
        if result.get("cancelled"):
            raise JobCancelledError(
                CANCEL_TOKEN,
                {"ok": False, "cancelled": True, "result": result, "stats": _library.stats()},
            )
        print(
            f"[图片分析] Google Drive 分析完成: 列出 {result.get('listed_files', 0)}，"
            f"候选 {result.get('image_candidates', 0)}，入库 {result.get('indexed', 0)}"
        )
        return {"ok": True, "result": result, "stats": _library.stats()}

    with _heavy_job_submit_lock:
        running = _running_heavy_jobs()
        if running:
            return jsonify({
                "error": "已有重任务运行中，请等待完成后再开始云端图片分析",
                "running_jobs": running,
                "system": _system_load_snapshot(),
            }), 409
        if _is_overloaded():
            return jsonify({
                "error": "系统负载过高，暂不启动新分析任务，请稍后重试",
                "system": _system_load_snapshot(),
            }), 429
        job_id = str(uuid.uuid4())[:8]
        _run_in_bg(job_id, _do_gdrive_images, kind="library_ingest_gdrive_images")

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "mode": "async",
        "max_images": max_images,
        "max_scan_folders": max_scan_folders,
        "system": _system_load_snapshot(),
    })


@app.route("/api/library/preview/gdrive/images", methods=["POST"])
def api_library_preview_gdrive_images():
    data = request.json or {}
    url = (data.get("url", "") or "").strip()
    priority_subdirs = data.get("priority_subdirs", "")
    try:
        max_scan_folders = int(data.get("max_scan_folders", 120))
    except Exception:
        max_scan_folders = 120
    try:
        max_results = int(data.get("max_results", 30))
    except Exception:
        max_results = 30
    if max_scan_folders <= 0:
        max_scan_folders = 120
    max_scan_folders = min(max_scan_folders, 2000)
    if max_results <= 0:
        max_results = 30
    max_results = min(max_results, 200)
    if not url:
        return jsonify({"error": "url 不能为空"}), 400
    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再预览",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409
    try:
        preview = _library.preview_google_drive_images(
            url=url,
            priority_subdirs=priority_subdirs,
            max_scan_folders=max_scan_folders,
            max_results=max_results,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "preview": preview})


@app.route("/api/open_project", methods=["POST"])
def api_open_project():
    data = request.json or {}
    project_dir = data.get("project_dir", "").strip()
    if not project_dir:
        return jsonify({"error": "project_dir 不能为空"}), 400
    p = Path(project_dir)
    if not (p / "workflow.json").exists():
        return jsonify({"error": "目录内没有 workflow.json，不是有效项目"}), 400
    _load_state(p)
    return jsonify({"ok": True, **_state_dict()})


@app.route("/api/approve/<int:step>", methods=["POST"])
def api_approve(step: int):
    """
    审核通过某一步骤。
    Body JSON 包含该步骤 review 文件需要的字段，
    服务端直接写入 review 文件 YAML 块并触发运行。
    """
    if _ws is None or _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400

    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再继续",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409
    if _is_overloaded():
        return jsonify({
            "error": "系统负载过高，已阻止新任务启动，请稍后重试",
            "system": _system_load_snapshot(),
        }), 429

    data = request.json or {}
    review_map = {
        1: "reviews/01_materials.md",
        2: "reviews/02_topics.md",
        3: "reviews/03_script.md",
        4: "reviews/04_matching.md",
        5: None,   # 自动通过
        6: "reviews/05_render_options.md",
    }
    review_rel = review_map.get(step)

    if review_rel:
        review_path = _project_dir / review_rel
        if not review_path.exists():
            return jsonify({
                "error": f"审核文件不存在: {review_rel}（请先运行 Step {step} 生成审核文件）"
            }), 404

        content = review_path.read_text(encoding="utf-8")

        # 构建新 YAML 块
        yaml_lines = ["approved: true"]
        for k, v in data.items():
            if k == "approved":
                continue
            if isinstance(v, str):
                safe = v.replace('"', '\\"')
                yaml_lines.append(f'{k}: "{safe}"')
            elif isinstance(v, bool):
                yaml_lines.append(f"{k}: {'true' if v else 'false'}")
            else:
                yaml_lines.append(f"{k}: {v}")
        new_yaml = "\n".join(yaml_lines)

        import re
        # 替换 ```yaml ... ``` 块
        new_content = re.sub(
            r"```yaml\n.*?```",
            f"```yaml\n{new_yaml}\n```",
            content,
            count=1,
            flags=re.DOTALL,
        )
        review_path.write_text(new_content, encoding="utf-8")

    # Step 6 参数同步回 workflow config，便于重复执行粗剪/渲染时复用最近配置
    if step == 6 and isinstance(data, dict):
        render_cfg = _ws.data.setdefault("config", {}).setdefault("render", {})
        for k, v in data.items():
            if k == "approved":
                continue
            render_cfg[k] = v
        _ws.save()

    # 后台运行下一步
    job_id = str(uuid.uuid4())[:8]

    def _do_run():
        def _should_cancel():
            return bool(_jobs.get(job_id, {}).get("cancel_requested"))

        def _progress(payload: Dict):
            if not isinstance(payload, dict):
                return
            progress = payload.get("progress")
            message = str(payload.get("message", "") or "").strip()
            if isinstance(progress, (int, float)):
                _jobs[job_id]["progress"] = max(0, min(99, int(progress)))
            if message:
                _jobs[job_id]["log"].append(message)
                _jobs[job_id]["log"] = _jobs[job_id]["log"][-120:]

        runner = WorkflowRunner(_ws, should_cancel=_should_cancel, progress_callback=_progress)
        # 解析 review 并标记通过
        if review_rel:
            approved, parsed = runner.parse_review(step)
            if approved:
                _ws.approve_review(step, parsed)
        # 运行下一步
        target = _ws.data.get("current_step", step + 1)
        method_name = f"step{target}_{'analyze' if target==1 else 'topics' if target==2 else 'script' if target==3 else 'match' if target==4 else 'frames' if target==5 else 'rough' if target==6 else 'render'}"
        method = getattr(runner, method_name, None)
        if method:
            method()
        _ws.load()

    _run_in_bg(job_id, _do_run, kind="workflow_step")
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/run_step", methods=["POST"])
def api_run_step():
    """后台运行当前步骤（无需先写 review 文件）。"""
    if _ws is None:
        return jsonify({"error": "项目未加载"}), 400

    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再执行下一步",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409
    if _is_overloaded():
        return jsonify({
            "error": "系统负载过高，已阻止新任务启动，请稍后重试",
            "system": _system_load_snapshot(),
        }), 429

    job_id = str(uuid.uuid4())[:8]
    target = _ws.data.get("current_step", 1)

    step_method_map = {
        1: "step1_analyze",
        2: "step2_topics",
        3: "step3_script",
        4: "step4_match",
        5: "step5_frames",
        6: "step6_rough",
        7: "step7_render",
    }
    method_name = step_method_map.get(target)
    if not method_name:
        return jsonify({"error": f"未知步骤: {target}"}), 400

    def _do():
        def _should_cancel():
            return bool(_jobs.get(job_id, {}).get("cancel_requested"))

        def _progress(payload: Dict):
            if not isinstance(payload, dict):
                return
            progress = payload.get("progress")
            message = str(payload.get("message", "") or "").strip()
            if isinstance(progress, (int, float)):
                _jobs[job_id]["progress"] = max(0, min(99, int(progress)))
            if message:
                _jobs[job_id]["log"].append(message)
                _jobs[job_id]["log"] = _jobs[job_id]["log"][-120:]

        runner = WorkflowRunner(_ws, should_cancel=_should_cancel, progress_callback=_progress)
        getattr(runner, method_name)()
        _ws.load()

    _run_in_bg(job_id, _do, kind="workflow_step")
    return jsonify({"ok": True, "job_id": job_id, "step": target})


@app.route("/api/job/<job_id>")
def api_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "job 不存在"}), 404
    return jsonify({
        "status": job["status"],
        "kind": job.get("kind", "generic"),
        "log": job["log"][-50:],   # 最近 50 行
        "progress": job.get("progress", 0),
        "cancel_requested": bool(job.get("cancel_requested", False)),
        "error": job.get("error"),
        "result": job.get("result"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "system": _system_load_snapshot(),
        "state": _state_dict(),
    })


@app.route("/api/job/<job_id>/cancel", methods=["POST"])
def api_job_cancel(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "job 不存在"}), 404
    if job.get("status") != "running":
        return jsonify({
            "error": "任务不在运行中，无法取消",
            "status": job.get("status"),
        }), 409
    job["cancel_requested"] = True
    job["cancel_requested_at"] = datetime.now().isoformat(timespec="seconds")
    job["log"].append("[系统] 收到取消请求，正在安全停止…")
    return jsonify({
        "ok": True,
        "status": job.get("status"),
        "cancel_requested": True,
    })


@app.route("/api/frames")
def api_frames():
    if _project_dir is None:
        return jsonify([])
    frames_dir = _project_dir / "preview" / "frames"
    if not frames_dir.exists():
        return jsonify([])
    files = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))
    return jsonify([
        {"name": f.name, "url": f"/api/files/preview/frames/{f.name}"}
        for f in files
    ])


@app.route("/api/stage_files")
def api_stage_files():
    if _project_dir is None:
        return jsonify({})
    out_dir = _project_dir / "output"
    stages = {
        "stage_01_concat.mp4": 1,
        "stage_02_beauty.mp4": 2,
        "stage_03_color.mp4": 3,
        "stage_04_subtitle.mp4": 4,
        "final.mp4": 5,
    }
    result = {}
    for fname, n in stages.items():
        p = out_dir / fname
        result[fname] = {
            "exists": p.exists(),
            "size": p.stat().st_size if p.exists() else 0,
            "url": f"/api/files/output/{fname}" if p.exists() else None,
            "stage": n,
        }
    return jsonify(result)


@app.route("/api/files/<path:rel>")
def api_files(rel: str):
    """提供项目目录内的静态文件（视频/图片）。"""
    if _project_dir is None:
        abort(404)
    target = (_project_dir / rel).resolve()
    # 安全检查：不允许跳出项目目录
    if not str(target).startswith(str(_project_dir.resolve())):
        abort(403)
    if not target.exists():
        abort(404)
    return send_file(str(target))


@app.route("/api/open_in_finder", methods=["POST"])
def api_open_in_finder():
    data = request.json or {}
    path = data.get("path", "")
    if path and Path(path).exists():
        p = Path(path)
        if p.is_file():
            subprocess.Popen(["open", "-R", str(p)])
        else:
            subprocess.Popen(["open", str(p)])
    return jsonify({"ok": True})


@app.route("/api/dialog/folder", methods=["POST"])
def api_dialog_folder():
    """选择文件夹（pywebview 优先，失败时 fallback 到 osascript）。"""
    result = _choose_path("folder")
    if result.get("path"):
        return jsonify({"path": result.get("path"), "cancelled": False})
    if result.get("cancelled"):
        return jsonify({"path": None, "cancelled": True})
    return jsonify({
        "path": None,
        "cancelled": False,
        "error": result.get("error") or "无法打开文件夹选择对话框",
    }), 400


@app.route("/api/dialog/file", methods=["POST"])
def api_dialog_file():
    """选择文件（pywebview 优先，失败时 fallback 到 osascript）。"""
    result = _choose_path("file")
    if result.get("path"):
        return jsonify({"path": result.get("path"), "cancelled": False})
    if result.get("cancelled"):
        return jsonify({"path": None, "cancelled": True})
    return jsonify({
        "path": None,
        "cancelled": False,
        "error": result.get("error") or "无法打开文件选择对话框",
    }), 400


@app.route("/api/script", methods=["GET"])
def api_get_script():
    """读取 script_matched.json 或 script_draft.json。"""
    if _project_dir is None:
        return jsonify({}), 400
    for name in ["script_matched.json", "script_draft.json"]:
        p = _project_dir / "data" / name
        if p.exists():
            try:
                return jsonify(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
    return jsonify({})


@app.route("/api/script", methods=["POST"])
def api_save_script():
    """保存修改后的脚本到 script_draft.json。"""
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    data = request.json
    if not data:
        return jsonify({"error": "无效 JSON"}), 400
    p = _project_dir / "data" / "script_draft.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True})


@app.route("/api/materials")
def api_materials():
    if _project_dir is None:
        return jsonify({}), 400
    p = _project_dir / "data" / "materials.json"
    if not p.exists():
        return jsonify({})
    try:
        return jsonify(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return jsonify({})


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

@app.route("/api/capabilities")
def api_capabilities():
    from modules.capabilities import legacy_step_mapping, list_capabilities

    specs = [spec.__dict__ for spec in list_capabilities()]
    return jsonify({
        "ok": True,
        "capabilities": specs,
        "legacy_step_mapping": legacy_step_mapping(),
    })


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


@app.route("/api/capabilities/idempotency/cache", methods=["GET"])
def api_capability_idempotency_cache():
    source = str(request.args.get("source", "merged") or "merged").strip().lower()
    if source not in {"memory", "persisted", "merged"}:
        return jsonify({"error": "source 仅支持 memory/persisted/merged"}), 400
    include_expired = _parse_boolish(request.args.get("include_expired", "false"), default=False)
    match_mode = str(request.args.get("match_mode", "contains") or "contains").strip().lower()
    if match_mode not in {"contains", "exact"}:
        return jsonify({"error": "match_mode 仅支持 contains/exact"}), 400
    actor_id_filter = _normalize_capability_idempotency_filter_text(request.args.get("actor_id", ""))
    endpoint_filter = _normalize_capability_idempotency_filter_text(request.args.get("endpoint", ""))
    idempotency_key_filter = _normalize_capability_idempotency_filter_text(request.args.get("idempotency_key", ""))
    project_path_filter = _normalize_capability_idempotency_filter_text(request.args.get("project_path", ""))
    ttl_seconds = _normalize_capability_idempotency_ttl(
        request.args.get("ttl_seconds", _CAPABILITY_IDEMPOTENCY_TTL_SECONDS),
        default=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
    )
    try:
        limit = int(request.args.get("limit", "200") or "200")
    except Exception:
        limit = 200
    try:
        offset = int(request.args.get("offset", "0") or "0")
    except Exception:
        offset = 0

    payload = _collect_capability_idempotency_records(
        source=source,
        ttl_seconds=ttl_seconds,
        include_expired=include_expired,
        limit=limit,
        offset=offset,
        actor_id_filter=actor_id_filter,
        endpoint_filter=endpoint_filter,
        idempotency_key_filter=idempotency_key_filter,
        project_path_filter=project_path_filter,
        match_mode=match_mode,
    )
    return jsonify({"ok": True, **payload})


@app.route("/api/capabilities/idempotency/cache/prune", methods=["POST"])
def api_capability_idempotency_cache_prune():
    payload = request.json or {}
    ttl_seconds = _normalize_capability_idempotency_ttl(
        payload.get("ttl_seconds", _CAPABILITY_IDEMPOTENCY_TTL_SECONDS),
        default=_CAPABILITY_IDEMPOTENCY_TTL_SECONDS,
    )
    remove_expired = _parse_boolish(payload.get("remove_expired", True), default=True)
    clear_memory = _parse_boolish(payload.get("clear_memory", False), default=False)
    clear_persisted = _parse_boolish(payload.get("clear_persisted", False), default=False)

    max_entries_raw = payload.get("max_entries", None)
    max_entries = None
    if max_entries_raw not in {None, ""}:
        try:
            max_entries = max(1, int(max_entries_raw))
        except Exception:
            max_entries = _CAPABILITY_IDEMPOTENCY_LIMIT

    with _capability_idempotency_lock:
        memory_before = len(_capability_idempotency_cache)
        memory_after_map = deepcopy(_capability_idempotency_cache)
        if clear_memory:
            memory_after_map = {}
        else:
            if remove_expired:
                memory_after_map = _filter_capability_idempotency_entries(
                    memory_after_map,
                    ttl_seconds=ttl_seconds,
                    include_expired=False,
                )
            else:
                memory_after_map = _filter_capability_idempotency_entries(
                    memory_after_map,
                    ttl_seconds=ttl_seconds,
                    include_expired=True,
                )
            if max_entries is not None:
                if remove_expired:
                    memory_after_map = _trim_capability_idempotency_entries_with_limit(
                        memory_after_map,
                        max_entries=max_entries,
                        ttl_seconds=ttl_seconds,
                    )
                else:
                    memory_after_map = _limit_capability_idempotency_entries(
                        memory_after_map,
                        max_entries=max_entries,
                    )
            else:
                if remove_expired:
                    memory_after_map = _trim_capability_idempotency_entries_with_limit(
                        memory_after_map,
                        max_entries=_CAPABILITY_IDEMPOTENCY_LIMIT,
                        ttl_seconds=ttl_seconds,
                    )
                else:
                    memory_after_map = _limit_capability_idempotency_entries(
                        memory_after_map,
                        max_entries=_CAPABILITY_IDEMPOTENCY_LIMIT,
                    )
        _capability_idempotency_cache.clear()
        _capability_idempotency_cache.update(memory_after_map)
        memory_after = len(_capability_idempotency_cache)

    persisted_before_map = _load_capability_idempotency_store(include_expired=True, ttl_seconds=ttl_seconds)
    persisted_before = len(persisted_before_map)
    if clear_persisted:
        persisted_after_map = {}
    else:
        if remove_expired:
            persisted_after_map = _filter_capability_idempotency_entries(
                persisted_before_map,
                ttl_seconds=ttl_seconds,
                include_expired=False,
            )
        else:
            persisted_after_map = _filter_capability_idempotency_entries(
                persisted_before_map,
                ttl_seconds=ttl_seconds,
                include_expired=True,
            )
        if max_entries is not None:
            if remove_expired:
                persisted_after_map = _trim_capability_idempotency_entries_with_limit(
                    persisted_after_map,
                    max_entries=max_entries,
                    ttl_seconds=ttl_seconds,
                )
            else:
                persisted_after_map = _limit_capability_idempotency_entries(
                    persisted_after_map,
                    max_entries=max_entries,
                )
        else:
            if remove_expired:
                persisted_after_map = _trim_capability_idempotency_entries_with_limit(
                    persisted_after_map,
                    max_entries=_CAPABILITY_IDEMPOTENCY_LIMIT,
                    ttl_seconds=ttl_seconds,
                )
            else:
                persisted_after_map = _limit_capability_idempotency_entries(
                    persisted_after_map,
                    max_entries=_CAPABILITY_IDEMPOTENCY_LIMIT,
                )
    _save_capability_idempotency_store(persisted_after_map)
    persisted_after = len(persisted_after_map)

    snapshot = _collect_capability_idempotency_records(
        source="merged",
        ttl_seconds=ttl_seconds,
        include_expired=False,
        limit=200,
    )
    return jsonify(
        {
            "ok": True,
            "prune": {
                "ttl_seconds": ttl_seconds,
                "remove_expired": remove_expired,
                "clear_memory": clear_memory,
                "clear_persisted": clear_persisted,
                "max_entries": max_entries,
                "memory_before": memory_before,
                "memory_after": memory_after,
                "memory_removed": max(memory_before - memory_after, 0),
                "persisted_before": persisted_before,
                "persisted_after": persisted_after,
                "persisted_removed": max(persisted_before - persisted_after, 0),
            },
            **snapshot,
        }
    )


@app.route("/api/agent/capabilities", methods=["GET"])
def api_agent_capabilities():
    from modules.capabilities import legacy_step_mapping, list_capabilities

    specs = [spec.__dict__ for spec in list_capabilities()]
    route_map = _agent_capability_route_map()
    cost_model_cfg = _read_agent_cost_model_config()
    for spec in specs:
        cid = str(spec.get("capability_id", "") or "")
        spec["agent_routes"] = route_map.get(cid, {})

    return jsonify({
        "ok": True,
        "capabilities": specs,
        "legacy_step_mapping": legacy_step_mapping(),
        "agent_management_routes": {
            "templates_list": "GET /api/agent/templates",
            "templates_upsert": "POST /api/agent/templates",
            "templates_delete": "DELETE /api/agent/templates/<template_id>",
            "skills_invoke": "POST /api/agent/skills/invoke",
            "tasks_history": "GET /api/agent/tasks/history",
            "tasks_export": "POST /api/agent/tasks/<job_id>/export",
            "tasks_replay": "POST /api/agent/tasks/<job_id>/replay",
            "observability_summary": "GET /api/agent/observability",
            "observability_export": "POST /api/agent/observability/export",
            "workflows_catalog": "GET /api/workflows/catalog",
            "workflows_list": "GET /api/workflows",
            "workflows_upsert": "POST /api/workflows",
            "workflows_delete": "DELETE /api/workflows/<workflow_id>",
            "workflows_plan": "POST /api/workflows/plan",
            "workflows_run": "POST /api/workflows/run",
            "workflow_runs_history": "GET /api/workflows/runs",
            "workflow_run_rerun": "POST /api/workflows/runs/<run_id>/rerun",
        },
        "agent_skills": _list_agent_skills(),
        "agent_template_schema": {
            "scope": ["system", "project", "agent"],
            "variable_types": ["string", "number", "integer", "boolean", "array", "object"],
            "fields": [
                "template_id",
                "name",
                "capability_id",
                "scope",
                "actor_id",
                "tags",
                "content",
                "base_template_id",
                "overrides",
                "variables",
            ],
        },
        "agent_task_modes": {
            "single_capability": {
                "required_fields": ["capability_id", "input"],
                "entrypoint": "POST /api/agent/tasks/run",
            },
            "skill_sequence": {
                "required_fields": ["mode=skill_sequence", "skills[]"],
                "supported_strategy": ["sequential", "parallel", "conditional"],
                "entrypoint": "POST /api/agent/tasks/run",
                "step_fields": [
                    "skill_id",
                    "input",
                    "retry_policy",
                    "timeout_seconds",
                    "continue_on_error",
                    "condition",
                ],
                "flow_fields": ["strategy", "max_parallel", "budget_limit"],
                "condition_fields": ["depends_on", "status_in", "require_all", "if_overall_ok"],
                "budget_fields": ["max_steps", "max_failures", "max_duration_seconds"],
            },
        },
        "agent_governance": {
            "policy_file": "data/agent_governance.json",
            "usage_file": "data/agent_governance_usage.json",
            "cost_model_file": "data/agent_cost_model.json",
            "resolution_order": [
                "default_limits",
                "actor_limits",
                "capability_limits",
                "actor_capability_limits",
                "dynamic_usage_suggested_limits",
            ],
            "behavior": "tighten_only",
            "cost_model": cost_model_cfg,
            "usage_fields": [
                "total_prompt_tokens",
                "total_completion_tokens",
                "total_tokens",
                "total_estimated_cost_usd",
                "avg_estimated_cost_usd",
                "recent_runs",
            ],
        },
        "request_context_schema": {
            "actor_type": {"type": "string", "enum": ["human", "agent"], "default": "agent"},
            "actor_id": {"type": "string", "max_length": 128},
            "run_mode": {"type": "string", "enum": ["interactive", "headless"], "default": "headless"},
            "idempotency_key": {"type": "string", "max_length": 128},
            "trace_id": {"type": "string", "max_length": 128},
        },
    })


@app.route("/api/agent/tasks/plan", methods=["POST"])
def api_agent_tasks_plan():
    payload = request.json or {}
    request_ctx = _parse_request_context()
    mode_hint = str(payload.get("mode", "") or "").strip().lower()
    strategy = str(payload.get("strategy", "sequential") or "sequential").strip().lower()
    task_id = str(uuid.uuid4())[:8]
    dry_run = bool(payload.get("dry_run", True))

    skills_raw = payload.get("skills", None)
    if mode_hint == "skill_sequence" or isinstance(skills_raw, list):
        if strategy not in {"sequential", "parallel", "conditional"}:
            return jsonify({"error": "strategy 仅支持 sequential/parallel/conditional"}), 400
        explicit_max_parallel = "max_parallel" in payload
        try:
            requested_max_parallel = int(payload.get("max_parallel", 4) or 4)
        except Exception:
            requested_max_parallel = 4
        requested_max_parallel = max(1, min(requested_max_parallel, 8))
        requested_budget = _normalize_skill_budget_limit(payload.get("budget_limit", {}))
        try:
            steps = _normalize_agent_skill_steps(
                skills_raw,
                default_retry_policy=payload.get("retry_policy", {}),
                default_timeout_seconds=_normalize_skill_timeout_seconds(payload.get("timeout_seconds", 120), default=120.0),
            )
        except Exception as exc:
            return jsonify({"error": f"skills 解析失败: {exc}"}), 400
        try:
            governance_applied = _apply_governance_to_skill_flow(
                actor_id=str(request_ctx.get("actor_id", "") or ""),
                steps=steps,
                requested_budget=requested_budget,
                requested_max_parallel=requested_max_parallel,
                explicit_max_parallel=explicit_max_parallel,
            )
        except Exception as exc:
            return jsonify({"error": f"治理校验失败: {exc}"}), 400
        max_parallel = int(governance_applied.get("max_parallel", 1) or 1)
        budget_limit = governance_applied.get("budget_limit", {}) if isinstance(governance_applied.get("budget_limit"), dict) else {}
        governance = governance_applied.get("governance", {}) if isinstance(governance_applied.get("governance"), dict) else {}

        plan = {
            "task_id": task_id,
            "mode": "skill_sequence",
            "dry_run": dry_run,
            "skill_flow": {
                "strategy": strategy,
                "max_parallel": max_parallel,
                "budget_limit": budget_limit,
                "governance": governance,
                "steps": steps,
            },
        }
        return jsonify({
            "ok": True,
            "task_plan": plan,
            "plan_summary": {
                "task_id": task_id,
                "mode": "skill_sequence",
                "strategy": strategy,
                "total_steps": len(steps),
                "max_parallel": max_parallel if strategy == "parallel" else 1,
                "budget_limit": budget_limit,
                "governance": governance,
                "conditional_steps": sum(1 for x in steps if isinstance(x.get("condition"), dict) and x.get("condition")),
            },
        })

    capability_id = str(payload.get("capability_id", "") or "").strip()
    input_payload = payload.get("input", {})
    if not capability_id:
        return jsonify({"error": "capability_id 不能为空（或使用 mode=skill_sequence + skills）"}), 400
    if not isinstance(input_payload, dict):
        return jsonify({"error": "input 必须是对象"}), 400
    input_payload = _apply_agent_capability_input_defaults(capability_id, input_payload)

    route_map = _agent_capability_route_map()
    routes = route_map.get(capability_id)
    if not isinstance(routes, dict) or not routes:
        return jsonify({"error": f"不支持的 capability_id: {capability_id}"}), 400

    primary = routes.get("plan") or routes.get("draft") or routes.get("list") or next(iter(routes.values()))
    method, endpoint = primary.split(" ", 1) if " " in primary else ("POST", primary)

    plan = {
        "task_id": task_id,
        "capability_id": capability_id,
        "mode": "single_capability",
        "primary_call": {
            "method": method,
            "endpoint": endpoint,
            "payload": input_payload,
        },
        "available_routes": routes,
        "dry_run": dry_run,
    }
    return jsonify({
        "ok": True,
        "task_plan": plan,
        "plan_summary": {
            "task_id": task_id,
            "capability_id": capability_id,
            "primary_endpoint": endpoint,
            "available_route_count": len(routes),
        },
    })


@app.route("/api/agent/tasks/run", methods=["POST"])
def api_agent_tasks_run():
    payload = request.json or {}
    task_plan = payload.get("task_plan", {}) if isinstance(payload.get("task_plan"), dict) else {}
    request_ctx = _parse_request_context()
    mode_hint = str(payload.get("mode", "") or task_plan.get("mode", "") or "").strip().lower()
    dry_run = bool(payload.get("dry_run", task_plan.get("dry_run", False)))
    task_id = str(task_plan.get("task_id", "") or "") if isinstance(task_plan, dict) else ""
    if not task_id:
        task_id = str(uuid.uuid4())[:8]
    job_id = str(uuid.uuid4())[:8]

    plan_skill_flow = task_plan.get("skill_flow", {}) if isinstance(task_plan.get("skill_flow"), dict) else {}
    skills_raw = payload.get("skills", None)
    if skills_raw is None:
        skills_raw = plan_skill_flow.get("steps", None)
    if mode_hint == "skill_sequence" or isinstance(skills_raw, list):
        strategy = str(payload.get("strategy", "") or plan_skill_flow.get("strategy", "sequential") or "sequential").strip().lower()
        if strategy not in {"sequential", "parallel", "conditional"}:
            return jsonify({"error": "strategy 仅支持 sequential/parallel/conditional"}), 400
        explicit_max_parallel = ("max_parallel" in payload) or ("max_parallel" in plan_skill_flow)
        try:
            requested_max_parallel = int(payload.get("max_parallel", plan_skill_flow.get("max_parallel", 4)) or 4)
        except Exception:
            requested_max_parallel = 4
        requested_max_parallel = max(1, min(requested_max_parallel, 8))
        requested_budget = _normalize_skill_budget_limit(payload.get("budget_limit", plan_skill_flow.get("budget_limit", {})))
        try:
            steps = _normalize_agent_skill_steps(
                skills_raw,
                default_retry_policy=payload.get("retry_policy", plan_skill_flow.get("retry_policy", {})),
                default_timeout_seconds=_normalize_skill_timeout_seconds(
                    payload.get("timeout_seconds", plan_skill_flow.get("timeout_seconds", 120)),
                    default=120.0,
                ),
            )
        except Exception as exc:
            return jsonify({"error": f"skills 解析失败: {exc}"}), 400
        try:
            governance_applied = _apply_governance_to_skill_flow(
                actor_id=str(request_ctx.get("actor_id", "") or ""),
                steps=steps,
                requested_budget=requested_budget,
                requested_max_parallel=requested_max_parallel,
                explicit_max_parallel=explicit_max_parallel,
            )
        except Exception as exc:
            return jsonify({"error": f"治理校验失败: {exc}"}), 400
        max_parallel = int(governance_applied.get("max_parallel", 1) or 1)
        budget_limit = governance_applied.get("budget_limit", {}) if isinstance(governance_applied.get("budget_limit"), dict) else {}
        governance = governance_applied.get("governance", {}) if isinstance(governance_applied.get("governance"), dict) else {}

        if strategy == "parallel":
            has_condition = any(
                isinstance(step.get("condition"), dict) and bool(step.get("condition"))
                for step in steps
            )
            if has_condition:
                return jsonify({"error": "strategy=parallel 暂不支持 step.condition，请改用 strategy=conditional"}), 400

        steps_run = deepcopy(steps)
        if dry_run:
            for step in steps_run:
                if str(step.get("method", "")).upper() != "GET":
                    inp = step.get("input", {})
                    if isinstance(inp, dict) and "dry_run" not in inp:
                        inp["dry_run"] = True

        def _run_one_step(idx: int, step: Dict[str, Any]) -> Dict[str, Any]:
            skill_id = str(step.get("skill_id", "") or "")
            step_id = str(step.get("step_id", f"step_{idx:02d}") or f"step_{idx:02d}")
            _jobs[job_id]["log"].append(f"[AgentSkillFlow] {idx}/{len(steps_run)} step_id={step_id} skill={skill_id}")
            try:
                result = _execute_agent_skill(
                    skill_id=skill_id,
                    input_payload=step.get("input", {}) if isinstance(step.get("input"), dict) else {},
                    retry_policy=step.get("retry_policy", {}) if isinstance(step.get("retry_policy"), dict) else {},
                    timeout_seconds=float(step.get("timeout_seconds", 120.0) or 120.0),
                    request_context=request_ctx,
                    logger=lambda msg, sid=step_id: _jobs[job_id]["log"].append(f"[AgentSkillFlow:{sid}] {msg}"),
                )
                result["step_id"] = step_id
                result["index"] = idx
                result["status"] = "done"
                result["continue_on_error"] = bool(step.get("continue_on_error", False))
                result["condition"] = deepcopy(step.get("condition", {})) if isinstance(step.get("condition"), dict) else {}
                return result
            except Exception as exc:
                err = str(exc)
                failure_item = {
                    "step_id": step_id,
                    "index": idx,
                    "skill_id": skill_id,
                    "skill_name": str(step.get("skill_name", "") or ""),
                    "capability_id": str(step.get("capability_id", "") or ""),
                    "status": "error",
                    "continue_on_error": bool(step.get("continue_on_error", False)),
                    "error": err,
                    "condition": deepcopy(step.get("condition", {})) if isinstance(step.get("condition"), dict) else {},
                }
                _jobs[job_id]["log"].append(f"[AgentSkillFlow:{step_id}] 失败: {err}")
                return failure_item

        def _do_run_skill_sequence():
            _jobs[job_id]["progress"] = 6
            _jobs[job_id]["log"].append(
                f"[Agent] task_id={task_id} mode=skill_sequence strategy={strategy}"
            )
            started = time.monotonic()
            step_results: List[Dict[str, Any]] = []
            previous_by_step: Dict[str, Dict[str, Any]] = {}
            total = len(steps_run)
            if strategy in {"sequential", "conditional"}:
                for idx, step in enumerate(steps_run, start=1):
                    elapsed = time.monotonic() - started
                    if budget_limit.get("max_duration_seconds", 0) > 0 and elapsed > int(budget_limit.get("max_duration_seconds", 0)):
                        raise RuntimeError(
                            f"预算超限: max_duration_seconds={budget_limit.get('max_duration_seconds')}"
                        )
                    _jobs[job_id]["progress"] = min(10 + int((idx - 1) * 80 / max(total, 1)), 88)
                    step_id = str(step.get("step_id", f"step_{idx:02d}") or f"step_{idx:02d}")
                    if strategy == "conditional":
                        should_run, skip_reason = _should_run_conditional_step(
                            step.get("condition", {}) if isinstance(step.get("condition"), dict) else {},
                            previous_by_step,
                        )
                        if not should_run:
                            skipped_item = {
                                "step_id": step_id,
                                "index": idx,
                                "skill_id": str(step.get("skill_id", "") or ""),
                                "skill_name": str(step.get("skill_name", "") or ""),
                                "capability_id": str(step.get("capability_id", "") or ""),
                                "status": "skipped",
                                "continue_on_error": bool(step.get("continue_on_error", False)),
                                "skip_reason": skip_reason,
                                "condition": deepcopy(step.get("condition", {})),
                            }
                            step_results.append(skipped_item)
                            previous_by_step[step_id] = skipped_item
                            _jobs[job_id]["log"].append(f"[AgentSkillFlow:{step_id}] 跳过: {skip_reason}")
                            continue
                    item = _run_one_step(idx, step)
                    step_results.append(item)
                    previous_by_step[step_id] = item
                    failed_now = sum(1 for x in step_results if x.get("status") == "error")
                    if budget_limit.get("max_failures", 0) > 0 and failed_now > int(budget_limit.get("max_failures", 0)):
                        raise RuntimeError(
                            f"预算超限: max_failures={budget_limit.get('max_failures')}"
                        )
                    if item.get("status") == "error" and not bool(item.get("continue_on_error", False)):
                        raise RuntimeError(f"step={item.get('step_id')} 执行失败: {item.get('error')}")
            else:
                workers = min(max_parallel, max(total, 1))
                _jobs[job_id]["log"].append(f"[AgentSkillFlow] 并行执行 workers={workers}")
                ordered: Dict[int, Dict[str, Any]] = {}
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    future_map = {
                        pool.submit(_run_one_step, idx, step): idx
                        for idx, step in enumerate(steps_run, start=1)
                    }
                    completed = 0
                    for fut in as_completed(future_map):
                        idx = future_map[fut]
                        try:
                            item = fut.result()
                        except Exception as exc:  # pragma: no cover
                            item = {
                                "step_id": f"step_{idx:02d}",
                                "index": idx,
                                "skill_id": "",
                                "status": "error",
                                "continue_on_error": False,
                                "error": str(exc),
                            }
                        ordered[idx] = item
                        completed += 1
                        _jobs[job_id]["progress"] = min(12 + int(completed * 76 / max(total, 1)), 90)
                step_results = [ordered[i] for i in sorted(ordered.keys())]
                blocking = [x for x in step_results if x.get("status") == "error" and not bool(x.get("continue_on_error", False))]
                if blocking:
                    first = blocking[0]
                    raise RuntimeError(f"parallel step={first.get('step_id')} 执行失败: {first.get('error')}")

            failed = sum(1 for x in step_results if x.get("status") == "error")
            skipped = sum(1 for x in step_results if x.get("status") == "skipped")
            success = sum(1 for x in step_results if x.get("status") == "done")
            if budget_limit.get("max_failures", 0) > 0 and failed > int(budget_limit.get("max_failures", 0)):
                raise RuntimeError(f"预算超限: max_failures={budget_limit.get('max_failures')}")
            elapsed_total = time.monotonic() - started
            if budget_limit.get("max_duration_seconds", 0) > 0 and elapsed_total > int(budget_limit.get("max_duration_seconds", 0)):
                raise RuntimeError(
                    f"预算超限: max_duration_seconds={budget_limit.get('max_duration_seconds')}"
                )
            summary_payload = {
                "task_id": task_id,
                "mode": "skill_sequence",
                "strategy": strategy,
                "dry_run": dry_run,
                "max_parallel": max_parallel if strategy == "parallel" else 1,
                "budget_limit": budget_limit,
                "governance": governance,
                "total_steps": total,
                "success_steps": success,
                "failed_steps": failed,
                "skipped_steps": skipped,
                "overall_ok": failed == 0,
                "steps": step_results,
                "duration_seconds": round(max(elapsed_total, 0.0), 4),
            }
            governance_usage = (
                _record_governance_usage_for_skill_flow(
                    actor_id=str(request_ctx.get("actor_id", "") or ""),
                    summary=summary_payload,
                )
                if not dry_run
                else {"ok": False, "reason": "dry_run"}
            )
            if isinstance(governance_usage, dict):
                summary_payload["governance_usage"] = governance_usage
            _jobs[job_id]["progress"] = 95
            return summary_payload

        _run_in_bg(
            job_id,
            _do_run_skill_sequence,
            kind="agent_task",
            job_meta={
                "actor_type": str(request_ctx.get("actor_type", "") or ""),
                "actor_id": str(request_ctx.get("actor_id", "") or ""),
                "trace_id": str(request_ctx.get("trace_id", "") or ""),
                "task_mode": "skill_sequence",
                "strategy": strategy,
                "template_hits": _extract_template_ids_from_value(payload),
                "replay": {
                    "method": "POST",
                    "endpoint": "/api/agent/tasks/run",
                    "payload": deepcopy(payload),
                    "request_context": deepcopy(request_ctx),
                },
            },
        )
        return jsonify({
            "ok": True,
            "job_id": job_id,
            "task_id": task_id,
            "mode": "skill_sequence",
            "strategy": strategy,
            "max_parallel": max_parallel if strategy == "parallel" else 1,
            "budget_limit": budget_limit,
            "governance": governance,
            "total_steps": len(steps_run),
            "dry_run": dry_run,
        })

    capability_id = str(payload.get("capability_id", "") or task_plan.get("capability_id", "") or "").strip()
    if not capability_id:
        return jsonify({"error": "capability_id 不能为空（或使用 mode=skill_sequence + skills）"}), 400

    route_map = _agent_capability_route_map()
    routes = route_map.get(capability_id)
    if not isinstance(routes, dict) or not routes:
        return jsonify({"error": f"不支持的 capability_id: {capability_id}"}), 400

    input_payload = payload.get("input", None)
    if input_payload is None:
        input_payload = task_plan.get("primary_call", {}).get("payload", {}) if isinstance(task_plan, dict) else {}
    if not isinstance(input_payload, dict):
        return jsonify({"error": "input 必须是对象"}), 400
    input_payload = _apply_agent_capability_input_defaults(capability_id, input_payload)

    action = str(payload.get("action", "auto") or "auto").strip().lower()

    primary_call_raw = task_plan.get("primary_call") if isinstance(task_plan, dict) else None
    if isinstance(primary_call_raw, dict) and str(primary_call_raw.get("endpoint", "") or "").strip():
        method = str(primary_call_raw.get("method", "POST") or "POST").strip().upper()
        endpoint = str(primary_call_raw.get("endpoint", "") or "").strip()
    else:
        try:
            resolved = _resolve_agent_primary_call(capability_id=capability_id, routes=routes, action=action)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400
        method = resolved["method"]
        endpoint = resolved["endpoint"]

    call_payload = dict(input_payload)
    if dry_run and method != "GET" and "dry_run" not in call_payload:
        call_payload["dry_run"] = True

    def _do_run():
        _jobs[job_id]["progress"] = 10
        _jobs[job_id]["log"].append(f"[Agent] task_id={task_id} capability={capability_id}")
        _jobs[job_id]["log"].append(f"[Agent] 调用 {method} {endpoint}")

        ret = _invoke_agent_primary_call(
            method=method,
            endpoint=endpoint,
            payload=call_payload,
            request_context=request_ctx,
        )
        status_code = int(ret.get("status_code", 0) or 0)
        data = ret.get("data") if isinstance(ret.get("data"), dict) else {}
        _jobs[job_id]["progress"] = 85
        if status_code >= 400 or not bool(data.get("ok", False)):
            err = str(data.get("error", "") or f"子调用失败（status={status_code}）")
            raise RuntimeError(err)
        _jobs[job_id]["progress"] = 95
        return {
            "task_id": task_id,
            "capability_id": capability_id,
            "primary_call": {
                "method": method,
                "endpoint": endpoint,
                "payload": call_payload,
            },
            "status_code": status_code,
            "response": data,
        }

    _run_in_bg(
        job_id,
        _do_run,
        kind="agent_task",
        job_meta={
            "actor_type": str(request_ctx.get("actor_type", "") or ""),
            "actor_id": str(request_ctx.get("actor_id", "") or ""),
            "trace_id": str(request_ctx.get("trace_id", "") or ""),
            "task_mode": "single_capability",
            "capability_id": capability_id,
            "template_hits": _extract_template_ids_from_value(payload),
            "replay": {
                "method": "POST",
                "endpoint": "/api/agent/tasks/run",
                "payload": deepcopy(payload),
                "request_context": deepcopy(request_ctx),
            },
        },
    )
    return jsonify({
        "ok": True,
        "job_id": job_id,
        "task_id": task_id,
        "capability_id": capability_id,
        "primary_call": {
            "method": method,
            "endpoint": endpoint,
        },
    })


@app.route("/api/agent/tasks/<job_id>", methods=["GET"])
def api_agent_task_status(job_id: str):
    job = _jobs.get(job_id)
    if not isinstance(job, dict) or job.get("kind") not in {"agent_task", "agent_skill"}:
        history_item = _find_agent_task_history_record(job_id)
        if not isinstance(history_item, dict):
            return jsonify({"error": "agent task/skill 不存在"}), 404

        status = str(history_item.get("status", "unknown") or "unknown").strip().lower()
        chain_view = _build_chain_view_from_history_item(history_item)
        return jsonify({
            "ok": True,
            "job_id": str(history_item.get("job_id", "") or job_id),
            "status": status,
            "kind": str(history_item.get("kind", "agent_task") or "agent_task"),
            "source": "history",
            "progress": 100,
            "log": [],
            "error": history_item.get("error", ""),
            "result": {"history_summary": history_item},
            "chain_view": chain_view,
            "started_at": history_item.get("started_at"),
            "finished_at": history_item.get("finished_at"),
        })
    kind = str(job.get("kind", "agent_task") or "agent_task")
    result_payload = job.get("result") if isinstance(job.get("result"), dict) else {}

    def _to_int(value: Any) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = 0
        return max(parsed, 0)

    def _to_float(value: Any) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = 0.0
        return max(parsed, 0.0)

    def _build_chain_view(kind_value: str, result: Dict[str, Any], fallback_status: str) -> Dict[str, Any]:
        mode = "single_capability"
        status_norm = str(fallback_status or "unknown").strip().lower()
        if status_norm == "done":
            overall_status = "done"
        elif status_norm in {"error", "cancelled"}:
            overall_status = "error"
        else:
            overall_status = "running"

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cost_usd = 0.0

        if kind_value == "agent_skill":
            mode = "skill_invoke"
            usage_tokens = result.get("usage_tokens", {}) if isinstance(result.get("usage_tokens"), dict) else {}
            estimated_cost = result.get("estimated_cost", {}) if isinstance(result.get("estimated_cost"), dict) else {}
            p = _to_int(usage_tokens.get("prompt_tokens", 0))
            c = _to_int(usage_tokens.get("completion_tokens", 0))
            cost = _to_float(estimated_cost.get("total_cost_usd", 0.0))
            total_prompt_tokens += p
            total_completion_tokens += c
            total_cost_usd += cost
            nodes.append({
                "node_id": str(result.get("invoke_id", "") or result.get("skill_id", "skill")),
                "node_type": "skill",
                "status": "done" if bool(result.get("status_code", 0)) and _to_int(result.get("status_code", 0)) < 400 else overall_status,
                "skill_id": str(result.get("skill_id", "") or ""),
                "capability_id": str(result.get("capability_id", "") or ""),
                "duration_seconds": round(_to_float(result.get("duration_seconds", 0.0)), 4),
                "prompt_tokens": p,
                "completion_tokens": c,
                "estimated_cost_usd": round(cost, 8),
            })
        elif str(result.get("mode", "") or "").strip().lower() == "skill_sequence":
            mode = "skill_sequence"
            steps = result.get("steps", [])
            if not isinstance(steps, list):
                steps = []
            known_step_ids = set()
            for idx, item in enumerate(steps, start=1):
                if not isinstance(item, dict):
                    continue
                step_id = str(item.get("step_id", "") or f"step_{idx:02d}")
                known_step_ids.add(step_id)
                usage_tokens = item.get("usage_tokens", {}) if isinstance(item.get("usage_tokens"), dict) else {}
                estimated_cost = item.get("estimated_cost", {}) if isinstance(item.get("estimated_cost"), dict) else {}
                p = _to_int(usage_tokens.get("prompt_tokens", 0))
                c = _to_int(usage_tokens.get("completion_tokens", 0))
                cost = _to_float(estimated_cost.get("total_cost_usd", 0.0))
                total_prompt_tokens += p
                total_completion_tokens += c
                total_cost_usd += cost
                nodes.append({
                    "node_id": step_id,
                    "node_type": "skill",
                    "index": _to_int(item.get("index", idx)),
                    "status": str(item.get("status", "unknown") or "unknown"),
                    "skill_id": str(item.get("skill_id", "") or ""),
                    "capability_id": str(item.get("capability_id", "") or ""),
                    "continue_on_error": bool(item.get("continue_on_error", False)),
                    "duration_seconds": round(_to_float(item.get("duration_seconds", 0.0)), 4),
                    "prompt_tokens": p,
                    "completion_tokens": c,
                    "estimated_cost_usd": round(cost, 8),
                    "error": str(item.get("error", "") or ""),
                    "condition": deepcopy(item.get("condition", {})) if isinstance(item.get("condition"), dict) else {},
                })
            strategy = str(result.get("strategy", "") or "").strip().lower()
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
                    edges.append({
                        "from": dep_id,
                        "to": node_id,
                        "type": "condition_depends_on",
                    })
                    deps_added = True
                if not deps_added and strategy in {"sequential", "conditional"} and idx > 0:
                    prev_node_id = str(nodes[idx - 1].get("node_id", "") or "")
                    if prev_node_id:
                        edges.append({
                            "from": prev_node_id,
                            "to": node_id,
                            "type": "sequence",
                        })
        else:
            mode = "single_capability"
            nodes.append({
                "node_id": str(result.get("task_id", "") or "task"),
                "node_type": "capability",
                "status": "done" if bool(result.get("status_code", 0)) and _to_int(result.get("status_code", 0)) < 400 else overall_status,
                "capability_id": str(result.get("capability_id", "") or ""),
                "endpoint": str(
                    (result.get("primary_call", {}) if isinstance(result.get("primary_call"), dict) else {}).get("endpoint", "")
                    or ""
                ),
                "duration_seconds": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
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
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "estimated_cost_usd": round(total_cost_usd, 8),
            },
            "nodes": nodes,
            "edges": edges,
        }

    chain_view = _build_chain_view(
        kind_value=kind,
        result=result_payload,
        fallback_status=str(job.get("status", "unknown") or "unknown"),
    )
    return jsonify({
        "ok": True,
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "kind": kind,
        "source": "memory",
        "progress": int(job.get("progress", 0) or 0),
        "log": list(job.get("log", []))[-80:],
        "error": job.get("error"),
        "result": result_payload,
        "chain_view": chain_view,
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    })


@app.route("/api/agent/tasks/history", methods=["GET"])
def api_agent_tasks_history():
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400

    actor_id = str(request.args.get("actor_id", "") or "").strip()
    statuses = _parse_agent_history_filter_tokens(request.args.get("status", ""))
    task_modes = _parse_agent_history_filter_tokens(request.args.get("task_mode", ""))
    kinds = _parse_agent_history_filter_tokens(request.args.get("kind", ""))
    capability_id = str(request.args.get("capability_id", "") or "").strip().lower()
    skill_id = str(request.args.get("skill_id", "") or "").strip().lower()
    trace_id = str(request.args.get("trace_id", "") or "").strip()
    since = str(request.args.get("since", "") or "").strip()
    until = str(request.args.get("until", "") or "").strip()
    sort = str(request.args.get("sort", "desc") or "desc").strip().lower()
    if sort not in {"desc", "asc"}:
        sort = "desc"

    replay_supported = None
    replay_supported_raw = request.args.get("replay_supported", None)
    if replay_supported_raw is not None and str(replay_supported_raw).strip() != "":
        replay_supported = _parse_boolish(replay_supported_raw, default=False)

    try:
        limit = int(request.args.get("limit", 100) or 100)
    except Exception:
        limit = 100
    limit = max(1, min(limit, 1000))

    try:
        offset = int(request.args.get("offset", 0) or 0)
    except Exception:
        offset = 0
    offset = max(offset, 0)

    history = _read_agent_task_history()
    filtered = _filter_agent_task_history(
        history,
        actor_id=actor_id,
        statuses=statuses,
        task_modes=task_modes,
        kinds=kinds,
        capability_id=capability_id,
        skill_id=skill_id,
        trace_id=trace_id,
        replay_supported=replay_supported,
        since=since,
        until=until,
    )
    ordered = filtered if sort == "asc" else list(reversed(filtered))
    total_count = len(ordered)
    items = ordered[offset:offset + limit]
    return jsonify({
        "ok": True,
        "history_file": "data/agent_task_history.json",
        "total_count": total_count,
        "returned_count": len(items),
        "offset": offset,
        "limit": limit,
        "has_more": (offset + len(items)) < total_count,
        "filters": {
            "actor_id": actor_id or None,
            "status": statuses,
            "task_mode": task_modes,
            "kind": kinds,
            "capability_id": capability_id or None,
            "skill_id": skill_id or None,
            "trace_id": trace_id or None,
            "replay_supported": replay_supported,
            "since": since or None,
            "until": until or None,
            "sort": sort,
        },
        "items": items,
    })


@app.route("/api/agent/tasks/<job_id>/export", methods=["POST"])
def api_agent_task_export(job_id: str):
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    payload = request.json or {}
    fmt = str(payload.get("format", "json") or "json").strip().lower()
    if fmt not in {"json", "csv"}:
        return jsonify({"error": "format 仅支持 json/csv"}), 400
    include_logs = _coerce_bool(payload.get("include_logs", True), default=True)
    include_result = _coerce_bool(payload.get("include_result", True), default=True)

    snapshot = _build_agent_task_export_snapshot(
        job_id,
        include_logs=include_logs,
        include_result=include_result,
    )
    if not isinstance(snapshot, dict):
        return jsonify({"error": "agent task/skill 不存在"}), 404

    safe_job_id = str(job_id or "").strip() or "unknown"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _project_data_path(f"agent_task_export_{safe_job_id}_{ts}.{fmt}")
    if out_path is None:
        return jsonify({"error": "项目未加载"}), 400
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        summary = snapshot.get("summary", {}) if isinstance(snapshot.get("summary"), dict) else {}
        fieldnames = [
            "source",
            "job_id",
            "status",
            "kind",
            "task_mode",
            "strategy",
            "actor_type",
            "actor_id",
            "trace_id",
            "capability_ids",
            "skill_ids",
            "total_steps",
            "success_steps",
            "failed_steps",
            "skipped_steps",
            "retry_count",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "estimated_cost_usd",
            "duration_seconds",
            "template_hits",
            "template_hit_count",
            "replay_supported",
            "error",
            "started_at",
            "finished_at",
        ]
        row = {
            "source": str(snapshot.get("source", "") or ""),
            "job_id": str(summary.get("job_id", "") or snapshot.get("job_id", "") or ""),
            "status": str(summary.get("status", "") or snapshot.get("status", "") or ""),
            "kind": str(summary.get("kind", "") or snapshot.get("kind", "") or ""),
            "task_mode": str(summary.get("task_mode", "") or ""),
            "strategy": str(summary.get("strategy", "") or ""),
            "actor_type": str(summary.get("actor_type", "") or ""),
            "actor_id": str(summary.get("actor_id", "") or ""),
            "trace_id": str(summary.get("trace_id", "") or ""),
            "capability_ids": "|".join(str(x) for x in (summary.get("capability_ids", []) if isinstance(summary.get("capability_ids"), list) else [])),
            "skill_ids": "|".join(str(x) for x in (summary.get("skill_ids", []) if isinstance(summary.get("skill_ids"), list) else [])),
            "total_steps": int(summary.get("total_steps", 0) or 0),
            "success_steps": int(summary.get("success_steps", 0) or 0),
            "failed_steps": int(summary.get("failed_steps", 0) or 0),
            "skipped_steps": int(summary.get("skipped_steps", 0) or 0),
            "retry_count": int(summary.get("retry_count", 0) or 0),
            "prompt_tokens": int(summary.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(summary.get("completion_tokens", 0) or 0),
            "total_tokens": int(summary.get("total_tokens", 0) or 0),
            "estimated_cost_usd": float(summary.get("estimated_cost_usd", 0.0) or 0.0),
            "duration_seconds": float(summary.get("duration_seconds", 0.0) or 0.0),
            "template_hits": "|".join(str(x) for x in (summary.get("template_hits", []) if isinstance(summary.get("template_hits"), list) else [])),
            "template_hit_count": int(summary.get("template_hit_count", 0) or 0),
            "replay_supported": bool(summary.get("replay_supported", False)),
            "error": str(summary.get("error", "") or snapshot.get("error", "") or ""),
            "started_at": str(summary.get("started_at", "") or snapshot.get("started_at", "") or ""),
            "finished_at": str(summary.get("finished_at", "") or snapshot.get("finished_at", "") or ""),
        }
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)
        out_path.write_text(buf.getvalue(), encoding="utf-8")

    return jsonify({
        "ok": True,
        "job_id": safe_job_id,
        "source": str(snapshot.get("source", "") or ""),
        "format": fmt,
        "output": str(out_path),
        "history_file": "data/agent_task_history.json",
    })


@app.route("/api/agent/tasks/<job_id>/replay", methods=["POST"])
def api_agent_task_replay(job_id: str):
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    job = _jobs.get(job_id)
    source = "memory"
    replay_spec: Dict[str, Any] = {}
    if isinstance(job, dict) and job.get("kind") in {"agent_task", "agent_skill"}:
        meta = job.get("meta", {}) if isinstance(job.get("meta"), dict) else {}
        replay_spec = _extract_agent_replay_spec(meta.get("replay", {}))
        if not replay_spec:
            history_item = _find_agent_task_history_record(job_id)
            if isinstance(history_item, dict):
                history_replay = _extract_agent_replay_spec(history_item.get("replay", {}))
                if history_replay:
                    source = "history"
                    replay_spec = history_replay
    else:
        source = "history"
        history_item = _find_agent_task_history_record(job_id)
        if not isinstance(history_item, dict):
            return jsonify({"error": "agent task/skill 不存在"}), 404
        replay_spec = _extract_agent_replay_spec(history_item.get("replay", {}))

    req = request.json or {}
    if not isinstance(req, dict):
        req = {}
    payload_overrides = req.get("payload_overrides", {})
    if payload_overrides is None:
        payload_overrides = {}
    if not isinstance(payload_overrides, dict):
        return jsonify({"error": "payload_overrides 必须是对象"}), 400
    context_overrides = req.get("context_overrides", {})
    if context_overrides is None:
        context_overrides = {}
    if not isinstance(context_overrides, dict):
        return jsonify({"error": "context_overrides 必须是对象"}), 400

    endpoint = str(replay_spec.get("endpoint", "") or "").strip()
    method = str(replay_spec.get("method", "POST") or "POST").strip().upper()
    if not endpoint:
        return jsonify({"error": "该任务缺少 replay 元数据（仅支持新任务）"}), 400
    if method not in {"POST", "GET"}:
        return jsonify({"error": f"不支持的 replay method: {method}"}), 400

    base_payload = replay_spec.get("payload", {}) if isinstance(replay_spec.get("payload"), dict) else {}
    final_payload = _deep_merge_dict(base_payload, payload_overrides)
    ctx = _normalize_agent_replay_context(replay_spec.get("request_context", {}))
    for key in ("actor_type", "actor_id", "run_mode", "trace_id", "idempotency_key"):
        if key in context_overrides:
            ctx[key] = str(context_overrides.get(key, "") or "").strip()[:128]
    ctx = _normalize_agent_replay_context(ctx)

    new_trace_id = str(req.get("new_trace_id", "") or "").strip()[:128]
    if new_trace_id:
        ctx["trace_id"] = new_trace_id

    explicit_idem = None
    if "idempotency_key" in req:
        explicit_idem = str(req.get("idempotency_key", "") or "").strip()[:128]
    clear_idempotency = _coerce_bool(req.get("clear_idempotency", True), default=True)
    if explicit_idem is not None:
        ctx["idempotency_key"] = explicit_idem
    elif clear_idempotency:
        ctx["idempotency_key"] = ""

    for key in ("actor_type", "actor_id", "run_mode", "trace_id"):
        val = str(ctx.get(key, "") or "").strip()
        if val:
            final_payload[key] = val
    idem_val = str(ctx.get("idempotency_key", "") or "").strip()
    if idem_val:
        final_payload["idempotency_key"] = idem_val
    else:
        final_payload.pop("idempotency_key", None)

    if "dry_run" in req and "dry_run" not in payload_overrides:
        final_payload["dry_run"] = _coerce_bool(req.get("dry_run", False), default=False)
    final_payload["replay_of_job_id"] = job_id

    invoke_ret = _invoke_agent_primary_call(
        method=method,
        endpoint=endpoint,
        payload=final_payload,
        request_context=ctx,
    )
    status_code = int(invoke_ret.get("status_code", 500) or 500)
    data = invoke_ret.get("data", {}) if isinstance(invoke_ret.get("data"), dict) else {}
    out = {
        "ok": status_code < 400 and bool(data.get("ok", False)),
        "replay_of_job_id": job_id,
        "source": source,
        "target": {
            "method": method,
            "endpoint": endpoint,
        },
        "request_context": ctx,
        "request_payload": final_payload,
        "status_code": status_code,
        "response": data,
    }
    if isinstance(data.get("job_id"), str) and str(data.get("job_id", "")).strip():
        out["new_job_id"] = str(data.get("job_id", "")).strip()
    return jsonify(out), (status_code if status_code >= 400 else 200)


@app.route("/api/agent/observability", methods=["GET"])
def api_agent_observability():
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    actor_id = str(request.args.get("actor_id", "") or "").strip()
    statuses = _parse_agent_history_filter_tokens(request.args.get("status", ""))
    task_modes = _parse_agent_history_filter_tokens(request.args.get("task_mode", ""))
    kinds = _parse_agent_history_filter_tokens(request.args.get("kind", ""))
    capability_id = str(request.args.get("capability_id", "") or "").strip().lower()
    skill_id = str(request.args.get("skill_id", "") or "").strip().lower()
    trace_id = str(request.args.get("trace_id", "") or "").strip()
    since = str(request.args.get("since", "") or "").strip()
    until = str(request.args.get("until", "") or "").strip()
    replay_supported = None
    replay_supported_raw = request.args.get("replay_supported", None)
    if replay_supported_raw is not None and str(replay_supported_raw).strip() != "":
        replay_supported = _parse_boolish(replay_supported_raw, default=False)
    include_items = _parse_boolish(request.args.get("include_items", "false"), default=False)
    try:
        limit = int(request.args.get("limit", 200) or 200)
    except Exception:
        limit = 200
    limit = max(1, min(limit, 2000))
    try:
        top_n = int(request.args.get("top_n", 5) or 5)
    except Exception:
        top_n = 5
    top_n = max(1, min(top_n, 20))

    history = _read_agent_task_history()
    filtered = _filter_agent_task_history(
        history,
        actor_id=actor_id,
        statuses=statuses,
        task_modes=task_modes,
        kinds=kinds,
        capability_id=capability_id,
        skill_id=skill_id,
        trace_id=trace_id,
        replay_supported=replay_supported,
        since=since,
        until=until,
    )
    picked = filtered[-limit:] if filtered else []
    summary = _build_agent_observability_summary(picked, top_n=top_n)
    return jsonify({
        "ok": True,
        "actor_id": actor_id,
        "window_limit": limit,
        "top_n": top_n,
        "history_count": len(filtered),
        "window_count": len(picked),
        "summary": summary,
        "history_file": "data/agent_task_history.json",
        "filters": {
            "actor_id": actor_id or None,
            "status": statuses,
            "task_mode": task_modes,
            "kind": kinds,
            "capability_id": capability_id or None,
            "skill_id": skill_id or None,
            "trace_id": trace_id or None,
            "replay_supported": replay_supported,
            "since": since or None,
            "until": until or None,
        },
        "items": list(reversed(picked)) if include_items else [],
    })


@app.route("/api/agent/observability/export", methods=["POST"])
def api_agent_observability_export():
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    payload = request.json or {}
    actor_id = str(payload.get("actor_id", "") or "").strip()
    statuses = _parse_agent_history_filter_tokens(payload.get("status", ""))
    task_modes = _parse_agent_history_filter_tokens(payload.get("task_mode", ""))
    kinds = _parse_agent_history_filter_tokens(payload.get("kind", ""))
    capability_id = str(payload.get("capability_id", "") or "").strip().lower()
    skill_id = str(payload.get("skill_id", "") or "").strip().lower()
    trace_id = str(payload.get("trace_id", "") or "").strip()
    since = str(payload.get("since", "") or "").strip()
    until = str(payload.get("until", "") or "").strip()
    replay_supported = None
    replay_supported_raw = payload.get("replay_supported", None)
    if replay_supported_raw is not None and str(replay_supported_raw).strip() != "":
        replay_supported = _parse_boolish(replay_supported_raw, default=False)
    fmt = str(payload.get("format", "json") or "json").strip().lower()
    if fmt not in {"json", "csv"}:
        return jsonify({"error": "format 仅支持 json/csv"}), 400
    try:
        limit = int(payload.get("limit", 500) or 500)
    except Exception:
        limit = 500
    limit = max(1, min(limit, 5000))
    try:
        top_n = int(payload.get("top_n", 5) or 5)
    except Exception:
        top_n = 5
    top_n = max(1, min(top_n, 20))

    history = _read_agent_task_history()
    filtered = _filter_agent_task_history(
        history,
        actor_id=actor_id,
        statuses=statuses,
        task_modes=task_modes,
        kinds=kinds,
        capability_id=capability_id,
        skill_id=skill_id,
        trace_id=trace_id,
        replay_supported=replay_supported,
        since=since,
        until=until,
    )
    picked = filtered[-limit:] if filtered else []
    summary = _build_agent_observability_summary(picked, top_n=top_n)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "json" if fmt == "json" else "csv"
    out_path = _project_data_path(f"agent_observability_{ts}.{ext}")
    if out_path is None:
        return jsonify({"error": "项目未加载"}), 400
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        body = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "actor_id": actor_id,
            "window_limit": limit,
            "window_count": len(picked),
            "filters": {
                "actor_id": actor_id or None,
                "status": statuses,
                "task_mode": task_modes,
                "kind": kinds,
                "capability_id": capability_id or None,
                "skill_id": skill_id or None,
                "trace_id": trace_id or None,
                "replay_supported": replay_supported,
                "since": since or None,
                "until": until or None,
            },
            "summary": summary,
            "items": list(reversed(picked)),
        }
        out_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        fieldnames = [
            "job_id",
            "status",
            "kind",
            "task_mode",
            "strategy",
            "actor_type",
            "actor_id",
            "trace_id",
            "capability_ids",
            "skill_ids",
            "total_steps",
            "success_steps",
            "failed_steps",
            "skipped_steps",
            "retry_count",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "estimated_cost_usd",
            "duration_seconds",
            "template_hits",
            "template_hit_count",
            "error",
            "started_at",
            "finished_at",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for item in reversed(picked):
            if not isinstance(item, dict):
                continue
            row = dict(item)
            for key in ("capability_ids", "skill_ids", "template_hits"):
                val = row.get(key)
                row[key] = "|".join(str(x) for x in val) if isinstance(val, list) else ""
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        out_path.write_text(buf.getvalue(), encoding="utf-8")

    return jsonify({
        "ok": True,
        "format": fmt,
        "output": str(out_path),
        "history_file": "data/agent_task_history.json",
        "window_count": len(picked),
        "filters": {
            "actor_id": actor_id or None,
            "status": statuses,
            "task_mode": task_modes,
            "kind": kinds,
            "capability_id": capability_id or None,
            "skill_id": skill_id or None,
            "trace_id": trace_id or None,
            "replay_supported": replay_supported,
            "since": since or None,
            "until": until or None,
        },
        "summary": summary,
    })


@app.route("/api/agent/skills/invoke", methods=["POST"])
def api_agent_skills_invoke():
    payload = request.json or {}
    request_ctx = _parse_request_context()
    skill_id = str(payload.get("skill_id", "") or "").strip()
    if not skill_id:
        return jsonify({"error": "skill_id 不能为空"}), 400

    skill_spec = _AGENT_SKILL_REGISTRY.get(skill_id)
    if not isinstance(skill_spec, dict):
        return jsonify({
            "error": f"不支持的 skill_id: {skill_id}",
            "available_skills": [x.get("skill_id") for x in _list_agent_skills()],
        }), 400

    input_payload = payload.get("input", {})
    if input_payload is None:
        input_payload = {}
    if not isinstance(input_payload, dict):
        return jsonify({"error": "input 必须是对象"}), 400
    input_payload = _apply_agent_capability_input_defaults(
        str(skill_spec.get("capability_id", "") or ""),
        input_payload,
        default_input=skill_spec.get("default_input", {}),
    )

    retry_policy = _normalize_skill_retry_policy(payload.get("retry_policy", {}))
    timeout_seconds = _normalize_skill_timeout_seconds(payload.get("timeout_seconds", 120), default=120.0)

    method = str(skill_spec.get("method", "POST") or "POST").strip().upper()
    endpoint = str(skill_spec.get("endpoint", "") or "").strip()
    if not endpoint:
        return jsonify({"error": f"skill 配置缺少 endpoint: {skill_id}"}), 500

    job_id = str(uuid.uuid4())[:8]
    invoke_id = str(uuid.uuid4())[:8]

    def _do_invoke():
        _jobs[job_id]["progress"] = 8
        _jobs[job_id]["log"].append(f"[AgentSkill] invoke_id={invoke_id} skill_id={skill_id}")
        _jobs[job_id]["log"].append(f"[AgentSkill] 调用 {method} {endpoint}")
        ret = _execute_agent_skill(
            skill_id=skill_id,
            input_payload=input_payload,
            retry_policy=retry_policy,
            timeout_seconds=timeout_seconds,
            request_context=request_ctx,
            logger=lambda msg: _jobs[job_id]["log"].append(f"[AgentSkill] {msg}"),
        )
        _jobs[job_id]["progress"] = 95
        ret["invoke_id"] = invoke_id
        return ret

    _run_in_bg(
        job_id,
        _do_invoke,
        kind="agent_skill",
        job_meta={
            "actor_type": str(request_ctx.get("actor_type", "") or ""),
            "actor_id": str(request_ctx.get("actor_id", "") or ""),
            "trace_id": str(request_ctx.get("trace_id", "") or ""),
            "task_mode": "skill_invoke",
            "skill_id": skill_id,
            "capability_id": str(skill_spec.get("capability_id", "") or ""),
            "template_hits": _extract_template_ids_from_value(payload),
            "replay": {
                "method": "POST",
                "endpoint": "/api/agent/skills/invoke",
                "payload": deepcopy(payload),
                "request_context": deepcopy(request_ctx),
            },
        },
    )
    return jsonify({
        "ok": True,
        "job_id": job_id,
        "invoke_id": invoke_id,
        "skill_id": skill_id,
        "skill_name": str(skill_spec.get("name", "") or ""),
        "capability_id": str(skill_spec.get("capability_id", "") or ""),
        "primary_call": {
            "method": method,
            "endpoint": endpoint,
        },
        "retry_policy": retry_policy,
        "timeout_seconds": timeout_seconds,
        "status_endpoint": f"/api/agent/tasks/{job_id}",
    })


@app.route("/api/agent/templates", methods=["GET"])
def api_agent_templates_list():
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    ctx = _parse_request_context()
    capability_id = str(request.args.get("capability_id", "") or "").strip()
    scope = str(request.args.get("scope", "") or "").strip().lower()
    actor_id = str(request.args.get("actor_id", "") or "").strip() or ctx.get("actor_id", "")
    include_system = _parse_boolish(request.args.get("include_system", "true"), default=True)
    resolve = _parse_boolish(request.args.get("resolve", "true"), default=True)
    templates = _list_agent_templates(
        capability_id=capability_id,
        scope=scope,
        actor_id=actor_id,
        include_system=include_system,
        resolve=resolve,
    )
    return jsonify({
        "ok": True,
        "templates": templates,
        "count": len(templates),
        "filters": {
            "capability_id": capability_id,
            "scope": scope or None,
            "actor_id": actor_id or None,
            "include_system": include_system,
            "resolve": resolve,
        },
    })


@app.route("/api/agent/templates", methods=["POST"])
def api_agent_templates_upsert():
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    payload = request.json or {}
    ctx = _parse_request_context()
    default_scope = str(payload.get("scope", "") or "").strip().lower()
    if not default_scope:
        default_scope = "agent" if ctx.get("actor_type") == "agent" else "project"
    try:
        tmpl = _normalize_agent_template_payload(
            payload,
            scope_default=default_scope,
            actor_id_default=ctx.get("actor_id", ""),
        )
    except Exception as exc:
        return jsonify({"error": f"模板保存失败: {exc}"}), 400

    scope = str(tmpl.get("scope", "")).lower()
    if scope == "system":
        return jsonify({"error": "system scope 模板是只读内置模板，不能写入"}), 400

    store = _read_agent_template_store()
    candidate_store = deepcopy(store)
    if scope == "project":
        bucket = candidate_store.setdefault("project", {})
        if not isinstance(bucket, dict):
            bucket = {}
            candidate_store["project"] = bucket
        bucket[tmpl["template_id"]] = tmpl
    else:
        actor_id = str(tmpl.get("actor_id", "") or "").strip()
        if not actor_id:
            return jsonify({"error": "agent scope 需要 actor_id"}), 400
        agent_store = candidate_store.setdefault("agent", {})
        if not isinstance(agent_store, dict):
            agent_store = {}
            candidate_store["agent"] = agent_store
        actor_bucket = agent_store.setdefault(actor_id, {})
        if not isinstance(actor_bucket, dict):
            actor_bucket = {}
            agent_store[actor_id] = actor_bucket
        actor_bucket[tmpl["template_id"]] = tmpl

    base_error = _validate_agent_template_base_reference(tmpl, store=candidate_store)
    if base_error:
        return jsonify({"error": f"模板保存失败: {base_error}"}), 400

    saved = _save_agent_template_store(candidate_store)
    _ = saved  # keep for future diagnostics
    templates = _list_agent_templates(
        capability_id=str(tmpl.get("capability_id", "") or ""),
        scope=scope,
        actor_id=str(tmpl.get("actor_id", "") or ""),
        include_system=(scope == "system"),
        resolve=True,
    )
    return jsonify({
        "ok": True,
        "template": tmpl,
        "templates": templates,
    })


@app.route("/api/agent/templates/<template_id>", methods=["DELETE"])
def api_agent_templates_delete(template_id: str):
    if _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    ctx = _parse_request_context()
    payload = request.get_json(silent=True) if request.method == "DELETE" else {}
    if not isinstance(payload, dict):
        payload = {}

    tid = _normalize_agent_template_id(template_id)
    if not tid:
        return jsonify({"error": "template_id 无效"}), 400
    scope = str(request.args.get("scope", payload.get("scope", "")) or "").strip().lower()
    if scope not in {"project", "agent", "system"}:
        return jsonify({"error": "scope 不能为空，且仅支持 project/agent/system"}), 400
    if scope == "system":
        return jsonify({"error": "system scope 模板是只读内置模板，不能删除"}), 400

    store = _read_agent_template_store()
    if scope == "project":
        bucket = store.get("project", {})
        if not isinstance(bucket, dict) or tid not in bucket:
            return jsonify({"error": f"模板不存在: {tid}"}), 404
        deleted = bucket.pop(tid, None)
        store["project"] = bucket
    else:
        actor_id = str(request.args.get("actor_id", payload.get("actor_id", "")) or "").strip()
        if not actor_id:
            actor_id = str(ctx.get("actor_id", "") or "").strip()
        if not actor_id:
            return jsonify({"error": "agent scope 删除需要 actor_id"}), 400
        agent_store = store.get("agent", {})
        actor_bucket = agent_store.get(actor_id, {}) if isinstance(agent_store, dict) else {}
        if not isinstance(actor_bucket, dict) or tid not in actor_bucket:
            return jsonify({"error": f"模板不存在: {tid}"}), 404
        deleted = actor_bucket.pop(tid, None)
        if isinstance(agent_store, dict):
            if actor_bucket:
                agent_store[actor_id] = actor_bucket
            else:
                agent_store.pop(actor_id, None)
            store["agent"] = agent_store

    _save_agent_template_store(store)
    return jsonify({"ok": True, "deleted": deleted})


@app.route("/api/workflows/catalog", methods=["GET"])
def api_workflows_catalog():
    ctx = _parse_request_context()
    catalog = _build_custom_workflow_catalog()
    return jsonify(
        {
            "ok": True,
            "catalog": catalog,
            "count": len(catalog),
            "request_context": ctx,
        }
    )


@app.route("/api/workflows", methods=["GET"])
def api_workflows_list():
    ctx = _parse_request_context()
    workflow_id = _normalize_agent_template_id(request.args.get("workflow_id", ""))
    include_steps = _parse_boolish(request.args.get("include_steps", "true"), default=True)
    with _custom_workflow_lock:
        store = _read_custom_workflow_store()
    items = list(store.values())
    items.sort(key=lambda x: str(x.get("updated_at", "") or ""), reverse=True)
    if workflow_id:
        items = [x for x in items if str(x.get("workflow_id", "") or "") == workflow_id]
    if not include_steps:
        for item in items:
            item.pop("steps", None)
    return jsonify(
        {
            "ok": True,
            "workflows": items,
            "count": len(items),
            "persisted": _project_dir is not None,
            "request_context": ctx,
        }
    )


@app.route("/api/workflows", methods=["POST"])
def api_workflows_upsert():
    payload = request.json or {}
    ctx = _parse_request_context()
    try:
        workflow_id = _normalize_agent_template_id(payload.get("workflow_id", ""))
        with _custom_workflow_lock:
            store = _read_custom_workflow_store()
            existing = store.get(workflow_id) if workflow_id else None
            workflow = _normalize_custom_workflow_payload(payload, existing=existing)
            old_id = workflow_id if workflow_id and workflow_id in store else ""
            store[workflow["workflow_id"]] = workflow
            if old_id and old_id != workflow["workflow_id"]:
                store.pop(old_id, None)
            saved = _save_custom_workflow_store(store)
    except Exception as exc:
        return jsonify({"error": f"workflow 保存失败: {exc}"}), 400
    return jsonify(
        {
            "ok": True,
            "workflow": workflow,
            "count": len(saved),
            "persisted": _project_dir is not None,
            "request_context": ctx,
        }
    )


@app.route("/api/workflows/plan", methods=["POST"])
def api_workflows_plan():
    payload = request.json or {}
    ctx = _parse_request_context()
    dry_run = _coerce_bool(payload.get("dry_run", True), default=True)
    try:
        workflow = _resolve_custom_workflow_from_payload(payload)
        plan = _build_custom_workflow_plan(workflow=workflow, payload=payload, dry_run=dry_run)
    except Exception as exc:
        return jsonify({"error": f"workflow 规划失败: {exc}"}), 400
    return jsonify(
        {
            "ok": True,
            "workflow": {
                "workflow_id": plan.get("workflow_id"),
                "name": plan.get("name"),
                "description": plan.get("description"),
            },
            "plan": plan,
            "plan_summary": {
                "workflow_id": plan.get("workflow_id"),
                "total_steps": plan.get("total_steps", 0),
                "dry_run": dry_run,
                "start_step_id": (plan.get("graph", {}) or {}).get("start_step_id", ""),
                "edge_count": (plan.get("graph", {}) or {}).get("edge_count", 0),
                "has_cycle": bool((plan.get("graph", {}) or {}).get("has_cycle", False)),
                "enabled_steps": sum(
                    1
                    for step in (plan.get("steps", []) if isinstance(plan.get("steps"), list) else [])
                    if _coerce_bool(step.get("enabled", True), default=True)
                ),
            },
            "request_context": ctx,
        }
    )


@app.route("/api/workflows/run", methods=["POST"])
def api_workflows_run():
    payload = request.json or {}
    ctx = _parse_request_context()
    try:
        workflow = _resolve_custom_workflow_from_payload(payload)
        ret = _start_custom_workflow_run(
            workflow=workflow,
            payload=payload,
            request_context=ctx,
            source="api/workflows/run",
        )
    except Exception as exc:
        return jsonify({"error": f"workflow 执行失败: {exc}"}), 400
    ret["request_context"] = ctx
    return jsonify(ret)


@app.route("/api/workflows/runs", methods=["GET"])
def api_workflows_runs():
    ctx = _parse_request_context()
    workflow_id = _normalize_agent_template_id(request.args.get("workflow_id", ""))
    include_steps = _parse_boolish(request.args.get("include_steps", "false"), default=False)
    try:
        limit = int(request.args.get("limit", "50") or "50")
    except Exception:
        limit = 50
    try:
        offset = int(request.args.get("offset", "0") or "0")
    except Exception:
        offset = 0
    limit = max(1, min(limit, 200))
    offset = max(offset, 0)

    with _custom_workflow_lock:
        runs = _read_custom_workflow_runs()
    if workflow_id:
        runs = [x for x in runs if str(x.get("workflow_id", "") or "") == workflow_id]
    ordered = list(reversed(runs))
    page = ordered[offset : offset + limit]
    has_more = (offset + limit) < len(ordered)
    if not include_steps:
        for item in page:
            item.pop("steps", None)
            item.pop("workflow", None)
            item.pop("plan", None)
    return jsonify(
        {
            "ok": True,
            "items": page,
            "total_count": len(ordered),
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "request_context": ctx,
        }
    )


@app.route("/api/workflows/runs/<run_id>", methods=["GET"])
def api_workflows_run_detail(run_id: str):
    ctx = _parse_request_context()
    record = _find_custom_workflow_run(run_id)
    if not isinstance(record, dict):
        return jsonify({"error": f"run 不存在: {run_id}"}), 404
    return jsonify({"ok": True, "run": record, "request_context": ctx})


@app.route("/api/workflows/runs/<run_id>/rerun", methods=["POST"])
def api_workflows_run_rerun(run_id: str):
    payload = request.json or {}
    ctx = _parse_request_context()
    base = _find_custom_workflow_run(run_id)
    if not isinstance(base, dict):
        return jsonify({"error": f"run 不存在: {run_id}"}), 404

    workflow_raw = base.get("workflow", {})
    if not isinstance(workflow_raw, dict):
        workflow_raw = {}
    if not workflow_raw:
        workflow_id = _normalize_agent_template_id(base.get("workflow_id", ""))
        with _custom_workflow_lock:
            workflow_raw = _read_custom_workflow_store().get(workflow_id, {})
    if not isinstance(workflow_raw, dict) or not workflow_raw:
        return jsonify({"error": "历史 run 缺少可复用 workflow 定义"}), 400

    rerun_failed_only = _coerce_bool(payload.get("rerun_failed_only", False), default=False)
    failed_step_ids = [
        _normalize_agent_template_id(step.get("step_id", ""))
        for step in (base.get("steps", []) if isinstance(base.get("steps"), list) else [])
        if str(step.get("status", "") or "").strip().lower() == "error"
    ]
    failed_step_ids = [sid for sid in failed_step_ids if sid]
    try:
        workflow = _normalize_custom_workflow_payload(workflow_raw, existing=workflow_raw)
    except Exception as exc:
        return jsonify({"error": f"workflow 解析失败: {exc}"}), 400

    if rerun_failed_only:
        try:
            workflow = _build_failed_only_workflow_subset(workflow=workflow, base_run=base)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    run_payload = deepcopy(payload)
    run_payload["workflow"] = workflow
    included_step_ids = [
        _normalize_agent_template_id(step.get("step_id", ""))
        for step in (workflow.get("steps", []) if isinstance(workflow.get("steps"), list) else [])
    ]
    included_step_ids = [sid for sid in included_step_ids if sid]
    run_payload["rerun_context"] = {
        "mode": "failed_with_dependencies" if rerun_failed_only else "full",
        "source_run_id": run_id,
        "failed_step_ids": failed_step_ids,
        "included_step_ids": included_step_ids,
        "start_step_id": _normalize_agent_template_id(workflow.get("start_step_id", "")),
    }
    if "input" not in run_payload:
        plan_raw = base.get("plan", {})
        if isinstance(plan_raw, dict) and isinstance(plan_raw.get("input"), dict):
            run_payload["input"] = deepcopy(plan_raw.get("input", {}))
    try:
        ret = _start_custom_workflow_run(
            workflow=workflow,
            payload=run_payload,
            request_context=ctx,
            source=f"api/workflows/runs/{run_id}/rerun",
        )
    except Exception as exc:
        return jsonify({"error": f"workflow 重跑失败: {exc}"}), 400
    ret["source_run_id"] = run_id
    ret["rerun_context"] = deepcopy(run_payload.get("rerun_context", {}))
    ret["request_context"] = ctx
    return jsonify(ret)


@app.route("/api/workflows/<workflow_id>", methods=["DELETE"])
def api_workflows_delete(workflow_id: str):
    ctx = _parse_request_context()
    workflow_key = _normalize_agent_template_id(workflow_id)
    if not workflow_key:
        return jsonify({"error": "workflow_id 无效"}), 400
    with _custom_workflow_lock:
        store = _read_custom_workflow_store()
        deleted = store.pop(workflow_key, None)
        if deleted is None:
            return jsonify({"error": f"workflow 不存在: {workflow_key}"}), 404
        _save_custom_workflow_store(store)
    return jsonify({"ok": True, "deleted": deleted, "request_context": ctx})


@app.route("/api/capabilities/topic_library", methods=["GET"])
def api_topic_library_list():
    payload = _request_json_any_method()
    input_mode = _parse_capability_input_mode(
        request.args.get("input_mode", payload.get("input_mode", "project")),
        default="project",
    )
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    from modules.capabilities.topic_library import list_topics, search_topics

    query = str(request.args.get("q", payload.get("q", "")) or "").strip()
    category = str(request.args.get("category", payload.get("category", "")) or "").strip() or None
    tags_raw = str(request.args.get("tags", payload.get("tags", "")) or "").strip()
    tags = [x.strip() for x in tags_raw.replace("，", ",").split(",") if x.strip()] if tags_raw else None
    include_disabled = _parse_boolish(
        request.args.get("include_disabled", payload.get("include_disabled", "false")),
        default=False,
    )
    try:
        limit = int(request.args.get("limit", payload.get("limit", "60")) or "60")
    except Exception:
        limit = 60
    limit = max(1, min(limit, 300))

    if input_mode == "project":
        db_path = _project_data_path("topic_library.db")
        assert db_path is not None
        if query or category or tags:
            items = search_topics(str(db_path), query=query, category=category, tags=tags, limit=limit)
            if not include_disabled:
                items = [x for x in items if x.get("enabled", True)]
        else:
            items = list_topics(str(db_path), enabled_only=not include_disabled, limit=limit)
        return jsonify({"ok": True, "input_mode": input_mode, "topics": items, "db_path": str(db_path)})

    topics_raw = payload.get("topics", [])
    topic_items = [x for x in topics_raw if isinstance(x, dict)]
    query_l = query.lower()
    matched: List[Dict[str, Any]] = []
    for item in topic_items:
        enabled = bool(item.get("enabled", True))
        if not include_disabled and not enabled:
            continue
        if category and str(item.get("category", "") or "").strip().lower() != category.lower():
            continue
        item_tags = item.get("tags", [])
        item_tags_norm = []
        if isinstance(item_tags, list):
            item_tags_norm = [str(x).strip().lower() for x in item_tags if str(x).strip()]
        if tags:
            wanted = [x.lower() for x in tags]
            if not all(tag in item_tags_norm for tag in wanted):
                continue
        if query_l:
            hay = " ".join(
                [
                    str(item.get("slug", "") or ""),
                    str(item.get("title", "") or ""),
                    str(item.get("category", "") or ""),
                    " ".join(item_tags_norm),
                ]
            ).lower()
            if query_l not in hay:
                continue
        matched.append(item)
        if len(matched) >= limit:
            break
    return jsonify({"ok": True, "input_mode": input_mode, "topics": matched, "db_path": None})


@app.route("/api/capabilities/topic_library", methods=["POST"])
def api_topic_library_upsert():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    title = str(payload.get("title", "") or "").strip()
    if not title:
        return jsonify({"error": "title 不能为空"}), 400

    from modules.capabilities.topic_library import TopicTemplate, upsert_topic

    slug = str(payload.get("slug", "") or "").strip() or _slugify(title)
    topic = TopicTemplate(
        slug=slug,
        title=title,
        category=str(payload.get("category", "travel") or "travel"),
        audience=str(payload.get("audience", "general") or "general"),
        hook_style=str(payload.get("hook_style", "story") or "story"),
        outline_template=str(payload.get("outline_template", "") or ""),
        tags=payload.get("tags", []) if isinstance(payload.get("tags"), list) else [],
        enabled=bool(payload.get("enabled", True)),
    )
    topic_dict = {
        "slug": topic.slug,
        "title": topic.title,
        "category": topic.category,
        "audience": topic.audience,
        "hook_style": topic.hook_style,
        "outline_template": topic.outline_template,
        "tags": list(topic.tags),
        "enabled": bool(topic.enabled),
    }
    if input_mode == "project":
        db_path = _project_data_path("topic_library.db")
        assert db_path is not None
        upsert_topic(str(db_path), topic)
        return jsonify({"ok": True, "input_mode": input_mode, "slug": slug, "topic": topic_dict, "db_path": str(db_path)})

    topics_raw = payload.get("topics", [])
    topic_items = [dict(x) for x in topics_raw if isinstance(x, dict)]
    replaced = False
    for idx, item in enumerate(topic_items):
        if str(item.get("slug", "") or "").strip() == slug:
            topic_items[idx] = topic_dict
            replaced = True
            break
    if not replaced:
        topic_items.append(topic_dict)
    return jsonify({"ok": True, "input_mode": input_mode, "slug": slug, "topic": topic_dict, "topics": topic_items, "db_path": None})


@app.route("/api/capabilities/topic_library/bootstrap", methods=["POST"])
def api_topic_library_bootstrap():
    materials = _read_project_json("materials.json", fallback={})
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    if isinstance(payload.get("materials"), dict):
        materials = payload.get("materials")
    if not isinstance(materials, dict) or not materials:
        if input_mode == "project":
            return jsonify({"error": "data/materials.json 不存在或为空"}), 400
        return jsonify({"error": "inline 模式缺少 materials"}), 400

    from modules.capabilities.topic_library import TopicTemplate, upsert_topic

    db_path = _project_data_path("topic_library.db") if input_mode == "project" else None
    created = 0
    seen = set()
    generated: List[Dict[str, Any]] = []
    for _, vdata in materials.items():
        sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic"), dict) else {}
        setting = str(sem.get("setting", "") or "").strip() or "旅行场景"
        activity = str(sem.get("activity", "") or "").strip() or "探索"
        mood = str(sem.get("mood", "") or "").strip() or "真实"
        title = f"{setting}·{activity}高光"
        slug = _slugify(f"{setting}-{activity}")
        if slug in seen:
            continue
        seen.add(slug)
        outline = f"开场给出{setting}强画面，中段呈现{activity}过程，结尾落在{mood}情绪变化。"
        topic = TopicTemplate(
            slug=slug,
            title=title,
            category="travel",
            audience="short_video",
            hook_style="story",
            outline_template=outline,
            tags=[setting, activity, mood],
            enabled=True,
        )
        if db_path is not None:
            upsert_topic(str(db_path), topic)
        generated.append(
            {
                "slug": topic.slug,
                "title": topic.title,
                "category": topic.category,
                "audience": topic.audience,
                "hook_style": topic.hook_style,
                "outline_template": topic.outline_template,
                "tags": list(topic.tags),
                "enabled": bool(topic.enabled),
            }
        )
        created += 1
        if created >= 30:
            break

    return jsonify(
        {
            "ok": True,
            "input_mode": input_mode,
            "created": created,
            "topics": generated,
            "db_path": str(db_path) if db_path is not None else None,
        }
    )


@app.route("/api/capabilities/topic_copy/draft", methods=["POST"])
def api_topic_copy_draft():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    slug = str(payload.get("slug", "") or "").strip()
    target_duration_s = int(payload.get("target_duration_s", 60) or 60)

    from modules.capabilities.topic_library import TopicTemplate, get_topic, list_topics
    from modules.capabilities.topic_copy import build_copy_payload

    topic_dict = payload.get("topic") if isinstance(payload.get("topic"), dict) else None
    if input_mode == "project":
        db_path = _project_data_path("topic_library.db")
        assert db_path is not None
        if not topic_dict:
            topic_dict = get_topic(str(db_path), slug) if slug else None
        if not topic_dict:
            defaults = list_topics(str(db_path), enabled_only=True, limit=1)
            if defaults:
                topic_dict = defaults[0]
    else:
        topic_pool = payload.get("topics", [])
        if not topic_dict and isinstance(topic_pool, list):
            if slug:
                topic_dict = next(
                    (x for x in topic_pool if isinstance(x, dict) and str(x.get("slug", "") or "").strip() == slug),
                    None,
                )
            if not topic_dict:
                topic_dict = next((x for x in topic_pool if isinstance(x, dict)), None)
    if not topic_dict:
        return jsonify({"error": "未找到 topic，请先创建或传正确 slug"}), 404

    topic = TopicTemplate(
        slug=topic_dict.get("slug", slug),
        title=topic_dict.get("title", "Untitled"),
        category=topic_dict.get("category", "travel"),
        audience=topic_dict.get("audience", "general"),
        hook_style=topic_dict.get("hook_style", "story"),
        outline_template=topic_dict.get("outline_template", ""),
        tags=topic_dict.get("tags", []),
        enabled=bool(topic_dict.get("enabled", True)),
    )
    semantics_raw = payload.get("material_semantics", payload.get("semantics"))
    if isinstance(semantics_raw, list):
        semantics = [x for x in semantics_raw if isinstance(x, dict)]
    else:
        materials = _coerce_materials_input(payload, input_mode=input_mode)
        semantics = _extract_material_semantics(materials if isinstance(materials, dict) else {})
    draft = build_copy_payload(topic, semantics, target_duration_s=target_duration_s)
    out_path = _project_data_path("topic_copy_draft.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "draft": draft, "output": str(out_path) if out_path else None})


def _extract_text_rough_subtitle_spans(script: Dict) -> List[Dict]:
    out: List[Dict] = []
    subtitles = script.get("subtitles", []) if isinstance(script, dict) else []
    idx = 0
    for sub in subtitles:
        if not isinstance(sub, dict):
            continue
        text = str(sub.get("cn_text") or sub.get("text") or "").strip()
        if not text:
            continue
        try:
            st = float(sub.get("start_time"))
            et = float(sub.get("end_time"))
        except Exception:
            continue
        if et <= st:
            continue
        idx += 1
        out.append(
            {
                "index": idx,
                "start": round(st, 3),
                "end": round(et, 3),
                "duration_s": round(et - st, 3),
                "text": text,
            }
        )
    return out


@app.route("/api/capabilities/text_rough_cut/source", methods=["GET"])
def api_text_rough_cut_source():
    payload = _request_json_any_method()
    input_mode = _parse_capability_input_mode(
        request.args.get("input_mode", payload.get("input_mode", "project")),
        default="project",
    )
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400

    script = _coerce_script_input(payload, input_mode=input_mode)
    if not script and input_mode == "inline":
        return jsonify({"error": "inline 模式缺少 script/subtitles"}), 400
    spans = _extract_text_rough_subtitle_spans(script)
    out_path = _project_data_path("text_rough_source.json") if input_mode == "project" else None
    if out_path is not None and _project_dir is not None:
        out_path.write_text(json.dumps({"spans": spans}, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(
        {
            "ok": True,
            "input_mode": input_mode,
            "spans": spans,
            "total": len(spans),
            "output": str(out_path) if out_path else None,
        }
    )


@app.route("/api/capabilities/text_rough_cut/plan", methods=["POST"])
def api_text_rough_cut_plan():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    removed = payload.get("removed_phrases", None)
    target_duration_raw = payload.get("target_duration_s", 15)
    merge_gap_raw = payload.get("merge_gap_s", 0.15)
    keep_indexes_raw = payload.get("keep_span_indexes", None)
    drop_indexes_raw = payload.get("drop_span_indexes", None)
    apply_removed_phrases = bool(payload.get("apply_removed_phrases", True))

    from modules.capabilities.text_rough_cut import (
        TranscriptSpan,
        build_text_rough_cut_plan,
        coerce_span_indexes,
    )

    span_items: List[Dict[str, Any]] = []
    span_items_raw = payload.get("spans", [])
    if isinstance(span_items_raw, list) and span_items_raw:
        for idx, item in enumerate(span_items_raw, start=1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("cn_text") or "").strip()
            if not text:
                continue
            try:
                start = float(item.get("start", item.get("start_time", 0.0)))
                end = float(item.get("end", item.get("end_time", 0.0)))
            except Exception:
                continue
            if end <= start:
                continue
            span_items.append({"index": idx, "start": round(start, 3), "end": round(end, 3), "text": text})
    if not span_items:
        script = _coerce_script_input(payload, input_mode=input_mode)
        span_items = _extract_text_rough_subtitle_spans(script)
    if not span_items and input_mode == "inline":
        return jsonify({"error": "缺少可用于粗剪的字幕分段（spans/script/subtitles）"}), 400

    spans = [
        TranscriptSpan(
            start=float(item.get("start", 0.0)),
            end=float(item.get("end", 0.0)),
            text=str(item.get("text", "") or ""),
            confidence=1.0,
        )
        for item in span_items
    ]
    if isinstance(removed, str):
        removed = [x.strip() for x in removed.replace("，", ",").split(",") if x.strip()]
    elif not isinstance(removed, list):
        removed = None

    if target_duration_raw in {None, ""}:
        target_duration_s = None
    else:
        try:
            target_duration_s = float(target_duration_raw)
        except Exception:
            target_duration_s = 15.0
    try:
        merge_gap_s = float(merge_gap_raw)
    except Exception:
        merge_gap_s = 0.15
    keep_indexes = coerce_span_indexes(keep_indexes_raw, max_index=len(spans))
    drop_indexes = coerce_span_indexes(drop_indexes_raw, max_index=len(spans))

    plan = build_text_rough_cut_plan(
        spans=spans,
        removed_phrases=removed,
        target_duration_s=target_duration_s,
        merge_gap_s=merge_gap_s,
        keep_span_indexes=keep_indexes,
        drop_span_indexes=drop_indexes,
        apply_removed_phrases=apply_removed_phrases,
    )
    out_path = _project_data_path("text_rough_plan.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "plan": plan, "output": str(out_path) if out_path else None})


@app.route("/api/capabilities/short_clip/plan", methods=["POST"])
def api_short_clip_plan():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    target_duration_s = float(payload.get("target_duration_s", 30) or 30)
    max_clips = int(payload.get("max_clips", 8) or 8)

    from modules.capabilities.short_clip import HighlightCandidate, highlights_to_timeline, pick_highlights

    candidates: List[HighlightCandidate] = []
    candidate_items = payload.get("candidates", [])
    if isinstance(candidate_items, list) and candidate_items:
        for item in candidate_items:
            if not isinstance(item, dict):
                continue
            try:
                start = float(item.get("start", item.get("start_time", 0.0)))
                end = float(item.get("end", item.get("end_time", 0.0)))
            except Exception:
                continue
            if end <= start:
                continue
            try:
                score = float(item.get("score", item.get("highlight_score", 0.55)) or 0.55)
            except Exception:
                score = 0.55
            candidates.append(
                HighlightCandidate(
                    start=start,
                    end=end,
                    score=score,
                    reason=str(item.get("reason", item.get("scene_description", "")) or ""),
                )
            )
    if not candidates:
        script = _coerce_script_input(payload, input_mode=input_mode)
        cursor = 0.0
        for idx, clip in enumerate(script.get("clips", []), start=1):
            if not isinstance(clip, dict):
                continue
            start = cursor
            try:
                src_start = float(clip.get("source_start", 0) or 0)
            except Exception:
                src_start = 0.0
            src_end = clip.get("source_end")
            if src_end is None:
                try:
                    src_end = src_start + float(clip.get("duration", 5) or 5)
                except Exception:
                    src_end = src_start + 5.0
            try:
                duration = max(float(src_end) - src_start, 0.1)
            except Exception:
                duration = 5.0
            end = start + duration
            cursor = end
            try:
                score = float(clip.get("highlight_score", 0.55) or 0.55)
            except Exception:
                score = 0.55
            if idx == 1:
                score += 0.12
            if clip.get("has_face"):
                score += 0.08
            candidates.append(HighlightCandidate(start=start, end=end, score=score, reason=str(clip.get("scene_description", ""))))
    if not candidates:
        return jsonify({"error": "缺少候选片段（candidates/script/clips）"}), 400

    picked = pick_highlights(candidates, target_duration_s=target_duration_s, max_clips=max_clips)
    timeline = highlights_to_timeline(picked)
    out_path = _project_data_path("short_clip_plan.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "plan": timeline, "output": str(out_path) if out_path else None})


@app.route("/api/capabilities/refinement/plan", methods=["POST"])
def api_refinement_plan():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        # 保持既有兼容：project 模式下仅在有项目时落盘，不阻断规划结果返回
        input_mode = "inline"
    from modules.capabilities.refinement import build_refine_payload

    plan = build_refine_payload(
        style=str(payload.get("style", "travel_story") or "travel_story"),
        editor=str(payload.get("editor", "internal_ffmpeg") or "internal_ffmpeg"),
        quality=str(payload.get("quality", "high") or "high"),
    )
    if input_mode == "project" and _project_dir is not None and bool(payload.get("store_result", True)):
        out_path = _project_data_path("refinement_plan.json")
        if out_path is not None:
            out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "plan": plan})


@app.route("/api/capabilities/refinement/handoff", methods=["POST"])
def api_refinement_handoff():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    editor = str(payload.get("editor", "finalcut") or "finalcut").strip().lower()
    title = str(payload.get("title", "VideoEditer Timeline") or "VideoEditer Timeline").strip()
    fps = int(payload.get("fps", 30) or 30)

    from modules.capabilities.nle_handoff import create_nle_handoff

    script = _coerce_script_input(payload, input_mode=input_mode)
    if not script or not script.get("clips"):
        return jsonify({"error": "缺少脚本片段，请先生成 script_draft/script_matched"}), 400
    materials = _coerce_materials_input(payload, input_mode=input_mode)
    if not isinstance(materials, dict) or not materials:
        return jsonify({"error": "缺少 materials.json"}), 400

    output_dir_raw = str(payload.get("output_dir", "") or "").strip()
    if output_dir_raw:
        out_dir = _resolve_path_with_base(output_dir_raw, base_dir=_capability_base_dir(input_mode))
    elif input_mode == "project" and _project_dir is not None:
        out_dir = _project_dir / "data" / "nle_handoff" / editor
    else:
        out_dir = Path(tempfile.mkdtemp(prefix=f"videoeditor_nle_handoff_{editor}_"))
    try:
        ret = create_nle_handoff(
            script=script,
            materials=materials,
            output_dir=str(out_dir),
            editor=editor,
            title=title,
            fps=fps,
        )
    except Exception as exc:
        return jsonify({"error": f"NLE 交接包生成失败: {exc}"}), 500
    return jsonify({"ok": True, "input_mode": input_mode, "handoff": ret})


@app.route("/api/capabilities/refinement/execute", methods=["POST"])
def api_refinement_execute():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    editor = str(payload.get("editor", "finalcut") or "finalcut").strip().lower()
    title = str(payload.get("title", "VideoEditer Timeline") or "VideoEditer Timeline").strip()
    fps = int(payload.get("fps", 30) or 30)
    launch = bool(payload.get("launch", True))
    app_name = str(payload.get("app_name", "") or "").strip()
    timeout_seconds = float(payload.get("timeout_seconds", 20) or 20)

    from modules.capabilities.nle_handoff import create_nle_handoff, launch_nle_handoff

    script = _coerce_script_input(payload, input_mode=input_mode)
    if not script or not script.get("clips"):
        return jsonify({"error": "缺少脚本片段，请先生成 script_draft/script_matched"}), 400
    materials = _coerce_materials_input(payload, input_mode=input_mode)
    if not isinstance(materials, dict) or not materials:
        return jsonify({"error": "缺少 materials.json"}), 400

    output_dir_raw = str(payload.get("output_dir", "") or "").strip()
    if output_dir_raw:
        out_dir = _resolve_path_with_base(output_dir_raw, base_dir=_capability_base_dir(input_mode))
    elif input_mode == "project" and _project_dir is not None:
        out_dir = _project_dir / "data" / "nle_handoff" / editor
    else:
        out_dir = Path(tempfile.mkdtemp(prefix=f"videoeditor_nle_execute_{editor}_"))
    try:
        handoff = create_nle_handoff(
            script=script,
            materials=materials,
            output_dir=str(out_dir),
            editor=editor,
            title=title,
            fps=fps,
        )
    except Exception as exc:
        return jsonify({"error": f"NLE 交接包生成失败: {exc}"}), 500

    launch_result = None
    if launch:
        try:
            launch_result = launch_nle_handoff(
                handoff,
                app_name=app_name,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            return jsonify({"error": f"NLE 启动失败: {exc}", "handoff": handoff}), 500
        if launch_result.get("status") != "done":
            return jsonify({"error": "NLE 启动失败", "handoff": handoff, "launch": launch_result}), 500

    output = {
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "handoff": handoff,
        "launch": launch_result,
    }
    out_path = _project_data_path("refinement_execute_last.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(
        {
            "ok": True,
            "input_mode": input_mode,
            "handoff": handoff,
            "launch": launch_result,
            "output": str(out_path) if out_path else None,
        }
    )


@app.route("/api/capabilities/refinement/collect_master", methods=["POST"])
def api_refinement_collect_master():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    base_dir = _capability_base_dir(input_mode)
    editor = str(payload.get("editor", "finalcut") or "finalcut").strip().lower()
    source_video_raw = str(payload.get("source_video", "") or "").strip()
    output_name = str(payload.get("output_name", "final.mp4") or "final.mp4").strip() or "final.mp4"
    copy_mode = str(payload.get("copy_mode", "copy") or "copy").strip().lower()
    if copy_mode not in {"copy", "move"}:
        copy_mode = "copy"

    from modules.capabilities.nle_handoff import collect_nle_master_video, find_latest_video_candidate

    source_video = None
    if source_video_raw:
        source_video = _resolve_path_with_base(source_video_raw, base_dir=base_dir)
    else:
        search_dirs = _parse_str_list(payload.get("search_dirs"))
        if not search_dirs:
            if input_mode == "project" and _project_dir is not None:
                search_dirs = [
                    str(_project_dir / "data" / "nle_handoff" / editor),
                    str(_project_dir / "data" / "nle_handoff"),
                    str(_project_dir / "output"),
                ]
            else:
                search_dirs = [
                    str(base_dir / "data" / "nle_handoff" / editor),
                    str(base_dir / "data" / "nle_handoff"),
                    str(base_dir / "output"),
                ]
        resolved_dirs = []
        for item in search_dirs:
            p = _resolve_path_with_base(item, base_dir=base_dir)
            resolved_dirs.append(str(p))
        guessed = find_latest_video_candidate(resolved_dirs)
        if guessed:
            source_video = Path(guessed)
        else:
            return jsonify({"error": "未找到可导回的视频，请手动选择 source_video"}), 404

    output_dir_raw = str(payload.get("output_dir", "") or "").strip()
    if output_dir_raw:
        output_dir = _resolve_path_with_base(output_dir_raw, base_dir=base_dir)
    elif input_mode == "project" and _project_dir is not None:
        output_dir = _project_dir / "output"
    else:
        output_dir = (base_dir / "output").resolve()

    try:
        result = collect_nle_master_video(
            source_video=str(source_video),
            output_dir=str(output_dir),
            output_name=output_name,
            copy_mode=copy_mode,
        )
    except Exception as exc:
        return jsonify({"error": f"导回成片失败: {exc}"}), 400

    record = {
        "editor": editor,
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "source_video": result.get("source_video"),
        "output_video": result.get("output_video"),
        "mode": result.get("mode"),
        "size": result.get("size"),
    }
    if input_mode == "project" and _ws is not None:
        nle_history = _ws.data.get("nle_master_history", [])
        if not isinstance(nle_history, list):
            nle_history = []
        nle_history.append(record)
        _ws.data["nle_master_history"] = nle_history[-50:]
        _ws.save()

    out_path = _project_data_path("refinement_collect_last.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(
        {
            "ok": True,
            "input_mode": input_mode,
            "collect": result,
            "record": record,
            "output": str(out_path) if out_path else None,
        }
    )


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


def _build_subtitle_translator(payload: Dict[str, Any], warnings: List[str]):
    use_llm = bool(payload.get("use_llm", False))
    if not use_llm:
        return None, {"enabled": False, "provider": "", "model": "", "fallback": True}

    ai = _load_ai_settings()
    provider = str(payload.get("llm_provider") or ai.get("provider") or "").strip().lower()
    model = str(payload.get("llm_model") or ai.get("ai_model") or "").strip()
    base_url = str(payload.get("llm_base_url") or ai.get("ai_base_url") or "").strip()
    api_key = str(payload.get("llm_api_key") or "").strip()
    if not api_key:
        if provider == "anthropic":
            api_key = str(ai.get("anthropic_api_key") or "").strip()
        else:
            api_key = str(ai.get("openai_api_key") or "").strip()
    if not provider:
        provider = "openai" if api_key else ""
    if not api_key:
        warnings.append("字幕翻译 use_llm=true 但未配置 API Key，已降级为规则翻译。")
        return None, {"enabled": True, "provider": provider, "model": model, "fallback": True}

    client = AIClient(
        provider=provider or None,
        api_key=api_key or None,
        base_url=base_url or None,
        model=model or None,
        temperature=0.2,
        max_tokens=240,
    )

    warn_once = {"emitted": False}

    def _translator(text: str, target_lang: str) -> str:
        target = "English" if str(target_lang).lower().startswith("en") else "中文"
        prompt = (
            f"请将以下字幕翻译为 {target}。只输出翻译结果，不要解释，不要加引号。\\n"
            f"字幕：{text}"
        )
        try:
            result = client.chat(
                messages=[{"role": "user", "content": prompt}],
                system="你是字幕翻译助手，优先口语化、自然、简短。",
            )
            return str(result or "").strip()
        except Exception as exc:
            if not warn_once["emitted"]:
                warnings.append(f"字幕翻译 LLM 调用失败，已降级规则翻译: {exc}")
                warn_once["emitted"] = True
            from modules.capabilities.subtitle_calibration import _fallback_translate  # lazy import

            return _fallback_translate(text, "en" if str(target_lang).lower().startswith("en") else "zh")

    return _translator, {
        "enabled": True,
        "provider": str(client.provider or ""),
        "model": str(client.model or ""),
        "fallback": False,
    }


@app.route("/api/capabilities/subtitle_calibration/plan", methods=["POST"])
def api_subtitle_calibration_plan():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    subtitles = payload.get("subtitles", [])
    if not isinstance(subtitles, list):
        subtitles = []
    if input_mode == "project" and not subtitles:
        subtitles = _extract_subtitles_from_script(_read_script_json())
    if not subtitles:
        return jsonify({"error": "缺少 subtitles，input_mode=project 时可自动读取脚本字幕"}), 400

    mode = str(payload.get("mode", "text_only") or "text_only").strip().lower()
    if mode not in {"text_only", "timeline_align"}:
        mode = "text_only"
    translation = str(payload.get("translation", "off") or "off").strip().lower()
    if translation not in {"off", "zh2en", "en2zh", "bilingual"}:
        translation = "off"

    from modules.capabilities.subtitle_calibration import calibrate_subtitles

    preview = calibrate_subtitles(
        subtitles=subtitles,
        mode=mode,
        translation="off",
        source_audio=str(payload.get("source_audio", "") or "").strip(),
        translator=None,
    )
    plan = {
        "mode": mode,
        "translation": translation,
        "total_subtitles": int(preview.get("quality_report", {}).get("total_subtitles", 0) or 0),
        "timeline_change_estimate": int(preview.get("quality_report", {}).get("timeline_changed_count", 0) or 0),
        "overlap_before": int(preview.get("quality_report", {}).get("overlap_before", 0) or 0),
        "overlap_after": int(preview.get("quality_report", {}).get("overlap_after", 0) or 0),
    }
    return jsonify({"ok": True, "input_mode": input_mode, "plan": plan, "preview": preview})


@app.route("/api/capabilities/subtitle_calibration/run", methods=["POST"])
def api_subtitle_calibration_run():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    subtitles = payload.get("subtitles", [])
    if not isinstance(subtitles, list):
        subtitles = []
    if input_mode == "project" and not subtitles:
        subtitles = _extract_subtitles_from_script(_read_script_json())
    if not subtitles:
        return jsonify({"error": "缺少 subtitles，input_mode=project 时可自动读取脚本字幕"}), 400

    mode = str(payload.get("mode", "text_only") or "text_only").strip().lower()
    if mode not in {"text_only", "timeline_align"}:
        mode = "text_only"
    translation = str(payload.get("translation", "off") or "off").strip().lower()
    if translation not in {"off", "zh2en", "en2zh", "bilingual"}:
        translation = "off"
    source_audio = str(payload.get("source_audio", "") or "").strip()

    from modules.capabilities.subtitle_calibration import calibrate_subtitles

    warnings: List[str] = []
    translator, llm_meta = _build_subtitle_translator(payload, warnings)
    result = calibrate_subtitles(
        subtitles=subtitles,
        mode=mode,
        translation=translation,
        source_audio=source_audio,
        translator=translator,
    )
    if _project_dir is not None and bool(payload.get("store_result", True)):
        out_path = _project_data_path("subtitle_calibration_last.json")
        if out_path is not None:
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(
        {
            "ok": True,
            "input_mode": input_mode,
            "llm": llm_meta,
            "result": result,
            "warnings": warnings,
        }
    )


@app.route("/api/capabilities/image_semantic/analyze", methods=["POST"])
def api_image_semantic_analyze():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "inline"), default="inline")
    image_paths_raw = payload.get("image_paths", payload.get("images", payload.get("paths", [])))
    if isinstance(image_paths_raw, str):
        image_paths = [x.strip() for x in image_paths_raw.replace("，", ",").split(",") if x.strip()]
    elif isinstance(image_paths_raw, list):
        image_paths = [str(x).strip() for x in image_paths_raw if str(x).strip()]
    else:
        image_paths = []
    if input_mode == "project" and not image_paths:
        latest = _library.search_assets(query="", limit=20, offset=0, retrieval_mode="hybrid", media_type="image")
        image_paths = [str(x.get("path") or "").strip() for x in latest if isinstance(x, dict) and str(x.get("path") or "").strip()]

    from modules.capabilities.image_semantic import analyze_images

    result = analyze_images(
        image_paths,
        library=_library,
        max_images=int(payload.get("max_images", 200) or 200),
        retrieval_mode=str(payload.get("retrieval_mode", "hybrid") or "hybrid"),
        auto_ingest=bool(payload.get("auto_ingest", True)),
    )
    if _project_dir is not None and bool(payload.get("store_result", True)):
        out = _project_data_path("image_semantic_analyze_last.json")
        if out is not None:
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "result": result})


@app.route("/api/capabilities/image_semantic/search", methods=["POST"])
def api_image_semantic_search():
    payload = request.json or {}
    query = str(payload.get("query", "") or "").strip()
    from modules.capabilities.image_semantic import search_images

    result = search_images(
        query,
        library=_library,
        limit=int(payload.get("limit", 30) or 30),
        offset=int(payload.get("offset", 0) or 0),
        retrieval_mode=str(payload.get("retrieval_mode", "hybrid") or "hybrid"),
    )
    if _project_dir is not None and bool(payload.get("store_result", True)):
        out = _project_data_path("image_semantic_search_last.json")
        if out is not None:
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "result": result})


@app.route("/api/capabilities/article_expand/generate", methods=["POST"])
def api_article_expand_generate():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "inline"), default="inline")
    source_text = str(payload.get("source_text", payload.get("text", "")) or "").strip()
    key_points = payload.get("key_points", payload.get("points", []))
    if input_mode == "project" and not source_text:
        script_blocks = _script_to_text_blocks(_read_script_json())
        source_text = str(script_blocks.get("script_text", "") or "").strip()
        if not key_points:
            key_points = script_blocks.get("voiceover_text", "")

    warnings: List[str] = []
    use_llm = bool(payload.get("use_llm", False))
    text_generator = None
    llm_meta = {"enabled": False, "provider": "", "model": "", "fallback": True}
    if use_llm:
        ai = _load_ai_settings()
        provider = str(payload.get("llm_provider") or ai.get("provider") or "").strip().lower()
        model = str(payload.get("llm_model") or ai.get("ai_model") or "").strip()
        base_url = str(payload.get("llm_base_url") or ai.get("ai_base_url") or "").strip()
        api_key = str(payload.get("llm_api_key") or "").strip()
        if not api_key:
            if provider == "anthropic":
                api_key = str(ai.get("anthropic_api_key") or "").strip()
            else:
                api_key = str(ai.get("openai_api_key") or "").strip()
        if api_key:
            client = AIClient(
                provider=provider or None,
                api_key=api_key,
                base_url=base_url or None,
                model=model or None,
                temperature=0.4,
                max_tokens=800,
            )
            llm_meta = {"enabled": True, "provider": str(client.provider or ""), "model": str(client.model or ""), "fallback": False}

            warn_once = {"emitted": False}

            def _gen(field: str, prompt: str) -> str:
                try:
                    return str(
                        client.chat(
                            messages=[{"role": "user", "content": prompt}],
                            system=f"你是微信公众号文章编辑助手，当前字段={field}。",
                        )
                        or ""
                    ).strip()
                except Exception as exc:
                    if not warn_once["emitted"]:
                        warnings.append(f"article_expand LLM 调用失败，已降级规则生成: {exc}")
                        warn_once["emitted"] = True
                    return ""

            text_generator = _gen
        else:
            warnings.append("article_expand use_llm=true 但未配置 API Key，已降级规则生成。")
            llm_meta = {"enabled": True, "provider": provider, "model": model, "fallback": True}

    from modules.capabilities.article_expand import generate_article_expansion

    result = generate_article_expansion(
        source_text=source_text,
        key_points=key_points,
        tone=str(payload.get("tone", "professional") or "professional"),
        length_target=int(payload.get("length_target", 1200) or 1200),
        title_count=int(payload.get("title_count", 5) or 5),
        text_generator=text_generator,
    )
    if _project_dir is not None and bool(payload.get("store_result", True)):
        out = _project_data_path("article_expand_last.json")
        if out is not None:
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "llm": llm_meta, "result": result, "warnings": warnings})


@app.route("/api/capabilities/content_publish/platforms", methods=["GET"])
def api_content_publish_platforms():
    from modules.capabilities.content_publish import list_publish_platforms

    return jsonify({"ok": True, **list_publish_platforms()})


@app.route("/api/capabilities/content_publish/session/bootstrap", methods=["POST"])
def api_content_publish_session_bootstrap():
    payload = request.json or {}
    if _project_dir is None and _parse_capability_input_mode(payload.get("input_mode", "project"), default="project") == "project":
        return jsonify({"error": "项目未加载"}), 400

    from modules.capabilities.content_publish import bootstrap_publish_session

    session = bootstrap_publish_session(
        actor_id=str(payload.get("actor_id", "") or "").strip(),
        session_id=str(payload.get("session_id", "") or "").strip(),
        authenticated=bool(payload.get("authenticated", False)),
        expires_in_minutes=int(payload.get("expires_in_minutes", 120) or 120),
    )
    sessions = _read_content_publish_sessions() if _project_dir is not None else {}
    sessions[str(session.get("session_id"))] = session
    if _project_dir is not None:
        _save_content_publish_sessions(sessions)
    return jsonify({"ok": True, "session": session})


@app.route("/api/capabilities/content_publish/plan", methods=["POST"])
def api_content_publish_plan():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400

    from modules.capabilities.content_publish import build_publish_plan

    platforms = _parse_platforms(payload.get("platforms", payload.get("platform_ids", [])))
    content_payload = _resolve_content_publish_content(payload, input_mode=input_mode)
    sessions = _read_content_publish_sessions() if _project_dir is not None else {}
    session_id = str(payload.get("session_id", "") or "").strip()
    session = sessions.get(session_id, {}) if session_id else {}
    plan = build_publish_plan(
        content=content_payload,
        platform_ids=platforms,
        platform_content_type=str(payload.get("platform_content_type", "video_post") or "video_post"),
        dry_run=bool(payload.get("dry_run", True)),
        session=session,
        humanization=payload.get("humanization", {}) if isinstance(payload.get("humanization"), dict) else {},
    )
    plan_record = {
        "plan_id": str(uuid.uuid4())[:10],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_mode": input_mode,
        **plan,
    }
    if _project_dir is not None:
        out = _project_data_path("content_publish_plan_last.json")
        if out is not None:
            out.write_text(json.dumps(plan_record, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "plan": plan_record})


@app.route("/api/capabilities/content_publish/run", methods=["POST"])
def api_content_publish_run():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400

    from modules.capabilities.content_publish import run_publish_plan

    plan = payload.get("plan", {}) if isinstance(payload.get("plan"), dict) else {}
    if not plan:
        plan = _read_project_json("content_publish_plan_last.json", fallback={}) if _project_dir is not None else {}
    if not isinstance(plan, dict) or not plan:
        return jsonify({"error": "缺少 plan，请先调用 /api/capabilities/content_publish/plan"}), 400

    sessions = _read_content_publish_sessions() if _project_dir is not None else {}
    session_id = str(payload.get("session_id", "") or "").strip()
    if not session_id:
        session_id = str(plan.get("session", {}).get("session_id", "") if isinstance(plan.get("session"), dict) else "")
    session = sessions.get(session_id, {}) if session_id else {}

    result = run_publish_plan(
        plan=plan,
        session=session,
        dry_run=bool(payload.get("dry_run", plan.get("dry_run", False))),
        rerun_failed_only=bool(payload.get("rerun_failed_only", False)),
        random_seed=payload.get("random_seed", 7),
    )

    run_record = {
        "run_id": str(uuid.uuid4())[:10],
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "input_mode": input_mode,
        "plan_id": str(plan.get("plan_id", "") or ""),
        "plan": plan,
        "result": result,
    }
    history = _read_content_publish_history() if _project_dir is not None else []
    history.append(run_record)
    history = history[-300:]
    if _project_dir is not None:
        _save_content_publish_history(history)
        out = _project_data_path("content_publish_run_last.json")
        if out is not None:
            out.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")
    waiting_auth = str(result.get("status", "")).lower() == "waiting_auth"
    return jsonify(
        {
            "ok": True,
            "run": run_record,
            "state": result.get("status"),
            "auth_required": waiting_auth,
            "auth_hint": "会话过期，请扫码续登后重试" if waiting_auth else "",
        }
    )


@app.route("/api/capabilities/content_publish/rerun", methods=["POST"])
def api_content_publish_rerun():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400

    run_id = str(payload.get("run_id", "") or "").strip()
    if not run_id:
        return jsonify({"error": "run_id 不能为空"}), 400

    history = _read_content_publish_history() if _project_dir is not None else []
    base = next((x for x in reversed(history) if str(x.get("run_id", "") or "") == run_id), None)
    if not isinstance(base, dict):
        return jsonify({"error": f"未找到 run_id={run_id}"}), 404

    from modules.capabilities.content_publish import run_publish_plan

    plan = base.get("plan", {}) if isinstance(base.get("plan"), dict) else {}
    if not plan:
        return jsonify({"error": f"run_id={run_id} 缺少可复跑 plan"}), 400

    sessions = _read_content_publish_sessions() if _project_dir is not None else {}
    session_id = str(payload.get("session_id", "") or "").strip()
    if not session_id:
        session_id = str(plan.get("session", {}).get("session_id", "") if isinstance(plan.get("session"), dict) else "")
    session = sessions.get(session_id, {}) if session_id else {}

    result = run_publish_plan(
        plan=plan,
        session=session,
        dry_run=bool(payload.get("dry_run", False)),
        rerun_failed_only=bool(payload.get("rerun_failed_only", True)),
        random_seed=payload.get("random_seed", 7),
    )
    run_record = {
        "run_id": str(uuid.uuid4())[:10],
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "input_mode": input_mode,
        "plan_id": str(plan.get("plan_id", "") or ""),
        "plan": plan,
        "result": result,
        "rerun_from": run_id,
    }
    history.append(run_record)
    history = history[-300:]
    if _project_dir is not None:
        _save_content_publish_history(history)
        out = _project_data_path("content_publish_run_last.json")
        if out is not None:
            out.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")

    waiting_auth = str(result.get("status", "")).lower() == "waiting_auth"
    return jsonify(
        {
            "ok": True,
            "run": run_record,
            "state": result.get("status"),
            "auth_required": waiting_auth,
            "auth_hint": "会话过期，请扫码续登后重试" if waiting_auth else "",
            "rerun_from": run_id,
        }
    )


@app.route("/api/capabilities/social_export/profiles", methods=["GET"])
def api_social_export_profiles():
    from modules.capabilities.social_export import list_export_profiles
    payload = _request_json_any_method()
    input_mode = _parse_capability_input_mode(
        request.args.get("input_mode", payload.get("input_mode", "project")),
        default="project",
    )
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)
    profiles = list_export_profiles(profile_overrides=templates)
    custom_ids = set(templates.keys())
    for item in profiles:
        pid = str(item.get("platform_id", "") or "")
        item["is_custom"] = pid in custom_ids
    return jsonify({"ok": True, "input_mode": input_mode, "profiles": profiles})


@app.route("/api/capabilities/social_export/specs", methods=["GET"])
def api_social_export_specs():
    from modules.capabilities.social_export import list_export_specs
    payload = _request_json_any_method()
    input_mode = _parse_capability_input_mode(
        request.args.get("input_mode", payload.get("input_mode", "project")),
        default="project",
    )
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)
    specs = list_export_specs(profile_overrides=templates)
    return jsonify({"ok": True, "input_mode": input_mode, "specs": specs})


@app.route("/api/capabilities/social_export/templates", methods=["GET"])
def api_social_export_templates_list():
    payload = _request_json_any_method()
    input_mode = _parse_capability_input_mode(
        request.args.get("input_mode", payload.get("input_mode", "project")),
        default="project",
    )
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)
    items = list(templates.values())
    return jsonify({"ok": True, "input_mode": input_mode, "templates": items})


@app.route("/api/capabilities/social_export/templates", methods=["POST"])
def api_social_export_templates_upsert():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    try:
        tmpl = _normalize_export_template_payload(payload)
    except Exception as exc:
        return jsonify({"error": f"模板保存失败: {exc}"}), 400
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)
    templates[tmpl["platform_id"]] = tmpl
    saved = _save_social_export_templates(templates) if input_mode == "project" else templates
    return jsonify({"ok": True, "input_mode": input_mode, "template": tmpl, "templates": list(saved.values())})


@app.route("/api/capabilities/social_export/templates/<template_id>", methods=["DELETE"])
def api_social_export_templates_delete(template_id: str):
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(
        request.args.get("input_mode", payload.get("input_mode", "project")),
        default="project",
    )
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    pid = _normalize_export_template_id(template_id)
    if not pid:
        return jsonify({"error": "template_id 无效"}), 400
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)
    if pid not in templates:
        return jsonify({"error": f"模板不存在: {pid}"}), 404
    templates.pop(pid, None)
    saved = _save_social_export_templates(templates) if input_mode == "project" else templates
    return jsonify({"ok": True, "input_mode": input_mode, "deleted": pid, "templates": list(saved.values())})


@app.route("/api/capabilities/social_export/history", methods=["GET"])
def api_social_export_history():
    payload = _request_json_any_method()
    input_mode = _parse_capability_input_mode(
        request.args.get("input_mode", payload.get("input_mode", "project")),
        default="project",
    )
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    try:
        limit = int(request.args.get("limit", payload.get("limit", "30")) or "30")
    except Exception:
        limit = 30
    limit = max(1, min(limit, 200))

    history_raw = payload.get("history", [])
    if input_mode == "project":
        history = _get_social_export_history()
    else:
        history = [x for x in history_raw if isinstance(x, dict)] if isinstance(history_raw, list) else []
    items = list(reversed(history[-limit:])) if history else []
    return jsonify({"ok": True, "input_mode": input_mode, "history": items})


@app.route("/api/capabilities/social_export/validate_source", methods=["POST"])
def api_social_export_validate_source():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    base_dir = _capability_base_dir(input_mode)
    from modules.capabilities.social_export import validate_source_for_export

    input_video_raw = str(payload.get("input_video", "") or "").strip()
    if input_video_raw:
        input_video = _resolve_path_with_base(input_video_raw, base_dir=base_dir)
    else:
        if input_mode == "project":
            input_video = _default_master_video_path()
            if input_video is None:
                return jsonify({"error": "找不到可校验的母版视频"}), 404
        else:
            return jsonify({"error": "inline 模式需要 input_video"}), 400
    if not input_video.exists():
        return jsonify({"error": f"输入视频不存在: {input_video}"}), 404

    platforms = _parse_platforms(payload.get("platforms"))
    if not platforms:
        platforms = ["douyin", "xiaohongshu", "tiktok"]
    strict_duration_limit = bool(payload.get("strict_duration_limit", True))
    ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)
    try:
        report = validate_source_for_export(
            input_video=str(input_video),
            platform_ids=platforms,
            strict_duration_limit=strict_duration_limit,
            ffprobe_bin=ffprobe_bin,
            profile_overrides=templates,
        )
    except Exception as exc:
        return jsonify({"error": f"源视频校验失败: {exc}"}), 400

    out_path = _project_data_path("social_export_validation_last.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(
        {
            "ok": True,
            "input_mode": input_mode,
            "report": report,
            "output": str(out_path) if out_path else None,
        }
    )


@app.route("/api/capabilities/social_export/plan", methods=["POST"])
def api_social_export_plan():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    base_dir = _capability_base_dir(input_mode)
    from modules.capabilities.social_export import build_export_plan

    input_video_raw = str(payload.get("input_video", "") or "").strip()
    if input_video_raw:
        input_video = _resolve_path_with_base(input_video_raw, base_dir=base_dir)
    else:
        if input_mode == "project":
            input_video = _default_master_video_path()
            if input_video is None:
                return jsonify({"error": "找不到可导出的母版视频"}), 404
        else:
            return jsonify({"error": "inline 模式需要 input_video"}), 400
    if not input_video.exists():
        return jsonify({"error": f"输入视频不存在: {input_video}"}), 404

    quality = str(payload.get("quality", "high") or "high").strip().lower()
    strict_duration_limit = bool(payload.get("strict_duration_limit", True))
    ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
    platforms = _parse_platforms(payload.get("platforms"))
    if not platforms:
        platforms = ["douyin", "xiaohongshu", "tiktok"]
    output_dir_raw = str(payload.get("output_dir", "") or "").strip()
    output_dir = (
        (base_dir / "output" / "social_exports")
        if not output_dir_raw
        else _resolve_path_with_base(output_dir_raw, base_dir=base_dir)
    )
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)

    try:
        plan = build_export_plan(
            input_video=str(input_video),
            output_dir=str(output_dir),
            platform_ids=platforms,
            quality=quality,
            ffmpeg_bin=str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg"),
            ffprobe_bin=ffprobe_bin,
            strict_duration_limit=strict_duration_limit,
            profile_overrides=templates,
        )
    except Exception as exc:
        return jsonify({"error": f"导出计划生成失败: {exc}"}), 400

    plan_path = _project_data_path("social_export_plan.json") if input_mode == "project" else None
    if plan_path is not None and bool(payload.get("store_result", True)):
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(
        {
            "ok": True,
            "input_mode": input_mode,
            "plan": plan,
            "output": str(plan_path) if plan_path else None,
        }
    )


@app.route("/api/capabilities/social_export/run", methods=["POST"])
def api_social_export_run():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再执行导出",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409

    base_dir = _capability_base_dir(input_mode)
    timeout_seconds = float(payload.get("timeout_seconds", 3600) or 3600)
    ffmpeg_bin = str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg")
    ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
    strict_duration_limit = bool(payload.get("strict_duration_limit", True))
    quality = str(payload.get("quality", "high") or "high").strip().lower()
    platforms = _parse_platforms(payload.get("platforms"))
    output_dir_raw = str(payload.get("output_dir", "") or "").strip()
    input_video_raw = str(payload.get("input_video", "") or "").strip()
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)

    job_id = str(uuid.uuid4())[:8]
    runner = _build_social_export_runner(
        input_video_raw=input_video_raw,
        output_dir_raw=output_dir_raw,
        platforms=platforms,
        quality=quality,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
        strict_duration_limit=strict_duration_limit,
        timeout_seconds=timeout_seconds,
        job_id=job_id,
        profile_overrides=templates,
        input_mode=input_mode,
        base_dir=base_dir,
        persist_history=(input_mode == "project"),
    )
    _run_in_bg(job_id, runner, kind="social_export")
    return jsonify({"ok": True, "input_mode": input_mode, "job_id": job_id})


@app.route("/api/capabilities/social_export/rerun", methods=["POST"])
def api_social_export_rerun():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再执行导出",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409

    batch_id = str(payload.get("batch_id", "") or "").strip()
    record = payload.get("batch") if isinstance(payload.get("batch"), dict) else None
    if record is None and batch_id:
        history = _get_social_export_history() if input_mode == "project" else []
        record = next((x for x in reversed(history) if str(x.get("batch_id", "")) == batch_id), None)
    if record is None:
        if input_mode == "inline":
            return jsonify({"error": "inline rerun 需要 batch（或切换 project 模式并提供 batch_id）"}), 400
        if not batch_id:
            return jsonify({"error": "batch_id 不能为空"}), 400
        return jsonify({"error": f"未找到批次: {batch_id}"}), 404

    base_dir = _capability_base_dir(input_mode)
    input_video_raw = str(payload.get("input_video", record.get("input_video", "")) or "")
    output_dir_raw = str(payload.get("output_dir", record.get("output_dir", "")) or "")
    quality = str(payload.get("quality", record.get("quality", "high")) or "high").strip().lower()
    strict_duration_limit = bool(payload.get("strict_duration_limit", record.get("strict_duration_limit", True)))
    ffmpeg_bin = str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg")
    ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
    timeout_seconds = float(payload.get("timeout_seconds", 3600) or 3600)
    platforms = _parse_platforms(payload.get("platforms", record.get("platforms", [])))
    templates = _coerce_social_export_overrides(payload, input_mode=input_mode)

    job_id = str(uuid.uuid4())[:8]
    runner = _build_social_export_runner(
        input_video_raw=input_video_raw,
        output_dir_raw=output_dir_raw,
        platforms=platforms,
        quality=quality,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
        strict_duration_limit=strict_duration_limit,
        timeout_seconds=timeout_seconds,
        job_id=job_id,
        profile_overrides=templates,
        input_mode=input_mode,
        base_dir=base_dir,
        persist_history=(input_mode == "project"),
    )
    _run_in_bg(job_id, runner, kind="social_export")
    return jsonify({"ok": True, "input_mode": input_mode, "job_id": job_id, "rerun_from": batch_id or record.get("batch_id", "")})


@app.route("/api/capabilities/audio_voice/plan", methods=["POST"])
def api_audio_voice_plan():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    mood = str(payload.get("mood", "travel_story") or "travel_story")

    from modules.capabilities.audio_voice import build_audio_capability_payload

    script = _coerce_script_input(payload, input_mode=input_mode)
    if input_mode == "inline" and not script:
        return jsonify({"error": "inline 模式缺少 script/clips/subtitles"}), 400
    plan = build_audio_capability_payload(script, mood=mood)
    out_path = _project_data_path("audio_voice_plan.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "plan": plan, "output": str(out_path) if out_path else None})


@app.route("/api/capabilities/audio_voice/pick_bgm", methods=["POST"])
def api_audio_voice_pick_bgm():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    base_dir = _capability_base_dir(input_mode)
    mood = str(payload.get("mood", "travel_story") or "travel_story")
    provider = str(payload.get("bgm_provider", "local_library") or "local_library")
    api_key = str(payload.get("bgm_api_key", "") or "").strip()
    endpoint = str(payload.get("bgm_endpoint", "") or "").strip()
    bgm_download = bool(payload.get("bgm_download", True))
    bgm_strict_schema = bool(payload.get("bgm_strict_schema", False))
    bgm_cache_enabled = bool(payload.get("bgm_cache_enabled", True))
    bgm_force_refresh = bool(payload.get("bgm_force_refresh", False))
    bgm_cache_max_age_days = float(payload.get("bgm_cache_max_age_days", 0) or 0)
    bgm_cache_max_age_seconds = max(bgm_cache_max_age_days, 0.0) * 86400.0
    ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
    target_duration_s = payload.get("target_duration_s", None)
    try:
        target_duration_s = float(target_duration_s) if target_duration_s is not None else None
    except Exception:
        target_duration_s = None

    custom_dir = str(payload.get("bgm_library_dir", "") or "").strip()
    custom_dirs = _parse_str_list(payload.get("bgm_library_dirs", []))
    if input_mode == "project":
        library_dirs = _default_bgm_library_dirs(custom_dir=custom_dir, custom_dirs=custom_dirs)
        output_dir = _default_bgm_output_dir(str(payload.get("bgm_output_dir", "") or "").strip())
    else:
        library_dirs = []
        for raw in [custom_dir, *custom_dirs]:
            text = str(raw or "").strip()
            if not text:
                continue
            resolved = _resolve_path_with_base(text, base_dir=base_dir)
            if resolved.exists() and resolved.is_dir():
                library_dirs.append(resolved)
        bgm_output_raw = str(payload.get("bgm_output_dir", "") or "").strip()
        output_dir = (
            _resolve_path_with_base(bgm_output_raw, base_dir=base_dir)
            if bgm_output_raw
            else (base_dir / "data" / "audio_voice" / "bgm")
        )

    from modules.capabilities.audio_voice import pick_bgm

    try:
        pick = pick_bgm(
            provider=provider,
            mood=mood,
            target_duration_s=target_duration_s,
            library_dirs=[str(x) for x in library_dirs],
            ffprobe_bin=ffprobe_bin,
            max_candidates=int(payload.get("max_candidates", 20) or 20),
            api_key=api_key,
            endpoint=endpoint,
            timeout_seconds=float(payload.get("bgm_timeout_seconds", 45) or 45),
            output_dir=str(output_dir) if output_dir is not None else "",
            download_audio=bgm_download,
            strict_schema=bgm_strict_schema,
            cache_enabled=bgm_cache_enabled,
            force_refresh=bgm_force_refresh,
            cache_max_age_seconds=bgm_cache_max_age_seconds,
        )
    except Exception as exc:
        return jsonify({"error": f"自动配乐失败: {exc}"}), 400

    summary = {
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "mood": mood,
        "pick": pick,
    }
    out_path = _project_data_path("audio_voice_bgm_last.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "pick": pick, "output": str(out_path) if out_path else None})


@app.route("/api/capabilities/audio_voice/synthesize", methods=["POST"])
def api_audio_voice_synthesize():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    base_dir = _capability_base_dir(input_mode)
    mood = str(payload.get("mood", "travel_story") or "travel_story")
    provider = str(payload.get("provider", "elevenlabs") or "elevenlabs")
    voice_id = str(payload.get("voice_id", "") or "").strip()
    api_key = str(payload.get("api_key", "") or "").strip()
    model_id = str(payload.get("model_id", "eleven_multilingual_v2") or "eleven_multilingual_v2")
    output_format = str(payload.get("output_format", "mp3_44100_128") or "mp3_44100_128")
    dry_run = bool(payload.get("dry_run", False))
    timeout_seconds = float(payload.get("timeout_seconds", 90) or 90)

    from modules.capabilities.audio_voice import build_audio_capability_payload, synthesize_voiceover_segments

    script = _coerce_script_input(payload, input_mode=input_mode)
    plan = build_audio_capability_payload(script, mood=mood)
    segments = payload.get("segments", plan.get("voiceover_segments", []))
    if not isinstance(segments, list) or not segments:
        return jsonify({"error": "缺少可合成的字幕分段，请先完成脚本/字幕"}), 400

    output_dir_raw = str(payload.get("output_dir", "") or "").strip()
    output_dir = (
        (base_dir / "data" / "audio_voice" / "voiceover")
        if not output_dir_raw
        else _resolve_path_with_base(output_dir_raw, base_dir=base_dir)
    )

    try:
        result = synthesize_voiceover_segments(
            segments,
            output_dir=str(output_dir),
            provider=provider,
            voice_id=voice_id,
            api_key=api_key,
            model_id=model_id,
            output_format=output_format,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
        )
    except Exception as exc:
        return jsonify({"error": f"配音合成失败: {exc}"}), 400

    summary = {
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider,
        "voice_id": voice_id,
        "model_id": model_id,
        "dry_run": dry_run,
        "plan": plan,
        "synthesis": result,
    }
    out_path = _project_data_path("audio_voice_synthesize_last.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({
        "ok": True,
        "input_mode": input_mode,
        "plan": plan,
        "synthesis": result,
        "output": str(out_path) if out_path else None,
    })


@app.route("/api/capabilities/audio_voice/build_track", methods=["POST"])
def api_audio_voice_build_track():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    base_dir = _capability_base_dir(input_mode)
    ffmpeg_bin = str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg")
    timeout_seconds = float(payload.get("timeout_seconds", 600) or 600)
    dry_run = bool(payload.get("dry_run", False))

    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        if input_mode == "project":
            last = _read_project_json("audio_voice_synthesize_last.json", fallback={})
            synthesis = last.get("synthesis", {}) if isinstance(last, dict) else {}
            segments = synthesis.get("segments", []) if isinstance(synthesis, dict) else []
    if not isinstance(segments, list) or not segments:
        return jsonify({"error": "缺少可用的配音分段，请先执行 /api/capabilities/audio_voice/synthesize"}), 400

    output_audio_raw = str(payload.get("output_audio", "") or "").strip()
    output_audio = (
        (base_dir / "data" / "audio_voice" / "narration_timeline.m4a")
        if not output_audio_raw
        else _resolve_path_with_base(output_audio_raw, base_dir=base_dir)
    )

    from modules.capabilities.audio_voice import build_voiceover_timeline

    try:
        result = build_voiceover_timeline(
            segments,
            output_audio=str(output_audio),
            ffmpeg_bin=ffmpeg_bin,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
        )
    except Exception as exc:
        return jsonify({"error": f"旁白轨生成失败: {exc}"}), 400

    summary = {
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "timeline": result,
    }
    out_path = _project_data_path("audio_voice_timeline_last.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "input_mode": input_mode, "timeline": result, "output": str(out_path) if out_path else None})


@app.route("/api/capabilities/audio_voice/mix_master", methods=["POST"])
def api_audio_voice_mix_master():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    base_dir = _capability_base_dir(input_mode)
    ffmpeg_bin = str(payload.get("ffmpeg_bin", "ffmpeg") or "ffmpeg")
    ffprobe_bin = str(payload.get("ffprobe_bin", "ffprobe") or "ffprobe")
    timeout_seconds = float(payload.get("timeout_seconds", 900) or 900)
    dry_run = bool(payload.get("dry_run", False))
    replace_master = bool(payload.get("replace_master", input_mode == "project"))

    input_video_raw = str(payload.get("input_video", "") or "").strip()
    if input_video_raw:
        input_video = _resolve_path_with_base(input_video_raw, base_dir=base_dir)
    else:
        if input_mode == "project":
            input_video = _default_master_video_path()
            if input_video is None:
                return jsonify({"error": "找不到可混音的输入视频"}), 404
        else:
            return jsonify({"error": "inline 模式需要 input_video"}), 400
    if not input_video.exists():
        return jsonify({"error": f"输入视频不存在: {input_video}"}), 404

    narration_audio_raw = str(payload.get("narration_audio", "") or "").strip()
    if narration_audio_raw:
        narration_audio = _resolve_path_with_base(narration_audio_raw, base_dir=base_dir)
    else:
        if input_mode == "project":
            timeline_last = _read_project_json("audio_voice_timeline_last.json", fallback={})
            timeline = timeline_last.get("timeline", {}) if isinstance(timeline_last, dict) else {}
            maybe_path = str(timeline.get("output_audio", "") or "").strip()
        else:
            timeline = payload.get("timeline", {}) if isinstance(payload.get("timeline"), dict) else {}
            maybe_path = str(timeline.get("output_audio", "") or "").strip()
        if maybe_path:
            narration_audio = _resolve_path_with_base(maybe_path, base_dir=base_dir)
        else:
            narration_audio = base_dir / "data" / "audio_voice" / "narration_timeline.m4a"
    if not narration_audio.exists() and not dry_run:
        return jsonify({"error": f"旁白轨不存在: {narration_audio}"}), 404

    mood = str(payload.get("mood", "travel_story") or "travel_story")
    bgm_provider = str(payload.get("bgm_provider", "local_library") or "local_library")
    bgm_api_key = str(payload.get("bgm_api_key", "") or "").strip()
    bgm_endpoint = str(payload.get("bgm_endpoint", "") or "").strip()
    bgm_download = bool(payload.get("bgm_download", True))
    bgm_strict_schema = bool(payload.get("bgm_strict_schema", False))
    bgm_cache_enabled = bool(payload.get("bgm_cache_enabled", True))
    bgm_force_refresh = bool(payload.get("bgm_force_refresh", False))
    bgm_cache_max_age_days = float(payload.get("bgm_cache_max_age_days", 0) or 0)
    bgm_cache_max_age_seconds = max(bgm_cache_max_age_days, 0.0) * 86400.0
    bgm_audio_raw = str(payload.get("bgm_audio", "") or "").strip()
    bgm_pick = None
    bgm_audio = ""
    if bgm_audio_raw:
        if _is_remote_media_url(bgm_audio_raw):
            bgm_audio = bgm_audio_raw
        else:
            bgm_path = _resolve_path_with_base(bgm_audio_raw, base_dir=base_dir)
            bgm_audio = str(bgm_path)
    elif bool(payload.get("auto_pick_bgm", False)):
        from modules.capabilities.audio_voice import pick_bgm
        plan_guess = _read_project_json("audio_voice_plan.json", fallback={}) if input_mode == "project" else {}
        duration_guess = None
        if isinstance(plan_guess, dict):
            try:
                duration_guess = float(
                    plan_guess.get("music_plan", {}).get("duration_s")
                )
            except Exception:
                duration_guess = None
        custom_dir = str(payload.get("bgm_library_dir", "") or "").strip()
        custom_dirs = _parse_str_list(payload.get("bgm_library_dirs", []))
        if input_mode == "project":
            library_dirs = _default_bgm_library_dirs(custom_dir=custom_dir, custom_dirs=custom_dirs)
            output_dir = _default_bgm_output_dir(str(payload.get("bgm_output_dir", "") or "").strip())
        else:
            library_dirs = []
            for raw in [custom_dir, *custom_dirs]:
                text = str(raw or "").strip()
                if not text:
                    continue
                resolved = _resolve_path_with_base(text, base_dir=base_dir)
                if resolved.exists() and resolved.is_dir():
                    library_dirs.append(resolved)
            bgm_output_raw = str(payload.get("bgm_output_dir", "") or "").strip()
            output_dir = (
                _resolve_path_with_base(bgm_output_raw, base_dir=base_dir)
                if bgm_output_raw
                else (base_dir / "data" / "audio_voice" / "bgm")
            )
        try:
            bgm_pick = pick_bgm(
                provider=bgm_provider,
                mood=mood,
                target_duration_s=duration_guess,
                library_dirs=[str(x) for x in library_dirs],
                ffprobe_bin=ffprobe_bin,
                max_candidates=int(payload.get("bgm_max_candidates", 20) or 20),
                api_key=bgm_api_key,
                endpoint=bgm_endpoint,
                timeout_seconds=float(payload.get("bgm_timeout_seconds", 45) or 45),
                output_dir=str(output_dir) if output_dir is not None else "",
                download_audio=bgm_download,
                strict_schema=bgm_strict_schema,
                cache_enabled=bgm_cache_enabled,
                force_refresh=bgm_force_refresh,
                cache_max_age_seconds=bgm_cache_max_age_seconds,
            )
        except Exception as exc:
            return jsonify({"error": f"自动配乐失败: {exc}"}), 400
        maybe_track = str(bgm_pick.get("selected_track", "") or "").strip() if isinstance(bgm_pick, dict) else ""
        if maybe_track:
            bgm_audio = maybe_track
        elif isinstance(bgm_pick, dict):
            maybe_url = str(bgm_pick.get("selected_url", "") or "").strip()
            if maybe_url:
                bgm_audio = maybe_url

    output_video_raw = str(payload.get("output_video", "") or "").strip()
    if replace_master:
        output_video = base_dir / "output" / "final.mp4"
    elif output_video_raw:
        output_video = _resolve_path_with_base(output_video_raw, base_dir=base_dir)
    else:
        output_video = base_dir / "output" / "final_voice.mp4"

    mix_target = output_video
    used_temp = False
    if output_video.resolve() == input_video.resolve():
        used_temp = True
        mix_target = output_video.with_suffix(".mixing_tmp.mp4")

    from modules.capabilities.audio_voice import mix_voiceover_to_video

    try:
        result = mix_voiceover_to_video(
            input_video=str(input_video),
            output_video=str(mix_target),
            narration_audio=str(narration_audio),
            bgm_audio=bgm_audio,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
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
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
        )
    except Exception as exc:
        return jsonify({"error": f"成片混音失败: {exc}"}), 400

    if used_temp and not dry_run and result.get("status") == "done":
        mix_target.replace(output_video)
        result["output_video"] = str(output_video.resolve())

    summary = {
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "replace_master": replace_master,
        "bgm_pick": bgm_pick,
        "mix": result,
    }
    out_path = _project_data_path("audio_voice_mix_last.json") if input_mode == "project" else None
    if out_path is not None and bool(payload.get("store_result", True)):
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(
        {
            "ok": True,
            "input_mode": input_mode,
            "mix": result,
            "bgm_pick": bgm_pick,
            "output": str(out_path) if out_path else None,
        }
    )


@app.route("/api/capabilities/audio_voice/run", methods=["POST"])
def api_audio_voice_run():
    payload = request.json or {}
    input_mode = _parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
    if input_mode == "project" and _project_dir is None:
        return jsonify({"error": "项目未加载"}), 400
    running = _running_heavy_jobs()
    if running:
        return jsonify({
            "error": "已有重任务运行中，请等待完成后再执行音频流水线",
            "running_jobs": running,
            "system": _system_load_snapshot(),
        }), 409
    job_id = str(uuid.uuid4())[:8]
    runner = _build_audio_voice_runner(
        payload=payload,
        job_id=job_id,
        input_mode=input_mode,
        base_dir=_capability_base_dir(input_mode),
    )
    _run_in_bg(job_id, runner, kind="audio_voice")
    return jsonify({"ok": True, "input_mode": input_mode, "job_id": job_id})


# ── UI 静态文件 ───────────────────────────────────────────────────────

@app.route("/")
def serve_index():
    ui_dir = APP_UI_DIR
    return send_file(str(ui_dir / "index.html"))


@app.route("/<path:filename>")
def serve_static(filename):
    ui_dir = APP_UI_DIR
    target = (ui_dir / filename).resolve()
    if not str(target).startswith(str(ui_dir.resolve())):
        abort(403)
    if not target.exists():
        abort(404)
    return send_file(str(target))


# ── 工厂函数（供 app.py 调用）─────────────────────────────────────────

def create_app(project_dir: Optional[str] = None):
    """创建并配置 Flask app，可选预加载项目。"""
    if project_dir:
        p = Path(project_dir)
        if (p / "workflow.json").exists():
            _load_state(p)
    return app


def set_window(window):
    """由 app.py 在窗口创建后注入 pywebview window 引用。"""
    global _window
    _window = window
