"""Tests for modules.library.semantic.vector_index.VectorIndex."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from modules.library.semantic.vector_index import VectorIndex


DIM = 8  # small dimension for fast tests


def _random_vec(dim: int = DIM) -> list:
    v = np.random.randn(dim).astype(np.float32).tolist()
    return v


@pytest.fixture
def tmp_dir():
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------
# basic add + search
# ------------------------------------------------------------------


class TestAddSearch:
    def test_add_and_search_returns_match(self):
        idx = VectorIndex(dimension=DIM)
        v = _random_vec()
        idx.add("a1", v)
        results = idx.search(v, top_k=5, threshold=0.0)
        assert "a1" in results
        assert results["a1"] > 0.9  # same vector, similarity ≈ 1

    def test_search_empty_index_returns_empty(self):
        idx = VectorIndex(dimension=DIM)
        results = idx.search(_random_vec(), top_k=5)
        assert results == {}

    def test_search_respects_threshold(self):
        idx = VectorIndex(dimension=DIM)
        v1 = [1.0] + [0.0] * (DIM - 1)
        v2 = [0.0] + [1.0] + [0.0] * (DIM - 2)
        idx.add("a1", v1)
        # orthogonal vector → similarity ≈ 0
        results = idx.search(v2, top_k=5, threshold=0.5)
        assert "a1" not in results

    def test_search_top_k_limits_results(self):
        idx = VectorIndex(dimension=DIM)
        for i in range(10):
            idx.add(f"a{i}", _random_vec())
        q = _random_vec()
        results = idx.search(q, top_k=3, threshold=0.0)
        assert len(results) <= 3

    def test_add_replaces_existing(self):
        idx = VectorIndex(dimension=DIM)
        v1 = [1.0] + [0.0] * (DIM - 1)
        v2 = [0.0] + [1.0] + [0.0] * (DIM - 2)
        idx.add("a1", v1)
        idx.add("a1", v2)  # replace
        assert idx.count == 1
        results = idx.search(v2, top_k=5, threshold=0.5)
        assert "a1" in results


# ------------------------------------------------------------------
# remove
# ------------------------------------------------------------------


class TestRemove:
    def test_remove_excludes_from_search(self):
        idx = VectorIndex(dimension=DIM)
        v = _random_vec()
        idx.add("a1", v)
        idx.remove("a1")
        results = idx.search(v, top_k=5, threshold=0.0)
        assert "a1" not in results
        assert idx.count == 0

    def test_remove_nonexistent_is_noop(self):
        idx = VectorIndex(dimension=DIM)
        idx.remove("nonexistent")  # should not raise
        assert idx.count == 0


# ------------------------------------------------------------------
# rebuild
# ------------------------------------------------------------------


class TestRebuild:
    def test_rebuild_replaces_index(self):
        idx = VectorIndex(dimension=DIM)
        idx.add("old", _random_vec())

        new_uids = ["b1", "b2", "b3"]
        matrix = np.random.randn(3, DIM).astype(np.float32)
        idx.rebuild(new_uids, matrix)

        assert idx.count == 3
        # old entry gone
        assert "old" not in idx.search(_random_vec(), top_k=10, threshold=0.0)

    def test_rebuild_invalid_shape_is_noop(self):
        idx = VectorIndex(dimension=DIM)
        idx.add("a1", _random_vec())
        # wrong dimension
        bad_matrix = np.random.randn(2, DIM + 1).astype(np.float32)
        idx.rebuild(["x", "y"], bad_matrix)
        # original still intact
        assert idx.count == 1


# ------------------------------------------------------------------
# persistence
# ------------------------------------------------------------------


class TestPersistence:
    def test_save_and_load(self, tmp_dir):
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        vectors = {}
        for i in range(5):
            v = _random_vec()
            idx.add(f"a{i}", v)
            vectors[f"a{i}"] = v
        idx.save()

        # Load into fresh instance
        idx2 = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        assert idx2.count == 5

        # Search consistency
        for uid, v in vectors.items():
            results = idx2.search(v, top_k=5, threshold=0.5)
            assert uid in results

    def test_load_nonexistent_dir(self, tmp_dir):
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir / "nonexistent_sub")
        assert idx.count == 0

    def test_load_corrupted_meta(self, tmp_dir):
        (tmp_dir / "index_meta.json").write_text("not json", encoding="utf-8")
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        assert idx.count == 0


# ------------------------------------------------------------------
# numpy fallback
# ------------------------------------------------------------------


class TestNumpyFallback:
    def test_fallback_search_works(self):
        """Force NumPy backend by setting _use_faiss=False."""
        idx = VectorIndex(dimension=DIM)
        idx._use_faiss = False
        idx._faiss_index = None

        v = _random_vec()
        idx.add("a1", v)
        results = idx.search(v, top_k=5, threshold=0.0)
        assert "a1" in results
        assert results["a1"] > 0.9

    def test_fallback_remove_works(self):
        idx = VectorIndex(dimension=DIM)
        idx._use_faiss = False
        idx._faiss_index = None

        v = _random_vec()
        idx.add("a1", v)
        idx.remove("a1")
        results = idx.search(v, top_k=5, threshold=0.0)
        assert "a1" not in results


# ------------------------------------------------------------------
# edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_vector_rejected(self):
        idx = VectorIndex(dimension=DIM)
        idx.add("a1", [])
        assert idx.count == 0

    def test_wrong_dimension_rejected(self):
        idx = VectorIndex(dimension=DIM)
        idx.add("a1", [1.0, 2.0])  # wrong dim
        assert idx.count == 0

    def test_zero_vector_rejected(self):
        idx = VectorIndex(dimension=DIM)
        idx.add("a1", [0.0] * DIM)
        assert idx.count == 0

    def test_needs_compact(self):
        idx = VectorIndex(dimension=DIM)
        for i in range(10):
            idx.add(f"a{i}", _random_vec())
        for i in range(3):
            idx.remove(f"a{i}")
        assert idx.needs_compact  # 3/10 = 30% > 20%


# ------------------------------------------------------------------
# compact_if_needed (R4 W-006)
# ------------------------------------------------------------------


class TestCompact:
    def test_compact_clears_deleted_above_threshold(self):
        """Add 10, delete 3 (30%) → compact → _deleted empty."""
        idx = VectorIndex(dimension=DIM)
        vecs = {}
        for i in range(10):
            v = _random_vec()
            idx.add(f"a{i}", v)
            vecs[f"a{i}"] = v
        for i in range(3):
            idx.remove(f"a{i}")

        assert idx.needs_compact
        result = idx.compact_if_needed()
        assert result is True
        assert len(idx._deleted) == 0
        assert idx.count == 7

    def test_compact_not_triggered_below_threshold(self):
        """Add 10, delete 1 (10%) → no compact → _deleted still has 1."""
        idx = VectorIndex(dimension=DIM)
        for i in range(10):
            idx.add(f"a{i}", _random_vec())
        idx.remove("a0")

        assert not idx.needs_compact
        result = idx.compact_if_needed()
        assert result is False
        assert len(idx._deleted) == 1

    def test_search_consistent_after_compact(self):
        """Search results for surviving vectors identical before/after compact."""
        idx = VectorIndex(dimension=DIM)
        vecs = {}
        for i in range(10):
            v = _random_vec()
            idx.add(f"a{i}", v)
            vecs[f"a{i}"] = v

        # Delete first 3
        for i in range(3):
            idx.remove(f"a{i}")

        # Search before compact (only surviving vecs)
        q = vecs["a5"]
        before = idx.search(q, top_k=10, threshold=0.0)

        idx.compact_if_needed()

        after = idx.search(q, top_k=10, threshold=0.0)

        assert set(before.keys()) == set(after.keys())
        for uid in before:
            assert abs(before[uid] - after[uid]) < 1e-5

    def test_compact_logs_message(self, caplog):
        """Verify 'compact triggered' appears in logs."""
        import logging
        with caplog.at_level(logging.INFO):
            idx = VectorIndex(dimension=DIM)
            for i in range(10):
                idx.add(f"a{i}", _random_vec())
            for i in range(3):
                idx.remove(f"a{i}")
            idx.compact_if_needed()

        assert any("compact triggered" in r.message.lower() for r in caplog.records)

    def test_compact_via_save(self, tmp_dir):
        """save() triggers compact automatically when threshold met."""
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        for i in range(10):
            idx.add(f"a{i}", _random_vec())
        for i in range(3):
            idx.remove(f"a{i}")

        assert idx.needs_compact
        idx.save()
        assert len(idx._deleted) == 0
        assert idx.count == 7

    def test_compact_numpy_fallback(self):
        """compact works with NumPy backend too."""
        idx = VectorIndex(dimension=DIM)
        idx._use_faiss = False
        idx._faiss_index = None

        vecs = {}
        for i in range(10):
            v = _random_vec()
            idx.add(f"a{i}", v)
            vecs[f"a{i}"] = v
        for i in range(3):
            idx.remove(f"a{i}")

        q = vecs["a7"]
        before = idx.search(q, top_k=10, threshold=0.0)

        idx.compact_if_needed()
        assert len(idx._deleted) == 0
        assert idx.count == 7

        after = idx.search(q, top_k=10, threshold=0.0)
        assert set(before.keys()) == set(after.keys())
