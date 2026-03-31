"""Unit tests for render_pipeline module."""

from unittest.mock import MagicMock, call, patch

import pytest
from modules.review_engine.contracts import Segment
from modules.review_engine.exceptions import RenderError
from modules.review_engine.render_pipeline import (
    _run_ffmpeg,
    render_rough_cut,
)


class TestRunFfmpeg:
    """Test FFmpeg runner with retries."""

    @patch("modules.review_engine.render_pipeline.subprocess.run")
    def test_render_pipeline_success_first_try(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")
        result = _run_ffmpeg(["ffmpeg", "-version"])
        assert result.returncode == 0

    @patch("modules.review_engine.render_pipeline.subprocess.run")
    def test_render_pipeline_retries_on_failure(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr=b"error1"),
            MagicMock(returncode=0, stderr=b""),
        ]
        result = _run_ffmpeg(["ffmpeg", "-version"], retries=3)
        assert result.returncode == 0
        assert mock_run.call_count == 2

    @patch("modules.review_engine.render_pipeline.subprocess.run")
    def test_render_pipeline_raises_after_all_retries(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"persistent error")
        with pytest.raises(RenderError, match="FFmpeg failed after 2 attempts"):
            _run_ffmpeg(["ffmpeg", "-broken"], retries=2)
        assert mock_run.call_count == 2

    @patch("modules.review_engine.render_pipeline.subprocess.run")
    def test_render_pipeline_handles_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10)
        with pytest.raises(RenderError, match="FFmpeg failed after"):
            _run_ffmpeg(["ffmpeg"], timeout=10, retries=1)


class TestRenderRoughCut:
    """Test rough cut rendering pipeline."""

    def test_render_pipeline_empty_edits_raises(self):
        with pytest.raises(RenderError, match="Empty EDITS"):
            render_rough_cut([], "/tmp/out.mp4")

    def test_render_pipeline_all_removed_raises(self):
        segs = [
            Segment(source_path="/v.mp4", start_ms=0, end_ms=5000, segment_type="removed"),
        ]
        with pytest.raises(RenderError, match="All segments removed"):
            render_rough_cut(segs, "/tmp/out.mp4")

    @patch("modules.review_engine.render_pipeline._get_duration", return_value=10.0)
    @patch("modules.review_engine.render_pipeline.shutil.move")
    @patch("modules.review_engine.render_pipeline._run_ffmpeg")
    @patch("modules.review_engine.render_pipeline._transcode_segment")
    @patch("modules.review_engine.render_pipeline._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("modules.review_engine.render_pipeline.os.path.getsize", return_value=1024000)
    def test_render_pipeline_calls_transcode_per_segment(
        self, mock_size, mock_ff, mock_transcode, mock_run, mock_move, mock_dur,
    ):
        mock_transcode.side_effect = lambda src, s, e, out, ff: out

        segs = [
            Segment(source_path="/v.mp4", start_ms=0, end_ms=3000, segment_type="keep"),
            Segment(source_path="/v.mp4", start_ms=5000, end_ms=8000, segment_type="keep"),
            Segment(source_path="/v.mp4", start_ms=8000, end_ms=10000, segment_type="removed"),
        ]

        result = render_rough_cut(segs, "/tmp/out.mp4", apply_loudnorm=False)

        assert mock_transcode.call_count == 2  # removed segment skipped
        assert result["video_path"] == "/tmp/out.mp4"
        assert result["duration_s"] == 10.0
        assert result["file_size_bytes"] == 1024000

    @patch("modules.review_engine.render_pipeline._get_duration", return_value=5.0)
    @patch("modules.review_engine.render_pipeline._run_ffmpeg")
    @patch("modules.review_engine.render_pipeline._transcode_segment")
    @patch("modules.review_engine.render_pipeline._find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("modules.review_engine.render_pipeline.os.path.getsize", return_value=500000)
    def test_render_pipeline_progress_callback(
        self, mock_size, mock_ff, mock_transcode, mock_run, mock_dur,
    ):
        mock_transcode.side_effect = lambda src, s, e, out, ff: out
        progress_calls = []

        segs = [
            Segment(source_path="/v.mp4", start_ms=0, end_ms=5000, segment_type="keep"),
        ]

        render_rough_cut(
            segs, "/tmp/out.mp4",
            apply_loudnorm=True,
            on_progress=lambda step, total, msg: progress_calls.append((step, total, msg)),
        )

        assert len(progress_calls) >= 2  # at least transcode + concat
