"""Highlight-based short clip selection."""

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List


@dataclass
class HighlightCandidate:
    """Candidate moment detected from long video."""

    start: float
    end: float
    score: float
    reason: str = ""


def pick_highlights(
    candidates: Iterable[HighlightCandidate],
    target_duration_s: float = 30.0,
    max_clips: int = 8,
    min_gap_s: float = 0.30,
) -> List[HighlightCandidate]:
    """Greedy selection by score, keeping non-overlapping clips."""
    budget = max(float(target_duration_s), 1.0)
    max_clips = max(int(max_clips), 1)
    min_gap_s = max(float(min_gap_s), 0.0)

    ranked = sorted(candidates, key=lambda x: (x.score, -(x.end - x.start)), reverse=True)
    selected: List[HighlightCandidate] = []
    used = 0.0

    for cand in ranked:
        if len(selected) >= max_clips or used >= budget:
            break
        if cand.end <= cand.start:
            continue
        if _overlaps(selected, cand, min_gap_s):
            continue

        duration = cand.end - cand.start
        if used + duration > budget:
            duration = budget - used
            if duration <= 0:
                continue
            cand = HighlightCandidate(
                start=cand.start,
                end=round(cand.start + duration, 3),
                score=cand.score,
                reason=cand.reason,
            )

        selected.append(cand)
        used += cand.end - cand.start

    return sorted(selected, key=lambda x: x.start)


def highlights_to_timeline(selected: Iterable[HighlightCandidate]) -> Dict:
    """Return JSON-ready timeline payload."""
    clips = [asdict(x) for x in sorted(selected, key=lambda c: c.start)]
    total = round(sum(c["end"] - c["start"] for c in clips), 3)
    return {
        "clips": clips,
        "total_duration_s": total,
    }


def _overlaps(selected: Iterable[HighlightCandidate], cand: HighlightCandidate, min_gap_s: float) -> bool:
    for item in selected:
        if cand.end + min_gap_s <= item.start:
            continue
        if cand.start >= item.end + min_gap_s:
            continue
        return True
    return False
