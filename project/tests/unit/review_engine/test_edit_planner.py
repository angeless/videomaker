"""Tests for EditPlanner — R5 + R6."""

import pytest

from modules.review_engine.contracts import EditInstruction, Segment
from modules.review_engine.edit_planner import (
    apply_instructions,
    detect_conflicts,
    EditPlan,
)


def _seg(start, end, path="video.mp4"):
    return Segment(source_path=path, start_ms=start, end_ms=end)


def _inst(itype, idx=None, **params):
    return EditInstruction(instruction_type=itype, segment_idx=idx, params=params)


# ── R5: apply_instructions ──

class TestApplyInstructions:

    def test_extend(self):
        edits = [_seg(0, 5000), _seg(5000, 10000), _seg(10000, 15000)]
        result = apply_instructions([_inst("extend", idx=1, duration_ms=2000)], edits)
        # Segment 1 should be extended by 1000ms on each side
        assert result.new_edits[1].start_ms == 4000
        assert result.new_edits[1].end_ms == 11000
        assert len(result.diff) == 1
        assert result.diff[0].action == "modified"
        assert "扩展" in result.summary_text

    def test_remove(self):
        edits = [_seg(0, 5000), _seg(5000, 10000), _seg(10000, 15000)]
        result = apply_instructions([_inst("remove", idx=1)], edits)
        assert len(result.new_edits) == 2
        assert result.new_edits[0].end_ms == 5000
        assert result.new_edits[1].start_ms == 10000
        assert result.diff[0].action == "removed"
        assert "删除" in result.summary_text

    def test_insert(self):
        edits = [_seg(0, 5000), _seg(10000, 15000)]
        result = apply_instructions(
            [_inst("insert", source_start_ms=5000, source_end_ms=8000, position=1)],
            edits,
        )
        assert len(result.new_edits) == 3
        assert result.new_edits[1].start_ms == 5000
        assert result.new_edits[1].end_ms == 8000
        assert result.new_edits[1].segment_type == "inserted"
        assert "插入" in result.summary_text

    def test_reorder(self):
        edits = [_seg(0, 3000), _seg(3000, 6000), _seg(6000, 9000)]
        result = apply_instructions([_inst("reorder", idx=2, target_idx=0)], edits)
        assert result.new_edits[0].start_ms == 6000
        assert result.new_edits[1].start_ms == 0

    def test_diff_format(self):
        edits = [_seg(0, 5000), _seg(5000, 10000)]
        result = apply_instructions([_inst("remove", idx=0)], edits)
        assert len(result.diff) == 1
        d = result.diff[0]
        assert d.action == "removed"
        assert d.idx == 0
        assert d.segment is not None
        assert "source_path" in d.segment

    def test_no_instructions(self):
        edits = [_seg(0, 5000)]
        result = apply_instructions([], edits)
        assert len(result.new_edits) == 1
        assert result.summary_text == "无变更"

    def test_trim(self):
        edits = [_seg(0, 10000)]
        result = apply_instructions(
            [_inst("trim", idx=0, trim_start_ms=1000, trim_end_ms=2000)],
            edits,
        )
        assert result.new_edits[0].start_ms == 1000
        assert result.new_edits[0].end_ms == 8000

    def test_speed(self):
        edits = [_seg(0, 5000)]
        result = apply_instructions([_inst("speed", idx=0, factor=2.0)], edits)
        assert result.new_edits[0].label == "speed:2.0"


# ── R6: detect_conflicts ──

class TestDetectConflicts:

    def test_conflict_remove_extend(self):
        insts = [
            _inst("remove", idx=2),
            _inst("extend", idx=2, duration_ms=1000),
        ]
        conflicts, resolved = detect_conflicts(insts)
        assert len(conflicts) == 1
        assert conflicts[0]["segment_idx"] == 2

    def test_mergeable_trim_speed(self):
        insts = [
            _inst("trim", idx=1, trim_start_ms=500),
            _inst("speed", idx=1, factor=1.5),
        ]
        conflicts, resolved = detect_conflicts(insts)
        assert len(conflicts) == 0
        assert len(resolved) == 2

    def test_no_conflict_different_segments(self):
        insts = [
            _inst("remove", idx=1),
            _inst("extend", idx=3),
        ]
        conflicts, resolved = detect_conflicts(insts)
        assert len(conflicts) == 0
        assert len(resolved) == 2
