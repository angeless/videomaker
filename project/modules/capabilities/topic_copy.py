"""Topic + copy capability helpers."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List

from .topic_library import TopicTemplate


@dataclass
class CopyDraft:
    """Structured copy output for downstream script modules."""

    title: str
    hook: str
    outline: List[str]
    narration_style: str
    target_duration_s: int
    cta: str
    matched_signals: List[str]


def select_semantic_signals(
    material_semantics: Iterable[Dict[str, Any]],
    max_signals: int = 6,
) -> List[str]:
    """Pick compact, de-duplicated semantic hints from materials."""
    signals: List[str] = []
    for item in material_semantics:
        for key in ("setting", "activity", "mood", "time_of_day", "weather", "narrative_role"):
            value = str(item.get(key, "") or "").strip()
            if value and value not in signals:
                signals.append(value)
        if len(signals) >= max_signals:
            break
    return signals[:max_signals]


def build_copy_draft(
    topic: TopicTemplate,
    material_semantics: Iterable[Dict[str, Any]],
    target_duration_s: int = 60,
) -> CopyDraft:
    """
    Build a deterministic copy draft.

    This is a fallback generator that keeps output stable when AI providers are unavailable.
    """
    signals = select_semantic_signals(material_semantics)
    lead = signals[0] if signals else "旅途现场"
    support = "、".join(signals[1:3]) if len(signals) > 1 else "人物状态和环境变化"

    outline = [
        f"开场 0-3s: 用 {lead} 作为第一镜头，立即给出冲突或惊喜。",
        "中段 3-45s: 按时间推进，交代地点切换和人物行动。",
        f"结尾 45-{target_duration_s}s: 回收情绪，强调 {support} 的变化并给出观点。",
    ]

    hook = f"3秒内看完这段 {lead}，你会想立刻出发。"
    cta = "收藏这条路线，下一条我把完整拍摄机位给你。"

    return CopyDraft(
        title=topic.title,
        hook=hook,
        outline=outline,
        narration_style=topic.hook_style,
        target_duration_s=max(int(target_duration_s), 10),
        cta=cta,
        matched_signals=signals,
    )


def build_copy_payload(
    topic: TopicTemplate,
    material_semantics: Iterable[Dict[str, Any]],
    target_duration_s: int = 60,
) -> Dict[str, Any]:
    """Convenience wrapper returning plain dict."""
    return asdict(build_copy_draft(topic, material_semantics, target_duration_s=target_duration_s))
