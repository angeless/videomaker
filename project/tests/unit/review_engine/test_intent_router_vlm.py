"""Tests for IntentRouter multimodal upgrade (v0.17.0 R9)."""

import json
from unittest.mock import MagicMock

import pytest

from modules.review_engine.intent_router import route_comment


def _mock_llm(expected_response):
    """Create a mock LLM caller that returns a fixed response."""
    def caller(system_prompt, user_prompt):
        return expected_response
    return caller


class TestBackwardCompat:
    def test_no_visual_context_works(self):
        """Existing behavior without visual_context should be unchanged."""
        llm = _mock_llm('[{"type": "remove", "segment_idx": 3}]')
        result = route_comment("这段删掉", segment_idx=3, llm_caller=llm)
        assert len(result) == 1
        assert result[0].instruction_type == "remove"

    def test_keyword_fallback_no_visual_context(self):
        """Keyword fallback without visual_context works."""
        result = route_comment("这段删掉", segment_idx=2)
        assert len(result) >= 1
        assert result[0].instruction_type == "remove"


class TestVisualContextInjection:
    def test_logo_resize_with_visual_context(self):
        """Visual context about logo should influence resize instruction."""
        visual_ctx = {
            "summary": "画面右下角有一个品牌logo",
            "objects": ["logo"],
            "scene_type": "graphic",
            "visual_issues": [],
        }
        captured_prompts = []

        def llm_capture(system_prompt, user_prompt):
            captured_prompts.append(user_prompt)
            return '[{"type": "trim", "segment_idx": 1}]'

        route_comment(
            "这个太大了",
            segment_idx=1,
            llm_caller=llm_capture,
            visual_context=visual_ctx,
        )
        # Verify visual context was injected into prompt (wrapped in
        # <visual_context>…</visual_context> tags — Round-15 prompt-injection
        # hardening: the LLM is instructed to treat tag contents as data,
        # never as instructions).
        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "logo" in prompt
        assert "<visual_context>" in prompt
        assert "</visual_context>" in prompt

    def test_broll_with_scene_context(self):
        visual_ctx = {
            "summary": "户外天空场景",
            "objects": ["sky", "clouds"],
            "scene_type": "outdoor",
            "visual_issues": [],
        }
        captured = []

        def llm_capture(system, user):
            captured.append(user)
            return '[{"type": "broll", "query": "天空替换素材"}]'

        route_comment(
            "换个背景",
            segment_idx=0,
            llm_caller=llm_capture,
            visual_context=visual_ctx,
        )
        assert "outdoor" in captured[0] or "sky" in captured[0]

    def test_no_context_fallback(self):
        """visual_context=None should not inject anything."""
        captured = []

        def llm_capture(system, user):
            captured.append(user)
            return '[{"type": "remove"}]'

        route_comment(
            "删掉",
            segment_idx=0,
            llm_caller=llm_capture,
            visual_context=None,
        )
        # The Round-15 safety preamble mentions <visual_context> once
        # (explaining the rule). An actual injection would emit a
        # closing </visual_context> too — its absence confirms no
        # visual context was injected.
        assert "</visual_context>" not in captured[0]
