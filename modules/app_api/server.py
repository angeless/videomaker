#!/usr/bin/env python3
"""
Flask API 服务器 —— 为 pywebview GUI 提供后端接口

端点:
  GET  /api/status               → 当前 workflow 状态
  GET  /api/system/load          → 系统负载与运行任务
  GET  /api/settings/ai          → 读取 AI 配置
  POST /api/settings/ai          → 保存 AI 配置
  POST /api/init                 → 初始化新项目
  POST /api/open_project         → 打开已有项目
  POST /api/approve/<int:step>   → 审核通过某步骤（含表单数据）
  POST /api/run_step             → 后台运行当前步骤（返回 job_id）
  GET  /api/job/<job_id>         → 轮询后台任务状态
  POST /api/job/<job_id>/cancel  → 取消后台任务
  GET  /api/files/<path:rel>     → 提供项目文件（视频/图片）
  GET  /api/frames               → 列出帧预览图片
  GET  /api/stage_files          → 列出 Step 7 各 stage 文件存在情况
  POST /api/open_in_finder       → 在 Finder 中打开文件/目录
  POST /api/dialog/folder        → 触发 pywebview 文件夹选择对话框
  POST /api/dialog/file          → 触发 pywebview 文件选择对话框
"""

import sys
import os
import json
import uuid
import threading
import subprocess
import traceback
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_UI_DIR = REPO_ROOT / "apps" / "desktop" / "ui"

from flask import Flask, jsonify, request, send_file, abort
from modules.workflow_engine.workflow import WorkflowState, WorkflowRunner
from modules.library.global_media_library import GlobalMediaLibrary

app = Flask(__name__, static_folder=None)
app.config["JSON_AS_ASCII"] = False

# ── 全局状态 ────────────────────────────────────────────────────────
_project_dir: Optional[Path] = None
_ws: Optional[WorkflowState] = None
_jobs: Dict[str, dict] = {}      # job_id → {status, log, progress}
_window = None                    # pywebview window（由 app.py 注入）
_library = GlobalMediaLibrary()
CANCEL_TOKEN = "__CANCELLED__"


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
    return {
        "ready": True,
        "project_dir": str(ws.data.get("project_dir", "")),
        "videos_dir": str(ws.data.get("videos_dir", "")),
        "current_step": ws.data.get("current_step", 1),
        "steps": steps_info,
        "config": ws.config,
        "system": _system_load_snapshot(),
        "running_jobs": _running_heavy_jobs(),
    }


def _run_in_bg(job_id: str, fn, *args, kind: str = "generic", **kwargs):
    """在后台线程运行 fn，捕获 stdout 并更新 _jobs[job_id]。"""
    _jobs[job_id] = {
        "status": "running",
        "log": [],
        "progress": 0,
        "kind": kind,
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
    heavy_kinds = {"workflow_step", "library_ingest_local", "library_ingest_gdrive"}
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
    base_url = str(payload.get("ai_base_url", "") or "").strip()
    if provider:
        ai["provider"] = provider
    elif "provider" in payload:
        ai.pop("provider", None)
    if model:
        ai["ai_model"] = model
    elif "ai_model" in payload:
        ai.pop("ai_model", None)
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

    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key
    if anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_api_key
    if ai_base_url:
        os.environ["OPENAI_BASE_URL"] = ai_base_url


def _public_ai_settings(ai: Dict) -> Dict:
    return {
        "provider": ai.get("provider", ""),
        "ai_model": ai.get("ai_model", ""),
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
            return jsonify({"error": "所选素材均不可用（路径不存在或未入库）"}), 400

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
    results = _library.search_assets(query=query, limit=limit, offset=offset)
    total_matches = _library.count_matching_assets(query=query)
    stats = _library.stats()
    has_more = (offset + len(results)) < total_matches
    return jsonify({
        "query": query,
        "limit": limit,
        "offset": offset,
        "count": len(results),
        "total_matches": total_matches,
        "total_assets": stats.get("total_assets", 0),
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
            if done == total or done % 10 == 0:
                name = Path(current_path).name if current_path else ""
                _jobs[job_id]["log"].append(f"已处理 {done}/{total} {name}")

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

    _run_in_bg(job_id, _do_local, kind="library_ingest_local")
    return jsonify({
        "ok": True,
        "job_id": job_id,
        "mode": "async",
        "max_videos": max_videos,
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
            if done == total or done % 10 == 0:
                name = Path(current_path).name if current_path else ""
                _jobs[job_id]["log"].append(f"已处理 {done}/{total} {name}")

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
