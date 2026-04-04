"""FrameDiagnostics — AI-powered video frame quality analysis.

Checks composition, exposure, color temperature, and scene continuity.
Uses a mix of algorithmic analysis (histograms) and VLM assistance.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticIssue:
    """A single diagnostic finding."""

    issue_type: str  # composition / exposure / color_temp / continuity
    severity: str  # info / warning / error
    description: str
    suggestion: str = ""
    region: Optional[Tuple[int, int, int, int]] = None  # bbox
    scene_idx: Optional[int] = None


@dataclass
class ContinuityIssue:
    """Cross-scene continuity problem."""

    scene_a_idx: int
    scene_b_idx: int
    issue_type: str
    description: str


# ---------------------------------------------------------------------------
# Thresholds (configurable)
# ---------------------------------------------------------------------------

OVEREXPOSE_THRESHOLD = 240  # pixel value
OVEREXPOSE_RATIO = 0.05  # 5% of pixels
UNDEREXPOSE_THRESHOLD = 15
UNDEREXPOSE_RATIO = 0.10  # 10% of pixels
COLOR_TEMP_SHIFT_H = 15  # HSV hue shift threshold
BRIGHTNESS_JUMP_RATIO = 0.30  # 30% brightness change


class FrameDiagnostics:
    """Analyze video frames for quality issues."""

    def __init__(self, vlm_adapter: Optional[Any] = None):
        self._vlm = vlm_adapter

    # ------------------------------------------------------------------
    # R11: Composition check
    # ------------------------------------------------------------------

    def check_composition(self, frame: Any) -> List[DiagnosticIssue]:
        """Check frame composition quality using VLM.

        VLM analyzes: rule of thirds, headroom, horizon tilt, edge cropping.
        Falls back to empty list if VLM unavailable.
        """
        if self._vlm is None:
            return []

        prompt = (
            "分析这个视频帧的构图质量，检查以下问题并返回 JSON 数组：\n"
            "1. 三分法：主体是否偏��三分线太远\n"
            "2. 头顶空间：人物头顶留白是否过多或过少\n"
            "3. 水平线：是否明显倾斜\n"
            "4. 边缘裁切：主体是否被画面边缘裁切\n"
            "无问题返回空数组 []。有问题返回：\n"
            '[{"type":"composition","description":"描述","suggestion":"建议"}]\n'
            "仅返回 JSON，不要其他文字。"
        )

        try:
            resp = self._vlm.describe_image(image=frame, prompt=prompt)
            if resp is None:
                return []
            return self._parse_diagnostic_issues(resp.text, "composition")
        except Exception as exc:
            logger.warning("Composition check failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # R12: Exposure and color temperature check
    # ------------------------------------------------------------------

    def check_exposure(self, frame: Any) -> List[DiagnosticIssue]:
        """Check frame exposure using histogram analysis + optional VLM.

        Pure algorithm — works without VLM.
        """
        if not _HAS_NUMPY or not _HAS_PIL:
            return []

        issues = []
        try:
            arr = np.array(frame)
            if arr.ndim == 3:
                gray = np.mean(arr, axis=2)
            else:
                gray = arr.astype(float)

            total_px = gray.size

            # Overexposure check
            bright_ratio = np.sum(gray > OVEREXPOSE_THRESHOLD) / total_px
            if bright_ratio > OVEREXPOSE_RATIO:
                issues.append(DiagnosticIssue(
                    issue_type="exposure",
                    severity="warning",
                    description=f"高光溢出：{bright_ratio:.1%} 像素过亮 (>{OVEREXPOSE_THRESHOLD})",
                    suggestion="降低曝光或使用渐变滤镜",
                ))

            # Underexposure check
            dark_ratio = np.sum(gray < UNDEREXPOSE_THRESHOLD) / total_px
            if dark_ratio > UNDEREXPOSE_RATIO:
                issues.append(DiagnosticIssue(
                    issue_type="exposure",
                    severity="warning",
                    description=f"阴影死黑：{dark_ratio:.1%} 像素过暗 (<{UNDEREXPOSE_THRESHOLD})",
                    suggestion="提高暗部曝光或增加补光",
                ))

        except Exception as exc:
            logger.warning("Exposure check failed: %s", exc)

        return issues

    def check_color_temperature(self, frame: Any) -> List[DiagnosticIssue]:
        """Check color temperature bias using RGB blue-red ratio.

        Uses blue vs red channel mean difference instead of HSV hue,
        because PIL.Image.convert("HSV") is not supported.
        """
        if not _HAS_NUMPY or not _HAS_PIL:
            return []

        issues = []
        try:
            arr = np.array(frame.convert("RGB")).astype(float)
            r_mean = np.mean(arr[:, :, 0])
            b_mean = np.mean(arr[:, :, 2])

            # Blue-Red difference: positive = cool, negative = warm
            br_diff = b_mean - r_mean
            if br_diff > 30:
                issues.append(DiagnosticIssue(
                    issue_type="color_temp",
                    severity="info",
                    description=f"色温偏冷 (B-R差={br_diff:.0f})",
                    suggestion="增加暖色调或调整白平衡",
                ))
            elif br_diff < -30:
                issues.append(DiagnosticIssue(
                    issue_type="color_temp",
                    severity="info",
                    description=f"色温偏暖 (B-R差={br_diff:.0f})",
                    suggestion="降低暖色调或调整白平衡",
                ))

        except Exception as exc:
            logger.warning("Color temp check failed: %s", exc)

        return issues

    # ------------------------------------------------------------------
    # R13: Continuity check
    # ------------------------------------------------------------------

    def check_continuity(
        self,
        frames: List[Any],
        scene_indices: Optional[List[int]] = None,
    ) -> List[ContinuityIssue]:
        """Check visual continuity between adjacent scenes.

        Args:
            frames: List of representative frames (one per scene).
            scene_indices: Optional scene index labels.

        Returns:
            List of continuity issues found.
        """
        if not _HAS_NUMPY or not _HAS_PIL:
            return []

        if len(frames) < 2:
            return []

        issues = []
        for i in range(len(frames) - 1):
            idx_a = scene_indices[i] if scene_indices else i
            idx_b = scene_indices[i + 1] if scene_indices else i + 1

            try:
                arr_a = np.array(frames[i]).astype(float)
                arr_b = np.array(frames[i + 1]).astype(float)

                # Brightness jump
                bright_a = np.mean(arr_a)
                bright_b = np.mean(arr_b)
                if bright_a > 0:
                    jump = abs(bright_b - bright_a) / max(bright_a, 1)
                    if jump > BRIGHTNESS_JUMP_RATIO:
                        issues.append(ContinuityIssue(
                            scene_a_idx=idx_a,
                            scene_b_idx=idx_b,
                            issue_type="brightness_jump",
                            description=f"亮度跳变 {jump:.0%} (场景 {idx_a}→{idx_b})",
                        ))

                # Color temperature jump (blue-red ratio difference)
                rgb_a = np.array(frames[i].convert("RGB")).astype(float)
                rgb_b = np.array(frames[i + 1].convert("RGB")).astype(float)
                br_a = np.mean(rgb_a[:, :, 2]) - np.mean(rgb_a[:, :, 0])
                br_b = np.mean(rgb_b[:, :, 2]) - np.mean(rgb_b[:, :, 0])
                h_diff = abs(br_a - br_b)
                if h_diff > COLOR_TEMP_SHIFT_H:
                    issues.append(ContinuityIssue(
                        scene_a_idx=idx_a,
                        scene_b_idx=idx_b,
                        issue_type="color_jump",
                        description=f"色温跳变 H差={h_diff:.0f} (场景 {idx_a}→{idx_b})",
                    ))

            except Exception as exc:
                logger.warning("Continuity check failed for scenes %d→%d: %s", idx_a, idx_b, exc)

        return issues

    # ------------------------------------------------------------------
    # Combined diagnostics
    # ------------------------------------------------------------------

    def diagnose_frame(self, frame: Any) -> List[DiagnosticIssue]:
        """Run all single-frame diagnostics."""
        issues = []
        issues.extend(self.check_composition(frame))
        issues.extend(self.check_exposure(frame))
        issues.extend(self.check_color_temperature(frame))
        return issues

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_diagnostic_issues(text: str, default_type: str) -> List[DiagnosticIssue]:
        """Parse VLM response into DiagnosticIssue list."""
        import json

        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            items = json.loads(cleaned)
            if not isinstance(items, list):
                return []
            return [
                DiagnosticIssue(
                    issue_type=item.get("type", default_type),
                    severity=item.get("severity", "info"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                )
                for item in items
                if isinstance(item, dict) and item.get("description")
            ]
        except (json.JSONDecodeError, TypeError):
            return []
