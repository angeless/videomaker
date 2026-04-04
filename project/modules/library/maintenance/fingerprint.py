"""Fingerprint computation mixin for GlobalMediaLibrary.

Extracted from global_media_library.py — contains SHA-256, pHash, content
fingerprint, and thumbnail hash computation plus backfill / health helpers.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import numpy as np
except Exception:
    np = None

try:
    import cv2
except Exception:
    cv2 = None

try:
    from modules.step1_material_analysis.indexer.fingerprint import VideoHasher
except Exception:
    VideoHasher = None

logger = logging.getLogger(__name__)


class FingerprintMixin:
    """Methods related to file hashing and perceptual fingerprinting."""

    FINGERPRINT_VERSION = 1  # bump when algorithm changes

    # ------------------------------------------------------------------
    # SHA-256
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                block = f.read(chunk_size)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Perceptual hash (video / image)
    # ------------------------------------------------------------------

    def _compute_phash(self, path: Path) -> Optional[str]:
        if VideoHasher is None:
            return None
        try:
            fingerprint = VideoHasher.compute_video_fingerprint(str(path), sample_interval=2.0)
            return fingerprint.get("representative_hash") or None
        except Exception:
            return None

    @staticmethod
    def _compute_image_phash(path: Path) -> Optional[str]:
        if cv2 is None or np is None:
            return None
        try:
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                return None
            resized = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
            dct = cv2.dct(np.float32(resized))
            low = dct[:8, :8]
            med = float(np.median(low[1:, 1:])) if low.size >= 4 else float(np.median(low))
            bits = "".join("1" if v > med else "0" for v in low.flatten())
            return f"{int(bits, 2):016x}"
        except Exception:
            return None

    @staticmethod
    def _phash_distance(a: Optional[str], b: Optional[str]) -> Optional[int]:
        x = str(a or "").strip().lower()
        y = str(b or "").strip().lower()
        if not x or not y:
            return None
        if len(x) != len(y):
            return None
        try:
            return bin(int(x, 16) ^ int(y, 16)).count("1")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Content fingerprint (L2)
    # ------------------------------------------------------------------

    def _compute_content_fingerprint(self, path: Path, media_type: str = "video") -> Optional[str]:
        """
        Compute content fingerprint (L2).

        Video: SimHash aggregation of all sampled frame pHashes via VideoHasher.
        Image: reuse DCT pHash (same as _compute_image_phash).
        """
        if media_type == "image":
            return self._compute_image_phash(path)

        # Video path: sample frames → frame pHashes → SimHash aggregate
        if VideoHasher is None:
            return None
        try:
            fp = VideoHasher.compute_video_fingerprint(str(path), sample_interval=2.0)
            frame_hashes = fp.get("frame_hashes", [])
            if not frame_hashes:
                return fp.get("representative_hash") or None
            return VideoHasher.simhash_aggregate(frame_hashes) or None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Thumbnail hash (L3)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_thumbnail_hash(path: Path, media_type: str = "video") -> Optional[str]:
        """
        Compute thumbnail hash (L3) – first/representative frame 8×8 DCT hash.

        Quick pre-filter: millisecond-level exclusion of obviously different assets.
        """
        if cv2 is None or np is None:
            return None
        try:
            if media_type == "image":
                img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            else:
                cap = cv2.VideoCapture(str(path))
                try:
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        return None
                    img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                finally:
                    cap.release()

            if img is None:
                return None
            resized = cv2.resize(img, (8, 8), interpolation=cv2.INTER_AREA)
            dct = cv2.dct(np.float32(resized))
            med = float(np.median(dct))
            bits = "".join("1" if v > med else "0" for v in dct.flatten())
            return f"{int(bits, 2):016x}"
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Backfill & health
    # ------------------------------------------------------------------

    def backfill_fingerprints(self, limit: int = 0) -> Dict:
        """
        Compute content_fingerprint + thumbnail_hash for existing assets
        that don't have them yet.

        Args:
            limit: max assets to process (0 = unlimited)

        Returns: {processed, succeeded, failed, skipped}.
        """
        with self._connect() as conn:
            query = """
                SELECT uid, primary_path, source_type
                FROM assets
                WHERE (content_fingerprint IS NULL OR thumbnail_hash IS NULL
                       OR fingerprint_version IS NULL OR fingerprint_version < ?)
            """
            params: list = [self.FINGERPRINT_VERSION]
            if limit > 0:
                query += " LIMIT ?"
                params.append(limit)

            rows = conn.execute(query, params).fetchall()

        processed = 0
        succeeded = 0
        failed = 0
        skipped = 0

        for row in rows:
            uid = row["uid"]
            primary_path = row["primary_path"]
            source_type = row["source_type"] or "local"
            processed += 1

            if not primary_path or not Path(primary_path).exists():
                skipped += 1
                continue

            path = Path(primary_path)
            media_type = "image" if source_type == "image" else "video"

            try:
                content_fp = self._compute_content_fingerprint(path, media_type)
                thumb_hash = self._compute_thumbnail_hash(path, media_type)

                with self._connect() as conn:
                    conn.execute(
                        """
                        UPDATE assets
                        SET content_fingerprint=COALESCE(?, content_fingerprint),
                            thumbnail_hash=COALESCE(?, thumbnail_hash),
                            fingerprint_version=?,
                            updated_at=?
                        WHERE uid=?
                        """,
                        (content_fp, thumb_hash, self.FINGERPRINT_VERSION, self._now(), uid),
                    )
                succeeded += 1
            except Exception as e:
                logger.warning("Fingerprint backfill failed for %s: %s", uid, e)
                failed += 1

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        }

    def get_fingerprint_health(self) -> Dict:
        """Return fingerprint coverage and health statistics."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            with_fp = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE content_fingerprint IS NOT NULL AND content_fingerprint != ''"
            ).fetchone()[0]
            with_thumb = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE thumbnail_hash IS NOT NULL AND thumbnail_hash != ''"
            ).fetchone()[0]
            with_phash = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE phash IS NOT NULL AND phash != ''"
            ).fetchone()[0]
            current_version = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE fingerprint_version = ?",
                (self.FINGERPRINT_VERSION,),
            ).fetchone()[0]

            dup_groups = conn.execute("SELECT COUNT(*) FROM duplicate_group").fetchone()[0]
            pending_dups = conn.execute(
                "SELECT COUNT(*) FROM duplicate_group WHERE status='pending'"
            ).fetchone()[0]

            roots_active = conn.execute(
                "SELECT COUNT(*) FROM known_media_roots WHERE is_active=1"
            ).fetchone()[0]

            path_changes = conn.execute(
                "SELECT COUNT(*) FROM path_change_log"
            ).fetchone()[0]

        return {
            "total_assets": total,
            "with_content_fingerprint": with_fp,
            "with_thumbnail_hash": with_thumb,
            "with_phash": with_phash,
            "fingerprint_coverage_pct": round(with_fp / total * 100, 1) if total > 0 else 0,
            "current_version_count": current_version,
            "fingerprint_version": self.FINGERPRINT_VERSION,
            "needs_backfill": max(0, total - current_version),
            "duplicate_groups": dup_groups,
            "pending_duplicate_groups": pending_dups,
            "known_roots_active": roots_active,
            "total_path_changes": path_changes,
        }
