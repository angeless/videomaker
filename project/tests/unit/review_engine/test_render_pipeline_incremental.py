"""Tests for render_incremental — R9."""

import pytest

from modules.review_engine.exceptions import RenderError
from modules.review_engine.render_pipeline import render_incremental


class TestRenderIncremental:

    def test_cached_skip(self):
        """Skip nodes load from artifact cache."""
        class MockStore:
            def load(self, key):
                return {"data": f"cached_{key}"}
            def save(self, key, data):
                pass

        plan = {"run": [], "skip": ["thumbnails", "waveform"]}
        results = render_incremental(plan, {}, artifact_store=MockStore())
        assert results["thumbnails"]["data"] == "cached_thumbnails"
        assert results["waveform"]["data"] == "cached_waveform"

    def test_incremental_run(self):
        """Run nodes execute their runners and save artifacts."""
        saved = {}

        class MockStore:
            def load(self, key):
                return None
            def save(self, key, data):
                saved[key] = data

        runners = {
            "transcode": lambda: {"path": "/tmp/tc.mp4"},
            "analyze": lambda: {"type": "speech"},
        }
        plan = {"run": ["transcode", "analyze"], "skip": []}
        results = render_incremental(plan, runners, artifact_store=MockStore())
        assert results["transcode"]["path"] == "/tmp/tc.mp4"
        assert saved["transcode"]["path"] == "/tmp/tc.mp4"

    def test_failure_cascade(self):
        """A failing node raises RenderError."""
        def fail_runner():
            raise RuntimeError("FFmpeg crashed")

        runners = {"transcode": fail_runner}
        plan = {"run": ["transcode"], "skip": []}
        with pytest.raises(RenderError, match="transcode.*failed"):
            render_incremental(plan, runners)

    def test_progress_callback(self):
        """Progress callback is called for each node."""
        progress_calls = []

        def on_progress(node, status, pct):
            progress_calls.append((node, status))

        runners = {"x": lambda: "ok"}
        plan = {"run": ["x"], "skip": ["y"]}

        class MockStore:
            def load(self, key):
                return "cached"
            def save(self, key, data):
                pass

        render_incremental(plan, runners, artifact_store=MockStore(), on_progress=on_progress)
        statuses = [s for _, s in progress_calls]
        assert "skipped" in statuses
        assert "done" in statuses or "running" in statuses
