"""Tests for `_meta.provider` classification — L6 (Wave 1).

Per dev-plan-v0.19.0.md Feature L Task L6:
> `_meta.model_version` 反映真实 provider（`gpt-4o-mini` / `claude-sonnet-4-5` /
> `local_llava` / `heuristic_only`）

Wave 1 implementation: introduce a `_classify_provider()` helper that maps
`_model` strings to a stable provider classification. M1 (badge UI) reads
`_meta.provider` instead of regex-parsing `_model`.

Wave 2 (L2) will populate the actual claude/llava model_versions; this test
locks in the classification contract so Wave 2 only fills values, doesn't
break shape.
"""

from __future__ import annotations

import pytest

from modules.library.global_media_library import GlobalMediaLibrary


# ── L6-T1: classify heuristic_only ─────────────────────────────────────────


@pytest.mark.parametrize("model_version,expected", [
    # Heuristic
    ("heuristic_only", "heuristic"),
    ("heuristic", "heuristic"),
    # OpenAI variants
    ("gpt-4o-mini", "openai"),
    ("gpt-4o", "openai"),
    ("gpt-4-turbo", "openai"),
    ("openai/gpt-4o-mini", "openai"),
    # Anthropic / Claude variants
    ("claude-sonnet-4-5", "claude"),
    ("claude-3-5-sonnet-20241022", "claude"),
    ("anthropic/claude-3-haiku", "claude"),
    # LLaVA
    ("local_llava", "llava"),
    ("llava-v1.6-mistral-7b", "llava"),
    # Unknown / future
    ("unknown", "unknown"),
    ("", "unknown"),
    ("some-future-model", "unknown"),
])
def test_classify_provider(model_version, expected):
    result = GlobalMediaLibrary._classify_provider(model_version)
    assert result == expected, (
        f"_classify_provider({model_version!r}) returned {result!r}, "
        f"expected {expected!r}"
    )


# ── L6-T2: classification is case-insensitive on prefix ────────────────────


def test_classify_provider_case_insensitive():
    assert GlobalMediaLibrary._classify_provider("GPT-4O-MINI") == "openai"
    assert GlobalMediaLibrary._classify_provider("Claude-3-5-sonnet") == "claude"


# ── L6-T3: None / non-string handled gracefully ────────────────────────────


def test_classify_provider_handles_none():
    assert GlobalMediaLibrary._classify_provider(None) == "unknown"


def test_classify_provider_handles_non_string():
    # Defensive — should not raise on weird inputs
    assert GlobalMediaLibrary._classify_provider(123) == "unknown"
    assert GlobalMediaLibrary._classify_provider({}) == "unknown"
