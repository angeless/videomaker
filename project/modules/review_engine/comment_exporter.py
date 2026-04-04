"""CommentExporter — export review comments to JSON/CSV/EDL formats."""

import csv
import io
import json
import logging
from typing import Dict, List

from .exceptions import ReviewEngineError

logger = logging.getLogger(__name__)


def export_comments(comments: List[Dict], fmt: str = "json") -> str:
    """Export comments to the specified format.

    Args:
        comments: List of comment dicts
        fmt: "json" | "csv" | "edl"

    Returns:
        Formatted string content
    """
    if fmt == "json":
        return _export_json(comments)
    elif fmt == "csv":
        return _export_csv(comments)
    elif fmt == "edl":
        return _export_edl(comments)
    else:
        raise ReviewEngineError(f"Unsupported export format: {fmt}")


def _export_json(comments: List[Dict]) -> str:
    return json.dumps(comments, ensure_ascii=False, indent=2)


def _export_csv(comments: List[Dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timecode", "type", "text", "status", "ai_reply"])

    for c in comments:
        tc = _ms_to_timecode(c.get("time_start_ms", 0))
        writer.writerow([
            tc,
            c.get("type", ""),
            c.get("text", ""),
            c.get("status", "pending"),
            c.get("ai_reply", ""),
        ])

    return output.getvalue()


def _export_edl(comments: List[Dict]) -> str:
    """Export as CMX 3600 EDL (simplified).

    Each comment becomes a marker event.
    """
    lines = ["TITLE: Review Comments", "FCM: NON-DROP FRAME", ""]
    for i, c in enumerate(comments, 1):
        start_ms = c.get("time_start_ms") or 0
        end_ms = c.get("time_end_ms") or start_ms
        start_tc = _ms_to_smpte(start_ms)
        end_tc = _ms_to_smpte(end_ms)
        lines.append(f"{i:03d}  AX  V  C  {start_tc} {end_tc} {start_tc} {end_tc}")
        text = c.get("text", "").replace("\n", " ")[:60]
        lines.append(f"* COMMENT: [{c.get('type', 'note')}] {text}")
        lines.append("")

    return "\n".join(lines)


def _ms_to_timecode(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS.mmm."""
    s, ms_part = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_part:03d}"


def _ms_to_smpte(ms: int, fps: int = 25) -> str:
    """Convert milliseconds to SMPTE timecode HH:MM:SS:FF."""
    total_frames = int(ms / 1000 * fps)
    f = total_frames % fps
    s = (total_frames // fps) % 60
    m = (total_frames // fps // 60) % 60
    h = total_frames // fps // 60 // 60
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
