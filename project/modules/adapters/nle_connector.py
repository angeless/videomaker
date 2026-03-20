#!/usr/bin/env python3
"""NLE connector adapter layer (Resolve-first, API-friendly)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import importlib.util
import os
import sys


EDITOR_ALIASES: Dict[str, str] = {
    "resolve": "davinci",
    "davinci_resolve": "davinci",
    "fcp": "finalcut",
    "fcpx": "finalcut",
    "premiere_pro": "premiere",
}

EDITOR_DEFAULT_APP_NAMES: Dict[str, str] = {
    "davinci": "DaVinci Resolve",
    "finalcut": "Final Cut Pro",
    "premiere": "Adobe Premiere Pro",
    "jianying": "剪映专业版",
}


@dataclass(frozen=True)
class ConnectorStatus:
    editor: str
    name: str
    available: bool
    launch_supported: bool
    app_detected: bool
    app_name: str
    app_path: str
    scripting_available: bool
    reason: str
    hint: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "editor": self.editor,
            "name": self.name,
            "available": bool(self.available),
            "launch_supported": bool(self.launch_supported),
            "app_detected": bool(self.app_detected),
            "app_name": self.app_name,
            "app_path": self.app_path,
            "scripting_available": bool(self.scripting_available),
            "reason": self.reason,
            "hint": self.hint,
            "details": dict(self.details),
        }


class BaseNLEConnector(ABC):
    editor_id: str = ""
    display_name: str = ""
    default_app_name: str = ""

    @abstractmethod
    def detect(self) -> ConnectorStatus:
        raise NotImplementedError

    @abstractmethod
    def create_handoff(
        self,
        *,
        script: Dict[str, Any],
        materials: Dict[str, Any],
        output_dir: str,
        title: str,
        fps: int,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def launch(
        self,
        handoff: Dict[str, Any],
        *,
        app_name: str = "",
        timeout_seconds: float = 20,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def collect_master(
        self,
        *,
        source_video: str,
        output_dir: str,
        output_name: str = "final.mp4",
        copy_mode: str = "copy",
    ) -> Dict[str, Any]:
        raise NotImplementedError


class GenericNLEConnector(BaseNLEConnector):
    def __init__(self, editor_id: str, display_name: str = "", default_app_name: str = ""):
        self.editor_id = normalize_nle_editor(editor_id)
        self.display_name = display_name or self.editor_id
        self.default_app_name = default_app_name or EDITOR_DEFAULT_APP_NAMES.get(self.editor_id, "")

    def _app_env_var(self) -> str:
        token = self.editor_id.upper().replace("-", "_")
        return f"VIDEOEDITOR_{token}_APP_PATH"

    def _default_app_candidates(self) -> List[str]:
        if sys.platform.startswith("darwin"):
            mapping = {
                "finalcut": ["/Applications/Final Cut Pro.app"],
                "premiere": ["/Applications/Adobe Premiere Pro 2025/Adobe Premiere Pro 2025.app", "/Applications/Adobe Premiere Pro 2024/Adobe Premiere Pro 2024.app", "/Applications/Adobe Premiere Pro.app"],
                "davinci": ["/Applications/DaVinci Resolve.app", "/Applications/DaVinci Resolve Studio.app"],
                "jianying": ["/Applications/剪映专业版.app", "/Applications/JianyingPro.app"],
            }
            return mapping.get(self.editor_id, [])
        if sys.platform.startswith("win"):
            base = os.environ.get("ProgramFiles", r"C:\\Program Files")
            mapping = {
                "premiere": [
                    str(Path(base) / "Adobe" / "Adobe Premiere Pro 2025" / "Adobe Premiere Pro.exe"),
                    str(Path(base) / "Adobe" / "Adobe Premiere Pro 2024" / "Adobe Premiere Pro.exe"),
                ],
                "davinci": [
                    str(Path(base) / "Blackmagic Design" / "DaVinci Resolve" / "Resolve.exe"),
                ],
                "jianying": [
                    str(Path(base) / "JianyingPro" / "JianyingPro.exe"),
                ],
            }
            return mapping.get(self.editor_id, [])
        if sys.platform.startswith("linux"):
            mapping = {
                "davinci": ["/opt/resolve/bin/resolve", "/usr/bin/resolve"],
            }
            return mapping.get(self.editor_id, [])
        return []

    def _detect_app_path(self) -> str:
        env_path = str(os.environ.get(self._app_env_var(), "") or "").strip()
        if env_path and Path(env_path).expanduser().exists():
            return str(Path(env_path).expanduser().resolve())
        for candidate in self._default_app_candidates():
            p = Path(candidate).expanduser()
            if p.exists():
                return str(p.resolve())
        return ""

    def detect(self) -> ConnectorStatus:
        app_path = self._detect_app_path()
        app_detected = bool(app_path)
        launch_supported = bool(app_detected)
        available = bool(app_detected)
        reason = "ready" if available else "app_not_found"
        hint = ""
        if not available:
            env_key = self._app_env_var()
            hint = f"未检测到 {self.display_name}，可安装应用或设置环境变量 {env_key} 指向应用路径"
        return ConnectorStatus(
            editor=self.editor_id,
            name=self.display_name,
            available=available,
            launch_supported=launch_supported,
            app_detected=app_detected,
            app_name=self.default_app_name,
            app_path=app_path,
            scripting_available=False,
            reason=reason,
            hint=hint,
            details={
                "env_var": self._app_env_var(),
                "default_candidates": self._default_app_candidates(),
            },
        )

    def create_handoff(
        self,
        *,
        script: Dict[str, Any],
        materials: Dict[str, Any],
        output_dir: str,
        title: str,
        fps: int,
    ) -> Dict[str, Any]:
        from modules.capabilities.nle_handoff import create_nle_handoff

        return create_nle_handoff(
            script=script,
            materials=materials,
            output_dir=output_dir,
            editor=self.editor_id,
            title=title,
            fps=int(fps),
        )

    def launch(
        self,
        handoff: Dict[str, Any],
        *,
        app_name: str = "",
        timeout_seconds: float = 20,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        from modules.capabilities.nle_handoff import launch_nle_handoff

        return launch_nle_handoff(
            handoff,
            app_name=str(app_name or self.default_app_name or "").strip(),
            timeout_seconds=float(timeout_seconds),
            dry_run=bool(dry_run),
        )

    def collect_master(
        self,
        *,
        source_video: str,
        output_dir: str,
        output_name: str = "final.mp4",
        copy_mode: str = "copy",
    ) -> Dict[str, Any]:
        from modules.capabilities.nle_handoff import collect_nle_master_video

        return collect_nle_master_video(
            source_video=source_video,
            output_dir=output_dir,
            output_name=output_name,
            copy_mode=copy_mode,
        )


class ResolveConnector(GenericNLEConnector):
    def __init__(self):
        super().__init__("davinci", display_name="DaVinci Resolve", default_app_name="DaVinci Resolve")

    def detect(self) -> ConnectorStatus:
        generic = super().detect()
        scripting_available = importlib.util.find_spec("DaVinciResolveScript") is not None
        api_root = str(os.environ.get("RESOLVE_SCRIPT_API", "") or "").strip()
        api_root_exists = bool(api_root and Path(api_root).expanduser().exists())

        available = bool(generic.app_detected or scripting_available or api_root_exists)
        launch_supported = bool(generic.app_detected)

        reason = "ready" if available else "resolve_unavailable"
        hint = ""
        if not available:
            hint = (
                "未检测到 Resolve。可安装 DaVinci Resolve，或配置 RESOLVE_SCRIPT_API / "
                "VIDEOEDITOR_DAVINCI_APP_PATH 以启用外部交接。"
            )
        elif not launch_supported:
            hint = "已检测到脚本 API 但未找到应用路径，仅可生成交接文件，无法自动唤起 Resolve。"

        details = dict(generic.details)
        details.update(
            {
                "resolve_script_api_env": api_root,
                "resolve_script_api_exists": api_root_exists,
            }
        )

        return ConnectorStatus(
            editor="davinci",
            name="DaVinci Resolve",
            available=available,
            launch_supported=launch_supported,
            app_detected=generic.app_detected,
            app_name=generic.app_name,
            app_path=generic.app_path,
            scripting_available=scripting_available,
            reason=reason,
            hint=hint,
            details=details,
        )


def normalize_nle_editor(value: Any, default: str = "finalcut") -> str:
    token = str(value or "").strip().lower()
    if not token:
        token = default
    token = EDITOR_ALIASES.get(token, token)
    if token not in {"davinci", "finalcut", "premiere", "jianying"}:
        token = default
    return token


def get_nle_connector(editor: Any) -> BaseNLEConnector:
    key = normalize_nle_editor(editor)
    if key == "davinci":
        return ResolveConnector()
    return GenericNLEConnector(
        key,
        display_name=EDITOR_DEFAULT_APP_NAMES.get(key, key),
        default_app_name=EDITOR_DEFAULT_APP_NAMES.get(key, ""),
    )


def list_nle_connector_statuses(editors: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    requested = list(editors) if editors is not None else ["davinci", "finalcut", "premiere", "jianying"]
    statuses: List[Dict[str, Any]] = []
    seen = set()
    for item in requested:
        key = normalize_nle_editor(item)
        if key in seen:
            continue
        seen.add(key)
        connector = get_nle_connector(key)
        statuses.append(connector.detect().to_dict())
    return statuses
