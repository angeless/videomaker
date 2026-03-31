"""Review store — SQLite persistence for review sessions, comments, versions.

Thread-safe with internal locking. Uses parameterized queries to prevent
SQL injection.
"""

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from modules.review_engine.exceptions import ReviewEngineError

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS review_sessions (
    session_id TEXT PRIMARY KEY,
    project_path TEXT NOT NULL,
    video_path TEXT NOT NULL,
    video_type TEXT NOT NULL,
    speech_ratio REAL,
    current_version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_comments (
    comment_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES review_sessions(session_id),
    version INTEGER NOT NULL,
    time_start_ms INTEGER NOT NULL,
    time_end_ms INTEGER,
    comment_type TEXT NOT NULL,
    text TEXT NOT NULL,
    drawing_data TEXT,
    drawing_thumbnail TEXT,
    status TEXT DEFAULT 'pending',
    ai_reply TEXT,
    resolved_in_version INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES review_sessions(session_id),
    version_number INTEGER NOT NULL,
    edits_json TEXT NOT NULL,
    video_path TEXT,
    render_status TEXT DEFAULT 'pending',
    render_job_id TEXT,
    parent_version INTEGER,
    change_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, version_number)
);

CREATE TABLE IF NOT EXISTS review_artifacts (
    artifact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES review_sessions(session_id),
    version_number INTEGER NOT NULL,
    node_name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    checksum TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, version_number, node_name)
);
"""


class ReviewStore:
    """SQLite store for review sessions, comments, and versions."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.executescript(SCHEMA_SQL)
                conn.commit()
            finally:
                conn.close()

    def _connect(self) -> sqlite3.Connection:
        """Create a new connection with row_factory."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Sessions ──

    def create_session(
        self,
        project_path: str,
        video_path: str,
        video_type: str,
        speech_ratio: float = 0.0,
    ) -> str:
        """Create a new review session.

        Returns:
            session_id (UUID string).
        """
        session_id = str(uuid.uuid4())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO review_sessions
                       (session_id, project_path, video_path, video_type, speech_ratio)
                       VALUES (?, ?, ?, ?, ?)""",
                    (session_id, project_path, video_path, video_type, speech_ratio),
                )
                conn.commit()
            finally:
                conn.close()
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM review_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ── Comments ──

    def add_comment(
        self,
        session_id: str,
        version: int,
        time_start_ms: int,
        comment_type: str,
        text: str,
        time_end_ms: Optional[int] = None,
        drawing_data: Optional[str] = None,
    ) -> str:
        """Add a comment to a session.

        Returns:
            comment_id (UUID string).
        """
        comment_id = str(uuid.uuid4())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO review_comments
                       (comment_id, session_id, version, time_start_ms, time_end_ms,
                        comment_type, text, drawing_data)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (comment_id, session_id, version, time_start_ms, time_end_ms,
                     comment_type, text, drawing_data),
                )
                conn.commit()
            finally:
                conn.close()
        return comment_id

    # Static mapping of updatable columns — prevents SQL injection
    _COMMENT_UPDATE_COLUMNS = {
        "text": "text = ?",
        "comment_type": "comment_type = ?",
        "status": "status = ?",
        "ai_reply": "ai_reply = ?",
        "resolved_in_version": "resolved_in_version = ?",
    }

    def update_comment(self, comment_id: str, **fields) -> bool:
        """Update comment fields.

        Allowed fields: text, comment_type, status, ai_reply, resolved_in_version.
        Returns True if updated.
        """
        fragments = []
        values = []
        for k, v in fields.items():
            sql_frag = self._COMMENT_UPDATE_COLUMNS.get(k)
            if sql_frag:
                fragments.append(sql_frag)
                values.append(v)
        if not fragments:
            return False

        values.append(comment_id)
        sql = f"UPDATE review_comments SET {', '.join(fragments)} WHERE comment_id = ?"

        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(sql, values)
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment. Returns True if deleted."""
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM review_comments WHERE comment_id = ?",
                    (comment_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def list_comments(
        self,
        session_id: str,
        version: Optional[int] = None,
    ) -> List[Dict]:
        """List comments for a session, optionally filtered by version."""
        conn = self._connect()
        try:
            if version is not None:
                rows = conn.execute(
                    """SELECT * FROM review_comments
                       WHERE session_id = ? AND version = ?
                       ORDER BY time_start_ms""",
                    (session_id, version),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM review_comments
                       WHERE session_id = ?
                       ORDER BY time_start_ms""",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Versions ──

    def create_version(
        self,
        session_id: str,
        edits_json: str,
        video_path: Optional[str] = None,
        parent_version: Optional[int] = None,
        change_summary: Optional[str] = None,
    ) -> int:
        """Create a new version. Returns the version_number."""
        with self._lock:
            conn = self._connect()
            try:
                # Get next version number
                row = conn.execute(
                    """SELECT COALESCE(MAX(version_number), 0) + 1 as next_v
                       FROM review_versions WHERE session_id = ?""",
                    (session_id,),
                ).fetchone()
                version_number = row["next_v"]

                conn.execute(
                    """INSERT INTO review_versions
                       (session_id, version_number, edits_json, video_path,
                        parent_version, change_summary)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (session_id, version_number, edits_json, video_path,
                     parent_version, change_summary),
                )

                # Update session's current version
                conn.execute(
                    """UPDATE review_sessions SET current_version = ?, updated_at = ?
                       WHERE session_id = ?""",
                    (version_number, datetime.now(timezone.utc).isoformat(), session_id),
                )
                conn.commit()
                return version_number
            finally:
                conn.close()

    def get_version(self, session_id: str, version_number: int) -> Optional[Dict]:
        """Get a specific version."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT * FROM review_versions
                   WHERE session_id = ? AND version_number = ?""",
                (session_id, version_number),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_versions(self, session_id: str) -> List[Dict]:
        """List all versions for a session."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM review_versions
                   WHERE session_id = ? ORDER BY version_number""",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def diff_versions(
        self, session_id: str, v1: int, v2: int,
    ) -> Dict:
        """Compute diff between two versions.

        Returns dict with added/removed/modified segments.
        """
        ver1 = self.get_version(session_id, v1)
        ver2 = self.get_version(session_id, v2)

        if not ver1 or not ver2:
            return {"error": "version not found"}

        edits1 = json.loads(ver1["edits_json"])
        edits2 = json.loads(ver2["edits_json"])

        # Simple diff: compare by index
        added = []
        removed = []
        modified = []

        max_len = max(len(edits1), len(edits2))
        for i in range(max_len):
            if i >= len(edits1):
                added.append({"idx": i, "segment": edits2[i]})
            elif i >= len(edits2):
                removed.append({"idx": i, "segment": edits1[i]})
            elif edits1[i] != edits2[i]:
                modified.append({"idx": i, "old": edits1[i], "new": edits2[i]})

        return {"added": added, "removed": removed, "modified": modified}

    def rollback_to(self, session_id: str, version_number: int) -> int:
        """Rollback by creating a new version with the old version's edits.

        Does NOT delete history — creates a new version that copies
        the target version's edits.

        Returns:
            New version number.
        """
        target = self.get_version(session_id, version_number)
        if not target:
            raise ReviewEngineError(f"Version {version_number} not found for session {session_id}")

        return self.create_version(
            session_id=session_id,
            edits_json=target["edits_json"],
            parent_version=version_number,
            change_summary=f"Rollback to v{version_number}",
        )
