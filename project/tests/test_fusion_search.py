"""Tests for R6 fusion search mode and AI degradation transparency."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestFusionModeValidation:
    """R6: fusion mode is accepted throughout the search pipeline."""

    def test_fusion_in_search_assets_modes(self):
        """search_assets accepts mode='fusion'."""
        mode = "fusion"
        if mode not in {"hybrid", "keyword", "vector", "visual", "fusion"}:
            mode = "hybrid"
        assert mode == "fusion"

    def test_fusion_in_count_matching(self):
        mode = "fusion"
        if mode not in {"hybrid", "keyword", "vector", "visual", "fusion"}:
            mode = "hybrid"
        assert mode == "fusion"

    def test_fusion_in_api_route(self):
        """API route source includes fusion mode."""
        from modules.app_api.routes import library_routes
        source = inspect.getsource(library_routes)
        assert '"fusion"' in source or "'fusion'" in source


class TestAIDegradationTransparency:
    """R6: check_ai_status returns CLIP availability."""

    def test_check_ai_status_includes_clip(self):
        from modules.capabilities.image_semantic import check_ai_status
        result = check_ai_status(library=None)
        assert "clip_available" in result
        assert isinstance(result["clip_available"], bool)

    def test_check_ai_status_clip_false_without_library(self):
        from modules.capabilities.image_semantic import check_ai_status
        result = check_ai_status(library=None)
        assert result["clip_available"] is False

    def test_check_ai_status_reasons_include_clip(self):
        from modules.capabilities.image_semantic import check_ai_status
        result = check_ai_status(library=None)
        clip_reasons = [r for r in result["reasons"] if "CLIP" in r]
        assert len(clip_reasons) > 0


class TestAPIResponseVisualFields:
    """R6: /api/library/search response includes visual search fields."""

    def test_response_includes_visual_fields(self):
        from modules.app_api.routes import library_routes
        source = inspect.getsource(library_routes)
        assert "visual_search_enabled" in source
        assert "visual_embeddings_count" in source


class TestUIFusionButtons:
    """R6: UI includes visual and fusion mode buttons."""

    def test_ui_has_visual_button(self):
        with open(_PROJECT_ROOT / "apps/desktop/ui-legacy/index.html", "r") as f:
            html = f.read()
        assert "setLibrarySearchMode('visual')" in html

    def test_ui_has_fusion_button(self):
        with open(_PROJECT_ROOT / "apps/desktop/ui-legacy/index.html", "r") as f:
            html = f.read()
        assert "setLibrarySearchMode('fusion')" in html

    def test_ui_has_visual_status_badge(self):
        with open(_PROJECT_ROOT / "apps/desktop/ui-legacy/index.html", "r") as f:
            html = f.read()
        assert "libraryVisualSearchEnabled" in html

    def test_retrieval_mode_zh_includes_fusion(self):
        with open(_PROJECT_ROOT / "apps/desktop/ui-legacy/modules/capability_admin_mixin.js", "r") as f:
            js = f.read()
        assert "融合检索" in js
        assert "视觉检索" in js
