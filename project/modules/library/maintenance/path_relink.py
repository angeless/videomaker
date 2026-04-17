"""Path relink and project relink mixin for GlobalMediaLibrary.

Extracted from global_media_library.py — contains asset relocation,
known roots management, availability scanning, and the complete
project relink workflow (create/bind/apply/verify/handover).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from modules.library.project_relink_adapter import get_adapter as _get_relink_adapter
except ImportError:
    _get_relink_adapter = None

logger = logging.getLogger(__name__)


# Round-13 P1: os.walk accepts any directory path, but walking /, /System,
# /etc, /proc, /dev etc. is both a DoS (gigabytes of I/O + SHA256) and an
# information disclosure primitive (attacker can confirm existence of
# known files via timing / hash comparison).
#
# Denylist known-dangerous roots. macOS + Linux + Windows system paths
# are all excluded regardless of case.
_UNSAFE_WALK_ROOTS = {
    "/",
    "/System", "/Library", "/bin", "/sbin", "/etc", "/var", "/usr",
    "/proc", "/sys", "/dev", "/boot", "/root",
    "/private", "/private/var", "/private/etc", "/private/tmp",
    "C:\\", "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
}


def _is_safe_walk_root(root: Path) -> bool:
    """Reject system paths to prevent walk over / or /etc etc."""
    try:
        resolved = root.resolve()
    except OSError:
        return False
    try:
        s = str(resolved)
    except Exception:
        return False
    if s in _UNSAFE_WALK_ROOTS:
        return False
    # Prefix-match common system trees. Note: /private/var/folders/ on macOS
    # is where user tempfiles live (tmp_path fixtures, etc.) — we allow that.
    # Only /private/var/{db,root,log,...} is system.
    for deny in ("/System/", "/etc/", "/proc/", "/sys/", "/dev/",
                 "/private/etc/",
                 "/private/var/db/", "/private/var/root/", "/private/var/log/",
                 "C:\\Windows\\", "C:\\Program Files\\"):
        if s.startswith(deny):
            return False
    return True


class PathRelinkMixin:
    """Methods related to asset path relocation and project relinking."""

    def _candidate_local_roots(self, conn: sqlite3.Connection) -> List[Path]:
        rows = conn.execute(
            """
            SELECT DISTINCT source_ref, path
            FROM asset_locations
            WHERE source_type='local'
            """
        ).fetchall()
        roots: List[Path] = []
        seen = set()

        def _push_dir(p: Path):
            try:
                resolved = p.expanduser().resolve()
            except Exception:
                return
            if not resolved.exists() or not resolved.is_dir():
                return
            key = str(resolved)
            if key in seen:
                return
            seen.add(key)
            roots.append(resolved)

        for row in rows:
            raw_ref = str(row["source_ref"] or "").strip()
            if raw_ref:
                _push_dir(Path(raw_ref))

            raw_path = str(row["path"] or "").strip()
            if raw_path:
                p = Path(raw_path).expanduser()
                if p.exists() and p.is_file():
                    _push_dir(p.parent)
                elif p.exists() and p.is_dir():
                    _push_dir(p)

        expanded = list(roots)
        for root in expanded:
            parent = root.parent
            grand = parent.parent if parent != root else parent
            _push_dir(parent)
            _push_dir(grand)
            if root.name.lower() in {"dcim", "clips", "videos", "footage"}:
                _push_dir(parent)

        _push_dir(Path.cwd())

        return expanded + [p for p in roots if p not in expanded]

    def _try_relocate_asset(
        self,
        conn: sqlite3.Connection,
        uid: str,
        filename: Optional[str],
        sha256: Optional[str],
        size_bytes: Optional[int] = None,
    ) -> Optional[str]:
        if not filename or not sha256:
            return None

        now_ts = time.time()
        last_checked = self._relink_checked.get(uid, 0.0)
        if now_ts - last_checked < 30.0:
            return None
        self._relink_checked[uid] = now_ts

        roots = self._candidate_local_roots(conn)
        if not roots:
            return None

        checked = 0
        max_candidates = 2400
        deadline = time.time() + 8.0
        target_size = int(size_bytes) if size_bytes is not None else None

        for root in roots[:14]:
            if time.time() > deadline:
                return None
            # Reject system paths to avoid O(disk) I/O + info disclosure.
            if not _is_safe_walk_root(root):
                logger.warning("path_relink: refusing to walk system root %s", root)
                continue
            try:
                walker = os.walk(root)
            except Exception:
                continue
            for cur_dir, _, files in walker:
                if time.time() > deadline:
                    return None
                if filename not in files:
                    continue
                cand = Path(cur_dir) / filename
                checked += 1
                if checked > max_candidates:
                    return None
                if time.time() > deadline:
                    return None

                try:
                    stat = cand.stat()
                except Exception:
                    continue
                if target_size is not None and int(stat.st_size) != target_size:
                    continue
                try:
                    cand_sha = self._compute_sha256(cand)
                except Exception:
                    continue
                if cand_sha != sha256:
                    continue

                resolved = str(cand.resolve())
                try:
                    self._upsert_location(conn, uid, resolved, "local", str(root))
                    conn.execute(
                        """
                        UPDATE assets
                        SET primary_path=?, source_type='local', updated_at=?
                        WHERE uid=?
                        """,
                        (resolved, self._now(), uid),
                    )
                except sqlite3.OperationalError as exc:
                    if "database is locked" in str(exc).lower():
                        return None
                    raise
                return resolved
        return None

    def _best_existing_path(
        self,
        conn: sqlite3.Connection,
        uid: str,
        fallback: Optional[str],
        filename: Optional[str] = None,
        sha256: Optional[str] = None,
        size_bytes: Optional[int] = None,
        allow_relocate: bool = True,
        update_availability: bool = True,
    ) -> Optional[str]:
        rows = conn.execute(
            """
            SELECT path, source_type
            FROM asset_locations
            WHERE uid = ?
            ORDER BY CASE WHEN source_type='local' THEN 0 ELSE 1 END, id DESC
            """,
            (uid,),
        ).fetchall()

        for row in rows:
            p = Path(row["path"])
            exists = p.exists()
            if update_availability:
                try:
                    conn.execute(
                        "UPDATE asset_locations SET is_available=?, last_seen_at=? WHERE path=?",
                        (1 if exists else 0, self._now(), row["path"]),
                    )
                except sqlite3.OperationalError as exc:
                    if "database is locked" not in str(exc).lower():
                        raise
            if exists:
                return str(p)

        if fallback and Path(fallback).exists():
            return fallback
        if not allow_relocate:
            return fallback
        relocated = self._try_relocate_asset(
            conn=conn,
            uid=uid,
            filename=filename,
            sha256=sha256,
            size_bytes=size_bytes,
        )
        if relocated:
            return relocated
        return fallback

    # ── Phase 3: structured tag recall ──


    def add_known_root(self, root_path: str, label: Optional[str] = None) -> Dict:
        """Register a known media root directory."""
        rp = str(Path(root_path).resolve())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO known_media_roots (root_path, label)
                VALUES (?, ?)
                ON CONFLICT(root_path) DO UPDATE SET
                    label=COALESCE(excluded.label, known_media_roots.label),
                    is_active=1
                """,
                (rp, label),
            )
            row = conn.execute(
                "SELECT * FROM known_media_roots WHERE root_path=?", (rp,)
            ).fetchone()
            return dict(row) if row else {"root_path": rp, "label": label}

    def list_known_roots(self, active_only: bool = True) -> List[Dict]:
        """List all known media root directories."""
        with self._connect() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM known_media_roots WHERE is_active=1 ORDER BY root_id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM known_media_roots ORDER BY root_id"
                ).fetchall()
            return [dict(r) for r in rows]

    def remove_known_root(self, root_id: int) -> bool:
        """Soft-delete a known media root by setting is_active=0."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE known_media_roots SET is_active=0 WHERE root_id=?",
                (root_id,),
            )
            return conn.execute(
                "SELECT COUNT(*) FROM known_media_roots WHERE root_id=? AND is_active=0",
                (root_id,),
            ).fetchone()[0] > 0

    # ------------------------------------------------------------------
    # v0.7 – Path change audit log
    # ------------------------------------------------------------------

    def _log_path_change(
        self,
        conn: sqlite3.Connection,
        uid: str,
        old_path: Optional[str],
        new_path: Optional[str],
        change_type: str,
        source: str = "system",
    ):
        """Record a path change event in path_change_log."""
        conn.execute(
            """
            INSERT INTO path_change_log (uid, old_path, new_path, change_type, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (uid, old_path, new_path, change_type, source),
        )

    # ------------------------------------------------------------------
    # v0.7 – Asset availability scanning
    # ------------------------------------------------------------------

    def scan_asset_availability(self) -> Dict:
        """
        Batch-check all asset_locations for file existence.
        Updates is_available flag and logs path changes.

        Returns summary: {checked, available, unavailable, changed}.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, uid, path, is_available FROM asset_locations"
            ).fetchall()

            checked = 0
            available = 0
            unavailable = 0
            changed = 0

            for row in rows:
                loc_id = row["id"]
                uid = row["uid"]
                loc_path = row["path"]
                was_available = bool(row["is_available"])
                is_now_available = Path(loc_path).exists()

                checked += 1
                if is_now_available:
                    available += 1
                else:
                    unavailable += 1

                if was_available and not is_now_available:
                    conn.execute(
                        "UPDATE asset_locations SET is_available=0 WHERE id=?",
                        (loc_id,),
                    )
                    self._log_path_change(conn, uid, loc_path, None, "unavailable", "batch_scan")
                    changed += 1
                elif not was_available and is_now_available:
                    conn.execute(
                        "UPDATE asset_locations SET is_available=1, last_seen_at=? WHERE id=?",
                        (self._now(), loc_id),
                    )
                    self._log_path_change(conn, uid, None, loc_path, "added", "batch_scan")
                    changed += 1

        return {
            "checked": checked,
            "available": available,
            "unavailable": unavailable,
            "changed": changed,
        }

    # ------------------------------------------------------------------
    # v0.7 – Batch relocate
    # ------------------------------------------------------------------

    def batch_relocate(self, root_paths: Optional[List[str]] = None) -> Dict:
        """
        Attempt to relocate all unavailable assets by searching known roots
        and optionally additional root_paths.

        IMPORTANT design constraint:
        - Only sha256 EXACT match triggers automatic relink (updates primary_path).
        - content_fingerprint similarity is NEVER used for auto-relocation.
          Fingerprint-based candidates require future human confirmation (Phase B).
        - Every successful relocation MUST update assets.primary_path AND
          write to path_change_log (incomplete without both).

        Returns: {attempted, relocated, failed, details: [{uid, old_path, new_path}]}
        """
        with self._connect() as conn:
            # Gather unavailable assets
            unavailable = conn.execute(
                """
                SELECT DISTINCT a.uid, a.filename, a.sha256, a.size_bytes, a.primary_path
                FROM assets a
                JOIN asset_locations al ON a.uid = al.uid
                WHERE al.is_available = 0
                """
            ).fetchall()

            if not unavailable:
                return {"attempted": 0, "relocated": 0, "failed": 0, "details": []}

            # Build search roots from known_media_roots + provided root_paths
            search_roots = []
            known = conn.execute(
                "SELECT root_path FROM known_media_roots WHERE is_active=1"
            ).fetchall()
            for kr in known:
                p = Path(kr["root_path"])
                if p.is_dir():
                    search_roots.append(p)
            if root_paths:
                for rp in root_paths:
                    p = Path(rp)
                    if p.is_dir() and p not in search_roots:
                        search_roots.append(p)

            # Also include candidate roots from existing locations
            candidate_roots = self._candidate_local_roots(conn)
            for cr in candidate_roots:
                if cr not in search_roots:
                    search_roots.append(cr)

            attempted = 0
            relocated = 0
            failed = 0
            details = []

            for row in unavailable:
                uid = row["uid"]
                filename = row["filename"]
                sha256_val = row["sha256"]
                size_bytes = row["size_bytes"]
                old_primary = row["primary_path"]

                if not filename or not sha256_val:
                    failed += 1
                    continue

                attempted += 1
                found_path = None
                target_size = int(size_bytes) if size_bytes is not None else None

                for root in search_roots[:20]:
                    if not _is_safe_walk_root(Path(root)):
                        logger.warning(
                            "batch_relocate: refusing to walk system root %s", root
                        )
                        continue
                    try:
                        for cur_dir, _, files in os.walk(root):
                            if filename not in files:
                                continue
                            cand = Path(cur_dir) / filename
                            try:
                                stat = cand.stat()
                            except Exception:
                                continue
                            if target_size is not None and int(stat.st_size) != target_size:
                                continue
                            try:
                                cand_sha = self._compute_sha256(cand)
                            except Exception:
                                continue
                            if cand_sha == sha256_val:
                                found_path = str(cand.resolve())
                                break
                    except Exception:
                        continue
                    if found_path:
                        break

                if found_path:
                    self._upsert_location(conn, uid, found_path, "local", None)
                    conn.execute(
                        "UPDATE assets SET primary_path=?, updated_at=? WHERE uid=?",
                        (found_path, self._now(), uid),
                    )
                    self._log_path_change(conn, uid, old_primary, found_path, "relocated", "batch_scan")
                    relocated += 1
                    details.append({"uid": uid, "old_path": old_primary, "new_path": found_path})
                else:
                    failed += 1

        return {
            "attempted": attempted,
            "relocated": relocated,
            "failed": failed,
            "details": details,
        }

    # ------------------------------------------------------------------
    # detect_duplicates, list_duplicate_groups, resolve/ignore/set_duplicate_* → DuplicateDetectionMixin

    def list_unavailable_assets(self) -> List[Dict]:
        """List all asset locations that are currently unavailable."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT al.id, al.uid, al.path, al.source_type, al.last_seen_at,
                       a.filename, a.primary_path
                FROM asset_locations al
                JOIN assets a ON al.uid = a.uid
                WHERE al.is_available = 0
                ORDER BY al.last_seen_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # v0.7 – Relink report
    # ------------------------------------------------------------------

    def relink_report(self, uids: Optional[List[str]] = None, since: Optional[str] = None) -> List[Dict]:
        """
        Get path change history for specified assets.

        Args:
            uids: list of asset uids (None = all)
            since: ISO datetime string — only return changes after this time

        Returns: [{uid, changes: [{change_id, old_path, new_path, change_type, source, created_at}]}]
        """
        with self._connect() as conn:
            if uids:
                placeholders = ",".join("?" for _ in uids)
                if since:
                    rows = conn.execute(
                        f"""
                        SELECT * FROM path_change_log
                        WHERE uid IN ({placeholders}) AND created_at > ?
                        ORDER BY uid, created_at
                        """,
                        (*uids, since),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"""
                        SELECT * FROM path_change_log
                        WHERE uid IN ({placeholders})
                        ORDER BY uid, created_at
                        """,
                        tuple(uids),
                    ).fetchall()
            else:
                if since:
                    rows = conn.execute(
                        "SELECT * FROM path_change_log WHERE created_at > ? ORDER BY uid, created_at",
                        (since,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM path_change_log ORDER BY uid, created_at"
                    ).fetchall()

            # Group by uid
            from collections import defaultdict
            grouped: Dict[str, List[Dict]] = defaultdict(list)
            for r in rows:
                grouped[r["uid"]].append(dict(r))

            return [{"uid": uid, "changes": changes} for uid, changes in grouped.items()]

    # ------------------------------------------------------------------
    # v0.7 Phase C-1 – Project relink (Jianying工程自动relink)
    # ------------------------------------------------------------------

    def _match_path_to_uid(
        self,
        conn: sqlite3.Connection,
        path: str,
        filename: str,
        size_hint: Optional[int] = None,
    ) -> Tuple[Optional[str], str, float, str]:
        """
        Reverse-lookup: given a file path and filename, find the asset uid.

        Returns (uid, match_type, confidence, reason).
        Match priority:
          1. Exact path in asset_locations  → confidence 1.0
          2. primary_path in assets         → confidence 1.0
          3. filename in assets with secondary validation (size check)
             - unique filename match + size matches → confidence 0.9
             - unique filename match, size unknown  → confidence 0.7
             - multiple filename matches, one size matches → confidence 0.6
             - multiple filename matches, no size info → confidence 0.3
        """
        # 1. Exact path match in asset_locations
        row = conn.execute(
            "SELECT uid FROM asset_locations WHERE path = ?", (path,)
        ).fetchone()
        if row:
            return (row["uid"], "path", 1.0, "exact_path_in_locations")

        # 2. primary_path match in assets
        row = conn.execute(
            "SELECT uid FROM assets WHERE primary_path = ?", (path,)
        ).fetchone()
        if row:
            return (row["uid"], "path", 1.0, "primary_path_match")

        # 3. filename match with secondary validation
        if filename:
            rows = conn.execute(
                "SELECT uid, size_bytes FROM assets WHERE filename = ?", (filename,)
            ).fetchall()

            if not rows:
                return (None, "none", 0.0, "no_match")

            if len(rows) == 1:
                # Unique filename match
                candidate = rows[0]
                if size_hint and candidate["size_bytes"]:
                    if size_hint == candidate["size_bytes"]:
                        return (candidate["uid"], "filename", 0.9, "unique_filename_size_confirmed")
                    else:
                        # Size mismatch — likely a different file with the same name
                        return (None, "none", 0.0, "filename_match_size_mismatch")
                # No size info to validate — lower confidence
                return (candidate["uid"], "filename", 0.7, "unique_filename_no_size_check")

            # Multiple filename matches — try size-based disambiguation
            if size_hint:
                size_matches = [r for r in rows if r["size_bytes"] == size_hint]
                if len(size_matches) == 1:
                    return (size_matches[0]["uid"], "filename", 0.6, "filename_multi_size_disambiguated")
                elif len(size_matches) > 1:
                    # Multiple size matches — ambiguous, pick first but low confidence
                    return (size_matches[0]["uid"], "filename", 0.3, "filename_multi_size_ambiguous")
            # Multiple filename matches, no size info — too risky
            return (None, "none", 0.0, "filename_multi_no_size")

        return (None, "none", 0.0, "no_match")

    def parse_project_references(self, project_path: str, project_type: str = "jianying") -> List[Dict]:
        """
        Parse media references from a project file.

        Delegates to the appropriate ProjectRelinkAdapter.

        Returns: [{asset_name, old_path, source_ref, media_type}]
        """
        p = Path(project_path)
        if not p.exists():
            return []
        try:
            adapter = _get_relink_adapter(project_type)
            return adapter.parse_references(str(p))
        except Exception:
            return []

    def validate_project(self, project_path: str, project_type: str = "jianying") -> Dict:
        """
        Validate a project file structure before analysis.

        Delegates to the appropriate ProjectRelinkAdapter.

        Returns: {valid, errors, warnings, version_info}
        """
        p = Path(project_path)
        if not p.exists():
            return {"valid": False, "errors": [f"File not found: {project_path}"], "warnings": [], "version_info": {}}
        try:
            adapter = _get_relink_adapter(project_type)
            return adapter.validate(str(p))
        except Exception as exc:
            return {"valid": False, "errors": [str(exc)], "warnings": [], "version_info": {}}

    def build_project_relink_map(self, project_path: str, project_type: str = "jianying") -> Dict:
        """
        Build a structured relink map for a project.

        For each media reference in the project, determine:
        - stable: old_path still exists on disk
        - relinked: old_path broken but new path found via library
        - missing: uid found in library but no available path
        - unmatched: cannot match to any library asset

        Returns: {
            project_path, project_type,
            summary: {total_refs, stable_refs, changed_refs, missing_refs, unmatched_refs},
            items: [{uid, asset_name, source_ref, old_path, new_path, status,
                     fingerprint_match_type, media_type, match_confidence, reason}]
        }
        """
        refs = self.parse_project_references(project_path, project_type)
        items: List[Dict] = []

        # Build size map from parsed refs (adapter may return size_bytes) + raw JSON fallback
        size_map: Dict[str, int] = {}
        for ref in refs:
            sz = ref.get("size_bytes")
            if sz and isinstance(sz, (int, float)) and sz > 0:
                size_map[ref["old_path"]] = int(sz)
        # Also try to extract sizes from raw project JSON (e.g. Jianying "size" / "file_size" fields)
        try:
            with open(project_path, "r", encoding="utf-8") as f:
                draft = json.load(f)
            for category in ("videos", "audios"):
                for entry in draft.get("materials", {}).get(category, []):
                    p = (entry.get("path") or "").strip()
                    sz = entry.get("size") or entry.get("file_size") or 0
                    if p and p not in size_map and isinstance(sz, (int, float)) and sz > 0:
                        size_map[p] = int(sz)
        except Exception:
            pass

        with self._connect() as conn:
            for ref in refs:
                old_path = ref["old_path"]
                asset_name = ref["asset_name"]
                source_ref = ref.get("source_ref", "")
                media_type = ref.get("media_type", "")

                # 1. Check if old_path still exists
                if Path(old_path).exists():
                    items.append({
                        "uid": None,
                        "asset_name": asset_name,
                        "source_ref": source_ref,
                        "old_path": old_path,
                        "new_path": None,
                        "status": "stable",
                        "fingerprint_match_type": None,
                        "media_type": media_type,
                        "match_confidence": 1.0,
                        "reason": "path_exists",
                    })
                    continue

                # 2-4. Try to match to library uid (with size hint for secondary validation)
                size_hint = size_map.get(old_path)
                uid, match_type, confidence, reason = self._match_path_to_uid(
                    conn, old_path, asset_name, size_hint=size_hint
                )

                if uid is None:
                    # unmatched
                    items.append({
                        "uid": None,
                        "asset_name": asset_name,
                        "source_ref": source_ref,
                        "old_path": old_path,
                        "new_path": None,
                        "status": "unmatched",
                        "fingerprint_match_type": "none",
                        "media_type": media_type,
                        "match_confidence": 0.0,
                        "reason": reason,
                    })
                    continue

                # 5. Found uid — get asset info for _best_existing_path
                asset_row = conn.execute(
                    "SELECT filename, sha256, size_bytes, primary_path FROM assets WHERE uid = ?",
                    (uid,),
                ).fetchone()

                if asset_row:
                    best = self._best_existing_path(
                        conn,
                        uid,
                        fallback=old_path,
                        filename=asset_row["filename"],
                        sha256=asset_row["sha256"],
                        size_bytes=asset_row["size_bytes"],
                        allow_relocate=True,
                        update_availability=False,
                    )
                else:
                    best = None

                if best and Path(best).exists() and best != old_path:
                    items.append({
                        "uid": uid,
                        "asset_name": asset_name,
                        "source_ref": source_ref,
                        "old_path": old_path,
                        "new_path": best,
                        "status": "relinked",
                        "fingerprint_match_type": match_type,
                        "media_type": media_type,
                        "match_confidence": confidence,
                        "reason": reason,
                    })
                else:
                    items.append({
                        "uid": uid,
                        "asset_name": asset_name,
                        "source_ref": source_ref,
                        "old_path": old_path,
                        "new_path": None,
                        "status": "missing",
                        "fingerprint_match_type": match_type,
                        "media_type": media_type,
                        "match_confidence": confidence,
                        "reason": reason,
                    })

        # Build summary
        stable = sum(1 for i in items if i["status"] == "stable")
        relinked = sum(1 for i in items if i["status"] == "relinked")
        missing = sum(1 for i in items if i["status"] == "missing")
        unmatched = sum(1 for i in items if i["status"] == "unmatched")

        return {
            "project_path": str(project_path),
            "project_type": project_type,
            "summary": {
                "total_refs": len(items),
                "stable_refs": stable,
                "changed_refs": relinked,
                "missing_refs": missing,
                "unmatched_refs": unmatched,
            },
            "items": items,
        }

    def create_project_relink_job(self, project_path: str, project_type: str = "jianying") -> Dict:
        """
        Create a relink analysis job, run build_project_relink_map, and persist results.

        Returns: {job_id, project_path, project_type, status, summary, items}
        """
        p = Path(project_path)
        if not p.exists():
            return {"error": f"Project file not found: {project_path}"}

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO project_relink_job (project_path, project_type, status)
                VALUES (?, ?, 'running')
                """,
                (str(p), project_type),
            )
            job_id = cursor.lastrowid

        try:
            # Extract version info via adapter
            version_info_str = None
            try:
                adapter = _get_relink_adapter(project_type)
                vi = adapter.get_version_info(str(p))
                if vi:
                    version_info_str = json.dumps(vi, ensure_ascii=False)
            except Exception:
                pass

            result = self.build_project_relink_map(str(p), project_type)
            summary = result["summary"]
            items = result["items"]

            with self._connect() as conn:
                for item in items:
                    conn.execute(
                        """
                        INSERT INTO project_relink_item
                            (job_id, uid, asset_name, old_path, new_path, status,
                             source_ref, fingerprint_match_type, media_type,
                             match_confidence, reason, applied)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            job_id,
                            item.get("uid"),
                            item.get("asset_name"),
                            item.get("old_path"),
                            item.get("new_path"),
                            item["status"],
                            item.get("source_ref"),
                            item.get("fingerprint_match_type"),
                            item.get("media_type"),
                            item.get("match_confidence"),
                            item.get("reason"),
                        ),
                    )
                conn.execute(
                    """
                    UPDATE project_relink_job
                    SET status='done',
                        total_refs=?, stable_refs=?, changed_refs=?,
                        missing_refs=?, unmatched_refs=?,
                        result_json=?, version_info=?,
                        updated_at=?
                    WHERE job_id=?
                    """,
                    (
                        summary["total_refs"],
                        summary["stable_refs"],
                        summary["changed_refs"],
                        summary["missing_refs"],
                        summary["unmatched_refs"],
                        json.dumps(result, ensure_ascii=False),
                        version_info_str,
                        self._now(),
                        job_id,
                    ),
                )

            return {
                "job_id": job_id,
                "project_path": str(p),
                "project_type": project_type,
                "status": "done",
                "summary": summary,
                "items": items,
            }

        except Exception as exc:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE project_relink_job SET status='failed', error_message=?, updated_at=? WHERE job_id=?",
                    (str(exc), self._now(), job_id),
                )
            return {"error": str(exc), "job_id": job_id, "status": "failed"}

    def get_project_relink_job(self, job_id: int) -> Dict:
        """Get a relink job with its items."""
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? ORDER BY item_id",
                (job_id,),
            ).fetchall()

            job = dict(job_row)
            job.pop("result_json", None)  # Don't send full blob in normal queries
            job["items"] = [self._item_with_effective_fields(r) for r in items]
            return job

    def export_project_relink_map(self, job_id: int) -> Dict:
        """Export a relink job as a standardized relink map for download."""
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT uid, asset_name, old_path, new_path, status, source_ref, "
                "fingerprint_match_type, media_type, match_confidence, reason, applied "
                "FROM project_relink_item WHERE job_id = ? ORDER BY item_id",
                (job_id,),
            ).fetchall()

            return {
                "project_path": job_row["project_path"],
                "project_type": job_row["project_type"],
                "summary": {
                    "total_refs": job_row["total_refs"],
                    "stable_refs": job_row["stable_refs"],
                    "changed_refs": job_row["changed_refs"],
                    "missing_refs": job_row["missing_refs"],
                    "unmatched_refs": job_row["unmatched_refs"],
                },
                "items": [dict(r) for r in items],
            }

    def list_project_relink_jobs(
        self, project_path: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> List[Dict]:
        """
        List recent relink jobs, optionally filtered by project_path.

        Returns list of job dicts (without items), ordered by created_at DESC.
        """
        with self._connect() as conn:
            cols = (
                "job_id, project_path, project_type, status, total_refs, "
                "stable_refs, changed_refs, missing_refs, unmatched_refs, "
                "apply_count, version_info, error_message, "
                "retry_of, retry_count, last_error_at, "
                "predecessor_job_id, handover_at, "
                "created_at, updated_at"
            )
            if project_path:
                rows = conn.execute(
                    f"SELECT {cols} FROM project_relink_job WHERE project_path = ? "
                    "ORDER BY job_id DESC LIMIT ? OFFSET ?",
                    (project_path, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {cols} FROM project_relink_job "
                    "ORDER BY job_id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [dict(r) for r in rows]

    def compare_project_relink_jobs(self, job_id_a: int, job_id_b: int) -> Dict:
        """
        Compare two relink jobs and return delta analysis.

        Tracks which items changed status between job A and job B:
        - newly_relinked: was missing/unmatched in A, now relinked in B
        - newly_missing: was stable/relinked in A, now missing/unmatched in B
        - still_unmatched: unmatched in both
        - status_changed: any status change

        Returns: {job_id_a, job_id_b, newly_relinked, newly_missing,
                  still_unmatched, status_changed, summary}
        """
        with self._connect() as conn:
            rows_a = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ?", (job_id_a,)
            ).fetchall()
            rows_b = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ?", (job_id_b,)
            ).fetchall()

        if not rows_a and not rows_b:
            return {"error": f"No items found for job_id {job_id_a} or {job_id_b}"}

        items_a = {i["old_path"]: dict(i) for i in rows_a}
        items_b = {i["old_path"]: dict(i) for i in rows_b}

        newly_relinked: List[Dict] = []
        newly_missing: List[Dict] = []
        still_unmatched: List[Dict] = []
        status_changed: List[Dict] = []

        all_paths = sorted(set(items_a.keys()) | set(items_b.keys()))
        for path in all_paths:
            a = items_a.get(path)
            b = items_b.get(path)
            sa = a["status"] if a else None
            sb = b["status"] if b else None
            name = (b or a or {}).get("asset_name", "")

            if sa != sb:
                entry = {"old_path": path, "status_a": sa, "status_b": sb, "asset_name": name}
                status_changed.append(entry)
                if sb == "relinked" and sa in (None, "missing", "unmatched"):
                    newly_relinked.append(entry)
                elif sb in ("missing", "unmatched") and sa in ("stable", "relinked"):
                    newly_missing.append(entry)
            elif sa == "unmatched" and sb == "unmatched":
                still_unmatched.append({"old_path": path, "asset_name": name})

        return {
            "job_id_a": job_id_a,
            "job_id_b": job_id_b,
            "newly_relinked": newly_relinked,
            "newly_missing": newly_missing,
            "still_unmatched": still_unmatched,
            "status_changed": status_changed,
            "summary": {
                "newly_relinked": len(newly_relinked),
                "newly_missing": len(newly_missing),
                "still_unmatched": len(still_unmatched),
                "total_changes": len(status_changed),
            },
        }

    def apply_project_relink(
        self,
        job_id: int,
        output_path: Optional[str] = None,
        force: bool = False,
        naming_rule: str = "default",
    ) -> Dict:
        """
        Apply relink results to a project copy.

        Safety rules (hardcoded, cannot be overridden):
        1. ONLY items with status='relinked' are processed.
        2. Output is ALWAYS written to a new file — original is NEVER modified.
        3. If output_path == project_path, it is rejected.
        4. new_path must exist on disk at apply time; stale entries are skipped.
        5. Each applied item is marked with applied=1, applied_at set.
        6. Idempotent: if all relinked items already applied, returns error (unless force=True).
        7. apply_count on job is incremented.

        Args:
            job_id:      ID of a 'done' relink job.
            output_path: Optional explicit output path. If None, auto-generated.
            force:       If True, skip idempotency guard and allow re-apply.
            naming_rule: "default" → {stem}_relinked_{job_id}{suffix}
                         "timestamped" → {stem}_relinked_{job_id}_{TS}{suffix}

        Returns: {output_path, applied, skipped, apply_detail}
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            if job_row["status"] != "done":
                return {"error": f"Job {job_id} status is '{job_row['status']}', expected 'done'"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? AND status = 'relinked'",
                (job_id,),
            ).fetchall()

        if not items:
            return {"output_path": None, "applied": 0, "skipped": 0}

        # Idempotency guard
        if not force:
            already_applied = all(item["applied"] == 1 for item in items)
            if already_applied:
                return {
                    "error": "All relinked items already applied. Use force=True to re-apply.",
                    "already_applied": True,
                }

        project_path = Path(job_row["project_path"])
        if not project_path.exists():
            return {"error": f"Original project file not found: {project_path}"}

        # Determine output path
        if not output_path:
            stem = project_path.stem
            suffix = project_path.suffix
            if naming_rule == "timestamped":
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = str(project_path.parent / f"{stem}_relinked_{job_id}_{ts}{suffix}")
            else:
                candidate = project_path.parent / f"{stem}_relinked_{job_id}{suffix}"
                if candidate.exists():
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_path = str(project_path.parent / f"{stem}_relinked_{job_id}_{ts}{suffix}")
                else:
                    output_path = str(candidate)

        out = Path(output_path).resolve()

        # Safety rule 3: never overwrite the original
        if out == project_path.resolve():
            return {"error": "output_path must differ from the original project file"}

        # D-1 hard rule #3: if output file exists and not force, conflict
        if out.exists() and not force:
            return {
                "error": f"Output file already exists: {out}. Use force=True to overwrite.",
                "output_conflict": True,
            }

        # Build old_path → (new_path, item_id, asset_name) mapping — ONLY relinked items
        path_map: Dict[str, Tuple[str, int, str]] = {}
        skipped_items: List[Dict] = []
        for item in items:
            old = item["old_path"]
            # D-2: prefer manual_new_path when manually bound
            new = item["manual_new_path"] or item["new_path"]
            item_id = item["item_id"]
            name = item["asset_name"] or ""
            # Safety rule 4: verify new_path still exists on disk
            if old and new and Path(new).exists():
                path_map[old] = (new, item_id, name)
            else:
                reason = "new_path does not exist" if new else "no new_path"
                skipped_items.append({"item_id": item_id, "old_path": old, "new_path": new, "asset_name": name, "reason": reason})

        # Delegate file rewriting to adapter
        project_type = job_row["project_type"] or "jianying"
        try:
            adapter = _get_relink_adapter(project_type)
            simple_map = {old: new for old, (new, _, _) in path_map.items()}
            adapter.apply_relink(str(project_path), str(out), simple_map)
        except Exception as exc:
            return {"error": f"Adapter apply failed: {exc}"}

        # Collect applied items detail
        applied_item_ids: List[int] = []
        applied_items_detail: List[Dict] = []
        for old_p, (new_p, item_id, name) in path_map.items():
            applied_item_ids.append(item_id)
            applied_items_detail.append({
                "item_id": item_id,
                "old_path": old_p,
                "new_path": new_p,
                "asset_name": name,
            })

        now = self._now()

        # Mark applied items in DB + increment apply_count
        with self._connect() as conn:
            if applied_item_ids:
                placeholders = ",".join("?" for _ in applied_item_ids)
                conn.execute(
                    f"UPDATE project_relink_item SET applied = 1, applied_at = ? WHERE item_id IN ({placeholders})",
                    [now] + applied_item_ids,
                )
            conn.execute(
                "UPDATE project_relink_job SET apply_count = apply_count + 1, updated_at = ? WHERE job_id = ?",
                (now, job_id),
            )
            # Log path changes
            for old_p, (new_p, _, _) in path_map.items():
                uid_row = conn.execute(
                    "SELECT uid FROM asset_locations WHERE path = ? OR path = ?",
                    (old_p, new_p),
                ).fetchone()
                if uid_row:
                    self._log_path_change(
                        conn, uid_row["uid"], old_p, new_p, "relocated", "project_relink"
                    )

            # D-3: write output record
            cursor = conn.execute(
                "INSERT INTO project_relink_output (job_id, output_path, naming_rule, applied_count, skipped_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, str(out), naming_rule, len(applied_item_ids), len(skipped_items), now),
            )
            output_id = cursor.lastrowid

            # D-3: audit log
            self._log_project_relink_action(
                conn, job_id, "apply",
                payload={"output_path": str(out), "applied": len(applied_item_ids), "skipped": len(skipped_items), "output_id": output_id},
            )

        return {
            "output_path": str(out),
            "applied": len(applied_item_ids),
            "skipped": len(skipped_items),
            "output_id": output_id,
            "apply_detail": {
                "applied_items": applied_items_detail,
                "skipped_items": skipped_items,
            },
        }

    # ------------------------------------------------------------------
    # v0.7 Phase D-1 – Task Center + Missing Fix
    # ------------------------------------------------------------------

    def retry_project_relink_job(self, job_id: int) -> Dict:
        """
        Retry a *failed* relink job by creating a new job that re-reads the
        current project file.  The original job is never overwritten.

        Rules (D-1 hard rule #2):
          - Only jobs with status='failed' can be retried.
          - A new job row is always created (retry_of → original job_id).
          - retry_count on original job is incremented.
        """
        with self._connect() as conn:
            original = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()

        if not original:
            return {"error": f"Job {job_id} not found"}

        if original["status"] != "failed":
            return {"error": f"Only failed jobs can be retried. Job {job_id} status is '{original['status']}'"}

        project_path = original["project_path"]
        project_type = original["project_type"] or "jianying"

        # Create new job with retry_of pointing to original
        p = Path(project_path)
        if not p.exists():
            return {"error": f"Project file not found: {project_path}"}

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO project_relink_job
                    (project_path, project_type, status, retry_of)
                VALUES (?, ?, 'running', ?)
                """,
                (str(p), project_type, job_id),
            )
            new_job_id = cursor.lastrowid
            # Increment retry_count on original
            conn.execute(
                "UPDATE project_relink_job SET retry_count = retry_count + 1, updated_at = ? WHERE job_id = ?",
                (self._now(), job_id),
            )

        try:
            # Extract version info
            version_info_str = None
            try:
                adapter = _get_relink_adapter(project_type)
                vi = adapter.get_version_info(str(p))
                if vi:
                    version_info_str = json.dumps(vi, ensure_ascii=False)
            except Exception:
                pass

            result = self.build_project_relink_map(str(p), project_type)
            summary = result["summary"]
            items = result["items"]

            with self._connect() as conn:
                for item in items:
                    conn.execute(
                        """
                        INSERT INTO project_relink_item
                            (job_id, uid, asset_name, old_path, new_path, status,
                             source_ref, fingerprint_match_type, media_type,
                             match_confidence, reason, applied)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            new_job_id,
                            item.get("uid"),
                            item.get("asset_name"),
                            item.get("old_path"),
                            item.get("new_path"),
                            item["status"],
                            item.get("source_ref"),
                            item.get("fingerprint_match_type"),
                            item.get("media_type"),
                            item.get("match_confidence"),
                            item.get("reason"),
                        ),
                    )
                conn.execute(
                    """
                    UPDATE project_relink_job
                    SET status='done',
                        total_refs=?, stable_refs=?, changed_refs=?,
                        missing_refs=?, unmatched_refs=?,
                        result_json=?, version_info=?,
                        updated_at=?
                    WHERE job_id=?
                    """,
                    (
                        summary["total_refs"],
                        summary["stable_refs"],
                        summary["changed_refs"],
                        summary["missing_refs"],
                        summary["unmatched_refs"],
                        json.dumps(result, ensure_ascii=False),
                        version_info_str,
                        self._now(),
                        new_job_id,
                    ),
                )

            # D-3: audit log
            self._log_project_relink_action(
                conn, new_job_id, "retry",
                payload={"retry_of": job_id, "project_path": str(p)},
            )

            return {
                "job_id": new_job_id,
                "retry_of": job_id,
                "project_path": str(p),
                "project_type": project_type,
                "status": "done",
                "summary": summary,
                "items": items,
            }

        except Exception as exc:
            now = self._now()
            with self._connect() as conn:
                conn.execute(
                    "UPDATE project_relink_job SET status='failed', error_message=?, last_error_at=?, updated_at=? WHERE job_id=?",
                    (str(exc), now, now, new_job_id),
                )
            return {"error": str(exc), "job_id": new_job_id, "status": "failed"}

    def preview_project_relink_apply(self, job_id: int) -> Dict:
        """
        Read-only preview of what apply_project_relink would do.

        D-1 hard rule #3: must check output path conflicts.
        Does NOT modify any state.
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            if job_row["status"] != "done":
                return {"error": f"Job {job_id} status is '{job_row['status']}', expected 'done'"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? AND status = 'relinked'",
                (job_id,),
            ).fetchall()

        project_path = Path(job_row["project_path"])
        if not project_path.exists():
            return {"error": f"Original project file not found: {project_path}"}

        # Generate preview output path (same logic as apply)
        stem = project_path.stem
        suffix = project_path.suffix
        candidate = project_path.parent / f"{stem}_relinked_{job_id}{suffix}"
        output_exists = candidate.exists()
        if output_exists:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_preview = str(project_path.parent / f"{stem}_relinked_{job_id}_{ts}{suffix}")
        else:
            output_preview = str(candidate)

        will_apply = []
        will_skip = []
        already_applied_count = 0

        for item in items:
            # D-2: prefer manual_new_path when manually bound
            effective_new = item["manual_new_path"] or item["new_path"]
            d = {
                "item_id": item["item_id"],
                "asset_name": item["asset_name"] or "",
                "old_path": item["old_path"],
                "new_path": effective_new,
                "manual_uid": item["manual_uid"],
                "binding_mode": "manual" if item["manual_uid"] else "system",
            }
            if item["applied"] == 1:
                already_applied_count += 1
            if effective_new and Path(effective_new).exists():
                will_apply.append(d)
            else:
                reason = "new_path does not exist" if effective_new else "no new_path"
                d["reason"] = reason
                will_skip.append(d)

        warnings = []
        if already_applied_count > 0:
            warnings.append(f"{already_applied_count} item(s) already applied previously")
        if already_applied_count == len(items) and items:
            warnings.append("All relinked items already applied. Will need force=True to re-apply.")
        if output_exists:
            warnings.append(f"Default output path already exists; using timestamped name instead")

        # D-3: diff_items = will_apply + will_skip combined with reason/binding_mode
        diff_items = []
        for d in will_apply:
            di = dict(d)
            di["action"] = "apply"
            di.setdefault("reason", "")
            diff_items.append(di)
        for d in will_skip:
            di = dict(d)
            di["action"] = "skip"
            diff_items.append(di)

        # D-3: audit log (preview is read-only, but we record it)
        with self._connect() as conn2:
            self._log_project_relink_action(
                conn2, job_id, "preview_apply",
                payload={"will_apply": len(will_apply), "will_skip": len(will_skip)},
            )

        return {
            "job_id": job_id,
            "project_path": str(project_path),
            "total_relinked": len(items),
            "will_apply": will_apply,
            "will_skip": will_skip,
            "diff_items": diff_items,
            "already_applied": already_applied_count,
            "output_path_preview": output_preview,
            "output_path_conflict": output_exists,
            "warnings": warnings,
            "summary": {
                "total_refs": job_row["total_refs"],
                "stable_refs": job_row["stable_refs"],
                "changed_refs": job_row["changed_refs"],
                "missing_refs": job_row["missing_refs"],
                "unmatched_refs": job_row["unmatched_refs"],
            },
        }

    def export_missing_items(self, job_id: int, fmt: str = "json") -> Dict:
        """
        Export missing + unmatched items with standardized reason field.

        D-1 hard rule #4: every item must include reason for traceability.
        Reads from project_relink_item (source of truth, hard rule #1).
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT job_id, project_path, project_type FROM project_relink_job WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                """
                SELECT item_id, uid, asset_name, old_path, status,
                       source_ref, fingerprint_match_type, media_type,
                       match_confidence, reason
                FROM project_relink_item
                WHERE job_id = ? AND status IN ('missing', 'unmatched')
                ORDER BY status, asset_name
                """,
                (job_id,),
            ).fetchall()

        item_list = [dict(r) for r in items]
        filenames = set(r["asset_name"] for r in item_list if r["asset_name"])
        missing_count = sum(1 for r in item_list if r["status"] == "missing")
        unmatched_count = sum(1 for r in item_list if r["status"] == "unmatched")

        # D-3: audit log
        with self._connect() as conn2:
            self._log_project_relink_action(
                conn2, job_id, "export_missing",
                payload={"format": fmt, "total": len(item_list)},
            )

        summary = {
            "total_missing": missing_count,
            "total_unmatched": unmatched_count,
            "unique_filenames": len(filenames),
        }

        if fmt == "csv":
            import io
            import csv
            output = io.StringIO()
            writer = csv.writer(output)
            header = [
                "item_id", "status", "asset_name", "old_path", "uid",
                "source_ref", "media_type", "fingerprint_match_type",
                "match_confidence", "reason",
            ]
            writer.writerow(header)
            for r in item_list:
                writer.writerow([r.get(h, "") for h in header])
            return {
                "csv_content": output.getvalue(),
                "filename": f"missing_items_{job_id}.csv",
                "summary": summary,
            }

        return {
            "items": item_list,
            "summary": summary,
            "filename": f"missing_items_{job_id}.json",
            "project_path": job_row["project_path"],
        }

    # ------------------------------------------------------------------
    # v0.7 Phase D-1 – Candidate suggestion for missing items
    # ------------------------------------------------------------------

    def suggest_candidates_for_missing(
        self, job_id: int, max_candidates: int = 5
    ) -> Dict:
        """
        Suggest library assets that may match missing/unmatched items.

        For each missing/unmatched item, search by filename similarity.
        Uses difflib.SequenceMatcher — no new dependencies.

        D-1 hard rule #5: read-only, never auto-write to new_path or change status.
        """
        import difflib

        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT job_id, project_path FROM project_relink_job WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                """
                SELECT item_id, uid, asset_name, old_path, status, reason
                FROM project_relink_item
                WHERE job_id = ? AND status IN ('missing', 'unmatched')
                ORDER BY asset_name
                """,
                (job_id,),
            ).fetchall()

            if not items:
                return {"job_id": job_id, "suggestions": [], "total_items": 0}

            suggestions = []

            for item in items:
                asset_name = item["asset_name"] or ""
                stem = Path(asset_name).stem if asset_name else ""
                if not stem:
                    suggestions.append(
                        {
                            "item_id": item["item_id"],
                            "asset_name": asset_name,
                            "status": item["status"],
                            "candidates": [],
                        }
                    )
                    continue

                # Search for similar filenames in assets table
                like_pattern = f"%{stem}%"
                rows = conn.execute(
                    """
                    SELECT uid, filename, primary_path, source_type
                    FROM assets
                    WHERE filename LIKE ?
                    ORDER BY filename
                    LIMIT ?
                    """,
                    (like_pattern, max_candidates * 3),
                ).fetchall()

                # Score by similarity and pick top N
                scored = []
                for r in rows:
                    candidate_stem = Path(r["filename"]).stem if r["filename"] else ""
                    sim = difflib.SequenceMatcher(
                        None, stem.lower(), candidate_stem.lower()
                    ).ratio()
                    # Check availability via best existing path
                    best = self._best_existing_path(
                        conn,
                        r["uid"],
                        r["primary_path"],
                        filename=r["filename"],
                        update_availability=False,
                    )
                    scored.append(
                        {
                            "uid": r["uid"],
                            "filename": r["filename"],
                            "path": best or r["primary_path"],
                            "available": best is not None and Path(best).exists(),
                            "similarity": round(sim, 3),
                        }
                    )

                # Sort by similarity descending, take top N
                scored.sort(key=lambda x: x["similarity"], reverse=True)
                top = scored[:max_candidates]

                suggestions.append(
                    {
                        "item_id": item["item_id"],
                        "asset_name": asset_name,
                        "status": item["status"],
                        "candidates": top,
                    }
                )

            return {
                "job_id": job_id,
                "suggestions": suggestions,
                "total_items": len(suggestions),
            }

    # ------------------------------------------------------------------
    # v0.7 Phase D-3 – Reason Enum + Action Log + Workbench
    # ------------------------------------------------------------------

    PROJECT_RELINK_REASON_LABELS = {
        "path_still_valid": "原路径仍可用",
        "path_matched_in_locations": "通过历史路径匹配到素材",
        "primary_path_matched": "通过主路径匹配到素材",
        "filename_matched": "通过文件名匹配到素材",
        "filename_ambiguous": "同名素材过多，无法安全确认",
        "uid_has_no_available_path": "已识别素材，但当前没有可用路径",
        "manual_binding_applied": "已使用人工绑定路径",
        "manual_binding_missing": "已人工绑定素材，但绑定素材当前无可用路径",
        "no_library_match": "未匹配到素材库",
        "media_type_conflict": "素材类型不兼容",
    }

    @staticmethod
    def _log_project_relink_action(conn, job_id, action_type, item_id=None, payload=None, operator="system"):
        """Write an audit log entry to project_relink_action_log."""
        import json as _json
        payload_str = _json.dumps(payload, ensure_ascii=False) if payload else None
        conn.execute(
            "INSERT INTO project_relink_action_log (job_id, item_id, action_type, operator, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (job_id, item_id, action_type, operator, payload_str),
        )

    def get_project_relink_action_log(self, job_id: int, item_id: int = None) -> List[Dict]:
        """Return audit log entries for a job, optionally filtered by item."""
        with self._connect() as conn:
            if item_id:
                rows = conn.execute(
                    "SELECT * FROM project_relink_action_log WHERE job_id = ? AND item_id = ? ORDER BY action_id",
                    (job_id, item_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM project_relink_action_log WHERE job_id = ? ORDER BY action_id",
                    (job_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # v0.7 Phase D-2 – Manual Binding Loop
    # ------------------------------------------------------------------
    #
    # STATE MACHINE for project_relink_item (D-2 complete):
    #
    # [Initial scan] build_project_relink_map
    #   stable     <- Path(old_path).exists()
    #   relinked   <- uid matched + _best_existing_path found
    #   missing    <- uid matched + no available path
    #   unmatched  <- no uid match
    #
    # [Manual binding] bind_project_relink_item
    #   missing/unmatched  --bind(uid)--> relinked  (if path found)
    #   missing/unmatched  --bind(uid)--> missing   (uid set, no file)
    #   stable             --bind()-->    ERROR
    #
    # [Unbind] unbind_project_relink_item
    #   any(manual_uid)  --unbind()--> recalculate from original system match
    #
    # [Refresh] refresh_project_relink_items
    #   all non-stable  --> re-check _best_existing_path --> update status+path
    #
    # [Apply] apply_project_relink
    #   relinked --> path_map: prefer manual_new_path > system new_path

    def _recalc_project_relink_job_summary(
        self, conn, job_id: int
    ) -> None:
        """
        Recalculate job summary counts from current item statuses.

        D-2 rule #1: must be called after bind/unbind/refresh to keep
        job-level summary consistent with item-level truth.
        """
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='stable' THEN 1 ELSE 0 END) AS stable,
                SUM(CASE WHEN status='relinked' THEN 1 ELSE 0 END) AS changed,
                SUM(CASE WHEN status='missing' THEN 1 ELSE 0 END) AS missing,
                SUM(CASE WHEN status='unmatched' THEN 1 ELSE 0 END) AS unmatched
            FROM project_relink_item
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        conn.execute(
            """
            UPDATE project_relink_job
            SET total_refs=?, stable_refs=?, changed_refs=?,
                missing_refs=?, unmatched_refs=?, updated_at=?
            WHERE job_id=?
            """,
            (
                row["total"],
                row["stable"],
                row["changed"],
                row["missing"],
                row["unmatched"],
                self._now(),
                job_id,
            ),
        )

    @staticmethod
    def _infer_media_category(filename: str) -> Optional[str]:
        """Infer media category from filename extension for bind validation."""
        if not filename:
            return None
        ext = Path(filename).suffix.lower()
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mts"}
        audio_exts = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"}
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic"}
        if ext in video_exts:
            return "video"
        if ext in audio_exts:
            return "audio"
        if ext in image_exts:
            return "image"
        return None

    def bind_project_relink_item(
        self, item_id: int, uid: str, decision_source: str = "candidate"
    ) -> Dict:
        """
        Bind a library asset to a missing/unmatched item.

        D-2 rules:
        - Only missing/unmatched items can be bound (not stable).
        - Sets manual_uid/manual_new_path/manual_decision_source/manual_bound_at.
        - NEVER overwrites system fields: uid, fingerprint_match_type,
          match_confidence, reason.
        - Validates media_type compatibility (rule #5).
        - Recalculates job summary after change (rule #1).
        - Returns item with effective_uid/effective_new_path/binding_mode (rule #4).
        """
        with self._connect() as conn:
            item = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if not item:
                return {"error": f"Item {item_id} not found"}

            if item["status"] not in ("missing", "unmatched"):
                return {
                    "error": f"Can only bind missing or unmatched items, "
                    f"got status='{item['status']}'"
                }

            # Validate uid exists in library
            asset_row = conn.execute(
                "SELECT uid, filename, source_type FROM assets WHERE uid = ?",
                (uid,),
            ).fetchone()
            if not asset_row:
                return {"error": f"Asset uid '{uid}' not found in library"}

            # Rule #5: validate media_type compatibility
            item_media = item["media_type"]  # video / audio from project parse
            asset_category = self._infer_media_category(asset_row["filename"])
            if (
                item_media
                and asset_category
                and item_media != asset_category
            ):
                return {
                    "error": f"Media type mismatch: item is '{item_media}' "
                    f"but asset '{asset_row['filename']}' is '{asset_category}'"
                }

            # Find best existing path for the bound uid
            best_path = self._best_existing_path(
                conn,
                uid,
                fallback=None,
                filename=asset_row["filename"],
                update_availability=False,
            )

            now = self._now()
            if best_path and Path(best_path).exists():
                # Freeze rule §2.4: bind must NOT overwrite system new_path.
                # Manual path goes to manual_new_path only; system new_path preserved.
                conn.execute(
                    """
                    UPDATE project_relink_item
                    SET manual_uid=?, manual_new_path=?,
                        manual_decision_source=?, manual_bound_at=?,
                        status='relinked'
                    WHERE item_id=?
                    """,
                    (uid, best_path, decision_source, now, item_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE project_relink_item
                    SET manual_uid=?, manual_new_path=NULL,
                        manual_decision_source=?, manual_bound_at=?,
                        status='missing'
                    WHERE item_id=?
                    """,
                    (uid, decision_source, now, item_id),
                )

            # Rule #1: recalculate job summary
            self._recalc_project_relink_job_summary(conn, item["job_id"])

            # D-3: audit log
            self._log_project_relink_action(
                conn, item["job_id"], "bind", item_id=item_id,
                payload={"uid": uid, "decision_source": decision_source, "best_path": best_path},
            )

            # Re-read and return with effective fields (rule #4)
            updated = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            return self._item_with_effective_fields(updated)

    def unbind_project_relink_item(self, item_id: int) -> Dict:
        """
        Remove manual binding from an item, restoring system match status.

        D-2 rules:
        - Clears all manual_* fields.
        - Recalculates status from original system uid.
        - Recalculates job summary (rule #1).
        """
        with self._connect() as conn:
            item = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if not item:
                return {"error": f"Item {item_id} not found"}

            if not item["manual_uid"]:
                # Nothing to unbind — return as-is
                return self._item_with_effective_fields(item)

            # Clear manual fields
            original_uid = item["uid"]
            if original_uid:
                # Re-check system match
                asset_row = conn.execute(
                    "SELECT filename FROM assets WHERE uid = ?",
                    (original_uid,),
                ).fetchone()
                fname = asset_row["filename"] if asset_row else None
                best_path = self._best_existing_path(
                    conn,
                    original_uid,
                    fallback=None,
                    filename=fname,
                    update_availability=False,
                )
                if best_path and Path(best_path).exists():
                    new_status = "relinked"
                    new_path = best_path
                else:
                    new_status = "missing"
                    new_path = None
            else:
                new_status = "unmatched"
                new_path = None

            conn.execute(
                """
                UPDATE project_relink_item
                SET manual_uid=NULL, manual_new_path=NULL,
                    manual_decision_source=NULL, manual_bound_at=NULL,
                    status=?, new_path=?
                WHERE item_id=?
                """,
                (new_status, new_path, item_id),
            )

            # Rule #1: recalculate job summary
            self._recalc_project_relink_job_summary(conn, item["job_id"])

            # D-3: audit log
            self._log_project_relink_action(
                conn, item["job_id"], "unbind", item_id=item_id,
                payload={"old_manual_uid": item["manual_uid"], "new_status": new_status},
            )

            updated = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            return self._item_with_effective_fields(updated)

    def refresh_project_relink_items(self, job_id: int) -> Dict:
        """
        Refresh all non-stable item paths for a job.

        D-2 rule #3: when manual_uid is set, only update manual_new_path + status.
        D-2 rule #6: only refreshes paths, never re-parses the project file.
        D-2 rule #1: recalculates job summary after changes.
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT job_id FROM project_relink_job WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? AND status != 'stable'",
                (job_id,),
            ).fetchall()

            changed = 0
            unchanged = 0

            for item in items:
                manual_uid = item["manual_uid"]
                system_uid = item["uid"]
                effective_uid = manual_uid or system_uid

                if not effective_uid:
                    unchanged += 1
                    continue

                asset_row = conn.execute(
                    "SELECT filename FROM assets WHERE uid = ?",
                    (effective_uid,),
                ).fetchone()
                fname = asset_row["filename"] if asset_row else None
                best_path = self._best_existing_path(
                    conn,
                    effective_uid,
                    fallback=None,
                    filename=fname,
                    update_availability=False,
                )

                if best_path and Path(best_path).exists():
                    new_status = "relinked"
                else:
                    new_status = "missing"
                    best_path = None

                old_status = item["status"]
                old_path = (
                    item["manual_new_path"] if manual_uid else item["new_path"]
                )

                if new_status != old_status or best_path != old_path:
                    # Rule #3: manual_uid items → update manual_new_path only
                    if manual_uid:
                        conn.execute(
                            """
                            UPDATE project_relink_item
                            SET manual_new_path=?, status=?, new_path=?
                            WHERE item_id=?
                            """,
                            (best_path, new_status, best_path, item["item_id"]),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE project_relink_item
                            SET new_path=?, status=?
                            WHERE item_id=?
                            """,
                            (best_path, new_status, item["item_id"]),
                        )
                    changed += 1
                else:
                    unchanged += 1

            # Rule #1: recalculate job summary
            self._recalc_project_relink_job_summary(conn, job_id)

            # D-3: audit log
            self._log_project_relink_action(
                conn, job_id, "refresh_items",
                payload={"refreshed": len(items), "changed": changed, "unchanged": unchanged},
            )

            return {
                "job_id": job_id,
                "refreshed": len(items),
                "changed": changed,
                "unchanged": unchanged,
            }

    @staticmethod
    def _item_with_effective_fields(item) -> Dict:
        """
        Add effective_uid, effective_new_path, binding_mode to item dict.

        D-2 rule #4: frontend reads only these computed fields,
        does not assemble logic from raw manual_*/system fields.
        """
        d = dict(item)
        manual_uid = d.get("manual_uid")
        d["effective_uid"] = manual_uid or d.get("uid")
        d["effective_new_path"] = d.get("manual_new_path") or d.get("new_path")
        if manual_uid:
            d["binding_mode"] = "manual"
        elif d.get("uid"):
            d["binding_mode"] = "system"
        else:
            d["binding_mode"] = "none"
        return d

    # ------------------------------------------------------------------
    # v0.7 Phase D-3 – Batch Bind, History, Undo, Outputs, Workbench
    # ------------------------------------------------------------------

    def batch_bind_project_relink_items(
        self, bindings: List[Dict], decision_source: str = "candidate"
    ) -> Dict:
        """
        Batch-bind multiple items in one call.

        bindings = [{"item_id": 1, "uid": "..."}, ...]
        Each item validated independently; single failure doesn't block others.
        Recalculates affected job summaries once at end.
        """
        results = []
        affected_jobs = set()

        for b in bindings:
            item_id = b.get("item_id")
            uid = b.get("uid")
            if not item_id or not uid:
                results.append({"item_id": item_id, "ok": False, "error": "Missing item_id or uid"})
                continue
            r = self.bind_project_relink_item(item_id, uid, decision_source)
            if "error" in r:
                results.append({"item_id": item_id, "ok": False, "error": r["error"]})
            else:
                results.append({"item_id": item_id, "ok": True, "item": r})
                if r.get("job_id"):
                    affected_jobs.add(r["job_id"])

        success = sum(1 for r in results if r["ok"])
        failed = len(results) - success

        # Write batch_bind action log
        if affected_jobs:
            with self._connect() as conn:
                for jid in affected_jobs:
                    self._log_project_relink_action(
                        conn, jid, "batch_bind",
                        payload={"total": len(bindings), "success": success, "failed": failed, "decision_source": decision_source},
                    )

        return {
            "success_count": success,
            "failed_count": failed,
            "items": results,
        }

    def list_project_relink_item_history(self, item_id: int) -> List[Dict]:
        """Return bind/unbind/undo history for a specific item from action log."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT action_id, job_id, item_id, action_type, operator, payload_json, created_at
                FROM project_relink_action_log
                WHERE item_id = ? AND action_type IN ('bind', 'unbind', 'undo_bind', 'batch_bind')
                ORDER BY action_id DESC
                """,
                (item_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def undo_last_project_relink_action(self, item_id: int) -> Dict:
        """
        Undo the most recent manual bind on an item.

        Rules:
        - Only undoes the last 'bind' action (not apply, not unbind).
        - Cross-item undo not allowed.
        - Under the hood calls unbind_project_relink_item.
        - Writes undo_bind to action log.
        """
        with self._connect() as conn:
            item = conn.execute(
                "SELECT * FROM project_relink_item WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if not item:
                return {"error": f"Item {item_id} not found"}

            if not item["manual_uid"]:
                return {"error": "No manual binding to undo"}

            # Save old state for log
            old_manual_uid = item["manual_uid"]
            job_id = item["job_id"]

        # Perform unbind
        result = self.unbind_project_relink_item(item_id)
        if "error" in result:
            return result

        # Write undo_bind action log
        with self._connect() as conn:
            self._log_project_relink_action(
                conn, job_id, "undo_bind", item_id=item_id,
                payload={"undone_manual_uid": old_manual_uid},
            )

        return result

    def list_project_relink_outputs(self, job_id: int) -> List[Dict]:
        """List all output copies generated for a job."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_relink_output WHERE job_id = ? ORDER BY output_id DESC",
                (job_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_project_relink_workbench(self, job_id: int) -> Dict:
        """
        Return items grouped by workbench view categories.

        Groups:
        - stable
        - relinked_system (uid match, no manual_uid)
        - relinked_manual (manual_uid set, status=relinked)
        - missing
        - unmatched
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ? ORDER BY item_id",
                (job_id,),
            ).fetchall()

            groups = {
                "missing": [],
                "unmatched": [],
                "relinked_manual": [],
                "relinked_system": [],
                "stable": [],
            }

            for item in items:
                d = self._item_with_effective_fields(item)
                if d["status"] == "stable":
                    groups["stable"].append(d)
                elif d["status"] == "relinked" and d.get("manual_uid"):
                    groups["relinked_manual"].append(d)
                elif d["status"] == "relinked":
                    groups["relinked_system"].append(d)
                elif d["status"] == "missing":
                    groups["missing"].append(d)
                else:
                    groups["unmatched"].append(d)

            return {
                "job_id": job_id,
                "groups": groups,
                "summary": {
                    "total": len(items),
                    "stable": len(groups["stable"]),
                    "relinked_system": len(groups["relinked_system"]),
                    "relinked_manual": len(groups["relinked_manual"]),
                    "missing": len(groups["missing"]),
                    "unmatched": len(groups["unmatched"]),
                },
            }

    # ------------------------------------------------------------------
    # v0.7 Phase D-4 – Long-term sync + Handover closure
    # ------------------------------------------------------------------
    #
    # D-4 RULES:
    #
    # 1. job.status enum is FIXED: pending / running / done / failed.
    #    "Has this job been applied?" is expressed via apply_count / applied_at / output records.
    #    Predecessor selection uses status='done' only.
    #
    # 2. Manual binding inheritance uses 3-tier priority:
    #    (a) source_ref (Jianying material_id) — exact project-internal ID
    #    (b) old_path — filesystem path fallback
    #    (c) asset_name + media_type — filename + type fallback
    #    inherited_from_item_id MUST point to the actually matched predecessor item.
    #
    # 3. verify is read-only: sets verified_at, NEVER changes item.status.
    #    status (stable/relinked/missing/unmatched) and verify health
    #    (valid/stale/unchecked) are two independent dimensions.
    #
    # 4. handover_snapshot is a frozen snapshot at generation time.
    #    It is NOT a live view. Re-running generate_handover_report()
    #    replaces the snapshot; it does NOT auto-update.
    #
    # 5. "Recommended handover version" rule (for documentation/future UI):
    #    Same project_path, pick in order:
    #    (a) Latest job: status='done', handover_at IS NOT NULL, closure_status='complete'
    #    (b) Latest job: status='done', handover_at IS NOT NULL, closure_status='incomplete'
    #    (c) None — no recommended version
    #

    def reanalyze_project_relink(
        self, project_path: str, project_type: str = "jianying"
    ) -> Dict:
        """
        Re-analyze a project, carrying forward manual bindings from the
        latest predecessor job for the same project_path.

        Inheritance priority (D-4 rule #2):
          1. source_ref match (Jianying material_id)
          2. old_path match
          3. asset_name + media_type match

        Predecessor selection (D-4 rule #1):
          Latest job with status='done' for the same project_path.

        Returns: {job_id, predecessor_job_id, inherited_bindings,
                  delta_vs_predecessor, summary, items}
        """
        p = Path(project_path)
        if not p.exists():
            return {"error": f"Project file not found: {project_path}"}

        # 1. Find predecessor: latest done job for this project
        predecessor_job_id = None
        predecessor_bindings_by_source_ref = {}  # source_ref -> binding dict
        predecessor_bindings_by_old_path = {}    # old_path -> binding dict
        predecessor_bindings_by_name_type = {}   # (asset_name, media_type) -> binding dict

        with self._connect() as conn:
            pred_row = conn.execute(
                """SELECT job_id FROM project_relink_job
                   WHERE project_path = ? AND status = 'done'
                   ORDER BY job_id DESC LIMIT 1""",
                (str(p),),
            ).fetchone()

            if pred_row:
                predecessor_job_id = pred_row["job_id"]
                pred_items = conn.execute(
                    "SELECT * FROM project_relink_item WHERE job_id = ? AND manual_uid IS NOT NULL",
                    (predecessor_job_id,),
                ).fetchall()
                for pi in pred_items:
                    binding = {
                        "manual_uid": pi["manual_uid"],
                        "manual_decision_source": pi["manual_decision_source"],
                        "item_id": pi["item_id"],
                    }
                    # Index by all three keys
                    sr = (pi["source_ref"] or "").strip()
                    if sr:
                        predecessor_bindings_by_source_ref[sr] = binding
                    op = (pi["old_path"] or "").strip()
                    if op:
                        predecessor_bindings_by_old_path[op] = binding
                    aname = (pi["asset_name"] or "").strip()
                    mtype = (pi["media_type"] or "").strip()
                    if aname:
                        predecessor_bindings_by_name_type[(aname, mtype)] = binding

        # 2. Create new job with predecessor link
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO project_relink_job
                    (project_path, project_type, status, predecessor_job_id)
                VALUES (?, ?, 'running', ?)""",
                (str(p), project_type, predecessor_job_id),
            )
            new_job_id = cursor.lastrowid

        try:
            # 3. Extract version info
            version_info_str = None
            try:
                adapter = _get_relink_adapter(project_type)
                vi = adapter.get_version_info(str(p))
                if vi:
                    version_info_str = json.dumps(vi, ensure_ascii=False)
            except Exception:
                pass

            # 4. Fresh scan
            result = self.build_project_relink_map(str(p), project_type)
            summary = result["summary"]
            items = result["items"]

            # 5. Insert items with carry-forward
            inherited_count = 0
            with self._connect() as conn:
                for item in items:
                    inherited_from = None
                    manual_uid = None
                    manual_new_path = None
                    manual_decision_source = None
                    manual_bound_at = None
                    item_status = item["status"]

                    # Only inherit for non-stable items when we have a predecessor
                    if predecessor_job_id and item_status != "stable":
                        # 3-tier matching priority
                        binding = None
                        sr = (item.get("source_ref") or "").strip()
                        op = (item.get("old_path") or "").strip()
                        aname = (item.get("asset_name") or "").strip()
                        mtype = (item.get("media_type") or "").strip()

                        if sr and sr in predecessor_bindings_by_source_ref:
                            binding = predecessor_bindings_by_source_ref[sr]
                        elif op and op in predecessor_bindings_by_old_path:
                            binding = predecessor_bindings_by_old_path[op]
                        elif aname and (aname, mtype) in predecessor_bindings_by_name_type:
                            binding = predecessor_bindings_by_name_type[(aname, mtype)]

                        if binding:
                            manual_uid = binding["manual_uid"]
                            manual_decision_source = binding["manual_decision_source"]
                            inherited_from = binding["item_id"]
                            manual_bound_at = self._now()

                            # Re-verify the inherited uid's path
                            asset_row = conn.execute(
                                "SELECT filename FROM assets WHERE uid = ?",
                                (manual_uid,),
                            ).fetchone()
                            asset_filename = asset_row["filename"] if asset_row else None
                            best_path = self._best_existing_path(
                                conn, manual_uid, fallback=None,
                                filename=asset_filename,
                                update_availability=False,
                            )
                            if best_path and Path(best_path).exists():
                                manual_new_path = best_path
                                item_status = "relinked"
                            else:
                                manual_new_path = None
                                # Keep system status if system also found it relinked;
                                # otherwise mark missing since we have the uid
                                if item_status not in ("relinked",):
                                    item_status = "missing"

                            inherited_count += 1

                    conn.execute(
                        """INSERT INTO project_relink_item
                            (job_id, uid, asset_name, old_path, new_path, status,
                             source_ref, fingerprint_match_type, media_type,
                             match_confidence, reason, applied,
                             manual_uid, manual_new_path, manual_decision_source,
                             manual_bound_at, inherited_from_item_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,
                                ?, ?, ?, ?, ?)""",
                        (
                            new_job_id,
                            item.get("uid"),
                            item.get("asset_name"),
                            item.get("old_path"),
                            manual_new_path or item.get("new_path"),
                            item_status,
                            item.get("source_ref"),
                            item.get("fingerprint_match_type"),
                            item.get("media_type"),
                            item.get("match_confidence"),
                            item.get("reason"),
                            manual_uid,
                            manual_new_path,
                            manual_decision_source,
                            manual_bound_at,
                            inherited_from,
                        ),
                    )

                # 6. Recalc summary
                self._recalc_project_relink_job_summary(conn, new_job_id)

                conn.execute(
                    """UPDATE project_relink_job
                       SET status='done', version_info=?, updated_at=?
                       WHERE job_id=?""",
                    (version_info_str, self._now(), new_job_id),
                )

                # 7. Audit log
                self._log_project_relink_action(
                    conn, new_job_id, "reanalyze", payload={
                        "predecessor_job_id": predecessor_job_id,
                        "inherited_bindings": inherited_count,
                    },
                )

            # 8. Auto-compare with predecessor
            delta = None
            if predecessor_job_id:
                delta = self.compare_project_relink_jobs(predecessor_job_id, new_job_id)

            # Read back summary
            job = self.get_project_relink_job(new_job_id)

            return {
                "job_id": new_job_id,
                "predecessor_job_id": predecessor_job_id,
                "inherited_bindings": inherited_count,
                "delta_vs_predecessor": delta,
                "project_path": str(p),
                "project_type": project_type,
                "status": "done",
                "summary": job.get("summary") or summary,
                "items": job.get("items", []),
            }

        except Exception as exc:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE project_relink_job SET status='failed', error_message=?, updated_at=? WHERE job_id=?",
                    (str(exc), self._now(), new_job_id),
                )
            return {"error": str(exc), "job_id": new_job_id, "status": "failed"}

    def get_project_job_chain(self, project_path: str) -> Dict:
        """
        Return the chronological chain of relink jobs for a project path.

        Each entry includes predecessor linkage, summary counts,
        handover status, and apply info.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT job_id, status, predecessor_job_id,
                          total_refs, stable_refs, changed_refs,
                          missing_refs, unmatched_refs,
                          apply_count, handover_at,
                          created_at, updated_at
                   FROM project_relink_job
                   WHERE project_path = ?
                   ORDER BY job_id ASC""",
                (project_path,),
            ).fetchall()

            chain = []
            for r in rows:
                entry = dict(r)
                # Count inherited items for this job
                inh = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM project_relink_item WHERE job_id = ? AND inherited_from_item_id IS NOT NULL",
                    (r["job_id"],),
                ).fetchone()
                entry["inherited_count"] = inh["cnt"] if inh else 0
                chain.append(entry)

            return {
                "project_path": project_path,
                "chain": chain,
            }

    def verify_project_relink_state(self, job_id: int) -> Dict:
        """
        Verify that all resolved/stable item paths still exist on disk.

        D-4 rule #3: This is READ-ONLY with respect to item.status.
        Only sets verified_at timestamp and reports stale items.
        Status (stable/relinked/missing/unmatched) is NEVER changed.

        Returns: {job_id, verified, stale_count, stale_items, all_valid}
        """
        with self._connect() as conn:
            job_row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return {"error": f"Job {job_id} not found"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ?",
                (job_id,),
            ).fetchall()

            now = self._now()
            verified_count = 0
            stale_items = []

            for item in items:
                status = item["status"]
                # Determine the effective path to check
                if status == "stable":
                    check_path = item["old_path"]
                elif status == "relinked":
                    check_path = item["manual_new_path"] or item["new_path"]
                else:
                    # missing/unmatched — no path to verify
                    continue

                verified_count += 1
                is_valid = bool(check_path and Path(check_path).exists())

                # Update verified_at (D-4 rule #3: do NOT change status)
                conn.execute(
                    "UPDATE project_relink_item SET verified_at = ? WHERE item_id = ?",
                    (now, item["item_id"]),
                )

                if not is_valid:
                    stale_items.append({
                        "item_id": item["item_id"],
                        "asset_name": item["asset_name"],
                        "path": check_path,
                        "status": status,
                    })

            all_valid = len(stale_items) == 0

            # Audit log
            self._log_project_relink_action(
                conn, job_id, "verify", payload={
                    "verified": verified_count,
                    "stale_count": len(stale_items),
                    "all_valid": all_valid,
                },
            )

            return {
                "job_id": job_id,
                "verified": verified_count,
                "stale_count": len(stale_items),
                "stale_items": stale_items,
                "all_valid": all_valid,
            }

    def generate_handover_report(self, job_id: int, auto_verify: bool = True) -> Dict:
        """
        Generate a handover closure report for a completed relink job.

        D-4 rule #4: The handover_snapshot is a frozen snapshot.
        It captures state at generation time and does NOT auto-update.
        Re-calling this method replaces the snapshot.

        D-4 rule #1: closure_status is 'complete' when no missing/unmatched
        items remain; 'incomplete' otherwise.

        Recommended handover version rule (D-4 rule #5 comment):
        Same project_path → latest job where status='done' AND
        handover_at IS NOT NULL AND closure_status='complete'
        (fallback to 'incomplete', then None).
        """
        # 1. Optional auto-verify
        verification = None
        if auto_verify:
            verification = self.verify_project_relink_state(job_id)
            if verification.get("error"):
                return verification

        with self._connect() as conn:
            _row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not _row:
                return {"error": f"Job {job_id} not found"}
            job_row = dict(_row)

            if job_row["status"] != "done":
                return {"error": f"Job {job_id} status is '{job_row['status']}', expected 'done'"}

            items = conn.execute(
                "SELECT * FROM project_relink_item WHERE job_id = ?",
                (job_id,),
            ).fetchall()

        # 2. Group items by resolution method
        stable = []
        relinked_system = []
        relinked_manual = []
        missing_items = []
        unmatched_items = []
        manual_bindings_detail = []

        for item in items:
            d = dict(item)
            status = d["status"]
            if status == "stable":
                stable.append(d)
            elif status == "relinked" and d.get("manual_uid"):
                relinked_manual.append(d)
                manual_bindings_detail.append({
                    "asset_name": d["asset_name"],
                    "old_path": d["old_path"],
                    "bound_uid": d["manual_uid"],
                    "decision_source": d.get("manual_decision_source", ""),
                    "inherited": bool(d.get("inherited_from_item_id")),
                })
            elif status == "relinked":
                relinked_system.append(d)
            elif status == "missing":
                missing_items.append(d)
            else:
                unmatched_items.append(d)

        # 3. Get outputs and action log
        outputs = self.list_project_relink_outputs(job_id)
        action_log = self.get_project_relink_action_log(job_id)

        # 4. Build predecessor chain
        predecessor_chain = []
        with self._connect() as conn:
            chain_rows = conn.execute(
                """SELECT job_id, predecessor_job_id, created_at
                   FROM project_relink_job
                   WHERE project_path = ? AND job_id <= ?
                   ORDER BY job_id ASC""",
                (job_row["project_path"], job_id),
            ).fetchall()
            for cr in chain_rows:
                predecessor_chain.append({
                    "job_id": cr["job_id"],
                    "predecessor_job_id": cr["predecessor_job_id"],
                    "created_at": cr["created_at"],
                })

        # 5. Parse version_info
        version_info = None
        if job_row.get("version_info"):
            try:
                version_info = json.loads(job_row["version_info"])
            except Exception:
                version_info = None

        # 6. Determine closure_status
        has_unresolved = len(missing_items) > 0 or len(unmatched_items) > 0
        closure_status = "incomplete" if has_unresolved else "complete"

        # 7. Build snapshot
        now = self._now()
        snapshot = {
            "report_version": "1.0",
            "generated_at": now,
            "project": {
                "path": job_row["project_path"],
                "type": job_row["project_type"],
                "version_info": version_info,
            },
            "resolution_summary": {
                "total_refs": len(items),
                "stable": len(stable),
                "relinked_system": len(relinked_system),
                "relinked_manual": len(relinked_manual),
                "missing": len(missing_items),
                "unmatched": len(unmatched_items),
            },
            "manual_bindings": manual_bindings_detail,
            "outputs": [
                {
                    "output_path": o.get("output_path", ""),
                    "applied_count": o.get("applied_count", 0),
                    "created_at": o.get("created_at", ""),
                }
                for o in (outputs if isinstance(outputs, list) else outputs.get("outputs", []))
            ],
            "action_timeline": [
                {
                    "action": a.get("action_type", ""),
                    "time": a.get("created_at", ""),
                    "operator": a.get("operator", ""),
                    "item_id": a.get("item_id"),
                }
                for a in (action_log if isinstance(action_log, list) else [])
            ],
            "verification": verification if verification else {"all_valid": None, "stale_count": None, "checked_at": None},
            "predecessor_chain": predecessor_chain,
            "closure_status": closure_status,
        }

        # 8. Persist snapshot (D-4 rule #4: frozen, replaces any prior)
        with self._connect() as conn:
            conn.execute(
                "UPDATE project_relink_job SET handover_at = ?, handover_snapshot = ?, updated_at = ? WHERE job_id = ?",
                (now, json.dumps(snapshot, ensure_ascii=False), now, job_id),
            )
            self._log_project_relink_action(
                conn, job_id, "handover", payload={
                    "closure_status": closure_status,
                    "generated_at": now,
                },
            )

        return snapshot

    def export_handover_report(self, job_id: int, fmt: str = "json") -> Dict:
        """
        Export the handover report as JSON or Markdown.

        D-4 rule #4: If handover_snapshot exists, use the frozen snapshot.
        Otherwise generate it first.
        """
        with self._connect() as conn:
            _row = conn.execute(
                "SELECT * FROM project_relink_job WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not _row:
                return {"error": f"Job {job_id} not found"}
            job_row = dict(_row)

        # Use existing snapshot or generate
        snapshot = None
        if job_row.get("handover_snapshot"):
            try:
                snapshot = json.loads(job_row["handover_snapshot"])
            except Exception:
                pass

        if not snapshot:
            snapshot = self.generate_handover_report(job_id, auto_verify=True)
            if snapshot.get("error"):
                return snapshot

        filename_base = f"handover_{job_id}"

        if fmt == "markdown":
            md = self._render_handover_markdown(snapshot, job_row)
            return {
                "markdown_content": md,
                "filename": f"{filename_base}.md",
            }
        else:
            return {
                "report": snapshot,
                "filename": f"{filename_base}.json",
            }

    def _render_handover_markdown(self, snapshot: Dict, job_row) -> str:
        """Render a handover snapshot as human-readable Markdown."""
        lines = []
        proj = snapshot.get("project", {})
        rs = snapshot.get("resolution_summary", {})
        lines.append("# 工程 Relink 交接报告\n")
        lines.append("## 工程信息\n")
        lines.append(f"- 路径: {proj.get('path', '')}")
        lines.append(f"- 类型: {proj.get('type', '')}")
        lines.append(f"- 分析日期: {job_row['created_at'] if job_row else ''}")
        lines.append(f"- 交接日期: {snapshot.get('generated_at', '')}")
        lines.append(f"- 状态: {snapshot.get('closure_status', '')}")
        lines.append("")

        lines.append("## 解决汇总\n")
        lines.append("| 分类 | 数量 |")
        lines.append("|------|------|")
        lines.append(f"| 总引用 | {rs.get('total_refs', 0)} |")
        lines.append(f"| 正常 | {rs.get('stable', 0)} |")
        lines.append(f"| 系统恢复 | {rs.get('relinked_system', 0)} |")
        lines.append(f"| 人工绑定 | {rs.get('relinked_manual', 0)} |")
        lines.append(f"| 缺失 | {rs.get('missing', 0)} |")
        lines.append(f"| 未匹配 | {rs.get('unmatched', 0)} |")
        lines.append("")

        bindings = snapshot.get("manual_bindings", [])
        if bindings:
            lines.append("## 人工绑定明细\n")
            lines.append("| 素材 | 原路径 | 绑定方式 | 来源 | 继承 |")
            lines.append("|------|--------|----------|------|------|")
            for b in bindings:
                inherited = "是" if b.get("inherited") else "否"
                lines.append(f"| {b.get('asset_name', '')} | {b.get('old_path', '')} | {b.get('bound_uid', '')} | {b.get('decision_source', '')} | {inherited} |")
            lines.append("")

        outputs = snapshot.get("outputs", [])
        if outputs:
            lines.append("## 输出副本\n")
            for o in outputs:
                lines.append(f"- {o.get('output_path', '')} (修复 {o.get('applied_count', 0)} 项, {o.get('created_at', '')})")
            lines.append("")

        v = snapshot.get("verification", {})
        lines.append("## 验证结果\n")
        if v.get("all_valid") is True:
            lines.append("全部路径有效 ✓")
        elif v.get("all_valid") is False:
            lines.append(f"{v.get('stale_count', 0)} 个路径已失效 ⚠")
        else:
            lines.append("未验证")
        lines.append("")

        timeline = snapshot.get("action_timeline", [])
        if timeline:
            lines.append("## 操作时间线\n")
            for i, a in enumerate(timeline, 1):
                lines.append(f"{i}. {a.get('time', '')} — {a.get('action', '')}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # v0.7 Phase D-1 – Per-project missing stats aggregation
    # ------------------------------------------------------------------

    def get_project_missing_stats(self, project_path: str) -> Dict:
        """
        Aggregate missing/unmatched stats across all jobs for a project path.

        Returns unique missing asset names, persistent missing items,
        and per-job trend data for visualization.
        """
        with self._connect() as conn:
            jobs = conn.execute(
                """
                SELECT job_id, status, created_at,
                       missing_refs, unmatched_refs, total_refs
                FROM project_relink_job
                WHERE project_path = ?
                ORDER BY job_id DESC
                """,
                (project_path,),
            ).fetchall()

            if not jobs:
                return {
                    "project_path": project_path,
                    "total_jobs": 0,
                    "unique_missing_assets": 0,
                    "persistent_missing": [],
                    "trend": [],
                }

            # Collect unique missing asset names across all done jobs
            done_job_ids = [j["job_id"] for j in jobs if j["status"] == "done"]
            all_missing_names: Dict[str, int] = {}  # asset_name -> count of jobs it appears in

            for jid in done_job_ids:
                names = conn.execute(
                    """
                    SELECT DISTINCT asset_name
                    FROM project_relink_item
                    WHERE job_id = ? AND status IN ('missing', 'unmatched')
                      AND asset_name IS NOT NULL AND asset_name != ''
                    """,
                    (jid,),
                ).fetchall()
                for row in names:
                    n = row["asset_name"]
                    all_missing_names[n] = all_missing_names.get(n, 0) + 1

            # Persistent = appears in more than half of done jobs
            threshold = max(1, len(done_job_ids) // 2)
            persistent = [
                {"asset_name": name, "occurrences": count}
                for name, count in sorted(
                    all_missing_names.items(), key=lambda x: x[1], reverse=True
                )
                if count >= threshold
            ]

            # Trend: per-job missing/unmatched counts over time
            trend = [
                {
                    "job_id": j["job_id"],
                    "created_at": j["created_at"],
                    "missing": j["missing_refs"] or 0,
                    "unmatched": j["unmatched_refs"] or 0,
                    "total": j["total_refs"] or 0,
                }
                for j in jobs
                if j["status"] == "done"
            ]
            trend.reverse()  # chronological order for charting

            return {
                "project_path": project_path,
                "total_jobs": len(jobs),
                "unique_missing_assets": len(all_missing_names),
                "persistent_missing": persistent,
                "trend": trend,
            }
