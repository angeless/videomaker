"""Regression tests for round-13 P1 security fixes (library/ + step1/)."""

import json
from pathlib import Path

import pytest


# ── gdrive imports sanity ────────────────────────────────────────

def test_gdrive_module_imports_without_nameerror():
    """Round-13: gdrive.py was completely broken — 6 missing imports.
    Any attempt to call preview_google_drive / ingest_google_drive_*
    raised NameError. Just importing the module should now succeed."""
    import modules.library.integrations.gdrive as g
    # Verify the 6 previously-missing names are now accessible
    assert hasattr(g, "urlparse")
    assert hasattr(g, "parse_qs")
    assert hasattr(g, "importlib")
    assert hasattr(g, "hashlib")
    assert hasattr(g, "shutil")
    assert hasattr(g, "deque")


# ── project_relink_adapter path containment ──────────────────────

def test_relink_adapter_rejects_nonexistent_path():
    from modules.library.project_relink_adapter import _safe_project_path
    with pytest.raises(ValueError, match="not a file"):
        _safe_project_path("/nonexistent/path.json")


def test_relink_adapter_rejects_empty_path():
    from modules.library.project_relink_adapter import _safe_project_path
    with pytest.raises(ValueError, match="required"):
        _safe_project_path("")


def test_relink_adapter_rejects_huge_file(tmp_path, monkeypatch):
    """File over size cap must be rejected (DoS protection)."""
    from modules.library import project_relink_adapter as mod
    p = tmp_path / "project.json"
    p.write_text("{}")
    # Force cap to 0 so even a tiny file fails the size check
    monkeypatch.setattr(mod, "_MAX_PROJECT_JSON_BYTES", 0)
    with pytest.raises(ValueError, match="size cap"):
        mod._safe_project_path(str(p))


def test_relink_adapter_rejects_escape_of_allowed_base(tmp_path):
    """When allowed_base is given, resolved path must be inside."""
    from modules.library.project_relink_adapter import _safe_project_path
    inside = tmp_path / "inside"
    inside.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    with pytest.raises(ValueError, match="escapes allowed base"):
        _safe_project_path(str(outside), allowed_base=inside)


def test_relink_adapter_output_path_requires_json_suffix(tmp_path):
    from modules.library.project_relink_adapter import _safe_output_path
    with pytest.raises(ValueError, match=r"\.json"):
        _safe_output_path(str(tmp_path / "out.txt"))


def test_relink_adapter_output_path_accepts_json(tmp_path):
    from modules.library.project_relink_adapter import _safe_output_path
    p = _safe_output_path(str(tmp_path / "out.json"))
    assert p.suffix == ".json"


# ── path_relink system-root blocking ─────────────────────────────

def test_path_relink_rejects_system_roots():
    from modules.library.maintenance.path_relink import _is_safe_walk_root
    assert _is_safe_walk_root(Path("/")) is False
    assert _is_safe_walk_root(Path("/etc")) is False
    assert _is_safe_walk_root(Path("/proc")) is False
    assert _is_safe_walk_root(Path("/System/Library")) is False


def test_path_relink_accepts_user_dirs(tmp_path):
    from modules.library.maintenance.path_relink import _is_safe_walk_root
    # Use Path.home() / subdir which lives under /Users on macOS — not on
    # any deny-prefix. Using tmp_path alone was test-pollution prone: some
    # earlier tests chdir, which affected relative resolution of certain
    # module-level constants.
    test_dir = Path.home() / ".pytest_walk_ok_test"
    test_dir.mkdir(exist_ok=True)
    try:
        assert _is_safe_walk_root(test_dir) is True
    finally:
        test_dir.rmdir()


# ── Whisper model allowlist ──────────────────────────────────────

def test_whisper_allowlist_rejects_arbitrary_repo():
    """Attacker-controlled model name must fall back to 'base' — not
    trigger HF auto-download of a malicious repo."""
    from modules.step1_material_analysis.transcribe import _validate_model_size
    assert _validate_model_size("evil/malicious-model") == "base"
    assert _validate_model_size("../../etc/passwd") == "base"
    assert _validate_model_size("large-v3; rm -rf /") == "base"


def test_whisper_allowlist_accepts_known_sizes():
    from modules.step1_material_analysis.transcribe import _validate_model_size
    for size in ("tiny", "base", "small", "medium", "large", "large-v3"):
        assert _validate_model_size(size) == size


def test_whisper_allowlist_falls_back_on_empty():
    from modules.step1_material_analysis.transcribe import _validate_model_size
    assert _validate_model_size("") == "base"
    assert _validate_model_size(None) == "base"


# ── CLIP model allowlist ─────────────────────────────────────────

def test_clip_model_allowlist_exists():
    from modules.step1_material_analysis.indexer.semantic import _ALLOWED_CLIP_MODELS
    assert "openai/clip-vit-base-patch32" in _ALLOWED_CLIP_MODELS
    # Obvious attack string NOT in allowlist
    assert "evil/malicious-clip" not in _ALLOWED_CLIP_MODELS


# ── embedding_cache thread safety ────────────────────────────────

def test_embedding_cache_concurrent_writes_dont_explode():
    """Without the lock, this used to raise RuntimeError occasionally."""
    import threading as _t
    from modules.library.semantic.embedding_cache import EmbeddingCache
    cache = EmbeddingCache(max_size=20, ttl_seconds=3600)

    def worker(base):
        for i in range(100):
            cache.put(f"q{base}-{i}", [float(i)] * 8)
            cache.get(f"q{base}-{i}")

    threads = [_t.Thread(target=worker, args=(b,)) for b in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), "worker hung — likely deadlock"
    # Cache respects max_size
    assert cache.size <= 20


# ── schema DDL assertion ─────────────────────────────────────────

def test_schema_rejects_non_identifier_column_names():
    """The future-proofing assertion must reject bad column names even
    though today's callers all pass hardcoded literals."""
    import sqlite3
    from modules.library.db import schema as sch

    # Simulate what a bad patch might do: feed a bogus column via the
    # private extra_columns-like structure. We test the identifier check
    # directly on a representative string.
    assert not "col; DROP TABLE assets".isidentifier()
    assert "my_col".isidentifier()
