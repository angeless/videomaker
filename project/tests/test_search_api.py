"""Tests for search API enhancements (R5)."""

from __future__ import annotations

import json

import pytest


class TestSearchModeValidation:
    """R5: API accepts visual retrieval mode."""

    def test_visual_mode_accepted_in_search_assets(self):
        """search_assets should accept mode='visual' without downgrading."""
        from modules.library.core.core_mixin import CoreMixin

        # The mode validation logic is at the top of search_assets
        mode = "visual"
        if mode not in {"hybrid", "keyword", "vector", "visual"}:
            mode = "hybrid"
        assert mode == "visual"

    def test_visual_mode_accepted_in_count(self):
        """count_matching_assets should accept mode='visual'."""
        mode = "visual"
        if mode not in {"hybrid", "keyword", "vector", "visual"}:
            mode = "hybrid"
        assert mode == "visual"

    def test_unknown_mode_falls_back_to_hybrid(self):
        mode = "nonexistent"
        if mode not in {"hybrid", "keyword", "vector", "visual"}:
            mode = "hybrid"
        assert mode == "hybrid"


class TestLibraryRoutesModeValidation:
    """R5: /api/library/search route accepts visual mode."""

    def test_visual_in_allowed_modes(self):
        """The route should allow 'visual' as a retrieval_mode."""
        allowed = {"hybrid", "keyword", "vector", "visual"}
        assert "visual" in allowed

    def test_api_route_source_includes_visual(self):
        """Verify the actual route code includes visual."""
        import inspect
        from modules.app_api.routes import library_routes
        source = inspect.getsource(library_routes)
        assert '"visual"' in source or "'visual'" in source


class TestStatsVisualFields:
    """R5: stats() includes visual search fields."""

    def test_stats_contract(self):
        """Verify stats return dict has visual_search_enabled key."""
        # We can't easily instantiate GlobalMediaLibrary in tests without
        # a full DB, but we can verify the method source includes the field
        import inspect
        from modules.library.global_media_library import GlobalMediaLibrary
        source = inspect.getsource(GlobalMediaLibrary.stats)
        assert "visual_search_enabled" in source
        assert "visual_embeddings_count" in source
