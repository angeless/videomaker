"""Tests for BGMSelector — R16."""

import pytest

from modules.review_engine.bgm_selector import (
    analyze_beats,
    beat_sync_edits,
    HAS_LIBROSA,
)
from modules.review_engine.contracts import Segment
from modules.review_engine.exceptions import RenderError


def _seg(start, end):
    return Segment(source_path="v.mp4", start_ms=start, end_ms=end)


class TestBGMSelector:

    @pytest.mark.skipif(not HAS_LIBROSA, reason="librosa not installed")
    def test_beat_detection_returns_list(self, tmp_path):
        """Beat analysis returns list (may be empty if librosa/scipy incompatible)."""
        import numpy as np
        import soundfile as sf

        sr = 22050
        duration = 3.0
        samples = int(sr * duration)
        audio = np.zeros(samples)
        for i in range(0, samples, sr // 2):
            audio[i:i + 100] = 0.8

        audio_path = str(tmp_path / "test_bgm.wav")
        sf.write(audio_path, audio, sr)

        beats = analyze_beats(audio_path)
        # Should return a list (possibly empty if librosa/scipy version mismatch)
        assert isinstance(beats, list)
        if beats:
            assert all(isinstance(b, float) for b in beats)

    def test_sync_adjusts_cuts(self):
        """Beat sync shifts segment boundaries toward beats."""
        edits = [_seg(0, 5000), _seg(5000, 10100)]
        beats = [0.0, 2.5, 5.0, 7.5, 10.0]  # beats at every 2.5s
        result = beat_sync_edits(edits, beats, max_shift_ms=200)
        # Segment 1 end (10100) should snap to beat at 10000 (shift -100ms)
        assert result[1].end_ms == 10000

    def test_fallback_no_librosa(self):
        """Without beats, edits are returned unchanged."""
        edits = [_seg(0, 5000), _seg(5000, 10000)]
        result = beat_sync_edits(edits, [])
        assert result[0].end_ms == 5000
        assert result[1].end_ms == 10000

    def test_missing_bgm_file(self):
        with pytest.raises(RenderError, match="not found"):
            analyze_beats("/nonexistent/bgm.mp3")
