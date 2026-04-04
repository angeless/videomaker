"""Tests for reference resolution (v0.17.0 R10)."""

import pytest

from modules.review_engine.vlm_analyzer import RegionDescription, VLMAnalyzer


class TestSingleRef:
    def test_single_object_replacement(self):
        vc = RegionDescription(summary="logo", objects=["logo"])
        result = VLMAnalyzer.resolve_references("这个太大了", vc)
        assert "logo" in result
        assert "这个" not in result

    def test_different_ref_word(self):
        vc = RegionDescription(objects=["water_bottle"])
        result = VLMAnalyzer.resolve_references("把那个删了", vc)
        assert "water_bottle" in result


class TestMultiObject:
    def test_multi_objects_joined(self):
        vc = RegionDescription(objects=["water_bottle", "cup"])
        result = VLMAnalyzer.resolve_references("把这些删了", vc)
        assert "water_bottle" in result
        assert "cup" in result


class TestColorIssue:
    def test_color_issue_appended(self):
        vc = RegionDescription(visual_issues=["色温偏冷"])
        result = VLMAnalyzer.resolve_references("颜色不对", vc)
        assert "色温偏冷" in result

    def test_brightness_issue(self):
        vc = RegionDescription(visual_issues=["欠曝"])
        result = VLMAnalyzer.resolve_references("太暗了", vc)
        assert "欠曝" in result


class TestNoRefPassthrough:
    def test_no_ref_words_unchanged(self):
        vc = RegionDescription(objects=["logo"])
        text = "把音量调高"
        result = VLMAnalyzer.resolve_references(text, vc)
        assert result == text

    def test_none_context(self):
        result = VLMAnalyzer.resolve_references("这个太大了", None)
        assert result == "这个太大了"

    def test_empty_text(self):
        vc = RegionDescription(objects=["logo"])
        result = VLMAnalyzer.resolve_references("", vc)
        assert result == ""


class TestMultiRef:
    def test_ref_and_issue(self):
        vc = RegionDescription(
            objects=["person"],
            visual_issues=["欠曝"],
        )
        result = VLMAnalyzer.resolve_references("这个太暗了", vc)
        assert "person" in result
        assert "欠曝" in result
