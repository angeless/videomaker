"""VideoStreamAnalyzer — cross-frame temporal analysis (B2).

Delegates brightness/color-temp checks to FrameDiagnostics.check_continuity().
Adds transition quality and narrative arc analysis (VLM-enhanced when available).
"""

import logging
from typing import Any, Dict, List, Optional

from modules.review_engine.contracts import (
    SampledFrame,
    StreamAnalysis,
    StreamIssue,
)
from modules.review_engine.frame_diagnostics import FrameDiagnostics, ContinuityIssue

logger = logging.getLogger(__name__)

# Per-frame VLM timeout
VLM_FRAME_TIMEOUT_S = 10


class VideoStreamAnalyzer:
    """Analyze temporal relationships between sampled frames."""

    def __init__(self, vlm_adapter: Optional[Any] = None):
        self._vlm = vlm_adapter
        self._diag = FrameDiagnostics(vlm_adapter=None)  # continuity doesn't need VLM

    def analyze(self, frames: List[SampledFrame]) -> StreamAnalysis:
        """Run full temporal analysis on sampled frames.

        Args:
            frames: List of SampledFrame from FrameSampler.

        Returns:
            StreamAnalysis with issues, narrative arc, and scene descriptions.
        """
        if not frames:
            return StreamAnalysis()

        issues: List[StreamIssue] = []

        # 1. Delegate brightness/color-temp to check_continuity (audit X6)
        continuity_issues = self._check_continuity(frames)
        issues.extend(continuity_issues)

        # 2. Scene transition quality (VLM-enhanced)
        transition_issues = self._check_transitions(frames)
        issues.extend(transition_issues)

        # 3. Narrative arc (VLM-only)
        narrative_arc = self._analyze_narrative(frames)

        # 4. Per-scene descriptions (VLM-only)
        scene_descriptions = self._describe_scenes(frames)

        return StreamAnalysis(
            issues=issues,
            narrative_arc=narrative_arc,
            scene_descriptions=scene_descriptions,
        )

    # ── Delegated continuity check ───────────────────────────────

    def _check_continuity(self, frames: List[SampledFrame]) -> List[StreamIssue]:
        """Delegate to FrameDiagnostics.check_continuity() — one representative frame per scene."""
        # Collapse to one frame per scene to avoid redundant cross-frame comparisons
        seen_scenes: set = set()
        per_scene: List[SampledFrame] = []
        for f in frames:
            if f.scene_idx not in seen_scenes:
                seen_scenes.add(f.scene_idx)
                per_scene.append(f)

        pil_frames = [f.frame for f in per_scene]
        scene_indices = [f.scene_idx for f in per_scene]

        raw_issues = self._diag.check_continuity(pil_frames, scene_indices)

        # Map ContinuityIssue → StreamIssue
        return [
            StreamIssue(
                issue_type=ci.issue_type,
                severity="warning",
                description=ci.description,
                frame_indices=[ci.scene_a_idx, ci.scene_b_idx],
            )
            for ci in raw_issues
        ]

    # ── Transition quality ───────────────────────────────────────

    def _check_transitions(self, frames: List[SampledFrame]) -> List[StreamIssue]:
        """Check transition quality between scenes.

        Without VLM: skip (continuity already covers algorithmic checks).
        With VLM: ask for transition quality assessment.
        """
        if self._vlm is None or len(frames) < 2:
            return []

        issues = []
        for i in range(len(frames) - 1):
            if frames[i].scene_idx == frames[i + 1].scene_idx:
                continue  # same scene, no transition

            try:
                prompt = (
                    "Rate the visual transition between these two frames on a scale of 1-5. "
                    "Consider smoothness, color consistency, and visual flow. "
                    "Reply with just the number."
                )
                # Pass both boundary frames to VLM for transition assessment
                result = self._vlm.describe_region(
                    frame=frames[i].frame,
                    next_frame=frames[i + 1].frame,
                    strokes=[],
                    prompt=prompt,
                )
                if result and isinstance(result, dict):
                    desc = result.get("description", "")
                    try:
                        score = int(desc.strip()[0]) if desc.strip() else 3
                    except (ValueError, IndexError):
                        score = 3
                    if score <= 2:
                        issues.append(StreamIssue(
                            issue_type="transition_quality",
                            severity="warning",
                            description=f"Poor transition quality (score={score}/5) at scenes {frames[i].scene_idx}→{frames[i+1].scene_idx}",
                            frame_indices=[i, i + 1],
                        ))
            except Exception as exc:
                logger.debug("Transition quality check failed: %s", exc)

        return issues

    # ── Narrative arc ────────────────────────────────────────────

    def _analyze_narrative(self, frames: List[SampledFrame]) -> str:
        """Generate narrative arc description. VLM required."""
        if self._vlm is None:
            return "VLM 不可用，无法生成叙事弧线分析"

        try:
            # Collect scene descriptions first
            scene_descs = []
            seen_scenes = set()
            for f in frames:
                if f.scene_idx not in seen_scenes:
                    seen_scenes.add(f.scene_idx)
                    result = self._vlm.describe_region(
                        frame=f.frame,
                        strokes=[],
                        prompt="Describe this video frame in one sentence. Focus on the main subject and action.",
                    )
                    if result and isinstance(result, dict):
                        scene_descs.append(
                            f"Scene {f.scene_idx}: {result.get('description', 'unknown')}"
                        )

            if scene_descs:
                return "叙事弧线: " + " → ".join(scene_descs)
            return "无法提取叙事弧线"
        except Exception as exc:
            logger.warning("Narrative arc analysis failed: %s", exc)
            return f"叙事弧线分析失败: {exc}"

    # ── Scene descriptions ───────────────────────────────────────

    def _describe_scenes(self, frames: List[SampledFrame]) -> Dict[int, str]:
        """Generate per-scene description. VLM enhanced."""
        descriptions: Dict[int, str] = {}

        if self._vlm is None:
            # Fallback: just list frames per scene
            for f in frames:
                if f.scene_idx not in descriptions:
                    descriptions[f.scene_idx] = f"Scene {f.scene_idx} at {f.timestamp_ms}ms"
            return descriptions

        seen = set()
        for f in frames:
            if f.scene_idx in seen:
                continue
            seen.add(f.scene_idx)
            try:
                result = self._vlm.describe_region(
                    frame=f.frame,
                    strokes=[],
                    prompt="Describe the scene in this frame briefly.",
                )
                if result and isinstance(result, dict):
                    descriptions[f.scene_idx] = result.get("description", "")
                else:
                    descriptions[f.scene_idx] = f"Scene {f.scene_idx}"
            except Exception as exc:
                descriptions[f.scene_idx] = f"Scene {f.scene_idx} (VLM error)"
                logger.debug("Scene description failed for %d: %s", f.scene_idx, exc)

        return descriptions
