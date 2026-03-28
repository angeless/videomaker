"""Tests for cross-review audit fixes: path safety, key sanitization, WAL corruption."""

from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ------------------------------------------------------------------
# _is_safe_export_path
# ------------------------------------------------------------------

from modules.app_api.routes.capability_editing_routes import _is_safe_export_path


class TestSafeExportPath:
    def test_desktop_allowed(self):
        p = str(Path.home() / "Desktop" / "exports")
        assert _is_safe_export_path(p) is True

    def test_downloads_allowed(self):
        p = str(Path.home() / "Downloads" / "test")
        assert _is_safe_export_path(p) is True

    def test_documents_allowed(self):
        p = str(Path.home() / "Documents" / "out")
        assert _is_safe_export_path(p) is True

    def test_tmp_allowed(self):
        p = str(Path("/tmp/videoeditor_export").resolve())
        assert _is_safe_export_path(p) is True

    def test_etc_rejected(self):
        assert _is_safe_export_path("/etc/evil") is False

    def test_root_rejected(self):
        assert _is_safe_export_path("/") is False

    def test_system_path_rejected(self):
        assert _is_safe_export_path("/usr/local/bin") is False

    def test_home_root_rejected(self):
        assert _is_safe_export_path(str(Path.home())) is False

    def test_traversal_rejected(self):
        p = str(Path(str(Path.home() / "Desktop" / ".." / ".." / "etc")).resolve())
        assert _is_safe_export_path(p) is False

    def test_prefix_collision_rejected(self):
        """Desktop-evil should NOT match Desktop prefix."""
        p = str(Path.home() / "Desktop-evil" / "malware")
        assert _is_safe_export_path(p) is False


# ------------------------------------------------------------------
# _sanitize_setting_key
# ------------------------------------------------------------------

from modules.app_api.routes.settings_routes import _sanitize_setting_key


class TestSanitizeSettingKey:
    def test_normal_key(self):
        assert _sanitize_setting_key("clip_model") == "clip_model"

    def test_path_traversal_stripped(self):
        assert _sanitize_setting_key("../../etc/passwd") == "etcpasswd"

    def test_dots_stripped(self):
        assert _sanitize_setting_key("some.key.name") == "somekeyname"

    def test_null_bytes_stripped(self):
        assert _sanitize_setting_key("key\x00evil") == "keyevil"

    def test_empty_after_strip(self):
        assert _sanitize_setting_key("../../../") == ""

    def test_spaces_stripped(self):
        assert _sanitize_setting_key("my key") == "mykey"


# ------------------------------------------------------------------
# WAL corrupted-line resilience
# ------------------------------------------------------------------

from modules.library.semantic.vector_index import VectorIndex

DIM = 8


def _random_vec(dim: int = DIM) -> list:
    return np.random.randn(dim).astype(np.float32).tolist()


def _make_wal_line(uid: str, dim: int = DIM) -> str:
    vec = np.random.randn(dim).astype(np.float32)
    vec_b64 = base64.b64encode(vec.tobytes()).decode("ascii")
    return json.dumps({"op": "add", "uid": uid, "vec_b64": vec_b64})


@pytest.fixture
def tmp_dir():
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestWALCorruptedLineResilience:
    def test_corrupted_lines_skipped_valid_replayed(self, tmp_dir):
        """Mix of valid + corrupted lines: valid entries replayed, corrupted skipped."""
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        idx.add("base", _random_vec())
        idx.save()

        # Manually write a WAL with good + bad lines
        wal_path = tmp_dir / "vector_wal.jsonl"
        lines = [
            _make_wal_line("good1"),
            "{truncated json",              # corrupted
            _make_wal_line("good2"),
            "",                              # empty line
            "not even close to json !!!",   # corrupted
            _make_wal_line("good3"),
        ]
        wal_path.write_text("\n".join(lines), encoding="utf-8")

        # Reload
        idx2 = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        assert idx2.count == 4  # base + good1 + good2 + good3

    def test_all_corrupted_no_crash(self, tmp_dir):
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        idx.add("base", _random_vec())
        idx.save()

        wal_path = tmp_dir / "vector_wal.jsonl"
        wal_path.write_text("bad1\nbad2\n{}\n", encoding="utf-8")

        idx2 = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        assert idx2.count == 1  # only base

    def test_wrong_dimension_skipped(self, tmp_dir):
        """WAL entry with wrong vector dimension is skipped."""
        idx = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        idx.add("base", _random_vec())
        idx.save()

        # Write WAL with wrong-dim vector
        wrong_vec = np.random.randn(DIM + 4).astype(np.float32)
        vec_b64 = base64.b64encode(wrong_vec.tobytes()).decode("ascii")
        bad_line = json.dumps({"op": "add", "uid": "wrong_dim", "vec_b64": vec_b64})
        good_line = _make_wal_line("correct_dim")

        wal_path = tmp_dir / "vector_wal.jsonl"
        wal_path.write_text(f"{bad_line}\n{good_line}\n", encoding="utf-8")

        idx2 = VectorIndex(dimension=DIM, index_dir=tmp_dir)
        assert idx2.count == 2  # base + correct_dim (wrong_dim skipped)
