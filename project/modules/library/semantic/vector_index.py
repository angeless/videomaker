"""Vector index engine — FAISS preferred, NumPy fallback."""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        self._lock = threading.RLock()

        if self._index_dir:
            self._index_dir.mkdir(parents=True, exist_ok=True)
            self.load()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def add(self, uid: str, vector: List[float], _wal: bool = True) -> None:
        """Add or replace a single vector."""
        if np is None:
            return
        arr = self._to_unit_vector(vector)
        if arr is None:
            return

        with self._lock:
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
            if _wal:
                self._wal_append(uid, arr)

    def add_batch(self, uid_vec_pairs: List[Tuple[str, List[float]]]) -> int:
        """Add multiple vectors atomically.  Returns count added."""
        with self._lock:
            added = 0
            for uid, vec in uid_vec_pairs:
                prev = len(self._uid_to_pos)
                self.add(uid, vec)
                if len(self._uid_to_pos) > prev:
                    added += 1
            return added

    def remove(self, uid: str) -> None:
        """Mark a vector as deleted (lazy).  Cleaned up on next ``rebuild``."""
        with self._lock:
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
        with self._lock:
            n_total = len(self._pos_to_uid)
            if n_total == 0:
                return {}
            if self._use_faiss and self._faiss_index is not None:
                return self._search_faiss(q, top_k, threshold)
            return self._search_numpy(q, top_k, threshold)

    def rebuild(self, uids: List[str], vectors: Any) -> None:
        """Full rebuild from parallel UID list + (N × dim) matrix.

        R6a: auto-selects IndexIVFFlat when N >= FAISS_IVF_THRESHOLD.
        """
        if np is None:
            return
        if not isinstance(vectors, np.ndarray) or vectors.ndim != 2:
            return
        if vectors.shape[0] != len(uids) or vectors.shape[1] != self._dim:
            return
        with self._lock:
            self._rebuild_unlocked(uids, vectors)

    def _rebuild_unlocked(self, uids: List[str], vectors: Any) -> None:

        # L2-normalise rows
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        matrix = vectors / np.maximum(norms, 1e-8)
        matrix = matrix.astype(np.float32)

        self._uid_to_pos = {uid: i for i, uid in enumerate(uids)}
        self._pos_to_uid = list(uids)
        self._deleted.clear()

        if self._use_faiss:
            self._faiss_index = self._build_faiss_index(matrix)
            self._np_matrix = None
        else:
            self._np_matrix = matrix
            self._faiss_index = None

        self._dirty = True

    def _build_faiss_index(self, matrix: Any) -> Any:
        """Build the appropriate FAISS index based on vector count (R6a)."""
        from modules.library._constants import FAISS_IVF_THRESHOLD, FAISS_IVF_NLIST

        n = matrix.shape[0]
        if n >= FAISS_IVF_THRESHOLD:
            nlist = FAISS_IVF_NLIST
            min_train = max(nlist * 39, nlist + 1)
            if n >= min_train:
                try:
                    quantizer = faiss.IndexFlatIP(self._dim)
                    idx = faiss.IndexIVFFlat(quantizer, self._dim, nlist, faiss.METRIC_INNER_PRODUCT)
                    idx.train(matrix)
                    idx.add(matrix)
                    idx.nprobe = max(1, nlist // 10)
                    idx.make_direct_map()  # needed for reconstruct() in compact
                    _log.info("VectorIndex: IVFFlat index built (n=%d, nlist=%d, nprobe=%d)", n, nlist, idx.nprobe)
                    return idx
                except Exception:
                    _log.warning("VectorIndex: IVFFlat construction failed, falling back to FlatIP", exc_info=True)
            else:
                _log.warning("VectorIndex: insufficient vectors for IVF training (%d < %d), using FlatIP", n, min_train)

        idx = faiss.IndexFlatIP(self._dim)
        idx.add(matrix)
        return idx

    def save(self) -> None:
        """Persist index + mapping to ``index_dir``.

        NOTE: If a crash occurs between compact_if_needed() and _save_unlocked(),
        the on-disk state will still have the old index + WAL. On next load(),
        WAL replay may re-add vectors that already exist in the old index.
        This is self-healing: add() removes duplicates by UID before re-adding.
        No data is lost, only a minor startup overhead.
        """
        if not self._index_dir or not self._dirty:
            return
        with self._lock:
            self.compact_if_needed()
            self._save_unlocked()

    def _save_unlocked(self) -> None:
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
            self._wal_clear()  # R6b: checkpoint — WAL merged into main index
            _log.info("VectorIndex saved to %s (%d vectors)", self._index_dir,
                      self.count)
        except Exception:
            _log.warning("VectorIndex save failed", exc_info=True)

    def checkpoint(self) -> None:
        """Alias for save() — merges WAL into main index and clears WAL."""
        self._dirty = True  # force save even if no new adds
        self.save()

    def load(self) -> bool:
        """Load index from ``index_dir``.  Returns True on success."""
        if not self._index_dir:
            return False
        meta_path = self._index_dir / "index_meta.json"
        if not meta_path.exists():
            return False
        with self._lock:
            return self._load_unlocked(meta_path)

    def _load_unlocked(self, meta_path: Path) -> bool:
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
            # R6b: replay WAL
            wal_count = self._wal_replay()
            if wal_count > 0:
                _log.info("VectorIndex WAL replayed %d entries", wal_count)
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
        with self._lock:
            return len(self._uid_to_pos)

    @property
    def needs_compact(self) -> bool:
        """True when deleted positions exceed 20% of total."""
        with self._lock:
            total = len(self._pos_to_uid)
            return total > 0 and len(self._deleted) > total * 0.2

    def compact_if_needed(self) -> bool:
        """Rebuild index in-place if deleted ratio > 20%.  Returns True if compacted."""
        with self._lock:
            if not self.needs_compact:
                return False
            n_del = len(self._deleted)
            n_total = len(self._pos_to_uid)
            _log.info("VectorIndex compact triggered: %d deleted / %d total", n_del, n_total)

            live_uids: List[str] = []
            live_vecs: List[Any] = []
            for pos, uid in enumerate(self._pos_to_uid):
                if pos in self._deleted:
                    continue
                vec = self._extract_vector(pos)
                if vec is not None:
                    live_uids.append(uid)
                    live_vecs.append(vec)

            if not live_vecs:
                self._reset()
                return True

            matrix = np.vstack(live_vecs).astype(np.float32)
            self.rebuild(live_uids, matrix)
            return True

    def _extract_vector(self, pos: int) -> Any:
        """Extract raw vector at position *pos* from the current backend."""
        try:
            if self._use_faiss and self._faiss_index is not None:
                if pos < self._faiss_index.ntotal:
                    return self._faiss_index.reconstruct(pos)
            elif self._np_matrix is not None:
                if pos < self._np_matrix.shape[0]:
                    return self._np_matrix[pos].copy()
        except Exception:
            _log.debug("_extract_vector(%d) failed", pos, exc_info=True)
        return None

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

    # ------------------------------------------------------------------
    # WAL (Write-Ahead Log) — R6b
    # ------------------------------------------------------------------

    @property
    def _wal_path(self) -> Optional[Path]:
        if not self._index_dir:
            return None
        from modules.library._constants import VECTOR_WAL_FILENAME
        return self._index_dir / VECTOR_WAL_FILENAME

    def _wal_append(self, uid: str, arr: Any) -> None:
        """Append a single add entry to WAL.  Best-effort, never raises."""
        wp = self._wal_path
        if wp is None or np is None:
            return
        try:
            vec_b64 = base64.b64encode(arr.astype(np.float32).tobytes()).decode("ascii")
            line = json.dumps({"op": "add", "uid": uid, "vec_b64": vec_b64}, ensure_ascii=True)
            with open(wp, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            _log.debug("WAL append failed for %s", uid, exc_info=True)

    def _wal_replay(self) -> int:
        """Replay WAL entries into the live index.  Returns count replayed.

        Skips corrupted lines individually instead of aborting entire replay.
        """
        wp = self._wal_path
        if wp is None or not wp.exists() or np is None:
            return 0
        count = 0
        skipped = 0
        try:
            lines = wp.read_text(encoding="utf-8").splitlines()
        except Exception:
            _log.warning("WAL read failed", exc_info=True)
            return 0
        for raw_line in lines:
            try:
                line = raw_line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("op") != "add":
                    continue
                uid = entry.get("uid", "")
                vec_b64 = entry.get("vec_b64", "")
                if not uid or not vec_b64:
                    continue
                arr = np.frombuffer(base64.b64decode(vec_b64), dtype=np.float32)
                if arr.shape == (self._dim,):
                    self.add(uid, arr.tolist(), _wal=False)
                    count += 1
            except Exception:
                skipped += 1
                _log.debug("WAL line skipped (corrupted)", exc_info=True)
        if skipped > 0:
            _log.warning("WAL replay: %d lines skipped (corrupted)", skipped)
        if count > 0:
            self._dirty = True  # ensure next save() clears WAL
        return count

    def _wal_clear(self) -> None:
        """Delete WAL file after successful checkpoint."""
        wp = self._wal_path
        if wp is not None and wp.exists():
            try:
                wp.unlink()
            except Exception:
                pass
