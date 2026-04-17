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


# Round-14 P2: bound + lock the VLM cache.
# Previously unbounded (grew for process lifetime) and read/written without
# a lock (torn reads under Flask's threaded server). OrderedDict + Lock
# gives LRU semantics AND thread safety in one structure.
_VLM_CACHE_MAX = 512


class VLMAnalyzer:
    """VLM-powered region analysis with caching and graceful degradation."""

    def __init__(self, adapter: Optional[Any] = None):
        import threading as _threading
        from collections import OrderedDict as _OrderedDict
        self._adapter = adapter
        self._cache: "_OrderedDict[str, Tuple[float, RegionDescription]]" = _OrderedDict()
        self._cache_lock = _threading.Lock()

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

        # Check cache (thread-safe + LRU-promoting)
        cache_key = self._make_cache_key(image, context)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                ts, desc = cached
                if time.monotonic() - ts < CACHE_TTL_S:
                    # Promote to MRU
                    self._cache.move_to_end(cache_key)
                    return desc
                # Expired — drop it
                self._cache.pop(cache_key, None)

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
        with self._cache_lock:
            self._cache[cache_key] = (time.monotonic(), desc)
            # Evict oldest when over cap (LRU)
            while len(self._cache) > _VLM_CACHE_MAX:
                self._cache.popitem(last=False)

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

    # ------------------------------------------------------------------
    # R14: AI Reviewer — generate diagnostic comments
    # ------------------------------------------------------------------

    _SEVERITY_STATUS = {
        "info": "info",
        "warning": "open",
        "error": "flagged",
    }

    _TYPE_LABELS = {
        "composition": "构图",
        "exposure": "曝光",
        "color_temp": "色温",
        "continuity": "连续性",
    }

    @staticmethod
    def generate_ai_review(
        store: Any,
        session_id: str,
        version: int,
        diagnostics: List[Any],
        scene_times: Optional[Dict[int, tuple]] = None,
    ) -> int:
        """Convert diagnostic issues into AI review comments.

        Args:
            store: ReviewStore instance.
            session_id: Review session ID.
            version: Current version number.
            diagnostics: List[DiagnosticIssue].
            scene_times: Optional {scene_idx: (start_ms, end_ms)} mapping.

        Returns:
            Number of comments created.
        """
        if not diagnostics:
            return 0

        # Check existing AI comments to avoid duplicates (idempotency)
        existing = store.list_comments(session_id, filter_ai=True)
        existing_descs = {c["text"] for c in existing}

        created = 0
        for diag in diagnostics:
            label = VLMAnalyzer._TYPE_LABELS.get(diag.issue_type, diag.issue_type)
            text = f"[{label}] {diag.description}"
            if diag.suggestion:
                text += f" — {diag.suggestion}"
            text += " — AI 诊断"

            if text in existing_descs:
                continue

            # Determine time range from scene_times
            start_ms = 0
            end_ms = None
            if scene_times and diag.scene_idx is not None:
                times = scene_times.get(diag.scene_idx)
                if times:
                    start_ms, end_ms = times

            status = VLMAnalyzer._SEVERITY_STATUS.get(diag.severity, "info")
            comment_id = store.add_comment(
                session_id=session_id,
                version=version,
                time_start_ms=start_ms,
                time_end_ms=end_ms,
                comment_type="ai_diagnostic",
                text=text,
                ai_generated=True,
            )
            # Update status using returned comment_id (avoids N+1 query)
            if status != "pending":
                try:
                    store.update_comment(comment_id, status=status)
                except Exception:
                    pass  # update_comment may not support status field
            created += 1

        return created

    # ------------------------------------------------------------------
    # R10: Reference resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_references(
        comment_text: str,
        visual_context: Optional["RegionDescription"] = None,
    ) -> str:
        """Replace vague references with concrete objects from VLM context.

        Examples:
            "这个太大了" + objects=["logo"] → "logo 太大了"
            "颜色不对" + visual_issues=["色温偏冷"] → "颜色不对（色温偏冷）"
        """
        if visual_context is None or not comment_text:
            return comment_text

        result = comment_text

        # Chinese demonstrative pronouns to replace
        _SINGLE_REF = ["这个", "那个", "它", "这里", "那里", "这边", "那边", "这"]
        _PLURAL_REF = ["这些", "那些", "它们"]

        objects = visual_context.objects or []
        issues = visual_context.visual_issues or []

        # Replace single-object references
        if objects:
            obj_str = (
                objects[0] if len(objects) == 1
                else " 和 ".join(objects[:3])
            )
            for ref in _SINGLE_REF:
                if ref in result:
                    result = result.replace(ref, obj_str, 1)
                    break

            for ref in _PLURAL_REF:
                if ref in result:
                    result = result.replace(ref, obj_str, 1)
                    break

        # Append visual issues as clarification
        if issues and ("颜色" in result or "色" in result or "光" in result or "暗" in result or "亮" in result):
            issue_str = "、".join(issues[:2])
            if issue_str not in result:
                result += f"（{issue_str}）"

        return result

    @staticmethod
    def _make_cache_key(
        image: Any, context: Optional[AnalysisContext] = None
    ) -> str:
        """Generate a cache key from image content + context."""
        parts = []
        try:
            w, h = image.size
            parts.append(f"{w}x{h}")
            # Sample 5 pixels for better uniqueness
            samples = [
                (w // 2, h // 2),
                (w // 4, h // 4),
                (3 * w // 4, h // 4),
                (w // 4, 3 * h // 4),
                (3 * w // 4, 3 * h // 4),
            ]
            for sx, sy in samples:
                sx = min(sx, w - 1)
                sy = min(sy, h - 1)
                parts.append(str(image.getpixel((sx, sy))))
        except Exception:
            parts.append("unknown_image")

        if context:
            parts.append(f"ts={context.timestamp_ms}")
            parts.append(f"vt={context.video_type}")

        key_str = "|".join(parts)
        return hashlib.md5(key_str.encode()).hexdigest()
