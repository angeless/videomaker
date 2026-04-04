"""IntentRouter — parse natural language comments into structured edit instructions.

Uses a configurable LLM caller to convert free-text review comments
into typed EditInstruction objects with schema validation.
"""

import json
import logging
import re
from typing import Callable, Dict, List, Optional

from .contracts import EditInstruction
from .exceptions import IntentRouterError

logger = logging.getLogger(__name__)

# 14 supported instruction types with required/optional params
INSTRUCTION_SCHEMAS: Dict[str, Dict] = {
    "extend": {"required": [], "optional": ["duration_ms", "direction"]},
    "trim": {"required": [], "optional": ["trim_start_ms", "trim_end_ms"]},
    "remove": {"required": [], "optional": []},
    "insert": {"required": ["source_start_ms", "source_end_ms"], "optional": ["position"]},
    "reorder": {"required": ["target_idx"], "optional": []},
    "split": {"required": ["split_at_ms"], "optional": []},
    "merge": {"required": ["merge_with_idx"], "optional": []},
    "transition": {"required": [], "optional": ["effect", "duration_ms"]},
    "subtitle": {"required": ["text"], "optional": ["style"]},
    "speaker": {"required": ["action"], "optional": ["speaker_id"]},
    "hook": {"required": [], "optional": ["strategy"]},
    "speed": {"required": ["factor"], "optional": []},
    "broll": {"required": ["query"], "optional": ["duration_ms", "position"]},
    "audio": {"required": ["action"], "optional": ["level_db", "preset"]},
}

SYSTEM_PROMPT = """你是一个视频编辑指令解析器。根据用户的评审评论，生成结构化的编辑指令 JSON 数组。

支持的指令类型：
- extend: 延长片段
- trim: 裁剪片段
- remove: 删除片段
- insert: 插入新片段
- reorder: 重新排列
- split: 分割片段
- merge: 合并片段
- transition: 添加转场
- subtitle: 修改字幕
- speaker: 说话人操作
- hook: 钩子策略
- speed: 变速
- broll: B-roll 素材
- audio: 音频调整

返回格式（纯 JSON 数组，无其他文字）：
[{"type": "remove", "segment_idx": 3}, {"type": "transition", "effect": "cross_dissolve"}]
"""


def validate_instruction(raw: Dict) -> EditInstruction:
    """Validate a raw instruction dict against the schema."""
    itype = raw.get("type")
    if not itype or itype not in INSTRUCTION_SCHEMAS:
        raise IntentRouterError(f"Unknown instruction type: {itype}")

    schema = INSTRUCTION_SCHEMAS[itype]
    params = {k: v for k, v in raw.items() if k not in ("type", "segment_idx")}

    for req in schema["required"]:
        if req not in params:
            raise IntentRouterError(
                f"Instruction '{itype}' missing required param: {req}"
            )

    return EditInstruction(
        instruction_type=itype,
        segment_idx=raw.get("segment_idx"),
        params=params,
    )


def parse_llm_response(response_text: str) -> List[Dict]:
    """Extract JSON array from LLM response text."""
    # Try direct parse
    text = response_text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code block
    match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding array pattern
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise IntentRouterError(f"Cannot parse LLM response as JSON: {text[:200]}")


def route_comment(
    comment_text: str,
    segment_idx: Optional[int],
    context: Optional[Dict] = None,
    llm_caller: Optional[Callable] = None,
) -> List[EditInstruction]:
    """Route a comment through LLM to get edit instructions.

    Args:
        comment_text: The review comment text
        segment_idx: Which segment the comment targets (from CommentResolver)
        context: Optional context (video_type, duration, etc.)
        llm_caller: Callable(system_prompt, user_prompt) -> str
                    If None, uses keyword-based fallback
    """
    if llm_caller is not None:
        return _route_via_llm(comment_text, segment_idx, context, llm_caller)
    return _route_via_keywords(comment_text, segment_idx)


def _route_via_llm(
    comment_text: str,
    segment_idx: Optional[int],
    context: Optional[Dict],
    llm_caller: Callable,
) -> List[EditInstruction]:
    """Use LLM to parse comment into instructions."""
    ctx_str = ""
    if context:
        ctx_str = f"\n上下文: {json.dumps(context, ensure_ascii=False)}"

    seg_str = ""
    if segment_idx is not None:
        seg_str = f"\n目标片段索引: {segment_idx}"

    user_prompt = f"评论: {comment_text}{seg_str}{ctx_str}"

    try:
        response = llm_caller(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        raise IntentRouterError(f"LLM call failed: {e}") from e

    raw_instructions = parse_llm_response(response)
    instructions = []
    for raw in raw_instructions:
        if segment_idx is not None and "segment_idx" not in raw:
            raw["segment_idx"] = segment_idx
        instructions.append(validate_instruction(raw))
    return instructions


# Keyword-based fallback when no LLM is available
_KEYWORD_MAP = {
    "删": "remove",
    "砍": "remove",
    "去掉": "remove",
    "延长": "extend",
    "加长": "extend",
    "恢复": "extend",
    "裁": "trim",
    "缩短": "trim",
    "转场": "transition",
    "过渡": "transition",
    "字幕": "subtitle",
    "加速": "speed",
    "减速": "speed",
    "B-roll": "broll",
    "b-roll": "broll",
    "补充素材": "broll",
    "音频": "audio",
    "降噪": "audio",
    "音量": "audio",
    "钩子": "hook",
    "开场": "hook",
}


def _route_via_keywords(
    comment_text: str,
    segment_idx: Optional[int],
) -> List[EditInstruction]:
    """Simple keyword-based routing as fallback."""
    instructions = []
    for keyword, itype in _KEYWORD_MAP.items():
        if keyword in comment_text:
            params = {}
            if itype == "transition":
                params["effect"] = "cross_dissolve"
            elif itype == "speed":
                params["factor"] = 1.5 if "加速" in comment_text else 0.5
            elif itype == "audio":
                params["action"] = "denoise" if "降噪" in comment_text else "adjust"
            elif itype == "subtitle":
                params["text"] = comment_text
            elif itype == "hook":
                params["strategy"] = "auto"
            elif itype == "broll":
                params["query"] = comment_text

            instructions.append(EditInstruction(
                instruction_type=itype,
                segment_idx=segment_idx,
                params=params,
            ))
            break  # One keyword match per comment in fallback mode

    if not instructions:
        # Default: treat as a general note, no instruction
        instructions.append(EditInstruction(
            instruction_type="remove",
            segment_idx=segment_idx,
            params={},
        ))

    return instructions


# ── R11: AI Reply Generation ──

# Human-readable descriptions for each instruction type
_ACTION_LABELS = {
    "remove": "删除",
    "extend": "延长",
    "trim": "裁剪",
    "insert": "插入",
    "reorder": "移动",
    "split": "拆分",
    "merge": "合并",
    "transition": "添加转场",
    "subtitle": "修改字幕",
    "speaker": "切换说话人",
    "hook": "设为开场",
    "speed": "调速",
    "broll": "补充B-roll",
    "audio": "音频调整",
}


def generate_ai_reply(
    comment_text: str,
    instructions: List[EditInstruction],
    diff: Optional[List] = None,
) -> str:
    """Generate a concise AI reply explaining what was done for a comment.

    Args:
        comment_text: The original review comment
        instructions: Applied EditInstruction objects
        diff: Optional list of DiffEntry dicts with action/idx keys

    Returns:
        Natural language reply (< 100 chars)
    """
    if not instructions:
        return "已记录，暂无自动操作"

    parts = []
    for inst in instructions:
        label = _ACTION_LABELS.get(inst.instruction_type, inst.instruction_type)
        idx = inst.segment_idx
        params = inst.params or {}

        if inst.instruction_type == "remove" and idx is not None:
            parts.append(f"已{label}片段 #{idx}")
        elif inst.instruction_type == "extend":
            dur = params.get("duration_ms")
            direction = params.get("direction", "end")
            if dur:
                parts.append(f"已{label} {dur}ms ({direction})")
            else:
                parts.append(f"已{label}片段")
        elif inst.instruction_type == "trim":
            trim_s = params.get("trim_start_ms", 0)
            trim_e = params.get("trim_end_ms", 0)
            total = trim_s + trim_e
            if total:
                parts.append(f"已{label} {total}ms")
            else:
                parts.append(f"已{label}片段")
        elif inst.instruction_type == "speed":
            factor = params.get("factor", 1.0)
            parts.append(f"已{label}至 {factor}x")
        elif inst.instruction_type == "transition":
            effect = params.get("effect", "cross_dissolve")
            parts.append(f"已{label} ({effect})")
        else:
            parts.append(f"已{label}")

    reply = "；".join(parts)

    # Append diff summary if available
    if diff:
        n_changes = len(diff)
        reply += f"（共 {n_changes} 处变更）"

    # Ensure under 100 chars
    if len(reply) > 100:
        reply = reply[:97] + "..."

    return reply
