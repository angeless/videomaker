"""Tests for StockMedia — R18."""

import pytest

from modules.review_engine.stock_media import (
    search_stock,
    download_stock,
    StockResult,
)
from modules.review_engine.exceptions import StockMediaError


class MockStockAdapter:
    def search(self, query, **kwargs):
        return {
            "videos": [
                {
                    "id": 123,
                    "duration": 15,
                    "user": {"name": "John"},
                    "video_files": [
                        {"link": "https://example.com/v.mp4", "width": 1920, "height": 1080},
                    ],
                    "video_pictures": [{"picture": "https://example.com/thumb.jpg"}],
                }
            ]
        }

    def download(self, video_url, output_path):
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            f.write("fake video")
        return output_path


class TestStockMedia:

    def test_search_returns_results(self):
        adapter = MockStockAdapter()
        results = search_stock("sunset beach", adapter=adapter)
        assert len(results) == 1
        assert results[0].id == "123"
        assert results[0].photographer == "John"
        assert results[0].duration == 15

    def test_no_key_raises(self):
        """PexelsAdapter without API key raises StockMediaError."""
        import os
        old = os.environ.pop("PEXELS_API_KEY", None)
        try:
            with pytest.raises(StockMediaError, match="API key"):
                from modules.review_engine.stock_media import PexelsAdapter
                PexelsAdapter()
        finally:
            if old is not None:
                os.environ["PEXELS_API_KEY"] = old

    def test_download(self, tmp_path):
        adapter = MockStockAdapter()
        path = download_stock(
            "https://example.com/v.mp4",
            str(tmp_path),
            filename="test.mp4",
            adapter=adapter,
        )
        assert path.endswith("test.mp4")
