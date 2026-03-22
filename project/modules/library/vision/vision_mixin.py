"""VisionMixin — visual analysis and cross-modal search for GlobalMediaLibrary."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from modules.library.vision.clip_encoder import CLIPEncoder

_log = logging.getLogger(__name__)

CLIP_MODEL_NAME = "clip-vit-base-patch32"
NUM_KEYFRAMES = 3


class VisionMixin:
    """Mixin adding CLIP-based visual search to GlobalMediaLibrary.

    Expects the host class to provide:
    - ``self._visual_index``  — a ``VectorIndex(dim=512)`` instance
    - ``self._connect()``     — returns a ``sqlite3.Connection``
    - ``self._now()``         — returns an ISO timestamp string
    """

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def visual_search(self, query: str, top_k: int = 50,
                      threshold: float = 0.15) -> Dict[str, float]:
        """Search visual index using CLIP text encoding.

        Returns ``{asset_uid: best_frame_score}`` aggregated across frames.
        """
        if not hasattr(self, "_clip_encoder") or self._clip_encoder is None:
            return {}
        if not hasattr(self, "_visual_index") or self._visual_index is None:
            return {}

        text_vec = self._clip_encoder.encode_text(query)
        if not text_vec:
            return {}

        # Ensure visual index is populated
        self._refresh_visual_index()

        raw_results = self._visual_index.search(text_vec, top_k=top_k * NUM_KEYFRAMES,
                                                 threshold=threshold)
        # Aggregate: frame UID "abc123_f0" → asset UID "abc123", keep max score
        aggregated: Dict[str, float] = {}
        for frame_uid, score in raw_results.items():
            asset_uid = frame_uid.rsplit("_f", 1)[0] if "_f" in frame_uid else frame_uid
            if asset_uid not in aggregated or score > aggregated[asset_uid]:
                aggregated[asset_uid] = score

        # Sort by score descending, limit to top_k
        sorted_items = sorted(aggregated.items(), key=lambda x: -x[1])[:top_k]
        return dict(sorted_items)

    def index_asset_visual(self, uid: str, video_path: str) -> int:
        """Extract keyframes from *video_path* and index CLIP embeddings.

        Returns the number of frames indexed (0 if CLIP unavailable).
        """
        if not hasattr(self, "_clip_encoder") or self._clip_encoder is None:
            return 0

        frames = CLIPEncoder.extract_keyframes(video_path, num_frames=NUM_KEYFRAMES)
        if not frames:
            return 0

        vectors: List[Dict] = []
        for i, frame in enumerate(frames):
            vec = self._clip_encoder.encode_image(frame)
            if vec:
                frame_uid = f"{uid}_f{i}"
                vectors.append({"frame_uid": frame_uid, "index": i, "vec": vec})

        if not vectors:
            return 0

        # Store in SQLite for persistence
        conn = self._connect()
        try:
            now = self._now()
            for item in vectors:
                conn.execute(
                    """INSERT OR REPLACE INTO asset_visual_embeddings
                       (uid, frame_index, model, embedding_json, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (uid, item["index"], CLIP_MODEL_NAME,
                     json.dumps(item["vec"]), now),
                )
            conn.commit()

            # Add to visual VectorIndex
            for item in vectors:
                self._visual_index.add(item["frame_uid"], item["vec"])
            self._visual_index.save()

        finally:
            conn.close()

        return len(vectors)

    # ------------------------------------------------------------------
    # index refresh (load from DB into VectorIndex)
    # ------------------------------------------------------------------

    def _refresh_visual_index(self) -> None:
        """Load visual embeddings from DB into VectorIndex if stale."""
        if not hasattr(self, "_visual_index") or self._visual_index is None:
            return
        if not hasattr(self, "_visual_index_loaded"):
            self._visual_index_loaded = False

        if self._visual_index_loaded and self._visual_index.count > 0:
            return

        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT uid, frame_index, embedding_json FROM asset_visual_embeddings"
            ).fetchall()

            if not rows:
                self._visual_index_loaded = True
                return

            import numpy as np
            uids: List[str] = []
            vecs: List[List[float]] = []
            for row in rows:
                frame_uid = f"{row['uid']}_f{row['frame_index']}"
                try:
                    vec = json.loads(row["embedding_json"])
                    if isinstance(vec, list) and len(vec) == CLIPEncoder.DIMENSION:
                        uids.append(frame_uid)
                        vecs.append([float(x) for x in vec])
                except Exception:
                    continue

            if uids:
                matrix = np.array(vecs, dtype=np.float32)
                self._visual_index.rebuild(uids, matrix)
                self._visual_index.save()

            self._visual_index_loaded = True
        finally:
            conn.close()
