"""
v0.7 Phase C-2 — Project Relink Adapter ABC + Jianying implementation.

Provides a pluggable adapter interface for parsing and applying relink maps
across different NLE project formats.  Only Jianying is implemented for now;
adding FCPXML / EDL / Resolve in future phases requires implementing the
ProjectRelinkAdapter ABC.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

import json


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
            with open(project_path, "r", encoding="utf-8") as f:
                draft = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
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
        with open(project_path, "r", encoding="utf-8") as f:
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
        with open(project_path, "r", encoding="utf-8") as f:
            draft = json.load(f)

        applied = 0
        materials = draft.get("materials", {})
        for category in ("videos", "audios"):
            for entry in materials.get(category, []):
                entry_path = (entry.get("path") or "").strip()
                if entry_path in path_map:
                    entry["path"] = path_map[entry_path]
                    applied += 1

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)

        return {"applied": applied, "skipped": len(path_map) - applied}

    # ── get_version_info ──

    def get_version_info(self, project_path: str) -> Dict:
        try:
            with open(project_path, "r", encoding="utf-8") as f:
                draft = json.load(f)
            return {
                "app_version": draft.get("app_version"),
                "draft_version": draft.get("version"),
            }
        except Exception:
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
