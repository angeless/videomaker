#!/usr/bin/env python3
"""Persistent job state store (SQLite)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
import json
import sqlite3
import threading

from modules.app_api.migrations import SqliteMigration, run_sqlite_migrations


_MIGRATIONS = [
    SqliteMigration(
        version=1,
        name="create_jobs_and_job_events",
        script="""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            kind TEXT,
            progress INTEGER NOT NULL DEFAULT 0,
            queued_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            cancel_requested_at TEXT,
            queue_position INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            meta_json TEXT,
            result_json TEXT,
            log_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_kind ON jobs(kind);
        CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at);

        CREATE TABLE IF NOT EXISTS job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
        CREATE INDEX IF NOT EXISTS idx_job_events_created_at ON job_events(created_at);
        """,
    ),
]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(raw: Any, fallback: Any):
    text = str(raw or "").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception:
        return fallback


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        run_sqlite_migrations(self.db_path, _MIGRATIONS)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _normalize_row(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now()
        progress_raw = payload.get("progress", 0)
        try:
            progress = int(float(progress_raw))
        except Exception:
            progress = 0
        log_items = payload.get("log", [])
        if not isinstance(log_items, list):
            log_items = []
        log_items = [str(item) for item in log_items][-500:]
        return {
            "job_id": str(job_id or "").strip(),
            "status": str(payload.get("status", "queued") or "queued"),
            "kind": str(payload.get("kind", "generic") or "generic"),
            "progress": max(0, min(progress, 100)),
            "queued_at": str(payload.get("queued_at", "") or "") or None,
            "started_at": str(payload.get("started_at", "") or "") or None,
            "finished_at": str(payload.get("finished_at", "") or "") or None,
            "cancel_requested": 1 if bool(payload.get("cancel_requested", False)) else 0,
            "cancel_requested_at": str(payload.get("cancel_requested_at", "") or "") or None,
            "queue_position": max(0, int(payload.get("queue_position", 0) or 0)),
            "error": str(payload.get("error", "") or "") or None,
            "meta_json": _json_dumps(payload.get("meta", {})),
            "result_json": _json_dumps(payload.get("result")),
            "log_json": _json_dumps(log_items),
            "created_at": str(payload.get("created_at", "") or "") or now,
            "updated_at": now,
        }

    @staticmethod
    def _row_to_payload(row: sqlite3.Row) -> Dict[str, Any]:
        payload = {
            "job_id": str(row["job_id"] or ""),
            "status": str(row["status"] or "queued"),
            "kind": str(row["kind"] or "generic"),
            "progress": int(row["progress"] or 0),
            "queued_at": row["queued_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "cancel_requested": bool(int(row["cancel_requested"] or 0)),
            "cancel_requested_at": row["cancel_requested_at"],
            "queue_position": int(row["queue_position"] or 0),
            "error": row["error"],
            "meta": _json_loads(row["meta_json"], {}),
            "result": _json_loads(row["result_json"], None),
            "log": _json_loads(row["log_json"], []),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if not isinstance(payload["meta"], dict):
            payload["meta"] = {}
        if not isinstance(payload["log"], list):
            payload["log"] = []
        return payload

    def upsert_job(self, job_id: str, payload: Dict[str, Any]) -> None:
        row = self._normalize_row(job_id, payload)
        if not row["job_id"]:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(
                    job_id, status, kind, progress, queued_at, started_at, finished_at,
                    cancel_requested, cancel_requested_at, queue_position, error,
                    meta_json, result_json, log_json, created_at, updated_at
                ) VALUES (
                    :job_id, :status, :kind, :progress, :queued_at, :started_at, :finished_at,
                    :cancel_requested, :cancel_requested_at, :queue_position, :error,
                    :meta_json, :result_json, :log_json, :created_at, :updated_at
                )
                ON CONFLICT(job_id) DO UPDATE SET
                    status=excluded.status,
                    kind=excluded.kind,
                    progress=excluded.progress,
                    queued_at=excluded.queued_at,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at,
                    cancel_requested=excluded.cancel_requested,
                    cancel_requested_at=excluded.cancel_requested_at,
                    queue_position=excluded.queue_position,
                    error=excluded.error,
                    meta_json=excluded.meta_json,
                    result_json=excluded.result_json,
                    log_json=excluded.log_json,
                    updated_at=excluded.updated_at
                """,
                row,
            )
            conn.commit()

    def append_event(self, job_id: str, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        jid = str(job_id or "").strip()
        if not jid:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO job_events(job_id, event_type, payload_json, created_at)
                VALUES(?, ?, ?, ?)
                """,
                (
                    jid,
                    str(event_type or "").strip() or "job_update",
                    _json_dumps(payload or {}),
                    _now(),
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        jid = str(job_id or "").strip()
        if not jid:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (jid,)).fetchone()
        return self._row_to_payload(row) if row else None

    def list_jobs(self, limit: int = 600) -> List[Dict[str, Any]]:
        size = max(1, min(int(limit or 600), 2000))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                (size,),
            ).fetchall()
        return [self._row_to_payload(row) for row in rows]
