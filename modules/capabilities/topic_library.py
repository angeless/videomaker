"""Topic library capability backed by SQLite."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import sqlite3


@dataclass
class TopicTemplate:
    """A reusable topic blueprint."""

    slug: str
    title: str
    category: str = "travel"
    audience: str = "general"
    hook_style: str = "story"
    outline_template: str = ""
    tags: List[str] = field(default_factory=list)
    enabled: bool = True


def init_topic_db(db_path: str) -> None:
    """Initialize topic library tables if missing."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topic_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                audience TEXT NOT NULL,
                hook_style TEXT NOT NULL,
                outline_template TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_topic_templates_category "
            "ON topic_templates(category)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_topic_templates_enabled "
            "ON topic_templates(enabled)"
        )
        conn.commit()


def upsert_topic(db_path: str, topic: TopicTemplate) -> None:
    """Insert or update a topic template by slug."""
    init_topic_db(db_path)
    tags_value = ",".join(sorted({t.strip().lower() for t in topic.tags if t and t.strip()}))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO topic_templates (
                slug, title, category, audience, hook_style,
                outline_template, tags, enabled, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(slug) DO UPDATE SET
                title=excluded.title,
                category=excluded.category,
                audience=excluded.audience,
                hook_style=excluded.hook_style,
                outline_template=excluded.outline_template,
                tags=excluded.tags,
                enabled=excluded.enabled,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                topic.slug,
                topic.title,
                topic.category,
                topic.audience,
                topic.hook_style,
                topic.outline_template,
                tags_value,
                1 if topic.enabled else 0,
            ),
        )
        conn.commit()


def list_topics(
    db_path: str,
    enabled_only: bool = True,
    limit: int = 100,
) -> List[Dict]:
    """List topic templates ordered by last update."""
    init_topic_db(db_path)
    where = "WHERE enabled = 1" if enabled_only else ""
    sql = (
        "SELECT slug, title, category, audience, hook_style, outline_template, tags, enabled, updated_at "
        f"FROM topic_templates {where} ORDER BY updated_at DESC LIMIT ?"
    )
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(sql, (max(int(limit), 1),))
        rows = cur.fetchall()
    return [_row_to_topic_dict(row) for row in rows]


def get_topic(db_path: str, slug: str) -> Optional[Dict]:
    """Get one topic template by slug."""
    init_topic_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT slug, title, category, audience, hook_style, outline_template, tags, enabled, updated_at
            FROM topic_templates
            WHERE slug = ?
            """,
            (slug,),
        )
        row = cur.fetchone()
    return _row_to_topic_dict(row) if row else None


def search_topics(
    db_path: str,
    query: str = "",
    category: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
    limit: int = 20,
) -> List[Dict]:
    """Search topic templates by text and optional filters."""
    init_topic_db(db_path)
    clauses = []
    params: List = []

    if query:
        q = f"%{query.strip().lower()}%"
        clauses.append("(lower(title) LIKE ? OR lower(outline_template) LIKE ? OR lower(tags) LIKE ?)")
        params.extend([q, q, q])
    if category:
        clauses.append("category = ?")
        params.append(category)
    if tags:
        for tag in {t.strip().lower() for t in tags if t and t.strip()}:
            clauses.append("lower(tags) LIKE ?")
            params.append(f"%{tag}%")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT slug, title, category, audience, hook_style, outline_template, tags, enabled, updated_at "
        f"FROM topic_templates {where} "
        "ORDER BY updated_at DESC LIMIT ?"
    )
    params.append(max(int(limit), 1))

    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_topic_dict(row) for row in rows]


def _row_to_topic_dict(row: sqlite3.Row) -> Dict:
    slug, title, category, audience, hook_style, outline_template, tags, enabled, updated_at = row
    tag_list = [t for t in (tags or "").split(",") if t]
    return {
        "slug": slug,
        "title": title,
        "category": category,
        "audience": audience,
        "hook_style": hook_style,
        "outline_template": outline_template,
        "tags": tag_list,
        "enabled": bool(enabled),
        "updated_at": updated_at,
    }
