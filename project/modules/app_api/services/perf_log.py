"""Best-effort performance log backed by SQLite.

All writes are wrapped in try/except — a perf_log failure must **never**
break the main code path.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

_DDL = """\
CREATE TABLE IF NOT EXISTS perf_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation   TEXT    NOT NULL,
    duration_ms REAL    NOT NULL,
    metadata_json TEXT,
    created_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_perf_op   ON perf_log(operation);
CREATE INDEX IF NOT EXISTS idx_perf_time ON perf_log(created_at);
"""


# ── init / close ───────────────────────────────────────────────────────

def init_perf_log(db_path: Path | str) -> None:
    global _conn
    with _lock:
        try:
            _conn = sqlite3.connect(str(db_path), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(_DDL)
        except Exception:
            logger.debug("[perf_log] init failed for %s", db_path, exc_info=True)
            _conn = None


def close() -> None:
    global _conn
    with _lock:
        if _conn:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


# ── write ──────────────────────────────────────────────────────────────

def record(operation: str, duration_ms: float, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Best-effort insert. Never raises."""
    with _lock:
        if _conn is None:
            return
        try:
            _conn.execute(
                "INSERT INTO perf_log (operation, duration_ms, metadata_json) VALUES (?, ?, ?)",
                (
                    operation,
                    round(duration_ms, 1),
                    json.dumps(metadata, ensure_ascii=False) if metadata else None,
                ),
            )
            _conn.commit()
        except Exception:
            pass


# ── read ───────────────────────────────────────────────────────────────

def _quantile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def query_stats(operation: str = "", since: str = "", limit: int = 2000) -> Dict[str, Any]:
    """Aggregate perf stats, grouped by operation."""
    with _lock:
        if _conn is None:
            return {}
        try:
            sql = "SELECT operation, duration_ms FROM perf_log WHERE 1=1"
            params: list = []
            if operation:
                sql += " AND operation = ?"
                params.append(operation)
            if since:
                sql += " AND created_at >= ?"
                params.append(since)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = _conn.execute(sql, params).fetchall()
        except Exception:
            return {}
    if not rows:
        return {}
    groups: Dict[str, List[float]] = {}
    for r in rows:
        groups.setdefault(r["operation"], []).append(float(r["duration_ms"]))
    out: Dict[str, Any] = {}
    for op, vals in groups.items():
        vals.sort()
        out[op] = {
            "count": len(vals),
            "min": round(vals[0], 1),
            "max": round(vals[-1], 1),
            "avg": round(mean(vals), 1),
            "p50": round(_quantile(vals, 0.5), 1),
            "p95": round(_quantile(vals, 0.95), 1),
        }
    return out


def recent(limit: int = 100) -> List[Dict[str, Any]]:
    """Return most recent perf_log entries."""
    with _lock:
        if _conn is None:
            return []
        try:
            rows = _conn.execute(
                "SELECT id, operation, duration_ms, metadata_json, created_at "
                "FROM perf_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:
            return []
    result = []
    for r in rows:
        entry: Dict[str, Any] = {
            "id": r["id"],
            "operation": r["operation"],
            "duration_ms": r["duration_ms"],
            "created_at": r["created_at"],
        }
        if r["metadata_json"]:
            try:
                entry["metadata"] = json.loads(r["metadata_json"])
            except Exception:
                entry["metadata"] = None
        result.append(entry)
    return result
