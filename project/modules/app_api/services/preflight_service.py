#!/usr/bin/env python3
"""Startup preflight checks for desktop runtime diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import importlib.util
import json
import os
import shutil
import sys

from modules.adapters.nle_connector import list_nle_connector_statuses


@dataclass(frozen=True)
class PreflightCheck:
    check_id: str
    title: str
    status: str
    severity: str
    detail: str
    hint: str
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.check_id,
            "title": self.title,
            "status": self.status,
            "severity": self.severity,
            "detail": self.detail,
            "hint": self.hint,
            "data": dict(self.data),
        }


def _module_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _is_writable_dir(path: Path) -> bool:
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _which(binary: str) -> str:
    hit = shutil.which(str(binary or "").strip())
    return str(hit or "")


def _openai_compatible(provider: str) -> bool:
    return provider in {"", "openai", "moonshot", "qwen", "gemini", "maxmini"}


def _check(
    checks: List[PreflightCheck],
    *,
    check_id: str,
    title: str,
    ok: bool,
    detail_ok: str,
    detail_bad: str,
    hint: str = "",
    severity_on_bad: str = "error",
    data: Optional[Dict[str, Any]] = None,
) -> None:
    status = "ok" if ok else severity_on_bad
    checks.append(
        PreflightCheck(
            check_id=check_id,
            title=title,
            status=status,
            severity=status,
            detail=detail_ok if ok else detail_bad,
            hint="" if ok else str(hint or ""),
            data=data or {},
        )
    )


def run_startup_preflight(
    *,
    repo_root: Path,
    library_db_path: Path,
    app_state_db_path: Path,
    ai_settings: Optional[Dict[str, Any]] = None,
    ui_settings: Optional[Dict[str, Any]] = None,
    secret_storage_status: Optional[Dict[str, Any]] = None,
    require_local_token: bool = False,
    require_csrf: bool = True,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    checks: List[PreflightCheck] = []
    ai = ai_settings if isinstance(ai_settings, dict) else {}
    ui = ui_settings if isinstance(ui_settings, dict) else {}
    secret_status = secret_storage_status if isinstance(secret_storage_status, dict) else {}

    py_ok = sys.version_info >= (3, 10)
    _check(
        checks,
        check_id="runtime.python",
        title="Python 版本",
        ok=py_ok,
        detail_ok=f"Python {sys.version.split()[0]}",
        detail_bad=f"Python 版本过低：{sys.version.split()[0]}",
        hint="建议使用 Python 3.10+（推荐 3.11/3.12）。",
        severity_on_bad="error",
        data={"version": sys.version.split()[0]},
    )

    flask_ok = _module_exists("flask")
    _check(
        checks,
        check_id="runtime.flask",
        title="Flask 依赖",
        ok=flask_ok,
        detail_ok="已安装 Flask",
        detail_bad="缺少 Flask 依赖",
        hint="启动器可自动安装 requirements.txt。",
        severity_on_bad="error",
    )

    webview_ok = _module_exists("webview")
    _check(
        checks,
        check_id="runtime.pywebview",
        title="pywebview 依赖",
        ok=webview_ok,
        detail_ok="已安装 pywebview",
        detail_bad="缺少 pywebview，桌面窗口无法启动",
        hint="启动器会自动安装 pywebview。",
        severity_on_bad="error",
    )

    ffmpeg_path = _which("ffmpeg")
    _check(
        checks,
        check_id="runtime.ffmpeg",
        title="FFmpeg",
        ok=bool(ffmpeg_path),
        detail_ok=f"已找到 FFmpeg：{ffmpeg_path}",
        detail_bad="未找到 FFmpeg",
        hint="请安装 ffmpeg 并确保在 PATH 中可执行。",
        severity_on_bad="error",
        data={"path": ffmpeg_path},
    )

    ffprobe_path = _which("ffprobe")
    _check(
        checks,
        check_id="runtime.ffprobe",
        title="FFprobe",
        ok=bool(ffprobe_path),
        detail_ok=f"已找到 FFprobe：{ffprobe_path}",
        detail_bad="未找到 FFprobe",
        hint="请安装 ffmpeg 套件（含 ffprobe）。",
        severity_on_bad="warning",
        data={"path": ffprobe_path},
    )

    # Hardware detection (best-effort, never blocks startup)
    hw_profile = None
    try:
        from modules.hardware.detector import get_system_profile
        from modules.hardware.encoding_strategy import choose_encoder, suggest_max_concurrent
        hw_profile = get_system_profile()
        enc = choose_encoder(hw_profile)
        max_conc = suggest_max_concurrent(hw_profile)
        _check(
            checks,
            check_id="hardware.profile",
            title="硬件自适应",
            ok=True,
            detail_ok=f"CPU {hw_profile.cpu.physical_cores}核 / RAM {hw_profile.memory.total_gb}GB / 编码器: {enc.label}",
            detail_bad="",
            severity_on_bad="warning",
            data={
                "cpu_cores": hw_profile.cpu.physical_cores,
                "ram_gb": hw_profile.memory.total_gb,
                "gpu_vendor": hw_profile.gpu.vendor,
                "encoder": enc.video_encoder,
                "encoder_label": enc.label,
                "hwaccels": hw_profile.ffmpeg_hwaccels,
                "suggested_max_concurrent": max_conc,
            },
        )
    except Exception:
        _check(
            checks,
            check_id="hardware.profile",
            title="硬件自适应",
            ok=True,
            detail_ok="硬件探测跳过（不影响核心功能）",
            detail_bad="",
            severity_on_bad="warning",
        )

    repo_writable = _is_writable_dir(Path(repo_root))
    _check(
        checks,
        check_id="storage.repo",
        title="工作目录写入权限",
        ok=repo_writable,
        detail_ok=f"可写：{Path(repo_root)}",
        detail_bad=f"不可写：{Path(repo_root)}",
        hint="请确认当前账号对项目目录有写权限。",
        severity_on_bad="error",
    )

    lib_dir = Path(library_db_path).expanduser().resolve().parent
    lib_writable = _is_writable_dir(lib_dir)
    _check(
        checks,
        check_id="storage.library",
        title="素材库目录写入权限",
        ok=lib_writable,
        detail_ok=f"可写：{lib_dir}",
        detail_bad=f"不可写：{lib_dir}",
        hint="请检查 .video_library 目录权限。",
        severity_on_bad="error",
    )

    app_state_dir = Path(app_state_db_path).expanduser().resolve().parent
    app_state_writable = _is_writable_dir(app_state_dir)
    _check(
        checks,
        check_id="storage.app_state",
        title="任务状态库写入权限",
        ok=app_state_writable,
        detail_ok=f"可写：{app_state_dir}",
        detail_bad=f"不可写：{app_state_dir}",
        hint="任务队列状态无法持久化，请检查目录权限。",
        severity_on_bad="error",
    )

    provider = str(ai.get("provider", "openai") or "openai").strip().lower()
    model = str(ai.get("ai_model", "") or "").strip()
    embedding_model = str(ai.get("embedding_model", "") or "").strip() or "text-embedding-3-small"
    openai_key = str(ai.get("openai_api_key", "") or "").strip()
    anthropic_key = str(ai.get("anthropic_api_key", "") or "").strip()

    _check(
        checks,
        check_id="ai.provider_model",
        title="AI Provider / Model 配置",
        ok=bool(provider and model),
        detail_ok=f"已配置：{provider} / {model}",
        detail_bad=f"AI 模型未完整配置（provider={provider or '-'} model={model or '-'})",
        hint="请在 AI 配置中选择 provider 并填写 model。",
        severity_on_bad="warning",
        data={"provider": provider, "model": model},
    )

    if provider == "anthropic":
        ai_key_ok = bool(anthropic_key)
        ai_key_hint = "Anthropic provider 需要配置 Anthropic API Key。"
    elif _openai_compatible(provider):
        ai_key_ok = bool(openai_key)
        ai_key_hint = "当前 provider 需要 OpenAI 兼容 API Key（OpenAI/Kimi/Qwen/Gemini/MiniMax）。"
    else:
        ai_key_ok = bool(openai_key or anthropic_key)
        ai_key_hint = "请配置可用 API Key。"

    _check(
        checks,
        check_id="ai.api_key",
        title="AI Key 可用性",
        ok=ai_key_ok,
        detail_ok="已检测到有效 API Key",
        detail_bad="未检测到当前 provider 对应 API Key",
        hint=ai_key_hint,
        severity_on_bad="warning",
    )

    embedding_ready = bool(openai_key)
    _check(
        checks,
        check_id="ai.embedding",
        title="向量检索能力",
        ok=embedding_ready,
        detail_ok=f"Embedding 可用（{embedding_model}）",
        detail_bad="向量检索不可用（缺少 OpenAI API Key）",
        hint="若需要语义向量检索，请配置 OpenAI API Key。",
        severity_on_bad="warning",
        data={"embedding_model": embedding_model},
    )

    secure_backend = bool(secret_status.get("available", False))
    _check(
        checks,
        check_id="security.secret_store",
        title="密钥安全存储",
        ok=secure_backend,
        detail_ok=f"启用系统安全存储：{secret_status.get('backend', 'secure_store')}",
        detail_bad="当前降级为本地明文存储",
        hint="建议启用系统钥匙串/安全存储后再保存生产密钥。",
        severity_on_bad="warning",
        data={"secret_storage": secret_status},
    )

    _check(
        checks,
        check_id="security.local_token",
        title="本地 API 访问保护",
        ok=bool(require_local_token),
        detail_ok="已启用本地 API Token 校验",
        detail_bad="未启用本地 API Token 校验",
        hint="桌面环境建议开启 VIDEOEDITOR_REQUIRE_LOCAL_TOKEN=1。",
        severity_on_bad="warning",
    )

    _check(
        checks,
        check_id="security.csrf",
        title="CSRF 保护",
        ok=bool(require_csrf),
        detail_ok="已启用 CSRF 校验",
        detail_bad="未启用 CSRF 校验",
        hint="建议保持 CSRF 保护开启。",
        severity_on_bad="warning",
    )

    default_videos_dir = str(ui.get("default_videos_dir", "") or "").strip()
    videos_dir_ok = (not default_videos_dir) or Path(default_videos_dir).expanduser().exists()
    _check(
        checks,
        check_id="ui.default_videos_dir",
        title="默认素材目录",
        ok=videos_dir_ok,
        detail_ok=(f"已配置：{default_videos_dir}" if default_videos_dir else "未配置（可选）"),
        detail_bad=f"默认素材目录不存在：{default_videos_dir}",
        hint="可在应用设置里重新选择目录。",
        severity_on_bad="warning",
        data={"default_videos_dir": default_videos_dir},
    )

    connector_statuses = list_nle_connector_statuses(["davinci"])
    resolve_status = connector_statuses[0] if connector_statuses else {}
    resolve_ok = bool(resolve_status.get("available", False))
    _check(
        checks,
        check_id="nle.davinci",
        title="DaVinci Resolve 连接",
        ok=resolve_ok,
        detail_ok="Resolve 连接器可用",
        detail_bad="Resolve 未检测到（仍可生成交接文件）",
        hint=str(resolve_status.get("hint", "可安装 Resolve 后启用自动唤起")),
        severity_on_bad="warning",
        data=resolve_status,
    )

    counts = {"ok": 0, "warning": 0, "error": 0}
    for item in checks:
        key = item.status if item.status in counts else "warning"
        counts[key] += 1

    blockers = [x.to_dict() for x in checks if x.status == "error"]
    warnings = [x.to_dict() for x in checks if x.status == "warning"]
    actions: List[str] = []
    for x in blockers + warnings:
        hint = str(x.get("hint", "") or "").strip()
        if hint and hint not in actions:
            actions.append(hint)

    clock = now or datetime.now()
    total = len(checks)
    startup_ready = counts["error"] == 0
    score = round((counts["ok"] / total) * 100, 1) if total else 100.0

    return {
        "ok": startup_ready,
        "startup_ready": startup_ready,
        "summary": {
            "total": total,
            "ok": counts["ok"],
            "warning": counts["warning"],
            "error": counts["error"],
            "score": score,
            "generated_at": clock.isoformat(timespec="seconds"),
        },
        "checks": [item.to_dict() for item in checks],
        "blockers": blockers,
        "warnings": warnings,
        "recommended_actions": actions,
        "nle_connectors": connector_statuses,
        "meta": {
            "repo_root": str(Path(repo_root).resolve()),
            "library_db_path": str(Path(library_db_path).resolve()),
            "app_state_db_path": str(Path(app_state_db_path).resolve()),
            "platform": sys.platform,
            "python": sys.version.split()[0],
        },
    }


def dump_preflight_report(path: Path, report: Dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    from modules.app_api.param_utils import atomic_write_json
    atomic_write_json(target, report)
    return target
