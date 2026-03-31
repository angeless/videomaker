"""Tests for _auto_visual_index — R3 (W-010) auto visual indexing on ingest."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from modules.library.semantic.vector_index import VectorIndex
from modules.library.vision.clip_encoder import CLIPEncoder
from modules.library.vision.vision_mixin import VisionMixin, NUM_KEYFRAMES


DIM = CLIPEncoder.DIMENSION  # 512


def _random_vec(dim: int = DIM) -> list:
    v = np.random.randn(dim).astype(np.float32)
    v = v / (np.linalg.norm(v) + 1e-8)
    return v.tolist()


# ------------------------------------------------------------------
# Minimal host class that has both VisionMixin + _auto_visual_index
# ------------------------------------------------------------------


class _StubLibrary(VisionMixin):
    """Provides just enough to test _auto_visual_index from CoreMixin."""

    def __init__(self, db_path: Path, clip_available: bool = True):
        self.db_path = db_path
        self._visual_index = VectorIndex(dimension=DIM)
        if clip_available:
            self._clip_encoder = MagicMock(spec=CLIPEncoder)
            self._clip_encoder.is_available = MagicMock(return_value=True)
            self._clip_encoder.encode_image = MagicMock(side_effect=lambda img: _random_vec())
            self._clip_encoder.encode_text = MagicMock(side_effect=lambda text: _random_vec())
        else:
            self._clip_encoder = None
        self._visual_index_loaded = False

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS asset_visual_embeddings (
                uid TEXT NOT NULL,
                frame_index INTEGER NOT NULL,
                model TEXT NOT NULL DEFAULT 'clip-vit-base-patch32',
                embedding_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (uid, frame_index)
            )
        """)
        conn.commit()
        conn.close()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now():
        return "2026-03-27T00:00:00"

    # Import the real methods from CoreMixin to test in isolation
    from modules.library.core.core_mixin import CoreMixin
    _auto_visual_index = CoreMixin._auto_visual_index
    _cancel_visual_index = CoreMixin._cancel_visual_index


@pytest.fixture
def stub_lib(tmp_path):
    """Library with CLIP available."""
    return _StubLibrary(tmp_path / "test.db", clip_available=True)


@pytest.fixture
def stub_lib_no_clip(tmp_path):
    """Library with CLIP unavailable."""
    return _StubLibrary(tmp_path / "test.db", clip_available=False)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestAutoVisualIndexTriggered:
    """_auto_visual_index returns True and indexes when CLIP is available."""

    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
           return_value=["frame1", "frame2", "frame3"])
    def test_returns_true_with_valid_assets(self, mock_kf, stub_lib, tmp_path):
        video = tmp_path / "sample.mp4"
        video.write_bytes(b"\x00" * 100)

        assets = [{"uid": "abc123", "path": str(video)}]
        result = stub_lib._auto_visual_index(assets)
        assert result is True

    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
           return_value=["frame1", "frame2", "frame3"])
    def test_indexes_in_background_thread(self, mock_kf, stub_lib, tmp_path):
        video = tmp_path / "sample.mp4"
        video.write_bytes(b"\x00" * 100)

        assets = [{"uid": "abc123", "path": str(video)}]
        stub_lib._auto_visual_index(assets)

        # Wait for background thread to finish
        time.sleep(1.0)

        assert stub_lib._visual_index.count == NUM_KEYFRAMES

    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
           return_value=["frame1", "frame2", "frame3"])
    def test_multiple_assets(self, mock_kf, stub_lib, tmp_path):
        videos = []
        assets = []
        for i in range(3):
            v = tmp_path / f"video_{i}.mp4"
            v.write_bytes(b"\x00" * 100)
            videos.append(v)
            assets.append({"uid": f"uid_{i}", "path": str(v)})

        result = stub_lib._auto_visual_index(assets)
        assert result is True

        time.sleep(2.0)
        assert stub_lib._visual_index.count == NUM_KEYFRAMES * 3

    def test_empty_assets_returns_false(self, stub_lib):
        assert stub_lib._auto_visual_index([]) is False

    def test_missing_file_skipped(self, stub_lib):
        assets = [{"uid": "abc123", "path": "/nonexistent/video.mp4"}]
        result = stub_lib._auto_visual_index(assets)
        assert result is False

    def test_accepts_primary_path_key(self, stub_lib, tmp_path):
        video = tmp_path / "sample.mp4"
        video.write_bytes(b"\x00" * 100)
        assets = [{"uid": "abc123", "primary_path": str(video)}]
        result = stub_lib._auto_visual_index(assets)
        assert result is True


class TestAutoVisualIndexDegraded:
    """_auto_visual_index returns False when CLIP unavailable, uses R2 notification."""

    def test_returns_false_no_clip(self, stub_lib_no_clip):
        assets = [{"uid": "abc123", "path": "/fake/video.mp4"}]
        result = stub_lib_no_clip._auto_visual_index(assets)
        assert result is False

    @patch("modules.workflow_engine.workflow._log_degradation")
    def test_logs_degradation_when_no_clip(self, mock_degrade, stub_lib_no_clip):
        assets = [{"uid": "abc123", "path": "/fake/video.mp4"}]
        stub_lib_no_clip._auto_visual_index(assets)
        mock_degrade.assert_called_once()
        args = mock_degrade.call_args[0]
        assert "auto_visual_index" in args[0]
        assert "CLIP" in args[1]


class TestAutoVisualIndexNonBlocking:
    """Verify indexing runs async and doesn't block the caller."""

    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
           return_value=["frame1", "frame2", "frame3"])
    def test_returns_immediately(self, mock_kf, stub_lib, tmp_path):
        video = tmp_path / "sample.mp4"
        video.write_bytes(b"\x00" * 100)

        # Make encoding slow to prove non-blocking
        def slow_encode(img):
            time.sleep(0.5)
            return _random_vec()

        stub_lib._clip_encoder.encode_image = MagicMock(side_effect=slow_encode)

        assets = [{"uid": f"uid_{i}", "path": str(video)} for i in range(5)]

        start = time.time()
        result = stub_lib._auto_visual_index(assets)
        elapsed = time.time() - start

        assert result is True
        # Should return almost immediately (thread spawned, not waited)
        assert elapsed < 0.5, f"_auto_visual_index blocked for {elapsed:.2f}s"
