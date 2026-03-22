"""Execute parsed editing commands against a timeline clips list."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from modules.prompt_editing.parser import EditCommand


def execute_edit_command(
    clips: List[Dict[str, Any]],
    command: EditCommand,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Apply *command* to *clips* and return (new_clips, change_summary).

    Does NOT persist — caller is responsible for writing back to disk.
    Operates on a deep copy to allow undo.
    """
    if not command.valid:
        return clips, {"error": "unrecognised command", "raw": command.raw}

    working = copy.deepcopy(clips)
    total = len(working)

    # Resolve special index -1 → last clip
    targets = _resolve_indices(command.targets, total)

    handler = _HANDLERS.get(command.action)
    if handler is None:
        return clips, {"error": f"unknown action: {command.action}"}

    new_clips, summary = handler(working, targets, command.params)
    # Reassign clip_index sequentially
    for i, c in enumerate(new_clips):
        c["clip_index"] = i + 1

    summary["action"] = command.action
    summary["affected_clips"] = targets
    return new_clips, summary


# ── resolvers ──

def _resolve_indices(targets: List[int], total: int) -> List[int]:
    out = []
    for t in targets:
        if t == -1:
            out.append(total)
        elif 1 <= t <= total:
            out.append(t)
    return out


# ── action handlers ──

def _handle_delete(
    clips: List[Dict], targets: List[int], params: Dict,
) -> Tuple[List[Dict], Dict]:
    if not targets:
        return clips, {"error": "no clip targets specified for delete"}
    target_set = set(targets)
    remaining = [c for c in clips if c.get("clip_index") not in target_set]
    return remaining, {"deleted": len(clips) - len(remaining)}


def _handle_reorder(
    clips: List[Dict], targets: List[int], params: Dict,
) -> Tuple[List[Dict], Dict]:
    if len(targets) < 2:
        return clips, {"error": "reorder needs at least 2 clip indices"}
    # Simple swap: move first target to position of second target
    by_idx = {c["clip_index"]: i for i, c in enumerate(clips)}
    from_pos = by_idx.get(targets[0])
    to_pos = by_idx.get(targets[1])
    if from_pos is None or to_pos is None:
        return clips, {"error": "clip index not found"}
    moved = clips.pop(from_pos)
    clips.insert(to_pos, moved)
    return clips, {"moved": targets[0], "to_position": to_pos + 1}


def _handle_trim(
    clips: List[Dict], targets: List[int], params: Dict,
) -> Tuple[List[Dict], Dict]:
    new_duration = params.get("duration")
    if not targets:
        return clips, {"error": "no clip targets specified for trim"}
    trimmed = 0
    for clip in clips:
        if clip.get("clip_index") in targets:
            old_dur = float(clip.get("duration", 0) or 0)
            if new_duration and new_duration < old_dur:
                clip["duration"] = round(new_duration, 3)
                clip["source_end"] = round(
                    float(clip.get("source_start", 0) or 0) + new_duration, 3
                )
                trimmed += 1
            elif not new_duration:
                # Default: trim 30%
                clip["duration"] = round(old_dur * 0.7, 3)
                clip["source_end"] = round(
                    float(clip.get("source_start", 0) or 0) + clip["duration"], 3
                )
                trimmed += 1
    return clips, {"trimmed": trimmed}


def _handle_reverse(
    clips: List[Dict], targets: List[int], params: Dict,
) -> Tuple[List[Dict], Dict]:
    clips.reverse()
    return clips, {"reversed": True}


def _handle_speed(
    clips: List[Dict], targets: List[int], params: Dict,
) -> Tuple[List[Dict], Dict]:
    speed = params.get("speed", 1.0) or 1.0
    if not targets:
        return clips, {"error": "no clip targets specified for speed change"}
    adjusted = 0
    for clip in clips:
        if clip.get("clip_index") in targets:
            old_dur = float(clip.get("duration", 0) or 0)
            if old_dur > 0 and speed > 0:
                clip["duration"] = round(old_dur / speed, 3)
                clip["speed"] = round(speed, 2)
                adjusted += 1
    return clips, {"speed_adjusted": adjusted, "speed": speed}


_HANDLERS = {
    "delete": _handle_delete,
    "reorder": _handle_reorder,
    "trim": _handle_trim,
    "reverse": _handle_reverse,
    "speed": _handle_speed,
}
