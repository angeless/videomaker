"""Feature gate for subscription tiers.

Controls which capabilities are available based on the user's plan.
Currently local-only (no server-side validation); tier is stored in
the app settings JSON.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Set

_log = logging.getLogger(__name__)


class Tier(str, Enum):
    FREE = "free"
    PRO = "pro"


# Features available per tier.  PRO includes all FREE features.
_FREE_FEATURES: Set[str] = {
    "library_browse",
    "library_search_keyword",
    "library_ingest_local",
    "workflow_basic",       # 7-step workflow
    "timeline_view",
    "timeline_reorder",
    "render_basic",         # 720p render
    "export_mp4",
}

_PRO_ONLY_FEATURES: Set[str] = {
    "library_search_vector",
    "library_search_visual",
    "library_search_fusion",
    "prompt_editing",
    "render_hd",            # 1080p+ render
    "render_4k",
    "ai_script_generation",
    "ai_semantic_analysis",
    "clip_speed_adjust",
    "social_export_multi",  # export to multiple platforms
    "gdrive_sync",
}


class FeatureGate:
    """Check feature access based on the current subscription tier.

    The tier is read from ``settings.json`` at ``subscription.tier``
    and defaults to ``Tier.FREE``.  When ``override_tier`` is set,
    it takes precedence (useful for testing and CLI).
    """

    def __init__(self, settings_path: Optional[Path] = None, override_tier: Optional[Tier] = None):
        self._settings_path = settings_path
        self._override = override_tier
        self._tier: Optional[Tier] = override_tier

    @property
    def tier(self) -> Tier:
        if self._override is not None:
            return self._override
        if self._tier is not None:
            return self._tier
        self._tier = self._load_tier()
        return self._tier

    def is_allowed(self, feature: str) -> bool:
        """Return True if *feature* is available on the current tier."""
        if self.tier == Tier.PRO:
            return feature in _FREE_FEATURES or feature in _PRO_ONLY_FEATURES
        return feature in _FREE_FEATURES

    def gate(self, feature: str) -> Dict[str, Any]:
        """Return gate status dict suitable for API responses."""
        allowed = self.is_allowed(feature)
        return {
            "feature": feature,
            "allowed": allowed,
            "tier": self.tier.value,
            "upgrade_required": not allowed,
        }

    def all_features(self) -> Dict[str, bool]:
        """Return dict of all features with their access status."""
        all_f = _FREE_FEATURES | _PRO_ONLY_FEATURES
        return {f: self.is_allowed(f) for f in sorted(all_f)}

    def set_tier(self, tier: Tier) -> None:
        """Update tier (persists to settings if path is set)."""
        self._tier = tier
        self._override = None
        if self._settings_path:
            self._save_tier(tier)

    # ── persistence ──

    def _load_tier(self) -> Tier:
        if not self._settings_path or not self._settings_path.exists():
            return Tier.FREE
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            raw = str(data.get("subscription", {}).get("tier", "free") or "free").lower()
            return Tier(raw) if raw in ("free", "pro") else Tier.FREE
        except Exception:
            return Tier.FREE

    def _save_tier(self, tier: Tier) -> None:
        if not self._settings_path:
            return
        try:
            data = {}
            if self._settings_path.exists():
                data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            if not isinstance(data.get("subscription"), dict):
                data["subscription"] = {}
            data["subscription"]["tier"] = tier.value
            self._settings_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            _log.warning("Failed to save tier to settings", exc_info=True)
