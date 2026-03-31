"""Unit tests for review_store module."""

import os
import tempfile

import pytest
from modules.review_engine.review_store import ReviewStore


@pytest.fixture
def store(tmp_path):
    """Create a ReviewStore backed by a temp SQLite file."""
    db_path = str(tmp_path / "test_review.db")
    return ReviewStore(db_path)


@pytest.fixture
def session_id(store):
    """Create a session and return its ID."""
    return store.create_session(
        project_path="/tmp/proj",
        video_path="/tmp/video.mp4",
        video_type="speech",
        speech_ratio=0.75,
    )


class TestSessions:
    """Test session CRUD."""

    def test_review_store_create_and_get_session(self, store):
        sid = store.create_session("/p", "/v.mp4", "speech", 0.8)
        assert sid  # UUID string
        session = store.get_session(sid)
        assert session is not None
        assert session["project_path"] == "/p"
        assert session["video_path"] == "/v.mp4"
        assert session["video_type"] == "speech"
        assert session["speech_ratio"] == 0.8
        assert session["current_version"] == 1
        assert session["status"] == "active"

    def test_review_store_get_nonexistent_session(self, store):
        assert store.get_session("nonexistent-id") is None


class TestComments:
    """Test comment CRUD and filtering."""

    def test_review_store_add_and_list_comments(self, store, session_id):
        cid = store.add_comment(
            session_id=session_id,
            version=1,
            time_start_ms=1000,
            comment_type="text",
            text="Fix this part",
        )
        assert cid  # UUID string

        comments = store.list_comments(session_id)
        assert len(comments) == 1
        assert comments[0]["text"] == "Fix this part"
        assert comments[0]["time_start_ms"] == 1000
        assert comments[0]["status"] == "pending"

    def test_review_store_filter_comments_by_version(self, store, session_id):
        store.add_comment(session_id, 1, 500, "text", "V1 comment")
        store.add_comment(session_id, 2, 800, "text", "V2 comment")

        v1_comments = store.list_comments(session_id, version=1)
        assert len(v1_comments) == 1
        assert v1_comments[0]["text"] == "V1 comment"

        v2_comments = store.list_comments(session_id, version=2)
        assert len(v2_comments) == 1
        assert v2_comments[0]["text"] == "V2 comment"

    def test_review_store_update_comment_fields(self, store, session_id):
        cid = store.add_comment(session_id, 1, 0, "text", "Original")

        updated = store.update_comment(cid, text="Revised", status="resolved")
        assert updated is True

        comments = store.list_comments(session_id)
        assert comments[0]["text"] == "Revised"
        assert comments[0]["status"] == "resolved"

    def test_review_store_update_rejects_disallowed_fields(self, store, session_id):
        cid = store.add_comment(session_id, 1, 0, "text", "Hello")
        result = store.update_comment(cid, session_id="hacked", version=99)
        assert result is False

    def test_review_store_delete_comment(self, store, session_id):
        cid = store.add_comment(session_id, 1, 0, "text", "To delete")
        assert store.delete_comment(cid) is True
        assert store.list_comments(session_id) == []

    def test_review_store_delete_nonexistent_comment(self, store, session_id):
        assert store.delete_comment("nonexistent-id") is False

    def test_review_store_comments_ordered_by_time(self, store, session_id):
        store.add_comment(session_id, 1, 3000, "text", "Third")
        store.add_comment(session_id, 1, 1000, "text", "First")
        store.add_comment(session_id, 1, 2000, "text", "Second")

        comments = store.list_comments(session_id)
        assert [c["text"] for c in comments] == ["First", "Second", "Third"]

    def test_review_store_comment_with_drawing_data(self, store, session_id):
        cid = store.add_comment(
            session_id, 1, 0, "drawing", "Circle here",
            drawing_data='{"type":"circle","x":100,"y":200}',
        )
        comments = store.list_comments(session_id)
        assert comments[0]["drawing_data"] == '{"type":"circle","x":100,"y":200}'


class TestVersions:
    """Test version management, diff, and rollback."""

    def test_review_store_create_version_auto_increments(self, store, session_id):
        import json
        v1 = store.create_version(session_id, json.dumps([{"type": "keep"}]))
        v2 = store.create_version(session_id, json.dumps([{"type": "cut"}]))
        assert v1 == 1
        assert v2 == 2

    def test_review_store_get_version(self, store, session_id):
        import json
        edits = [{"type": "keep", "start": 0, "end": 5000}]
        store.create_version(session_id, json.dumps(edits))
        ver = store.get_version(session_id, 1)
        assert ver is not None
        assert json.loads(ver["edits_json"]) == edits

    def test_review_store_list_versions(self, store, session_id):
        import json
        store.create_version(session_id, json.dumps([]))
        store.create_version(session_id, json.dumps([{"x": 1}]))
        versions = store.list_versions(session_id)
        assert len(versions) == 2
        assert versions[0]["version_number"] == 1
        assert versions[1]["version_number"] == 2

    def test_review_store_session_current_version_updates(self, store, session_id):
        import json
        store.create_version(session_id, json.dumps([]))
        store.create_version(session_id, json.dumps([]))
        session = store.get_session(session_id)
        assert session["current_version"] == 2

    def test_review_store_diff_versions(self, store, session_id):
        import json
        store.create_version(session_id, json.dumps([
            {"type": "keep", "start": 0},
            {"type": "keep", "start": 5000},
        ]))
        store.create_version(session_id, json.dumps([
            {"type": "keep", "start": 0},
            {"type": "cut", "start": 5000},
            {"type": "keep", "start": 10000},
        ]))

        diff = store.diff_versions(session_id, 1, 2)
        assert len(diff["added"]) == 1      # idx 2 added
        assert len(diff["modified"]) == 1    # idx 1 changed keep→cut
        assert len(diff["removed"]) == 0

    def test_review_store_diff_nonexistent_version(self, store, session_id):
        import json
        store.create_version(session_id, json.dumps([]))
        diff = store.diff_versions(session_id, 1, 99)
        assert "error" in diff

    def test_review_store_rollback_creates_new_version(self, store, session_id):
        import json
        edits_v1 = [{"type": "keep"}]
        store.create_version(session_id, json.dumps(edits_v1))
        store.create_version(session_id, json.dumps([{"type": "cut"}]))

        new_v = store.rollback_to(session_id, 1)
        assert new_v == 3  # new version, not overwrite

        ver3 = store.get_version(session_id, 3)
        assert json.loads(ver3["edits_json"]) == edits_v1
        assert ver3["parent_version"] == 1
        assert "Rollback" in ver3["change_summary"]

    def test_review_store_rollback_nonexistent_raises(self, store, session_id):
        from modules.review_engine.exceptions import ReviewEngineError
        with pytest.raises(ReviewEngineError, match="not found"):
            store.rollback_to(session_id, 99)
