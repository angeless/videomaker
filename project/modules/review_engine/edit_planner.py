"""EditPlanner — apply edit instructions to segment list, produce diffs.

Takes EditInstruction objects and the current EDITS list, generates a new
edit list with a structured diff describing what changed.
"""

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .contracts import EditInstruction, Segment
from .exceptions import ConflictingCommentsError

logger = logging.getLogger(__name__)


@dataclass
class DiffEntry:
    """A single change in the edit plan diff."""
    action: str  # "added" | "removed" | "modified"
    idx: int
    segment: Optional[Dict] = None
    old_segment: Optional[Dict] = None
    new_segment: Optional[Dict] = None


@dataclass
class EditPlan:
    """Result of applying instructions to the edit list."""
    new_edits: List[Segment]
    diff: List[DiffEntry]
    summary_text: str


def _seg_to_dict(seg: Segment) -> Dict:
    return {
        "source_path": seg.source_path,
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "segment_type": seg.segment_type,
        "label": seg.label,
    }


def apply_instructions(
    instructions: List[EditInstruction],
    current_edits: List[Segment],
) -> EditPlan:
    """Apply a list of instructions to the current edit list."""
    new_edits = deepcopy(current_edits)
    diff = []
    summaries = []

    # Sort instructions by segment_idx descending so removals don't shift indices
    sorted_insts = sorted(
        instructions,
        key=lambda i: i.segment_idx if i.segment_idx is not None else -1,
        reverse=True,
    )

    for inst in sorted_insts:
        idx = inst.segment_idx
        itype = inst.instruction_type

        if itype == "remove" and idx is not None and 0 <= idx < len(new_edits):
            removed = new_edits.pop(idx)
            diff.append(DiffEntry(
                action="removed", idx=idx, segment=_seg_to_dict(removed),
            ))
            dur = (removed.end_ms - removed.start_ms) / 1000
            summaries.append(f"删除了第{idx + 1}段 ({dur:.1f}s)")

        elif itype == "extend" and idx is not None and 0 <= idx < len(new_edits):
            seg = new_edits[idx]
            old = _seg_to_dict(seg)
            ext_ms = inst.params.get("duration_ms", 2000)
            direction = inst.params.get("direction", "both")
            if direction == "start":
                seg.start_ms = max(0, seg.start_ms - ext_ms)
            elif direction == "end":
                seg.end_ms += ext_ms
            else:
                seg.start_ms = max(0, seg.start_ms - ext_ms // 2)
                seg.end_ms += ext_ms // 2
            diff.append(DiffEntry(
                action="modified", idx=idx,
                old_segment=old, new_segment=_seg_to_dict(seg),
            ))
            summaries.append(f"扩展了第{idx + 1}段 {ext_ms / 1000:.1f}s")

        elif itype == "trim" and idx is not None and 0 <= idx < len(new_edits):
            seg = new_edits[idx]
            old = _seg_to_dict(seg)
            if "trim_start_ms" in inst.params:
                seg.start_ms += inst.params["trim_start_ms"]
            if "trim_end_ms" in inst.params:
                seg.end_ms -= inst.params["trim_end_ms"]
            seg.end_ms = max(seg.start_ms + 100, seg.end_ms)  # min 100ms
            diff.append(DiffEntry(
                action="modified", idx=idx,
                old_segment=old, new_segment=_seg_to_dict(seg),
            ))
            summaries.append(f"裁剪了第{idx + 1}段")

        elif itype == "insert":
            src_start = inst.params.get("source_start_ms", 0)
            src_end = inst.params.get("source_end_ms", 0)
            pos = inst.params.get("position", len(new_edits))
            if isinstance(pos, str):
                pos = len(new_edits)
            new_seg = Segment(
                source_path=current_edits[0].source_path if current_edits else "",
                start_ms=src_start,
                end_ms=src_end,
                segment_type="inserted",
            )
            pos = min(pos, len(new_edits))
            new_edits.insert(pos, new_seg)
            diff.append(DiffEntry(
                action="added", idx=pos, segment=_seg_to_dict(new_seg),
            ))
            dur = (src_end - src_start) / 1000
            summaries.append(f"在位置{pos + 1}插入了 {dur:.1f}s 片段")

        elif itype == "reorder" and idx is not None and 0 <= idx < len(new_edits):
            target = inst.params.get("target_idx", 0)
            if 0 <= target < len(new_edits) and target != idx:
                seg = new_edits.pop(idx)
                new_edits.insert(target, seg)
                diff.append(DiffEntry(
                    action="modified", idx=idx,
                    old_segment={"position": idx},
                    new_segment={"position": target},
                ))
                summaries.append(f"将第{idx + 1}段移到位置{target + 1}")

        elif itype == "speed" and idx is not None and 0 <= idx < len(new_edits):
            seg = new_edits[idx]
            old = _seg_to_dict(seg)
            factor = inst.params.get("factor", 1.0)
            seg.label = f"speed:{factor}"
            diff.append(DiffEntry(
                action="modified", idx=idx,
                old_segment=old, new_segment=_seg_to_dict(seg),
            ))
            summaries.append(f"第{idx + 1}段变速 {factor}x")

        elif itype == "transition":
            effect = inst.params.get("effect", "cross_dissolve")
            target = idx if idx is not None else len(new_edits) - 1
            if 0 <= target < len(new_edits):
                seg = new_edits[target]
                old = _seg_to_dict(seg)
                seg.label = f"transition:{effect}"
                diff.append(DiffEntry(
                    action="modified", idx=target,
                    old_segment=old, new_segment=_seg_to_dict(seg),
                ))
                summaries.append(f"第{target + 1}段添加{effect}转场")

        # Other types (subtitle, speaker, hook, broll, audio, split, merge)
        # are handled at a higher level or don't modify the edit list directly

    summary = "；".join(reversed(summaries)) if summaries else "无变更"
    return EditPlan(new_edits=new_edits, diff=diff, summary_text=summary)


def detect_conflicts(
    instructions: List[EditInstruction],
) -> Tuple[List[Dict], List[EditInstruction]]:
    """Detect conflicts between instructions targeting the same segment.

    Returns:
        (conflicts, resolved_instructions) where conflicts is a list of
        conflict descriptions and resolved_instructions has conflicts removed.
    """
    # Group by segment_idx
    by_segment: Dict[int, List[EditInstruction]] = {}
    no_segment = []
    for inst in instructions:
        if inst.segment_idx is not None:
            by_segment.setdefault(inst.segment_idx, []).append(inst)
        else:
            no_segment.append(inst)

    conflicts = []
    resolved = list(no_segment)

    # Incompatible pairs
    INCOMPATIBLE = {
        frozenset({"remove", "extend"}),
        frozenset({"remove", "trim"}),
        frozenset({"remove", "speed"}),
        frozenset({"remove", "insert"}),
    }

    # Mergeable pairs (both can coexist)
    MERGEABLE = {
        frozenset({"trim", "speed"}),
        frozenset({"extend", "transition"}),
        frozenset({"trim", "transition"}),
        frozenset({"speed", "transition"}),
    }

    for seg_idx, insts in by_segment.items():
        if len(insts) <= 1:
            resolved.extend(insts)
            continue

        types = {i.instruction_type for i in insts}
        type_pairs = [
            frozenset({a, b})
            for i, a in enumerate(types)
            for b in list(types)[i + 1:]
        ]

        has_conflict = any(p in INCOMPATIBLE for p in type_pairs)

        if has_conflict:
            conflicts.append({
                "segment_idx": seg_idx,
                "instructions": [i.instruction_type for i in insts],
                "reason": f"Conflicting operations on segment {seg_idx}",
            })
        else:
            resolved.extend(insts)

    return conflicts, resolved
