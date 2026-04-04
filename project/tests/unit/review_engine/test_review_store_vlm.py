"""Tests for ReviewStore VLM migration (v0.17.0 R6)."""

import json
import os
import tempfile

import pytest

from modules.review_engine.review_store import ReviewStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_review.db")
    return ReviewStore(db_path)


@pytest.fixture
def session_id(store):
    """Create a test session and return its ID."""
    sid = store.create_session(
        project_path="/tmp/test",
        video_path="/tmp/test.mp4",
        video_type="speech",
    )
    return sid


class TestMigration:
    def test_new_columns_exist(self, store):
        """visual_context and ai_generated columns should exist after init."""
        import sqlite3
        conn = sqlite3.connect(store._db_path)
        cursor = conn.execute("PRAGMA table_info(review_comments)")
        cols = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert "visual_context" in cols
        assert "ai_generated" in cols

    def test_migration_idempotent(self, store):
        """Running migration twice should not fail."""
        import sqlite3
        conn = sqlite3.connect(store._db_path)
        store._migrate_v17(conn)  # second run
        conn.close()


class TestAddCommentWithContext:
    def test_add_with_visual_context(self, store, session_id):
        vc = json.dumps({"summary": "A tree", "objects": ["tree"]})
        cid = store.add_comment(
            session_id=session_id,
            version=1,
            time_start_ms=1000,
            comment_type="visual",
            text="这棵树太暗了",
            visual_context=vc,
        )
        comments = store.list_comments(session_id)
        found = [c for c in comments if c["comment_id"] == cid]
        assert len(found) == 1
        assert found[0]["visual_context"] == vc

    def test_add_ai_generated_comment(self, store, session_id):
        cid = store.add_comment(
            session_id=session_id,
            version=1,
            time_start_ms=2000,
            comment_type="ai_diagnostic",
            text="[构图] 主体偏右 — AI 诊断",
            ai_generated=True,
        )
        comments = store.list_comments(session_id)
        found = [c for c in comments if c["comment_id"] == cid]
        assert len(found) == 1
        assert found[0]["ai_generated"] == 1


class TestListWithFilter:
    def test_filter_ai_only(self, store, session_id):
        store.add_comment(
            session_id=session_id, version=1, time_start_ms=1000,
            comment_type="note", text="human comment",
        )
        store.add_comment(
            session_id=session_id, version=1, time_start_ms=2000,
            comment_type="ai_diagnostic", text="AI comment",
            ai_generated=True,
        )
        ai_only = store.list_comments(session_id, filter_ai=True)
        human_only = store.list_comments(session_id, filter_ai=False)
        all_comments = store.list_comments(session_id)

        assert len(ai_only) == 1
        assert ai_only[0]["text"] == "AI comment"
        assert len(human_only) == 1
        assert human_only[0]["text"] == "human comment"
        assert len(all_comments) == 2


class TestBackwardCompat:
    def test_old_style_add_still_works(self, store, session_id):
        """add_comment without new params should work (backward compat)."""
        cid = store.add_comment(
            session_id=session_id,
            version=1,
            time_start_ms=500,
            comment_type="note",
            text="old style",
        )
        comments = store.list_comments(session_id)
        found = [c for c in comments if c["comment_id"] == cid]
        assert len(found) == 1
        assert found[0]["visual_context"] is None
        assert found[0]["ai_generated"] == 0
