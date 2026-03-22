"""Tests for modules.library.vision (CLIPEncoder + VisionMixin)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
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
# CLIPEncoder availability
# ------------------------------------------------------------------


class TestCLIPEncoderAvailability:
    def test_is_available_returns_bool(self):
        result = CLIPEncoder.is_available()
        assert isinstance(result, bool)

    def test_encode_text_returns_none_when_unavailable(self):
        encoder = CLIPEncoder()
        if not CLIPEncoder.is_available():
            assert encoder.encode_text("hello") is None

    def test_encode_image_returns_none_when_unavailable(self):
        encoder = CLIPEncoder()
        if not CLIPEncoder.is_available():
            assert encoder.encode_image(np.zeros((100, 100, 3), dtype=np.uint8)) is None


# ------------------------------------------------------------------
# VisionMixin with mock CLIP
# ------------------------------------------------------------------


class MockLibrary(VisionMixin):
    """Minimal host class for testing VisionMixin."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._visual_index = VectorIndex(dimension=DIM)
        self._clip_encoder = MagicMock(spec=CLIPEncoder)
        self._clip_encoder.is_available = MagicMock(return_value=True)
        self._clip_encoder.encode_image = MagicMock(side_effect=lambda img: _random_vec())
        self._clip_encoder.encode_text = MagicMock(side_effect=lambda text: _random_vec())
        self._visual_index_loaded = False

        # Set up SQLite
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
        return "2026-03-22T00:00:00"


@pytest.fixture
def mock_lib(tmp_path):
    db = tmp_path / "test.db"
    return MockLibrary(db)


class TestVisionMixinIndex:
    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
                  return_value=["fake_frame_1", "fake_frame_2", "fake_frame_3"])
    def test_index_asset_visual_adds_to_index(self, mock_kf, mock_lib):
        count = mock_lib.index_asset_visual("asset1", "/fake/video.mp4")
        assert count == NUM_KEYFRAMES
        assert mock_lib._visual_index.count == NUM_KEYFRAMES

    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
                  return_value=["fake_frame_1", "fake_frame_2", "fake_frame_3"])
    def test_index_stores_in_db(self, mock_kf, mock_lib):
        mock_lib.index_asset_visual("asset1", "/fake/video.mp4")
        conn = mock_lib._connect()
        rows = conn.execute("SELECT * FROM asset_visual_embeddings").fetchall()
        conn.close()
        assert len(rows) == NUM_KEYFRAMES
        assert rows[0]["uid"] == "asset1"

    def test_index_no_clip_returns_zero(self, mock_lib):
        mock_lib._clip_encoder = None
        count = mock_lib.index_asset_visual("asset1", "/fake/video.mp4")
        assert count == 0


class TestVisionMixinSearch:
    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
                  return_value=["fake_frame_1", "fake_frame_2", "fake_frame_3"])
    def test_visual_search_returns_matches(self, mock_kf, mock_lib):
        mock_lib.index_asset_visual("a1", "/fake/v1.mp4")
        mock_lib.index_asset_visual("a2", "/fake/v2.mp4")
        results = mock_lib.visual_search("sunset beach", top_k=10, threshold=0.0)
        assert isinstance(results, dict)
        assert len(results) <= 2

    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
                  return_value=["fake_frame_1", "fake_frame_2", "fake_frame_3"])
    def test_visual_search_aggregates_frames(self, mock_kf, mock_lib):
        """Multiple frames of same asset → single entry with max score."""
        fixed_vec = _random_vec()
        mock_lib._clip_encoder.encode_image = MagicMock(return_value=fixed_vec)
        mock_lib._clip_encoder.encode_text = MagicMock(return_value=fixed_vec)

        mock_lib.index_asset_visual("a1", "/fake/v1.mp4")
        results = mock_lib.visual_search("query", top_k=10, threshold=0.0)
        assert "a1" in results

    def test_visual_search_no_clip_returns_empty(self, mock_lib):
        mock_lib._clip_encoder = None
        results = mock_lib.visual_search("query")
        assert results == {}

    def test_visual_search_empty_query_returns_empty(self, mock_lib):
        mock_lib.index_asset_visual("a1", "/fake/v1.mp4")
        results = mock_lib.visual_search("", top_k=10)
        assert results == {}


class TestVisionMixinRefresh:
    @patch("modules.library.vision.vision_mixin.CLIPEncoder.extract_keyframes",
                  return_value=["fake_frame_1", "fake_frame_2", "fake_frame_3"])
    def test_refresh_loads_from_db(self, mock_kf, mock_lib):
        """After indexing, a fresh MockLibrary should load from DB."""
        mock_lib.index_asset_visual("a1", "/fake/v1.mp4")

        lib2 = MockLibrary(mock_lib.db_path)
        lib2._visual_index_loaded = False
        lib2._refresh_visual_index()
        assert lib2._visual_index.count == NUM_KEYFRAMES
