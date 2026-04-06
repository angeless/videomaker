"""TimelineStore — SQLite persistence for multi-track timelines (C1).

Reuses the same SQLite database as ReviewStore (same db_path).
Uses WAL journal mode for concurrent read/write safety (audit H2).
"""

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from modules.review_engine.contracts import Clip, Timeline, TimelineTrack

logger = logging.getLogger(__name__)

_TIMELINE_DDL = """
CREATE TABLE IF NOT EXISTS timeline_tracks (
    track_id TEXT PRIMARY KEY,
    timeline_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    track_type TEXT NOT NULL,
    label TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    muted INTEGER DEFAULT 0,
    locked INTEGER DEFAULT 0,
    volume REAL DEFAULT 1.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_clips (
    clip_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    source_path TEXT DEFAULT '',
    source_in_ms INTEGER DEFAULT 0,
    source_out_ms INTEGER DEFAULT 0,
    label TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (track_id) REFERENCES timeline_tracks(track_id)
);
"""


class TimelineStore:
    """SQLite store for multi-track timelines.

    Shares the same db file as ReviewStore. Call with the same db_path.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(_TIMELINE_DDL)
                conn.commit()
            finally:
                conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ── Timeline CRUD ────────────────────────────────────────────

    def create_timeline(self, session_id: str) -> str:
        """Create a new timeline for a session. Returns timeline_id."""
        timeline_id = uuid.uuid4().hex[:16]
        logger.info("Created timeline %s for session %s", timeline_id, session_id)
        return timeline_id

    def get_timeline(self, session_id: str) -> Optional[Timeline]:
        """Load full timeline (tracks + clips) for a session."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM timeline_tracks WHERE session_id = ? ORDER BY sort_order",
                (session_id,),
            ).fetchall()
            if not rows:
                return None

            timeline_id = rows[0]["timeline_id"]
            tracks = []
            for r in rows:
                clips = self._get_clips_for_track(conn, r["track_id"])
                tracks.append(TimelineTrack(
                    track_id=r["track_id"],
                    timeline_id=r["timeline_id"],
                    session_id=r["session_id"],
                    track_type=r["track_type"],
                    label=r["label"],
                    sort_order=r["sort_order"],
                    muted=bool(r["muted"]),
                    locked=bool(r["locked"]),
                    volume=r["volume"],
                    clips=clips,
                ))

            duration_ms = 0
            for t in tracks:
                for c in t.clips:
                    if c.end_ms > duration_ms:
                        duration_ms = c.end_ms

            return Timeline(
                timeline_id=timeline_id,
                session_id=session_id,
                tracks=tracks,
                duration_ms=duration_ms,
            )
        finally:
            conn.close()

    def delete_timeline(self, session_id: str) -> int:
        """Delete all tracks and clips for a session. Returns tracks removed."""
        conn = self._connect()
        try:
            track_ids = [
                r["track_id"] for r in
                conn.execute(
                    "SELECT track_id FROM timeline_tracks WHERE session_id = ?",
                    (session_id,),
                ).fetchall()
            ]
            for tid in track_ids:
                conn.execute("DELETE FROM timeline_clips WHERE track_id = ?", (tid,))
            conn.execute("DELETE FROM timeline_tracks WHERE session_id = ?", (session_id,))
            conn.commit()
            return len(track_ids)
        finally:
            conn.close()

    # ── Track CRUD ───────────────────────────────────────────────

    def add_track(
        self,
        timeline_id: str,
        session_id: str,
        track_type: str,
        label: str = "",
        sort_order: int = 0,
    ) -> str:
        """Add a track. Returns track_id."""
        track_id = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO timeline_tracks "
                "(track_id, timeline_id, session_id, track_type, label, sort_order, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (track_id, timeline_id, session_id, track_type, label, sort_order, now),
            )
            conn.commit()
            return track_id
        finally:
            conn.close()

    def get_tracks(self, session_id: str) -> List[TimelineTrack]:
        """Get all tracks for a session."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM timeline_tracks WHERE session_id = ? ORDER BY sort_order",
                (session_id,),
            ).fetchall()
            return [self._row_to_track(conn, r) for r in rows]
        finally:
            conn.close()

    def update_track(self, track_id: str, **kwargs) -> bool:
        """Update track fields (label, sort_order, muted, locked, volume)."""
        allowed = {"label", "sort_order", "muted", "locked", "volume"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        # Convert booleans to int for SQLite
        for k in ("muted", "locked"):
            if k in updates:
                updates[k] = int(updates[k])

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [track_id]

        conn = self._connect()
        try:
            conn.execute(f"UPDATE timeline_tracks SET {set_clause} WHERE track_id = ?", values)
            conn.commit()
            return True
        finally:
            conn.close()

    def remove_track(self, track_id: str) -> bool:
        """Remove a track and all its clips."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM timeline_clips WHERE track_id = ?", (track_id,))
            cursor = conn.execute("DELETE FROM timeline_tracks WHERE track_id = ?", (track_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Clip CRUD ────────────────────────────────────────────────

    def add_clip(
        self,
        track_id: str,
        start_ms: int,
        end_ms: int,
        source_path: str = "",
        source_in_ms: int = 0,
        source_out_ms: int = 0,
        label: str = "",
        metadata: Optional[Dict] = None,
    ) -> str:
        """Add a clip to a track. Returns clip_id."""
        clip_id = uuid.uuid4().hex[:16]
        meta_json = json.dumps(metadata or {})
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO timeline_clips "
                "(clip_id, track_id, start_ms, end_ms, source_path, source_in_ms, source_out_ms, label, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (clip_id, track_id, start_ms, end_ms, source_path, source_in_ms, source_out_ms, label, meta_json),
            )
            conn.commit()
            return clip_id
        finally:
            conn.close()

    def get_clips(self, track_id: str) -> List[Clip]:
        """Get all clips for a track."""
        conn = self._connect()
        try:
            return self._get_clips_for_track(conn, track_id)
        finally:
            conn.close()

    def update_clip(self, clip_id: str, **kwargs) -> bool:
        """Update clip fields."""
        allowed = {"start_ms", "end_ms", "source_path", "source_in_ms", "source_out_ms", "label", "track_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [clip_id]

        conn = self._connect()
        try:
            conn.execute(f"UPDATE timeline_clips SET {set_clause} WHERE clip_id = ?", values)
            conn.commit()
            return True
        finally:
            conn.close()

    def remove_clip(self, clip_id: str) -> bool:
        """Remove a clip."""
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM timeline_clips WHERE clip_id = ?", (clip_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Internal ─────────────────────────────────────────────────

    def _get_clips_for_track(self, conn: sqlite3.Connection, track_id: str) -> List[Clip]:
        rows = conn.execute(
            "SELECT * FROM timeline_clips WHERE track_id = ? ORDER BY start_ms",
            (track_id,),
        ).fetchall()
        return [
            Clip(
                clip_id=r["clip_id"],
                track_id=r["track_id"],
                start_ms=r["start_ms"],
                end_ms=r["end_ms"],
                source_path=r["source_path"],
                source_in_ms=r["source_in_ms"],
                source_out_ms=r["source_out_ms"],
                label=r["label"],
                metadata=json.loads(r["metadata"] or "{}"),
            )
            for r in rows
        ]

    def _row_to_track(self, conn: sqlite3.Connection, r) -> TimelineTrack:
        clips = self._get_clips_for_track(conn, r["track_id"])
        return TimelineTrack(
            track_id=r["track_id"],
            timeline_id=r["timeline_id"],
            session_id=r["session_id"],
            track_type=r["track_type"],
            label=r["label"],
            sort_order=r["sort_order"],
            muted=bool(r["muted"]),
            locked=bool(r["locked"]),
            volume=r["volume"],
            clips=clips,
        )
