"""Best-effort security audit log backed by SQLite.

Records sensitive operations (delete, publish, config change, batch tasks, etc.)
with structured fields: who, when, what object, what operation, result.

All writes are wrapped in try/except — an audit_log failure must **never**
break the main code path.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

_DDL = """\
CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operation     TEXT    NOT NULL,
    resource_type TEXT    NOT NULL,
    resource_id   TEXT,
    actor         TEXT,
    status        TEXT    NOT NULL DEFAULT 'ok',
    detail_json   TEXT,
    created_at    TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_op    ON audit_log(operation);
CREATE INDEX IF NOT EXISTS idx_audit_res   ON audit_log(resource_type);
CREATE INDEX IF NOT EXISTS idx_audit_time  ON audit_log(created_at);
"""


# ── init / close ───────────────────────────────────────────────────────

def init_audit_log(db_path: Path | str) -> None:
    global _conn
    with _lock:
        try:
            _conn = sqlite3.connect(str(db_path), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(_DDL)
        except Exception:
            logger.debug("[audit_log] init failed for %s", db_path, exc_info=True)
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

def audit(
    operation: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    *,
    actor: str = "unknown",
    status: str = "ok",
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort insert. Never raises."""
    with _lock:
        if _conn is None:
            return
        try:
            _conn.execute(
                "INSERT INTO audit_log "
                "(operation, resource_type, resource_id, actor, status, detail_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    operation,
                    resource_type,
                    str(resource_id) if resource_id is not None else None,
                    actor or "unknown",
                    status,
                    json.dumps(detail, ensure_ascii=False) if detail else None,
                ),
            )
            _conn.commit()
        except Exception:
            logger.debug("[audit_log] write failed", exc_info=True)


# ── read ───────────────────────────────────────────────────────────────

def query(
    *,
    operation: str = "",
    resource_type: str = "",
    actor: str = "",
    since: str = "",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Query recent audit log entries with optional filters."""
    with _lock:
        if _conn is None:
            return []
        try:
            sql = "SELECT * FROM audit_log WHERE 1=1"
            params: list = []
            if operation:
                sql += " AND operation = ?"
                params.append(operation)
            if resource_type:
                sql += " AND resource_type = ?"
                params.append(resource_type)
            if actor:
                sql += " AND actor LIKE ?"
                params.append(f"%{actor}%")
            if since:
                sql += " AND created_at >= ?"
                params.append(since)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(min(limit, 1000))
            rows = _conn.execute(sql, params).fetchall()
        except Exception:
            return []
    result = []
    for r in rows:
        entry: Dict[str, Any] = {
            "id": r["id"],
            "operation": r["operation"],
            "resource_type": r["resource_type"],
            "resource_id": r["resource_id"],
            "actor": r["actor"],
            "status": r["status"],
            "created_at": r["created_at"],
        }
        if r["detail_json"]:
            try:
                entry["detail"] = json.loads(r["detail_json"])
            except Exception:
                entry["detail"] = None
        result.append(entry)
    return result


def count(*, since: str = "") -> int:
    """Total audit entries, optionally since a datetime."""
    with _lock:
        if _conn is None:
            return 0
        try:
            sql = "SELECT COUNT(*) FROM audit_log"
            params: list = []
            if since:
                sql += " WHERE created_at >= ?"
                params.append(since)
            row = _conn.execute(sql, params).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0
