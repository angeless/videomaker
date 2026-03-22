"""Tests for modules.library.semantic.embedding_cache.EmbeddingCache."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from modules.library.semantic.embedding_cache import EmbeddingCache


class TestHitMiss:
    def test_put_and_get_returns_vector(self):
        cache = EmbeddingCache()
        vec = [1.0, 2.0, 3.0]
        cache.put("hello", vec)
        assert cache.get("hello") == vec

    def test_get_miss_returns_none(self):
        cache = EmbeddingCache()
        assert cache.get("nonexistent") is None

    def test_normalizes_query(self):
        cache = EmbeddingCache()
        cache.put("  Hello World  ", [1.0])
        assert cache.get("hello world") == [1.0]

    def test_empty_query_returns_none(self):
        cache = EmbeddingCache()
        cache.put("", [1.0])
        assert cache.get("") is None

    def test_empty_embedding_not_stored(self):
        cache = EmbeddingCache()
        cache.put("hello", [])
        assert cache.get("hello") is None


class TestTTL:
    def test_expired_entry_returns_none(self):
        cache = EmbeddingCache(ttl_seconds=1)
        cache.put("hello", [1.0])
        # Manually expire
        cache._store["hello"]["ts"] = time.time() - 2
        assert cache.get("hello") is None

    def test_fresh_entry_returns_vector(self):
        cache = EmbeddingCache(ttl_seconds=3600)
        cache.put("hello", [1.0])
        assert cache.get("hello") == [1.0]


class TestLRU:
    def test_evicts_oldest_when_full(self):
        cache = EmbeddingCache(max_size=4)
        for i in range(5):
            cache.put(f"q{i}", [float(i)])
        # oldest (q0) should be evicted
        assert cache.size <= 4

    def test_eviction_keeps_recent(self):
        cache = EmbeddingCache(max_size=4)
        for i in range(5):
            cache.put(f"q{i}", [float(i)])
            time.sleep(0.01)  # ensure ordering
        # most recent should survive
        assert cache.get("q4") == [4.0]


class TestClear:
    def test_clear_empties_cache(self):
        cache = EmbeddingCache()
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None


class TestSize:
    def test_size_tracks_entries(self):
        cache = EmbeddingCache()
        assert cache.size == 0
        cache.put("a", [1.0])
        assert cache.size == 1
        cache.put("b", [2.0])
        assert cache.size == 2
