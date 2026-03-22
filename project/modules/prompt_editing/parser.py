"""Rule-based parser for natural language timeline editing commands.

Supports Chinese and English commands.  No LLM dependency — pure regex.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EditCommand:
    """Parsed editing command."""
    action: str  # delete | reorder | trim | reverse | speed
    targets: List[int] = field(default_factory=list)  # clip indices (1-based)
    params: Dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    confidence: float = 1.0

    @property
    def valid(self) -> bool:
        return bool(self.action)


# ── number extraction helpers ──

_ZH_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
              "第一": 1, "第二": 2, "第三": 3, "第四": 4, "第五": 5,
              "第六": 6, "第七": 7, "第八": 8, "第九": 9, "第十": 10,
              "最后": -1, "last": -1, "first": 1}

_NUM_RE = re.compile(r"\d+")


def _extract_clip_indices(text: str) -> List[int]:
    """Extract clip index references from text."""
    indices: List[int] = []
    # Chinese ordinals
    for zh, num in _ZH_DIGITS.items():
        if zh in text:
            indices.append(num)
    # Numeric: "clip 3", "#3", "第3个"
    for m in _NUM_RE.finditer(text):
        n = int(m.group())
        if 1 <= n <= 100:
            indices.append(n)
    # Deduplicate preserving order
    seen = set()
    out = []
    for i in indices:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _extract_seconds(text: str) -> Optional[float]:
    """Extract a duration in seconds from text."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:秒|s|sec|seconds?)", text)
    if m:
        return float(m.group(1))
    return None


def _extract_speed(text: str) -> Optional[float]:
    """Extract speed multiplier from text."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*[xX×倍]", text)
    if m:
        return float(m.group(1))
    # "加速" / "减速" without explicit multiplier
    if re.search(r"加速|speed\s*up|faster", text, re.I):
        return 2.0
    if re.search(r"减速|slow\s*down|slower", text, re.I):
        return 0.5
    return None


# ── intent patterns ──

_DELETE_RE = re.compile(
    r"删除|移除|去掉|remove|delete|drop|cut out",
    re.I,
)

_MOVE_RE = re.compile(
    r"移动|移到|放到|swap|move|put.*(?:after|before|behind)",
    re.I,
)

_TRIM_RE = re.compile(
    r"裁剪|缩短|截短|缩到|改为|trim|shorten|cut to|make.*shorter",
    re.I,
)

_REVERSE_RE = re.compile(
    r"倒序|反转|逆序|reverse|flip order",
    re.I,
)

_SPEED_RE = re.compile(
    r"加速|减速|变速|speed|faster|slower|倍速",
    re.I,
)


def parse_edit_command(text: str) -> EditCommand:
    """Parse a natural language editing command into an EditCommand."""
    text = str(text or "").strip()
    if not text:
        return EditCommand(action="", raw=text, confidence=0.0)

    indices = _extract_clip_indices(text)

    # Delete
    if _DELETE_RE.search(text):
        return EditCommand(action="delete", targets=indices, raw=text)

    # Move / reorder
    if _MOVE_RE.search(text):
        return EditCommand(action="reorder", targets=indices, raw=text)

    # Trim
    if _TRIM_RE.search(text):
        secs = _extract_seconds(text)
        params = {"duration": secs} if secs else {}
        return EditCommand(action="trim", targets=indices, params=params, raw=text)

    # Reverse
    if _REVERSE_RE.search(text):
        return EditCommand(action="reverse", targets=indices, raw=text)

    # Speed
    if _SPEED_RE.search(text):
        spd = _extract_speed(text)
        params = {"speed": spd} if spd else {}
        return EditCommand(action="speed", targets=indices, params=params, raw=text)

    return EditCommand(action="", raw=text, confidence=0.0)
