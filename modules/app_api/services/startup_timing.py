"""Startup sequence timing marks.

Usage::

    from modules.app_api.services.startup_timing import mark, snapshot
    mark("launcher_start")
    ...
    mark("flask_ready")
    print(snapshot())   # {"marks": [...], "total_ms": 1234.5}
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_marks: List[tuple] = []  # [(event, monotonic_ts), ...]
_t0: float = 0.0


def mark(event: str) -> None:
    """Record a named timestamp in the startup sequence."""
    with _lock:
        global _t0
        now = time.monotonic()
        if not _marks:
            _t0 = now
        _marks.append((event, now))
        elapsed = (now - _t0) * 1000
        logger.info("[startup] %s at +%.0fms", event, elapsed)


def snapshot() -> Dict[str, Any]:
    """Return an immutable copy of all marks with durations."""
    with _lock:
        if not _marks:
            return {"marks": [], "total_ms": 0}
        entries = [
            {"event": name, "offset_ms": round((ts - _t0) * 1000, 1)}
            for name, ts in _marks
        ]
        last_ts = _marks[-1][1]
        return {
            "marks": entries,
            "total_ms": round((last_ts - _t0) * 1000, 1),
        }


def reset() -> None:
    """Clear all marks (for testing)."""
    with _lock:
        global _t0
        _marks.clear()
        _t0 = 0.0
