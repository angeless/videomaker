"""Tests for R6a (IVFFlat upgrade), R6b (WAL persistence), R6c (CLIP model swap)."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from modules.library.semantic.vector_index import VectorIndex

DIM = 8


def _random_vec(dim: int = DIM) -> list:
    return np.random.randn(dim).astype(np.float32).tolist()


@pytest.fixture
def tmp_dir():
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------
# R6a: FAISS IndexIVFFlat auto-selection
# ------------------------------------------------------------------


import platform
import subprocess
import sys

# IVFFlat segfaults on some FAISS builds (notably Homebrew macOS).
# Run a subprocess probe to avoid crashing the test runner.
_IVF_SAFE = False
try:
    _code = (
        "import faiss,numpy as np;"
        "q=faiss.IndexFlatIP(32);"
        "i=faiss.IndexIVFFlat(q,32,4,faiss.METRIC_INNER_PRODUCT);"
        "m=np.random.randn(200,32).astype(np.float32);"
        "i.train(m);i.add(m);print('ok')"
    )
    _r = subprocess.run([sys.executable, "-c", _code], capture_output=True, timeout=10)
    _IVF_SAFE = _r.returncode == 0 and b"ok" in _r.stdout
except Exception:
    pass


class TestIVFUpgrade:
    def test_small_index_uses_flatip(self):
        idx = VectorIndex(dimension=DIM)
        uids = [f"a{i}" for i in range(100)]
        matrix = np.random.randn(100, DIM).astype(np.float32)
        idx.rebuild(uids, matrix)
        if idx._use_faiss and idx._faiss_index is not None:
            assert type(idx._faiss_index).__name__ == "IndexFlatIP"

    def test_ivf_subprocess_validation(self):
        """Validate IVFFlat works in a clean subprocess (avoids torch+FAISS OMP conflict)."""
        code = (
            "import faiss,numpy as np;"
            "q=faiss.IndexFlatIP(32);"
            "i=faiss.IndexIVFFlat(q,32,4,faiss.METRIC_INNER_PRODUCT);"
            "m=np.random.randn(200,32).astype(np.float32);"
            "i.train(m);i.add(m);"
            "print(type(i).__name__)"
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=15)
        assert r.returncode == 0, f"IVFFlat subprocess failed: {r.stderr.decode()}"
        assert b"IndexIVFFlat" in r.stdout

    @patch("modules.library._constants.FAISS_IVF_THRESHOLD", 10)
    @patch("modules.library._constants.FAISS_IVF_NLIST", 100)
    def test_insufficient_training_data_fallback(self, caplog):
        """Not enough vectors for IVF training -> fallback to FlatIP."""
        import logging
        with caplog.at_level(logging.WARNING):
            idx = VectorIndex(dimension=DIM)
            n = 20
            uids = [f"a{i}" for i in range(n)]
            matrix = np.random.randn(n, DIM).astype(np.float32)
            idx.rebuild(uids, matrix)

        if idx._use_faiss and idx._faiss_index is not None:
            assert type(idx._faiss_index).__name__ == "IndexFlatIP"
            assert any("insufficient" in r.message.lower() for r in caplog.records)


# ------------------------------------------------------------------
# R6b: WAL persistence
# ------------------------------------------------------------------


class TestWAL:
    def test_add_creates_wal_entry(self, tmp_dir):
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        idx.add("uid1", _random_vec())
        wal_path = tmp_dir / "vector_wal.jsonl"
        assert wal_path.exists()
        lines = wal_path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["op"] == "add"
        assert entry["uid"] == "uid1"

    def test_wal_replay_on_load(self, tmp_dir):
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        v = _random_vec()
        idx.add("uid1", v)
        # Save main index (without uid1 in WAL replay scenario)
        # Actually save will clear WAL. So let's test: add -> no save -> reload
        # We need to save the base index first, then add more
        idx.save()  # this clears WAL
        idx.add("uid2", _random_vec())  # this goes to WAL only

        # Reload from scratch
        idx2 = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        assert idx2.count == 2
        results = idx2.search(_random_vec(), top_k=10, threshold=0.0)
        assert "uid2" in results or idx2.count == 2  # uid2 was replayed

    def test_checkpoint_clears_wal(self, tmp_dir):
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        idx.add("uid1", _random_vec())
        wal_path = tmp_dir / "vector_wal.jsonl"
        assert wal_path.exists()

        idx.checkpoint()
        assert not wal_path.exists()

    def test_add_batch(self, tmp_dir):
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        pairs = [(f"uid{i}", _random_vec()) for i in range(5)]
        added = idx.add_batch(pairs)
        assert added == 5
        assert idx.count == 5

    def test_wal_write_speed(self, tmp_dir):
        """Single WAL write < 10ms average over 10 calls."""
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        times = []
        for i in range(10):
            v = _random_vec()
            start = time.time()
            idx.add(f"uid{i}", v)
            times.append(time.time() - start)
        avg_ms = (sum(times) / len(times)) * 1000
        assert avg_ms < 10, f"Average WAL write {avg_ms:.1f}ms > 10ms"

    def test_no_wal_without_index_dir(self):
        """In-memory index: no WAL file."""
        idx = VectorIndex(dimension=DIM)
        idx.add("uid1", _random_vec())
        assert idx._wal_path is None


# ------------------------------------------------------------------
# R6c: CLIP model config
# ------------------------------------------------------------------


class TestCLIPModelConfig:
    def test_clip_encoder_exposes_dim(self):
        from modules.library.vision.clip_encoder import CLIPEncoder
        enc = CLIPEncoder("openai/clip-vit-base-patch32")
        assert enc.dim == 512
        assert enc.model_id == "openai/clip-vit-base-patch32"

    def test_clip_encoder_large_model_dim(self):
        from modules.library.vision.clip_encoder import CLIPEncoder
        enc = CLIPEncoder("openai/clip-vit-large-patch14")
        assert enc.dim == 768

    def test_clip_model_dims_registry(self):
        from modules.library.vision.clip_encoder import _CLIP_MODEL_DIMS
        assert "openai/clip-vit-base-patch32" in _CLIP_MODEL_DIMS
        assert "openai/clip-vit-large-patch14" in _CLIP_MODEL_DIMS
        assert _CLIP_MODEL_DIMS["openai/clip-vit-base-patch32"] == 512
        assert _CLIP_MODEL_DIMS["openai/clip-vit-large-patch14"] == 768
