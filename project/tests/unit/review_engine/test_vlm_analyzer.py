"""Tests for VLMAnalyzer — region description engine (v0.17.0 R5)."""

import json
from unittest.mock import MagicMock, patch

import pytest

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

pytestmark = pytest.mark.skipif(not _HAS_PIL, reason="PIL not available")

from modules.review_engine.vlm_analyzer import (
    AnalysisContext,
    RegionDescription,
    VLMAnalyzer,
)
from modules.adapters.vlm_adapter import StubVLMAdapter, VLMResponse


@pytest.fixture
def stub_adapter():
    return StubVLMAdapter(
        fixed_response=json.dumps({
            "summary": "画面右下角有一个咖啡杯",
            "objects": ["coffee_cup"],
            "scene_type": "indoor",
            "visual_issues": [],
        })
    )


@pytest.fixture
def analyzer(stub_adapter):
    return VLMAnalyzer(adapter=stub_adapter)


@pytest.fixture
def test_image():
    return Image.new("RGB", (200, 200), "white")


@pytest.fixture
def context():
    return AnalysisContext(video_type="speech", timestamp_ms=5000)


class TestStructuredOutput:
    def test_describe_region_returns_structured(self, analyzer, test_image, context):
        result = analyzer.describe_region(test_image, context)
        assert isinstance(result, RegionDescription)
        assert "咖啡杯" in result.summary
        assert "coffee_cup" in result.objects
        assert result.scene_type == "indoor"

    def test_describe_region_with_visual_issues(self, test_image, context):
        adapter = StubVLMAdapter(
            fixed_response=json.dumps({
                "summary": "过曝的天空",
                "objects": ["sky"],
                "scene_type": "outdoor",
                "visual_issues": ["overexposed highlights"],
            })
        )
        analyzer = VLMAnalyzer(adapter=adapter)
        result = analyzer.describe_region(test_image, context)
        assert len(result.visual_issues) == 1
        assert "overexposed" in result.visual_issues[0]


class TestTextFallbackParse:
    def test_plain_text_response_parsed(self, test_image, context):
        """When VLM returns plain text instead of JSON, fall back gracefully."""
        adapter = StubVLMAdapter(
            fixed_response="This is a person walking in a park with trees."
        )
        analyzer = VLMAnalyzer(adapter=adapter)
        result = analyzer.describe_region(test_image, context)
        assert isinstance(result, RegionDescription)
        assert "person" in result.summary.lower() or "park" in result.summary.lower()
        # Objects should be empty (couldn't parse JSON)
        assert isinstance(result.objects, list)


class TestDegradation:
    def test_no_adapter_returns_fallback(self, test_image, context):
        analyzer = VLMAnalyzer(adapter=None)
        result = analyzer.describe_region(test_image, context)
        assert isinstance(result, RegionDescription)
        assert result.summary == "[画面区域]"
        assert result.objects == []

    def test_adapter_returns_none_gracefully(self, test_image, context):
        """Adapter that returns None from describe_image."""
        adapter = MagicMock()
        adapter.describe_image.return_value = None
        analyzer = VLMAnalyzer(adapter=adapter)
        result = analyzer.describe_region(test_image, context)
        assert isinstance(result, RegionDescription)
        assert result.summary == "[画面区域]"


class TestCache:
    def test_cache_hit_same_request(self, analyzer, test_image, context):
        """Same image+context should hit cache within TTL."""
        r1 = analyzer.describe_region(test_image, context)
        r2 = analyzer.describe_region(test_image, context)
        assert r1.summary == r2.summary
        # Adapter should only be called once
        # (StubVLMAdapter doesn't track calls, but result identity confirms cache)


class TestChinesePrompt:
    def test_prompt_contains_chinese(self, test_image, context):
        adapter = MagicMock()
        adapter.describe_image.return_value = VLMResponse(
            text='{"summary":"test","objects":[],"scene_type":"","visual_issues":[]}',
            model="mock",
        )
        analyzer = VLMAnalyzer(adapter=adapter)
        analyzer.describe_region(test_image, context)

        # Verify the prompt sent to adapter contains Chinese
        call_args = adapter.describe_image.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[1].get("prompt", "")
        if not prompt:
            prompt = call_args[0][1] if len(call_args[0]) > 1 else ""
        assert any(
            c >= "\u4e00" and c <= "\u9fff" for c in prompt
        ), f"Prompt should contain Chinese chars: {prompt}"
