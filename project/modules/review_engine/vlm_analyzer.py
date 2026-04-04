"""VLMAnalyzer — core VLM analysis engine for region description and diagnostics.

Accepts cropped region images from RegionExtractor, sends them to a VLM adapter,
and returns structured descriptions. Includes caching to avoid redundant calls.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CACHE_TTL_S = 300  # 5 minutes

# Default prompt for region description
_DESCRIBE_PROMPT = (
    "你是一个视频画面分析助手。请分析这个视频帧的标注区域，返回 JSON 格式：\n"
    '{"summary": "画面内容的自然语言描述", '
    '"objects": ["识别到的物体列表"], '
    '"scene_type": "场景类型(indoor/outdoor/closeup/text/graphic)", '
    '"visual_issues": ["画面问题列表(过曝/欠曝/模糊/色温偏移等)"]}\n'
    "仅返回 JSON，不要附加其他文字。"
)


@dataclass
class AnalysisContext:
    """Context for VLM analysis — helps the model understand the video."""

    video_type: str = ""  # speech / scenic / mixed
    timestamp_ms: int = 0
    surrounding_text: str = ""


@dataclass
class RegionDescription:
    """Structured description of an annotated region."""

    summary: str = ""
    objects: List[str] = field(default_factory=list)
    scene_type: str = ""
    visual_issues: List[str] = field(default_factory=list)


_FALLBACK = RegionDescription(summary="[画面区域]", objects=[], scene_type="", visual_issues=[])


class VLMAnalyzer:
    """VLM-powered region analysis with caching and graceful degradation."""

    def __init__(self, adapter: Optional[Any] = None):
        self._adapter = adapter
        self._cache: Dict[str, Tuple[float, RegionDescription]] = {}

    def describe_region(
        self,
        image: Any,
        context: Optional[AnalysisContext] = None,
    ) -> RegionDescription:
        """Analyze an image region and return a structured description.

        Args:
            image: PIL.Image of the cropped region.
            context: Optional analysis context.

        Returns:
            RegionDescription — always returns a valid object (never None).
        """
        if self._adapter is None:
            return RegionDescription(
                summary="[画面区域]", objects=[], scene_type="", visual_issues=[]
            )

        # Check cache
        cache_key = self._make_cache_key(image, context)
        cached = self._cache.get(cache_key)
        if cached is not None:
            ts, desc = cached
            if time.monotonic() - ts < CACHE_TTL_S:
                return desc

        # Build prompt with context
        prompt = self._build_prompt(context)

        # Call VLM
        try:
            resp = self._adapter.describe_image(image=image, prompt=prompt)
        except Exception as exc:
            logger.warning("VLM adapter call failed: %s", exc)
            resp = None

        if resp is None:
            return RegionDescription(
                summary="[画面区域]", objects=[], scene_type="", visual_issues=[]
            )

        # Parse response
        desc = self._parse_response(resp.text)

        # Update cache
        self._cache[cache_key] = (time.monotonic(), desc)

        return desc

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_prompt(self, context: Optional[AnalysisContext] = None) -> str:
        """Build the VLM prompt, optionally enriched with context."""
        parts = [_DESCRIBE_PROMPT]
        if context:
            if context.video_type:
                parts.append(f"视频类型: {context.video_type}")
            if context.timestamp_ms:
                secs = context.timestamp_ms / 1000.0
                parts.append(f"时间位置: {secs:.1f}s")
            if context.surrounding_text:
                parts.append(f"上下文文本: {context.surrounding_text}")
        return "\n".join(parts)

    @staticmethod
    def _parse_response(text: str) -> RegionDescription:
        """Parse VLM response text into RegionDescription.

        Tries JSON first, falls back to using raw text as summary.
        """
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        # Try JSON parse
        try:
            data = json.loads(cleaned)
            return RegionDescription(
                summary=data.get("summary", cleaned),
                objects=data.get("objects", []),
                scene_type=data.get("scene_type", ""),
                visual_issues=data.get("visual_issues", []),
            )
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: use raw text as summary
        return RegionDescription(
            summary=cleaned if cleaned else "[画面区域]",
            objects=[],
            scene_type="",
            visual_issues=[],
        )

    @staticmethod
    def _make_cache_key(
        image: Any, context: Optional[AnalysisContext] = None
    ) -> str:
        """Generate a cache key from image content + context."""
        parts = []
        try:
            # Use image size + a sample of pixel data for fast hashing
            w, h = image.size
            parts.append(f"{w}x{h}")
            # Sample center pixel
            cx, cy = w // 2, h // 2
            parts.append(str(image.getpixel((cx, cy))))
        except Exception:
            parts.append("unknown_image")

        if context:
            parts.append(f"ts={context.timestamp_ms}")
            parts.append(f"vt={context.video_type}")

        key_str = "|".join(parts)
        return hashlib.md5(key_str.encode()).hexdigest()
