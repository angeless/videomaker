"""E2E flow test — Search & Browse user journey.

Exercises the complete search path through the API layer:
  stats → browse (empty query) → keyword search → media filter → pagination
"""

import json


class TestE2ESearchFlow:
    """Full search lifecycle via /api/library/* endpoints."""

    def test_stats_reflect_seeded_data(self, e2e_client):
        """GET /stats returns correct counts for seeded 3 assets."""
        resp = e2e_client.get("/api/library/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_assets"] == 3
        assert data["video_assets"] == 2
        assert data["image_assets"] == 1

    def test_browse_all_assets(self, e2e_client):
        """Empty query browse mode returns all 3 assets."""
        resp = e2e_client.get("/api/library/search?q=")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 3
        assert data["retrieval_mode"] == "browse"
        assert data["has_more"] is False

    def test_keyword_search(self, e2e_client):
        """Keyword search for 'clip' returns 2 video assets."""
        resp = e2e_client.get("/api/library/search?q=clip&mode=keyword")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2
        fnames = {r["filename"] for r in data["results"]}
        assert "clip_a.mp4" in fnames
        assert "clip_b.mp4" in fnames

    def test_media_type_filter_video(self, e2e_client):
        """Filter by media_type=video returns only videos."""
        resp = e2e_client.get("/api/library/search?q=&media_type=video")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2
        for r in data["results"]:
            assert r["filename"].endswith(".mp4")

    def test_media_type_filter_image(self, e2e_client):
        """Filter by media_type=image returns only images."""
        resp = e2e_client.get("/api/library/search?q=&media_type=image")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["results"][0]["filename"] == "photo_c.jpg"

    def test_pagination(self, e2e_client):
        """Pagination: limit=1 returns 1 result with has_more=True."""
        resp = e2e_client.get("/api/library/search?q=&limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["has_more"] is True
        assert data["total_matches"] == 3

        # Page 2
        resp2 = e2e_client.get("/api/library/search?q=&limit=1&offset=1")
        data2 = resp2.get_json()
        assert data2["count"] == 1
        assert data2["has_more"] is True

        # Page 3 (last)
        resp3 = e2e_client.get("/api/library/search?q=&limit=1&offset=2")
        data3 = resp3.get_json()
        assert data3["count"] == 1
        assert data3["has_more"] is False
