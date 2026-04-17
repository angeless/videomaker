"""
v0.7 Phase C-2 — Project Relink Adapter ABC + Jianying implementation.

Provides a pluggable adapter interface for parsing and applying relink maps
across different NLE project formats.  Only Jianying is implemented for now;
adding FCPXML / EDL / Resolve in future phases requires implementing the
ProjectRelinkAdapter ABC.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

import json


# Round-13 P1: project_path / output_path flow in from HTTP API payloads
# (see /api/library/project-relink routes). Without validation, attackers
# with local-token access could read arbitrary files via project_path
# (e.g. `/etc/passwd`) or write to arbitrary locations via output_path
# (e.g. `~/.ssh/authorized_keys`). We enforce:
#   1. Path must resolve to an existing .json (for reads) or parent dir
#      (for writes)
#   2. If ``allowed_base`` is provided, the resolved path must be inside it
#   3. Max file size for reads to prevent DoS via huge-JSON parse
_MAX_PROJECT_JSON_BYTES = 256 * 1024 * 1024  # 256 MB — well above any real NLE project


def _safe_project_path(
    raw: str, *, allowed_base: Optional[Path] = None, must_exist: bool = True
) -> Path:
    """Resolve and validate a user-supplied project file path.

    Raises ValueError if the path is missing, not a file, too large, or
    escapes ``allowed_base`` (when provided).
    """
    if not raw:
        raise ValueError("project_path is required")
    p = Path(str(raw).strip()).expanduser().resolve()
    if allowed_base is not None:
        base = Path(allowed_base).expanduser().resolve()
        try:
            p.relative_to(base)
        except ValueError as exc:
            raise ValueError(
                f"project_path {p} escapes allowed base {base}"
            ) from exc
    if must_exist:
        if not p.is_file():
            raise ValueError(f"project_path is not a file: {p}")
        try:
            size = p.stat().st_size
        except OSError as exc:
            raise ValueError(f"cannot stat project_path: {exc}") from exc
        if size > _MAX_PROJECT_JSON_BYTES:
            raise ValueError(
                f"project_path exceeds size cap "
                f"({size} > {_MAX_PROJECT_JSON_BYTES} bytes)"
            )
    return p


def _safe_output_path(
    raw: str, *, allowed_base: Optional[Path] = None
) -> Path:
    """Resolve and validate a user-supplied OUTPUT path.

    Ensures we're writing a .json file inside an allowed base directory.
    The parent directory need not exist (we'll create it).
    """
    if not raw:
        raise ValueError("output_path is required")
    p = Path(str(raw).strip()).expanduser().resolve()
    if p.suffix.lower() != ".json":
        raise ValueError(f"output_path must be a .json file (got {p.suffix!r})")
    if allowed_base is not None:
        base = Path(allowed_base).expanduser().resolve()
        try:
            p.relative_to(base)
        except ValueError as exc:
            raise ValueError(
                f"output_path {p} escapes allowed base {base}"
            ) from exc
    return p


class ProjectRelinkAdapter(ABC):
    """Abstract base class for project relink adapters.

    Each adapter knows how to:
    1. validate a project file
    2. parse media references out of it
    3. apply a path substitution map to produce a relinked copy
    4. extract version/meta info
    """

    @property
    @abstractmethod
    def project_type(self) -> str:
        """Return the project type identifier (e.g., 'jianying')."""

    @abstractmethod
    def validate(self, project_path: str) -> Dict:
        """
        Validate the project file structure and readability.

        Returns:
            {
                "valid": bool,
                "errors": [str],       # fatal problems
                "warnings": [str],     # non-fatal notes
                "version_info": {}     # extracted version/meta fields
            }
        """

    @abstractmethod
    def parse_references(self, project_path: str) -> List[Dict]:
        """
        Parse media references from the project file.

        Returns a list of dicts, each with:
            asset_name   – filename portion (e.g. "clip.mp4")
            old_path     – absolute path as stored in the project
            source_ref   – unique id inside the project (e.g. material id)
            media_type   – "video" | "audio"
            size_bytes   – file size hint if available (may be None)
        """

    @abstractmethod
    def apply_relink(
        self, project_path: str, output_path: str, path_map: Dict[str, str]
    ) -> Dict:
        """
        Apply path substitutions to a project copy.

        Args:
            project_path: original project file
            output_path: where to write the relinked copy
            path_map: {old_path: new_path}

        Returns:
            {"applied": int, "skipped": int}
        """

    @abstractmethod
    def get_version_info(self, project_path: str) -> Dict:
        """Extract version/meta info from the project file."""


# ──────────────────────────────────────────────────────────
# Jianying (剪映) adapter
# ──────────────────────────────────────────────────────────


class JianyingRelinkAdapter(ProjectRelinkAdapter):
    """Adapter for Jianying (剪映) draft JSON files.

    Jianying stores media references as absolute paths in:
        materials.videos[].path
        materials.audios[].path
    """

    @property
    def project_type(self) -> str:
        return "jianying"

    # ── validate ──

    def validate(self, project_path: str) -> Dict:
        errors: List[str] = []
        warnings: List[str] = []
        version_info: Dict = {}

        try:
            safe_path = _safe_project_path(project_path)
            with open(safe_path, "r", encoding="utf-8") as f:
                draft = json.load(f)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            return {
                "valid": False,
                "errors": [str(exc)],
                "warnings": [],
                "version_info": {},
            }

        if "materials" not in draft:
            errors.append("Missing 'materials' key")
        else:
            mats = draft["materials"]
            if "videos" not in mats and "audios" not in mats:
                warnings.append("No videos or audios in materials")

        # Extract version info
        version_info["app_version"] = draft.get("app_version", None)
        version_info["draft_version"] = draft.get("version", None)
        platform = draft.get("platform")
        version_info["platform"] = (
            platform.get("os", None) if isinstance(platform, dict) else None
        )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "version_info": version_info,
        }

    # ── parse_references ──

    def parse_references(self, project_path: str) -> List[Dict]:
        safe_path = _safe_project_path(project_path)
        with open(safe_path, "r", encoding="utf-8") as f:
            draft = json.load(f)

        refs: List[Dict] = []
        materials = draft.get("materials", {})
        for category, media_type in [("videos", "video"), ("audios", "audio")]:
            for entry in materials.get(category, []):
                path = (entry.get("path") or "").strip()
                if not path:
                    continue
                refs.append(
                    {
                        "asset_name": Path(path).name,
                        "old_path": path,
                        "source_ref": entry.get("id", ""),
                        "media_type": media_type,
                        "size_bytes": entry.get("size_bytes"),
                    }
                )
        return refs

    # ── apply_relink ──

    def apply_relink(
        self, project_path: str, output_path: str, path_map: Dict[str, str]
    ) -> Dict:
        safe_in = _safe_project_path(project_path)
        safe_out = _safe_output_path(output_path)
        with open(safe_in, "r", encoding="utf-8") as f:
            draft = json.load(f)

        applied = 0
        materials = draft.get("materials", {})
        for category in ("videos", "audios"):
            for entry in materials.get(category, []):
                entry_path = (entry.get("path") or "").strip()
                if entry_path in path_map:
                    entry["path"] = path_map[entry_path]
                    applied += 1

        # Atomic write so a crash during apply can't corrupt the output.
        from modules.app_api.param_utils import atomic_write_json
        atomic_write_json(safe_out, draft)

        return {"applied": applied, "skipped": len(path_map) - applied}

    # ── get_version_info ──

    def get_version_info(self, project_path: str) -> Dict:
        try:
            safe_path = _safe_project_path(project_path)
            with open(safe_path, "r", encoding="utf-8") as f:
                draft = json.load(f)
            return {
                "app_version": draft.get("app_version"),
                "draft_version": draft.get("version"),
            }
        except (ValueError, json.JSONDecodeError, OSError):
            return {}


# ──────────────────────────────────────────────────────────
# Adapter registry
# ──────────────────────────────────────────────────────────

ADAPTERS: Dict[str, type] = {
    "jianying": JianyingRelinkAdapter,
}


def get_adapter(project_type: str) -> ProjectRelinkAdapter:
    """Get an adapter instance for the given project type."""
    cls = ADAPTERS.get(project_type)
    if not cls:
        raise ValueError(
            f"Unsupported project type: {project_type}. "
            f"Supported: {list(ADAPTERS.keys())}"
        )
    return cls()
