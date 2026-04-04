"""Tests for CommentExporter — R21."""

import json
import pytest

from modules.review_engine.comment_exporter import export_comments
from modules.review_engine.exceptions import ReviewEngineError


SAMPLE_COMMENTS = [
    {"time_start_ms": 5000, "type": "cut", "text": "删掉这段", "status": "pending", "ai_reply": "已删除"},
    {"time_start_ms": 12000, "time_end_ms": 15000, "type": "pacing", "text": "太慢了", "status": "resolved", "ai_reply": ""},
]


class TestCommentExporter:

    def test_json_export(self):
        result = export_comments(SAMPLE_COMMENTS, "json")
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["text"] == "删掉这段"

    def test_csv_export(self):
        result = export_comments(SAMPLE_COMMENTS, "csv")
        lines = result.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "timecode" in lines[0]

    def test_edl_export(self):
        result = export_comments(SAMPLE_COMMENTS, "edl")
        assert "TITLE: Review Comments" in result
        assert "COMMENT:" in result

    def test_unsupported_format(self):
        with pytest.raises(ReviewEngineError, match="Unsupported"):
            export_comments(SAMPLE_COMMENTS, "pdf")
