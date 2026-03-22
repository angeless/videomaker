"""Query embedding LRU cache with TTL expiry."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class EmbeddingCache:
    """In-memory LRU cache for query embeddings.

    Stores (query → vector) mappings with a configurable max size and TTL.
    When max_size is exceeded, the oldest 25% of entries are evicted.
    """

    def __init__(self, max_size: int = 128, ttl_seconds: int = 3600):
        self._max_size = max(1, max_size)
        self._ttl = max(0, ttl_seconds)
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, query: str) -> Optional[List[float]]:
        """Return cached embedding for *query*, or None on miss/expiry."""
        key = self._normalize(query)
        if not key:
            return None
        entry = self._store.get(key)
        if entry is None:
            return None
        if (time.time() - float(entry.get("ts", 0.0))) >= self._ttl:
            self._store.pop(key, None)
            return None
        vec = entry.get("vec")
        if isinstance(vec, list) and vec:
            return vec
        return None

    def put(self, query: str, embedding: List[float]) -> None:
        """Cache *embedding* for *query*.  Evicts oldest entries if full."""
        key = self._normalize(query)
        if not key or not embedding:
            return
        self._store[key] = {"ts": time.time(), "vec": embedding}
        if len(self._store) > self._max_size:
            self._evict()

    def clear(self) -> None:
        """Drop all cached entries."""
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------
    # internals

    @staticmethod
    def _normalize(query: str) -> str:
        return str(query or "").strip().lower()

    def _evict(self) -> None:
        """Remove oldest 25% of entries."""
        n_remove = max(1, len(self._store) // 4)
        oldest = sorted(
            self._store.items(),
            key=lambda kv: float(kv[1].get("ts", 0.0)),
        )[:n_remove]
        for k, _ in oldest:
            self._store.pop(k, None)
