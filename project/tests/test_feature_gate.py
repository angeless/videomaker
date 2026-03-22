"""Tests for R9 subscription feature gate."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from modules.subscription.feature_gate import FeatureGate, Tier


class TestFeatureGate:
    def test_default_tier_is_free(self):
        gate = FeatureGate()
        assert gate.tier == Tier.FREE

    def test_override_tier(self):
        gate = FeatureGate(override_tier=Tier.PRO)
        assert gate.tier == Tier.PRO

    def test_free_allows_basic_features(self):
        gate = FeatureGate(override_tier=Tier.FREE)
        assert gate.is_allowed("library_browse")
        assert gate.is_allowed("workflow_basic")
        assert gate.is_allowed("timeline_view")

    def test_free_blocks_pro_features(self):
        gate = FeatureGate(override_tier=Tier.FREE)
        assert not gate.is_allowed("library_search_vector")
        assert not gate.is_allowed("prompt_editing")
        assert not gate.is_allowed("render_4k")

    def test_pro_allows_all(self):
        gate = FeatureGate(override_tier=Tier.PRO)
        assert gate.is_allowed("library_browse")
        assert gate.is_allowed("library_search_vector")
        assert gate.is_allowed("prompt_editing")
        assert gate.is_allowed("render_4k")

    def test_gate_returns_dict(self):
        gate = FeatureGate(override_tier=Tier.FREE)
        result = gate.gate("prompt_editing")
        assert result["feature"] == "prompt_editing"
        assert result["allowed"] is False
        assert result["tier"] == "free"
        assert result["upgrade_required"] is True

    def test_all_features(self):
        gate = FeatureGate(override_tier=Tier.PRO)
        features = gate.all_features()
        assert isinstance(features, dict)
        assert all(v is True for v in features.values())

    def test_unknown_feature_blocked(self):
        gate = FeatureGate(override_tier=Tier.PRO)
        assert not gate.is_allowed("nonexistent_feature")


class TestTierPersistence:
    def test_save_and_load_tier(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text("{}", encoding="utf-8")

        gate = FeatureGate(settings_path=settings)
        gate.set_tier(Tier.PRO)

        # Reload
        gate2 = FeatureGate(settings_path=settings)
        assert gate2.tier == Tier.PRO

    def test_load_from_nonexistent_defaults_free(self, tmp_path):
        gate = FeatureGate(settings_path=tmp_path / "nope.json")
        assert gate.tier == Tier.FREE

    def test_load_from_corrupted_defaults_free(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text("not json", encoding="utf-8")
        gate = FeatureGate(settings_path=settings)
        assert gate.tier == Tier.FREE
