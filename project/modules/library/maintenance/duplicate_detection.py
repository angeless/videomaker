"""Duplicate detection mixin for GlobalMediaLibrary.

Extracted from global_media_library.py — contains duplicate scanning,
pHash similarity search, and duplicate group management methods.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from modules.step1_material_analysis.indexer.fingerprint import VideoHasher
except Exception:
    VideoHasher = None

logger = logging.getLogger(__name__)


class DuplicateDetectionMixin:
    """Methods related to duplicate/similar asset detection and management."""

    def _find_similar_by_phash(self, conn: sqlite3.Connection, phash: Optional[str], threshold: int = 5) -> tuple[Optional[str], Optional[int]]:
        if not phash:
            return None, None
        rows = conn.execute(
            "SELECT uid, phash FROM assets WHERE phash IS NOT NULL AND phash != ''"
        ).fetchall()
        best_uid = None
        best_dist = None
        for row in rows:
            candidate = row["phash"]
            dist = None
            if VideoHasher is not None:
                try:
                    dist = VideoHasher.hamming_distance(phash, candidate)
                except Exception:
                    dist = None
            if dist is None:
                dist = self._phash_distance(phash, candidate)
            if dist is None:
                continue
            if dist <= threshold and (best_dist is None or dist < best_dist):
                best_uid = row["uid"]
                best_dist = dist
        return best_uid, best_dist

    # ------------------------------------------------------------------
    # v0.7 – Duplicate detection
    # ------------------------------------------------------------------

    SIMILARITY_THRESHOLDS = {
        "near_identical": 3,
        "very_similar": 6,
        "similar": 10,
    }

    def detect_duplicates(self, threshold: int = 6) -> Dict:
        """
        Scan entire library for duplicate/similar assets.

        Detection strategy:
        1. Exact duplicates: same sha256 but different uid (shouldn't happen, but check)
        2. Near-identical: content_fingerprint hamming distance <= threshold

        Writes results to duplicate_group + duplicate_group_member tables.
        Returns: {groups_found, exact_groups, similar_groups, total_duplicate_assets}.
        """
        with self._connect() as conn:
            # Clear old pending groups (keep resolved/ignored)
            conn.execute("DELETE FROM duplicate_group_member WHERE group_id IN (SELECT group_id FROM duplicate_group WHERE status='pending')")
            conn.execute("DELETE FROM duplicate_group WHERE status='pending'")

            groups_found = 0
            exact_groups = 0
            similar_groups = 0
            total_dup_assets = 0

            # ── Phase 1: Exact sha256 duplicates across different uid ──
            # (edge case: shouldn't normally happen, but files ingested differently could create this)
            sha256_dups = conn.execute(
                """
                SELECT sha256, GROUP_CONCAT(uid) as uids, COUNT(*) as cnt
                FROM assets
                GROUP BY sha256
                HAVING cnt > 1
                """
            ).fetchall()

            for row in sha256_dups:
                uids = row["uids"].split(",")
                if len(uids) < 2:
                    continue

                # Create group
                conn.execute(
                    """
                    INSERT INTO duplicate_group (group_type, primary_uid, member_count, total_size_bytes, status)
                    VALUES ('exact_sha', ?, ?, 0, 'pending')
                    """,
                    (uids[0], len(uids)),
                )
                group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                total_size = 0
                for u in uids:
                    info = conn.execute(
                        "SELECT size_bytes, resolution, codec FROM assets WHERE uid=?", (u,)
                    ).fetchone()
                    sz = info["size_bytes"] or 0 if info else 0
                    total_size += sz
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO duplicate_group_member
                            (group_id, uid, fingerprint_distance, file_size, resolution, codec)
                        VALUES (?, ?, 0, ?, ?, ?)
                        """,
                        (group_id, u, sz,
                         info["resolution"] if info else None,
                         info["codec"] if info else None),
                    )
                conn.execute(
                    "UPDATE duplicate_group SET total_size_bytes=? WHERE group_id=?",
                    (total_size, group_id),
                )
                groups_found += 1
                exact_groups += 1
                total_dup_assets += len(uids)

            # ── Phase 2: Similar content_fingerprint ──
            # Two-stage: coarse filter (thumbnail_hash) → fine distance (content_fingerprint)
            # Note: idx_assets_content_fp is a B-tree index for IS NOT NULL queries only,
            # NOT a distance-aware index. All hamming distance computations happen in
            # application code. Future optimization: VP-tree or BK-tree for sub-linear lookup.
            fp_rows = conn.execute(
                """
                SELECT uid, content_fingerprint, thumbnail_hash, size_bytes, resolution, codec
                FROM assets
                WHERE content_fingerprint IS NOT NULL AND content_fingerprint != ''
                """
            ).fetchall()

            # Stage 1 (coarse): build thumbnail_hash → uid list for fast pre-grouping
            # Assets with very different thumbnails (distance > threshold * 2) are skipped
            # to avoid unnecessary content_fingerprint distance computation.
            # Stage 2 (fine): compute exact hamming distance on content_fingerprint for
            # pairs that survived the coarse filter.
            visited = set()
            for i, row_i in enumerate(fp_rows):
                uid_i = row_i["uid"]
                if uid_i in visited:
                    continue
                fp_i = row_i["content_fingerprint"]
                thumb_i = row_i["thumbnail_hash"]
                group_members = [(uid_i, 0)]

                for row_j in fp_rows[i + 1:]:
                    uid_j = row_j["uid"]
                    if uid_j in visited:
                        continue

                    # ── Coarse filter: thumbnail_hash pre-screen ──
                    # If both have thumbnail hashes, skip pair if thumbnails are very different
                    thumb_j = row_j["thumbnail_hash"]
                    if thumb_i and thumb_j:
                        thumb_dist = self._phash_distance(thumb_i, thumb_j)
                        if thumb_dist is not None and thumb_dist > threshold * 2:
                            continue  # thumbnails too different, skip expensive comparison

                    # ── Fine filter: content_fingerprint distance ──
                    fp_j = row_j["content_fingerprint"]
                    dist = self._phash_distance(fp_i, fp_j)
                    if dist is not None and dist <= threshold:
                        group_members.append((uid_j, dist))
                        visited.add(uid_j)

                if len(group_members) < 2:
                    continue

                visited.add(uid_i)
                # Classify group type by max distance
                max_dist = max(d for _, d in group_members)
                if max_dist <= self.SIMILARITY_THRESHOLDS["near_identical"]:
                    group_type = "near_identical"
                elif max_dist <= self.SIMILARITY_THRESHOLDS["very_similar"]:
                    group_type = "very_similar"
                else:
                    group_type = "similar"

                conn.execute(
                    """
                    INSERT INTO duplicate_group (group_type, primary_uid, member_count, total_size_bytes, status)
                    VALUES (?, ?, ?, 0, 'pending')
                    """,
                    (group_type, uid_i, len(group_members)),
                )
                group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                total_size = 0
                for uid_m, dist_m in group_members:
                    info = conn.execute(
                        "SELECT size_bytes, resolution, codec FROM assets WHERE uid=?", (uid_m,)
                    ).fetchone()
                    sz = info["size_bytes"] or 0 if info else 0
                    total_size += sz
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO duplicate_group_member
                            (group_id, uid, fingerprint_distance, file_size, resolution, codec)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (group_id, uid_m, dist_m, sz,
                         info["resolution"] if info else None,
                         info["codec"] if info else None),
                    )

                conn.execute(
                    "UPDATE duplicate_group SET total_size_bytes=? WHERE group_id=?",
                    (total_size, group_id),
                )
                groups_found += 1
                similar_groups += 1
                total_dup_assets += len(group_members)

        return {
            "groups_found": groups_found,
            "exact_groups": exact_groups,
            "similar_groups": similar_groups,
            "total_duplicate_assets": total_dup_assets,
        }

    def list_duplicate_groups(self, status: Optional[str] = None) -> List[Dict]:
        """List duplicate groups with their members."""
        with self._connect() as conn:
            if status:
                groups = conn.execute(
                    "SELECT * FROM duplicate_group WHERE status=? ORDER BY group_id",
                    (status,),
                ).fetchall()
            else:
                groups = conn.execute(
                    "SELECT * FROM duplicate_group ORDER BY group_id"
                ).fetchall()

            result = []
            for g in groups:
                members = conn.execute(
                    """
                    SELECT dgm.*, a.filename, a.primary_path
                    FROM duplicate_group_member dgm
                    LEFT JOIN assets a ON dgm.uid = a.uid
                    WHERE dgm.group_id = ?
                    ORDER BY dgm.fingerprint_distance
                    """,
                    (g["group_id"],),
                ).fetchall()
                result.append({
                    **dict(g),
                    "members": [dict(m) for m in members],
                })
            return result

    # ------------------------------------------------------------------
    # v0.7 Phase B – Duplicate resolution + unavailable assets
    # ------------------------------------------------------------------

    def resolve_duplicate_group(self, group_id: int) -> Dict:
        """Mark a duplicate group as resolved."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_group WHERE group_id=?", (group_id,)
            ).fetchone()
            if not row:
                return {"error": f"group {group_id} not found"}
            conn.execute(
                "UPDATE duplicate_group SET status='resolved', resolved_at=? WHERE group_id=?",
                (self._now(), group_id),
            )
            return {"ok": True, "group_id": group_id, "status": "resolved"}

    def ignore_duplicate_group(self, group_id: int) -> Dict:
        """Mark a duplicate group as ignored."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_group WHERE group_id=?", (group_id,)
            ).fetchone()
            if not row:
                return {"error": f"group {group_id} not found"}
            conn.execute(
                "UPDATE duplicate_group SET status='ignored', resolved_at=? WHERE group_id=?",
                (self._now(), group_id),
            )
            return {"ok": True, "group_id": group_id, "status": "ignored"}

    def set_duplicate_primary(self, group_id: int, uid: str) -> Dict:
        """Set the primary (keep) member of a duplicate group."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_group WHERE group_id=?", (group_id,)
            ).fetchone()
            if not row:
                return {"error": f"group {group_id} not found"}
            member = conn.execute(
                "SELECT * FROM duplicate_group_member WHERE group_id=? AND uid=?",
                (group_id, uid),
            ).fetchone()
            if not member:
                return {"error": f"uid {uid} is not a member of group {group_id}"}
            conn.execute(
                "UPDATE duplicate_group SET primary_uid=? WHERE group_id=?",
                (uid, group_id),
            )
            return {"ok": True, "group_id": group_id, "primary_uid": uid}

    def set_member_decision(self, group_id: int, member_id: int, decision: str) -> Dict:
        """Set keep/remove decision for a duplicate group member."""
        if decision not in ("keep", "remove", "undecided"):
            return {"error": f"invalid decision: {decision}, must be keep|remove|undecided"}
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_group_member WHERE id=? AND group_id=?",
                (member_id, group_id),
            ).fetchone()
            if not row:
                return {"error": f"member {member_id} not found in group {group_id}"}
            conn.execute(
                "UPDATE duplicate_group_member SET keep_decision=? WHERE id=?",
                (decision, member_id),
            )
            return {"ok": True, "member_id": member_id, "decision": decision}

