"""Unit tests for artifact_store module."""

import os

import pytest
from modules.review_engine.artifact_store import ArtifactStore, LARGE_FILE_THRESHOLD
from modules.review_engine.exceptions import ArtifactNotFoundError
from modules.review_engine.review_store import ReviewStore


@pytest.fixture
def setup(tmp_path):
    """Create ArtifactStore + ReviewStore backed by temp dirs."""
    db_path = str(tmp_path / "test.db")
    project_dir = str(tmp_path / "project")
    os.makedirs(project_dir, exist_ok=True)

    review_store = ReviewStore(db_path)
    session_id = review_store.create_session(project_dir, "/v.mp4", "speech")
    artifact_store = ArtifactStore(project_dir, review_store)

    # Create a sample source file
    source_file = str(tmp_path / "render_output.mp4")
    with open(source_file, "wb") as f:
        f.write(b"fake video data " * 100)

    return {
        "store": artifact_store,
        "review_store": review_store,
        "session_id": session_id,
        "source_file": source_file,
        "tmp_path": tmp_path,
    }


class TestSaveAndGet:
    """Test saving and retrieving artifacts."""

    def test_artifact_store_save_and_get(self, setup):
        s = setup
        aid = s["store"].save(
            s["session_id"], 1, "transcode", "video", s["source_file"],
        )
        assert aid  # UUID string

        path = s["store"].get(s["session_id"], 1, "transcode")
        assert os.path.isfile(path)

        # Content matches
        with open(path, "rb") as f:
            content = f.read()
        with open(s["source_file"], "rb") as f:
            original = f.read()
        assert content == original

    def test_artifact_store_get_nonexistent_raises(self, setup):
        s = setup
        with pytest.raises(ArtifactNotFoundError):
            s["store"].get(s["session_id"], 99, "nothing")

    def test_artifact_store_save_source_not_found_raises(self, setup):
        s = setup
        with pytest.raises(FileNotFoundError):
            s["store"].save(s["session_id"], 1, "x", "video", "/nonexistent.mp4")

    def test_artifact_store_atomic_write_no_partial(self, setup):
        """Verify dest file is complete (no .tmp leftover)."""
        s = setup
        s["store"].save(s["session_id"], 1, "concat", "video", s["source_file"])

        artifacts_dir = os.path.join(
            s["store"]._artifacts_root, s["session_id"], "v1", "concat",
        )
        files = os.listdir(artifacts_dir)
        assert not any(f.endswith(".tmp") for f in files)
        assert len(files) == 1


class TestRollback:
    """Test artifact rollback."""

    def test_artifact_store_rollback_copies_artifacts(self, setup):
        s = setup
        s["store"].save(s["session_id"], 1, "transcode", "video", s["source_file"])
        s["store"].save(s["session_id"], 1, "loudnorm", "video", s["source_file"])

        copied = s["store"].rollback_artifacts(s["session_id"], 1, 3)
        assert copied == 2

        # Both artifacts exist in v3
        path1 = s["store"].get(s["session_id"], 3, "transcode")
        path2 = s["store"].get(s["session_id"], 3, "loudnorm")
        assert os.path.isfile(path1)
        assert os.path.isfile(path2)


class TestLargeFileSymlink:
    """Test symlink behavior for large files."""

    def test_artifact_store_large_file_uses_symlink(self, setup):
        s = setup
        # Create a file that looks large (we mock the threshold)
        large_file = str(s["tmp_path"] / "large.mp4")
        with open(large_file, "wb") as f:
            f.write(b"x" * 1024)

        import modules.review_engine.artifact_store as mod
        original_threshold = mod.LARGE_FILE_THRESHOLD
        mod.LARGE_FILE_THRESHOLD = 512  # Lower threshold for test
        try:
            s["store"].save(s["session_id"], 1, "bignode", "video", large_file)
            path = s["store"].get(s["session_id"], 1, "bignode")
            assert os.path.islink(path)
        finally:
            mod.LARGE_FILE_THRESHOLD = original_threshold
