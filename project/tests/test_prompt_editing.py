"""Tests for R8 prompt editing engine."""

from __future__ import annotations

import json

import pytest

from modules.prompt_editing.parser import parse_edit_command, EditCommand
from modules.prompt_editing.executor import execute_edit_command


SAMPLE_CLIPS = [
    {"clip_index": 1, "video_id": "v1", "source_start": 0, "source_end": 5, "duration": 5, "has_face": False},
    {"clip_index": 2, "video_id": "v2", "source_start": 2, "source_end": 8, "duration": 6, "has_face": True},
    {"clip_index": 3, "video_id": "v3", "source_start": 0, "source_end": 4, "duration": 4, "has_face": False},
]


class TestParser:
    def test_parse_delete_zh(self):
        cmd = parse_edit_command("删除第2个片段")
        assert cmd.action == "delete"
        assert 2 in cmd.targets

    def test_parse_delete_en(self):
        cmd = parse_edit_command("remove clip 3")
        assert cmd.action == "delete"
        assert 3 in cmd.targets

    def test_parse_trim_with_duration(self):
        cmd = parse_edit_command("把第1个片段缩短到3秒")
        assert cmd.action == "trim"
        assert 1 in cmd.targets
        assert cmd.params.get("duration") == 3.0

    def test_parse_reverse(self):
        cmd = parse_edit_command("倒序排列")
        assert cmd.action == "reverse"

    def test_parse_speed(self):
        cmd = parse_edit_command("加速第2个片段到2x")
        assert cmd.action == "speed"
        assert 2 in cmd.targets
        assert cmd.params.get("speed") == 2.0

    def test_parse_move(self):
        cmd = parse_edit_command("把第1个移到第3个后面")
        assert cmd.action == "reorder"
        assert 1 in cmd.targets
        assert 3 in cmd.targets

    def test_parse_unknown(self):
        cmd = parse_edit_command("hello world")
        assert not cmd.valid

    def test_parse_empty(self):
        cmd = parse_edit_command("")
        assert not cmd.valid

    def test_parse_last_clip(self):
        cmd = parse_edit_command("删除最后一个")
        assert cmd.action == "delete"
        assert -1 in cmd.targets


class TestExecutor:
    def test_delete_clip(self):
        new_clips, summary = execute_edit_command(
            SAMPLE_CLIPS,
            EditCommand(action="delete", targets=[2]),
        )
        assert len(new_clips) == 2
        assert summary["deleted"] == 1
        assert all(c["clip_index"] == i + 1 for i, c in enumerate(new_clips))

    def test_reverse(self):
        new_clips, summary = execute_edit_command(
            SAMPLE_CLIPS,
            EditCommand(action="reverse"),
        )
        assert new_clips[0]["video_id"] == "v3"
        assert new_clips[2]["video_id"] == "v1"

    def test_trim_with_duration(self):
        new_clips, summary = execute_edit_command(
            SAMPLE_CLIPS,
            EditCommand(action="trim", targets=[1], params={"duration": 3.0}),
        )
        assert new_clips[0]["duration"] == 3.0
        assert summary["trimmed"] == 1

    def test_trim_default_30pct(self):
        new_clips, summary = execute_edit_command(
            SAMPLE_CLIPS,
            EditCommand(action="trim", targets=[2]),
        )
        # 6 * 0.7 = 4.2
        assert abs(new_clips[1]["duration"] - 4.2) < 0.01

    def test_speed_up(self):
        new_clips, summary = execute_edit_command(
            SAMPLE_CLIPS,
            EditCommand(action="speed", targets=[1], params={"speed": 2.0}),
        )
        assert new_clips[0]["duration"] == 2.5  # 5 / 2
        assert new_clips[0]["speed"] == 2.0

    def test_reorder_swap(self):
        new_clips, summary = execute_edit_command(
            SAMPLE_CLIPS,
            EditCommand(action="reorder", targets=[1, 3]),
        )
        assert new_clips[0]["video_id"] == "v2"

    def test_invalid_command(self):
        new_clips, summary = execute_edit_command(
            SAMPLE_CLIPS,
            EditCommand(action=""),
        )
        assert "error" in summary

    def test_delete_last(self):
        new_clips, summary = execute_edit_command(
            SAMPLE_CLIPS,
            EditCommand(action="delete", targets=[-1]),
        )
        assert len(new_clips) == 2
        assert new_clips[-1]["video_id"] == "v2"
