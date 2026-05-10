"""Tests for L9 — _vision_enrich_tags routes through vlm_adapter dispatcher.

Per dev-plan-v0.19.0.md Feature L Task L9:
> `_vision_enrich_tags` (line 352, 用于图片素材) 走 vlm_adapter
> 测试：仅 Anthropic key 时图片素材入库 `method=image_vision_enrich` 而非 `image_heuristic`

L9 mirrors L1+L2 for the image-only ingestion path (`_vision_enrich_tags`
is invoked when ingesting standalone images). Same env var gate fix +
provider-routing dispatch.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from modules.library.global_media_library import GlobalMediaLibrary


@pytest.fixture
def library(tmp_path: Path) -> GlobalMediaLibrary:
    return GlobalMediaLibrary(db_path=tmp_path / "library.db")


# ── L9-T1: enabled with only OpenAI key ────────────────────────────────────


def test_vision_enrich_enabled_with_only_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_VISION_ENRICH", raising=False)
    assert GlobalMediaLibrary._vision_enrich_enabled() is True


# ── L9-T2: enabled with only Anthropic key (NEW behavior) ─────────────────


def test_vision_enrich_enabled_with_only_anthropic(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_VISION_ENRICH", raising=False)
    # BEFORE L9: returned False (only checked OPENAI_API_KEY).
    # AFTER L9: must return True.
    assert GlobalMediaLibrary._vision_enrich_enabled() is True


# ── L9-T3: disabled when neither key ──────────────────────────────────────


def test_vision_enrich_enabled_with_no_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_DISABLE_VISION_ENRICH", raising=False)
    assert GlobalMediaLibrary._vision_enrich_enabled() is False


# ── L9-T4: kill-switch overrides any key ──────────────────────────────────


def test_vision_enrich_disabled_via_killswitch(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VIDEOEDITOR_DISABLE_VISION_ENRICH", "1")
    assert GlobalMediaLibrary._vision_enrich_enabled() is False


# ── L9-T5: returns {} when not enabled ────────────────────────────────────


def test_vision_enrich_tags_no_key_returns_empty(library, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_image = tmp_path / "test.jpg"
    fake_image.write_bytes(b"fake")
    assert library._vision_enrich_tags(fake_image) == {}


# ── L9-T6: routes through dispatcher (verifies Anthropic-only path works) ─


def test_vision_enrich_tags_uses_vlm_dispatcher(library, tmp_path, monkeypatch):
    """L9 wires _vision_enrich_tags to _call_vlm_json so Anthropic-only
    users get image enrichment, not just OpenAI users."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    fake_image = tmp_path / "test.jpg"
    fake_image.write_bytes(b"fake jpeg bytes")

    expected_result = {
        "scene": "urban street",
        "keywords": ["city", "night"],
        "landmarks": [],
        "architecture_style": [],
        "_model": "claude-sonnet-4-20250514",
    }

    with patch.object(library, "_extract_keyframe_data_url",
                      return_value="data:image/jpeg;base64,FAKE"), \
         patch.object(library, "_call_vlm_json", return_value=expected_result) as mock_call:
        result = library._vision_enrich_tags(fake_image)

    mock_call.assert_called_once()
    assert result.get("scene") == "urban street"
    assert "keywords" in result


# ── L9-T7: respects dispatcher's empty-result contract ────────────────────


def test_vision_enrich_tags_returns_empty_on_dispatcher_empty(library, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_image = tmp_path / "test.jpg"
    fake_image.write_bytes(b"fake")

    with patch.object(library, "_extract_keyframe_data_url",
                      return_value="data:image/jpeg;base64,FAKE"), \
         patch.object(library, "_call_vlm_json", return_value={}):
        result = library._vision_enrich_tags(fake_image)

    assert result == {}


# ── L9-T8: returns {} when no keyframe extracted ──────────────────────────


def test_vision_enrich_tags_no_keyframe(library, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_image = tmp_path / "test.jpg"
    fake_image.write_bytes(b"fake")

    with patch.object(library, "_extract_keyframe_data_url", return_value=""):
        result = library._vision_enrich_tags(fake_image)

    assert result == {}
