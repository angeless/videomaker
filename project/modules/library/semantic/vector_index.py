"""Vector index engine — FAISS preferred, NumPy fallback."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Prevent OMP duplicate-library abort when torch + FAISS coexist (macOS)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    import faiss
except ImportError:
    faiss = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)


class VectorIndex:
    """Manages a vector index for similarity search.

    Uses FAISS ``IndexFlatIP`` (inner-product on L2-normalised vectors ≡
    cosine similarity) when the ``faiss`` package is available, otherwise
    falls back to brute-force NumPy search that replicates the original
    behaviour.

    The index is **incrementally updatable** (add / remove) and can be
    persisted to disk so that it survives process restarts.
    """

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    def __init__(self, dimension: int = 1536, index_dir: Optional[Path] = None):
        self._dim = dimension
        self._index_dir = Path(index_dir) if index_dir else None

        # UID ↔ position mapping
        self._uid_to_pos: Dict[str, int] = {}
        self._pos_to_uid: List[str] = []

        # Deleted positions (lazy deletion for FAISS)
        self._deleted: set = set()

        # Backend state
        self._faiss_index: Any = None  # faiss.IndexFlatIP or None
        self._np_matrix: Any = None    # np.ndarray (N × dim) or None

        self._use_faiss = faiss is not None
        self._dirty = False

        if self._index_dir:
            self._index_dir.mkdir(parents=True, exist_ok=True)
            self.load()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def add(self, uid: str, vector: List[float]) -> None:
        """Add or replace a single vector."""
        if np is None:
            return
        arr = self._to_unit_vector(vector)
        if arr is None:
            return

        if uid in self._uid_to_pos:
            self.remove(uid)

        pos = len(self._pos_to_uid)
        self._uid_to_pos[uid] = pos
        self._pos_to_uid.append(uid)

        if self._use_faiss and self._faiss_index is not None:
            self._faiss_index.add(arr.reshape(1, -1))
        elif self._use_faiss:
            self._faiss_index = faiss.IndexFlatIP(self._dim)
            self._faiss_index.add(arr.reshape(1, -1))
        else:
            if self._np_matrix is None:
                self._np_matrix = arr.reshape(1, -1)
            else:
                self._np_matrix = np.vstack([self._np_matrix, arr.reshape(1, -1)])

        self._dirty = True

    def remove(self, uid: str) -> None:
        """Mark a vector as deleted (lazy).  Cleaned up on next ``rebuild``."""
        pos = self._uid_to_pos.pop(uid, None)
        if pos is not None:
            self._deleted.add(pos)
            self._dirty = True

    def search(self, query_vector: List[float], top_k: int = 1200,
               threshold: float = 0.08) -> Dict[str, float]:
        """Return ``{uid: similarity}`` for the *top_k* nearest neighbours
        above *threshold*."""
        if np is None:
            return {}
        q = self._to_unit_vector(query_vector)
        if q is None:
            return {}

        n_total = len(self._pos_to_uid)
        if n_total == 0:
            return {}

        if self._use_faiss and self._faiss_index is not None:
            return self._search_faiss(q, top_k, threshold)
        return self._search_numpy(q, top_k, threshold)

    def rebuild(self, uids: List[str], vectors: Any) -> None:
        """Full rebuild from parallel UID list + (N × dim) matrix."""
        if np is None:
            return
        if not isinstance(vectors, np.ndarray) or vectors.ndim != 2:
            return
        if vectors.shape[0] != len(uids) or vectors.shape[1] != self._dim:
            return

        # L2-normalise rows
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        matrix = vectors / np.maximum(norms, 1e-8)

        self._uid_to_pos = {uid: i for i, uid in enumerate(uids)}
        self._pos_to_uid = list(uids)
        self._deleted.clear()

        if self._use_faiss:
            idx = faiss.IndexFlatIP(self._dim)
            idx.add(matrix.astype(np.float32))
            self._faiss_index = idx
            self._np_matrix = None
        else:
            self._np_matrix = matrix.astype(np.float32)
            self._faiss_index = None

        self._dirty = True

    def save(self) -> None:
        """Persist index + mapping to ``index_dir``."""
        if not self._index_dir or not self._dirty:
            return
        try:
            meta = {
                "dim": self._dim,
                "uids": self._pos_to_uid,
                "deleted": sorted(self._deleted),
                "use_faiss": self._use_faiss and self._faiss_index is not None,
            }
            meta_path = self._index_dir / "index_meta.json"
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

            if self._use_faiss and self._faiss_index is not None:
                faiss.write_index(self._faiss_index,
                                  str(self._index_dir / "index.faiss"))
            elif self._np_matrix is not None:
                np.save(str(self._index_dir / "index.npy"), self._np_matrix)

            self._dirty = False
            _log.info("VectorIndex saved to %s (%d vectors)", self._index_dir,
                      self.count)
        except Exception:
            _log.warning("VectorIndex save failed", exc_info=True)

    def load(self) -> bool:
        """Load index from ``index_dir``.  Returns True on success."""
        if not self._index_dir:
            return False
        meta_path = self._index_dir / "index_meta.json"
        if not meta_path.exists():
            return False
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self._dim = int(meta.get("dim", self._dim))
            self._pos_to_uid = list(meta.get("uids", []))
            self._uid_to_pos = {uid: i for i, uid in enumerate(self._pos_to_uid)}
            self._deleted = set(meta.get("deleted", []))

            was_faiss = meta.get("use_faiss", False)
            faiss_path = self._index_dir / "index.faiss"
            npy_path = self._index_dir / "index.npy"

            if was_faiss and self._use_faiss and faiss_path.exists():
                self._faiss_index = faiss.read_index(str(faiss_path))
                self._np_matrix = None
            elif npy_path.exists():
                self._np_matrix = np.load(str(npy_path))
                self._faiss_index = None
            else:
                return False

            self._dirty = False
            _log.info("VectorIndex loaded from %s (%d vectors)", self._index_dir,
                      self.count)
            return True
        except Exception:
            _log.warning("VectorIndex load failed, will rebuild on demand",
                         exc_info=True)
            self._reset()
            return False

    @property
    def count(self) -> int:
        """Number of active (non-deleted) vectors."""
        return len(self._uid_to_pos)

    @property
    def needs_compact(self) -> bool:
        """True when deleted positions exceed 20% of total."""
        total = len(self._pos_to_uid)
        return total > 0 and len(self._deleted) > total * 0.2

    # ------------------------------------------------------------------
    # FAISS search
    # ------------------------------------------------------------------

    def _search_faiss(self, q: Any, top_k: int, threshold: float) -> Dict[str, float]:
        n_total = self._faiss_index.ntotal
        k = min(max(1, top_k + len(self._deleted)), n_total)
        scores, indices = self._faiss_index.search(q.reshape(1, -1).astype(np.float32), k)

        out: Dict[str, float] = {}
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._pos_to_uid):
                continue
            if idx in self._deleted:
                continue
            s = float(score)
            if s < threshold:
                continue
            uid = self._pos_to_uid[idx]
            if uid in self._uid_to_pos:
                out[uid] = s
            if len(out) >= top_k:
                break
        return out

    # ------------------------------------------------------------------
    # NumPy fallback search
    # ------------------------------------------------------------------

    def _search_numpy(self, q: Any, top_k: int, threshold: float) -> Dict[str, float]:
        if self._np_matrix is None:
            return {}
        if self._np_matrix.shape[1] != q.shape[0]:
            return {}

        sims = self._np_matrix @ q
        count = int(sims.shape[0])
        if count <= 0:
            return {}

        k = min(max(1, top_k), count)
        if k >= count:
            top_idx = np.arange(count)
        else:
            top_idx = np.argpartition(-sims, k - 1)[:k]
        sorted_idx = top_idx[np.argsort(sims[top_idx])[::-1]]

        out: Dict[str, float] = {}
        for idx in sorted_idx:
            i = int(idx)
            if i in self._deleted:
                continue
            s = float(sims[i])
            if s < threshold:
                continue
            if i < len(self._pos_to_uid):
                uid = self._pos_to_uid[i]
                if uid in self._uid_to_pos:
                    out[uid] = s
        return out

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _to_unit_vector(self, vec: List[float]) -> Any:
        """Convert list → L2-normalised np.float32 array, or None."""
        if np is None or not vec:
            return None
        try:
            arr = np.array([float(x) for x in vec], dtype=np.float32)
        except (ValueError, TypeError):
            return None
        if arr.shape != (self._dim,):
            return None
        norm = float(np.linalg.norm(arr))
        if norm < 1e-8:
            return None
        return arr / norm

    def _reset(self) -> None:
        self._uid_to_pos.clear()
        self._pos_to_uid.clear()
        self._deleted.clear()
        self._faiss_index = None
        self._np_matrix = None
        self._dirty = False
