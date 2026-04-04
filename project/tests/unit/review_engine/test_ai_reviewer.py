"""Tests for AI reviewer — diagnostic→comment generation (v0.17.0 R14)."""

import json
import pytest

from modules.review_engine.vlm_analyzer import VLMAnalyzer
from modules.review_engine.frame_diagnostics import DiagnosticIssue
from modules.review_engine.review_store import ReviewStore


@pytest.fixture
def store(tmp_path):
    return ReviewStore(str(tmp_path / "test.db"))


@pytest.fixture
def session_id(store):
    return store.create_session(
        project_path="/tmp/test",
        video_path="/tmp/test.mp4",
        video_type="speech",
    )


class TestCreatesDiagnosticComment:
    def test_creates_comment_from_issue(self, store, session_id):
        issues = [
            DiagnosticIssue(
                issue_type="composition",
                severity="warning",
                description="主体偏右，建议使用三分构图",
                suggestion="向左移动主体",
                scene_idx=0,
            )
        ]
        VLMAnalyzer.generate_ai_review(store, session_id, version=1, diagnostics=issues)

        comments = store.list_comments(session_id, filter_ai=True)
        assert len(comments) == 1
        assert "构图" in comments[0]["text"]
        assert comments[0]["ai_generated"] == 1
        assert comments[0]["comment_type"] == "ai_diagnostic"

    def test_correct_time_range(self, store, session_id):
        issues = [
            DiagnosticIssue(
                issue_type="exposure",
                severity="info",
                description="轻微过曝",
                scene_idx=2,
            )
        ]
        VLMAnalyzer.generate_ai_review(
            store, session_id, version=1, diagnostics=issues,
            scene_times={2: (5000, 8000)},
        )
        comments = store.list_comments(session_id, filter_ai=True)
        assert len(comments) == 1
        assert comments[0]["time_start_ms"] == 5000
        assert comments[0]["time_end_ms"] == 8000

    def test_idempotent(self, store, session_id):
        issues = [
            DiagnosticIssue(
                issue_type="exposure",
                severity="warning",
                description="过曝",
            )
        ]
        VLMAnalyzer.generate_ai_review(store, session_id, version=1, diagnostics=issues)
        VLMAnalyzer.generate_ai_review(store, session_id, version=1, diagnostics=issues)

        comments = store.list_comments(session_id, filter_ai=True)
        assert len(comments) == 1  # Should not duplicate

    def test_severity_mapping(self, store, session_id):
        issues = [
            DiagnosticIssue(issue_type="x", severity="info", description="mild"),
            DiagnosticIssue(issue_type="y", severity="warning", description="medium"),
            DiagnosticIssue(issue_type="z", severity="error", description="bad"),
        ]
        VLMAnalyzer.generate_ai_review(store, session_id, version=1, diagnostics=issues)
        comments = store.list_comments(session_id, filter_ai=True)
        statuses = {c["text"].split("]")[0].strip("[") + ":" + c["status"] for c in comments}
        # At least 3 comments created
        assert len(comments) == 3
