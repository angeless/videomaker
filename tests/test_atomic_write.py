"""Tests for _atomic_write_text in workflow_engine/workflow.py."""

import os
import json
import tempfile
from pathlib import Path

import pytest

from modules.workflow_engine.workflow import _atomic_write_text


class TestAtomicWriteText:
    """Verify write-to-temp + os.replace semantics."""

    def test_basic_write(self, tmp_path):
        target = tmp_path / "test.json"
        _atomic_write_text(target, '{"a": 1}')
        assert target.read_text(encoding="utf-8") == '{"a": 1}'

    def test_overwrite_existing(self, tmp_path):
        target = tmp_path / "test.json"
        target.write_text("old content")
        _atomic_write_text(target, "new content")
        assert target.read_text() == "new content"

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "deep" / "file.txt"
        _atomic_write_text(target, "hello")
        assert target.read_text() == "hello"

    def test_unicode_content(self, tmp_path):
        target = tmp_path / "unicode.json"
        content = json.dumps({"标题": "测试中文", "emoji": "🎬"}, ensure_ascii=False)
        _atomic_write_text(target, content)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["标题"] == "测试中文"
        assert loaded["emoji"] == "🎬"

    def test_no_tmp_file_left_on_success(self, tmp_path):
        target = tmp_path / "clean.txt"
        _atomic_write_text(target, "data")
        tmp_files = [f for f in tmp_path.iterdir() if f.suffix == ".tmp"]
        assert tmp_files == []

    def test_no_tmp_file_left_on_error(self, tmp_path):
        target = tmp_path / "fail.txt"
        # Simulate write failure by passing non-string content
        with pytest.raises(TypeError):
            _atomic_write_text(target, 12345)  # int, not str
        tmp_files = [f for f in tmp_path.iterdir() if f.suffix == ".tmp"]
        assert tmp_files == []
        assert not target.exists()

    def test_original_preserved_on_error(self, tmp_path):
        target = tmp_path / "preserve.txt"
        target.write_text("original")
        with pytest.raises(TypeError):
            _atomic_write_text(target, 99999)
        assert target.read_text() == "original"

    def test_accepts_path_string(self, tmp_path):
        target = str(tmp_path / "str_path.txt")
        _atomic_write_text(target, "works with str")
        assert Path(target).read_text() == "works with str"

    def test_large_json(self, tmp_path):
        target = tmp_path / "large.json"
        data = {"items": [{"id": i, "value": f"item_{i}"} for i in range(10000)]}
        content = json.dumps(data, ensure_ascii=False, indent=2)
        _atomic_write_text(target, content)
        loaded = json.loads(target.read_text())
        assert len(loaded["items"]) == 10000
