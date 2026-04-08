"""SceneSummarizer — scene-level description aggregation (B3).

Aggregates multi-frame descriptions into per-scene summaries.
Uses VLM for polished summaries when available; falls back to
first-frame description otherwise.
"""

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from modules.review_engine.contracts import (
    SampledFrame,
    SceneSummary,
    StreamAnalysis,
)

logger = logging.getLogger(__name__)

# Common stop words to exclude from key_objects extraction
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "in", "on", "at",
    "to", "of", "for", "with", "and", "or", "but", "this", "that",
    "it", "its", "from", "by", "as", "be", "has", "have", "had",
})


class SceneSummarizer:
    """Aggregate multi-frame descriptions into per-scene summaries."""

    def __init__(self, vlm_adapter: Optional[Any] = None):
        self._vlm = vlm_adapter

    def summarize(
        self,
        analysis: StreamAnalysis,
        frames: List[SampledFrame],
    ) -> Dict[int, SceneSummary]:
        """Produce a SceneSummary for each scene.

        Args:
            analysis: StreamAnalysis from VideoStreamAnalyzer (contains scene_descriptions).
            frames: Original SampledFrame list (needed for duration and representative frame).

        Returns:
            Dict mapping scene_idx to SceneSummary.
        """
        if not frames:
            return {}

        # Group frames by scene
        scene_frames: Dict[int, List[SampledFrame]] = defaultdict(list)
        for f in frames:
            scene_frames[f.scene_idx].append(f)

        result: Dict[int, SceneSummary] = {}
        for scene_idx in sorted(scene_frames.keys()):
            sf_list = scene_frames[scene_idx]
            descriptions = self._gather_descriptions(scene_idx, sf_list, analysis)

            if not descriptions:
                continue  # empty scene → skip

            merged_objects = self._merge_objects(descriptions)
            representative_ms = self._pick_representative(sf_list, descriptions)
            duration_ms = self._compute_duration(sf_list)
            summary_text = self._generate_summary(descriptions, merged_objects)

            result[scene_idx] = SceneSummary(
                scene_idx=scene_idx,
                summary=summary_text,
                key_objects=merged_objects,
                duration_ms=duration_ms,
                representative_frame_ms=representative_ms,
            )

        return result

    # ── Description gathering ────────────────────────────────────

    def _gather_descriptions(
        self,
        scene_idx: int,
        sf_list: List[SampledFrame],
        analysis: StreamAnalysis,
    ) -> List[str]:
        """Collect descriptions for a scene. Uses existing + VLM for extra frames."""
        descriptions: List[str] = []

        # Use existing scene description from StreamAnalysis
        existing = analysis.scene_descriptions.get(scene_idx, "")
        if existing:
            descriptions.append(existing)

        # If VLM available and multiple frames, describe additional frames
        if self._vlm is not None and len(sf_list) > 1:
            for f in sf_list[1:]:  # skip first (already described)
                try:
                    result = self._vlm.describe_region(
                        frame=f.frame,
                        strokes=[],
                        prompt="Describe this video frame briefly. List the main objects.",
                    )
                    if result and isinstance(result, dict):
                        desc = result.get("description", "")
                        if desc and desc not in descriptions:
                            descriptions.append(desc)
                except Exception as exc:
                    logger.debug("VLM description failed for frame at %dms: %s",
                                 f.timestamp_ms, exc)

        return descriptions

    # ── Object extraction and merging ────────────────────────────

    @staticmethod
    def _extract_objects(description: str) -> List[str]:
        """Extract candidate object nouns from a description string."""
        words = re.findall(r"[a-zA-Z\u4e00-\u9fff]+", description.lower())
        return [w for w in words if w not in _STOP_WORDS and len(w) > 2]

    def _merge_objects(self, descriptions: List[str]) -> List[str]:
        """De-duplicate and merge key objects from multiple descriptions."""
        seen = set()
        objects: List[str] = []
        for desc in descriptions:
            for obj in self._extract_objects(desc):
                if obj not in seen:
                    seen.add(obj)
                    objects.append(obj)
        return objects

    # ── Representative frame selection ───────────────────────────

    def _pick_representative(
        self,
        sf_list: List[SampledFrame],
        descriptions: List[str],
    ) -> int:
        """Pick the frame whose description has the most objects."""
        if not descriptions:
            return sf_list[0].timestamp_ms if sf_list else 0

        best_idx = 0
        best_count = 0
        for i, desc in enumerate(descriptions):
            count = len(self._extract_objects(desc))
            if count > best_count:
                best_count = count
                best_idx = i

        # Map description index back to frame timestamp
        if best_idx < len(sf_list):
            return sf_list[best_idx].timestamp_ms
        return sf_list[0].timestamp_ms

    # ── Duration computation ─────────────────────────────────────

    @staticmethod
    def _compute_duration(sf_list: List[SampledFrame]) -> int:
        """Estimate scene duration from frame timestamps."""
        if len(sf_list) < 2:
            return 0
        timestamps = [f.timestamp_ms for f in sf_list]
        return max(timestamps) - min(timestamps)

    # ── Summary generation ───────────────────────────────────────

    def _generate_summary(
        self,
        descriptions: List[str],
        key_objects: List[str],
    ) -> str:
        """Generate a one-sentence scene summary.

        With VLM: Ask LLM to condense multiple descriptions.
        Without VLM: Use the first description as-is.
        """
        if not descriptions:
            return ""

        if self._vlm is not None and len(descriptions) > 1:
            try:
                combined = "; ".join(descriptions)
                result = self._vlm.describe_region(
                    frame=None,
                    strokes=[],
                    prompt=(
                        f"Summarize these frame descriptions into one concise sentence: {combined}"
                    ),
                )
                if result and isinstance(result, dict):
                    summary = result.get("description", "")
                    if summary:
                        return summary
            except Exception as exc:
                logger.debug("VLM summary generation failed: %s", exc)

        # Fallback: first description
        return descriptions[0]
