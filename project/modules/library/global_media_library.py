#!/usr/bin/env python3
"""Global media library for semantic analysis and selection."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from modules.step1_material_analysis.video_asset_toolkit import VideoAssetToolkit
except Exception as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(f"无法导入 VideoAssetToolkit: {exc}") from exc

_gml_logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_LIBRARY_DIR = REPO_ROOT / ".video_library"
DEFAULT_LIBRARY_DB = DEFAULT_LIBRARY_DIR / "library.db"
DEFAULT_CACHE_DIR = DEFAULT_LIBRARY_DIR / "cache" / "gdrive"

from modules.library.maintenance.fingerprint import FingerprintMixin
from modules.library.integrations.gdrive import GDriveMixin
from modules.library.maintenance.duplicate_detection import DuplicateDetectionMixin
from modules.library.maintenance.path_relink import PathRelinkMixin
from modules.library.tagging.tag_manager import TagManagerMixin
from modules.library.tagging.auto_tagger import AutoTaggerMixin
from modules.library.core.core_mixin import CoreMixin
from modules.library.db.schema import SchemaMixin
from modules.library._constants import *  # noqa: F403 — shared constants
from modules.library._constants import (  # noqa: F401 — private constants need explicit import
    _KIND_TO_SLOT, _TOPCATEGORY_TO_CODE, _TAG_CATEGORY_TO_SLOT,
    _FIELD_TO_SLOT, _SEED_DATA_DIR,
)



class GlobalMediaLibrary(SchemaMixin, CoreMixin, FingerprintMixin, GDriveMixin, DuplicateDetectionMixin, PathRelinkMixin, TagManagerMixin, AutoTaggerMixin):
    def __init__(self, db_path: Optional[Path] = None, cache_dir: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_LIBRARY_DB)
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._toolkit: Optional[VideoAssetToolkit] = None
        self._relink_checked: Dict[str, float] = {}
        self._semantic_refresh_checked: Dict[str, float] = {}
        self._vector_cache: Dict[str, Any] = {
            "model": "",
            "updated_at": "",
            "uids": [],
            "matrix": None,
        }
        self._query_embedding_cache: Dict[str, Dict[str, Any]] = {}
        self._init_db()

    # ------------------------------------------------------------------
    # DB basics

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        # WAL 提升并发读写能力，降低搜索与入库互相阻塞概率。
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            pass
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # DB schema init (_init_db, seeds, migrations) → SchemaMixin (db/schema.py)

    def get_assets(self, uids: List[str]) -> List[Dict]:
        if not uids:
            return []

        placeholder = ",".join("?" for _ in uids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT uid, filename, sha256, size_bytes, primary_path, source_type, duration, resolution,
                       quality_score, scene_description, mood, objects_json,
                       semantic_json, semantic_text, keywords_json, updated_at,
                       gps_latitude, gps_longitude
                FROM assets
                WHERE uid IN ({placeholder})
                """,
                tuple(uids),
            ).fetchall()

            by_uid = {}
            for row in rows:
                best_path = self._best_existing_path(
                    conn,
                    row["uid"],
                    row["primary_path"],
                    filename=row["filename"],
                    sha256=row["sha256"],
                    size_bytes=row["size_bytes"],
                )
                objects = []
                try:
                    objects = json.loads(row["objects_json"] or "[]")
                except Exception:
                    objects = []
                semantic = self._safe_json_loads(row["semantic_json"], {})
                semantic_keywords = self._safe_json_loads(row["keywords_json"], [])
                by_uid[row["uid"]] = {
                    "uid": row["uid"],
                    "filename": row["filename"],
                    "path": best_path,
                    "asset_kind": self._infer_asset_kind(row["filename"], best_path or row["primary_path"]),
                    "available": bool(best_path and Path(best_path).exists()),
                    "source_type": row["source_type"],
                    "duration": row["duration"],
                    "resolution": row["resolution"],
                    "quality_score": row["quality_score"],
                    "scene_description": row["scene_description"],
                    "mood": row["mood"],
                    "objects": objects,
                    "semantic": semantic,
                    "semantic_keywords": semantic_keywords,
                    "semantic_dimensions_count": len(semantic.keys()) if isinstance(semantic, dict) else 0,
                    "semantic_dimension_names": list(semantic.keys()) if isinstance(semantic, dict) else [],
                    "updated_at": row["updated_at"],
                    "gps_latitude": row["gps_latitude"],
                    "gps_longitude": row["gps_longitude"],
                    "thumbnail_url": f"/api/library/thumbnail/{row['uid']}" if self.thumbnail_path(row["uid"]) else None,
                }

            return [by_uid[uid] for uid in uids if uid in by_uid]

    def build_workflow_materials(self, uids: List[str]) -> Dict:
        if not uids:
            return {}

        placeholder = ",".join("?" for _ in uids)
        materials: Dict = {}

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT uid, filename, sha256, size_bytes, primary_path, analysis_json, semantic_json, keywords_json, updated_at FROM assets WHERE uid IN ({placeholder})",
                tuple(uids),
            ).fetchall()

            for row in rows:
                path = self._best_existing_path(
                    conn,
                    row["uid"],
                    row["primary_path"],
                    filename=row["filename"],
                    sha256=row["sha256"],
                    size_bytes=row["size_bytes"],
                )
                if not path:
                    continue
                if self._infer_asset_kind(row["filename"], path) != "video":
                    continue

                analysis = {}
                try:
                    analysis = json.loads(row["analysis_json"] or "{}")
                except Exception:
                    analysis = {}
                semantic = self._safe_json_loads(row["semantic_json"], {})
                semantic_keywords = self._safe_json_loads(row["keywords_json"], [])

                analysis.setdefault("metadata", {})
                analysis["metadata"]["path"] = path

                materials[row["uid"]] = {
                    "filename": row["filename"],
                    "path": path,
                    "asset_kind": self._infer_asset_kind(row["filename"], path),
                    "hash": row["uid"],
                    "analysis": analysis,
                    "semantic": semantic if isinstance(semantic, dict) else {},
                    "semantic_keywords": semantic_keywords if isinstance(semantic_keywords, list) else [],
                    "timestamp": row["updated_at"],
                }

        return materials

    def stats(self) -> Dict:
        runtime = self._embedding_runtime_status()
        with self._connect() as conn:
            total_assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            video_assets = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE lower(filename) GLOB '*.mp4' OR lower(filename) GLOB '*.mov' OR lower(filename) GLOB '*.avi' OR lower(filename) GLOB '*.mkv' OR lower(filename) GLOB '*.m4v' OR lower(filename) GLOB '*.hevc' OR lower(filename) GLOB '*.flv' OR lower(filename) GLOB '*.wmv'"
            ).fetchone()[0]
            image_assets = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE lower(filename) GLOB '*.jpg' OR lower(filename) GLOB '*.jpeg' OR lower(filename) GLOB '*.png' OR lower(filename) GLOB '*.webp' OR lower(filename) GLOB '*.bmp' OR lower(filename) GLOB '*.tif' OR lower(filename) GLOB '*.tiff' OR lower(filename) GLOB '*.heic'"
            ).fetchone()[0]
            total_locations = conn.execute("SELECT COUNT(*) FROM asset_locations").fetchone()[0]
            local_assets = conn.execute("SELECT COUNT(*) FROM assets WHERE source_type='local'").fetchone()[0]
            gdrive_assets = conn.execute("SELECT COUNT(*) FROM assets WHERE source_type='gdrive'").fetchone()[0]
            semantic_ready_assets = conn.execute(
                """
                SELECT COUNT(*)
                FROM assets
                WHERE semantic_version = ?
                  AND semantic_json IS NOT NULL
                  AND semantic_json != ''
                """,
                (SEMANTIC_SCHEMA_VERSION,),
            ).fetchone()[0]
            semantic_pending_assets = conn.execute(
                """
                SELECT COUNT(*)
                FROM assets
                WHERE semantic_version IS NULL
                   OR semantic_version != ?
                   OR semantic_json IS NULL
                   OR semantic_json = ''
                """,
                (SEMANTIC_SCHEMA_VERSION,),
            ).fetchone()[0]
            available_assets = conn.execute(
                """
                SELECT COUNT(DISTINCT uid)
                FROM asset_locations
                WHERE is_available=1
                """
            ).fetchone()[0]
            embedding_ready_assets = conn.execute(
                """
                SELECT COUNT(*)
                FROM asset_embeddings
                WHERE embedding_version = ?
                """,
                (EMBEDDING_SCHEMA_VERSION,),
            ).fetchone()[0]

        return {
            "db_path": str(self.db_path),
            "cache_dir": str(self.cache_dir),
            "total_assets": total_assets,
            "video_assets": video_assets,
            "image_assets": image_assets,
            "total_locations": total_locations,
            "available_assets": available_assets,
            "local_assets": local_assets,
            "gdrive_assets": gdrive_assets,
            "semantic_schema_version": SEMANTIC_SCHEMA_VERSION,
            "semantic_dimensions_supported": len(SEMANTIC_DIMENSIONS),
            "semantic_ready_assets": semantic_ready_assets,
            "semantic_pending_assets": semantic_pending_assets,
            "embedding_enabled": bool(runtime.get("enabled", False)),
            "embedding_status": runtime.get("reason", ""),
            "embedding_status_message": runtime.get("message", ""),
            "embedding_model": self._embedding_model(),
            "embedding_version": EMBEDDING_SCHEMA_VERSION,
            "embedding_ready_assets": embedding_ready_assets,
            "embedding_pending_assets": max(0, int(total_assets) - int(embedding_ready_assets)),
            "hybrid_search_enabled": True,
        }


    # Path relink APIs (add_known_root .. get_project_missing_stats) → PathRelinkMixin
    # backfill_fingerprints, get_fingerprint_health → FingerprintMixin
