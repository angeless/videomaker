#!/usr/bin/env python3
"""Lightweight SQLite migration runner for local app state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Dict, Any, List
import sqlite3


@dataclass(frozen=True)
class SqliteMigration:
    version: int
    name: str
    script: str


def run_sqlite_migrations(db_path: Path, migrations: Iterable[SqliteMigration]) -> Dict[str, Any]:
    """Apply ordered SQL migrations to a SQLite database exactly once."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered: List[SqliteMigration] = sorted(list(migrations), key=lambda item: int(item.version))

    with sqlite3.connect(str(path), timeout=30.0) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        applied_versions = {int(row[0]) for row in rows}

        applied_now: List[int] = []
        for migration in ordered:
            version = int(migration.version)
            if version in applied_versions:
                continue
            conn.executescript(migration.script)
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES(?, ?, ?)",
                (version, str(migration.name), datetime.now().isoformat(timespec="seconds")),
            )
            applied_now.append(version)

        conn.commit()

    return {
        "db_path": str(path),
        "applied_now": applied_now,
        "latest_version": int(ordered[-1].version) if ordered else 0,
    }
